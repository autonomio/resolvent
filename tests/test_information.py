"""The information ledger's promises, each stated as a known change and its exact reading."""
from __future__ import annotations

import copy
from fractions import Fraction
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

from scripts.answers import admitted_set
from scripts.information import (GROUPS, Commitment, History, Invalid, Measure, bits, commitment_delta, delta, ledger,
                                 origin_key, period_end, poisson_quantile, wilson)


def source(sid: str, uri: str | None, *, kind='publication', title='T', **extra) -> dict:
    return {'id': sid, 'kind': kind, 'title': title, 'uri': uri, 'date': '2026-01-01', 'locator': 'p1',
            'excerpt': 'x', 'access': 'inspected', **extra}


def evidence(eid: str, sources: list[str], claims: list[str], *, independent=False, premises=()) -> dict:
    return {'id': eid, 'kind': 'external', 'summary': 's', 'source_ids': sources, 'independent': independent,
            'limitations': [], 'premise_claim_ids': list(premises), 'claim_ids': claims}


def claim(cid: str, evidence_ids: list[str], *, uncertainty='medium', kind='observed_fact', state='active') -> dict:
    return {'id': cid, 'class': kind, 'statement': 'Statement ' + cid, 'uncertainty': uncertainty,
            'evidence_ids': evidence_ids, 'state': state}


def world() -> dict:
    """Three claims over three documents; C-b and C-c share document B."""
    records = {group: {} for group in GROUPS}
    for item in (source('S-a1', 'https://a.example/doc'), source('S-a2', 'https://A.example/doc#page=2'),
                 source('S-b', 'https://b.example/doc'), source('S-c', 'https://c.example/doc')):
        records['sources'][item['id']] = item
    for item in (evidence('E-a', ['S-a1', 'S-a2'], ['C-a']), evidence('E-b', ['S-b'], ['C-b', 'C-c']),
                 evidence('E-c', ['S-c'], ['C-c'], independent=True)):
        records['evidence'][item['id']] = item
    for item in (claim('C-a', ['E-a']), claim('C-b', ['E-b'], kind='derived_inference'),
                 claim('C-c', ['E-b', 'E-c'], uncertainty='low')):
        records['claims'][item['id']] = item
    return records


def gain(report: dict) -> dict:
    return {key: report['gain'][key] for key in ('claims', 'origins', 'links', 'citations')}


class Ledger(unittest.TestCase):
    def test_counts_origins_not_passages(self):
        totals = ledger(world())['totals']
        self.assertEqual((totals['claims'], totals['origins'], totals['links'], totals['citations']), (3, 3, 4, 5))
        self.assertEqual(totals['repeat_citations'], 1)  # two passages of document A bear on one claim
        self.assertEqual(totals['origins_by_identity_basis']['uri'], 3)

    def test_attribution_sums_exactly_to_the_whole_for_any_partition(self):
        m = Measure(world())
        shares = {cid: m.attribution(cid) for cid in m.claims}
        self.assertEqual(shares, {'C-a': Fraction(1), 'C-b': Fraction(1, 2), 'C-c': Fraction(3, 2)})
        self.assertEqual(sum(shares.values()), len(m.origins))
        report = ledger(world())
        for field in ('by_class', 'by_uncertainty'):
            total = sum(Fraction(part['origins_attributed']['exact']) for part in report[field].values())
            self.assertEqual(total, 3)

    def test_parts_have_reach_exclusive_and_shared_origins(self):
        m = Measure(world())
        self.assertEqual((m.coverage(['C-b', 'C-c']), m.exclusive(['C-b', 'C-c']), m.exclusive(['C-b'])), (2, 2, 0))
        self.assertEqual((m.shared(['C-b'], ['C-c']), m.shared(['C-a'], ['C-c'])), (1, 0))

    def test_wording_and_identifiers_are_invisible(self):
        base, reworded = world(), world()
        for record in reworded['claims'].values():
            record['statement'] = 'Completely different and far longer wording. ' * 40
        self.assertEqual(ledger(base), ledger(reworded))
        self.assertEqual(delta(base, reworded)['outcome'], 'unmeasured_edit_only')
        shuffled = {group: dict(reversed(list(items.items()))) for group, items in world().items()}
        self.assertEqual(ledger(base), ledger(shuffled))

    def test_identity_uses_declared_digest_then_address_then_record(self):
        self.assertEqual(origin_key(source('S-1', 'HTTPS://Host.example/p?q=1#frag'))[1], 'uri:https://host.example/p?q=1')
        self.assertEqual(origin_key(source('S-2', None, kind='simulation', title='Run 1')), ('generated', 'source:S-2'))
        digest = {'status': 'unknown', 'parent_source_ids': [], 'notes': ['n'], 'content_sha256': 'a' * 64}
        self.assertEqual(origin_key(source('S-3', 'https://x.example', ancestry=digest))[1], 'sha256:' + 'a' * 64)
        records = world()  # the same bytes at two addresses are one origin once the digest is declared
        records['sources']['S-b']['ancestry'] = digest
        records['sources']['S-c']['ancestry'] = digest
        self.assertEqual(ledger(records)['totals']['origins'], 2)

    def test_identical_titles_without_addresses_do_not_fold_distinct_sources(self):
        records = world()
        for sid in ('S-b', 'S-c'):
            records['sources'][sid] = source(sid, None, kind='simulation', title='Simulation run')
        totals = ledger(records)['totals']
        self.assertEqual(totals['origins'], 3)
        self.assertEqual(totals['origins_by_identity_basis'], {'sha256': 0, 'uri': 1, 'title': 0, 'source': 2})

    def test_multi_origin_citations_repeat_only_another_citation_with_the_same_origins(self):
        first = world()
        first['sources']['S-summary'] = source('S-summary', 'https://example.org/summary', ancestry={
            'status': 'derived', 'parent_source_ids': ['S-b', 'S-c'], 'notes': ['Draws on two originals'],
        })
        first['evidence']['E-b']['source_ids'] = ['S-summary']
        first['evidence']['E-a']['source_ids'] = ['S-a1']
        totals = ledger(first)['totals']
        self.assertEqual((totals['citations'], totals['links'], totals['repeat_citations']), (4, 5, 0))
        second = copy.deepcopy(first)
        second['sources']['S-copy'] = source('S-copy', None, ancestry={
            'status': 'derived', 'parent_source_ids': ['S-summary'], 'notes': ['Repeats the summary'],
        })
        second['evidence']['E-b']['source_ids'].append('S-copy')
        self.assertEqual(ledger(second)['totals']['repeat_citations'], 2)  # both citing claims
        self.assertEqual(delta(first, second)['gain']['repeat_citations'], 2)
        self.assertEqual(delta(second, first)['gain']['repeat_citations'], -2)
        subset = copy.deepcopy(first)
        subset['evidence']['E-b']['source_ids'].append('S-b')
        change = delta(first, subset)
        self.assertEqual((change['gain']['citations'], change['gain']['repeat_citations']), (2, 0))
        self.assertEqual(change['claims']['C-b']['verdict'], 'adds_citation')
        self.assertEqual(change['outcome'], 'adds_citations')
        with tempfile.TemporaryDirectory() as temporary:
            Currency().history(Path(temporary), [(0, first, []), (1, second, []), (2, first, [])])
            steps = History(Path(temporary)).replay('HEAD')['steps']
        self.assertEqual([row['step']['gain']['repeat_citations'] for row in steps], [0, 2, -2])

    def test_declared_ancestry_resolves_to_the_original(self):
        records = world()
        records['sources']['S-root'] = source('S-root', 'https://root.example/original')
        for sid in ('S-b', 'S-c'):
            records['sources'][sid]['ancestry'] = {'status': 'derived', 'parent_source_ids': ['S-root'], 'notes': ['n']}
        report = delta(world(), records)
        self.assertEqual((report['gain']['origins'], report['gain']['links']), (-1, -1))
        self.assertEqual(ledger(records)['totals']['origins'], 2)

    def test_connectors_repeating_endpoint_evidence_add_no_observation(self):
        records = world()
        records['graph']['R-1'] = {'id': 'R-1', 'from': 'C-a', 'to': 'C-b', 'type': 'coupling',
                                   'spec': 'structural:weak:balanced', 'reason': 'r', 'uncertainty': 'high',
                                   'evidence_ids': ['E-a', 'E-b'], 'state': 'active'}
        report = delta(world(), records)
        self.assertEqual(gain(report), {'claims': 0, 'origins': 0, 'links': 0, 'citations': 0})
        self.assertEqual((report['outcome'], report['gain']['connectors_with_own_origins']), ('adds_connectors', 0))
        records['graph']['R-1']['evidence_ids'] = ['E-c']
        self.assertEqual(ledger(records)['connectors']['with_own_origins'], 1)


