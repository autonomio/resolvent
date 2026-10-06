"""Synthetic software fixtures only; never seed claims for a real world model."""
from __future__ import annotations
import copy,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from scripts.model import Invalid,load_state,read_data,validate_delta,validate_state
from scripts.world_control import apply_changes,canonical_id,plan_admission

def contribution(method='research',token='1'*32):
 p={'schema_version':'1.0','id':'RUN-'+token,'input_method':method,'created_at':'2026-01-01T12:00:00Z',
    'researcher':'synthetic-test-fixture','title':'Synthetic software test, not research','scope':'Unit tests only',
    'origin':{'mode':'live','coverage':'not_applicable','limitations':[]},'parent_run_id':None,
    'brief':{'question':'What does the synthetic fixture say?','assumption_to_test':'The fixture is internally consistent.',
             'evidence_requirements':['Inspect the synthetic fixture.'],'questions':['Is the fixture internally consistent?'],
             'acceptance_criteria':[{'id':'ac1','criterion':'The fixture has a precise excerpt.'}],'created_before_research':True},
    'result':{'summary':'Synthetic fixture for software tests.','acceptance_outcomes':[{'criterion_id':'ac1','result':'pass','notes':'Fixture inspected.'}],
              'limitations':['Not empirical research.'],'artifacts':[]},
    'sources':[{'id':'s1','kind':'conversation','title':'Synthetic fixture','uri':None,'date':'2026-01-01','locator':'Test fixture, line 1',
                'excerpt':'A synthetic value is 7.','access':'inspected'}],
    'evidence':[{'id':'e1','kind':'statement','summary':'Synthetic reported statement, not independent evidence.','source_ids':['s1'],
                 'independent':False,'limitations':['Synthetic.'],'premise_claim_ids':[]}],
    'claims':[{'id':'c1','class':'hypothesis','statement':'The synthetic fixture value is 7.','uncertainty':'high','evidence_ids':['e1']}],
    'connectors':[],'questions':[],'handoff':{'summary':'Synthetic candidate for tests.','no_claims_reason':None,'suggested_follow_up':[]},'method_metadata':{}}
 if method!='research':p['brief']=None;p['result']['acceptance_outcomes']=[]
 if method=='conversation':p['origin']={'mode':'retrospective','coverage':'complete','limitations':[]};p['method_metadata']={'new_research_performed':False}
 elif method=='interview':p['sources'][0]['kind']='interview';p['method_metadata']={'participants':['Synthetic person'],'interview_date':'2026-01-01'}
 elif method=='simulation':p['sources'][0]['kind']='simulation';p['evidence'][0]['kind']='simulation';p['method_metadata']={'spec_id':'test','spec_version':'1','run_id':'test','parameters':{}}
 elif method=='liminal_research':
  p['sources'][0]['kind']='reasoning';p['evidence'][0]['kind']='assumption';p['claims'][0]['class']='assumption'
  p['method_metadata']={'topic':'Synthetic','perspective':'Testing','stage_outputs':['Synthetic stage summary'],'external_search_performed':False,'world_model_read_during_generation':False}
 return p

def decisions(p,action='accept'):
 return {'claims':{c['id']:{'action':action,'reason':'Synthetic software-test decision.'} for c in p['claims']},
         'connection_review':({c['id']:{'considered_claim_ids':[],'outcome':'no_justified_connection','reason':'Synthetic isolated fixture.'} for c in p['claims']} if action in ('accept','merge') else {}),'follow_up_gaps':[]}
def state_for(p):return {f"input-artefacts/{p['id']}.json":p}
def admitted(p=None):
 p=p or contribution();s=state_for(p);s.update(plan_admission(s,p['id'],decisions(p),ROOT));return s
def write_state(root,state):
 for path,record in state.items():
  p=root/path;p.parent.mkdir(parents=True,exist_ok=True)
  if p.suffix=='.json':p.write_text(json.dumps(record,indent=2)+'\n')
  else:apply_changes(root,{path:record})

