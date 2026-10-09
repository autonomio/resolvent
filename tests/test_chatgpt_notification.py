"""Publisher notices require available assets and survive CI retries safely."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from scripts.notify_chatgpt_release import notify, send_resend, REPOSITORY, UPDATE_URL


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 9, tzinfo=timezone.utc)
        self.tag = 'resolvent-v1.0.0'
        self.download = f'https://github.com/{REPOSITORY}/releases/download/{self.tag}/resolvent-chatgpt-1.0.0.zip'
        self.release = {'tag_name': self.tag, 'published_at': self.now.isoformat(),
                        'prerelease': False,
                        'html_url': f'https://github.com/{REPOSITORY}/releases/tag/{self.tag}',
                        'assets': [{'name': 'resolvent-chatgpt-1.0.0.zip',
                                    'browser_download_url': self.download, 'size': 1234}]}
        self.config = {'RESEND_API_KEY': 'test-key', 'RESOLVENT_NOTIFY_TO': 'recipient@example.invalid',
                       'RESOLVENT_NOTIFY_FROM': 'Resolvent <sender@example.invalid>'}
        self.persist = Mock()
        self.send = Mock(return_value='provider-message-id')

    def notify(self, receipt=None, **kwargs):
        return notify(self.release, receipt, self.config, self.persist, self.send, now=self.now, **kwargs)

    def test_notice_follows_durable_intent_and_has_action_links(self):
        calls = []
        self.persist.side_effect = lambda record: calls.append(record['status'])
        self.send.side_effect = lambda *args: calls.append('send') or 'provider-message-id'
        self.assertTrue(self.notify())
        self.assertEqual(calls, ['pending', 'send', 'accepted'])
        payload, _, key = self.send.call_args.args
        self.assertIn(self.download, payload['text'])
        self.assertIn(UPDATE_URL, payload['text'])
        self.assertIn('1.0.0', payload['subject'])
        self.assertEqual(key, f'{REPOSITORY}/chatgpt-update/{self.tag}')

    def test_accepted_notice_skips_on_retries_and_data_only_runs(self):
        self.notify()
        accepted = self.persist.call_args.args[0]
        self.persist.reset_mock()
        self.send.reset_mock()
        self.assertFalse(notify(self.release, accepted, {}, self.persist, self.send, self.now))
        self.persist.assert_not_called()
        self.send.assert_not_called()

    def test_pending_retry_uses_same_key_and_payload(self):
        self.notify()
        pending = self.persist.call_args_list[0].args[0]
        first = self.send.call_args.args
        self.now += timedelta(hours=1)
        self.assertTrue(self.notify(pending))
        self.assertEqual(self.send.call_args.args, first)

    def test_expired_or_changed_pending_notice_requires_inspection(self):
        self.notify()
        pending = self.persist.call_args_list[0].args[0]
        self.send.reset_mock()
        self.config['RESOLVENT_NOTIFY_TO'] = 'changed@example.invalid'
        with self.assertRaisesRegex(ValueError, 'payload changed'):
            self.notify(pending)
        self.config['RESOLVENT_NOTIFY_TO'] = 'recipient@example.invalid'
        self.now += timedelta(hours=23)
        with self.assertRaisesRegex(ValueError, 'safe retry window'):
            self.notify(pending)
        self.send.assert_not_called()

    def test_unavailable_unstable_or_missing_archive_never_sends(self):
        for change in ({'published_at': None}, {'prerelease': True}, {'assets': []}):
            with self.subTest(change=change):
                release = {**deepcopy(self.release), **change}
                with self.assertRaises(ValueError):
                    notify(release, None, self.config, self.persist, self.send, self.now)
        self.send.assert_not_called()
        self.persist.assert_not_called()

    def test_missing_configuration_does_not_record_an_attempt(self):
        self.config.pop('RESEND_API_KEY')
        with self.assertRaisesRegex(ValueError, 'Configure'):
            self.notify()
        self.persist.assert_not_called()
        self.send.assert_not_called()

    def test_provider_failure_retains_pending_intent_only(self):
        self.send.side_effect = ValueError('provider rejected')
        with self.assertRaisesRegex(ValueError, 'provider rejected'):
            self.notify()
        self.assertEqual([c.args[0]['status'] for c in self.persist.call_args_list], ['pending'])

    def test_provider_accepts_identified_client_and_preserves_retry_request(self):
        def provider(request, timeout):
            agent = request.get_header('User-agent', '')
            if not agent or agent.startswith('Python-urllib/'):
                raise HTTPError(request.full_url, 403, 'Forbidden', {}, BytesIO(b'error code: 1010'))
            self.assertEqual(request.full_url, 'https://api.resend.com/emails')
            self.assertEqual(request.get_method(), 'POST')
            self.assertEqual(request.get_header('Authorization'), 'Bearer test-key')
            self.assertEqual(request.get_header('Idempotency-key'), 'release-retry-key')
            self.assertEqual(json.loads(request.data), payload)
            self.assertEqual(timeout, 30)
            return BytesIO(b'{"id":"provider-message-id"}')

        payload = {'from': 'sender@example.invalid', 'to': ['recipient@example.invalid'],
                   'subject': 'Update ready', 'text': 'Download the published release'}
        with patch('scripts.notify_chatgpt_release.urlopen', side_effect=provider):
            self.assertEqual(send_resend(payload, 'test-key', 'release-retry-key'), 'provider-message-id')

    def test_journal_failure_prevents_external_send(self):
        self.persist.side_effect = ValueError('cannot record intent')
        with self.assertRaisesRegex(ValueError, 'record intent'):
            self.notify()
        self.send.assert_not_called()

    def test_unexpected_download_or_publisher_url_is_rejected(self):
        self.release['assets'][0]['browser_download_url'] = 'https://example.invalid/file.zip'
        with self.assertRaisesRegex(ValueError, 'unexpected URL'):
            self.notify()
        self.release['assets'][0]['browser_download_url'] = self.download
        self.config['CHATGPT_PLUGIN_UPDATE_URL'] = UPDATE_URL + '.example.invalid'
        with self.assertRaisesRegex(ValueError, 'official'):
            self.notify()
        self.send.assert_not_called()


if __name__ == '__main__':
    unittest.main()
