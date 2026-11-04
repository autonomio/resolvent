"""Synthetic question histories only; never fetch or seed a real world model."""
import hashlib
import json
import subprocess
import sys
import unittest

import jsonschema

from scripts.build_knowledge import json_bytes
from scripts.model import Invalid
from scripts.research_state import research_artifact
from scripts.world_control import canonical_id, plan_admission
from test_model import ROOT, admitted, contribution, decisions, state_for
from test_model_operations import QueryFixture, ids


def research():
    return {'question': 'Synthetic prior question?',
        'references': [{'id': 'paper-one', 'doi': '10.example/test', 'url': 'https://example.invalid/paper',
                        'fresh_download_at': '2026-01-01T00:00:00Z', 'full_text_status': 'full_text'}],
        'selection': {'selected_for_review_ids': ['paper-one']},
        'reviewed_papers': [{'work_id': 'paper-one', 'eligibility': 'core', 'investigated_sections': ['results'],
                            'passage_ids_read': ['p1'], 'incorporated_in_output': True,
                            'substantive_review_note': 'Synthetic review of the recorded results.'}],
        'contradictions': [{'id': 'conflict-one', 'description': 'Synthetic unresolved contradiction.'}],
        'gaps': ['Synthetic unresolved gap.']}


def proposal(token='1'):
    p = contribution(token=token*32)
    p['method_metadata'] = {'external': {'question': 'external-question-9'}}
    p['result']['artifacts'] = [{'name': 'canary-research.json', 'content': json.dumps(research(), ensure_ascii=False)}]
    return p


