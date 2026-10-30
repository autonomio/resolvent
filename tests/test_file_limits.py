"""Real byte-boundary fixtures, isolated from production model data."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from scripts.build_knowledge import snapshot
from scripts.model import Invalid, read_data
from scripts.world_control import apply_changes


LIMIT = 10 * 1024 * 1024


class FileLimitTests(unittest.TestCase):
    def test_reader_accepts_ten_mib_of_utf8_and_rejects_one_byte_more(self):
        value = {'text': '\u00e9' * ((LIMIT - len(b'{"text":""}')) // 2)}
        raw = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()
        raw += b' ' * (LIMIT - len(raw))
        self.assertEqual(len(raw), LIMIT)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'record.json'
            path.write_bytes(raw)
            self.assertEqual(read_data(path), value)
            path.write_bytes(raw + b' ')
            with self.assertRaisesRegex(Invalid, '10 MiB'):
                read_data(path)

    def test_snapshot_uses_the_same_inclusive_byte_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / 'repo'
            repo.mkdir()
            def git(*args):
                return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.PIPE)
            git('init', '-q')
            source = repo / 'input-artefacts' / 'record.json'
            source.parent.mkdir()
            raw = b'{}' + b' ' * (LIMIT - 2)
            source.write_bytes(raw)
            def commit():
                git('add', '.')
                git('-c', 'user.name=Synthetic fixture', '-c', 'user.email=fixture@example.invalid',
                    'commit', '-qm', 'Synthetic byte-boundary fixture')
            commit()
            destination = root / 'snapshot'
            _, hashes = snapshot(repo, 'HEAD', destination)
            self.assertIn('input-artefacts/record.json', hashes)
            self.assertEqual((destination / 'input-artefacts/record.json').read_bytes(), raw)
            source.write_bytes(raw + b' ')
            commit()
            with self.assertRaisesRegex(Invalid, '10 MiB'):
                snapshot(repo, 'HEAD', root / 'oversized')
            self.assertFalse((root / 'oversized').exists())

    def test_writer_accepts_ten_mib_and_rejects_oversized_batch_before_writes(self):
        value = {'payload': 'x' * (LIMIT - len(b'payload: \n'))}
        relative = 'sources/record.yaml'
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            apply_changes(root, {relative: value})
            path = root / relative
            self.assertEqual(path.stat().st_size, LIMIT)
            original = path.read_bytes()
            with self.assertRaisesRegex(Invalid, '10 MiB'):
                apply_changes(root, {'questions/small.yaml': {'value': 'small'},
                                     relative: {'payload': value['payload'] + 'x'}})
            self.assertEqual(path.read_bytes(), original)
            self.assertFalse((root / 'questions').exists())


if __name__ == '__main__':
    unittest.main()
