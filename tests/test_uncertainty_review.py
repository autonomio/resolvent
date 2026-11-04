"""Synthetic audited-uncertainty handoffs only; no research, producer runtime or real world data."""
from __future__ import annotations
import copy
from pathlib import Path
import tempfile
import unittest

from scripts.model import Invalid, validate_delta, validate_state
from scripts.model_operations import model_digest
from scripts.uncertainty_review import AUDIT_NOTES, HORIZON_NOTE, PRIOR_NOTES
from scripts.world_control import canonical_id, plan_admission
from test_model import ROOT, admitted, contribution, decisions, state_for, write_state
from test_model_operations import QueryFixture

STATEMENT = 'The synthetic fixture value is 7.'


def review(**changes):
    value = {'recommended_class': 'high', 'reason': 'Synthetic auditor judgment citing e1.', 'evidence_ids': ['e1'],
             'original_evidence_ids': ['E1'], 'prior_claim_id': None, 'prior_class': None, 'prior_match_reason': '',
             'status': 'assessed', 'change': 'not_comparable', 'limitations': [],
             'disposition': 'requires_destination_review'}
    value.update(changes)
    return value


def handoff(token='5', **changes):
    """Synthetic source material with a writer grade, an auditor review and a passed review date."""
    p = contribution('source_material', token * 32)
    p['claims'][0].update({'class': 'derived_inference', 'uncertainty': 'medium'})
    p['method_metadata'] = {'producer': 'synthetic-fixture', 'id_map': {'claims': {'C1': 'c1'}, 'evidence': {'E1': 'e1'}},
        'claim_metadata': {'c1': {'uncertainty': {'class': 'moderate', 'score': 2, 'rationale': 'Synthetic writer grade.'},
                                  'uncertainty_review': review(**changes),
                                  'freshness': {'policy': 'scheduled', 'as_of': '2020-01-01', 'review_after': '2021-01-01',
                                                'triggers': [], 'rationale': 'Synthetic review horizon.'}}},
        'independent_audit': {'claim_checks': [{'claim_id': 'C1', 'assessment': 'supported'}], 'audit_complete': True}}
    return p


def decide(p, action='accept', **extra):
    d = decisions(p)
    d['uncertainty_reviews'] = {'c1': {'action': action, 'reason': 'Synthetic destination decision citing e1.', **extra}}
    if action == 'defer':
        d['follow_up_gaps'] = ['Reassess the deferred synthetic uncertainty recommendation for c1.']
    return d


def receipt(state, p):
    return state['briefs/closed/' + p['id'].replace('RUN-', 'BC-') + '.yaml']


def existing():
    """An admitted same-scope claim to propose as the auditor's prior."""
    first = contribution('source_material', '4' * 32)
    first['claims'][0].update({'class': 'derived_inference', 'uncertainty': 'medium'})
    return admitted(first), canonical_id(first['id'], 'claims', 'c1')


def reassess(target, p, grade='high'):
    return {'id': 'assess1', 'kind': 'reassessment', 'subject_ids': [target], 'basis_ids': [p['id']],
            'uncertainty': grade, 'predecessors': {target: None},
            'reason': 'Synthetic acceptance of the audited recommendation for the same proposition.'}


def delta(before, after):
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        old, new = Path(a), Path(b)
        write_state(old, before)
        write_state(new, after)
        validate_delta(new, old, after)