class ModelTests(unittest.TestCase):
 def test_empty(self):self.assertEqual(validate_state({},ROOT,True),{})
 def test_proposal_not_admitted(self):
  s=state_for(contribution());validate_state(s,ROOT)
  with self.assertRaisesRegex(Invalid,'Awaiting admission'):validate_state(s,ROOT,True)
 def test_direct_routes(self):
  for route in ['research','conversation','interview','source_material','simulation','liminal_research']:
   with self.subTest(route=route):self.assertEqual(validate_state(admitted(contribution(route)),ROOT,True)['claims'],1)
 def test_intra_model_route(self):
  s=admitted();cid=canonical_id('RUN-'+'1'*32,'claims','c1');p=contribution('intra_model','2'*32)
  p['claims'][0]['statement']='A second synthetic claim follows from the first.';p['sources'][0]['kind']='model';p['evidence'][0]['kind']='derivation'
  p['evidence'][0]['premise_claim_ids']=[cid];p['method_metadata']={'source_claim_ids':[cid],'source_commit':'a'*40}
  s.update(state_for(p));s.update(plan_admission(s,p['id'],decisions(p),ROOT));self.assertEqual(validate_state(s,ROOT,True)['claims'],2)
 def test_research_three_artifacts(self):
  s=admitted()
  for root in ['briefs/open/done/','briefs/ready/','briefs/closed/']:self.assertTrue(any(k.startswith(root) for k in s))
 def test_idempotence(self):
  p=contribution();self.assertEqual(plan_admission(admitted(p),p['id'],decisions(p),ROOT),{})
 def test_duplicate_merges_without_confidence_upgrade(self):
  s=admitted();p=contribution('research','2'*32);p['claims'][0]['uncertainty']='medium';s.update(state_for(p));s.update(plan_admission(s,p['id'],decisions(p),ROOT))
  self.assertEqual(validate_state(s,ROOT,True)['claims'],1);c=next(v for k,v in s.items() if k.startswith('claims/'))
  self.assertEqual(c['uncertainty'],'high');self.assertEqual(len(c['evidence_ids']),2)
 def test_concurrent_ids(self):self.assertNotEqual(canonical_id('RUN-'+'1'*32,'claims','c1'),canonical_id('RUN-'+'2'*32,'claims','c1'))
 def test_zero_claims(self):
  p=contribution();p['claims']=[];p['handoff']['no_claims_reason']='Inconclusive test.';self.assertNotIn('claims',validate_state(admitted(p),ROOT,True))
 def test_zero_claims_require_reason(self):
  p=contribution();p['claims']=[]
  with self.assertRaisesRegex(Invalid,'zero-claim'):validate_state(state_for(p),ROOT)
 def test_rejected_claim(self):
  p=contribution();s=state_for(p);s.update(plan_admission(s,p['id'],decisions(p,'reject'),ROOT));self.assertNotIn('claims',validate_state(s,ROOT,True))
 def test_missing_disposition(self):
  p=contribution();d=decisions(p);d['claims']={}
  with self.assertRaisesRegex(Invalid,'every candidate'):plan_admission(state_for(p),p['id'],d,ROOT)
 def test_missing_connection_review(self):
  p=contribution();d=decisions(p);d['connection_review']={}
  with self.assertRaisesRegex(Invalid,'connection assessment'):plan_admission(state_for(p),p['id'],d,ROOT)
 def test_chat_no_new_research(self):
  p=contribution('conversation');p['method_metadata']['new_research_performed']=True
  with self.assertRaisesRegex(Invalid,'prohibit new research'):validate_state(state_for(p),ROOT)
 def test_partial_chat(self):
  p=contribution('conversation');p['origin']['coverage']='partial'
  with self.assertRaisesRegex(Invalid,'Partial chat'):validate_state(state_for(p),ROOT)
  p['origin']['limitations']=['Earlier messages unavailable.'];validate_state(state_for(p),ROOT)
 def test_chat_no_fabricated_brief(self):
  p=contribution('conversation');p['brief']=contribution()['brief']
  with self.assertRaisesRegex(Invalid,'fabricate'):validate_state(state_for(p),ROOT)
 def test_research_criterion_coverage(self):
  p=contribution();p['result']['acceptance_outcomes']=[]
  with self.assertRaisesRegex(Invalid,'Every acceptance criterion'):validate_state(state_for(p),ROOT)
 def test_low_uncertainty_needs_evidence(self):
  p=contribution();p['claims'][0]['uncertainty']='low'
  with self.assertRaisesRegex(Invalid,'independent inspected evidence'):validate_state(state_for(p),ROOT)
 def test_chat_not_independent(self):
  p=contribution();p['evidence'][0].update(independent=True,kind='external')
  with self.assertRaisesRegex(Invalid,'inspected, addressable external'):validate_state(state_for(p),ROOT)
 def test_unretrieved_not_independent(self):
  p=contribution();p['evidence'][0].update(independent=True,kind='external');p['sources'][0].update(kind='web',uri='https://example.invalid/fixture',access='not_retrieved')
  with self.assertRaisesRegex(Invalid,'inspected, addressable external'):validate_state(state_for(p),ROOT)
 def test_liminal_cap(self):
  p=contribution('liminal_research');p['claims'][0]['uncertainty']='medium'
  with self.assertRaisesRegex(Invalid,'capped'):validate_state(state_for(p),ROOT)
 def test_missing_evidence(self):
  p=contribution();p['claims'][0]['evidence_ids']=['missing']
  with self.assertRaisesRegex(Invalid,'unresolved evidence'):validate_state(state_for(p),ROOT)
 def test_backlinks(self):
  s=admitted();next(v for k,v in s.items() if k.startswith('evidence/'))['claim_ids']=[]
  with self.assertRaisesRegex(Invalid,'backlink'):validate_state(s,ROOT)
 def cyclic(self,kind):
  p=contribution();c=copy.deepcopy(p['claims'][0]);c.update(id='c2',statement='Another synthetic value is 9.');p['claims'].append(c)
  p['connectors']=[{'id':rid,'from':a,'to':b,'type':kind,'spec':'structural:strong:inward','reason':'Synthetic relationship.',
                    'uncertainty':'high','evidence_ids':['e1']} for rid,a,b in [('r1','c1','c2'),('r2','c2','c1')]]
  return p
 def test_dependency_cycle(self):
  p=self.cyclic('dependency')
  with self.assertRaisesRegex(Invalid,'Circular dependency'):plan_admission(state_for(p),p['id'],decisions(p),ROOT)
 def test_coupling_cycles_allowed(self):validate_state(admitted(self.cyclic('coupling')),ROOT,True)
 def test_circular_evidence(self):
  p=contribution();p['evidence'][0]['premise_claim_ids']=['c1']
  with self.assertRaisesRegex(Invalid,'self-validation'):plan_admission(state_for(p),p['id'],decisions(p),ROOT)
 def test_stale_closure(self):
  s=admitted();s['input-artefacts/RUN-'+'1'*32+'.json']['title']='Changed after admission'
  with self.assertRaisesRegex(Invalid,'closure is stale'):validate_state(s,ROOT)
 def test_bad_closure_counts(self):
  s=admitted();next(v for k,v in s.items() if k.startswith('briefs/closed/'))['counts']['created_claims']=999
  with self.assertRaisesRegex(Invalid,'counts disagree'):validate_state(s,ROOT)
 def test_pending_maintenance(self):
  s=admitted();cid=canonical_id('RUN-'+'1'*32,'claims','c1');mid='M-'+'3'*32
  m={'schema_version':'1.0','id':mid,'status':'pending','base_commit':'a'*40,'created_at':'2026-01-01T12:00:00Z','claim_ids':[cid],
     'reviewed_claim_ids':[],'touched_files':[],'findings':[],'deferred':[],'no_change_reason':None};s[f'maintenance/{mid}.yaml']=m
  with self.assertRaisesRegex(Invalid,'Awaiting maintenance'):validate_state(s,ROOT,True)
  m.update(status='completed',reviewed_claim_ids=[cid],no_change_reason='No justified change in test.');validate_state(s,ROOT,True)
 def test_duplicate_keys(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'bad.yaml';p.write_text('id: first\nid: second\n')
   with self.assertRaisesRegex(Invalid,'Duplicate mapping key'):read_data(p)
 def test_yaml_aliases(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'bad.yaml';p.write_text('a: &ref [1]\nb: *ref\n')
   with self.assertRaisesRegex(Invalid,'anchors and aliases'):read_data(p)
 def test_nonfinite_json(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'bad.json';p.write_text('{"x":NaN}')
   with self.assertRaisesRegex(Invalid,'Non-finite'):read_data(p)
 def test_symlink(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'target.json';p.write_text('{}');link=Path(d)/'link.json';link.symlink_to(p)
   with self.assertRaisesRegex(Invalid,'Symlinks'):read_data(link)
 def test_actual_delta_and_mixed_governance(self):
  with tempfile.TemporaryDirectory() as a,tempfile.TemporaryDirectory() as b:
   base,root=Path(a),Path(b);s=admitted();write_state(root,s);validate_delta(root,base,s);(root/'AGENTS.md').write_text('Change rules.')
   with self.assertRaisesRegex(Invalid,'Separate governance'):validate_delta(root,base,s)
 def test_unrecorded_edit(self):
  with tempfile.TemporaryDirectory() as a,tempfile.TemporaryDirectory() as b:
   base,root=Path(a),Path(b);s=admitted();write_state(base,s);write_state(root,s);path=next(k for k in s if k.startswith('claims/'))
   s[path]['uncertainty']='medium';write_state(root,{path:s[path]})
   with self.assertRaisesRegex(Invalid,'Unrecorded'):validate_delta(root,base,s)
 def test_registry(self):
  registry=read_data(ROOT/'docs/contracts/governance/contract_registry.json')
  self.assertEqual(set(registry['routes']),{'research','conversation','interview','source_material','simulation','intra_model','liminal_research'})
  for filename in set(registry['routes'].values())|set(registry['shared'])|set(registry['research_phases']):self.assertTrue((ROOT/'docs/contracts/activity'/filename).is_file(),filename)

if __name__=='__main__':unittest.main()
