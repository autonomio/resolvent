#!/usr/bin/env python3
"""Build/check reproducible ChatGPT and Claude plugins from one generic source."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import struct
import sys
import yaml

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.package_skill import ROOT, archive_bytes, skill_files


def _manifest(root: Path, relative: str) -> dict:
    result = json.loads((root / relative).read_text())
    if not isinstance(result, dict):
        raise ValueError('Manifest must be an object: ' + relative)
    if result.get('apps') is not None or result.get('extensions', {}).get('com.openai', {}).get('apps') is not None:
        raise ValueError('Public distribution must not include private app bindings')
    return result


def plugin_files(root: Path = ROOT) -> tuple[str, dict[str, bytes]]:
    names = ('plugin.json', '.codex-plugin/plugin.json', '.claude-plugin/plugin.json')
    manifests = [_manifest(root, name) for name in names]
    version = manifests[0].get('version', '')
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version):
        raise ValueError('Plugin version must be a semantic release version')
    for key in ('name', 'version', 'description', 'author', 'homepage'):
        if any(manifest.get(key) != manifests[0].get(key) for manifest in manifests[1:]):
            raise ValueError('Host manifests differ: ' + key)
    if manifests[0].get('name') != 'resolvent':
        raise ValueError('Plugin identity must remain resolvent')
    interface = manifests[0]['extensions']['com.openai']['interface']
    if interface != manifests[1].get('interface'):
        raise ValueError('OpenAI and compatibility listing metadata differ')
    for key, limit in (('displayName', 30), ('shortDescription', 30), ('developerName', 80), ('longDescription', 4000)):
        value = interface.get(key, '')
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            raise ValueError('Invalid listing field: ' + key)
    prompts = interface.get('defaultPrompt')
    prompts = [prompts] if isinstance(prompts, str) else prompts
    if not isinstance(prompts, list) or not 1 <= len(prompts) <= 3:
        raise ValueError('Provide one to three default prompts')
    if any(not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 128 or '\n' in prompt or '@' in prompt for prompt in prompts):
        raise ValueError('Invalid default prompt')
    skill = skill_files(root)
    metadata = yaml.safe_load(skill['SKILL.md'].decode().split('---', 2)[1])
    if metadata.get('metadata', {}).get('version') != version:
        raise ValueError('Skill and plugin release versions differ')
    files = {name: (root / name).read_bytes() for name in names}
    files.update({'skills/resolvent/' + path: data for path, data in skill.items()})
    for path in sorted((root / 'assets').rglob('*')):
        if path.is_symlink():
            raise ValueError('Assets must not contain symlinks')
        if path.is_file():
            files[path.relative_to(root).as_posix()] = path.read_bytes()
    for field in ('logo', 'composerIcon'):
        reference = interface.get(field, '')
        relative = reference.removeprefix('./')
        if not reference.startswith('./') or '..' in Path(relative).parts or relative not in files:
            raise ValueError('Missing or unsafe icon: ' + field)
        data = files[relative]
        if not data.startswith(b'\x89PNG\r\n\x1a\n') or len(data) < 24:
            raise ValueError('Directory icon must be a PNG')
        width, height = struct.unpack('>II', data[16:24])
        minimum = 256 if field == 'logo' else 48
        if width != height or width < minimum or width > 4096 or len(data) > 5 * 1024 * 1024:
            raise ValueError('Directory icon size is invalid')
    files['README.md'] = (root / 'docs/PLUGIN_README.md').read_bytes()
    files['verification/README.md'] = (root / 'verification/README.md').read_bytes()
    for relative, data in files.items():
        if relative.endswith(('.md', '.json', '.yaml', '.py')):
            text = data.decode().lower()
            if any(token in text for token in ('velocinbio', 'portal.velocin.fi', 'mikkokotila', 'mikko kotila', 'portal_context.md', 'portal_context.py')):
                raise ValueError('Organization-specific content in ' + relative)
    return version, files


def distributions(root: Path = ROOT) -> dict[Path, bytes]:
    version, files = plugin_files(root)
    data = archive_bytes({'resolvent/' + path: contents for path, contents in files.items()})
    return {root / 'dist' / host / f'resolvent-{version}.zip': data for host in ('chatgpt', 'claude')}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    artifacts = distributions()
    _, files = plugin_files()
    staged = ROOT / 'dist/plugin/resolvent'
    if args.check:
        stale = [str(path.relative_to(ROOT)) for path, data in artifacts.items() if not path.exists() or path.read_bytes() != data]
        actual = {path.relative_to(staged).as_posix(): path.read_bytes()
                  for path in staged.rglob('*') if path.is_file() and '__pycache__' not in path.parts}
        if actual != files:
            stale.append('dist/plugin/resolvent')
        if stale:
            print('Plugin ZIPs are stale: ' + ', '.join(stale))
            return 1
        print('ChatGPT and Claude plugin ZIPs are current, identical and reproducible.')
        return 0
    if staged.exists():
        import shutil
        shutil.rmtree(staged)
    for relative, data in files.items():
        path = staged / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    for path, data in artifacts.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        print(f'Built {path} ({len(data)} bytes)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
