"""Synthetic model operations only; no research or production-world writes."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest

from scripts.build_knowledge import compile_revision, json_bytes
from scripts.model import Invalid, digest, load_state, validate_delta, validate_state
from scripts.model_operations import current_assessments, model_digest, operation_records
from scripts.query_knowledge import Knowledge
from scripts.world_control import canonical_id, plan_admission, plan_maintenance
from test_model import ROOT, admitted, contribution, decisions, state_for, write_state


def fixture():
    state={}
    for token,statement,uncertainty in [('1','The synthetic fixture value is 7.','high'),
            ('2','The fixture has a synthetic value of seven.','medium')]:
        p=contribution(token=token*32)
        p['claims'][0].update(statement=statement,uncertainty=uncertainty)
        p['questions']=[{'id':'q1','question':'What is the synthetic fixture value?','claim_ids':['c1']}]
        state.update(state_for(p))
        state.update(plan_admission(state,p['id'],decisions(p),ROOT))
    return state


def ids(state,kind):
    return sorted(r['id'] for p,r in state.items() if p.startswith(kind+'/'))


def comparison(subjects,outcome='equivalent',*,identity='compare1',supersedes=None):
    return dict(id=identity,kind='comparison',subject_ids=subjects,basis_ids=subjects,
                outcome=outcome,reason='Synthetic external comparison judgment.',supersedes=supersedes)


def reassessment(state,subjects,uncertainty='high'):
    current=current_assessments(operation_records(state))
    return dict(id='assess1',kind='reassessment',subject_ids=subjects,basis_ids=subjects,
                uncertainty=uncertainty,predecessors={s:current.get(s) for s in subjects},
                reason='Synthetic external reassessment judgment, not research.')


def maintain(state,operations,token='a',*,apply=True,seeds=None):
    mid='M-'+token*32
    record=dict(schema_version='1.2',id=mid,status='pending',base_commit='a'*40,
                created_at='2026-01-01T12:00:00Z',claim_ids=ids(state,'claims'),
                subject_ids=sorted({s for op in operations for s in op['subject_ids']}),
                reviewed_claim_ids=[],touched_files=[],findings=[],deferred=[],no_change_reason=None)
    if seeds is not None:
        record.update(claim_ids=seeds,subject_ids=seeds)
    state=copy.deepcopy(state)
    state['maintenance/'+mid+'.yaml']=record
    decision=dict(expected_model_sha256=model_digest(state),model_operations=operations,
                  reviewed_claim_ids=record['claim_ids'])
    changes=plan_maintenance(state,mid,decision,ROOT)
    if apply:
        state.update(changes)
    return state,changes,decision


class QueryFixture:
    def __init__(self,state):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        repo=self.root/'repo';repo.mkdir()
        write_state(repo,state)
        subprocess.run(['git','init','-q',str(repo)],check=True)
        subprocess.run(['git','-C',str(repo),'add','.'],check=True)
        subprocess.run(['git','-C',str(repo),'-c','user.name=Synthetic fixture',
                        '-c','user.email=fixture@example.invalid','commit','-qm','Synthetic state'],check=True)
        self.package=self.root/'package';self.package.mkdir()
        for name,data in compile_revision(repo,'HEAD').items():
            (self.package/name).write_bytes(data)
        self.query=Knowledge(self.package)


class ModelOperationTests(unittest.TestCase):
    def setUp(self):
        self.state=fixture()

    def query(self,state):
        fixture=QueryFixture(state)
        self.addCleanup(fixture.temp.cleanup)
        return fixture.query

    def test_grouped_reads_keep_original_records_and_disagreement(self):
        subjects=ids(self.state,'claims')
        original={s:copy.deepcopy(self.state['claims/'+s+'.yaml']) for s in subjects}
        state,_,_=maintain(self.state,[comparison(subjects)])
        q=self.query(state)
        self.assertEqual(q.search()['total'],1)
        for subject in subjects:
            view=q.lookup(subject,level=2)
            self.assertEqual(view['record'],original[subject])
            self.assertEqual(view['equivalence_group']['members']['items'],subjects)
            self.assertEqual(view['current_assessment']['status'],'disputed')
            self.assertIsNone(view['current_assessment']['uncertainty'])
            self.assertEqual(view['related']['evidence']['total'],2)
            self.assertGreaterEqual(view['provenance']['total'],6)

    def test_question_groups_are_grouped_in_typed_search(self):
        subjects=ids(self.state,'questions')
        state,_,_=maintain(self.state,[comparison(subjects)])
        q=self.query(state)
        result=q.search(kind='questions')
        self.assertEqual(result['total'],1)
        self.assertEqual(result['items'][0]['member_count'],2)
        self.assertEqual(q.candidates(kind='questions')['total'],2)

    def test_uncertain_and_overlapping_comparisons_do_not_group(self):
        for outcome in ('overlap','distinct','unresolved'):
            with self.subTest(outcome=outcome):
                state,_,_=maintain(self.state,[comparison(ids(self.state,'claims'),outcome)])
                self.assertEqual(self.query(state).search()['total'],2)

    def test_correction_preserves_the_previous_comparison(self):
        subjects=ids(self.state,'claims')
        state,_,_=maintain(self.state,[comparison(subjects)])
        original=copy.deepcopy(state['maintenance/M-'+'a'*32+'.yaml'])
        correction=comparison(subjects,'distinct',supersedes='M-'+'a'*32+'#compare1')
        state,_,_=maintain(state,[correction],token='b')
        self.assertEqual(state['maintenance/M-'+'a'*32+'.yaml'],original)
        self.assertEqual(self.query(state).search()['total'],2)

    def test_reassessment_updates_current_grade_with_permanent_history(self):
        subjects=ids(self.state,'claims')
        state,_,_=maintain(self.state,[comparison(subjects)])
        old=copy.deepcopy(state)
        state,_,decision=maintain(state,[reassessment(state,subjects)],token='b')
        q=self.query(state)
        self.assertEqual(q.lookup(subjects[0])['current_assessment']['status'],'agreed')
        self.assertEqual(q.lookup(subjects[0])['current_assessment']['uncertainty'],'high')
        for subject in subjects:
            history=q.assessments(subject)
            self.assertEqual(history['current_assessment'],'M-'+'b'*32+'#assess1')
            self.assertEqual({item['kind'] for item in history['items']},{'supplied_assessment','reassessment'})
        for path,record in old.items():
            if not path.startswith('claims/'):
                self.assertEqual(record,state[path])
        self.assertEqual(plan_maintenance(state,'M-'+'b'*32,decision,ROOT),{})
        with tempfile.TemporaryDirectory() as a,tempfile.TemporaryDirectory() as b:
            before,after=Path(a),Path(b);write_state(before,old);write_state(after,state)
            validate_delta(after,before,state)

    def test_maintenance_cli_dry_run_apply_and_retry(self):
        subjects=ids(self.state,'claims')
        state,changes,d=maintain(self.state,[reassessment(self.state,subjects)],apply=False)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            write_state(root,state)
            shutil.copytree(ROOT/'docs/schemas',root/'docs/schemas')
            local=root/'.resolvent';local.mkdir()
            decision=local/'decisions.json';decision.write_text(json.dumps(d))
            command=[sys.executable,str(ROOT/'scripts/world_control.py'),'M-'+'a'*32,
                     '--root',str(root),'--decisions',str(decision)]
            dry=subprocess.run(command,capture_output=True,text=True,check=True)
            self.assertEqual(json.loads(dry.stdout)['mode'],'dry_run')
            self.assertEqual(load_state(root),state)
            subprocess.run(command+['--apply'],capture_output=True,text=True,check=True)
            expected=copy.deepcopy(state);expected.update(changes)
            self.assertEqual(load_state(root),expected)
            retry=subprocess.run(command+['--apply'],capture_output=True,text=True,check=True)
            self.assertTrue(json.loads(retry.stdout)['already_processed'])

    def test_admission_can_record_comparison_with_a_new_candidate(self):
        base=copy.deepcopy(self.state)
        p=contribution(token='3'*32);p['claims'][0]['uncertainty']='medium'
        old=canonical_id('RUN-'+'1'*32,'claims','c1')
        new=canonical_id(p['id'],'claims','c1')
        state=copy.deepcopy(base);state.update(state_for(p))
        d=decisions(p)
        d.update(expected_model_sha256=model_digest(state),model_operations=[comparison([old,new])])
        state.update(plan_admission(state,p['id'],d,ROOT))
        self.assertEqual(self.query(state).lookup(new)['current_assessment']['status'],'disputed')
        self.assertEqual(plan_admission(state,p['id'],d,ROOT),{})
        with tempfile.TemporaryDirectory() as a,tempfile.TemporaryDirectory() as b:
            before,after=Path(a),Path(b);write_state(before,base);write_state(after,state)
            validate_delta(after,before,state)

    def test_linkage_for_an_incoming_connector_uses_the_admitted_base(self):
        base=copy.deepcopy(self.state)
        p=contribution(token='3'*32)
        first=canonical_id('RUN-'+'1'*32,'claims','c1')
        second=canonical_id('RUN-'+'2'*32,'claims','c1')
        p['connectors']=[dict(id='r1',type='coupling',spec='structural:weak:balanced',
            uncertainty='high',reason='Synthetic input connector.',evidence_ids=['e1'],
            **{'from':'c1','to':second})]
        state=copy.deepcopy(base);state.update(state_for(p))
        rid=canonical_id(p['id'],'graph','r1')
        record=copy.deepcopy(p['connectors'][0])
        record.update(id=rid,state='active',reason='Synthetic supplied linkage correction.',
            evidence_ids=[canonical_id(p['id'],'evidence','e1')],**{'from':first})
        op=dict(id='link1',kind='linkage',subject_ids=[first,second],basis_ids=[p['id']],
            reason=record['reason'],record=record,previous_sha256=None)
        d=decisions(p);d.update(expected_model_sha256=model_digest(state),model_operations=[op])
        proposed=copy.deepcopy(state);proposed.update(plan_admission(state,p['id'],d,ROOT))
        receipt=proposed['briefs/closed/'+p['id'].replace('RUN-','BC-')+'.yaml']
        saved=receipt['model_operations'][0]
        self.assertIsNone(saved['previous_sha256'])
        self.assertNotIn(rid,saved['read_sha256'])
        self.assertEqual(proposed['graph/'+rid+'.yaml'],record)
        with tempfile.TemporaryDirectory() as a,tempfile.TemporaryDirectory() as b:
            before,after=Path(a),Path(b);write_state(before,base);write_state(after,proposed)
            validate_delta(after,before,proposed)
        changed=copy.deepcopy(d);changed['model_operations'][0]['previous_sha256']=digest(record)
        with self.assertRaisesRegex(Invalid,'Stale relationship write'):
            plan_admission(state,p['id'],changed,ROOT)
        changed=copy.deepcopy(d);changed['model_operations'][0]['basis_ids']=[rid]
        with self.assertRaisesRegex(Invalid,'cannot cite itself'):
            plan_admission(state,p['id'],changed,ROOT)
        # A later edit reads the actually admitted relationship and preserves its digest.
        op=copy.deepcopy(op);op['previous_sha256']=digest(record)
        op['basis_ids']=[rid];op['record']['reason']='Synthetic later linkage correction.'
        updated,_,_=maintain(proposed,[op])
        saved=updated['maintenance/M-'+'a'*32+'.yaml']['model_operations'][0]
        self.assertEqual(saved['read_sha256'][rid],digest(record))
        with tempfile.TemporaryDirectory() as a,tempfile.TemporaryDirectory() as b:
            before,after=Path(a),Path(b);write_state(before,proposed);write_state(after,updated)
            validate_delta(after,before,updated)

    def test_assessment_predecessors_are_explicit_and_stale_ones_fail(self):
        subjects=ids(self.state,'claims')
        state,_,_=maintain(self.state,[reassessment(self.state,subjects)],token='a')
        operation=reassessment(state,subjects,'medium')
        operation['predecessors']={s:None for s in subjects}
        with self.assertRaisesRegex(Invalid,'Stale reassessment'):
            maintain(state,[operation],token='b')
        next_state,_,_=maintain(state,[reassessment(state,subjects,'medium')],token='b')
        self.assertEqual(self.query(next_state).assessments(subjects[0])['current_uncertainty'],'medium')

    def test_grouping_cannot_manufacture_low_uncertainty(self):
        with self.assertRaisesRegex(Invalid,'low uncertainty lacks independent'):
            maintain(self.state,[reassessment(self.state,ids(self.state,'claims'),'low')])

    def test_legacy_reused_assessment_disagreement_is_visible(self):
        state=admitted()
        p=contribution(token='2'*32);state.update(state_for(p))
        state.update(plan_admission(state,p['id'],decisions(p),ROOT))
        # A legacy admission retained a differing supplied grade under the reused ID.
        p=state['input-artefacts/'+p['id']+'.json'];p['claims'][0]['uncertainty']='medium'
        state['briefs/closed/'+p['id'].replace('RUN-','BC-')+'.yaml']['submission_sha256']=digest(p)
        subject=ids(state,'claims')[0]
        self.assertEqual(self.query(state).lookup(subject)['current_assessment']['status'],'disputed')
        state,_,_=maintain(state,[reassessment(state,[subject])])
        self.assertEqual(self.query(state).lookup(subject)['current_assessment']['status'],'agreed')

    def test_grouped_dependency_and_premise_self_support_are_rejected(self):
        subjects=ids(self.state,'claims')
        state=copy.deepcopy(self.state)
        evidence=state['evidence/'+state['claims/'+subjects[0]+'.yaml']['evidence_ids'][0]+'.yaml']
        evidence['premise_claim_ids']=[subjects[1]]
        with self.assertRaisesRegex(Invalid,'grouped evidential self-validation'):
            maintain(state,[comparison(subjects)])
        state=copy.deepcopy(self.state)
        rid='R-'+'f'*32;path='graph/'+rid+'.yaml'
        state[path]=dict(id=rid,type='dependency',spec='structural:weak:inward',reason='Synthetic fixture.',
            uncertainty='high',evidence_ids=ids(state,'evidence')[:1],state='active',**{'from':subjects[0],'to':subjects[1]})
        mid='M-'+'e'*32
        state['maintenance/'+mid+'.yaml']=dict(schema_version='1.0',id=mid,status='completed',
            base_commit='a'*40,created_at='2026-01-01T12:00:00Z',claim_ids=subjects,reviewed_claim_ids=subjects,
            touched_files=[path],findings=['Synthetic fixture.'],deferred=[],no_change_reason=None)
        with self.assertRaisesRegex(Invalid,'Equivalence creates a self-connector'):
            maintain(state,[comparison(subjects)])

    def test_non_equivalence_and_history_branches_are_rejected_on_join(self):
        state=copy.deepcopy(self.state)
        p=contribution(token='3'*32);p['claims'][0]['statement']='A third synthetic wording says seven.'
        state.update(state_for(p));state.update(plan_admission(state,p['id'],decisions(p),ROOT))
        a,b,c=ids(state,'claims')
        for outcome in ('overlap','distinct','unresolved'):
            ops=[comparison([a,b],identity='ab'),comparison([b,c],identity='bc'),comparison([a,c],outcome,identity='ac')]
            with self.assertRaisesRegex(Invalid,'Non-equivalent records'):
                maintain(state,ops)
        state,_,_=maintain(state,[comparison([a,b])])
        with self.assertRaisesRegex(Invalid,'already has a decision'):
            maintain(state,[comparison([a,b],'distinct')],token='b')
        prior='M-'+'a'*32+'#compare1'
        state,_,_=maintain(state,[comparison([a,b],'distinct',supersedes=prior)],token='b')
        with self.assertRaisesRegex(Invalid,'history branches'):
            maintain(state,[comparison([a,b],'overlap',supersedes=prior)],token='c')

    def test_delta_rechecks_selected_reads_but_allows_unrelated_base_change(self):
        subjects=ids(self.state,'claims')
        proposal,_,_=maintain(self.state,[comparison(subjects)])
        for selected in (False,True):
            base=copy.deepcopy(self.state);state=copy.deepcopy(proposal)
            path=('claims/'+subjects[0]+'.yaml') if selected else ('sources/'+ids(base,'sources')[0]+'.yaml')
            field='statement' if selected else 'title'
            base[path][field]+=' Synthetic concurrent edit.';state[path]=copy.deepcopy(base[path])
            with tempfile.TemporaryDirectory() as a,tempfile.TemporaryDirectory() as b:
                before,after=Path(a),Path(b);write_state(before,base);write_state(after,state)
                if selected:
                    with self.assertRaisesRegex(Invalid,'Stale model operation read'):
                        validate_delta(after,before,state)
                else:
                    validate_delta(after,before,state)

    def test_repeated_research_groups_records_and_preserves_every_run(self):
        first=contribution()
        first['questions']=[dict(id='q1',question='What is the synthetic value?',claim_ids=['c1'])]
        state=admitted(first)
        for token in ('2','3'):
            p=copy.deepcopy(first);p['id']='RUN-'+token*32
            state.update(state_for(p))
            d=decisions(p)
            changes=plan_admission(state,p['id'],d,ROOT)
            state.update(changes)
            self.assertEqual(plan_admission(state,p['id'],d,ROOT),{})
        counts=validate_state(state,ROOT,True)
        self.assertEqual(counts['claims'],1)
        operations=[]
        for kind in ('sources','evidence','questions'):
            self.assertEqual(counts[kind],3)
            members=ids(state,kind)
            operations.extend(comparison([members[0],m],identity=kind+str(i)) for i,m in enumerate(members[1:]))
        state,_,_=maintain(state,operations)
        self.assertEqual(counts['submission'],3)
        q=self.query(state)
        history=q.assessments(ids(state,'claims')[0])
        self.assertEqual(history['total'],3)
        self.assertEqual(history['current_uncertainty'],'high')
        for kind in ('sources','evidence','questions'):
            self.assertEqual(q.search(kind=kind)['total'],1)
            for member in ids(state,kind):
                self.assertEqual(q.lookup(member)['record'],state[kind+'/'+member+'.yaml'])
                self.assertEqual(q.lookup(member,level=2)['equivalence_group']['members']['total'],3)
        view=q.lookup(ids(state,'claims')[0],level=2)
        for kind in ('sources','evidence','questions'):
            self.assertEqual(view['related'][kind]['total'],1)
        self.assertEqual(sum(item['path'].startswith('input-artefacts/') for item in view['provenance']['items']),3)

    def test_known_scope_class_and_origin_differences_prevent_grouping(self):
        state=copy.deepcopy(self.state)
        subjects=ids(state,'claims')
        state['claims/'+subjects[1]+'.yaml']['class']='assumption'
        with self.assertRaisesRegex(Invalid,'same class and temporal scope'):
            maintain(state,[comparison(subjects)])
        sources=ids(self.state,'sources')
        state=copy.deepcopy(self.state)
        state['sources/'+sources[1]+'.yaml']['locator']='A different independent observation.'
        with self.assertRaisesRegex(Invalid,'anchored passage'):
            maintain(state,[comparison(sources)])
        with self.assertRaisesRegex(Invalid,'origins, independence and joint premises'):
            maintain(self.state,[comparison(ids(self.state,'evidence'))])

    def test_stale_snapshot_and_out_of_scope_write_are_rejected(self):
        subjects=ids(self.state,'claims')
        pending,_,d=maintain(self.state,[reassessment(self.state,subjects)],apply=False)
        pending['claims/'+subjects[0]+'.yaml']['statement']+=' Synthetic changed scope.'
        with self.assertRaisesRegex(Invalid,'Stale model snapshot'):
            plan_maintenance(pending,'M-'+'a'*32,d,ROOT)
        with self.assertRaisesRegex(Invalid,'outside the selected maintenance'):
            maintain(self.state,[reassessment(self.state,subjects)],seeds=[subjects[0]])

    def test_linkage_uses_existing_types_and_cycle_validation(self):
        subjects=ids(self.state,'claims')
        def link(identity,ends):
            record=dict(id='R-'+identity*32,type='dependency',spec='structural:strong:inward',
                        reason='Synthetic supplied dependency.',uncertainty='high',state='active',
                        evidence_ids=[ids(self.state,'evidence')[0]],**{'from':ends[0],'to':ends[1]})
            return dict(id='link'+identity,kind='linkage',subject_ids=ends,reason=record['reason'],
                        basis_ids=ends,record=record,previous_sha256=None)
        state,_,_=maintain(self.state,[link('1',subjects)])
        self.assertEqual(len(ids(state,'graph')),1)
        with self.assertRaisesRegex(Invalid,'Circular dependency'):
            maintain(state,[link('2',list(reversed(subjects)))],token='b')
        operation=link('2',subjects);operation['record']['type']='contradiction'
        with self.assertRaises(Invalid):
            maintain(state,[operation],token='b')

    def test_bad_fields_unknown_ids_and_forged_history_fail(self):
        operation=comparison(ids(self.state,'claims'))
        for mutate in (lambda op:op.update(extra=True), lambda op:op.update(subject_ids=['C-'+'f'*32,op['subject_ids'][0]]),
                       lambda op:op.update(id=[]), lambda op:op.update(basis_ids=None),lambda op:op.update(outcome='similar_enough')):
            bad=copy.deepcopy(operation);mutate(bad)
            with self.assertRaises(Invalid):
                maintain(self.state,[bad])
        state,_,_=maintain(self.state,[reassessment(self.state,ids(self.state,'claims'),'medium')])
        for s in ids(state,'claims'):
            state['maintenance/M-'+'a'*32+'.yaml']['model_operations'][0]['previous_uncertainty'][s]='low'
        with tempfile.TemporaryDirectory() as a,tempfile.TemporaryDirectory() as b:
            before,after=Path(a),Path(b)
            write_state(before,self.state);write_state(after,state)
            with self.assertRaisesRegex(Invalid,'actual base assessment'):
                validate_delta(after,before,state)

    def test_new_retirement_is_rejected_but_legacy_remains_readable(self):
        state=copy.deepcopy(self.state)
        subject=ids(state,'claims')[0];path='claims/'+subject+'.yaml'
        state[path]['state']='retired'
        mid='M-'+'d'*32
        state['maintenance/'+mid+'.yaml']=dict(schema_version='1.0',id=mid,status='completed',
            base_commit='a'*40,created_at='2026-01-01T12:00:00Z',claim_ids=[subject],reviewed_claim_ids=[subject],
            touched_files=[path],findings=['Synthetic legacy record.'],deferred=[],no_change_reason=None)
        self.assertEqual(self.query(state).lookup(subject)['record']['state'],'retired')
        with tempfile.TemporaryDirectory() as a,tempfile.TemporaryDirectory() as b:
            before,after=Path(a),Path(b);write_state(before,self.state);write_state(after,state)
            with self.assertRaisesRegex(Invalid,'claim-retirement'):
                validate_delta(after,before,state)

    def test_bounded_context_and_unicode_passages_are_complete(self):
        p=contribution();p['sources'][0]['excerpt']='Synthetic 🙂 \\ " quotation\n'*8000
        state=admitted(p)
        q=self.query(state)
        source=ids(state,'sources')[0]
        text,offset='',0
        while True:
            result=q.passage(source,field='excerpt',offset=offset,max_bytes=2048)
            self.assertLessEqual(len(json_bytes(result)),2048)
            text+=result['text']
            if result['next_offset'] is None:break
            self.assertGreater(result['next_offset'],offset);offset=result['next_offset']
        self.assertEqual(text,p['sources'][0]['excerpt'])
        subject=ids(state,'claims')[0]
        for purpose in ('comparison','linkage','reassessment'):
            result=q.context(subject,purpose=purpose,limit=1)
            self.assertEqual(len(result['items']),1)
            self.assertIsNotNone(result['next_offset'])
            self.assertEqual(result['model_sha256'],model_digest(state))
            self.assertLessEqual(len(json_bytes(result)),32768)

    def test_large_enumeration_is_paged_and_never_implies_identity(self):
        p=contribution();p['claims']=[];p['handoff']['no_claims_reason']='Synthetic question enumeration.'
        p['questions']=[dict(id='q'+str(n),question='Synthetic same-looking question '+str(n)+'?',claim_ids=[]) for n in range(1500)]
        q=self.query(admitted(p))
        first=q.candidates(kind='questions')
        self.assertEqual(first['total'],1500)
        self.assertEqual(len(first['items']),20)
        self.assertLessEqual(len(json_bytes(first)),32768)
        second=q.candidates(kind='questions',offset=first['next_offset'])
        self.assertFalse({r['id'] for r in first['items']} & {r['id'] for r in second['items']})

    def test_lineage_is_bounded_by_default_and_flags_expand(self):
        q=self.query(self.state)
        result=q.lineage(limit=1)
        self.assertEqual(len(result['items']),1)
        self.assertIsNotNone(result['next_offset'])
        self.assertLessEqual(len(json_bytes(result)),32768)
        flags=q.lineage(limit=None)['flags']
        for flag in flags:
            result=q.lineage_flag(flag['id'],limit=1)
            self.assertLessEqual(len(result['items']),1)
            self.assertEqual(result['independence_assessment'],'unresolved')

    def test_recent_changes_include_accepted_model_results(self):
        state,_,_=maintain(self.state,[comparison(ids(self.state,'claims'))])
        after=self.query(state)
        # No canonical record changed: the comparison is itself permanent model provenance.
        package=QueryFixture(self.state);self.addCleanup(package.temp.cleanup)
        result=after.changes(package.package)
        self.assertEqual([r['kind'] for r in result['items']],['comparison'])


if __name__=='__main__':unittest.main()