class UncertaintyReviewTests(unittest.TestCase):
    def query(self, state):
        fixture = QueryFixture(state)
        self.addCleanup(fixture.temp.cleanup)
        return fixture.query

    def test_every_assessed_recommendation_needs_one_explicit_decision(self):
        p = handoff(); state = state_for(p)
        with self.assertRaisesRegex(Invalid, 'accept, override or defer each assessed'):
            plan_admission(state, p['id'], decisions(p), ROOT)
        d = decide(p); d['uncertainty_reviews']['c2'] = d['uncertainty_reviews']['c1']
        with self.assertRaisesRegex(Invalid, 'Only assessed'):
            plan_admission(state, p['id'], d, ROOT)
        for bad in ({'action': 'approve'}, {'reason': ' '}, {'uncertainty': 'medium'},
                    {'action': 'override', 'uncertainty': 'high'}, {'action': 'override', 'uncertainty': 'certain'}):
            d = decide(p); d['uncertainty_reviews']['c1'].update(bad)
            with self.subTest(bad=bad), self.assertRaises(Invalid):
                plan_admission(state, p['id'], d, ROOT)
        d = decide(p, 'defer'); d['follow_up_gaps'] = []
        with self.assertRaisesRegex(Invalid, 'recorded for maintenance'):
            plan_admission(state, p['id'], d, ROOT)

    def test_decision_sets_only_the_new_claim_grade_and_keeps_provenance(self):
        for action, extra, expected in (('accept', {}, 'high'), ('override', {'uncertainty': 'medium'}, 'medium'),
                                        ('defer', {}, 'medium')):
            with self.subTest(action=action):
                p = handoff(); state = state_for(p); original = copy.deepcopy(p)
                state.update(plan_admission(state, p['id'], decide(p, action, **extra), ROOT))
                validate_state(state, ROOT, True)
                delta({}, state)
                cid = canonical_id(p['id'], 'claims', 'c1')
                claim = state['claims/' + cid + '.yaml']
                # A passed review date is not expiry: no decay, retirement or valid time.
                self.assertEqual((claim['uncertainty'], claim['state'], 'valid_time' in claim), (expected, 'active', False))
                self.assertEqual(len(claim['evidence_ids']), 1)
                self.assertEqual(state['input-artefacts/' + p['id'] + '.json'], original)
                closure = receipt(state, p)
                self.assertEqual(closure['schema_version'], '1.2')
                self.assertEqual(closure['uncertainty_reviews'], [{'candidate_id': 'c1', 'claim_id': cid,
                    'recommended_uncertainty': 'high', 'decision': action,
                    'uncertainty': None if action == 'defer' else expected,
                    'reason': 'Synthetic destination decision citing e1.', 'reassessment': None, 'prior': None}])
                self.assertEqual(plan_admission(state, p['id'], decide(p, action, **extra), ROOT), {})

    def test_report_keeps_writer_auditor_destination_and_horizon_inspectable(self):
        p = handoff(); state = state_for(p)
        state.update(plan_admission(state, p['id'], decide(p), ROOT))
        q = self.query(state); cid = canonical_id(p['id'], 'claims', 'c1')
        self.assertEqual(q.lookup(cid)['current_assessment']['status'], 'agreed')
        self.assertEqual(q.lookup(cid)['current_assessment']['uncertainty'], 'high')
        item = q.assessments(cid)['items'][0]
        self.assertEqual(item['uncertainty'], 'medium')
        self.assertEqual(item['writer_uncertainty'], {'label': 'moderate', 'uncertainty': 'medium',
                                                      'rationale_preview': 'Synthetic writer grade.'})
        found = item['uncertainty_review']
        self.assertEqual((found['status'], found['recommended_uncertainty'], found['producer_audit']), ('assessed', 'high', 'complete'))
        self.assertEqual(found['evidence_ids'], [canonical_id(p['id'], 'evidence', 'e1')])
        self.assertEqual(found['original_evidence_ids'], ['E1'])
        self.assertEqual(found['decision']['action'], 'accept')
        self.assertEqual(found['decision']['receipt'], receipt(state, p)['id'])
        horizon = item['review_horizon']
        self.assertEqual((horizon['policy'], horizon['review_after'], horizon['interpretation']), ('scheduled', '2021-01-01', HORIZON_NOTE))
        p = handoff('6'); p['method_metadata']['claim_metadata']['c1']['freshness'] = {'policy': 'expires_automatically'}
        state = state_for(p); state.update(plan_admission(state, p['id'], decide(p), ROOT))
        horizon = self.query(state).assessments(canonical_id(p['id'], 'claims', 'c1'))['items'][0]['review_horizon']
        self.assertEqual(horizon['policy'], 'unknown')
        self.assertIn('Missing or unsupported review horizon; recorded as unknown.', horizon['limitations'])

    def test_low_needs_independent_evidence_and_agreement_or_repetition_never_promotes(self):
        p = handoff(recommended_class='low')
        p['method_metadata']['claim_metadata']['c1']['uncertainty']['class'] = 'low'  # Writer and auditor agree.
        with self.assertRaisesRegex(Invalid, 'low uncertainty lacks independent evidence'):
            plan_admission(state_for(p), p['id'], decide(p), ROOT)
        state = state_for(p)
        state.update(plan_admission(state, p['id'], decide(p, 'override', uncertainty='medium'), ROOT))
        repeated = handoff('6', recommended_class='low')  # Another report of the same synthetic observation.
        state.update(state_for(repeated))
        state.update(plan_admission(state, repeated['id'], decide(repeated, 'defer'), ROOT))
        claims = [record for path, record in state.items() if path.startswith('claims/')]
        self.assertEqual([(c['uncertainty'], len(c['evidence_ids'])) for c in claims], [('medium', 2)])
        self.assertEqual(receipt(state, repeated)['claim_dispositions'][0]['disposition'], 'merged')

    def test_merge_changes_an_existing_grade_only_through_linked_reassessment(self):
        base, target = existing()
        p = handoff(prior_claim_id=target, prior_class='moderate', prior_match_reason='Same synthetic proposition and scope.')
        state = copy.deepcopy(base); state.update(state_for(p))
        d = decide(p); d['claims']['c1'] = {'action': 'merge', 'target': target, 'reason': 'Synthetic same proposition.'}
        with self.assertRaisesRegex(Invalid, 'uncertainty or temporal scope differs'):
            plan_admission(state, p['id'], d, ROOT)
        d['uncertainty_reviews']['c1']['reassessment'] = 'assess1'
        d.update(expected_model_sha256=model_digest(state), model_operations=[reassess(target, p)])
        bad = copy.deepcopy(d); bad['model_operations'][0]['basis_ids'] = [target]
        with self.assertRaisesRegex(Invalid, 'cites the contribution'):
            plan_admission(state, p['id'], bad, ROOT)
        proposed = copy.deepcopy(state); proposed.update(plan_admission(state, p['id'], d, ROOT))
        delta(base, proposed)
        self.assertEqual(proposed['claims/' + target + '.yaml']['uncertainty'], 'high')
        record = receipt(proposed, p)['uncertainty_reviews'][0]
        self.assertEqual((record['claim_id'], record['reassessment']), (target, 'assess1'))
        self.assertEqual(record['prior'], {'claim_id': target, 'status': 'comparable', 'uncertainty': 'medium'})
        q = self.query(proposed)
        history = q.assessments(target)
        self.assertEqual(history['current_uncertainty'], 'high')
        operation = [i for i in history['items'] if i['kind'] == 'reassessment'][0]
        self.assertEqual((operation['previous_uncertainty'], operation['uncertainty']), ('medium', 'high'))
        found = [i for i in history['items'] if i.get('uncertainty_review')][0]['uncertainty_review']
        self.assertEqual(found['prior']['change'], 'increased')
        self.assertEqual(found['decision']['reassessment'], receipt(proposed, p)['id'] + '#assess1')
        self.assertEqual(q.lookup(target)['current_assessment']['status'], 'agreed')
        # Deferring a merged review keeps the old grade explicitly and records the follow-up.
        d = decide(p, 'defer'); d['claims']['c1'] = {'action': 'merge', 'target': target, 'reason': 'Synthetic same proposition.'}
        deferred = copy.deepcopy(state); deferred.update(plan_admission(state, p['id'], d, ROOT))
        self.assertEqual(deferred['claims/' + target + '.yaml']['uncertainty'], 'medium')
        self.assertEqual(receipt(deferred, p)['uncertainty_reviews'][0]['decision'], 'defer')

    def test_prior_checks_use_the_current_revision_and_never_map_candidate_ids(self):
        base, target = existing()
        reason = 'Same synthetic proposition and scope.'
        cases = (('c1', 'moderate', reason, 'missing'), (target, 'high', reason, 'stale'),
                 (target, 'moderate', '', 'no_match_reason'), (target, 'moderate', reason, 'comparable'))
        for prior, grade, match, expected in cases:
            with self.subTest(expected=expected):
                p = handoff(prior_claim_id=prior, prior_class=grade, prior_match_reason=match)
                state = copy.deepcopy(base); state.update(state_for(p))
                state.update(plan_admission(state, p['id'], decide(p), ROOT))
                check = receipt(state, p)['uncertainty_reviews'][0]['prior']
                self.assertEqual(check['status'], expected)
                found = self.query(state).assessments(canonical_id(p['id'], 'claims', 'c1'))['items'][0]['uncertainty_review']
                self.assertEqual(found['prior']['change'], 'increased' if expected == 'comparable' else 'not_comparable')
                if expected != 'comparable':
                    self.assertIn(PRIOR_NOTES[expected], found['limitations'])
                    continue
                forged = copy.deepcopy(state); receipt(forged, p)['uncertainty_reviews'][0]['prior']['status'] = 'stale'
                with self.assertRaisesRegex(Invalid, 'actual destination base revision'):
                    delta(base, forged)
        scoped = copy.deepcopy(base); scoped['claims/' + target + '.yaml']['class'] = 'hypothesis'
        p = handoff(prior_claim_id=target, prior_class='moderate', prior_match_reason=reason)
        scoped.update(state_for(p)); scoped.update(plan_admission(scoped, p['id'], decide(p), ROOT))
        self.assertEqual(receipt(scoped, p)['uncertainty_reviews'][0]['prior']['status'], 'scope_differs')

    def test_unassessed_ambiguous_and_incomplete_reviews_stay_explicit_limitations(self):
        duplicate = 'Duplicate audit checks; inspect all rows in independent_audit before destination review.'
        p = handoff(status='not_assessed', recommended_class=None, limitations=[duplicate],
                    reason='Multiple recorded audit checks share this claim ID; no single uncertainty recommendation can be assigned.')
        audit = p['method_metadata']['independent_audit']
        audit['claim_checks'].append(dict(audit['claim_checks'][0], assessment='correction_needed'))
        state = state_for(p); state.update(plan_admission(state, p['id'], decisions(p), ROOT))
        self.assertEqual(receipt(state, p)['schema_version'], '1.0')
        self.assertEqual(state['input-artefacts/' + p['id'] + '.json']['method_metadata']['independent_audit'], audit)
        found = self.query(state).assessments(canonical_id(p['id'], 'claims', 'c1'))['items'][0]['uncertainty_review']
        self.assertEqual((found['status'], found['decision'], found['producer_audit']), ('not_assessed', None, 'ambiguous'))
        self.assertIn(duplicate, found['limitations'])
        self.assertIn(AUDIT_NOTES['ambiguous'], found['limitations'])
        # A producer row marked assessed is not trusted over duplicate raw rows or unavailable evidence.
        for changes in ({}, {'evidence_ids': ['e9']}):
            p = handoff('6', **changes)
            if not changes:
                p['method_metadata']['independent_audit']['claim_checks'] *= 2
            with self.subTest(changes=changes), self.assertRaisesRegex(Invalid, 'Only assessed'):
                plan_admission(state_for(p), p['id'], decide(p), ROOT)
        p = handoff('7'); p['method_metadata']['independent_audit']['audit_complete'] = False
        state = state_for(p); state.update(plan_admission(state, p['id'], decide(p), ROOT))
        found = self.query(state).assessments(canonical_id(p['id'], 'claims', 'c1'))['items'][0]['uncertainty_review']
        self.assertEqual((found['status'], found['producer_audit']), ('assessed', 'partial'))
        self.assertIn(AUDIT_NOTES['partial'], found['limitations'])

    def test_legacy_inputs_and_closures_stay_readable_but_new_admissions_decide(self):
        p = handoff(); del p['method_metadata']['claim_metadata']['c1']['uncertainty_review']
        state = admitted(p)
        self.assertEqual(receipt(state, p)['schema_version'], '1.0')
        self.assertNotIn('uncertainty_review', self.query(state).assessments(canonical_id(p['id'], 'claims', 'c1'))['items'][0])
        p = handoff('8'); meta = p['method_metadata']
        meta.update(id_map={'claims': {'C1': ['c1']}}, independent_audit='legacy audit text')
        meta['claim_metadata']['c1'].update(uncertainty_review='legacy review text', freshness=None)
        item = self.query(admitted(p)).assessments(canonical_id(p['id'], 'claims', 'c1'))['items'][0]
        self.assertEqual((item['uncertainty_review']['status'], item['uncertainty_review']['producer_audit']), ('not_assessed', 'absent'))
        self.assertEqual(item['review_horizon']['policy'], 'unknown')
        p = handoff('6'); state = state_for(p)
        state.update(plan_admission(state, p['id'], decide(p, 'defer'), ROOT))
        legacy = receipt(state, p); del legacy['uncertainty_reviews']; legacy['schema_version'] = '1.0'
        validate_state(state, ROOT, True)
        found = self.query(state).assessments(canonical_id(p['id'], 'claims', 'c1'))['items'][0]['uncertainty_review']
        self.assertIn('No destination decision was recorded for this assessed recommendation.', found['limitations'])
        with self.assertRaisesRegex(Invalid, 'record an explicit decision'):
            delta({}, state)

    def test_forged_decisions_and_materialized_grades_fail_validation(self):
        p = handoff(); state = state_for(p)
        state.update(plan_admission(state, p['id'], decide(p), ROOT))
        cid = canonical_id(p['id'], 'claims', 'c1')
        for field, value, message in (('claim_id', 'C-' + 'f' * 32, 'differs from its disposition'),
                                      ('recommended_uncertainty', 'medium', 'differs from its disposition'),
                                      ('decision', 'override', 'override adopts another grade'),
                                      ('reassessment', 'assess1', 'linked reassessment'),
                                      ('prior', {'claim_id': cid, 'status': 'missing', 'uncertainty': None}, 'proposed prior')):
            forged = copy.deepcopy(state); receipt(forged, p)['uncertainty_reviews'][0][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(Invalid, message):
                validate_state(forged, ROOT, True)
        forged = copy.deepcopy(state); receipt(forged, p)['uncertainty_reviews'].append(receipt(forged, p)['uncertainty_reviews'][0])
        with self.assertRaisesRegex(Invalid, 'Duplicate entries'):
            validate_state(forged, ROOT, True)
        forged = copy.deepcopy(state); forged['claims/' + cid + '.yaml']['uncertainty'] = 'medium'
        validate_state(forged, ROOT, True)
        with self.assertRaisesRegex(Invalid, 'differs from its recorded decision'):
            delta({}, forged)


if __name__ == '__main__':
    unittest.main()
