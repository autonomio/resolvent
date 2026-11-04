"""Synthetic audited-uncertainty handoffs only; no research, producer runtime or real world data."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.build_knowledge import json_bytes
from scripts.model import Invalid, validate_delta, validate_state
from scripts.model_operations import model_digest
from scripts.uncertainty_review import AUDIT_NOTES, HORIZON_NOTE, LONG_NOTE, PRIOR_NOTES
from scripts.world_control import canonical_id, plan_admission
from test_model import ROOT, admitted, contribution, decisions, state_for, write_state
from test_model_operations import QueryFixture, comparison, maintain

MAINTENANCE = 'maintenance/M-' + 'a' * 32 + '.yaml'


def review(**changes):
    value = {'recommended_class': 'high', 'reason': 'Synthetic auditor judgment citing e1.', 'evidence_ids': ['e1'],
             'original_evidence_ids': ['E1'], 'prior_claim_id': None, 'prior_class': None, 'prior_match_reason': '',
             'status': 'assessed', 'change': 'not_comparable', 'limitations': [],
             'disposition': 'requires_destination_review'}
    value.update(changes)
    return value


def handoff(token='5', grade='medium', **changes):
    """Synthetic source material: exported grade, writer grade, auditor review and a passed review date."""
    p = contribution('source_material', token * 32)
    p['claims'][0].update({'class': 'derived_inference', 'uncertainty': grade,
                           'statement': 'The synthetic fixture has a value of seven.'})
    p['method_metadata'] = {'producer': 'synthetic-fixture', 'id_map': {'claims': {'C1': 'c1'}, 'evidence': {'E1': 'e1'}},
        'claim_metadata': {'c1': {'uncertainty': {'class': 'moderate', 'score': 2, 'rationale': 'Synthetic writer grade.'},
                                  'uncertainty_review': review(**changes),
                                  'freshness': {'policy': 'scheduled', 'as_of': '2020-01-01', 'review_after': '2021-01-01',
                                                'triggers': [], 'rationale': 'Synthetic review horizon.'}}},
        'independent_audit': {'claim_checks': [{'claim_id': 'C1', 'assessment': 'supported'}], 'audit_complete': True}}
    return p


def existing(grade='medium', token='4', inspected=False):
    """A same-class claim without producer metadata, to propose as a prior or merge with."""
    p = contribution('source_material', token * 32)
    p['claims'][0].update({'class': 'derived_inference', 'uncertainty': grade})
    return independent(p) if inspected else p


def independent(p):
    p['sources'][0].update(kind='publication', uri='https://example.invalid/' + p['id'], access='inspected')
    p['evidence'][0].update(kind='external', independent=True)
    return p


def claim_id(p):
    return canonical_id(p['id'], 'claims', 'c1')


def evidence_id(p):
    return canonical_id(p['id'], 'evidence', 'e1')


def pending(state, p):
    state = copy.deepcopy(state)
    state.update(state_for(p))
    return state


def admit(state, p, d=None):
    state = pending(state, p)
    state.update(plan_admission(state, p['id'], d or decisions(p), ROOT))
    return state


def regrade(identity, subjects, grade, basis):
    return {'id': identity, 'kind': 'reassessment', 'subject_ids': subjects, 'basis_ids': basis, 'uncertainty': grade,
            'predecessors': {s: None for s in subjects}, 'reason': 'Synthetic merge outcome on the cited basis.'}


def delta(before, after):
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        write_state(Path(a), before)
        write_state(Path(b), after)
        validate_delta(Path(b), Path(a), after)


class UncertaintyReviewTests(unittest.TestCase):
    def query(self, state):
        fixture = QueryFixture(state)
        self.addCleanup(fixture.temp.cleanup)
        return fixture.query

    def supplied(self, state, p):
        return next(i for i in self.query(state).assessments(claim_id(p))['items'] if i['id'] == p['id'] + '#c1')

    def test_admission_uses_the_exported_grade_and_takes_no_uncertainty_decision(self):
        p = handoff(recommended_class='low')
        p['method_metadata']['claim_metadata']['c1']['uncertainty']['class'] = 'low'  # Writer and auditor agree.
        original = copy.deepcopy(p)
        d = decisions(p)
        d['uncertainty_reviews'] = {'c1': {'action': 'accept', 'reason': 'Synthetic.'}}
        with self.assertRaisesRegex(Invalid, 'supported model operations only'):
            plan_admission(state_for(p), p['id'], d, ROOT)
        state = admit({}, p)
        validate_state(state, ROOT, True)
        delta({}, state)
        claim = state['claims/' + claim_id(p) + '.yaml']
        # Agreement is not promotion, and a passed review date is not decay, retirement or valid time.
        self.assertEqual((claim['uncertainty'], claim['state'], 'valid_time' in claim), ('medium', 'active', False))
        self.assertEqual(state['input-artefacts/' + p['id'] + '.json'], original)
        closure = state['briefs/closed/' + p['id'].replace('RUN-', 'BC-') + '.yaml']
        self.assertEqual(closure['schema_version'], '1.0')
        self.assertEqual(plan_admission(state, p['id'], decisions(p), ROOT), {})

    def test_report_keeps_writer_auditor_and_horizon_inspectable(self):
        p = handoff()
        state = admit({}, p)
        q = self.query(state)
        self.assertEqual(q.lookup(claim_id(p))['current_assessment']['status'], 'agreed')  # A review is not a grade.
        history = q.assessments(claim_id(p))
        self.assertEqual(history['current_uncertainty'], 'medium')
        item = history['items'][0]
        self.assertEqual((item['id'], item['uncertainty']), (p['id'] + '#c1', 'medium'))
        self.assertEqual(item['writer_uncertainty'], {'label': 'moderate', 'uncertainty': 'medium',
                                                      'rationale_preview': 'Synthetic writer grade.'})
        found = item['uncertainty_review']
        self.assertEqual({key: found[key] for key in ('status', 'recommended_uncertainty', 'producer_audit', 'audit_verdict',
                                                      'prior', 'limitations')},
                         {'status': 'assessed', 'recommended_uncertainty': 'high', 'producer_audit': 'complete',
                          'audit_verdict': 'supported', 'prior': None, 'limitations': []})
        self.assertEqual((found['evidence_ids'], found['original_evidence_ids']), ([evidence_id(p)], ['E1']))
        horizon = item['review_horizon']
        self.assertEqual((horizon['policy'], horizon['review_after'], horizon['interpretation'], horizon['limitations']),
                         ('scheduled', '2021-01-01', HORIZON_NOTE, []))
        # Worst-case producer text: every string long and escape-heavy, every list long.
        heavy = '\x01' * 1000
        p = handoff('6', evidence_ids=[f'e{n}' for n in range(1, 27)], reason=heavy, prior_claim_id=heavy,
                    prior_match_reason=heavy, original_evidence_ids=[heavy] * 30,
                    limitations=[f'Synthetic producer note {n}: ' + heavy for n in range(30)])
        p['evidence'] += [dict(p['evidence'][0], id=f'e{n}') for n in range(2, 27)]
        p['claims'][0]['evidence_ids'] = [e['id'] for e in p['evidence']]
        entry = p['method_metadata']['claim_metadata']['c1']
        entry['uncertainty'] = {'class': heavy, 'rationale': '\U0001F642' * 1000}
        entry['freshness'] = {'policy': 'expires_automatically', 'as_of': heavy, 'review_after': heavy,
                              'triggers': [f'{n}{heavy}' for n in range(30)], 'rationale': heavy}
        page = self.query(admit({}, p)).assessments(claim_id(p))
        self.assertLessEqual(len(json_bytes(page)), 32768)
        item = page['items'][0]
        self.assertEqual(item['review_horizon']['policy'], 'unknown')
        self.assertIn('Missing or unsupported review horizon; recorded as unknown.', item['review_horizon']['limitations'])
        # Long producer values are bounded for paged reads; the contribution keeps them unchanged.
        notes = item['uncertainty_review']['limitations']
        self.assertIn(LONG_NOTE, notes)
        self.assertEqual(sum(note.startswith('Synthetic producer note') for note in notes), 20)
        self.assertLessEqual(max(len(json.dumps(note, ensure_ascii=False).encode()) - 2 for note in notes), 240)
        self.assertEqual(len(item['uncertainty_review']['evidence_ids']), 20)

    def test_prior_checks_use_the_read_revision_and_never_map_candidate_ids(self):
        first = existing()
        base, target = admitted(first), claim_id(first)
        reason = 'Same synthetic proposition and scope.'
        cases = (('c1', 'moderate', reason, 'missing'), (target, 'high', reason, 'stale'), (target, None, reason, 'stale'),
                 (target, 'moderate', ' ', 'no_match_reason'), (target, 'moderate', reason, 'comparable'))
        for prior, grade, match, expected in cases:
            with self.subTest(expected=expected, grade=grade):
                p = handoff(prior_claim_id=prior, prior_class=grade, prior_match_reason=match)
                found = self.supplied(admit(base, p), p)['uncertainty_review']
                self.assertEqual((found['prior']['claim_id'], found['prior']['destination']['status']), (prior, expected))
                self.assertEqual(found['prior']['uncertainty_change'], 'increased' if expected == 'comparable' else 'not_comparable')
                self.assertEqual(PRIOR_NOTES.get(expected) in found['limitations'], expected != 'comparable')
        scoped = copy.deepcopy(base)
        scoped['claims/' + target + '.yaml']['class'] = 'hypothesis'
        p = handoff(prior_claim_id=target, prior_class='moderate', prior_match_reason=reason)
        self.assertEqual(self.supplied(admit(scoped, p), p)['uncertainty_review']['prior']['destination']['status'], 'scope_differs')
        # The check follows the revision being read: a later reassessment of the prior makes the same review stale.
        state, _, _ = maintain(admit(base, p), [regrade('assess1', [target], 'high', [target])])
        prior = self.supplied(state, p)['uncertainty_review']['prior']
        self.assertEqual((prior['destination'], prior['uncertainty_change'], prior['producer_uncertainty_change']),
                         ({'status': 'stale', 'uncertainty': 'high'}, 'not_comparable', 'not_comparable'))

    def test_unassessed_ambiguous_and_incomplete_reviews_stay_explicit_limitations(self):
        duplicate = 'Duplicate audit checks; inspect all rows in independent_audit before destination review.'
        p = handoff(status='not_assessed', recommended_class=None, limitations=[duplicate],
                    reason='Multiple recorded audit checks share this claim ID; no single uncertainty recommendation can be assigned.')
        audit = p['method_metadata']['independent_audit']
        audit['claim_checks'].append(dict(audit['claim_checks'][0], assessment='correction_needed'))
        state = admit({}, p)
        self.assertEqual(state['input-artefacts/' + p['id'] + '.json']['method_metadata']['independent_audit'], audit)
        found = self.supplied(state, p)['uncertainty_review']
        self.assertEqual((found['status'], found['producer_audit'], found['audit_verdict']), ('not_assessed', 'ambiguous', 'ambiguous'))
        self.assertIn(duplicate, found['limitations'])
        self.assertIn(AUDIT_NOTES['ambiguous'], found['limitations'])
        # A review marked assessed fails closed on duplicate rows (even ones the producer map cannot resolve), an
        # incomplete audit, unavailable or no evidence, or a blank reason; its otherwise comparable prior is never compared.
        first = existing()
        base = admitted(first)
        prior = {'prior_claim_id': claim_id(first), 'prior_class': 'moderate', 'prior_match_reason': 'Same synthetic proposition.'}
        cases = (('6', {}, 'duplicate', AUDIT_NOTES['ambiguous']), ('7', {}, 'unmapped duplicate', AUDIT_NOTES['ambiguous']),
                 ('8', {}, 'incomplete', AUDIT_NOTES['partial']), ('9', {'evidence_ids': ['e9']}, 'unavailable', 'unavailable'),
                 ('c', {'evidence_ids': []}, 'no evidence', 'cites no evidence'),
                 ('b', {'reason': ' '}, 'blank reason', 'No assessed recommendation'))
        for token, changes, case, note in cases:
            p = handoff(token, **prior, **changes)
            meta = p['method_metadata']
            if 'duplicate' in case:
                meta['independent_audit']['claim_checks'] *= 2
            if case == 'unmapped duplicate':
                del meta['id_map']
            if case == 'incomplete':
                meta['independent_audit']['audit_complete'] = False
            found = self.supplied(admit(base, p), p)['uncertainty_review']
            with self.subTest(case=case):
                self.assertEqual((found['status'], found['recommended_uncertainty'], found['evidence_ids']), ('not_assessed', None, []))
                self.assertEqual((found['prior']['destination']['status'], found['prior']['uncertainty_change']),
                                 ('comparable', 'not_comparable'))
                self.assertTrue(any(note in limitation for limitation in found['limitations']))

    def test_legacy_malformed_and_unreviewed_inputs_read_explicitly(self):
        p = handoff()
        del p['method_metadata']['claim_metadata']['c1']['uncertainty_review']  # Exported before reviews existed.
        item = self.supplied(admit({}, p), p)
        self.assertEqual(item['uncertainty_review']['status'], 'not_assessed')
        self.assertIn('No uncertainty review was recorded for this candidate.', item['uncertainty_review']['limitations'])
        p = handoff('6')
        meta = p['method_metadata']
        meta.update(id_map={'claims': {'C1': ['c1']}}, independent_audit='legacy audit text')
        meta['claim_metadata']['c1'].update(uncertainty='moderate', uncertainty_review='legacy review text', freshness=None)
        item = self.supplied(admit({}, p), p)
        self.assertEqual((item['uncertainty_review']['status'], item['uncertainty_review']['producer_audit']), ('not_assessed', 'absent'))
        self.assertEqual((item['writer_uncertainty'], item['review_horizon']['policy']),
                         ({'label': 'moderate', 'uncertainty': 'medium'}, 'unknown'))
        p = existing(token='7')  # No per-candidate metadata: nothing is recorded or invented.
        self.assertEqual(set(self.supplied(admit({}, p), p)), {'id', 'kind', 'uncertainty', 'disposition'})

    def test_admission_keeps_differing_reviewed_grades_separate_for_maintenance(self):
        first = existing('high')
        base, target = admitted(first), claim_id(first)
        p = handoff(prior_claim_id=target, prior_class='high', prior_match_reason='Same synthetic proposition.')
        state = pending(base, p)
        d = decisions(p)
        d['claims']['c1'] = {'action': 'merge', 'target': target, 'reason': 'Synthetic same proposition.'}
        with self.assertRaisesRegex(Invalid, 'uncertainty or temporal scope differs'):
            plan_admission(state, p['id'], d, ROOT)
        d = decisions(p)
        d.update(expected_model_sha256=model_digest(state), model_operations=[comparison([target, claim_id(p)])])
        with self.assertRaisesRegex(Invalid, 'in maintenance'):
            plan_admission(state, p['id'], d, ROOT)
        separate = admit(base, p)
        self.assertEqual({r['id']: r['uncertainty'] for k, r in separate.items() if k.startswith('claims/')},
                         {target: 'high', claim_id(p): 'medium'})
        # An equal-grade merge keeps the incoming review visible on the target.
        same = existing('medium', '3')
        p = handoff('6')
        d = decisions(p)
        d['claims']['c1'] = {'action': 'merge', 'target': claim_id(same), 'reason': 'Synthetic same proposition.'}
        items = self.query(admit(admitted(same), p, d)).assessments(claim_id(same))['items']
        self.assertEqual([i['id'] for i in items if 'uncertainty_review' in i], [p['id'] + '#c1'])

    def test_maintenance_merge_records_old_and_incoming_grades_basis_and_outcome(self):
        first, p = existing('high'), handoff()
        base = admit(admitted(first), p)
        old, new = claim_id(first), claim_id(p)
        evidence, merge = [evidence_id(first), evidence_id(p)], comparison([old, new])
        attempts = (([merge], 'reassesses every merged claim'),
                    ([merge, regrade('grade1', [new], 'high', evidence + [p['id']])], 'reassesses every merged claim'),
                    ([merge, regrade('grade1', [old, new], 'medium', evidence + [p['id']])], 'needs cited independent'),
                    ([merge, regrade('grade1', [old, new], 'high', evidence)], 'cites each run'))
        for operations, message in attempts:
            with self.subTest(message=message), self.assertRaisesRegex(Invalid, message):
                maintain(base, operations)
        state, _, _ = maintain(base, [merge, regrade('grade1', [old, new], 'high', evidence + [p['id']])])
        delta(base, state)
        record = state[MAINTENANCE]['model_operations'][1]
        self.assertEqual((record['previous_uncertainty'], record['uncertainty']), ({old: 'high', new: 'medium'}, 'high'))
        q = self.query(state)
        self.assertEqual(q.lookup(new)['current_assessment']['status'], 'agreed')
        for subject, previous in ((old, 'high'), (new, 'medium')):
            history = q.assessments(subject)
            operation = next(i for i in history['items'] if i['kind'] == 'reassessment')
            self.assertEqual((operation['previous_uncertainty'], operation['uncertainty']), (previous, 'high'))
        # The review is not dropped: it stays on the incoming supplied grade, and the merge cites its run.
        supplied = q.assessments(new)['items'][0]
        self.assertEqual((supplied['uncertainty'], supplied['uncertainty_review']['recommended_uncertainty']), ('medium', 'high'))
        forged = copy.deepcopy(state)
        forged[MAINTENANCE]['model_operations'][1]['basis_ids'].remove(p['id'])
        with self.assertRaisesRegex(Invalid, 'cites each run'):
            delta(base, forged)

    def test_merges_never_promote_confidence_from_repetition_or_model_agreement(self):
        state = {}
        for token in ('5', '6'):  # Repeated publication of one cohort; writer and auditor agree on low.
            p = handoff(token, recommended_class='low')
            p['method_metadata']['claim_metadata']['c1']['uncertainty']['class'] = 'low'
            state = admit(state, p)
        claims = [r for k, r in state.items() if k.startswith('claims/')]
        self.assertEqual([(c['uncertainty'], len(c['evidence_ids'])) for c in claims], [('medium', 2)])
        # Even independent evidence cannot take a merge past the most confident merged grade.
        first, p = existing('medium', inspected=True), independent(handoff('7', 'high', recommended_class='low'))
        base = admit(admitted(first), p)
        old, new = claim_id(first), claim_id(p)
        basis = [evidence_id(first), evidence_id(p), p['id']]
        with self.assertRaisesRegex(Invalid, 'never ends more confident'):
            maintain(base, [comparison([old, new]), regrade('grade1', [old, new], 'low', basis)])
        state, _, _ = maintain(base, [comparison([old, new]), regrade('grade1', [old, new], 'medium', basis)])
        delta(base, state)
        self.assertEqual({state['claims/' + c + '.yaml']['uncertainty'] for c in (old, new)}, {'medium'})

    def test_equal_grade_and_unreviewed_merges_keep_existing_behavior(self):
        first, p = existing(), handoff()
        base = admit(admitted(first), p)
        state, _, _ = maintain(base, [comparison([claim_id(first), claim_id(p)])])
        delta(base, state)
        self.assertEqual(self.query(state).lookup(claim_id(p))['current_assessment']['status'], 'agreed')
        first, second = existing('high'), existing('medium', '6')
        base = admit(admitted(first), second)
        state, _, _ = maintain(base, [comparison([claim_id(first), claim_id(second)])])
        delta(base, state)
        self.assertEqual(self.query(state).lookup(claim_id(first))['current_assessment']['status'], 'disputed')


if __name__ == '__main__':
    unittest.main()
