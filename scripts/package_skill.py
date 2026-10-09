#!/usr/bin/env python3
"""Build/check the generic Resolvent skill ZIP from its canonical source."""
from __future__ import annotations
import argparse
import io
from pathlib import Path
import zipfile
import yaml

ROOT = Path(__file__).resolve().parent.parent


def skill_files(root: Path = ROOT) -> dict[str, bytes]:
    source = root / 'skills/resolvent'
    text = (source / 'SKILL.md').read_text()
    if not text.startswith('---\n'):
        raise ValueError('Missing SKILL.md frontmatter')
    meta = yaml.safe_load(text.split('---', 2)[1])
    if meta.get('name') != 'resolvent' or not 1 <= len(meta.get('description', '')) <= 200:
        raise ValueError('Skill name/description does not meet portable packaging constraints')
    files = {}
    for path in sorted(source.rglob('*')):
        if '__pycache__' in path.parts or path.suffix == '.pyc':
            continue
        if path.is_symlink():
            raise ValueError('Skill source must not contain symlinks')
        if path.is_file():
            files[path.relative_to(source).as_posix()] = path.read_bytes()
    if files['references/submission.schema.json'] != (root / 'docs/schemas/submission.schema.json').read_bytes():
        raise ValueError('Bundled submission schema differs from the repository protocol')
    return files


def archive_bytes(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative, data in sorted(files.items()):
            path = Path(relative)
            if path.is_absolute() or '..' in path.parts or '\\' in relative:
                raise ValueError('Archive entry must stay within its package')
            info = zipfile.ZipInfo(relative, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return output.getvalue()


def build(root: Path = ROOT) -> bytes:
    return archive_bytes({'resolvent/' + path: data for path, data in skill_files(root).items()})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/resolvent.zip')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    data = build()
    if args.check:
        if not args.output.exists() or args.output.read_bytes() != data:
            print('Skill ZIP is stale; run python scripts/package_skill.py')
            return 1
        print('Skill ZIP is current and reproducible.')
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(data)
    print(f'Built {args.output} ({len(data)} bytes)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