class ResearchStateTests(unittest.TestCase):
    def query(self, state):
        fixture = QueryFixture(state)
        self.addCleanup(fixture.temp.cleanup)
        return fixture.query

    def export(self, query, **options):
        return query.research_state('external-question-9', repository='example/world',
            reference_pointer='/method_metadata/external/question', complete=True, **options)

    def test_external_question_without_q_keeps_native_records_and_history(self):
        p = proposal(); state = admitted(p); q = self.query(state)
        result = self.export(q)
        self.assertEqual(result['canonical']['questions'], {})
        self.assertEqual(result['question']['recorded_texts'][0]['text'], p['brief']['question'])
        for group, records in q.records.items():
            self.assertEqual(result['canonical'][group], records)
        self.assertEqual(result['producer_material'], q.knowledge['provenance'])
        self.assertEqual(result['contributing_submission_ids'], [p['id']])
        self.assertEqual(result['build'], q.build)
        self.assertEqual(result['repository'], 'example/world')
        self.assertFalse(result['coverage']['exhaustive'])
        self.assertEqual(result['publications'][0]['stages']['substantively_reviewed'], 'producer_reported')
        self.assertEqual(result['producer_findings'][0]['fields']['contradictions'], research()['contradictions'])
        result['canonical']['claims'].clear()
        self.assertTrue(q.records['claims'])

    def test_canonical_question_uses_context_and_keeps_support_chains(self):
        p = proposal()
        p['questions'] = [{'id': 'q1', 'question': 'Synthetic question?', 'claim_ids': ['c1']}]
        q = self.query(admitted(p)); qid = ids(q.state, 'questions')[0]
        result = q.research_state(qid, repository='example/world', complete=True)
        for group in ('claims', 'sources', 'evidence', 'questions'):
            self.assertEqual(result['canonical'][group], q.records[group])
        self.assertEqual(result['question']['recorded_texts'][0]['text'], 'Synthetic question?')
        self.assertEqual(result['selection']['kind'], 'canonical_question')

    def test_external_question_text_can_come_from_preserved_material_without_a_brief(self):
        p = proposal(); p.update(input_method='source_material', brief=None)
        p['result']['acceptance_outcomes'] = []
        result = self.export(self.query(admitted(p)))
        self.assertEqual(result['question']['recorded_texts'][0]['text'], research()['question'])
        self.assertTrue(result['question']['recorded_texts'][0]['basis'].endswith('#/question'))

    def test_premises_sources_and_disputed_assessments_remain_explicit(self):
        from test_knowledge import linked_state
        from test_model_operations import fixture, maintain, comparison
        q = self.query(linked_state()); qid = ids(q.state, 'questions')[0]
        result = q.research_state(qid, repository='example/world', complete=True)
        for group in ('claims', 'evidence', 'sources', 'graph'):
            self.assertEqual(result['canonical'][group], q.records[group])
        state = fixture(); subjects = ids(state, 'claims')
        state, _, _ = maintain(state, [comparison(subjects)])
        q = self.query(state); qid = ids(state, 'questions')[0]
        result = q.research_state(qid, repository='example/world', complete=True)
        self.assertEqual(result['assessments'][subjects[0]]['status'], 'disputed')

    def test_rejected_and_deferred_findings_are_never_exported_as_claims(self):
        for action in ('reject', 'defer'):
            p = proposal(); state = state_for(p)
            d = decisions(p, action); d['follow_up_gaps'] = ['Synthetic disposition gap.']
            state.update(plan_admission(state, p['id'], d, ROOT))
            result = self.export(self.query(state))
            self.assertEqual(result['canonical']['claims'], {})
            run = result['producer_material'][f"input-artefacts/{p['id']}.json"]
            self.assertEqual(run['claims'], p['claims'])
            receipt = result['producer_material'][f"briefs/closed/BC-{'1'*32}.yaml"]
            self.assertEqual(receipt['claim_dispositions'][0]['disposition'], 'rejected' if action == 'reject' else 'deferred')
            self.assertEqual(receipt['follow_up_gaps'], d['follow_up_gaps'])

    def test_all_matched_submissions_and_unmatched_reviews_are_preserved(self):
        state = admitted(proposal())
        p = proposal('2'); payload = research()
        payload['reviewed_papers'].append({'work_id': 'missing-paper', 'eligibility': 'uncertain'})
        p['result']['artifacts'][0]['content'] = json.dumps(payload)
        state.update(state_for(p)); state.update(plan_admission(state, p['id'], decisions(p), ROOT))
        q = self.query(state); result = self.export(q)
        self.assertEqual(len(result['contributing_submission_ids']), 2)
        self.assertEqual(len(result['publications']), 2)  # Same DOI never collapses observations.
        self.assertEqual(result['review_coverage'][1]['unmatched_review_records'], [payload['reviewed_papers'][1]])

    def test_citation_inspection_hashes_and_incomplete_reviews_do_not_imply_review(self):
        for change in ('no_review', 'preview', 'unselected', 'no_passages', 'no_note', 'uncertain'):
            p = proposal(); payload = research()
            if change == 'no_review': payload['reviewed_papers'] = []
            elif change == 'preview': payload['references'][0]['preview_marker_detected'] = True
            elif change == 'unselected': payload['selection']['selected_for_review_ids'] = []
            elif change == 'no_passages': payload['reviewed_papers'][0]['passage_ids_read'] = []
            elif change == 'no_note': payload['reviewed_papers'][0]['substantive_review_note'] = ''
            else: payload['reviewed_papers'][0]['eligibility'] = 'uncertain'
            p['result']['artifacts'][0]['content'] = json.dumps(payload)
            result = self.export(self.query(admitted(p)))
            self.assertEqual(result['publications'][0]['stages']['substantively_reviewed'], 'unknown', change)
        p = proposal(); p['sources'][0].update(kind='publication', uri='https://doi.org/10.example/native')
        result = self.export(self.query(admitted(p)))
        native = next(r for r in result['publications'] if r['submission_id'] is None)
        self.assertEqual(native['doi'], '10.example/native')
        self.assertEqual(native['stages'], {'discovered': 'recorded_source', 'cited': 'recorded_evidence_link',
            'retrieved': 'inspected_passage_only', 'substantively_reviewed': 'unknown'})

    def test_unknown_artifact_keeps_raw_producer_material(self):
        for content in ('not JSON', '{"references":{},"reviewed_papers":[]}'):
            p = proposal(); p['result']['artifacts'][0]['content'] = content
            result = self.export(self.query(admitted(p)))
            self.assertEqual(result['review_coverage'][0]['status'], 'unknown')
            self.assertEqual(result['producer_material'][f"input-artefacts/{p['id']}.json"], p)

    def test_unlinked_world_data_is_omitted_with_an_explicit_scope(self):
        state = admitted(proposal()); p = contribution(token='3'*32)
        p['claims'][0]['statement'] = 'An unrelated synthetic proposition.'
        state.update(state_for(p)); state.update(plan_admission(state, p['id'], decisions(p), ROOT))
        result = self.export(self.query(state))
        self.assertNotIn(p['id'], result['contributing_submission_ids'])
        self.assertNotIn(canonical_id(p['id'], 'claims', 'c1'), result['canonical']['claims'])
        self.assertTrue(result['coverage']['omissions'])

    def test_unicode_pages_reassemble_exact_export_with_stable_digest(self):
        p = proposal(); p['sources'][0]['excerpt'] = 'Synthetic 🙂 \\ " quotation\n'*50
        q = self.query(admitted(p)); options = dict(repository='example/world', reference_pointer='/method_metadata/external/question')
        parts, offset, hashes = [], 0, set()
        while True:
            page = q.research_state('external-question-9', offset=offset, max_bytes=2048, **options)
            self.assertLessEqual(len(json_bytes(page)), 2048)
            hashes.add(page['state_sha256']); parts.append(page['text'])
            if page['next_offset'] is None:
                self.assertFalse(page['truncated']); break
            self.assertTrue(page['truncated']); self.assertGreater(page['next_offset'], offset)
            offset = page['next_offset']
        text = ''.join(parts)
        self.assertEqual(json.loads(text), self.export(q))
        self.assertEqual(hashes, {hashlib.sha256(text.encode()).hexdigest()})

    def test_invalid_selectors_fail_without_guessing(self):
        q = self.query(admitted(proposal()))
        for options in ({'reference_pointer': '/missing'}, {'reference_pointer': '/bad/~7'}, {'repository': ''}):
            args = dict(repository='example/world', reference_pointer='/method_metadata/external/question'); args.update(options)
            with self.assertRaises(Invalid): q.research_state('external-question-9', **args)
        with self.assertRaises(Invalid): q.research_state('unknown-question', repository='example/world')

    def test_encoded_artifact_round_trip_and_checksum_failure(self):
        p = proposal(); original = p['result']['artifacts'][0]['content']
        payload = research(); payload['question'] = {'$canary_ref': '/brief/question'}
        expected = research(); expected['question'] = p['brief']['question']
        encoded = json.dumps(payload, ensure_ascii=False)
        p['result']['artifacts'][0]['content'] = encoded
        restored = json.dumps(expected, ensure_ascii=False)
        body = json.dumps({'artifacts': [restored]}, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        p['method_metadata']['canary_encoding'] = {'format': 'canary.references', 'version': 1,
            'values': [], 'artifacts': [{'index': 0, 'name': 'canary-research.json', 'style': 'default'}],
            'view': False, 'sha256': hashlib.sha256(body.encode()).hexdigest()}
        self.assertEqual(research_artifact(p)[1], expected)
        p['method_metadata']['canary_encoding']['sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'checksum'): research_artifact(p)
        self.assertEqual(self.export(self.query(admitted(p)))['review_coverage'][0]['status'], 'unknown')

    def test_encoded_cycles_external_pointers_and_expansion_are_bounded(self):
        from unittest.mock import patch
        for token in ({'$canary_value': 0}, {'$canary_ref': 'https://example.invalid/payload'},
                      {'$canary_ref': '/result/artifacts/0/content'}):
            p = proposal(); p['result']['artifacts'][0]['content'] = json.dumps(token)
            p['method_metadata']['canary_encoding'] = {'format':'canary.references','version':1,'values':[token],
                'artifacts':[{'index':0,'name':'canary-research.json','style':'default'}], 'view':False,'sha256':'0'*64}
            with self.assertRaises(ValueError): research_artifact(p)
        with patch('scripts.research_state.MAX_EXPANDED_BYTES', 10):
            with self.assertRaises(ValueError): research_artifact(p)

    def test_encoded_values_literals_numbers_ordered_objects_and_native_arrays(self):
        p = proposal()
        payload = {'references': {'$canary_value': 0}, 'native': {'$canary_ref': '/claims'},
            'literal': {'$canary_literal': {'$canary_ref': 'literal text'}},
            'number': {'$canary_number': '1.0'}, 'ordered': {'$canary_object': [['z', 1], ['1', 2]]}}
        expected = {'references': research()['references'], 'native': p['claims'],
            'literal': {'$canary_ref': 'literal text'}, 'number': 1.0, 'ordered': {'z': 1, '1': 2}}
        p['result']['artifacts'][0]['content'] = json.dumps(payload)
        expanded = json.dumps(expected, ensure_ascii=False)
        checksum = hashlib.sha256(json.dumps({'artifacts': [expanded]}, ensure_ascii=False,
            sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        p['method_metadata']['canary_encoding'] = {'format': 'canary.references', 'version': 1,
            'values': [research()['references']], 'artifacts': [{'index': 0, 'name': 'canary-research.json', 'style': 'default'}],
            'view': False, 'sha256': checksum}
        self.assertEqual(research_artifact(p)[1], expected)

    def test_cli_and_schema(self):
        fixture = QueryFixture(admitted(proposal())); self.addCleanup(fixture.temp.cleanup)
        raw = subprocess.check_output([sys.executable, str(ROOT/'scripts/query_knowledge.py'), '--package', str(fixture.package),
            'research-state', 'external-question-9', '--repository', 'example/world',
            '--reference-pointer', '/method_metadata/external/question', '--complete'])
        result = json.loads(raw)
        schema = json.loads((ROOT/'docs/schemas/research-state.schema.json').read_text())
        jsonschema.validate(result, schema)
        self.assertEqual(result, self.export(fixture.query))
