"""Producer uncertainty metadata is preserved and reported, never applied.

A contribution may carry `method_metadata.claim_metadata[candidate]` with the
writer's original `uncertainty`, an auditor's `uncertainty_review` and a
`freshness` review horizon. Admission keeps each candidate's exported grade as
supplied. These fields are separate model judgments, not independent observations,
and change no grade. Grades conflict only when claims merge; maintenance records
that through reassessment (`model_operations.check_merges`). Labels are ordinal,
never probabilities; `moderate` means `medium`.
"""
from __future__ import annotations

import json

from scripts.temporal import temporal_scope

FIELDS = {'uncertainty', 'uncertainty_review', 'freshness'}
GRADES = {'low': 'low', 'moderate': 'medium', 'medium': 'medium', 'high': 'high'}
ORDER = {'low': 0, 'medium': 1, 'high': 2}
CHANGES = ('increased', 'decreased', 'unchanged', 'not_comparable')
HORIZONS = ('scheduled', 'event_driven', 'historical', 'unknown')
PREVIEW, ITEMS = 240, 20  # Preview characters and encoded bytes per string; entries per list.
HORIZON_NOTE = ('A review horizon prompts reassessment only. A passed date is not falsification, '
                'uncertainty decay, retirement or valid time.')
LONG_NOTE = 'Long producer values are previewed here; the contribution preserves them unchanged.'
AUDIT_NOTES = {
    'absent': 'No producer audit record is preserved.',
    'partial': 'The producer audit is not recorded as complete; unchecked scope remains.',
    'ambiguous': 'Duplicate producer audit rows are present; audit_complete=true is not an unambiguous verdict.'}
PRIOR_NOTES = {
    'missing': 'The proposed prior is not an active claim in this destination revision; no comparison is made.',
    'stale': 'The auditor-reported prior grade is absent or differs from the destination grade; no comparison is made.',
    'scope_differs': 'The proposed prior has a different class or temporal scope; no comparison is made.',
    'no_match_reason': 'The auditor gave no same-proposition reason for the prior match; no comparison is made.'}


def grade(value):
    """The ordinal destination label for a producer label, or None."""
    return GRADES.get(value) if isinstance(value, str) else None


def text(record, key):
    value = record.get(key)
    return value if isinstance(value, str) else ''


def clip(value):
    """At most PREVIEW characters and PREVIEW JSON-encoded bytes, so one report always fits a bounded page."""
    value = value[:PREVIEW]
    if len(json.dumps(value, ensure_ascii=False).encode()) <= PREVIEW + 2:
        return value
    size = 0
    for end, char in enumerate(value):
        size += len(json.dumps(char, ensure_ascii=False).encode()) - 2
        if size > PREVIEW:
            return value[:end]
    return value


def strings(value, notes):
    """Previewed producer strings for bounded reads; `notes` records any shortening."""
    values = [item for item in value if isinstance(item, str)] if isinstance(value, list) else []
    shown = [clip(item) for item in values[:ITEMS]]
    if len(values) > ITEMS or shown != values[:ITEMS]:
        notes.append(LONG_NOTE)
    return shown


def audit_rows(meta):
    """Raw audit rows by producer claim ID, and how far `audit_complete` can be read."""
    audit = meta.get('independent_audit')
    if not isinstance(audit, dict):
        return {}, 'absent'
    rows = {}
    for row in audit['claim_checks'] if isinstance(audit.get('claim_checks'), list) else []:
        if isinstance(row, dict) and isinstance(row.get('claim_id'), str):
            rows.setdefault(row['claim_id'], []).append(row)
    if any(len(found) > 1 for found in rows.values()):
        return rows, 'ambiguous'  # Duplicate rows: a reported complete audit is not one verdict.
    return rows, 'complete' if audit.get('audit_complete') is True else 'partial'


def prior_check(identity, reported, reason, candidate, claims):
    """Check a proposed prior against one destination revision; sameness stays a proposal."""
    prior = claims.get(identity)
    if prior is None or prior['state'] != 'active':
        return {'status': 'missing', 'uncertainty': None}
    if reported != prior['uncertainty']:
        status = 'stale'
    elif (prior['class'] != candidate['class'] or
          temporal_scope(prior.get('valid_time')) != temporal_scope(candidate.get('valid_time'))):
        status = 'scope_differs'
    else:
        status = 'comparable' if reason.strip() else 'no_match_reason'
    return {'status': status, 'uncertainty': prior['uncertainty']}


def change(recommended, check):
    """The recommendation relative to the checked destination grade, as an uncertainty direction."""
    if recommended is None or check['status'] != 'comparable':
        return 'not_comparable'
    delta = ORDER[recommended] - ORDER[check['uncertainty']]
    return 'increased' if delta > 0 else 'decreased' if delta < 0 else 'unchanged'


def writer(value):
    """The writer's original label beside its ordinal destination equivalent."""
    label = value.get('class') if isinstance(value, dict) else value
    result = {'label': clip(label) if isinstance(label, str) else None, 'uncertainty': grade(label)}
    if isinstance(value, dict) and isinstance(value.get('rationale'), str):
        result['rationale_preview'] = clip(value['rationale'])
    return result


