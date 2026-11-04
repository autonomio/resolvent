"""Producer uncertainty recommendations need explicit destination decisions.

A contribution may carry `method_metadata.claim_metadata[candidate]` with the
writer's original `uncertainty`, an auditor's `uncertainty_review` and a
`freshness` review horizon. These are preserved model judgments, not independent
observations. Nothing here changes a grade by itself: admission records accept,
override or defer, and an existing claim changes only through its linked recorded
reassessment. Labels are ordinal, never probabilities; `moderate` means `medium`.
"""
from __future__ import annotations

from collections import Counter

from scripts.model import fail, no_duplicates
from scripts.temporal import temporal_scope

GRADES = {'low': 'low', 'moderate': 'medium', 'medium': 'medium', 'high': 'high'}
ORDER = {'low': 0, 'medium': 1, 'high': 2}
DECISIONS = ('accept', 'override', 'defer')
HORIZONS = ('scheduled', 'event_driven', 'historical', 'unknown')
PREVIEW = 240
HORIZON_NOTE = ('A review horizon prompts reassessment only. A passed date is not falsification, '
                'uncertainty decay, retirement or valid time.')
AUDIT_NOTES = {
    'absent': 'No producer audit record is preserved.',
    'partial': 'The producer audit is not recorded as complete; unchecked scope remains.',
    'ambiguous': 'Duplicate producer audit rows are present; audit_complete=true is not an unambiguous verdict.'}
PRIOR_NOTES = {
    'missing': 'The proposed prior is not an active claim in the destination revision; no comparison is made.',
    'stale': 'The auditor-reported prior grade differs from the destination grade; the comparison is stale.',
    'scope_differs': 'The proposed prior has a different class or temporal scope; no comparison is made.',
    'no_match_reason': 'The auditor gave no same-proposition reason for the prior match; no comparison is made.'}


def grade(value):
    return GRADES.get(value) if isinstance(value, str) else None


def text(record, key):
    return record[key] if isinstance(record.get(key), str) else ''


def audit_summary(meta):
    """Raw audit completeness. Duplicate rows make a reported complete audit ambiguous."""
    audit = meta.get('independent_audit')
    if not isinstance(audit, dict):
        return {'interpretation': 'absent', 'audit_complete': None, 'duplicate_claim_ids': []}
    rows = audit['claim_checks'] if isinstance(audit.get('claim_checks'), list) else []
    counts = Counter(row['claim_id'] for row in rows
                     if isinstance(row, dict) and isinstance(row.get('claim_id'), str))
    duplicates = sorted(identity for identity, count in counts.items() if count > 1)
    complete = audit.get('audit_complete')
    return {'interpretation': 'ambiguous' if duplicates else 'complete' if complete is True else 'partial',
            'audit_complete': complete if isinstance(complete, bool) else None,
            'duplicate_claim_ids': duplicates}