class Delta(unittest.TestCase):
    def step(self, change) -> dict:
        after = world()
        change(after)
        return delta(world(), after)

    def test_repeat_citation_is_exactly_zero(self):
        def change(records):
            records['sources']['S-a3'] = source('S-a3', 'https://a.example/doc')
            records['evidence']['E-a']['source_ids'].append('S-a3')
        report = self.step(change)
        self.assertEqual(gain(report), {'claims': 0, 'origins': 0, 'links': 0, 'citations': 1})
        self.assertEqual((report['outcome'], report['claims']['C-a']['verdict']), ('repeat_citations_only', 'repeat_citation'))

    def test_new_origin_on_shared_evidence_is_one_origin_split_between_its_claims(self):
        def change(records):
            records['sources']['S-d'] = source('S-d', 'https://d.example/doc')
            records['evidence']['E-b']['source_ids'].append('S-d')
        report = self.step(change)
        self.assertEqual(gain(report), {'claims': 0, 'origins': 1, 'links': 2, 'citations': 2})
        self.assertEqual({row['origins']['exact'] for row in report['claims'].values()}, {'1/2'})
        self.assertEqual({row['verdict'] for row in report['claims'].values()}, {'gains_origin'})

    def test_known_origin_reaching_another_claim_adds_a_link_not_an_origin(self):
        report = self.step(lambda records: records['evidence']['E-a']['source_ids'].append('S-c'))
        self.assertEqual(gain(report), {'claims': 0, 'origins': 0, 'links': 1, 'citations': 1})
        self.assertEqual(report['outcome'], 'adds_links')

    def test_new_claims_are_split_by_whether_their_origin_is_new(self):
        def change(records):
            records['sources']['S-d'] = source('S-d', 'https://d.example/doc')
            records['evidence']['E-d'] = evidence('E-d', ['S-d'], ['C-d'])
            records['evidence']['E-e'] = evidence('E-e', ['S-b'], ['C-e'])
            records['claims']['C-d'] = claim('C-d', ['E-d'])
            records['claims']['C-e'] = claim('C-e', ['E-e'])
        report = self.step(change)
        self.assertEqual(gain(report), {'claims': 2, 'origins': 1, 'links': 2, 'citations': 2})
        self.assertEqual({cid: row['verdict'] for cid, row in report['claims'].items()},
                         {'C-d': 'new_claim_new_origin', 'C-e': 'new_claim_known_origins'})
        self.assertEqual(report['known_origin_share']['exact'], '1/2')

    def test_retirement_loses_exactly_the_exclusive_origins(self):
        report = self.step(lambda records: records['claims']['C-c'].update(state='retired'))
        self.assertEqual(gain(report), {'claims': -1, 'origins': -1, 'links': -2, 'citations': -2})
        self.assertEqual((report['outcome'], report['claims']['C-c']['verdict']), ('loss', 'retired'))

    def test_reassessment_and_unattached_material_are_reported_without_gain(self):
        report = self.step(lambda records: records['claims']['C-a'].update(uncertainty='high'))
        self.assertEqual((report['outcome'], report['claims']['C-a']['effects']), ('reassessment_only', ['reassessed:uncertainty']))

        def orphan(records):
            records['sources']['S-o'] = source('S-o', 'https://o.example/doc')
            records['evidence']['E-o'] = evidence('E-o', ['S-o'], [])
        report = self.step(orphan)
        self.assertEqual((report['outcome'], report['gain']['origins'], report['gain']['unattached_evidence']),
                         ('unattached_material_only', 0, 1))

    def test_restatement_cue_is_a_cue_and_never_a_gain(self):
        def change(records):
            records['evidence']['E-e'] = evidence('E-e', ['S-b'], ['C-e'])
            records['claims']['C-e'] = {**claim('C-e', ['E-e']), 'statement': 'Statement C-b'}
        report = self.step(change)
        self.assertEqual([(cue['claim_id'], cue['earlier_claim_id'], cue['basis']) for cue in report['review_cues']],
                         [('C-e', 'C-b', 'heuristic')])
        self.assertEqual(gain(report), {'claims': 1, 'origins': 0, 'links': 1, 'citations': 1})


