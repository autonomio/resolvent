"""Synthetic impact analysis: advisory paths, never belief revision."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.build_knowledge import ROOT, json_bytes, projection
from scripts.change_impact import analyze, compare_revisions, readable_summary
from scripts.model import Invalid
from scripts.world_control import canonical_id
from test_model import admitted, contribution, state_for, write_state

RUN = 'RUN-' + '5' * 32


def rid(group: str, local: str) -> str:
    return canonical_id(RUN, group, local)


def fixture(dependencies=(), premises=None, couplings=()) -> dict:
    proposal = contribution(token='5' * 32)
    source, evidence, claim = [copy.deepcopy(proposal[group][0])
                               for group in ('sources', 'evidence', 'claims')]
    proposal.update(sources=[], evidence=[], claims=[])
    for number in range(1, 5):
        proposal['sources'].append({**copy.deepcopy(source), 'id': f's{number}'})
        proposal['evidence'].append({**copy.deepcopy(evidence), 'id': f'e{number}',
                                    'source_ids': [f's{number}'],
                                    'premise_claim_ids': (premises or {}).get(number, [])})
        proposal['claims'].append({**copy.deepcopy(claim), 'id': f'c{number}',
                                  'statement': f'Synthetic claim {number} is untested.',
                                  'evidence_ids': [f'e{number}']})
    proposal['sources'].append({**copy.deepcopy(source), 'id': 's_link'})
    proposal['evidence'].append({**copy.deepcopy(evidence), 'id': 'e_link',
                                'source_ids': ['s_link']})
    for kind, pairs in (('dependency', dependencies), ('coupling', couplings)):
        for child, parent in pairs:
            proposal['connectors'].append({
                'id': f'r{len(proposal["connectors"]) + 1}',
                'from': f'c{child}', 'to': f'c{parent}', 'type': kind,
                'spec': 'structural:moderate:balanced', 'reason': 'Synthetic relationship.',
                'uncertainty': 'high', 'evidence_ids': ['e_link'],
            })
    return admitted(proposal)


def records(**kwargs) -> dict:
    return projection(fixture(**kwargs))['records']


def impacts(report: dict, seed: str, group='dependency_impacts', snapshot='after') -> dict:
    return {item['claim_id']: item for item in report[group]
            if item['change_id'] == seed and item['snapshot'] == snapshot}


class ImpactTests(unittest.TestCase):
    def test_unchanged_projections_have_no_changes_or_impacts(self):
        original = records(dependencies=[(2, 1), (3, 2)])
        report = analyze(original, copy.deepcopy(original))
        self.assertEqual(report['changes'], [])
        self.assertEqual(report['dependency_impacts'], [])
        self.assertEqual(report['contextual_impacts'], [])

    def test_dependency_chain_distinguishes_direct_and_transitive(self):
        before = records(dependencies=[(2, 1), (3, 2), (4, 3)])
        after = copy.deepcopy(before)
        seed = rid('claims', 'c1')
        after['claims'][seed]['uncertainty'] = 'medium'
        report = analyze(before, after)
        affected = impacts(report, seed)
        self.assertEqual(set(affected), {rid('claims', f'c{number}') for number in (2, 3, 4)})
        self.assertEqual(affected[rid('claims', 'c2')]['proximity'], 'direct')
        self.assertEqual(affected[rid('claims', 'c3')]['proximity'], 'transitive')
        self.assertEqual(affected[rid('claims', 'c4')]['claim_hops'], 3)
        self.assertTrue(all(item['assessment'] == 'potentially_affected'
                            for item in report['dependency_impacts']))

    def test_diamond_has_one_stable_explanation_per_cause_and_claim(self):
        before = records(dependencies=[(2, 1), (3, 1), (4, 2), (4, 3)])
        after = copy.deepcopy(before)
        seed = rid('claims', 'c1')
        after['claims'][seed]['uncertainty'] = 'medium'
        report = analyze(before, after)
        target = impacts(report, seed)[rid('claims', 'c4')]
        self.assertEqual(target['claim_hops'], 2)
        self.assertEqual(len(target['path']), 2)
        self.assertIn(target['path'][0]['to'], [rid('claims', 'c2'), rid('claims', 'c3')])
        reordered = {group: dict(reversed(list(values.items()))) for group, values in after.items()}
        self.assertEqual(json_bytes(report), json_bytes(analyze(before, reordered)))

    def test_overlapping_causes_are_retained(self):
        before = records(dependencies=[(4, 2), (4, 3)])
        after = copy.deepcopy(before)
        causes = [rid('claims', local) for local in ('c2', 'c3')]
        for cause in causes:
            after['claims'][cause]['uncertainty'] = 'medium'
        report = analyze(before, after)
        paths = [item for item in report['dependency_impacts']
                 if item['claim_id'] == rid('claims', 'c4') and item['snapshot'] == 'after']
        self.assertEqual({item['change_id'] for item in paths}, set(causes))

    def test_evidential_premises_preserve_joint_sets(self):
        before = records(premises={2: ['c1'], 3: ['c2'], 4: ['c2', 'c3']})
        after = copy.deepcopy(before)
        seed = rid('claims', 'c1')
        after['claims'][seed]['uncertainty'] = 'medium'
        affected = impacts(analyze(before, after), seed)
        self.assertEqual(affected[rid('claims', 'c2')]['proximity'], 'direct')
        self.assertEqual(affected[rid('claims', 'c3')]['proximity'], 'transitive')
        premise_step = next(step for step in affected[rid('claims', 'c4')]['path']
                            if step['via'] == rid('evidence', 'e4'))
        self.assertEqual(premise_step['premise_claim_ids'],
                         [rid('claims', 'c2'), rid('claims', 'c3')])

    def test_revised_source_traces_evidence_and_transitive_claim_consumers(self):
        before = records(dependencies=[(2, 1), (3, 2)])
        after = copy.deepcopy(before)
        seed = rid('sources', 's1')
        after['sources'][seed]['excerpt'] = 'A revised synthetic source excerpt.'
        report = analyze(before, after)
        affected = impacts(report, seed)
        self.assertEqual(affected[rid('claims', 'c1')]['proximity'], 'direct')
        self.assertEqual(affected[rid('claims', 'c2')]['proximity'], 'transitive')
        path = affected[rid('claims', 'c3')]['path']
        self.assertEqual(path[0]['from'], seed)
        self.assertEqual(path[0]['to'], rid('evidence', 'e1'))
        self.assertEqual(path[-1]['to'], rid('claims', 'c3'))
        self.assertTrue(report['changes'][0]['support_changed'])
        self.assertEqual(report['changes'][0]['before'], before['sources'][seed])

    def test_evidence_limitations_trigger_support_reassessment(self):
        before = records(dependencies=[(3, 2)])
        after = copy.deepcopy(before)
        seed = rid('evidence', 'e2')
        after['evidence'][seed]['limitations'].append('A synthetic new limitation.')
        report = analyze(before, after)
        affected = impacts(report, seed)
        self.assertEqual(affected[rid('claims', 'c2')]['proximity'], 'direct')
        self.assertEqual(affected[rid('claims', 'c3')]['proximity'], 'transitive')
        self.assertIn('limitations', report['changes'][0]['changed_fields'])

    def test_retired_premise_still_flags_dependents_and_preserves_lifecycle(self):
        before = records(dependencies=[(2, 1), (3, 2)])
        after = copy.deepcopy(before)
        seed = rid('claims', 'c1')
        after['claims'][seed]['state'] = 'retired'
        after['claims'][rid('claims', 'c2')]['state'] = 'retired'
        report = analyze(before, after)
        changes_by_id = {item['id']: item for item in report['changes']}
        self.assertEqual(changes_by_id[seed]['operation'], 'retired')
        affected = impacts(report, seed)
        self.assertEqual(affected[rid('claims', 'c2')]['after_state'], 'retired')
        self.assertEqual(affected[rid('claims', 'c2')]['before_state'], 'active')
        self.assertEqual(affected[rid('claims', 'c3')]['after_state'], 'active')

    def test_old_and_new_edges_cannot_form_an_invented_path(self):
        before = records(dependencies=[(2, 1)])
        after = copy.deepcopy(before)
        seed = rid('claims', 'c1')
        after['claims'][seed]['uncertainty'] = 'medium'
        after['graph'][rid('graph', 'r1')]['state'] = 'retired'
        new_connector = copy.deepcopy(after['graph'][rid('graph', 'r1')])
        new_connector.update(id=rid('graph', 'r2'), state='active',
                             **{'from': rid('claims', 'c3'), 'to': rid('claims', 'c2')})
        after['graph'][new_connector['id']] = new_connector
        report = analyze(before, after)
        self.assertIn(rid('claims', 'c2'), impacts(report, seed, snapshot='before'))
        self.assertNotIn(rid('claims', 'c3'), impacts(report, seed, snapshot='before'))
        self.assertEqual(impacts(report, seed), {})

    def test_coupling_is_contextual_and_does_not_propagate_dependency(self):
        before = records(dependencies=[(3, 2)], couplings=[(1, 2)])
        after = copy.deepcopy(before)
        seed = rid('claims', 'c1')
        after['claims'][seed]['uncertainty'] = 'medium'
        report = analyze(before, after)
        self.assertEqual(impacts(report, seed), {})
        contextual = impacts(report, seed, group='contextual_impacts')
        self.assertEqual(set(contextual), {rid('claims', 'c2')})
        self.assertEqual(contextual[rid('claims', 'c2')]['path'][0]['relation'], 'coupling')
        self.assertNotIn(rid('claims', 'c3'), contextual)

    def test_changed_connectors_reassess_their_declared_consumers(self):
        for kind in ('dependency', 'coupling'):
            before = records(**{'dependencies' if kind == 'dependency' else 'couplings': [(2, 1)]})
            after = copy.deepcopy(before)
            seed = rid('graph', 'r1')
            after['graph'][seed]['reason'] = 'Revised synthetic explanation.'
            report = analyze(before, after)
            if kind == 'dependency':
                self.assertEqual(set(impacts(report, seed)), {rid('claims', 'c2')})
            else:
                self.assertEqual(impacts(report, seed), {})
                self.assertEqual(set(impacts(report, seed, group='contextual_impacts')),
                                 {rid('claims', 'c1'), rid('claims', 'c2')})

    def test_changed_connector_support_reaches_dependents(self):
        before = records(dependencies=[(2, 1)], couplings=[(3, 4)])
        after = copy.deepcopy(before)
        seed = rid('sources', 's_link')
        after['sources'][seed]['access'] = 'not_retrieved'
        report = analyze(before, after)
        self.assertEqual(set(impacts(report, seed)), {rid('claims', 'c2')})
        self.assertEqual(set(impacts(report, seed, group='contextual_impacts')),
                         {rid('claims', 'c3'), rid('claims', 'c4')})

    def test_direct_consumer_explanation_is_preferred_over_a_shorter_transitive_path(self):
        before = records(dependencies=[(2, 1), (3, 2)])
        seed = rid('claims', 'c1')
        before['evidence'][rid('evidence', 'e_link')]['premise_claim_ids'] = [seed]
        after = copy.deepcopy(before)
        after['claims'][seed]['uncertainty'] = 'medium'
        affected = impacts(analyze(before, after), seed)[rid('claims', 'c3')]
        self.assertEqual(affected['proximity'], 'direct')
        self.assertEqual([step['relation'] for step in affected['path']],
                         ['evidence_premise', 'connector_evidence', 'dependency_connector'])

    def test_claim_metadata_and_evidence_link_changes_are_preserved(self):
        before = records()
        after = copy.deepcopy(before)
        seed = rid('claims', 'c1')
        after['claims'][seed].update(**{'class': 'assumption', 'uncertainty': 'medium',
                                        'statement': 'A corrected synthetic statement.'})
        after['claims'][seed]['evidence_ids'].append(rid('evidence', 'e_link'))
        report = analyze(before, after)
        change = report['changes'][0]
        self.assertEqual(change['changed_fields'], ['class', 'evidence_ids', 'statement', 'uncertainty'])
        self.assertTrue(change['support_changed'])
        self.assertEqual(change['before'], before['claims'][seed])
        self.assertEqual(change['after'], after['claims'][seed])

    def test_additions_removals_and_null_fields_are_explicit(self):
        before = records()
        after = copy.deepcopy(before)
        old_id = rid('sources', 's_link')
        new_id = rid('sources', 's_new')
        added = after['sources'].pop(old_id)
        after['sources'][new_id] = {**added, 'id': new_id}
        report = analyze(before, after)
        by_id = {item['id']: item for item in report['changes']}
        self.assertEqual(by_id[old_id]['operation'], 'removed')
        self.assertEqual(by_id[new_id]['operation'], 'added')
        self.assertIn('uri', by_id[new_id]['changed_fields'])
        self.assertIsNone(by_id[new_id]['after']['uri'])

    def test_no_text_similarity_links_or_input_mutation(self):
        before = records()
        after = copy.deepcopy(before)
        seed = rid('claims', 'c1')
        after['claims'][seed]['statement'] = after['claims'][rid('claims', 'c2')]['statement']
        unchanged = copy.deepcopy((before, after))
        report = analyze(before, after)
        self.assertEqual(report['dependency_impacts'], [])
        self.assertEqual(report['contextual_impacts'], [])
        self.assertEqual((before, after), unchanged)


class RevisionImpactTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name)
        subprocess.run(['git', 'init', '-q', '--initial-branch=main', str(self.repo)], check=True)
        self.state = fixture(dependencies=[(2, 1), (3, 2)])
        self.before = self.commit(self.state)

    def commit(self, state):
        write_state(self.repo, state)
        subprocess.run(['git', '-C', str(self.repo), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(self.repo), '-c', 'user.name=Synthetic test',
                        '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'Synthetic fixture'], check=True)
        return subprocess.check_output(['git', '-C', str(self.repo), 'rev-parse', 'HEAD'], text=True).strip()

    def test_api_pins_validated_revisions_and_does_not_write_worktree(self):
        source_path = f"sources/{rid('sources', 's1')}.yaml"
        self.state[source_path]['excerpt'] = 'Revised synthetic observation.'
        mid = 'M-' + '6' * 32
        self.state[f'maintenance/{mid}.yaml'] = {
            'schema_version': '1.0', 'id': mid, 'status': 'completed', 'base_commit': self.before,
            'created_at': '2026-01-02T12:00:00Z', 'claim_ids': [rid('claims', 'c1')],
            'reviewed_claim_ids': [rid('claims', 'c1')], 'touched_files': [source_path],
            'findings': ['Synthetic source correction.'], 'deferred': [], 'no_change_reason': None,
        }
        after = self.commit(self.state)
        report = compare_revisions(self.repo, self.before, after)
        self.assertEqual(report['before']['source_revision'], self.before)
        self.assertEqual(report['after']['source_revision'], after)
        self.assertEqual(len(report['after']['manifest_sha256']), 64)
        self.assertEqual(json_bytes(report), json_bytes(compare_revisions(self.repo, self.before, after)))
        self.assertIn('Potential reassessment only', readable_summary(report))
        self.assertIn(rid('sources', 's1'), readable_summary(report))
        status = subprocess.check_output(['git', '-C', str(self.repo), 'status', '--porcelain'], text=True)
        self.assertEqual(status, '')

    def test_pending_revision_is_rejected(self):
        proposal = contribution(token='7' * 32)
        self.state.update(state_for(proposal))
        pending = self.commit(self.state)
        with self.assertRaisesRegex(Invalid, 'Awaiting admission'):
            compare_revisions(self.repo, self.before, pending)

    def test_cli_json_and_text_use_the_same_pinned_report(self):
        for output_format in ('json', 'text'):
            result = subprocess.run(
                [sys.executable, str(ROOT / 'scripts/change_impact.py'), '--repo', str(self.repo),
                 '--before', self.before, '--after', self.before, '--format', output_format],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            if output_format == 'json':
                self.assertEqual(json.loads(result.stdout)['changes'], [])
            else:
                self.assertIn('0 changed records.', result.stdout)


if __name__ == '__main__':
    unittest.main()
