from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from scripts.reconcile_plugin_assets import reconcile


class AssetRecoveryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.assets = Path(directory.name)
        for name in ('chatgpt.zip', 'claude.zip', 'release.json', 'SHA256SUMS'):
            (self.assets / name).write_bytes(name.encode())
        self.download = Mock(side_effect=lambda name: name.encode())
        self.upload = Mock()

    def test_partial_publication_uploads_only_missing_assets(self):
        uploaded = reconcile(self.assets, {'chatgpt.zip', 'release.json'}, self.download, self.upload)
        self.assertEqual(uploaded, ['SHA256SUMS', 'claude.zip'])
        self.assertEqual({call.args[0].name for call in self.upload.call_args_list}, set(uploaded))
        self.assertEqual({call.args[0] for call in self.download.call_args_list}, {'chatgpt.zip', 'release.json'})

    def test_complete_release_is_read_only_and_ignores_notification_journal(self):
        existing = {path.name for path in self.assets.iterdir()} | {'chatgpt-notification.json'}
        self.assertEqual(reconcile(self.assets, existing, self.download, self.upload), [])
        self.upload.assert_not_called()

    def test_mismatched_existing_asset_blocks_all_repair_uploads(self):
        self.download.return_value = b'wrong'
        self.download.side_effect = None
        with self.assertRaisesRegex(ValueError, 'differs'):
            reconcile(self.assets, {'release.json'}, self.download, self.upload)
        self.upload.assert_not_called()

    def test_upload_failure_propagates_for_a_later_retry(self):
        self.upload.side_effect = RuntimeError('upload failed')
        with self.assertRaisesRegex(RuntimeError, 'upload failed'):
            reconcile(self.assets, set(), self.download, self.upload)


if __name__ == '__main__':
    unittest.main()