YES_NO = {'kind': 'categorical', 'values': ['yes', 'no']}
RATE = {'kind': 'numeric', 'low': '0', 'high': '100', 'step': '1'}


def values(question: str, *chosen: str) -> dict:
    return {'question_id': question, 'values': list(chosen), 'evidence_ids': ['E-x']}


def ranges(question: str, *pairs: tuple[str, str]) -> dict:
    return {'question_id': question, 'ranges': [{'low': low, 'high': high} for low, high in pairs], 'evidence_ids': ['E-x']}


def asked() -> dict:
    """The base world plus two declared questions; C-a answers the focus one, C-b the numeric one."""
    records = world()
    records['questions'] = {
        'Q-f': {'id': 'Q-f', 'question': 'Gated?', 'claim_ids': [], 'state': 'open', 'space': YES_NO, 'focus': True},
        'Q-n': {'id': 'Q-n', 'question': 'Rate?', 'claim_ids': [], 'state': 'open', 'space': RATE}}
    records['claims']['C-a']['answers'] = [values('Q-f', 'yes')]
    records['claims']['C-b']['answers'] = [ranges('Q-n', ('40', '50'))]
    return records


def answering(records: dict, cid: str, answer: dict) -> dict:
    records = copy.deepcopy(records)
    records['evidence']['E-' + cid] = evidence('E-' + cid, ['S-b'], [cid])
    records['claims'][cid] = {**claim(cid, ['E-' + cid]), 'answers': [answer]}
    return records


class Commitments(unittest.TestCase):
    def reading(self, before: dict, after: dict, question: str, cid: str) -> tuple:
        row = delta(before, after)['commitment']['questions'][question]
        answer = row['answers'][cid]
        surprise = answer.get('surprise')
        return (answer['verdict'], surprise if surprise in (None, 'infinite') else surprise['ratio'], row['gain']['ratio'])

    def test_undeclared_models_measure_nothing_and_stay_valid(self):
        report = ledger(world())['commitment']
        self.assertEqual((report['questions'], report['held']['bits'], report['claims_answering_nothing']), (0, 0.0, 3))
        self.assertEqual(delta(world(), world())['commitment']['questions'], {})

    def test_bits_held_and_capacity(self):
        report = ledger(asked())['commitment']
        self.assertEqual(report['by_question']['Q-f']['held'], {'ratio': '2/1', 'bits': 1.0})
        self.assertEqual(report['by_question']['Q-n']['held']['ratio'], '101/11')  # cells 40..50 of 0..100
        self.assertEqual(report['by_question']['Q-n']['capacity']['ratio'], '101/1')
        self.assertEqual((report['held_on_focus']['bits'], report['questions_fully_resolved']), (1.0, 1))

    def test_first_answer_repeat_narrowing_and_weaker_answer(self):
        base = asked()
        empty = copy.deepcopy(base)
        del empty['claims']['C-b']['answers']
        self.assertEqual(self.reading(empty, base, 'Q-n', 'C-b'), ('first_answer', '101/11', '101/11'))
        self.assertEqual(self.reading(base, answering(base, 'C-x', ranges('Q-n', ('40', '50'))), 'Q-n', 'C-x'),
                         ('repeats', '1/1', '1/1'))
        self.assertEqual(self.reading(base, answering(base, 'C-x', ranges('Q-n', ('0', '90'))), 'Q-n', 'C-x'),
                         ('repeats', '1/1', '1/1'))
        # a consistent answer gains exactly its surprise
        self.assertEqual(self.reading(base, answering(base, 'C-x', ranges('Q-n', ('48', '60'))), 'Q-n', 'C-x'),
                         ('narrows', '11/3', '11/3'))

    def test_contradiction_is_infinite_surprise_and_lost_bits_without_any_polarity_label(self):
        base = asked()
        against = answering(base, 'C-x', values('Q-f', 'no'))
        self.assertEqual(self.reading(base, against, 'Q-f', 'C-x'), ('conflicts', 'infinite', '1/2'))
        report = ledger(against)['commitment']['by_question']['Q-f']
        self.assertEqual((report['held']['bits'], report['conflict'], report['consistent_groups']), (0.0, True, 2))
        # two claims against one: nothing is voted on, the question stays unresolved
        outvoted = answering(against, 'C-y', values('Q-f', 'yes'))
        self.assertEqual(ledger(outvoted)['commitment']['by_question']['Q-f']['held']['bits'], 0.0)
        # withdrawing one side restores the bit
        against['claims']['C-x']['state'] = 'retired'
        self.assertEqual(ledger(against)['commitment']['by_question']['Q-f']['held']['bits'], 1.0)
        numeric = answering(base, 'C-x', ranges('Q-n', ('70', '80')))  # two equal, disjoint ranges cost exactly one bit
        self.assertEqual(self.reading(base, numeric, 'Q-n', 'C-x'), ('conflicts', 'infinite', '1/2'))

    def test_agreeing_group_or_dissenter_remains_admitted(self):
        records = answering(answering(asked(), 'C-x', ranges('Q-n', ('45', '60'))), 'C-y', ranges('Q-n', ('90', '90.4')))
        state = Commitment(records).states['Q-n']
        self.assertEqual((state['admitted'], len(state['maximal'])), (6 + 1, 2))  # cells 45..50, or cell 90

    def test_digits_beyond_the_declared_step_earn_nothing(self):
        fine, coarse = ranges('Q-n', ('41.99999999999999999', '42.00000000000000001')), ranges('Q-n', ('41.6', '42.4'))
        self.assertEqual(admitted_set(RATE, fine), admitted_set(RATE, coarse))
        report = ledger(answering(asked(), 'C-x', fine))['commitment']
        self.assertEqual(report, ledger(answering(asked(), 'C-x', coarse))['commitment'])
        self.assertLessEqual(report['held']['bits'], report['capacity']['bits'])

    def test_rewording_that_widens_an_answer_is_measured(self):
        base, loose = asked(), asked()
        loose['claims']['C-b']['answers'] = [ranges('Q-n', ('30', '60'))]
        self.assertEqual(self.reading(base, loose, 'Q-n', 'C-b'), ('widened', None, '11/31'))

    def test_bits_land_on_the_question_answered(self):
        base = asked()
        report = delta(base, answering(base, 'C-x', ranges('Q-n', ('48', '60'))))['commitment']
        self.assertEqual((report['gain_on_focus']['ratio'], report['gain_off_focus']['ratio']), ('1/1', '11/3'))


