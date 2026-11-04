"""Opt-in mechanical admission of contributions that carry a producer verification receipt.

A destination opts in with `verified_contributions: true` in `resolvent.yaml`; without it
nothing here runs. A verified contribution is `source_material`, exports only claims
whose producer audit records a current `supported` verdict bound to the exact
statement, and lists withheld claims apart from its candidates. Admitting it takes no
agent judgment: every candidate is accepted with the recorded verdict as its reason and
keeps its exported grade, withheld claims stay out, and relationships to existing
claims and duplicates are deferred to scheduled maintenance. Where the base branch
opts in, CI requires the PR's whole data delta to be exactly this result on the actual
base, so it needs no review. Nothing here assesses truth.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from scripts.model import fail, family, indexes, read_data

POLICY_ROOT = Path(__file__).resolve().parent.parent
SETTING = 'verified_contributions'
RECEIPT_VERSION = 1
VERDICT_REASON = 'Mechanical admission: the producer verification records a supported verdict bound to this statement.'
CONNECTION_REASON = ('Mechanical admission of a verified contribution: the producer supplies within-run '
                     'relationships; relationships to existing claims are assessed in scheduled maintenance.')


def enabled(root: Path) -> bool:
    """The destination's opt-in in its resolvent.yaml; off unless it is explicitly true.

    A world that never opted in keeps today's behavior, so a missing or unreadable
    resolvent.yaml leaves the setting off instead of failing its checks.
    """
    try:
        settings = read_data(root / 'resolvent.yaml')
    except (OSError, ValueError):  # Invalid and undecodable bytes are ValueErrors.
        return False
    value = settings.get(SETTING, False)
    fail(isinstance(value, bool), f'resolvent.yaml: {SETTING} must be true or false')
    return value


def verified(p: dict) -> bool:
    """A source_material contribution with a version 1 producer verification receipt."""
    meta = p.get('method_metadata')
    receipt = meta.get('verification') if isinstance(meta, dict) else None
    return (p.get('input_method') == 'source_material' and isinstance(receipt, dict) and
            type(receipt.get('version')) is int and receipt['version'] == RECEIPT_VERSION)


def statement_sha256(statement: str) -> str:
    return hashlib.sha256(statement.encode('utf-8')).hexdigest()


def verdicts(p: dict) -> dict[str, str]:
    """Check the receipt; return each candidate's recorded verdict reason."""
    sid, meta = p['id'], p['method_metadata']
    receipt, entries, withheld = meta['verification'], meta.get('claim_metadata'), meta.get('withheld_claims')
    names = meta['id_map'].get('claims') if isinstance(meta.get('id_map'), dict) else None
    fail(isinstance(withheld, list) and isinstance(names, dict),
         f'{sid}: a verification receipt lists withheld claims and maps exported claims')
    result = {}
    for c in p['claims']:
        entry = entries.get(c['id']) if isinstance(entries, dict) else None
        check = entry.get('final_check') if isinstance(entry, dict) else None
        bound = statement_sha256(c['statement'])
        # The verdict belongs to the producer claim mapped to this candidate and covers its exact statement.
        fail(isinstance(check, dict) and entry.get('final_verdict') == 'supported' and
             check.get('assessment') == 'supported' and isinstance(check.get('claim_id'), str) and
             names.get(check['claim_id']) == c['id'] and
             entry.get('statement_sha256') == bound and check.get('statement_sha256') == bound,
             f"{sid}: {c['id']} lacks a current supported verdict bound to its statement")
        result[c['id']] = check['reason'].strip() if isinstance(check.get('reason'), str) else ''
    for item in withheld:
        identity = item['claim'].get('id') if isinstance(item, dict) and isinstance(item.get('claim'), dict) else None
        fail(isinstance(identity, str) and identity not in names, f'{sid}: withheld claims stay out of admission')
    fail(receipt.get('supported_claims') == len(p['claims']) and receipt.get('withheld_claims') == len(withheld),
         f'{sid}: verification receipt counts differ from its supported and withheld claims')
    return result


def decisions(p: dict) -> dict:
    """The only decisions a verified contribution takes; none of them is an agent judgment."""
    claims = {cid: {'action': 'accept', 'reason': VERDICT_REASON + (' Recorded verdict: ' + reason if reason else '')}
              for cid, reason in verdicts(p).items()}
    return {'claims': claims,
            'connection_review': {cid: {'considered_claim_ids': [], 'outcome': 'deferred', 'reason': CONNECTION_REASON}
                                  for cid in claims},
            'follow_up_gaps': [f"{p['id']}: scheduled maintenance assesses duplicates of and relationships to "
                               'existing claims for every mechanically admitted candidate.'] if claims else []}


def plan_verified(state: dict[str, dict], submission_id: str, policy_root: Path) -> dict[str, dict]:
    from scripts.world_control import plan_admission  # Deferred: the writer imports this module.
    p = indexes(state).get('submission', {}).get(submission_id)
    fail(p is not None, f'Unknown contribution: {submission_id}')
    fail(verified(p), f'{submission_id}: mechanical admission needs a source_material contribution with a '
                      'producer verification receipt; use admission-agent decisions instead')
    return plan_admission(state, submission_id, decisions(p), policy_root)


def validate_verified_delta(base: Path, old: dict[str, dict], current: dict[str, dict], data_changes: set[str]) -> None:
    """PR gate where the base opts in: a verified contribution's whole data delta is its mechanical admission."""
    if not enabled(base):
        return
    closures = sorted(path for path in data_changes if path in current and path not in old and family(path) == 'closure')
    runs = [current[path]['submission_id'] for path in closures]
    if not any(verified(current.get(f'input-artefacts/{sid}.json', {})) for sid in runs):
        return
    fail(len(closures) == 1, 'Admit a verified contribution in its own delta')
    sid, closure = runs[0], current[closures[0]]
    path = f'input-artefacts/{sid}.json'
    proposed = dict(old)
    proposed[path] = current[path]
    expected = plan_verified(proposed, sid, POLICY_ROOT)
    expected[closures[0]] = {**expected[closures[0]], 'completed_at': closure['completed_at']}
    fail(data_changes == set(expected) | {path} and all(current.get(p) == record for p, record in expected.items()),
         f'{sid}: a verified contribution must be exactly its mechanical admission on the current base; '
         'rebuild it with world_control.py --verified')