def reviews(p):
    """Destination-checked recommendation facts per candidate, from immutable input only."""
    meta = p['method_metadata']
    entries = meta.get('claim_metadata')
    if not isinstance(entries, dict):
        return {}
    audit = audit_summary(meta)
    names = meta['id_map'].get('claims') if isinstance(meta.get('id_map'), dict) else None
    originals = {}
    for original, local in (names.items() if isinstance(names, dict) else ()):
        if isinstance(local, str):  # Producer metadata is free-form; malformed maps never break validation.
            originals.setdefault(local, set()).add(original)
    evidence = {e['id'] for e in p['evidence']}
    result = {}
    for c in p['claims']:
        entry = entries.get(c['id'])
        if not isinstance(entry, dict) or 'uncertainty_review' not in entry:
            continue
        raw = entry['uncertainty_review'] if isinstance(entry['uncertainty_review'], dict) else {}
        notes = raw['limitations'] if isinstance(raw.get('limitations'), list) else []
        notes = [note for note in notes if isinstance(note, str) and note.strip()]
        recommended, basis = grade(raw.get('recommended_class')), raw.get('evidence_ids')
        if raw.get('status') != 'assessed' or recommended is None or not text(raw, 'reason').strip():
            notes.append('No assessed recommendation was recorded; no destination decision or comparison applies.')
            recommended = None
        elif not isinstance(basis, list) or any(not isinstance(e, str) or e not in evidence for e in basis):
            notes.append('The recommendation cites evidence unavailable in this contribution; it remains unassessed.')
            recommended = None
        elif originals.get(c['id'], set()) & set(audit['duplicate_claim_ids']):
            notes.append('Duplicate producer audit rows share this claim; the recommendation remains unassessed.')
            recommended = None
        elif not basis:
            notes.append('The recommendation cites no evidence.')
        if audit['interpretation'] != 'complete':
            notes.append(AUDIT_NOTES[audit['interpretation']])
        result[c['id']] = {
            'status': 'not_assessed' if recommended is None else 'assessed',
            'recommended_uncertainty': recommended,
            'evidence_ids': [] if recommended is None else list(basis),
            # A proposed prior is a destination ID; it is never mapped like a local candidate ID.
            'prior_claim_id': text(raw, 'prior_claim_id') or None,
            'prior_uncertainty': grade(raw.get('prior_class')),
            'prior_match_reason': text(raw, 'prior_match_reason'),
            'limitations': list(dict.fromkeys(notes))}
    return result


def prior_check(facts, candidate, claims):
    """Check a proposed prior against one destination revision; sameness stays a proposal."""
    identity = facts['prior_claim_id']
    if identity is None:
        return None
    prior = claims.get(identity)
    if prior is None or prior['state'] != 'active':
        return {'claim_id': identity, 'status': 'missing', 'uncertainty': None}
    if facts['prior_uncertainty'] != prior['uncertainty']:
        status = 'stale'
    elif (prior['class'] != candidate['class'] or
          temporal_scope(prior.get('valid_time')) != temporal_scope(candidate.get('valid_time'))):
        status = 'scope_differs'
    else:
        status = 'comparable' if facts['prior_match_reason'].strip() else 'no_match_reason'
    return {'claim_id': identity, 'status': status, 'uncertainty': prior['uncertainty']}


def decisions(facts, supplied):
    """One explicit decision per assessed recommendation; returns the adopted grades."""
    fail(isinstance(supplied, dict), 'Uncertainty review decisions must be an object')
    assessed = sorted(cid for cid, f in facts.items() if f['status'] == 'assessed')
    missing, extra = [c for c in assessed if c not in supplied], sorted(set(supplied) - set(assessed))
    fail(not missing, 'Explicitly accept, override or defer each assessed uncertainty recommendation: ' + ', '.join(missing))
    fail(not extra, 'Only assessed uncertainty recommendations take decisions: ' + ', '.join(extra))
    result = {}
    for cid in assessed:
        d, recommended = supplied[cid], facts[cid]['recommended_uncertainty']
        fail(isinstance(d, dict) and set(d) <= {'action', 'uncertainty', 'reason', 'reassessment'} and
             isinstance(d.get('reason'), str) and bool(d['reason'].strip()),
             f'{cid}: an uncertainty decision needs an evidence-based reason')
        fail(d.get('action') in DECISIONS, f'{cid}: uncertainty decisions are accept, override or defer')
        if d['action'] == 'override':
            fail(isinstance(d.get('uncertainty'), str) and d['uncertainty'] in ORDER and d['uncertainty'] != recommended,
                 f'{cid}: an override adopts a different low, medium or high grade')
        fail(d['action'] == 'override' or 'uncertainty' not in d, f'{cid}: only an override supplies its own grade')
        fail(d.get('reassessment') is None or isinstance(d['reassessment'], str),
             f'{cid}: name a linked reassessment by its local operation ID')
        result[cid] = {'decision': d['action'], 'uncertainty': recommended if d['action'] == 'accept' else d.get('uncertainty'),
                       'reason': d['reason'], 'reassessment': d.get('reassessment')}
    return result


