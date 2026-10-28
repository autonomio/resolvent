"""Synthetic ancestry fixtures; review cues never establish evidence independence."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.build_knowledge import ROOT, compile_revision, json_bytes
from scripts.model import Invalid, validate_state
from scripts.query_knowledge import Knowledge
from scripts.world_control import canonical_id, plan_admission
from test_model import contribution, decisions, state_for, write_state

RUN = 'RUN-' + '4' * 32


def ident(group, local):
    return canonical_id(RUN, group, local)


def proposal():
    p = contribution('conversation', token='4' * 32)
    p['schema_version'] = '1.2'
    source, evidence, claim = [copy.deepcopy(p[group][0]) for group in ('sources','evidence','claims')]
    text = ('Synthetic ancestralquartz observations use one shared fixture with twelve numbered '
            'entries to exercise source lineage without making any empirical research claim.')
    digest = hashlib.sha256(text.encode()).hexdigest()
    p.update(sources=[], evidence=[], claims=[])
    for number in range(1, 6):
        p['sources'].append({**copy.deepcopy(source), 'id':f's{number}',
            'title':f'Synthetic source {number}', 'locator':f'Fixture paragraph {number}',
            'uri':f'https://example.invalid/fixture/{number}',
            'excerpt':text if number <= 3 else f'Distinct synthetic record {number}.',
            'access':'not_retrieved' if number == 5 else 'inspected'})
        p['evidence'].append({**copy.deepcopy(evidence), 'id':f'e{number}',
            'summary':f'Synthetic statement {number}.', 'source_ids':[f's{number}']})
        if number <= 4:
            p['claims'].append({**copy.deepcopy(claim), 'id':f'c{number}',
                'statement':f'Synthetic proposition {number} remains untested.', 'evidence_ids':[f'e{number}']})
    for number, status, parents in ((1,'original',[]),(2,'derived',['s1']),
                                    (3,'derived',['s2']),(4,'original',[]),(5,'unknown',[])):
        p['sources'][number-1]['ancestry'] = {
            'status':status, 'parent_source_ids':parents, 'notes':['Synthetic declared lineage only.']}
    p['sources'][0]['ancestry'].update(content_sha256=digest, version='Synthetic version 1')
    p['sources'][1]['ancestry']['content_sha256'] = digest
    p['evidence'][1]['premise_claim_ids'] = ['c1']
    p['evidence'][4]['premise_claim_ids'] = ['c1','c2']
    p['connectors'] = [{'id':'r1','from':'c4','to':'c1','type':'dependency',
        'spec':'structural:weak:inward', 'reason':'Synthetic premise relation.',
        'uncertainty':'high','evidence_ids':['e5']}]
    return p


def admitted(p=None):
    p = p or proposal()
    state = state_for(p)
    state.update(plan_admission(state, p['id'], decisions(p), ROOT))
    return state


class LineageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.fixture.cleanup)
        cls.repo = Path(cls.fixture.name)/'repo'
        cls.repo.mkdir()
        cls.state = admitted()
        write_state(cls.repo, cls.state)
        subprocess.run(['git','init','-q',str(cls.repo)], check=True)
        subprocess.run(['git','-C',str(cls.repo),'add','.'], check=True)
        subprocess.run(['git','-C',str(cls.repo),'-c','user.name=Synthetic test',
                        '-c','user.email=test@example.invalid','commit','-qm','Synthetic lineage fixture'],check=True)
        cls.revision = subprocess.check_output(['git','-C',str(cls.repo),'rev-parse','HEAD'],text=True).strip()
        cls.package = Path(cls.fixture.name)/'package'
        cls.package.mkdir()
        for name,data in compile_revision(cls.repo,cls.revision).items():
            (cls.package/name).write_bytes(data)

    def setUp(self):
        self.query = Knowledge(self.package)

    def test_direct_and_indirect_copies_expose_one_declared_origin(self):
        report = self.query.lineage(ident('evidence','e3'),limit=None)
        source = report['sources'][ident('sources','s3')]
        self.assertEqual(source['ancestor_source_ids'],sorted([ident('sources','s1'),ident('sources','s2')]))
        self.assertEqual(source['declared_original_source_ids'],[ident('sources','s1')])
        flag = next(item for item in report['flags'] if item['key']==ident('sources','s1'))
        self.assertEqual(flag['basis'],'deterministic_metadata')
        self.assertTrue({ident('evidence','e1'),ident('evidence','e2'),ident('evidence','e3')} <= set(flag['evidence_ids']))
        self.assertEqual(flag['independence_assessment'],'unresolved')

    def test_identical_declared_hashes_are_distinct_from_similarity_heuristics(self):
        flags = self.query.lineage(limit=None)['flags']
        exact = next(item for item in flags if item['kind']=='shared_declared_content_sha256')
        self.assertEqual(exact['basis'],'deterministic_metadata')
        self.assertEqual(exact['source_ids'],sorted([ident('sources','s1'),ident('sources','s2')]))
        repeated = next(item for item in flags if item['kind']=='possible_repeated_excerpt')
        self.assertEqual(repeated['basis'],'heuristic')
        self.assertEqual(len(repeated['source_ids']),3)

    def test_distinct_declared_source_does_not_become_an_independence_verdict(self):
        report = self.query.lineage(ident('evidence','e4'),limit=None)
        self.assertEqual(report['flags'],[])
        self.assertEqual(report['evidence'][ident('evidence','e4')]['independence_assessment'],'not_determined')
        self.assertEqual(report['sources'][ident('sources','s4')]['record'],self.state[f"sources/{ident('sources','s4')}.yaml"])

    def test_premise_inheritance_includes_connector_only_evidence(self):
        report = self.query.lineage(ident('evidence','e5'),limit=None)
        evidence = report['evidence'][ident('evidence','e5')]
        self.assertEqual(evidence['record']['claim_ids'],[])
        self.assertEqual(evidence['record']['premise_claim_ids'],[ident('claims','c1'),ident('claims','c2')])
        self.assertEqual(evidence['upstream_evidence_ids'],sorted([ident('evidence','e1'),ident('evidence','e2')]))
        self.assertIn(ident('sources','s1'),evidence['source_ancestry_ids'])
        self.assertEqual(evidence['connector_ids'],[ident('graph','r1')])
        self.assertIn(ident('graph','r1'),report['connectors'])
        self.assertTrue({ident('claims','c1'),ident('claims','c4')} <= set(report['claims']))

    def test_unknown_ancestry_and_unretrieved_access_remain_unresolved(self):
        report = self.query.lineage(ident('evidence','e5'),limit=None)
        sid = ident('sources','s5')
        self.assertEqual(report['sources'][sid]['unresolved_sources'][sid],['ancestry_unknown','not_retrieved'])
        self.assertEqual(report['evidence'][ident('evidence','e5')]['unresolved_sources'][sid],['ancestry_unknown','not_retrieved'])
        self.assertEqual(report['sources'][sid]['record']['access'],'not_retrieved')

    def test_report_is_stable_keeps_anchors_and_does_not_mutate_the_model(self):
        before = copy.deepcopy(self.query.knowledge)
        report = self.query.lineage(limit=None)
        self.assertEqual(json_bytes(report),json_bytes(self.query.lineage(limit=None)))
        self.assertEqual(self.query.knowledge,before)
        self.assertEqual(report['build']['source_revision'],self.revision)
        source = report['sources'][ident('sources','s1')]['record']
        self.assertEqual(source['locator'],'Fixture paragraph 1')
        self.assertEqual(source['ancestry']['version'],'Synthetic version 1')
        self.assertEqual(report['claims'][ident('claims','c1')]['uncertainty'],'high')
        self.assertFalse(report['evidence'][ident('evidence','e1')]['record']['independent'])

    def test_l2_and_search_retain_declared_ancestor_records(self):
        report = self.query.lookup(ident('claims','c3'),level=2)
        ids = {source['id'] for source in report['related']['sources']['items']}
        self.assertTrue({ident('sources',f's{n}') for n in (1,2,3)} <= ids)
        ids = {item['record']['id'] for item in self.query.search('ancestralquartz')['items']}
        self.assertTrue({ident('claims',f'c{n}') for n in (1,2,3)} <= ids)

    def test_cli_reports_a_real_compiled_snapshot(self):
        result = subprocess.run([sys.executable,str(ROOT/'scripts/query_knowledge.py'),
            '--package',str(self.package),'lineage','--evidence',ident('evidence','e3')],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['focus_evidence_id'],ident('evidence','e3'))
        with self.assertRaises(Invalid):
            self.query.lineage('e3')


class AncestryValidationTests(unittest.TestCase):
    def test_canonical_and_submission_ancestry_definitions_match(self):
        canonical=json.loads((ROOT/'docs/schemas/sources.schema.json').read_text())
        submission=json.loads((ROOT/'docs/schemas/submission.schema.json').read_text())
        self.assertEqual(canonical['$defs']['source_ancestry'],submission['$defs']['source_ancestry'])
    def test_schema_extension_preserves_legacy_protocols_and_rejects_early_ancestry(self):
        for version in ('1.0','1.1'):
            p=proposal();p['schema_version']=version
            with self.subTest(version=version),self.assertRaises(Invalid):
                validate_state(state_for(p),ROOT)
            for source in p['sources']:
                source.pop('ancestry')
            validate_state(admitted(p),ROOT,True)

    def test_parents_are_remapped_but_source_records_and_input_remain_intact(self):
        p=proposal();original=copy.deepcopy(p);state=admitted(p)
        self.assertEqual(p,original)
        source=state[f"sources/{ident('sources','s3')}.yaml"]
        self.assertEqual(source['ancestry']['parent_source_ids'],[ident('sources','s2')])
        self.assertEqual(source['excerpt'],p['sources'][2]['excerpt'])
        self.assertEqual(source['access'],p['sources'][2]['access'])

    def test_self_cycles_missing_parents_and_invalid_declarations_are_rejected(self):
        cases = [
            (0,{'status':'derived','parent_source_ids':['s1']}),
            (0,{'status':'derived','parent_source_ids':['s3']}),
            (1,{'parent_source_ids':['missing']}),
            (1,{'parent_source_ids':[]}),
            (0,{'parent_source_ids':['s4']}),
            (1,{'content_sha256':'not-a-digest'}),
        ]
        for index,mutation in cases:
            p=proposal();p['sources'][index]['ancestry'].update(mutation)
            with self.subTest(mutation=mutation),self.assertRaises(Invalid):
                admitted(p)

    def test_lineage_does_not_relax_low_uncertainty_or_external_access_rules(self):
        p=proposal();p['claims'][0]['uncertainty']='low'
        with self.assertRaisesRegex(Invalid,'independent inspected'):
            admitted(p)
        p=proposal();p['evidence'][4].update(kind='external',independent=True)
        with self.assertRaisesRegex(Invalid,'inspected, addressable'):
            admitted(p)

    def test_a_new_run_can_preserve_an_existing_canonical_parent_source(self):
        state=admitted();p=contribution('conversation',token='5'*32)
        p['schema_version']='1.2';p['parent_run_id']=RUN
        p['claims'][0]['statement']='A synthetic follow-up remains untested.'
        parent=ident('sources','s1')
        p['sources'][0]['ancestry']={'status':'derived','parent_source_ids':[parent],
                                  'notes':['Synthetic reuse of a prior canonical source.']}
        state.update(state_for(p));state.update(plan_admission(state,p['id'],decisions(p),ROOT))
        validate_state(state,ROOT,True)
        child=canonical_id(p['id'],'sources','s1')
        self.assertEqual(state[f'sources/{child}.yaml']['ancestry']['parent_source_ids'],[parent])
        self.assertEqual(p['sources'][0]['ancestry']['parent_source_ids'],[parent])

    def test_canonical_cycles_remain_invalid_even_when_local_input_was_acyclic(self):
        state=admitted();source=state[f"sources/{ident('sources','s1')}.yaml"]
        source['ancestry'].update(status='derived',parent_source_ids=[ident('sources','s3')])
        with self.assertRaisesRegex(Invalid,'Circular source ancestry'):
            validate_state(state,ROOT,True)

    def test_legacy_sources_produce_useful_unresolved_and_heuristic_reports(self):
        p=proposal();p['schema_version']='1.0'
        for source in p['sources']:
            source.pop('ancestry')
        p['sources'][1]['uri']=p['sources'][0]['uri']+'#copied-section'
        with tempfile.TemporaryDirectory() as directory:
            repo=Path(directory)/'repo';repo.mkdir();write_state(repo,admitted(p))
            subprocess.run(['git','init','-q',str(repo)],check=True)
            subprocess.run(['git','-C',str(repo),'add','.'],check=True)
            subprocess.run(['git','-C',str(repo),'-c','user.name=Synthetic test',
                            '-c','user.email=test@example.invalid','commit','-qm','Legacy fixture'],check=True)
            package=Path(directory)/'package';package.mkdir()
            for name,data in compile_revision(repo,'HEAD').items():
                (package/name).write_bytes(data)
            report=Knowledge(package).lineage(ident('evidence','e2'),limit=None)
            source=report['sources'][ident('sources','s2')]
            self.assertEqual(source['declared_original_source_ids'],[])
            self.assertEqual(source['unresolved_sources'][ident('sources','s2')],['ancestry_unknown'])
            uri_flag=next(item for item in report['flags'] if item['kind']=='possible_duplicate_uri')
            self.assertEqual(uri_flag['basis'],'heuristic')
            self.assertFalse(any(item['kind']=='shared_declared_content_sha256' for item in report['flags']))


if __name__=='__main__':
    unittest.main()
