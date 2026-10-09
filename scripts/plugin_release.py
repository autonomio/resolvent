#!/usr/bin/env python3
"""Validate plugin version changes and prepare a publication from validated main."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.package_plugin import plugin_files
from scripts.package_skill import ROOT, archive_bytes, build

RELEASE_BRANCH = 'plugin-release'
PACKAGED_PATHS = (
    'plugin.json', '.codex-plugin/plugin.json', '.claude-plugin/plugin.json',
    'skills/resolvent', 'assets', 'docs/PLUGIN_README.md', 'verification/README.md',
    'scripts/package_plugin.py', 'scripts/package_skill.py',
    '.agents/plugins/marketplace.json', '.claude-plugin/marketplace.json',
)


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(['git', *args], cwd=root, text=True).strip()


def version_tuple(version: str) -> tuple[int, ...]:
    if not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', version):
        raise ValueError('Release requires a canonical major.minor.patch version')
    return tuple(map(int, version.split('.')))


def check_version(root: Path, base: str) -> None:
    version, _ = plugin_files(root)
    version_tuple(version)
    # The template predates the portable plugin. Its first plugin release is 1.0.0.
    paths = git(root, 'ls-tree', '--name-only', base, '--', 'plugin.json').splitlines()
    if not paths:
        print('Initial portable plugin release: ' + version)
        return
    previous = json.loads(git(root, 'show', base + ':plugin.json'))['version']
    changed = git(root, 'diff', '--name-only', base, '--', *PACKAGED_PATHS)
    if changed and version_tuple(version) <= version_tuple(previous):
        raise ValueError('Packaged plugin contents changed: bump the shared plugin version')
    if version_tuple(version) < version_tuple(previous):
        raise ValueError('Plugin versions cannot decrease')
    print('Plugin version change is valid: ' + version)


def previous_release(root: Path) -> dict | None:
    ref = 'refs/remotes/origin/' + RELEASE_BRANCH
    found = subprocess.run(['git', 'show-ref', '--verify', '--quiet', ref], cwd=root)
    if found.returncode == 1:
        return None
    if found.returncode:
        raise ValueError('Cannot inspect the existing release branch')
    # An existing branch without our record is not safe to replace.
    return json.loads(git(root, 'show', ref + ':release.json'))


def release_record(version: str, plugin: bytes, source: str, previous: dict | None) -> tuple[dict, bool]:
    version_tuple(version)
    if not re.fullmatch(r'[0-9a-f]{40}', source):
        raise ValueError('Release source must be a full Git commit SHA')
    digest = hashlib.sha256(plugin).hexdigest()
    if previous:
        old = version_tuple(previous['version'])
        if version_tuple(version) < old:
            raise ValueError('Refusing to roll the release branch back')
        if version_tuple(version) == old:
            if previous['plugin_sha256'] != digest:
                raise ValueError('Published version has different bytes: bump the plugin version')
            if not re.fullmatch(r'[0-9a-f]{40}', previous['source_commit']):
                raise ValueError('Invalid previous release source')
            # Preserve provenance on retries and data-only main commits.
            return previous, False
    return {'version': version, 'source_commit': source, 'plugin_sha256': digest}, True


def prepare(root: Path, output: Path, previous: dict | None) -> dict[str, str]:
    if output.exists():
        raise ValueError('Publication output must be a new directory')
    version, files = plugin_files(root)
    plugin = archive_bytes({'resolvent/' + path: data for path, data in files.items()})
    record, changed = release_record(version, plugin, git(root, 'rev-parse', 'HEAD'), previous)
    folder = output / 'plugin'
    for relative, contents in files.items():
        destination = folder / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(contents)
    # The branch is an installable plugin, without world-model data or governance.
    for relative in ('.claude-plugin/marketplace.json', '.agents/plugins/marketplace.json'):
        catalog = json.loads((root / relative).read_text())
        catalog['plugins'][0]['source'] = './' if relative.startswith('.claude') else {'source': 'local', 'path': './'}
        destination = folder / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(catalog, indent=2) + '\n')
    serialized = json.dumps(record, indent=2) + '\n'
    (folder / 'release.json').write_text(serialized)
    assets = output / 'assets'
    assets.mkdir()
    archives = {
        f'resolvent-chatgpt-{version}.zip': plugin,
        f'resolvent-claude-{version}.zip': plugin,
        f'resolvent-skill-{version}.zip': build(root),
    }
    for filename, contents in archives.items():
        (assets / filename).write_bytes(contents)
    (assets / 'release.json').write_text(serialized)
    (assets / 'SHA256SUMS').write_text(''.join(
        f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n'
        for path in sorted(assets.iterdir()) if path.is_file()
    ))
    notes = json.loads((root / 'plugin.json').read_text())['extensions']['com.openai']['publication']['release_notes']
    (output / 'notes.md').write_text(
        f'Resolvent {version} by [Autonomio](https://autonom.io).\n\n{notes}\n\n'
        f'Source: `{record["source_commit"]}`. Both host ZIPs contain identical plugin bytes.\n\n'
        'Claude directory updates follow the validated `plugin-release` branch and '
        'its publishing settings. The ChatGPT ZIP is ready for upload to the existing '
        'listing; bundled skill updates still require review and publication. '
        'This GitHub release is not evidence of directory approval.\n'
    )
    return {'version': version, 'tag': 'resolvent-v' + version,
            'source_commit': record['source_commit'], 'changed': str(changed).lower()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    check = sub.add_parser('check-version')
    check.add_argument('--base', required=True)
    stage = sub.add_parser('prepare')
    stage.add_argument('--output', required=True, type=Path)
    stage.add_argument('--github-output', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'check-version':
            check_version(ROOT, args.base)
        else:
            outputs = prepare(ROOT, args.output, previous_release(ROOT))
            if args.github_output:
                with args.github_output.open('a') as stream:
                    stream.write(''.join(f'{key}={value}\n' for key, value in outputs.items()))
            print(json.dumps(outputs))
    except (ValueError, KeyError, subprocess.CalledProcessError) as error:
        parser.exit(1, str(error) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
