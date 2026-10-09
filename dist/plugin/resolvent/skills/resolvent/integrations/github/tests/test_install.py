import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('resolvent_installer', HERE / 'install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='resolvent-install-', dir=Path.cwd())
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / 'repository'
        self.repo.mkdir()
        (self.repo / '.git').mkdir()

    def install(self, dry_run=False):
        with contextlib.redirect_stdout(io.StringIO()):
            return installer.install(self.repo, dry_run)

    def test_dry_run_makes_no_changes(self):
        (self.repo / 'AGENTS.md').write_bytes(b'Original rules\r\n')
        self.install(dry_run=True)
        self.assertEqual((self.repo / 'AGENTS.md').read_bytes(), b'Original rules\r\n')
        self.assertEqual({p.name for p in self.repo.iterdir()}, {'.git', 'AGENTS.md'})

    def test_install_preserves_instructions_and_stays_disabled(self):
        agents, claude = b'Existing instructions\r\nKeep them.\r\n', b'Original Claude rules, no final newline'
        (self.repo / 'AGENTS.md').write_bytes(agents)
        (self.repo / 'CLAUDE.md').write_bytes(claude)
        self.install()
        self.assertTrue((self.repo / 'AGENTS.md').read_bytes().startswith(agents))
        self.assertTrue((self.repo / 'CLAUDE.md').read_bytes().startswith(claude))
        installed = self.repo / '.github/resolvent'
        self.assertIs(json.loads((installed / 'policy.json').read_text())['enabled'], False)
        self.assertEqual(json.loads((installed / 'policy.json').read_text())['authoring_owner'], 'originating_task')
        for name in ('PR_FOLLOWUP.md', 'SUBMISSION.md', 'GITHUB_ACCESS.md', 'ADMISSION.md', 'MERGE.md', 'CONTINUATION.md', 'TARGET.md'):
            self.assertEqual((installed / name).read_bytes(), (installer.BUNDLE_ROOT / 'references' / name).read_bytes())
        result = subprocess.run([sys.executable, str(installed / 'controller.py'), 'validate-policy'], cwd=self.repo, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('enabled=false', result.stdout)

    def test_second_identical_install_is_idempotent(self):
        self.install()
        before = {p.relative_to(self.repo): p.read_bytes() for p in self.repo.rglob('*') if p.is_file()}
        operations = self.install()
        after = {p.relative_to(self.repo): p.read_bytes() for p in self.repo.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        self.assertTrue(all(op[0] == 'unchanged' for op in operations))

    def test_changed_policy_is_preserved_and_blocks_install_before_writes(self):
        target = self.repo / '.github/resolvent'
        target.mkdir(parents=True)
        original = b'{"customized":true}\n'
        (target / 'policy.json').write_bytes(original)
        with self.assertRaisesRegex(ValueError, 'Existing file differs'):
            self.install()
        self.assertEqual((target / 'policy.json').read_bytes(), original)
        self.assertFalse((target / 'controller.py').exists())
        self.assertFalse((self.repo / 'AGENTS.md').exists())

    def test_old_instruction_block_requires_review_instead_of_conflicting_append(self):
        original = b'Original policy\n<!-- resolvent-followup:1.1.0 -->\nPrior follow-up instructions\n'
        (self.repo / 'AGENTS.md').write_bytes(original)
        with self.assertRaisesRegex(ValueError, 'another version'):
            self.install()
        self.assertEqual((self.repo / 'AGENTS.md').read_bytes(), original)
        self.assertFalse((self.repo / '.github').exists())
        self.assertFalse((self.repo / 'CLAUDE.md').exists())

    def test_symlinked_destination_is_rejected(self):
        outside = Path(self.temp.name) / 'outside'
        outside.mkdir()
        try:
            (self.repo / '.github').symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest('Symlinks unavailable on this host')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.install()
        self.assertEqual(list(outside.iterdir()), [])

    def test_file_in_directory_position_is_rejected(self):
        (self.repo / '.github').write_bytes(b'preserve')
        with self.assertRaisesRegex(ValueError, 'not a directory'):
            self.install()
        self.assertEqual((self.repo / '.github').read_bytes(), b'preserve')
        self.assertFalse((self.repo / 'AGENTS.md').exists())

    def test_requires_existing_checkout(self):
        (self.repo / '.git').rmdir()
        with self.assertRaisesRegex(ValueError, 'Git checkout'):
            self.install()
        self.assertEqual(list(self.repo.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