def compared(left: str, right: str, outcome: str, supersedes=None) -> dict:
    return {'id': 'x', 'kind': 'comparison', 'subject_ids': [left, right], 'basis_ids': ['E-a'], 'reason': 'r',
            'read_sha256': {}, 'outcome': outcome, 'supersedes': supersedes}


class Equivalence(unittest.TestCase):
    def judged(self, **operations) -> dict:
        records = world()
        records['operations'] = operations
        return records

    def test_claims_the_repository_judged_equivalent_are_one_proposition(self):
        report = ledger(self.judged(**{'M-1#x': compared('C-a', 'C-b', 'equivalent')}))
        self.assertEqual((report['totals']['claims'], report['totals']['propositions']), (3, 2))
        self.assertEqual(report['equivalence']['claims_folded'], 1)
        # C-a rests on document A and C-b on document B: the same finding now has two origins
        self.assertEqual(report['equivalence']['groups_drawing_on_several_origins'], 1)
        self.assertEqual(ledger(world())['totals']['propositions'], 3)

    def test_recording_an_equivalence_is_read_as_a_fold_not_as_new_information(self):
        report = delta(world(), self.judged(**{'M-1#x': compared('C-a', 'C-b', 'equivalent')}))
        self.assertEqual(gain(report), {'claims': 0, 'origins': 0, 'links': 0, 'citations': 0})
        self.assertEqual((report['outcome'], report['gain']['propositions']), ('records_equivalence', -1))
        self.assertEqual(report['equivalences'], [{'claims': ['C-a', 'C-b'], 'origins': 2, 'verdict': 'adds_origins'}])

    def test_equivalent_claims_answering_one_question_differently_are_reported(self):
        records = asked()
        records['claims']['C-c']['answers'] = [values('Q-f', 'no')]
        self.assertEqual(ledger(records)['commitment']['equivalent_groups_answering_differently'], 0)
        records['operations'] = {'M-1#x': compared('C-a', 'C-c', 'equivalent')}
        report = ledger(records)['commitment']
        self.assertEqual((report['equivalent_groups_answering_differently'], report['by_question']['Q-f']['conflict']), (1, True))

    def test_only_the_standing_judgment_counts(self):
        records = self.judged(**{'M-1#x': compared('C-a', 'C-b', 'equivalent'),
                                 'M-2#x': compared('C-a', 'C-b', 'distinct', supersedes='M-1#x')})
        self.assertEqual(ledger(records)['totals']['propositions'], 3)
        self.assertEqual(ledger(records)['equivalence']['compared_pairs'], {'distinct': 1})

    def test_splitting_a_group_does_not_fold_or_tag_its_remaining_members(self):
        before = self.judged(**{'M-1#x': compared('C-a', 'C-b', 'equivalent'),
                                'M-2#x': compared('C-b', 'C-c', 'equivalent')})
        after = copy.deepcopy(before)
        after['operations']['M-3#x'] = compared('C-b', 'C-c', 'distinct', supersedes='M-2#x')
        after['claims']['C-b']['uncertainty'] = 'high'
        report = delta(before, after)
        self.assertEqual((report['gain']['propositions'], report['equivalences']), (1, []))
        self.assertEqual(report['claims']['C-b']['loss'], ['uncertainty_raised'])
        self.assertFalse(report['claims']['C-b']['at_equivalence'])

    def test_a_pair_already_judged_is_not_flagged_again(self):
        def restated(operations):
            after = self.judged(**operations)
            after['evidence']['E-e'] = evidence('E-e', ['S-b'], ['C-e'])
            after['claims']['C-e'] = {**claim('C-e', ['E-e']), 'statement': 'Statement C-b'}
            return delta(world(), after)['review_cues']
        self.assertEqual([cue['earlier_claim_id'] for cue in restated({})], ['C-b'])
        judged = restated({'M-1#x': compared('C-b', 'C-e', 'overlap')})
        self.assertNotIn('C-b', [cue['earlier_claim_id'] for cue in judged])


