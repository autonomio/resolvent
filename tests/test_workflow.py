"""Live-reference safety and delivery regressions; no LLM behavior is simulated."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from urllib.request import Request

from skills.resolvent.scripts.load_workflow import (
    INDEX_URL, MAX_FILE, NoRedirect, blob_sha, file_url, load, parse_manifest,
    validate_manifest, verify_connector_metadata, verify_file,
)
from scripts.workflow_release import manifest, previous_manifest
from scripts.plugin_release import check_version, prepare
import test_plugin_release as release_fixtures


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.data = b'# Synthetic workflow\nNo research data.\n'
        self.record = {
            'format_version':'1.0', 'client_protocol':'1.0', 'workflow_version':'1.0.0',
            'source_commit':'a'*40, 'entrypoint':'WORKFLOW.md',
            'files':{'WORKFLOW.md':{'sha256':hashlib.sha256(self.data).hexdigest(),
                                     'git_blob_sha1':blob_sha(self.data), 'size':len(self.data)}}}

    def test_load_resolves_the_channel_once_and_uses_only_immutable_urls(self):
        calls = []
        def reader(url, limit):
            calls.append(url)
            if url == INDEX_URL:
                self.assertEqual(calls, [INDEX_URL])
                return json.dumps(self.record).encode()
            self.assertEqual(url, file_url(self.record, 'WORKFLOW.md'))
            self.assertEqual(limit, len(self.data))
            return self.data
        result = load(reader)
        self.assertEqual(result['files']['WORKFLOW.md'], self.data.decode())
        self.assertEqual(len(calls), 2)

    def test_wrong_bytes_length_or_digest_fail_before_returning_instructions(self):
        for data in (self.data+b'!', self.data.replace(b'Synthetic', b'Malicious'), self.data[:-1]):
            with self.subTest(data=data), self.assertRaisesRegex(ValueError, 'does not match'):
                load(lambda url, limit: json.dumps(self.record).encode() if url == INDEX_URL else data)
        for field in ('sha256','git_blob_sha1'):
            bad = copy.deepcopy(self.record)
            bad['files']['WORKFLOW.md'][field] = '0' * len(bad['files']['WORKFLOW.md'][field])
            with self.subTest(field=field), self.assertRaises(ValueError):
                verify_file(bad, 'WORKFLOW.md', self.data)

    def test_unexpected_authority_fields_and_incompatible_client_fail_closed(self):
        for key, value in (('permissions',['write']), ('destination','somewhere/world'),
                           ('format_version','2.0'), ('client_protocol','2.0'),
                           ('source_commit','main'), ('entrypoint',{}), ('workflow_version','1.01.0')):
            bad = copy.deepcopy(self.record)
            bad[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_manifest(bad)

    def test_no_unlisted_encoded_absolute_or_traversing_paths(self):
        for path in ('../WORKFLOW.md','/WORKFLOW.md','x/../WORKFLOW.md','x\\WORKFLOW.md',
                     'https://other.invalid/x.md','x/%2e%2e/file.md','x//file.md','run.py'):
            bad = copy.deepcopy(self.record)
            bad['entrypoint'] = path
            bad['files'] = {path:bad['files']['WORKFLOW.md']}
            with self.subTest(path=path), self.assertRaises(ValueError):
                validate_manifest(bad)
        with self.assertRaises(ValueError):
            file_url(self.record, 'unlisted.md')

    def test_duplicates_partial_utf8_and_size_limits_are_rejected(self):
        for data in (b'{"files":{},"files":{}}', b'{"files":', b'\xff', b' '*65537):
            with self.subTest(data=data[:30]), self.assertRaises(ValueError):
                parse_manifest(data)
        for size in (True, -1, 0, MAX_FILE+1, '20'):
            bad = copy.deepcopy(self.record)
            bad['files']['WORKFLOW.md']['size'] = size
            with self.subTest(size=size), self.assertRaises(ValueError):
                validate_manifest(bad)
        bad = copy.deepcopy(self.record)
        bad['files'] = {f'f{i}.md':dict(bad['files']['WORKFLOW.md'], size=MAX_FILE) for i in range(5)}
        bad['entrypoint'] = 'f0.md'
        with self.assertRaises(ValueError):
            validate_manifest(bad)

    def test_no_redirect_can_change_the_reference_source(self):
        for code in (301,302,303,307,308):
            with self.subTest(code=code), self.assertRaisesRegex(ValueError, 'redirect'):
                NoRedirect().redirect_request(Request(INDEX_URL), None, code, 'moved', {}, 'https://other.invalid')

    def test_native_connector_identity_needs_the_expected_regular_blob_and_size(self):
        entry = {'type':'blob','mode':'100644','sha':blob_sha(self.data),'size':len(self.data)}
        verify_connector_metadata(self.record, 'WORKFLOW.md', entry)
        for mutation in ({'mode':'120000'}, {'type':'commit'}, {'sha':'0'*40}, {'size':1}, {'size':True}):
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                verify_connector_metadata(self.record, 'WORKFLOW.md', dict(entry, **mutation))

    def test_network_failure_returns_no_partial_workflow(self):
        def reader(url, limit):
            if url == INDEX_URL:
                return json.dumps(self.record).encode()
            raise OSError('Synthetic unavailable source')
        with self.assertRaises(OSError):
            load(reader)


class WorkflowReleaseTests(unittest.TestCase):
    def setUp(self):
        # Reuse the real committed publication fixture without inheriting/rerunning its tests.
        self.fixture = release_fixtures.ReleaseTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.git = self.fixture.git
        self.directory = Path(self.fixture.temp.name)
        config = json.loads((self.root/'workflows/resolvent/workflow.json').read_text())
        major, minor, patch = map(int, config['workflow_version'].split('.'))
        self.next_version = f'{major}.{minor}.{patch+1}'
        self.future_version = f'{major+1}.0.0'

    def publish(self, name, previous=None, previous_workflow=None):
        output = self.directory / name
        result = prepare(self.root, output, previous, previous_workflow)
        return (result, json.loads((output/'plugin/release.json').read_text()),
                json.loads((output/'workflow/workflow.json').read_text()), output)

    def update_reference(self, bump=True):
        path = self.root/'workflows/resolvent/WORKFLOW.md'
        path.write_text(path.read_text()+'\nSynthetic workflow-only improvement.\n')
        if bump:
            path = self.root/'workflows/resolvent/workflow.json'
            config = json.loads(path.read_text())
            config['workflow_version'] = self.next_version
            path.write_text(json.dumps(config))

    def test_install_once_then_update_references_without_changing_the_plugin_zip(self):
        first, plugin, workflow, old = self.publish('first')
        self.update_reference()
        self.git('add','workflows')
        self.git('commit','-qm','Synthetic workflow update')
        check_version(self.root, self.fixture.base)
        result, same_plugin, current, new = self.publish('second', plugin, workflow)
        self.assertEqual(result['changed'], 'false')
        self.assertEqual(result['workflow_changed'], 'true')
        self.assertEqual(same_plugin, plugin)
        self.assertEqual(current['workflow_version'], self.next_version)
        self.assertEqual(current['source_commit'], self.git('rev-parse','HEAD'))
        for path in (old/'assets').iterdir():
            self.assertEqual(path.read_bytes(), (new/'assets'/path.name).read_bytes(), path.name)
        def reader(url, limit):
            if url == INDEX_URL:
                return (new/'workflow/workflow.json').read_bytes()
            relative = url.split('/workflows/resolvent/',1)[1]
            return (new/'workflow/workflows/resolvent'/relative).read_bytes()
        loaded = load(reader)
        self.assertIn('Synthetic workflow-only improvement.', loaded['files']['WORKFLOW.md'])

    def test_data_only_commit_and_retries_preserve_both_source_revisions(self):
        _, plugin, workflow, _ = self.publish('first')
        (self.root/'claims').mkdir()
        (self.root/'claims/C-fixture.yaml').write_text('Synthetic data only.\n')
        self.git('add','claims')
        self.git('commit','-qm','Data only')
        result, same_plugin, same_workflow, output = self.publish('again', plugin, workflow)
        self.assertEqual(result['workflow_changed'], 'false')
        self.assertEqual(same_plugin, plugin)
        self.assertEqual(same_workflow, workflow)
        self.assertFalse((output/'plugin/claims').exists())

    def test_unversioned_updates_rollbacks_and_uncommitted_source_cannot_publish(self):
        _, plugin, workflow, _ = self.publish('first')
        self.update_reference(bump=False)
        with self.assertRaisesRegex(ValueError, 'bump'):
            manifest(self.root, self.git('rev-parse','HEAD'), workflow)
        with self.assertRaisesRegex(ValueError, 'bump'):
            check_version(self.root, self.fixture.base)
        self.update_reference(bump=True)
        with self.assertRaisesRegex(ValueError, 'pinned source'):
            self.publish('dirty', plugin, workflow)
        future = copy.deepcopy(workflow)
        future['workflow_version'] = self.future_version
        with self.assertRaisesRegex(ValueError, 'back'):
            manifest(self.root, self.git('rev-parse','HEAD'), future)

    def test_symlinks_and_unexpected_source_files_cannot_enter_a_workflow(self):
        folder = self.root/'workflows/resolvent'
        (folder/'leak.md').symlink_to(self.root/'plugin.json')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            manifest(self.root, self.git('rev-parse','HEAD'))
        (folder/'leak.md').unlink()
        (folder/'payload.py').write_text('No execution allowed.\n')
        with self.assertRaisesRegex(ValueError, 'path'):
            manifest(self.root, self.git('rev-parse','HEAD'))

    def test_existing_unrecognized_channel_is_not_silently_replaced(self):
        self.git('update-ref', 'refs/remotes/origin/workflow-release', self.fixture.base)
        with self.assertRaisesRegex(ValueError, 'no valid manifest'):
            previous_manifest(self.root)


if __name__ == '__main__':
    unittest.main()