def validate_closure(closure, p):
    """A closure with decisions covers every assessed recommendation consistently."""
    records = closure.get('uncertainty_reviews')
    if records is None:
        return  # Legacy closures stay readable; validate_delta requires decisions for new admissions.
    sid, facts = p['id'], reviews(p)
    no_duplicates([r['candidate_id'] for r in records], 'uncertainty review decisions')
    fail({r['candidate_id'] for r in records} == {c for c, f in facts.items() if f['status'] == 'assessed'},
         f'{sid}: every assessed uncertainty recommendation needs one destination decision')
    targets = {d['candidate_id']: d['claim_id'] for d in closure['claim_dispositions']}
    operations = {op['id']: op for op in closure.get('model_operations', [])
                  if isinstance(op, dict) and isinstance(op.get('id'), str)}
    for r in records:
        f = facts[r['candidate_id']]
        fail(r['claim_id'] == targets[r['candidate_id']] and r['recommended_uncertainty'] == f['recommended_uncertainty'],
             f"{sid}: the {r['candidate_id']} uncertainty decision differs from its disposition or recommendation")
        if r['decision'] == 'defer':
            fail(r['uncertainty'] is None and r['reassessment'] is None, f'{sid}: a deferred recommendation changes no grade')
            fail(r['claim_id'] is None or bool(closure['follow_up_gaps']),
                 f'{sid}: deferred uncertainty decisions must be recorded for maintenance')
        else:
            fail(r['claim_id'] is not None, f'{sid}: only an admitted claim can adopt a reviewed grade')
            fail(r['uncertainty'] is not None and
                 (r['uncertainty'] == f['recommended_uncertainty']) == (r['decision'] == 'accept'),
                 f'{sid}: accept adopts the recommendation; override adopts another grade')
        if r['reassessment'] is not None:
            op = operations.get(r['reassessment'], {})
            listed = lambda key, value: isinstance(op.get(key), list) and value in op[key]
            fail(op.get('kind') == 'reassessment' and listed('subject_ids', r['claim_id']) and
                 op.get('uncertainty') == r['uncertainty'] and listed('basis_ids', sid),
                 f'{sid}: a linked reassessment sets the decided grade on that claim and cites the contribution')
        prior = r['prior']
        fail((prior is None) == (f['prior_claim_id'] is None) and (prior is None or prior['claim_id'] == f['prior_claim_id']),
             f'{sid}: the recorded prior check differs from the proposed prior')


def validate_admission(closure, p, before, after):
    """At PR time: decisions exist, prior checks use the actual base and grades match the delta."""
    sid, facts = p['id'], reviews(p)
    fail('uncertainty_reviews' in closure or all(f['status'] != 'assessed' for f in facts.values()),
         f'{sid}: record an explicit decision for every assessed uncertainty recommendation')
    candidates = {c['id']: c for c in p['claims']}
    for r in closure.get('uncertainty_reviews', []):
        candidate = candidates[r['candidate_id']]
        fail(r['prior'] == prior_check(facts[r['candidate_id']], candidate, before),
             f'{sid}: prior checks must use the actual destination base revision')
        if r['claim_id'] is None or (r['decision'] == 'defer' and r['claim_id'] in before):
            continue
        old = before.get(r['claim_id'])
        expected = candidate['uncertainty'] if r['decision'] == 'defer' else r['uncertainty']
        fail(after[r['claim_id']]['uncertainty'] == expected,
             f"{sid}: {r['claim_id']} uncertainty differs from its recorded decision")
        fail((r['reassessment'] is not None) == (old is not None and old['uncertainty'] != expected),
             f"{sid}: link a reassessment exactly when a decision changes an existing claim's grade")


def change(recommended, check):
    if recommended is None or not check or check['status'] != 'comparable':
        return 'not_comparable'
    delta = ORDER[recommended] - ORDER[check['uncertainty']]
    return 'increased' if delta > 0 else 'decreased' if delta < 0 else 'unchanged'


