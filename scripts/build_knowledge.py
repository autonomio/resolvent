#!/usr/bin/env python3
"""Build disposable knowledge views from a pinned, structurally closed Git revision."""
from __future__ import annotations

import argparse
import hashlib
from datetime import datetime, timezone
from importlib.metadata import version
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.model import (
    CANONICAL_ROOTS, DATA_ROOTS, MAX_FILE_BYTES, Invalid, digest, family,
    indexes, load_state, safe_relative, validate_state,
)
from scripts.temporal import point

ROOT = Path(__file__).resolve().parent.parent
FORMAT_VERSION = '1.0'
COMPILER_VERSION = '1.2.0'


def json_bytes(value: object) -> bytes:
    """The package encoding: sorted keys, UTF-8, two-space indent, final newline."""
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False,
                       allow_nan=False) + '\n').encode('utf-8')


def sha256(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()


def git(repo: Path, *args: str) -> bytes:
    # Block transports even on Git versions predating GIT_NO_LAZY_FETCH.
    result = subprocess.run(['git', '--no-replace-objects', '-C', str(repo), *args],
                            capture_output=True,
                            env={**os.environ, 'GIT_NO_LAZY_FETCH': '1',
                                 'GIT_ALLOW_PROTOCOL': '',
                                 'GIT_TERMINAL_PROMPT': '0'})
    if result.returncode:
        raise Invalid(result.stderr.decode('utf-8', errors='replace').strip())
    return result.stdout


def knowledge_revision(repo: Path, revision: str, known_at: str) -> str:
    """Select first-parent history by recorded Git committer time, never source date."""
    kind, at = point(known_at)
    if kind != 'instant':
        raise Invalid('Knowledge time requires a full timestamp with timezone')
    elapsed = at - datetime(1970, 1, 1, tzinfo=timezone.utc)
    cutoff = elapsed.days * 86400 + elapsed.seconds
    commit = git(repo, 'rev-parse', '--verify', '--end-of-options', revision + '^{commit}').decode().strip()
    history = git(repo, 'log', '--first-parent', '--format=%H %ct', commit).decode().splitlines()
    for line in history:
        candidate, recorded_time = line.split()
        if int(recorded_time) <= cutoff:
            return candidate
    raise Invalid('No local first-parent revision is recorded by the requested knowledge time')


def snapshot(repo: Path, revision: str, destination: Path) -> tuple[str, dict[str, str]]:
    """Read Git objects only; never check out or execute code from the revision."""
    commit = git(repo, 'rev-parse', '--verify', '--end-of-options',
                 revision + '^{commit}').decode().strip()
    entries = git(repo, 'ls-tree', '-r', '-l', '-z', '--full-tree', commit,
                  '--', *DATA_ROOTS)
    hashes = {}
    for entry in entries.split(b'\0'):
        if not entry:
            continue
        metadata, raw_path = entry.split(b'\t', 1)
        mode, kind, oid, size = metadata.split()
        path = raw_path.decode('utf-8')
        if kind != b'blob' or mode not in (b'100644', b'100755'):
            raise Invalid(f'Only regular data files are accepted: {path}')
        if not safe_relative(path):
            raise Invalid(f'Unsafe data path: {path}')
        if Path(path).name in ('.gitkeep', 'README.md'):
            continue
        if not size.isdigit():
            raise Invalid(f'Missing local Git object: {path}')
        if int(size) > MAX_FILE_BYTES:
            raise Invalid(f'File exceeds the 2 MiB contribution limit: {path}')
        contents = git(repo, 'cat-file', 'blob', oid.decode())
        target = destination / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(contents)
        hashes[path] = sha256(contents)
    return commit, hashes


def projection(state: dict[str, dict]) -> dict:
    """Preserve canonical fields and provenance; derive only explicit reverse links."""
    idx = indexes(state)
    records = {group: idx.get(group, {}) for group in CANONICAL_ROOTS}
    reverse = {
        'sources': {sid: {'evidence_ids': []} for sid in records['sources']},
        'evidence': {eid: {'claim_ids': [], 'connector_ids': []}
                     for eid in records['evidence']},
        'claims': {cid: {'incoming_connector_ids': [], 'outgoing_connector_ids': [],
                         'premise_evidence_ids': [], 'question_ids': []}
                   for cid in records['claims']},
    }
    for cid, claim in records['claims'].items():
        for eid in claim['evidence_ids']:
            reverse['evidence'][eid]['claim_ids'].append(cid)
    for eid, evidence in records['evidence'].items():
        for sid in evidence['source_ids']:
            reverse['sources'][sid]['evidence_ids'].append(eid)
        for cid in evidence['premise_claim_ids']:
            reverse['claims'][cid]['premise_evidence_ids'].append(eid)
    for rid, connector in records['graph'].items():
        reverse['claims'][connector['from']]['outgoing_connector_ids'].append(rid)
        reverse['claims'][connector['to']]['incoming_connector_ids'].append(rid)
        for eid in connector['evidence_ids']:
            reverse['evidence'][eid]['connector_ids'].append(rid)
    for qid, question in records['questions'].items():
        for cid in question['claim_ids']:
            reverse['claims'][cid]['question_ids'].append(qid)
    for group in reverse.values():
        for record in group.values():
            for key, values in record.items():
                record[key] = sorted(set(values))
    return {
        'format_version': FORMAT_VERSION,
        'derived': True,
        'records': records,
        'record_paths': {record['id']: path for path, record in state.items()
                         if family(path) in CANONICAL_ROOTS},
        'reverse_links': reverse,
        'provenance': {path: record for path, record in state.items()
                       if family(path) not in CANONICAL_ROOTS},
    }


def compile_revision(repo: Path, revision: str, *, known_at: str | None = None) -> dict[str, bytes]:
    """Return versioned package bytes after the existing closure gate passes.

    Validation uses this installed compiler and its schemas, not code in the
    selected revision. The manifest fingerprints both data and validation policy.
    Structural closure does not establish independent semantic approval.
    """
    if known_at is not None:
        revision = knowledge_revision(repo, revision, known_at)
    with tempfile.TemporaryDirectory(prefix='resolvent-snapshot-') as temporary:
        root = Path(temporary)
        commit, input_files = snapshot(repo, revision, root)
        state = load_state(root)
        counts = validate_state(state, ROOT, require_closure=True)
    knowledge = json_bytes(projection(state))
    policy_paths = ['scripts/model.py', 'scripts/temporal.py', 'scripts/build_knowledge.py', 'requirements.txt']
    policy_paths += sorted(path.relative_to(ROOT).as_posix()
                           for path in (ROOT / 'docs/schemas').glob('*.schema.json'))
    manifest = {
        'artifact_format': 'resolvent.knowledge',
        'artifact_format_version': FORMAT_VERSION,
        'schema_version': FORMAT_VERSION,
        'compiler_version': COMPILER_VERSION,
        'derived': True,
        'source_revision': commit,
        'input_files': input_files,
        'input_tree_sha256': digest(input_files),
        'validation': {
            'structural_validation': 'passed',
            'require_closure': True,
            'semantic_review': 'not established by compilation',
            'records': counts,
            'policy_files': {path: sha256((ROOT / path).read_bytes())
                             for path in policy_paths},
            'dependencies': {name: version(name) for name in ('PyYAML', 'jsonschema')},
        },
        'artifacts': {'knowledge.json': {'sha256': sha256(knowledge),
                                         'bytes': len(knowledge)}},
    }
    return {'knowledge.json': knowledge, 'manifest.json': json_bytes(manifest)}


def build(repo: Path, revision: str, output: Path, *, known_at: str | None = None) -> dict:
    """Write a new package directory; refuse canonical or tracked output locations."""
    if output.exists() or output.is_symlink():
        raise Invalid('Build output must be a new directory')
    repository = Path(git(repo, 'rev-parse', '--show-toplevel').decode().strip()).resolve()
    output = output.resolve()
    if output.is_relative_to(repository):
        relative = output.relative_to(repository)
        if not relative.parts or relative.parts[0] != '.resolvent':
            raise Invalid('Build output inside the repository must be under .resolvent/')
    package = compile_revision(repository, revision, known_at=known_at)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.knowledge-', dir=output.parent) as temporary:
        staged = Path(temporary) / 'package'
        staged.mkdir()
        for filename, contents in package.items():
            (staged / filename).write_bytes(contents)
        staged.rename(output)
    return json.loads(package['manifest.json'])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path('.'))
    parser.add_argument('--revision', required=True, help='Local Git commit/ref, resolved once')
    parser.add_argument('--known-at', help='Select first-parent revision by recorded Git committer timestamp')
    parser.add_argument('--output', type=Path, required=True, help='New directory under .resolvent/ or outside the repository')
    args = parser.parse_args()
    try:
        manifest = build(args.repo, args.revision, args.output, known_at=args.known_at)
    except (Invalid, OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(1, f'FAIL: {exc}\n')
    print(json.dumps({'source_revision': manifest['source_revision'],
                      'input_tree_sha256': manifest['input_tree_sha256'],
                      'manifest_sha256': sha256(json_bytes(manifest))}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
