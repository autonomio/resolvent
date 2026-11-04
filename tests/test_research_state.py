"""Synthetic question histories only; never fetch or seed a real world model."""
import hashlib
import json
import subprocess
import sys
import unittest

import jsonschema

from scripts.build_knowledge import json_bytes
from scripts.model import Invalid, digest
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


def records(result, kind):
    return {row['id']: row for row in result[kind]}


class ResearchStateTests(unittest.TestCase):
    def query(self, state):
        fixture = QueryFixture(state)
        self.addCleanup(fixture.temp.cleanup)
        return fixture.query

    def export(self, query, **options):
        return query.research_state('external-question-9', repository='example/world',
            reference_pointer='/method_metadata/external/question', complete=True, **options)

    def test_external_question_without_q_keeps_native_science_and_compact_provenance(self):
        p = proposal(); q = self.query(admitted(p)); result = self.export(q)
        for kind, values in q.records.items():
            self.assertEqual(records(result, kind), values)
        self.assertEqual(result['question']['recorded_texts'][0]['text'], p['brief']['question'])
        self.assertEqual(result['provenance']['submissions'][0]['id'], p['id'])
        self.assertEqual(result['provenance']['submissions'][0]['sha256'], q.input_hashes[f"input-artefacts/{p['id']}.json"])
        self.assertEqual(result['build'], q.build)
        self.assertEqual(result['repository'], 'example/world')
        self.assertEqual(result['references'][0]['id'], 'paper-one')
        self.assertEqual(result['reviewed_papers'][0]['work_id'], 'paper-one')
        self.assertEqual(result['contradictions'][0]['record'], research()['contradictions'][0])
        self.assertFalse(result['coverage']['exhaustive'])
        self.assertNotIn('producer_material', result)
        result['claims'].clear(); self.assertTrue(q.records['claims'])

    def test_canonical_question_uses_context_and_keeps_support_chains(self):
        p = proposal(); p['questions'] = [{'id': 'q1', 'question': 'Synthetic question?', 'claim_ids': ['c1']}]
        q = self.query(admitted(p)); qid = ids(q.state, 'questions')[0]
        result = q.research_state(qid, repository='example/world', complete=True)
        for kind in ('claims', 'sources', 'evidence', 'questions'):
            self.assertEqual(records(result, kind), q.records[kind])
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
        for kind in ('claims', 'evidence', 'sources', 'graph'):
            self.assertEqual(records(result, kind), q.records[kind])
        state = fixture(); subjects = ids(state, 'claims')
        state, _, _ = maintain(state, [comparison(subjects)])
        q = self.query(state); qid = ids(state, 'questions')[0]
        self.assertEqual(q.research_state(qid, repository='example/world', complete=True)['assessments'][subjects[0]]['status'], 'disputed')

    def test_rejected_and_deferred_findings_are_never_exported_as_claims(self):
        for action in ('reject', 'defer'):
            p = proposal(); state = state_for(p)
            d = decisions(p, action); d['follow_up_gaps'] = ['Synthetic disposition gap.']
            state.update(plan_admission(state, p['id'], d, ROOT))
            result = self.export(self.query(state))
            self.assertEqual(result['claims'], [])
            finding = result['rejected_deferred_findings'][0]
            self.assertEqual(finding['claims'], p['claims'])
            self.assertEqual(finding['evidence'], p['evidence'])
            self.assertEqual(finding['sources'][0]['access'], p['sources'][0]['access'])
            self.assertNotIn('excerpt', finding['sources'][0])
            self.assertEqual(finding['dispositions'][0]['disposition'], 'rejected' if action == 'reject' else 'deferred')
            self.assertIn('Synthetic disposition gap.', [r['record'] for r in result['gaps']])

    def test_repeated_reviews_compact_only_display_fields_and_keep_each_origin(self):
        state = admitted(proposal()); p = proposal('2'); payload = research()
        payload['reviewed_papers'].append({'work_id': 'missing-paper', 'eligibility': 'uncertain'})
        p['result']['artifacts'][0]['content'] = json.dumps(payload)
        state.update(state_for(p)); state.update(plan_admission(state, p['id'], decisions(p), ROOT))
        result = self.export(self.query(state))
        self.assertEqual(len(result['provenance']['submissions']), 2)
        self.assertEqual(len(result['references']), 1)
        self.assertEqual(len(result['references'][0]['provenance']), 2)
        self.assertEqual(len(result['reviewed_papers']), 1)
        self.assertEqual(len(result['reviewed_papers'][0]['provenance']), 2)
        self.assertEqual(result['review_coverage']['other_reviews'][0]['work_id'], 'missing-paper')

    def test_citation_inspection_and_incomplete_reviews_do_not_imply_review(self):
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
            self.assertEqual(result['reviewed_papers'], [], change)
            self.assertEqual(result['references'][0]['stages']['substantively_reviewed'], 'unknown', change)
            if change == 'preview':
                self.assertTrue(result['references'][0]['preview_marker_detected'])
        p = proposal(); p['sources'][0].update(kind='publication', uri='https://doi.org/10.example/native')
        p['result']['artifacts'] = []
        result = self.export(self.query(admitted(p)))
        self.assertEqual(result['sources'][0]['access'], 'inspected')
        self.assertEqual(result['sources'][0]['uri'], 'https://doi.org/10.example/native')
        self.assertEqual(result['reviewed_papers'], [])
        self.assertEqual(result['review_coverage']['submissions'][0]['status'], 'unknown')

    def test_unknown_artifact_reports_unknown_coverage_and_identifies_the_original(self):
        for content in ('not JSON', '{}', '{"references":[]}', '{"reviewed_papers":[]}', '{"references":{},"reviewed_papers":[]}'):
            p = proposal(); p['result']['artifacts'][0]['content'] = content
            q = self.query(admitted(p)); result = self.export(q)
            self.assertEqual(result['review_coverage']['submissions'][0]['status'], 'unknown')
            path = f"input-artefacts/{p['id']}.json"
            self.assertEqual(result['provenance']['submissions'][0]['path'], path)
            self.assertEqual(result['provenance']['submissions'][0]['sha256'], q.input_hashes[path])

    def test_invalid_plain_numbers_and_unicode_fall_back_without_breaking_the_export(self):
        for content in ('{"references":[],"reviewed_papers":[],"gaps":[1e999]}',
                        '{"references":[],"reviewed_papers":[],"gaps":["\\ud800"]}'):
            p = proposal(); p['result']['artifacts'][0]['content'] = content
            result = self.export(self.query(admitted(p)))
            self.assertEqual(result['review_coverage']['submissions'][0]['status'], 'unknown')
            json_bytes(result)  # Still finite, valid UTF-8 JSON.
        p = proposal(); p['result']['artifacts'][0]['content'] = '{"references":[],"reviewed_papers":[]}'
        self.assertEqual(self.export(self.query(admitted(p)))['review_coverage']['submissions'][0]['status'], 'preserved_producer_report')

    def test_external_question_closes_existing_claim_links_like_the_q_selector(self):
        parent = proposal(); parent['method_metadata']['external']['question'] = 'older-question'
        state = admitted(parent)
        cid = canonical_id(parent['id'], 'claims', 'c1')
        child = proposal('2'); child['claims'] = []
        child['handoff']['no_claims_reason'] = 'Question-only follow-up.'
        child['questions'] = [{'id': 'q1', 'question': 'Which prior finding applies?', 'claim_ids': [cid]}]
        state.update(state_for(child)); state.update(plan_admission(state, child['id'], decisions(child), ROOT))
        q = self.query(state); external = self.export(q)
        qid = canonical_id(child['id'], 'questions', 'q1')
        canonical = q.research_state(qid, repository='example/world', complete=True)
        for kind in ('claims', 'evidence', 'sources'):
            self.assertEqual(records(external, kind), records(canonical, kind))
        self.assertIn(cid, records(external, 'claims'))
        self.assertIn(cid, external['assessments'])

    def test_unlinked_world_data_is_omitted_with_an_explicit_scope(self):
        state = admitted(proposal()); p = contribution(token='3'*32)
        p['claims'][0]['statement'] = 'An unrelated synthetic proposition.'
        state.update(state_for(p)); state.update(plan_admission(state, p['id'], decisions(p), ROOT))
        result = self.export(self.query(state))
        self.assertNotIn(p['id'], {r['id'] for r in result['provenance']['submissions']})
        self.assertNotIn(canonical_id(p['id'], 'claims', 'c1'), records(result, 'claims'))
        self.assertTrue(result['coverage']['omissions'])

    def test_graph_neighbours_do_not_import_another_questions_claims(self):
        from test_knowledge import linked_state
        state = linked_state(); qid = ids(state, 'questions')[0]
        cid = canonical_id('RUN-'+'1'*32, 'claims', 'c1')
        state['questions/'+qid+'.yaml']['claim_ids'] = [cid]
        result = self.query(state).research_state(qid, repository='example/world', complete=True)
        self.assertEqual(set(records(result, 'claims')), {cid})
        self.assertEqual(result['graph'], [])
        self.assertEqual(result['coverage']['omitted_record_counts']['claims'], 1)

    def test_unused_sources_and_producer_bundles_are_not_copied_into_context(self):
        import copy
        p = proposal(); unused = copy.deepcopy(p['sources'][0]); unused['id'] = 'unused'
        unused['excerpt'] = 'Unneeded full text. ' * 10000
        p['sources'].append(unused)
        p['method_metadata']['canary_view'] = {'display': 'unused' * 10000}
        p['result']['artifacts'].append({'name': 'canary-bundle.json', 'content': 'unused' * 10000})
        result = self.export(self.query(admitted(p)))
        self.assertEqual(len(result['sources']), 1)
        self.assertLess(len(json_bytes(result)), 20000)
        self.assertNotIn('Unneeded full text.', json.dumps(result))
        self.assertEqual(result['coverage']['omitted_record_counts']['sources'], 1)

    def test_parent_lineage_keeps_anchors_without_importing_another_questions_reviews(self):
        parent = proposal(); parent['method_metadata']['external']['question'] = 'another-question'
        payload = research(); payload['references'][0]['id'] = 'other-paper'
        payload['reviewed_papers'][0]['work_id'] = 'other-paper'
        payload['selection']['selected_for_review_ids'] = ['other-paper']
        parent['result']['artifacts'][0]['content'] = json.dumps(payload)
        state = admitted(parent)
        child = proposal('2'); child['parent_run_id'] = parent['id']
        child['claims'][0]['statement'] = 'A different synthetic finding for the selected question.'
        state.update(state_for(child)); state.update(plan_admission(state, child['id'], decisions(child), ROOT))
        result = self.export(self.query(state))
        self.assertEqual(len(result['provenance']['submissions']), 2)
        self.assertEqual({r['id'] for r in result['references']}, {'paper-one'})
        self.assertEqual({r['work_id'] for r in result['reviewed_papers']}, {'paper-one'})
        self.assertEqual(result['review_coverage']['submissions'][0]['status'], 'lineage_only')

    def test_unicode_pages_reassemble_exact_export_with_stable_digest(self):
        p = proposal(); p['sources'][0]['excerpt'] = 'Synthetic 🙂 quotation\n'*50
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
        self.assertEqual(self.export(self.query(admitted(p)))['review_coverage']['submissions'][0]['status'], 'unknown')

    def test_encoded_cycles_external_pointers_and_expansion_are_bounded(self):
        from unittest.mock import patch
        for token in ({'$canary_value': 0}, {'$canary_ref': 'https://example.invalid/payload'},
                      {'$canary_ref': '/result/artifacts/0/content'}):
            p = proposal(); p['result']['artifacts'][0]['content'] = json.dumps(token)
            p['method_metadata']['canary_encoding'] = {'format':'canary.references','version':1,'values':[token],
                'artifacts':[{'index':0,'name':'canary-research.json','style':'default'}], 'view':False,'sha256':'0'*64}
            with self.assertRaises(ValueError): research_artifact(p)
        p = proposal(); original = p['result']['artifacts'][0]['content']
        checksum = hashlib.sha256(json.dumps({'artifacts': [original]}, ensure_ascii=False,
            sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        p['method_metadata']['canary_encoding'] = {'format': 'canary.references', 'version': 1,
            'values': [], 'artifacts': [{'index': 0, 'name': 'canary-research.json', 'style': 'default'}],
            'view': False, 'sha256': checksum}
        self.assertEqual(research_artifact(p)[1], research())
        with patch('scripts.research_state.MAX_EXPANDED_BYTES', 10):
            with self.assertRaisesRegex(ValueError, 'expansion exceeds'): research_artifact(p)

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

    def test_original_git_json_restores_order_dependent_checksums_with_verified_pins(self):
        p = proposal(); payload = research(); payload['native'] = {'$canary_ref': '/claims'}
        expected = research(); expected['native'] = p['claims']
        p['result']['artifacts'][0]['content'] = json.dumps(payload)
        expanded = json.dumps(expected, ensure_ascii=False)
        checksum = hashlib.sha256(json.dumps({'artifacts': [expanded]}, ensure_ascii=False,
            sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        p['method_metadata']['canary_encoding'] = {'format': 'canary.references', 'version': 1,
            'values': [], 'artifacts': [{'index': 0, 'name': 'canary-research.json', 'style': 'default'}],
            'view': False, 'sha256': checksum}
        fixture = QueryFixture(admitted(p)); self.addCleanup(fixture.temp.cleanup)
        self.assertEqual(self.export(fixture.query)['review_coverage']['submissions'][0]['status'], 'unknown')
        result = self.export(fixture.query, source_repo=fixture.root/'repo')
        self.assertEqual(result['review_coverage']['submissions'][0]['status'], 'preserved_producer_report')
        self.assertEqual(result['coverage']['producer_material_input'], 'original_git_json')
        path = f"input-artefacts/{p['id']}.json"
        fixture.query.input_hashes[path] = '0'*64
        with self.assertRaisesRegex(Invalid, 'input-file hash'):
            self.export(fixture.query, source_repo=fixture.root/'repo')
        from unittest.mock import patch
        with patch('scripts.research_state.git', return_value=b'10485761\n') as read:
            with self.assertRaisesRegex(Invalid, '10 MiB'):
                self.export(fixture.query, source_repo=fixture.root/'repo')
            self.assertEqual(read.call_count, 1)  # Refuse before reading the oversized blob.

    def test_cli_and_schema(self):
        fixture = QueryFixture(admitted(proposal())); self.addCleanup(fixture.temp.cleanup)
        raw = subprocess.check_output([sys.executable, str(ROOT/'scripts/query_knowledge.py'), '--package', str(fixture.package),
            'research-state', 'external-question-9', '--repository', 'example/world',
            '--reference-pointer', '/method_metadata/external/question', '--complete'])
        result = json.loads(raw)
        schema = json.loads((ROOT/'docs/schemas/research-state.schema.json').read_text())
        jsonschema.validate(result, schema)
        self.assertEqual(result, self.export(fixture.query))