class Currency(unittest.TestCase):
    T0 = 1769904000  # 2026-02-01T00:00:00Z

    def history(self, root: Path, states: list[tuple[int, dict, list]]) -> None:
        git = lambda *args, **env: subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True,
                                                  env={'PATH': __import__('os').environ['PATH'], **env})
        git('init', '-q')
        for number, (day, state, judgments) in enumerate(states):
            for group in GROUPS:
                (root / group).mkdir(exist_ok=True)
                for record_id, record in state[group].items():
                    (root / group / f'{record_id}.yaml').write_text(yaml.safe_dump(record), encoding='utf-8')
            for record in judgments:
                folder = root / ('briefs/closed' if record['id'].startswith('BC-') else 'maintenance')
                folder.mkdir(parents=True, exist_ok=True)
                (folder / f"{record['id']}.yaml").write_text(yaml.safe_dump(record), encoding='utf-8')
            when = f'{self.T0 + day * 86400} +0000'
            git('add', '-A')
            git('-c', 'user.name=t', '-c', 'user.email=t@example.invalid', 'commit', '-q', '--allow-empty', '-m', f'step {number}',
                GIT_COMMITTER_DATE=when, GIT_AUTHOR_DATE=when)

    def test_clocks_attrition_and_walk_forward_come_from_recorded_history_only(self):
        first, second = world(), world()
        second['claims']['C-a']['uncertainty'] = 'high'  # weakened when reviewed on day 1
        review = {'id': 'M-1', 'status': 'completed', 'reviewed_claim_ids': ['C-a', 'C-b']}
        pending = {'id': 'M-2', 'status': 'pending', 'reviewed_claim_ids': ['C-c']}
        with tempfile.TemporaryDirectory() as temporary:
            self.history(Path(temporary), [(0, first, []), (1, second, [review, pending]), (3, second, [review, pending])])
            report, again = History(Path(temporary)).replay('HEAD'), History(Path(temporary)).replay('HEAD')
        self.assertEqual(report, again)  # as_of is the last recorded commit time, never the wall clock
        now = report['currency']
        self.assertEqual((now['as_of'], now['history_days']), ('2026-02-04T00:00:00Z', 3.0))
        clocks = now['clocks_days']
        self.assertEqual((clocks['since_admitted']['max'], clocks['since_last_review']['max'], clocks['never_reviewed']), (3.0, 2.0, 1))
        self.assertEqual(clocks['since_newest_evidence_reported_at_least']['min'], 34)  # sources dated 2026-01-01
        found = now['attrition']
        self.assertEqual((found['reviews'], found['losses'], found['losses_by_kind']), (2, 1, {'uncertainty_raised': 1}))
        self.assertEqual(found['loss_per_review']['estimate'], 0.5)
        self.assertEqual(found['loss_per_claim_day']['exposure'], 9.0)  # three claims over three days
        self.assertEqual((found['losses_when_folded_as_equivalent'], found['losses_otherwise']), (0, 1))
        low, high = found['loss_per_claim_day']['interval95']
        self.assertTrue(low < found['loss_per_claim_day']['estimate'] < high)
        self.assertEqual((now['walk_forward']['windows'], now['walk_forward']['inside']), (2, 2))
        self.assertLessEqual(now['projection']['horizon_days'], now['history_days'])
        self.assertNotIn('half_life', found['loss_per_claim_day'])

    def test_no_loss_seen_gives_a_bound_not_a_zero(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.history(Path(temporary), [(0, world(), []), (2, world(), [])])
            found = History(Path(temporary)).replay('HEAD')['currency']
        self.assertEqual(found['attrition']['loss_per_claim_day']['estimate'], 0.0)
        self.assertEqual(found['attrition']['loss_per_claim_day']['interval95'][0], 0.0)
        self.assertGreater(found['attrition']['loss_per_claim_day']['interval95'][1], 0.0)
        self.assertEqual(found['attrition']['loss_per_review'], {'estimate': None, 'interval95': None})

    def test_admission_and_maintenance_reassessments_count_once_per_record(self):
        first, second = world(), world()
        for cid in ('C-a', 'C-b'):
            second['claims'][cid]['uncertainty'] = 'high'
        reassessment = {'id': 'grade', 'kind': 'reassessment', 'subject_ids': ['C-a', 'C-b'],
                        'basis_ids': ['E-a', 'E-b'], 'reason': 'New evidence raises uncertainty',
                        'uncertainty': 'high', 'predecessors': {'C-a': None, 'C-b': None},
                        'read_sha256': {}, 'previous_uncertainty': {'C-a': 'medium', 'C-b': 'medium'}}
        admission = {'id': 'BC-' + 'a' * 32, 'schema_version': '1.1', 'model_operations': [reassessment]}
        maintenance = {'id': 'M-1', 'status': 'completed', 'reviewed_claim_ids': ['C-c'],
                       'model_operations': [{**reassessment, 'subject_ids': ['C-c']}]}
        pending = {'id': 'M-2', 'status': 'pending', 'model_operations': [reassessment]}
        with tempfile.TemporaryDirectory() as temporary:
            self.history(Path(temporary), [(0, first, []), (1, second, [admission, maintenance, pending]),
                                           (2, second, [])])
            found = History(Path(temporary)).replay('HEAD')['currency']
        attrition = found['attrition']
        self.assertEqual((attrition['reviews'], attrition['losses_found_at_review'],
                          attrition['losses_outside_review']), (3, 2, 0))
        self.assertEqual(attrition['loss_per_review'], {'estimate': 0.666667, 'interval95': wilson(2, 3)})
        self.assertEqual(found['clocks_days']['since_last_review']['max'], 1.0)


def repo_git(root: Path, *args: str, **env: str) -> str:
    return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True, text=True,
                          env={'PATH': __import__('os').environ['PATH'], **env}).stdout.strip()


