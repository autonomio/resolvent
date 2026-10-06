#!/usr/bin/env python3
"""Materialize a reviewed handoff on a PR branch, never merge it.

Default is a dry run. --apply writes only after the complete proposed state passes
validation. Decisions must be supplied by the admission agent, not invented here.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.model import Invalid, digest, fail, indexes, load_state, read_data, validate_state

NAMESPACE = uuid.UUID('f546a1e4-a5b6-4a1d-9b85-d348abf54b03')
FAMILIES = ('claims', 'evidence', 'sources', 'graph', 'questions', 'briefs')
PREFIX = {'claims': 'C', 'evidence': 'E', 'sources': 'S', 'graph': 'R', 'questions': 'Q'}


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def canonical_id(run: str, group: str, local: str) -> str:
    return PREFIX[group] + '-' + uuid.uuid5(NAMESPACE, f'{run}/{group}/{local}').hex


def normalized(statement: str) -> str:
    # Only whitespace is normalized. Case, punctuation, units and scope may matter.
    return ' '.join(statement.split())


def plan_admission(state: dict[str, dict], submission_id: str, decisions: dict, policy_root: Path) -> dict[str, dict]:
    validate_state(state, policy_root)
    idx = indexes(state)
    fail(submission_id in idx.get('submission', {}), f'Unknown contribution: {submission_id}')
    p = idx['submission'][submission_id]
    closed_path = f"briefs/closed/{submission_id.replace('RUN-', 'BC-')}.yaml"
    if closed_path in state:
        fail(state[closed_path]['submission_sha256'] == digest(p), 'Existing closure refers to different input')
        return {}  # Idempotent retry; does not create duplicate objects.
    fail(set(decisions) == {'claims', 'connection_review', 'follow_up_gaps'}, 'Decisions need claims, connection_review, follow_up_gaps')
    expected = {c['id'] for c in p['claims']}
    fail(set(decisions['claims']) == expected, 'Decisions must cover every candidate exactly once')
    after = copy.deepcopy(state)
    changes: dict[str, dict] = {}
    maps = {group: {} for group in PREFIX}
    for group in ('sources', 'evidence', 'graph', 'questions'):
        input_group = 'connectors' if group == 'graph' else group
        maps[group] = {v['id']: canonical_id(submission_id, group, v['id']) for v in p[input_group]}
    current_claims = copy.deepcopy(idx.get('claims', {}))
    # Retired claims are not silently revived by duplicate matching.
    exact = {}
    for c in current_claims.values():
        if c['state'] == 'active':
            exact.setdefault((normalized(c['statement']), c['class']), []).append(c['id'])
    dispositions = []
    for c in p['claims']:
        d = decisions['claims'][c['id']]
        fail(isinstance(d, dict) and set(d) <= {'action', 'target', 'reason'} and bool(d.get('reason')), 'Each decision requires a reason')
        action = d.get('action')
        fail(action in ('accept', 'merge', 'reject', 'defer'), f"Invalid disposition for {c['id']}")
        cid = None
        if action == 'merge':
            cid = d.get('target')
            fail(cid in current_claims and current_claims[cid]['state'] == 'active', 'Merge target must be an active canonical claim')
            disposition = 'merged'
        elif action == 'accept':
            match = exact.get((normalized(c['statement']), c['class']), [])
            fail(len(match) <= 1, f"Ambiguous existing duplicates for {c['id']}; choose merge target explicitly")
            cid = match[0] if match else canonical_id(submission_id, 'claims', c['id'])
            disposition = 'merged' if match else 'created'
            exact.setdefault((normalized(c['statement']), c['class']), []).append(cid) if not match else None
            if cid not in current_claims:
                current_claims[cid] = {**copy.deepcopy(c), 'id': cid, 'evidence_ids': [], 'state': 'active'}
        else:
            disposition = 'rejected' if action == 'reject' else 'deferred'
        maps['claims'][c['id']] = cid
        dispositions.append({'candidate_id': c['id'], 'disposition': disposition, 'claim_id': cid, 'reason': d['reason']})

    def claim_ref(value: str) -> str:
        if value in maps['claims']:
            fail(maps['claims'][value] is not None, f'Relationship/premise depends on rejected or deferred candidate {value}; revise handoff')
            return maps['claims'][value]
        fail(value in current_claims, f'Unresolved canonical claim {value}')
        return value

    def set_record(path: str, record: dict) -> None:
        if state.get(path) != record:
            changes[path] = record
        after[path] = record

    for source in p['sources']:
        rec = copy.deepcopy(source)
        rec['id'] = maps['sources'][source['id']]
        set_record(f"sources/{rec['id']}.yaml", rec)
    for evidence in p['evidence']:
        rec = copy.deepcopy(evidence)
        rec['id'] = maps['evidence'][evidence['id']]
        rec['source_ids'] = [maps['sources'][v] for v in evidence['source_ids']]
        rec['premise_claim_ids'] = [claim_ref(v) for v in evidence['premise_claim_ids']]
        rec['claim_ids'] = []
        set_record(f"evidence/{rec['id']}.yaml", rec)
    for candidate in p['claims']:
        cid = maps['claims'][candidate['id']]
        if cid is None:
            continue
        rec = current_claims[cid]
        new_eids = [maps['evidence'][v] for v in candidate['evidence_ids']]
        rec['evidence_ids'] = sorted(set(rec['evidence_ids']) | set(new_eids))
        # A merge adds evidence, never automatically changes class/uncertainty.
        set_record(f'claims/{cid}.yaml', copy.deepcopy(rec))
        for eid in new_eids:
            e = copy.deepcopy(after[f'evidence/{eid}.yaml'])
            e['claim_ids'] = sorted(set(e['claim_ids']) | {cid})
            set_record(f'evidence/{eid}.yaml', e)
    for connector in p['connectors']:
        rec = copy.deepcopy(connector)
        rec['id'] = maps['graph'][connector['id']]
        rec['from'], rec['to'] = claim_ref(connector['from']), claim_ref(connector['to'])
        rec['evidence_ids'] = [maps['evidence'][v] for v in connector['evidence_ids']]
        rec['state'] = 'active'
        fail(rec['from'] != rec['to'], 'Duplicate resolution collapses a connector onto itself; revise the handoff')
        set_record(f"graph/{rec['id']}.yaml", rec)
    for question in p['questions']:
        rec = copy.deepcopy(question)
        rec['id'] = maps['questions'][question['id']]
        rec['claim_ids'] = [claim_ref(v) for v in question['claim_ids']]
        rec['state'] = 'open'
        set_record(f"questions/{rec['id']}.yaml", rec)
    if p['input_method'] == 'research':
        bid = submission_id.replace('RUN-', 'BR-')
        set_record(f'briefs/open/done/{bid}.yaml', {'id': bid, 'submission_id': submission_id, 'brief': p['brief']})
        set_record(f'briefs/ready/{bid}.yaml', {'id': bid, 'submission_id': submission_id, 'result': p['result']})
    categorized = {mode: {g: [] for g in FAMILIES} for mode in ('created', 'updated')}
    for path in changes:
        categorized['updated' if path in state else 'created'][path.split('/')[0]].append(path)
    assessments = []
    admitted = {d['candidate_id'] for d in dispositions if d['claim_id'] is not None}
    fail(set(decisions['connection_review']) == admitted, 'Each admitted candidate needs a connection assessment')
    for local in sorted(admitted):
        r = copy.deepcopy(decisions['connection_review'][local])
        r['candidate_id'] = local
        r['considered_claim_ids'] = [claim_ref(v) for v in r.get('considered_claim_ids', [])]
        assessments.append(r)
    closure = {
        'schema_version': '1.0', 'id': submission_id.replace('RUN-', 'BC-'), 'submission_id': submission_id,
        'input_method': p['input_method'], 'submission_sha256': digest(p), 'completed_at': now(),
        'claim_dispositions': dispositions, **categorized, 'touched_files': sorted(changes),
        'connection_review': assessments, 'follow_up_gaps': decisions['follow_up_gaps'],
        'counts': {f'{n}_claims': sum(d['disposition'] == n for d in dispositions) for n in ('created', 'merged', 'rejected', 'deferred')}
    }
    closure['counts']['created_connectors'] = len(categorized['created']['graph'])
    set_record(closed_path, closure)
    validate_state(after, policy_root)
    return changes


def apply_changes(root: Path, changes: dict[str, dict]) -> None:
    """Write validated data. Roll back already written files on ordinary I/O failure."""
    originals: dict[Path, bytes | None] = {}
    try:
        for rel, value in changes.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            originals[path] = path.read_bytes() if path.exists() else None
            temporary = path.with_suffix(path.suffix + '.tmp')
            temporary.write_text(yaml.safe_dump(value, sort_keys=False, allow_unicode=True), encoding='utf-8')
            os.replace(temporary, path)
    except OSError:
        for path, original in originals.items():
            if original is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(original)
            path.with_suffix(path.suffix + '.tmp').unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('submission', help='RUN-ID or input-artefacts/RUN-ID.json')
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--decisions', type=Path, required=True, help='Admission-agent decisions JSON, see docs/AGENT_JOBS.md')
    parser.add_argument('--apply', action='store_true', help='Apply validated changes; default is dry run')
    args = parser.parse_args()
    try:
        decisions = read_data(args.decisions)
        root = args.root.resolve()
        lockdir = root / '.resolvent'
        lockdir.mkdir(exist_ok=True)
        lock = lockdir / 'admission.lock'
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise Invalid('Another admission is running in this checkout; use a separate worktree')
        try:
            os.close(fd)
            state = load_state(root)
            changes = plan_admission(state, Path(args.submission).stem, decisions, root)
            if args.apply:
                apply_changes(root, changes)
            print(json.dumps({'mode': 'applied' if args.apply else 'dry_run', 'files': sorted(changes), 'already_processed': not bool(changes)}, indent=2))
        finally:
            lock.unlink(missing_ok=True)
    except (Invalid, OSError, ValueError, TypeError, KeyError) as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