def horizon(value):
    """Preserve a producer review horizon. It never expires, decays or dates a claim."""
    value = value if isinstance(value, dict) else {}
    policy = value['policy'] if value.get('policy') in HORIZONS else 'unknown'
    notes = [] if policy == value.get('policy') else ['Missing or unsupported review horizon; recorded as unknown.']
    result = {'policy': policy, 'as_of': clip(text(value, 'as_of')) or None,
              'review_after': clip(text(value, 'review_after')) or None,
              'triggers': strings(value.get('triggers'), notes),
              'rationale_preview': clip(text(value, 'rationale')),
              'interpretation': HORIZON_NOTE, 'limitations': notes}
    if policy == 'scheduled' and result['review_after'] is None:
        notes.append('A scheduled review horizon has no review date.')
    return result


def report(run, claims):
    """Writer grade, auditor review, prior check and review horizon per admitted candidate.

    `claims` are the canonical claims of the destination revision being read. The
    report reads the immutable run only; it records no decision and changes no
    grade. A run without per-candidate `claim_metadata` reports nothing.
    """
    meta = run['method_metadata']
    entries = meta.get('claim_metadata')
    if not isinstance(entries, dict):
        return {}
    from scripts.world_control import canonical_id  # Deferred: the writer loads this module through model operations.
    rows, audit = audit_rows(meta)
    names = meta['id_map'].get('claims') if isinstance(meta.get('id_map'), dict) else None
    originals = {}
    for original, local in names.items() if isinstance(names, dict) else ():
        if isinstance(local, str):  # Free-form producer metadata never breaks a read.
            originals.setdefault(local, []).append(original)
    evidence = {e['id'] for e in run['evidence']}
    result = {}
    for c in run['claims']:
        entry = entries.get(c['id'])
        if not isinstance(entry, dict) or not FIELDS & set(entry):
            continue
        raw = entry['uncertainty_review'] if isinstance(entry.get('uncertainty_review'), dict) else {}
        notes = []
        producer_notes = strings(raw.get('limitations'), notes)
        # Rows keyed by the candidate ID itself are still found when the producer map does not resolve it.
        checks = [row for name in originals.get(c['id']) or [c['id']] for row in rows.get(name, [])]
        recommended, basis = grade(raw.get('recommended_class')), raw.get('evidence_ids')
        if 'uncertainty_review' not in entry:
            notes.append('No uncertainty review was recorded for this candidate.')
            recommended = None
        elif raw.get('status') != 'assessed' or recommended is None or not text(raw, 'reason').strip():
            notes.append('No assessed recommendation was recorded; no comparison applies.')
            recommended = None
        elif not isinstance(basis, list) or any(not isinstance(e, str) or e not in evidence for e in basis):
            notes.append('The recommendation cites evidence unavailable in this contribution; it remains unassessed.')
            recommended = None
        elif audit != 'complete':
            # Fail closed: duplicate rows anywhere, even unmapped ones, or an incomplete audit leave no verdict to rely on.
            notes.append('Only a complete producer audit without duplicate rows yields an assessed recommendation.')
            recommended = None
        elif not basis:
            notes.append('The recommendation cites no evidence.')
        if audit != 'complete':
            notes.append(AUDIT_NOTES[audit])
        verdict = None
        if len(checks) > 1:
            verdict = 'ambiguous'
        elif checks:
            verdict = clip(text(checks[0], 'assessment')) or None
        found = {'status': 'assessed' if recommended else 'not_assessed', 'recommended_uncertainty': recommended,
                 'reason_preview': clip(text(raw, 'reason')),
                 'evidence_ids': strings([canonical_id(run['id'], 'evidence', e) for e in basis], notes) if recommended else [],
                 'original_evidence_ids': strings(raw.get('original_evidence_ids'), notes),
                 'producer_audit': audit, 'audit_verdict': verdict, 'prior': None}
        identity = text(raw, 'prior_claim_id')
        if identity:
            # A proposed prior is a destination ID; it is never mapped like a local candidate ID.
            reported, reason = grade(raw.get('prior_class')), text(raw, 'prior_match_reason')
            check = prior_check(identity, reported, reason, c, claims)
            found['prior'] = {'claim_id': clip(identity), 'auditor_uncertainty': reported,
                              'match_reason_preview': clip(reason), 'destination': check,
                              'uncertainty_change': change(recommended, check),
                              'producer_uncertainty_change': raw.get('change') if raw.get('change') in CHANGES else None}
            if check['status'] != 'comparable':
                notes.append(PRIOR_NOTES[check['status']])
        found['limitations'] = list(dict.fromkeys(producer_notes + notes))
        item = {'uncertainty_review': found}
        if 'uncertainty' in entry:
            item['writer_uncertainty'] = writer(entry['uncertainty'])
        if 'freshness' in entry:
            item['review_horizon'] = horizon(entry['freshness'])
        result[c['id']] = item
    return result


def reviewed_claims(idx):
    """Admitted claim IDs whose candidates carried an `uncertainty_review`, with those runs."""
    result = {}
    for closure in idx.get('closure', {}).values():
        run = idx['submission'][closure['submission_id']]
        entries = run['method_metadata'].get('claim_metadata')
        for d in closure['claim_dispositions'] if isinstance(entries, dict) else ():
            entry = entries.get(d['candidate_id'])
            if d['claim_id'] is not None and isinstance(entry, dict) and 'uncertainty_review' in entry:
                result.setdefault(d['claim_id'], set()).add(run['id'])
    return result
