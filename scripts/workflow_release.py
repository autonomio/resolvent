"""Build a versioned live-reference index independently of plugin ZIP versions."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess

from skills.resolvent.scripts.load_workflow import blob_sha, object_pairs, parse_manifest, safe_path, validate_manifest, version

ROOT_PATH = 'workflows/resolvent'


def reference_files(root: Path):
    folder = root / ROOT_PATH
    files = {}
    for path in sorted(folder.rglob('*')):
        if path.is_symlink():
            raise ValueError('Workflow source must not contain symlinks')
        if path.is_file() and path != folder / 'workflow.json':
            if path.stat().st_mode & 0o111:
                raise ValueError('Workflow references must be regular non-executable text files')
            relative = path.relative_to(folder).as_posix()
            safe_path(relative)
            files[relative] = path.read_bytes()
    return files


def manifest(root: Path, source: str, previous=None):
    config_path = root / ROOT_PATH / 'workflow.json'
    if config_path.is_symlink() or (root / ROOT_PATH).is_symlink() or (root / 'workflows').is_symlink():
        raise ValueError('Workflow source must not contain symlinks')
    config = json.loads(config_path.read_text(), object_pairs_hook=object_pairs)
    if set(config) != {'format_version', 'client_protocol', 'workflow_version', 'entrypoint'}:
        raise ValueError('Unexpected workflow source configuration')
    files = reference_files(root)
    result = validate_manifest({**config, 'source_commit': source, 'files': {
        path: {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'git_blob_sha1': blob_sha(data)}
        for path, data in files.items()}})
    if previous:
        validate_manifest(previous)
        if version(result['workflow_version']) < version(previous['workflow_version']):
            raise ValueError('Refusing to roll workflow publication back')
        if result['workflow_version'] == previous['workflow_version']:
            old, new = copy.deepcopy(previous), copy.deepcopy(result)
            old.pop('source_commit')
            new.pop('source_commit')
            if old != new:
                raise ValueError('Published workflow changed: bump workflow_version')
            return previous, files, False
    return result, files, True


def previous_manifest(root: Path):
    ref = 'refs/remotes/origin/workflow-release'
    exists = subprocess.run(['git', 'show-ref', '--verify', '--quiet', ref], cwd=root)
    if exists.returncode == 1:
        return None
    if exists.returncode:
        raise ValueError('Cannot inspect the workflow publication branch')
    paths = subprocess.check_output(['git', 'ls-tree', '--name-only', ref, '--', 'workflow.json'], cwd=root, text=True)
    if not paths.strip():
        raise ValueError('Existing workflow channel has no valid manifest')
    return parse_manifest(subprocess.check_output(['git', 'show', ref + ':workflow.json'], cwd=root))


def verify_committed_source(root: Path, source: str, files: dict):
    expected = {ROOT_PATH + '/' + path for path in files} | {ROOT_PATH + '/workflow.json'}
    actual = set(subprocess.check_output(
        ['git', 'ls-tree', '-r', '--name-only', source, '--', ROOT_PATH], cwd=root, text=True).splitlines())
    if actual != expected:
        raise ValueError('Workflow inventory differs from its pinned source commit')
    for path in sorted(expected):
        committed = subprocess.check_output(['git', 'show', source + ':' + path], cwd=root)
        if committed != (root / path).read_bytes():
            raise ValueError('Workflow bytes differ from their pinned source commit: ' + path)


def check_version(root: Path, base: str):
    current = json.loads((root / ROOT_PATH / 'workflow.json').read_text())['workflow_version']
    version(current)
    paths = subprocess.check_output(['git', 'ls-tree', '--name-only', base, '--', ROOT_PATH + '/workflow.json'], cwd=root, text=True)
    if not paths.strip():
        return
    old = json.loads(subprocess.check_output(['git', 'show', base + ':' + ROOT_PATH + '/workflow.json'], cwd=root))['workflow_version']
    changed = subprocess.check_output(['git', 'diff', '--name-only', base, '--', ROOT_PATH], cwd=root, text=True)
    if version(current) < version(old) or (changed and version(current) <= version(old)):
        raise ValueError('Workflow references changed: bump workflow_version')
