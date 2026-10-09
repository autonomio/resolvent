"""Distribution regressions: compatibility, integrity and generic routing."""
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile
from scripts.package_plugin import distributions, plugin_files
from scripts.package_skill import ROOT, archive_bytes, build


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for relative in ('plugin.json', '.codex-plugin', '.claude-plugin', 'assets', 'skills', 'docs/schemas', 'docs/PLUGIN_README.md', 'verification'):
            source, target = ROOT / relative, self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, target, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            else:
                shutil.copy2(source, target)

    def mutate_json(self, relative, mutation):
        path = self.root / relative
        value = json.loads(path.read_text())
        mutation(value)
        path.write_text(json.dumps(value))

    def test_two_hosts_install_the_same_skill_and_protocol(self):
        artifacts = distributions(self.root)
        self.assertEqual(len(artifacts), 2)
        self.assertEqual(len(set(artifacts.values())), 1)
        with zipfile.ZipFile(io.BytesIO(next(iter(artifacts.values())))) as archive:
            self.assertIsNone(archive.testzip())
            for path in ('plugin.json', '.codex-plugin/plugin.json', '.claude-plugin/plugin.json', 'skills/resolvent/SKILL.md', 'assets/resolvent.png'):
                self.assertIn('resolvent/' + path, archive.namelist())
            self.assertEqual(archive.read('resolvent/skills/resolvent/references/submission.schema.json'), (self.root / 'docs/schemas/submission.schema.json').read_bytes())
            self.assertFalse(any('portal_context' in path for path in archive.namelist()))

    def test_reproducibility_ignores_filesystem_timestamp(self):
        first = distributions(self.root)
        os.utime(self.root / 'skills/resolvent/SKILL.md', (1, 1))
        self.assertEqual(first, distributions(self.root))

    def test_versions_cannot_drift_between_hosts(self):
        self.mutate_json('.claude-plugin/plugin.json', lambda value: value.update(version='9.0.0'))
        with self.assertRaisesRegex(ValueError, 'Host manifests differ'):
            distributions(self.root)

    def test_schema_drift_cannot_ship_silently(self):
        (self.root / 'skills/resolvent/references/submission.schema.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'repository protocol'):
            build(self.root)

    def test_archive_paths_cannot_escape_the_package(self):
        for path in ('../secret', '/secret', 'folder/../../secret', 'folder\\secret'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                archive_bytes({path: b'data'})

    def test_symlink_cannot_import_unselected_data(self):
        (self.root / 'skills/resolvent/leak').symlink_to(self.root / 'plugin.json')
        with self.assertRaisesRegex(ValueError, 'symlinks'):
            build(self.root)

    def test_private_binding_is_rejected_in_compatibility_manifest(self):
        self.mutate_json('.codex-plugin/plugin.json', lambda value: value.update(apps='./.app.json'))
        with self.assertRaisesRegex(ValueError, 'private app bindings'):
            plugin_files(self.root)

    def test_organization_coupling_is_rejected(self):
        target = self.root / 'skills/resolvent/references/TARGET.md'
        target.write_text(target.read_text() + '\nUse velocinbio/Resolvent.\n')
        with self.assertRaisesRegex(ValueError, 'Organization-specific'):
            distributions(self.root)

    def test_missing_icon_is_rejected(self):
        (self.root / 'assets/resolvent.png').unlink()
        with self.assertRaisesRegex(ValueError, 'icon'):
            plugin_files(self.root)


if __name__ == '__main__':
    unittest.main()