class Hardening(unittest.TestCase):
    """One test per defect an independent review reproduced."""

    def commit(self, root: Path, message: str = 'more') -> None:
        repo_git(root, 'add', '-A')
        repo_git(root, '-c', 'user.name=t', '-c', 'user.email=t@example.invalid', 'commit', '-q', '--allow-empty', '-m', message)

    def repo(self, temporary: str) -> Path:
        root = Path(temporary)
        Currency().history(root, [(0, world(), [])])
        return root

    def test_only_regular_record_files_at_their_fixed_path_are_read(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.repo(temporary)
            head = repo_git(root, 'rev-parse', 'HEAD')
            blob = repo_git(root, 'rev-parse', 'HEAD:claims/C-a.yaml')
            # a submodule entry named like a record, and a record-like file outside its fixed path
            repo_git(root, 'update-index', '--add', '--cacheinfo', f'160000,{head},claims/C-zz.yaml')
            (root / 'claims' / 'nested').mkdir()
            (root / 'claims' / 'nested' / 'C-n.yaml').write_text(yaml.safe_dump(claim('C-n', ['E-a'])), encoding='utf-8')
            repo_git(root, 'add', 'claims/nested')
            repo_git(root, '-c', 'user.name=t', '-c', 'user.email=t@example.invalid', 'commit', '-q', '-m', 'odd entries')
            self.assertEqual(sorted(History(root).records('HEAD')['claims']), ['C-a', 'C-b', 'C-c'])
            repo_git(root, 'update-index', '--add', '--cacheinfo', f'120000,{blob},claims/C-link.yaml')
            repo_git(root, '-c', 'user.name=t', '-c', 'user.email=t@example.invalid', 'commit', '-q', '-m', 'symlink')
            with self.assertRaisesRegex(Invalid, 'regular files'):
                History(root).records('HEAD')

    def test_record_id_must_match_its_file_name_and_revisions_cannot_be_options(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.repo(temporary)
            (root / 'claims' / 'C-wrong.yaml').write_text(yaml.safe_dump(claim('C-a', ['E-a'])), encoding='utf-8')
            self.commit(root)
            with self.assertRaisesRegex(Invalid, 'does not match its file name'):
                History(root).records('HEAD')
            for revision in ('--output=/tmp/x', '-n1', ''):
                with self.assertRaises(Invalid):
                    History(root).records(revision)

    def test_commit_subjects_with_line_separators_do_not_break_history(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.repo(temporary)
            self.commit(root, 'Merge pull request #7 from fork/fix\u2028x\x0cy\x85z')
            self.assertEqual(len(History(root).revisions('HEAD')), 2)
            self.assertTrue(History(root).replay('HEAD')['currency']['measured'])

    def test_records_parse_as_the_compiler_parses_them(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.repo(temporary)
            (root / 'questions' / 'Q-d.yaml').write_text(
                'id: Q-d\nquestion: When?\nclaim_ids: []\nstate: open\n'
                'space:\n  kind: categorical\n  values: [2024-01-01, 2024-02-01, unknown]\n', encoding='utf-8')
            record = yaml.safe_load((root / 'claims' / 'C-a.yaml').read_text())
            record['answers'] = [{'question_id': 'Q-d', 'values': ['2024-01-01'], 'evidence_ids': ['E-a']}]
            (root / 'claims' / 'C-a.yaml').write_text(yaml.safe_dump(record), encoding='utf-8')
            self.commit(root)
            report = ledger(History(root).records('HEAD'))['commitment']
            self.assertEqual(report['by_question']['Q-d']['held']['ratio'], '3/1')  # dates stay text, as in the compiler

    def test_a_loss_outside_any_review_is_not_a_share_of_reviews(self):
        self.assertIsNone(wilson(11, 10))
        self.assertIsNone(wilson(1, 0))
        weakened = world()
        weakened['claims']['C-a']['uncertainty'] = 'high'
        with tempfile.TemporaryDirectory() as temporary:
            Currency().history(Path(temporary), [(0, world(), []), (1, weakened, []), (2, weakened, [])])
            found = History(Path(temporary)).replay('HEAD')['currency']['attrition']
        self.assertEqual((found['losses'], found['losses_found_at_review'], found['losses_outside_review']), (1, 0, 1))
        self.assertEqual(found['loss_per_review'], {'estimate': None, 'interval95': None})

    def test_identity_and_question_changes_are_not_losses_of_standing(self):
        digest = world()
        digest['sources']['S-b']['ancestry'] = {'status': 'unknown', 'parent_source_ids': [], 'notes': ['n'],
                                               'content_sha256': 'b' * 64}
        report = delta(world(), digest)
        self.assertEqual({row['verdict'] for row in report['claims'].values()}, {'origin_reidentified'})
        self.assertEqual(([row['loss'] for row in report['claims'].values()], report['outcome']),
                         ([[], []], 'origin_identity_changed'))
        split = world()  # two passages of one document; a digest on one of them splits the origin
        split['sources']['S-a1']['ancestry'] = {'status': 'unknown', 'parent_source_ids': [], 'notes': ['n'],
                                                'content_sha256': 'a' * 64}
        report = delta(world(), split)
        self.assertEqual((report['gain']['origins'], report['outcome'], report['claims']['C-a']['loss']),
                         (1, 'origin_identity_changed', []))
        retired, regridded = asked(), asked()
        retired['questions']['Q-f']['state'] = 'retired'
        regridded['questions']['Q-n']['space'] = {**RATE, 'step': '0.5'}
        for after in (retired, regridded):
            report = delta(asked(), after)
            self.assertEqual([row['loss'] for row in report['claims'].values() if row['loss']], [])
            self.assertEqual(report['commitment']['loss']['ratio'], '1/1')  # the question changed, not the claims
        self.assertLess(delta(asked(), retired)['commitment']['gain']['bits'], 0)  # fewer bits held, yet no loss booked
        dropped = asked()  # the claim's own answer removed is a loss
        del dropped['claims']['C-b']['answers']
        self.assertEqual(delta(asked(), dropped)['claims']['C-b']['loss'], ['answer_withdrawn'])

    def test_a_changed_space_is_measured_by_state_and_never_mixes_cells(self):
        wider = asked()
        wider['questions']['Q-f']['space'] = {'kind': 'categorical', 'values': ['yes', 'no', 'maybe', 'unknown']}
        row = commitment_delta(asked(), wider)['questions']['Q-f']
        self.assertEqual((row['gain']['ratio'], row['space_changed'], row['answers']['C-a']['verdict']), ('2/1', True, 'space_changed'))
        numeric = asked()  # categorical becomes numeric and the answer is rewritten: no crash, no cell comparison
        numeric['questions']['Q-f']['space'] = RATE
        numeric['claims']['C-a']['answers'] = [ranges('Q-f', ('10', '20'))]
        row = commitment_delta(asked(), numeric)['questions']['Q-f']
        self.assertEqual((row['answers']['C-a']['verdict'], row['held_after']['ratio']), ('space_changed', '101/11'))

    def test_exact_ratios_are_printed_only_while_short(self):
        self.assertEqual(bits(Fraction(10 ** 400, 1))['ratio'], None)
        self.assertAlmostEqual(bits(Fraction(10 ** 400, 1))['bits'], 1328.771238, places=5)
        many = asked()
        for number in range(2000):
            many['questions'][f'Q-{number}'] = {'id': f'Q-{number}', 'question': '?', 'claim_ids': [], 'state': 'open', 'space': RATE}
            many['claims']['C-a']['answers'].append(ranges(f'Q-{number}', ('40', '40.2')))
        report = ledger(many)['commitment']
        self.assertEqual((report['held']['ratio'], report['questions']), (None, 2002))
        with self.assertRaises(ValueError):
            admitted_set(RATE, ranges('Q-n', ('1' * 41, '2' * 41)))

    def test_contested_answers_are_conflicts_and_a_restated_side_is_a_repeat(self):
        four = {'kind': 'categorical', 'values': ['a', 'b', 'c', 'd']}
        base = asked()
        base['questions']['Q-4'] = {'id': 'Q-4', 'question': '?', 'claim_ids': [], 'state': 'open', 'space': four}
        base['claims']['C-a']['answers'].append(values('Q-4', 'a', 'b', 'c', 'd'))
        split = answering(answering(base, 'C-x', values('Q-4', 'a', 'b')), 'C-y', values('Q-4', 'c', 'd'))
        row = commitment_delta(base, split)['questions']['Q-4']
        self.assertEqual(({answer['verdict'] for answer in row['answers'].values()}, row['conflict_after']), ({'conflicts'}, True))
        restated = answering(split, 'C-z', values('Q-4', 'a', 'b'))
        row = commitment_delta(split, restated)['questions']['Q-4']
        self.assertEqual((row['answers']['C-z']['verdict'], row['gain']['ratio']), ('repeats', '1/1'))
        self.assertEqual(row['answers']['C-z']['surprise'], bits(1))

    def test_period_end_rejects_invalid_dates_and_handles_leap_year(self):
        self.assertEqual([period_end(text) for text in ('2024-13', '2024-00', '2024-05-00', '2024-02-30', 'soon')], [None] * 5)
        self.assertEqual(period_end('2024-02') - period_end('2024-01'), 29)

    def test_poisson_quantile_reaches_both_tails_at_the_first_count(self):
        # Reference counts from a high-precision Poisson CDF.
        for mean, lower, upper in ((0, 0, 0), (0.5, 0, 2), (500, 457, 544),
                                   (500.5, 457, 545), (512, 468, 557), (1000, 938, 1062),
                                   (100000, 99381, 100620)):
            with self.subTest(mean=mean):
                self.assertEqual(poisson_quantile(mean, 0.025), lower)
                self.assertEqual(poisson_quantile(mean, 0.975), upper)
        self.assertEqual(poisson_quantile(1000, 0.9999999999999999), 1270)

    def test_commit_times_that_run_backwards_never_give_a_negative_span(self):
        weakened = world()
        weakened['claims']['C-a']['uncertainty'] = 'high'
        with tempfile.TemporaryDirectory() as temporary:
            Currency().history(Path(temporary), [(10, world(), []), (12, world(), []), (9, weakened, [])])
            found = History(Path(temporary)).replay('HEAD')['currency']
        self.assertEqual((found['history_days'], found['clocks_days']['since_admitted']['min']), (2.0, 2.0))
        self.assertEqual(found['attrition']['loss_per_claim_day']['exposure'], 6.0)
        self.assertEqual(found['projection']['horizon_days'], 2.0)
        self.assertTrue(all(0 <= value <= 1 for value in found['projection']['share_keeping_standing']['interval95']))

    def test_declaring_answers_is_not_read_as_no_change(self):
        before = asked()
        del before['claims']['C-b']['answers']
        self.assertEqual(delta(before, asked())['outcome'], 'changes_commitment')

    def test_ci_reports_the_ledger_even_when_history_cannot_be_replayed_in_time(self):
        script = Path(__file__).resolve().parents[1] / 'scripts/information.py'
        with tempfile.TemporaryDirectory() as temporary:
            root = self.repo(temporary)
            result = subprocess.run([sys.executable, str(script), '--repo', str(root), 'ci', '--budget', '-1'],
                                    capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn('| Now | 3 | 3 | 3 | 4 |', result.stdout)
        self.assertIn('Currency: not reported for this change (history is longer than the time allowed for replay).', result.stdout)

    def test_ci_still_reports_when_its_report_files_cannot_be_written(self):
        script = Path(__file__).resolve().parents[1] / 'scripts/information.py'
        with tempfile.TemporaryDirectory() as temporary:
            root = self.repo(temporary)
            blocked = Path(temporary) / 'claims' / 'C-a.yaml' / 'out'  # a path under a file can never be a directory
            result = subprocess.run([sys.executable, str(script), '--repo', str(root), 'ci', '--out', str(blocked)],
                                    capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn('| Now | 3 | 3 | 3 | 4 |', result.stdout)
        self.assertIn('does not measure truth', result.stdout)

    def test_ci_exits_zero_when_its_reader_goes_away(self):
        script = Path(__file__).resolve().parents[1] / 'scripts/information.py'
        with tempfile.TemporaryDirectory() as temporary:
            root = self.repo(temporary)
            process = subprocess.Popen([sys.executable, str(script), '--repo', str(root), 'ci'],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            process.stdout.close()  # nobody reads the summary
            self.assertEqual(process.wait(), 0)
            process.stderr.close()


class Replay(unittest.TestCase):
    def test_step_gains_sum_to_the_final_state_and_bytes_are_reproducible(self):
        states = [world()]
        second = copy.deepcopy(states[0])
        second['sources']['S-d'] = source('S-d', 'https://d.example/doc')
        second['evidence']['E-d'] = evidence('E-d', ['S-d', 'S-a1'], ['C-d'])
        second['claims']['C-d'] = claim('C-d', ['E-d'])
        third = copy.deepcopy(second)
        third['claims']['C-a']['state'] = 'retired'
        states += [second, third]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            git = lambda *args: subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True)
            git('init', '-q')
            for number, state in enumerate(states):
                for group, items in state.items():
                    (root / group).mkdir(exist_ok=True)
                    for record_id, record in items.items():
                        (root / group / f'{record_id}.yaml').write_text(yaml.safe_dump(record), encoding='utf-8')
                git('add', '-A')
                git('-c', 'user.name=t', '-c', 'user.email=t@example.invalid', 'commit', '-q', '-m', f'step {number}')
            first, again = History(root).replay('HEAD'), History(root).replay('HEAD')
        self.assertEqual(first, again)
        self.assertEqual([row['step']['outcome'] for row in first['steps']], ['adds_origins', 'adds_origins', 'loss'])
        self.assertEqual([row['step']['gain']['origins'] for row in first['steps']], [3, 1, 0])
        self.assertEqual(sum(row['step']['gain']['claims'] for row in first['steps']), first['steps'][-1]['totals']['claims'])

    def test_ci_summary_is_advisory_and_never_fails_the_caller(self):
        script = Path(__file__).resolve().parents[1] / 'scripts/information.py'
        with tempfile.TemporaryDirectory() as temporary:
            root, out = Path(temporary) / 'repo', Path(temporary) / 'out'
            root.mkdir()
            Currency().history(root, [(0, world(), []), (1, world(), [])])
            head = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD~1'], check=True, capture_output=True, text=True).stdout.strip()
            run = lambda *args: subprocess.run([sys.executable, str(script), '--repo', str(root), 'ci', *args],
                                               capture_output=True, text=True)
            good = run('--before', head, '--out', str(out))
            self.assertEqual(good.returncode, 0)
            self.assertIn('| Now | 3 | 3 | 3 | 4 |', good.stdout)
            self.assertIn('| This change | +0 | +0 | +0 | +0 |', good.stdout)
            self.assertIn('does not measure truth', good.stdout)
            self.assertEqual(sorted(path.name for path in out.iterdir()), ['change.json', 'history.json', 'ledger.json'])
            for before in ('', '0' * 40, 'f' * 40, 'not-a-revision; rm -rf /'):
                result = run('--before', before)
                self.assertEqual((result.returncode, 'This change' in result.stdout), (0, False))
            broken = subprocess.run([sys.executable, str(script), '--repo', str(Path(temporary) / 'absent'), 'ci'],
                                    capture_output=True, text=True)
            self.assertEqual(broken.returncode, 0)
            self.assertIn('Not available for this change', broken.stdout)

    def test_validation_workflow_runs_the_ledger_from_trusted_code_without_blocking(self):
        workflow = (Path(__file__).resolve().parents[1] / '.github/workflows/validate.yml').read_text()
        step = workflow.split('Report the information ledger (advisory, never blocks)')[1].split('\n  tests:')[0]
        # after the push-range steps, so it can never delay or pre-empt that artifact
        self.assertLess(workflow.index('name: resolvent-push-range'), workflow.index('Report the information ledger'))
        self.assertIn('continue-on-error: true', step)
        self.assertIn('python policy/scripts/information.py --repo candidate ci', step)  # base-branch code, proposed data
        self.assertNotIn('candidate/scripts', step)
        self.assertNotIn('secrets.', step)
        self.assertIn('|| true', step)

    def test_missing_revision_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            subprocess.run(['git', '-C', temporary, 'init', '-q'], check=True)
            with self.assertRaises(Invalid):
                History(Path(temporary)).records('HEAD')


if __name__ == '__main__':
    unittest.main()
