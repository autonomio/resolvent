#!/usr/bin/env python3
"""Finish a partial plugin upload without replacing any existing release bytes."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

REPOSITORY = 'autonomio/resolvent'


def reconcile(assets: Path, existing: set[str], download, upload) -> list[str]:
    missing = []
    files = sorted(path for path in assets.iterdir() if path.is_file())
    if not files:
        raise ValueError('Expected release assets are missing')
    # Verify all published package bytes before making any repair writes.
    for path in files:
        if path.name in existing:
            if download(path.name) != path.read_bytes():
                raise ValueError('Published asset differs from validated bytes: ' + path.name)
        else:
            missing.append(path)
    for path in missing:
        # Never clobber an existing asset, even if an unexpected writer races CI.
        upload(path)
    return [path.name for path in missing]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--assets', type=Path, required=True)
    args = parser.parse_args()
    try:
        record = json.loads((args.assets / 'release.json').read_text())
        if args.tag != 'resolvent-v' + record['version']:
            raise ValueError('Release tag does not match the prepared assets')
        release = json.loads(subprocess.check_output(
            ['gh', 'api', f'repos/{REPOSITORY}/releases/tags/{args.tag}'], text=True))
        with tempfile.TemporaryDirectory() as folder:
            def download(name):
                subprocess.run(['gh', 'release', 'download', args.tag, '--repo', REPOSITORY,
                                '--pattern', name, '--dir', folder], check=True)
                return (Path(folder) / name).read_bytes()

            def upload(path):
                subprocess.run(['gh', 'release', 'upload', args.tag, str(path),
                                '--repo', REPOSITORY], check=True)

            uploaded = reconcile(args.assets, {a['name'] for a in release['assets']}, download, upload)
        print('Verified existing assets; uploaded ' + str(len(uploaded)) + ' missing assets')
    except (ValueError, KeyError, subprocess.CalledProcessError) as error:
        parser.exit(1, str(error) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
