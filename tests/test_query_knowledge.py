"""Synthetic retrieval fixtures: bounded results retain epistemic provenance."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.build_knowledge import ROOT, compile_revision, json_bytes, sha256
from scripts.model import Invalid
from scripts.query_knowledge import Knowledge
from scripts.world_control import canonical_id, plan_admission
from test_model import admitted, contribution, decisions, state_for, write_state

RUN = 'RUN-' + '8' * 32


def ident(group, local):
    return canonical_id(RUN, group, local)


def query_state():
    proposal = contribution(token='8' * 32)
    parent = contribution(token='7' * 32)
    parent.update(claims=[], evidence=[], sources=[])
    parent['handoff']['no_claims_reason'] = 'Synthetic parent run without admitted claims.'
    state = admitted(parent)
    proposal['parent_run_id'] = parent['id']
    source, evidence, claim = [copy.deepcopy(proposal[group][0]) for group in ('sources', 'evidence', 'claims')]
    proposal.update(sources=[], evidence=[], claims=[])
    for number, word in enumerate(('amber', 'azure', 'violet', 'dragonfruit'), 1):
        proposal['sources'].append({**copy.deepcopy(source), 'id': f's{number}',
                                    'title': f'Synthetic {word} source', 'locator': f'Fixture section {number}',
                                    'excerpt': f'The synthetic {word} instrument records a spectral signal.',
                                    'access': 'not_retrieved' if number == 1 else 'inspected'})
        proposal['evidence'].append({**copy.deepcopy(evidence), 'id': f'e{number}',
                                     'summary': f'Synthetic {word} statement.', 'source_ids': [f's{number}'],
                                     'premise_claim_ids': ['c1'] if number == 2 else []})
        proposal['claims'].append({**copy.deepcopy(claim), 'id': f'c{number}',
                                   'statement': f'The synthetic {word} claim is untested.',
                                   'evidence_ids': [f'e{number}']})
    proposal['connectors'] = [
        {'id': 'r1', 'from': 'c2', 'to': 'c1', 'type': 'dependency',
         'spec': 'structural:moderate:inward', 'reason': 'Synthetic dependency.',
         'uncertainty': 'high', 'evidence_ids': ['e2']},
        {'id': 'r2', 'from': 'c2', 'to': 'c3', 'type': 'coupling',
         'spec': 'narrative:weak:balanced', 'reason': 'Synthetic coupling.',
         'uncertainty': 'high', 'evidence_ids': ['e3']},
    ]
    proposal['questions'] = [{'id': 'q1', 'question': 'What remains unknown in this fixture?', 'claim_ids': ['c1']}]
    decision = decisions(proposal)
    decision['claims']['c4']['action'] = 'reject'
    decision['connection_review'].pop('c4')
    decision['follow_up_gaps'] = ['Synthetic unresolved discovery gap.']
    state.update(state_for(proposal))
    state.update(plan_admission(state, proposal['id'], decision, ROOT))
    c3 = ident('claims', 'c3')
    state[f'claims/{c3}.yaml']['state'] = 'retired'
    mid = 'M-' + '9' * 32
    state[f'maintenance/{mid}.yaml'] = {
        'schema_version': '1.0', 'id': mid, 'status': 'completed', 'base_commit': 'a' * 40,
        'created_at': '2026-01-02T12:00:00Z', 'claim_ids': [c3], 'reviewed_claim_ids': [c3],
        'touched_files': [f'claims/{c3}.yaml'], 'findings': ['Synthetic retirement.'],
        'deferred': ['Synthetic deferred source review.'], 'no_change_reason': None,
    }
    return state


class QueryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture_temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.fixture_temp.cleanup)
        cls.repo = Path(cls.fixture_temp.name) / 'repo'
        cls.repo.mkdir()
        subprocess.run(['git', 'init', '-q', '--initial-branch=main', str(cls.repo)], check=True)
        cls.state = query_state()
        cls.commit_state(cls.state)
        cls.revision = subprocess.check_output(['git', '-C', str(cls.repo), 'rev-parse', 'HEAD'], text=True).strip()
        cls.package_bytes = compile_revision(cls.repo, cls.revision)
        later_state = copy.deepcopy(cls.state)
        source_path = f"sources/{ident('sources', 's1')}.yaml"
        later_state[source_path]['excerpt'] = 'A synthetic copper resonance appears in this later revision.'
        mid = 'M-' + 'b' * 32
        later_state[f'maintenance/{mid}.yaml'] = {
            'schema_version': '1.0', 'id': mid, 'status': 'completed', 'base_commit': cls.revision,
            'created_at': '2026-01-03T12:00:00Z', 'claim_ids': [ident('claims', 'c1')],
            'reviewed_claim_ids': [ident('claims', 'c1')], 'touched_files': [source_path],
            'findings': ['Synthetic source correction.'], 'deferred': [], 'no_change_reason': None,
        }
        cls.commit_state(later_state)
        cls.later_revision = subprocess.check_output(['git', '-C', str(cls.repo), 'rev-parse', 'HEAD'], text=True).strip()
        cls.later_package_bytes = compile_revision(cls.repo, cls.later_revision)

    @classmethod
    def commit_state(cls, state):
        write_state(cls.repo, state)
        subprocess.run(['git', '-C', str(cls.repo), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(cls.repo), '-c', 'user.name=Synthetic test',
                        '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'Synthetic fixture'], check=True)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.package = Path(self.temporary.name)
        for name, contents in self.package_bytes.items():
            (self.package / name).write_bytes(contents)
        self.query = Knowledge(self.package)

    def rewrite(self, mutation, *, update_hash=True):
        knowledge = json.loads((self.package / 'knowledge.json').read_bytes())
        mutation(knowledge)
        contents = json_bytes(knowledge)
        (self.package / 'knowledge.json').write_bytes(contents)
        if update_hash:
            manifest = json.loads((self.package / 'manifest.json').read_bytes())
            manifest['artifacts']['knowledge.json'] = {'sha256': sha256(contents), 'bytes': len(contents)}
            (self.package / 'manifest.json').write_bytes(json_bytes(manifest))

    def test_l0_keeps_claim_identity_scope_uncertainty_lifecycle_and_evidence_ids(self):
        for number in (1, 2, 3):
            cid = ident('claims', f'c{number}')
            result = self.query.lookup(cid)
            self.assertEqual(result['record'], self.state[f'claims/{cid}.yaml'])
            self.assertEqual(result['build']['source_revision'], self.revision)
            self.assertEqual(result['build']['manifest_sha256'], sha256(self.package_bytes['manifest.json']))
            self.assertNotIn('related', result)
        self.assertEqual(self.query.lookup(ident('claims', 'c3'))['record']['state'], 'retired')

    def test_l1_exposes_evidence_limitations_relationships_questions_and_gaps(self):
        result = self.query.lookup(ident('claims', 'c1'), level=1)
        related = result['related']
        self.assertEqual(related['graph']['items'][0]['type'], 'dependency')
        self.assertIn('Synthetic.', related['evidence']['items'][0]['limitations'])
        self.assertEqual(related['questions']['items'][0]['id'], ident('questions', 'q1'))
        self.assertTrue(any('Synthetic unresolved discovery gap.' in entry['gaps'] for entry in result['gaps']['items']))
        self.assertNotIn('sources', related)
        self.assertNotIn('premise_claim_ids', related['evidence']['items'][0])

    def test_l2_retains_sources_premises_and_original_contribution_provenance(self):
        result = self.query.lookup(ident('claims', 'c1'), level=2)
        sources = {item['id']: item for item in result['related']['sources']['items']}
        source = sources[ident('sources', 's1')]
        self.assertEqual(source['access'], 'not_retrieved')
        self.assertEqual(source['locator'], 'Fixture section 1')
        self.assertIn('spectral signal', source['excerpt'])
        evidence = {item['id']: item for item in result['related']['evidence']['items']}
        self.assertEqual(evidence[ident('evidence', 'e2')]['premise_claim_ids'], [ident('claims', 'c1')])
        provenance = {item['path']: item['record'] for item in result['provenance']['items']}
        self.assertEqual(provenance[f'input-artefacts/{RUN}.json'], self.state[f'input-artefacts/{RUN}.json'])
        self.assertIn('input-artefacts/RUN-' + '7' * 32 + '.json', provenance)
        self.assertTrue(any(path.startswith('briefs/closed/') for path in provenance))
        self.assertTrue(any(path.startswith('briefs/ready/') for path in provenance))

    def test_every_canonical_record_is_addressable(self):
        for group in ('claims', 'evidence', 'sources', 'graph', 'questions'):
            for record_id, record in self.query.records[group].items():
                result = self.query.lookup(record_id, level=2)
                self.assertTrue(result['found'])
                self.assertEqual(result['record'], record)

    def test_rejected_candidates_are_never_searchable_as_accepted_claims(self):
        self.assertEqual(self.query.search('dragonfruit')['items'], [])
        self.assertFalse(self.query.lookup(ident('claims', 'c4'))['found'])
        self.assertEqual(self.query.search('')['total'], 3)

    def test_keyword_search_includes_linked_sources_and_is_relevance_only(self):
        result = self.query.search('amber spectral', level=2)
        self.assertEqual(result['ranking'], 'keyword_relevance_only')
        self.assertEqual(len(result['items']), 1)
        hit = result['items'][0]
        self.assertEqual(hit['record']['id'], ident('claims', 'c1'))
        self.assertIn(ident('sources', 's1'), hit['matched_record_ids'])
        self.assertEqual(hit['record']['uncertainty'], 'high')
        self.assertEqual(self.query.search('not_a_fixture_word')['items'], [])

    def test_filtered_discovery_preserves_retired_state_and_pagination(self):
        retired = self.query.search(state='retired', claim_class='hypothesis', uncertainty='high')
        self.assertEqual(retired['total'], 1)
        self.assertEqual(retired['items'][0]['record']['id'], ident('claims', 'c3'))
        first = self.query.search(limit=1)
        second = self.query.search(limit=1, offset=first['next_offset'])
        self.assertEqual(first['total'], 3)
        self.assertNotEqual(first['items'][0]['record']['id'], second['items'][0]['record']['id'])
        self.assertEqual(len(first['items']), 1)

    def test_related_expansion_has_explicit_continuation(self):
        result = self.query.lookup(ident('claims', 'c2'), level=2, related_limit=1)
        evidence = result['related']['evidence']
        self.assertGreater(evidence['total'], 1)
        self.assertEqual(len(evidence['items']), 1)
        self.assertEqual(evidence['next_offset'], 1)
        next_page = self.query.lookup(ident('claims', 'c2'), level=2, related_limit=1, related_offset=1)
        self.assertNotEqual(evidence['items'][0]['id'], next_page['related']['evidence']['items'][0]['id'])

    def test_graph_traversal_follows_only_declared_connectors(self):
        result = self.query.traverse(ident('claims', 'c1'), depth=2)
        ids = {item['claim']['record']['id'] for item in result['items']}
        self.assertEqual(ids, {ident('claims', 'c2'), ident('claims', 'c3')})
        target = next(item for item in result['items'] if item['claim']['record']['id'] == ident('claims', 'c3'))
        self.assertEqual([step['relation'] for step in target['path']], ['dependency', 'coupling'])
        self.assertEqual(target['claim']['record']['state'], 'retired')
        outgoing = self.query.traverse(ident('claims', 'c1'), direction='outgoing')
        self.assertEqual(outgoing['items'], [])

    def test_reverse_dependencies_include_premises_but_exclude_coupling(self):
        result = self.query.dependents(ident('claims', 'c1'), depth=3)
        self.assertEqual([item['claim']['record']['id'] for item in result['items']], [ident('claims', 'c2')])
        # Remove the explicit dependency to verify the evidence-only reverse path.
        self.rewrite(lambda value: value['records']['graph'][ident('graph', 'r1')].update(state='retired'))
        query = Knowledge(self.package)
        path = query.dependents(ident('claims', 'c1'))['items'][0]['path'][0]
        self.assertEqual(path['relation'], 'evidence_premise')
        self.assertEqual(path['premise_claim_ids'], [ident('claims', 'c1')])

    def test_retired_connectors_are_explicitly_opted_in(self):
        self.rewrite(lambda value: value['records']['graph'][ident('graph', 'r1')].update(state='retired'))
        query = Knowledge(self.package)
        normal = query.traverse(ident('claims', 'c1'))
        self.assertEqual(normal['items'], [])
        self.assertFalse(normal['filters']['include_retired_connectors'])
        historical = query.traverse(ident('claims', 'c1'), include_retired=True)
        self.assertEqual(historical['items'][0]['path'][0]['connector_state'], 'retired')

    def test_walk_limits_and_depth_are_enforced(self):
        result = self.query.traverse(ident('claims', 'c2'), limit=1, depth=3)
        self.assertEqual(len(result['items']), 1)
        self.assertTrue(result['truncated'])
        self.assertEqual(self.query.traverse(ident('claims', 'c2'), depth=0)['items'], [])
        for options in ({'limit': 0}, {'limit': 101}, {'depth': -1}, {'depth': 11}, {'level': 3}):
            with self.subTest(options=options), self.assertRaises(Invalid):
                self.query.traverse(ident('claims', 'c1'), **options)
        for options in ({'limit': 0}, {'offset': -1}, {'related_limit': 0}):
            with self.subTest(options=options), self.assertRaises(Invalid):
                self.query.search(**options)

    def test_rebuilding_index_and_mutating_results_cannot_change_authoritative_data(self):
        before = self.query.search('synthetic', level=2)
        self.query.rebuild_index()
        self.assertEqual(json_bytes(before), json_bytes(self.query.search('synthetic', level=2)))
        result = self.query.lookup(ident('claims', 'c1'), level=2)
        result['record']['uncertainty'] = 'low'
        result['related']['sources']['items'][0]['access'] = 'inspected'
        self.assertEqual(self.query.lookup(ident('claims', 'c1'))['record']['uncertainty'], 'high')
        self.assertEqual({path.name: path.read_bytes() for path in self.package.iterdir()}, self.package_bytes)

    def test_package_corruption_and_wrong_manifest_pin_fail(self):
        with self.assertRaisesRegex(Invalid, 'Pinned manifest'):
            Knowledge(self.package, '0' * 64)
        self.rewrite(lambda value: value['records']['claims'][ident('claims', 'c1')].update(uncertainty='medium'),
                     update_hash=False)
        with self.assertRaisesRegex(Invalid, 'integrity'):
            Knowledge(self.package)

    def test_forged_reverse_links_and_pending_contributions_are_rejected(self):
        self.rewrite(lambda value: value['reverse_links']['sources'][ident('sources', 's1')].update(evidence_ids=[]))
        with self.assertRaisesRegex(Invalid, 'reverse links'):
            Knowledge(self.package)
        for name, contents in self.package_bytes.items():
            (self.package / name).write_bytes(contents)
        proposal = contribution(token='a' * 32)
        self.rewrite(lambda value: value['provenance'].update(state_for(proposal)))
        with self.assertRaisesRegex(Invalid, 'Awaiting admission'):
            Knowledge(self.package)

    def test_package_revision_and_manifest_pin_isolate_results(self):
        for name, contents in self.later_package_bytes.items():
            (self.package / name).write_bytes(contents)
        other = Knowledge(self.package)
        self.assertEqual(other.lookup(ident('claims', 'c1'))['build']['source_revision'], self.later_revision)
        self.assertNotEqual(other.build['manifest_sha256'], self.query.build['manifest_sha256'])
        self.assertEqual(other.search('amber spectral')['items'], [])
        self.assertEqual(self.query.search('copper resonance')['items'], [])
        self.assertEqual(other.search('copper resonance')['items'][0]['record']['id'], ident('claims', 'c1'))
        with self.assertRaisesRegex(Invalid, 'Pinned manifest'):
            Knowledge(self.package, self.query.build['manifest_sha256'])
        self.assertEqual(self.query.lookup(ident('claims', 'c1'))['build']['source_revision'], self.revision)

    def test_unknown_record_is_not_found_without_a_truth_verdict(self):
        result = self.query.lookup('C-' + 'f' * 32)
        self.assertFalse(result['found'])
        self.assertIsNone(result['record'])
        self.assertNotIn('truth', result)

    def test_duplicate_json_members_are_rejected(self):
        path = self.package / 'manifest.json'
        path.write_bytes(b'{"derived":true,"derived":false}')
        with self.assertRaisesRegex(Invalid, 'Duplicate mapping'):
            Knowledge(self.package)

    def test_cli_lookup_search_and_graph_queries(self):
        commands = [
            ['lookup', ident('claims', 'c1'), '--level', '2'],
            ['search', 'amber', '--limit', '1'],
            ['traverse', ident('claims', 'c1'), '--depth', '2'],
            ['dependents', ident('claims', 'c1')],
        ]
        for command in commands:
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/query_knowledge.py'),
                                     '--package', str(self.package), *command], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['build']['source_revision'], self.revision)


if __name__ == '__main__':
    unittest.main()