def writer(value):
    """The writer's original label beside its ordinal destination equivalent."""
    label = value.get('class') if isinstance(value, dict) else value
    label = label if isinstance(label, str) else None
    result = {'label': label, 'uncertainty': grade(label)}
    if isinstance(value, dict) and isinstance(value.get('rationale'), str):
        result['rationale_preview'] = value['rationale'][:PREVIEW]
    return result


def horizon(value):
    """Preserve a producer review horizon. It never expires, decays or dates a claim."""
    value = value if isinstance(value, dict) else {}
    policy = value.get('policy') if value.get('policy') in HORIZONS else 'unknown'
    triggers = value['triggers'] if isinstance(value.get('triggers'), list) else []
    result = {'policy': policy, 'as_of': value.get('as_of') if isinstance(value.get('as_of'), str) else None,
              'review_after': value.get('review_after') if isinstance(value.get('review_after'), str) else None,
              'triggers': [t for t in triggers if isinstance(t, str)],
              'rationale_preview': text(value, 'rationale')[:PREVIEW],
              'interpretation': HORIZON_NOTE, 'limitations': []}
    if policy != value.get('policy'):
        result['limitations'].append('Missing or unsupported review horizon; recorded as unknown.')
    if policy == 'scheduled' and result['review_after'] is None:
        result['limitations'].append('A scheduled review horizon has no review date.')
    return result


def adopted(item):
    """The grade a supplied assessment contributes after an explicit admission decision."""
    decision = (item.get('uncertainty_review') or {}).get('decision')
    return decision['uncertainty'] if decision and decision['action'] != 'defer' else item['uncertainty']


def report(run, receipt):
    """Researcher-visible writer, supplied, auditor and destination grades per candidate."""
    entries = run['method_metadata'].get('claim_metadata')
    if not isinstance(entries, dict):
        return {}
    from scripts.world_control import canonical_id  # Deferred: the writer imports this module.
    facts, audit = reviews(run), audit_summary(run['method_metadata'])['interpretation']
    recorded = {r['candidate_id']: r for r in receipt.get('uncertainty_reviews', [])}
    result = {}
    for c in run['claims']:
        entry = entries.get(c['id'])
        if not isinstance(entry, dict):
            continue
        item = {'writer_uncertainty': writer(entry['uncertainty'])} if 'uncertainty' in entry else {}
        if c['id'] in facts:
            f, r = facts[c['id']], recorded.get(c['id'])
            raw = entry['uncertainty_review'] if isinstance(entry['uncertainty_review'], dict) else {}
            originals = raw['original_evidence_ids'] if isinstance(raw.get('original_evidence_ids'), list) else []
            review = {'status': f['status'], 'recommended_uncertainty': f['recommended_uncertainty'],
                      'reason_preview': text(raw, 'reason')[:PREVIEW],
                      'evidence_ids': [canonical_id(run['id'], 'evidence', e) for e in f['evidence_ids']],
                      'original_evidence_ids': [e for e in originals if isinstance(e, str)],
                      'producer_audit': audit, 'prior': None, 'decision': None, 'limitations': list(f['limitations'])}
            if f['prior_claim_id'] is not None:
                check = r['prior'] if r else None
                review['prior'] = {'claim_id': f['prior_claim_id'], 'auditor_uncertainty': f['prior_uncertainty'],
                                   'match_reason_preview': f['prior_match_reason'][:PREVIEW],
                                   'destination_check': check, 'change': change(f['recommended_uncertainty'], check)}
                if check and check['status'] != 'comparable':
                    review['limitations'].append(PRIOR_NOTES[check['status']])
            if r is not None:
                review['decision'] = {'receipt': receipt['id'], 'claim_id': r['claim_id'], 'action': r['decision'],
                                      'uncertainty': r['uncertainty'], 'reason_preview': r['reason'][:PREVIEW],
                                      'reassessment': receipt['id'] + '#' + r['reassessment'] if r['reassessment'] else None}
            elif f['status'] == 'assessed':
                review['limitations'].append('No destination decision was recorded for this assessed recommendation.')
            item['uncertainty_review'] = review
        if 'freshness' in entry:
            item['review_horizon'] = horizon(entry['freshness'])
        result[c['id']] = item
    return result
