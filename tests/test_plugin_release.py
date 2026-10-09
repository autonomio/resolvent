"""Release regressions: changed-version gates, retries and isolated publishing."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile

from scripts.package_skill import ROOT
from scripts.plugin_release import check_version, prepare, release_record


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'source'
        self.root.mkdir()
        for relative in ('plugin.json', '.codex-plugin', '.claude-plugin', '.agents',
                         'assets', 'skills', 'docs/schemas', 'docs/PLUGIN_README.md', 'verification',
                         'scripts/package_plugin.py', 'scripts/package_skill.py'):
            source, destination = ROOT / relative, self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, destination, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            else:
                shutil.copy2(source, destination)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Release test')
        self.git('config', 'user.email', 'release-test@example.invalid')
        self.git('add', '.')
        self.git('commit', '-qm', 'Baseline plugin')
        self.base = self.git('rev-parse', 'HEAD')
        self.version = json.loads((self.root / 'plugin.json').read_text())['version']

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.root, text=True).strip()

    def test_changed_instructions_require_a_version_bump(self):
        path = self.root / 'skills/resolvent/SKILL.md'
        path.write_text(path.read_text() + '\nChanged workflow.\n')
        with self.assertRaisesRegex(ValueError, 'bump'):
            check_version(self.root, self.base)

    def test_packagers_and_catalogs_require_a_version_bump(self):
        for relative in ('scripts/package_plugin.py', 'scripts/package_skill.py',
                         '.agents/plugins/marketplace.json', '.claude-plugin/marketplace.json'):
            with self.subTest(path=relative):
                path = self.root / relative
                original = path.read_bytes()
                path.write_bytes(original + b'\n')
                with self.assertRaisesRegex(ValueError, 'bump'):
                    check_version(self.root, self.base)
                path.write_bytes(original)

    def test_world_model_data_does_not_require_a_plugin_release(self):
        (self.root / 'claims').mkdir()
        (self.root / 'claims/C-test.yaml').write_text('statement: test\n')
        self.git('add', 'claims')
        self.git('commit', '-qm', 'Data only')
        check_version(self.root, self.base)
        output = Path(self.temp.name) / 'first'
        prepare(self.root, output, None)
        record = json.loads((output / 'plugin/release.json').read_text())
        (self.root / 'claims/C-test.yaml').write_text('statement: revised test\n')
        self.git('commit', '-qam', 'More data only')
        second = prepare(self.root, Path(self.temp.name) / 'second', record)
        self.assertEqual(second['changed'], 'false')
        self.assertEqual(second['source_commit'], record['source_commit'])

    def set_version(self, version):
        for relative in ('plugin.json', '.codex-plugin/plugin.json', '.claude-plugin/plugin.json'):
            path = self.root / relative
            manifest = json.loads(path.read_text())
            manifest['version'] = version
            path.write_text(json.dumps(manifest))
        path = self.root / 'skills/resolvent/SKILL.md'
        path.write_text(path.read_text().replace('version: "' + self.version + '"', 'version: "' + version + '"'))

    def test_synchronized_version_bump_is_accepted(self):
        self.set_version('2.0.0')
        check_version(self.root, self.base)

    def test_versioned_catalog_change_reaches_the_release_branch(self):
        first = Path(self.temp.name) / 'first'
        prepare(self.root, first, None)
        previous = json.loads((first / 'plugin/release.json').read_text())
        relative = '.claude-plugin/marketplace.json'
        path = self.root / relative
        catalog = json.loads(path.read_text())
        catalog['plugins'][0]['description'] = 'Updated public catalog listing'
        path.write_text(json.dumps(catalog))
        self.set_version('2.0.0')
        check_version(self.root, self.base)
        second = Path(self.temp.name) / 'second'
        result = prepare(self.root, second, previous)
        self.assertEqual(result['changed'], 'true')
        published = json.loads((second / 'plugin' / relative).read_text())
        self.assertEqual(published['plugins'][0]['description'], 'Updated public catalog listing')

    def test_first_portable_release_can_start_at_one(self):
        self.git('rm', 'plugin.json')
        self.git('commit', '-qm', 'Template before portable plugin')
        template = self.git('rev-parse', 'HEAD')
        (self.root / 'plugin.json').write_bytes((ROOT / 'plugin.json').read_bytes())
        check_version(self.root, template)

    def test_published_version_cannot_change_bytes(self):
        record, _ = release_record('1.0.0', b'old', self.base, None)
        with self.assertRaisesRegex(ValueError, 'different bytes'):
            release_record('1.0.0', b'new', self.base, record)

    def test_stale_validation_cannot_roll_back_publication(self):
        record, _ = release_record('2.0.0', b'new', self.base, None)
        with self.assertRaisesRegex(ValueError, 'roll'):
            release_record('1.0.0', b'old', self.base, record)

    def test_release_retry_preserves_provenance(self):
        record, changed = release_record('1.0.0', b'plugin', self.base, None)
        retry, changed_again = release_record('1.0.0', b'plugin', 'a' * 40, record)
        self.assertTrue(changed)
        self.assertFalse(changed_again)
        self.assertEqual(retry, record)

    def test_branch_and_assets_contain_only_the_plugin(self):
        (self.root / 'claims').mkdir()
        (self.root / 'claims/private.yaml').write_text('private: data\n')
        output = Path(self.temp.name) / 'publication'
        plan = prepare(self.root, output, None)
        self.assertEqual(plan['changed'], 'true')
        self.assertFalse((output / 'plugin/claims').exists())
        self.assertFalse((output / 'plugin/AGENTS.md').exists())
        self.assertTrue((output / 'plugin/README.md').exists())
        for catalog_path in ('.claude-plugin/marketplace.json', '.agents/plugins/marketplace.json'):
            catalog = json.loads((output / 'plugin' / catalog_path).read_text())
            expected = './' if catalog_path.startswith('.claude') else {'source': 'local', 'path': './'}
            self.assertEqual(catalog['plugins'][0]['source'], expected)
        chatgpt = (output / 'assets' / f'resolvent-chatgpt-{self.version}.zip').read_bytes()
        claude = (output / 'assets' / f'resolvent-claude-{self.version}.zip').read_bytes()
        self.assertEqual(chatgpt, claude)
        record = json.loads((output / 'assets/release.json').read_text())
        self.assertEqual(record['plugin_sha256'], hashlib.sha256(chatgpt).hexdigest())
        with zipfile.ZipFile(output / 'assets' / f'resolvent-chatgpt-{self.version}.zip') as archive:
            self.assertIsNone(archive.testzip())
        for line in (output / 'assets/SHA256SUMS').read_text().splitlines():
            digest, filename = line.split('  ')
            self.assertEqual(digest, hashlib.sha256((output / 'assets' / filename).read_bytes()).hexdigest())


if __name__ == '__main__':
    unittest.main()
