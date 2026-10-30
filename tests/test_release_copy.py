"""Exercise the actual release-copy commands against timestamp collisions."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


class ReleaseCopyTests(unittest.TestCase):
    def test_equal_size_and_mtime_cannot_hide_changed_release_bytes(self):
        workflow = yaml.safe_load((ROOT / '.github/workflows/plugin-release.yml').read_text())
        steps = workflow['jobs']['publish']['steps']
        for folder, variable, name in (
            ('workflow', 'WORKFLOW_CHECKOUT', 'Publish the independent live-reference channel'),
            ('plugin', 'RELEASE_CHECKOUT', "Update the directory's tracked plugin branch"),
        ):
            with self.subTest(channel=folder), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / 'paths with spaces'
                source = root / 'release' / folder
                destination = root / 'checkout'
                source.mkdir(parents=True)
                (destination / '.git').mkdir(parents=True)
                (destination / '.git' / 'keep').write_text('repository metadata')
                (destination / 'obsolete').write_text('remove stale release file')
                source_file, destination_file = source / 'release.json', destination / 'release.json'
                source_file.write_bytes(b'{"version":"1.0.3"}\n')
                destination_file.write_bytes(b'{"version":"1.0.2"}\n')
                for path in (source_file, destination_file):
                    os.utime(path, (1_700_000_000, 1_700_000_000))
                self.assertEqual(source_file.stat().st_size, destination_file.stat().st_size)
                step = next(step for step in steps if step.get('name') == name)
                command = next(line.strip() for line in step['run'].splitlines()
                               if line.strip().startswith('rsync '))
                subprocess.run(['bash', '-eu', '-c', command], check=True,
                               env={**os.environ, 'RELEASE_ROOT': str(source.parent),
                                    variable: str(destination)})
                self.assertEqual(destination_file.read_bytes(), source_file.read_bytes())
                self.assertTrue((destination / '.git' / 'keep').is_file())
                self.assertFalse((destination / 'obsolete').exists())


if __name__ == '__main__':
    unittest.main()
