#!/usr/bin/env python3
"""Build/check a reproducible, upload-ready Claude skill ZIP from repository source."""
from __future__ import annotations
import argparse
import io
import re
from pathlib import Path
import zipfile
import yaml

ROOT=Path(__file__).resolve().parent.parent


def build(repository: str|None=None) -> bytes:
    if repository and not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository):
        raise ValueError('Repository must be OWNER/NAME')
    source=ROOT/'skills/resolvent'
    text=(source/'SKILL.md').read_text()
    if not text.startswith('---\n'):
        raise ValueError('Missing SKILL.md frontmatter')
    meta=yaml.safe_load(text.split('---',2)[1])
    if meta.get('name')!='resolvent' or not 1<=len(meta.get('description',''))<=200:
        raise ValueError('Skill name/description does not meet portable Claude packaging constraints')
    files={p.relative_to(source).as_posix():p.read_bytes() for p in source.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    files['references/submission.schema.json']=(ROOT/'docs/schemas/submission.schema.json').read_bytes()
    if repository:
        files['references/TARGET.md']=(f'# Default target\n\nUse `{repository}` unless the user explicitly selects another repository.\nNever send contributions to the template merely because it authored this skill.\n').encode()
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for rel,data in sorted(files.items()):
            info=zipfile.ZipInfo('resolvent/'+rel,date_time=(2026,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
            archive.writestr(info,data)
    return out.getvalue()


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository')
    parser.add_argument('--output',type=Path,default=ROOT/'dist/resolvent.zip')
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args();data=build(args.repository)
    if args.check:
        if not args.output.exists() or args.output.read_bytes()!=data:
            print('Skill ZIP is stale; run python scripts/package_skill.py');return 1
        print('Skill ZIP is current and reproducible.');return 0
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_bytes(data)
    print(f'Built {args.output} ({len(data)} bytes)');return 0
if __name__=='__main__':
    raise SystemExit(main())
