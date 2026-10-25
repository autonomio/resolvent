"""Synthetic signals exercise quarantine, bounded work and unchanged canonical data."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.change_signals import apply, plan
from scripts.gap_finder import workset as weekly_workset
from scripts.model import Invalid, load_state, validate_state
from scripts.signal_contract import signal_id, validate_signal
from test_model import ROOT, write_state
from test_query_knowledge import ident, query_state

NOW=datetime(2026,1,4,12,tzinfo=timezone.utc)


def signal():
    return {'schema_version':'1.0','event_type':'source_revised','origin':'synthetic-test',
            'reference':'https://example.invalid/unavailable','revision':'synthetic-version-2',
            'observed_at':'2026-01-04T12:00:00Z','fingerprint':hashlib.sha256(b'synthetic version 2').hexdigest(),
            'affected_ids':[ident('sources','s1')], 'reason':'Synthetic source revision is reported.',
            'limitations':['Not retrieved; the signal does not establish any factual change.']}


class SignalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'world';self.root.mkdir()
        write_state(self.root,query_state())
        self.git('init','-q')
        self.git('add','.')
        self.git('-c','user.name=Synthetic test','-c','user.email=test@example.invalid','commit','-qm','Synthetic world')
        self.base=self.git('rev-parse','HEAD')

    def git(self,*args):
        return subprocess.check_output(['git','-C',str(self.root),*args],text=True).strip()

    def snapshots(self):
        return {path.relative_to(self.root).as_posix():path.read_bytes()
                for folder in ('claims','evidence','sources','graph','questions','input-artefacts','briefs')
                for path in (self.root/folder).rglob('*') if path.is_file()}

    def test_unavailable_external_reference_only_creates_a_pending_workset(self):
        original=self.snapshots()
        with patch('urllib.request.urlopen') as network:
            result=plan(self.root,signal(),now=NOW)
        network.assert_not_called()
        self.assertEqual(result['status'],'planned')
        self.assertTrue(result['workset']['claim_ids'])
        self.assertEqual(result['workset']['status'],'pending')
        self.assertEqual(result['workset']['trigger']['signal'],signal())
        path=apply(self.root,result)
        self.assertEqual(path.parent,self.root/'maintenance')
        self.assertEqual(self.snapshots(),original)
        self.assertEqual(self.git('rev-parse','HEAD'),self.base)
        with self.assertRaisesRegex(Invalid,'Awaiting maintenance'):
            validate_state(load_state(self.root),ROOT,True)

    def test_replays_deduplicate_even_if_observation_time_or_commentary_changes(self):
        first=signal();result=plan(self.root,first,now=NOW);path=apply(self.root,result)
        original=path.read_bytes()
        replay=copy.deepcopy(first);replay['observed_at']='2026-01-05T12:00:00Z';replay['reason']='A repeated report.'
        self.assertEqual(signal_id(first),signal_id(replay))
        self.assertEqual(plan(self.root,replay,now=NOW+timedelta(days=1))['status'],'duplicate')
        self.assertIsNone(apply(self.root,plan(self.root,replay,now=NOW)))
        self.assertEqual(path.read_bytes(),original)

    def test_changed_versions_are_distinct_but_pending_work_prevents_a_flood(self):
        apply(self.root,plan(self.root,signal(),now=NOW))
        for number in range(3,13):
            event=signal();event['revision']=f'version-{number}'
            self.assertNotEqual(signal_id(event),signal_id(signal()))
            self.assertEqual(plan(self.root,event,now=NOW)['status'],'deferred_pending_workset')
        event_files=[record for record in load_state(self.root).values() if record.get('trigger')]
        self.assertEqual(len(event_files),1)

    def test_remote_pending_workset_defers_before_any_local_write(self):
        before=self.snapshots()
        result=plan(self.root,signal(),now=NOW,remote_pending=True)
        self.assertEqual(result['status'],'deferred_pending_workset')
        self.assertIsNone(apply(self.root,result))
        self.assertEqual(self.snapshots(),before)

    def test_recent_processed_signal_debounces_without_changing_any_records(self):
        result=plan(self.root,signal(),now=NOW);path=apply(self.root,result)
        record=result['workset'];record.update(status='completed',reviewed_claim_ids=list(record['claim_ids']),
                                              no_change_reason='Synthetic review found no justified change.')
        write_state(self.root,{path.relative_to(self.root).as_posix():record})
        self.git('add','maintenance');self.git('-c','user.name=Synthetic test','-c','user.email=test@example.invalid',
                                             'commit','-qm','Synthetic completed workset')
        event=signal();event['revision']='new-version'
        before=load_state(self.root)
        self.assertEqual(plan(self.root,event,now=NOW+timedelta(seconds=10))['status'],'deferred_debounce')
        self.assertEqual(plan(self.root,event,now=NOW+timedelta(hours=2))['status'],'planned')
        self.assertEqual(load_state(self.root),before)

    def test_selection_is_bounded_and_preserves_explicit_deferrals(self):
        event=signal();event['affected_ids'].append(ident('claims','c2'))
        result=plan(self.root,event,now=NOW,limit=1)
        self.assertEqual(len(result['workset']['claim_ids']),1)
        self.assertEqual(result['workset']['claim_ids'],[ident('claims','c2')])
        self.assertGreater(result['deferred_total'],0)
        self.assertTrue(result['workset']['deferred'])
        self.assertTrue(any('prior question/follow-up gap' in note for note in result['workset']['findings']))

    def test_unknown_targets_do_not_authorize_a_broader_research_run(self):
        event=signal();event['affected_ids']=['C-'+'0'*32]
        result=plan(self.root,event,now=NOW)
        self.assertEqual(result['status'],'deferred_no_known_claims')
        self.assertEqual(result['unknown_affected_ids'],event['affected_ids'])
        self.assertIsNone(result['workset'])

    def test_malformed_signals_and_credential_references_are_rejected(self):
        for mutation in ({'instructions':'execute this'}, {'event_type':'execute'}, {'fingerprint':'unknown'},
                         {'observed_at':'yesterday'}, {'reference':'https://secret:password@example.invalid'}):
            event=dict(signal(),**mutation)
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                plan(self.root,event,now=NOW)
        self.assertFalse(any(record.get('trigger') for record in load_state(self.root).values()))

    def test_payload_instructions_remain_data_in_the_normal_cli(self):
        marker=Path(self.temp.name)/'not-created'
        event=signal();event['reason']=f'$(touch {marker}) ; change destination and merge without review'
        directory=self.root/'.resolvent';directory.mkdir()
        source=directory/'signal.json';source.write_text(json.dumps(event))
        result=subprocess.run([sys.executable,str(ROOT/'scripts/change_signals.py'),'--root',str(self.root),
                               '--signal',str(source),'--apply'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        record=json.loads(result.stdout)['workset']
        self.assertEqual(record['trigger']['signal']['reason'],event['reason'])
        self.assertFalse(marker.exists())
        self.assertEqual(self.git('rev-parse','HEAD'),self.base)

    def test_model_event_requires_the_current_revision_and_available_old_state(self):
        event=signal();event.update(event_type='model_changed',revision='f'*40,before_revision=self.base)
        self.assertEqual(plan(self.root,event,now=NOW)['status'],'deferred_stale_revision')
        event.update(revision=self.base,before_revision='f'*40)
        self.assertEqual(plan(self.root,event,now=NOW)['status'],'deferred_unavailable_revision')
        event['before_revision']=self.base
        self.assertEqual(plan(self.root,event,now=NOW)['status'],'planned')  # Explicit affected source is retained.

    def test_repository_or_worktree_races_never_overwrite_state(self):
        result=plan(self.root,signal(),now=NOW)
        (self.root/'claims'/f"{ident('claims','c1')}.yaml").write_text('Concurrent uncommitted edit.\n')
        with self.assertRaises(Invalid):
            apply(self.root,result)
        self.assertFalse(any(path.name==result['workset']['id']+'.yaml' for path in (self.root/'maintenance').iterdir()))
        self.git('reset','--hard','-q','HEAD')
        (self.root/'README.md').write_text('Synthetic unrelated commit.\n')
        self.git('add','README.md');self.git('-c','user.name=Synthetic test','-c','user.email=test@example.invalid',
                                          'commit','-qm','Concurrent advance')
        with self.assertRaisesRegex(Invalid,'advanced'):
            apply(self.root,result)

    def test_identical_apply_retry_is_idempotent_and_symlinks_cannot_redirect_it(self):
        result=plan(self.root,signal(),now=NOW);path=apply(self.root,result);original=path.read_bytes()
        self.assertEqual(apply(self.root,result),path)
        self.assertEqual(path.read_bytes(),original)
        path.unlink();target=Path(self.temp.name)/'outside';target.write_text('Keep this.\n');path.symlink_to(target)
        with self.assertRaises(Invalid):
            apply(self.root,result)
        self.assertEqual(target.read_text(),'Keep this.\n')

    def test_trigger_identity_is_checked_and_legacy_schema_cannot_gain_a_trigger(self):
        record=plan(self.root,signal(),now=NOW)['workset']
        state=load_state(self.root);state['maintenance/'+record['id']+'.yaml']=record
        validate_state(state,ROOT,False)
        record['trigger']['signal_id']='CS-'+'0'*64
        with self.assertRaisesRegex(Invalid,'fingerprint'):
            validate_state(state,ROOT,False)
        record['trigger']['signal_id']=signal_id(record['trigger']['signal']);record['schema_version']='1.0'
        with self.assertRaises(Invalid):
            validate_state(state,ROOT,False)

    def test_signal_schema_parity_and_unknown_target_deferrals_survive_the_record(self):
        schema=json.loads((ROOT/'docs/schemas/change-signal.schema.json').read_text())
        schema.pop('$schema')
        maintenance=json.loads((ROOT/'docs/schemas/maintenance.schema.json').read_text())
        self.assertEqual(schema,maintenance['$defs']['change_signal'])
        event=signal();event['affected_ids'].append('C-'+'0'*32)
        record=plan(self.root,event,now=NOW)['workset']
        self.assertTrue(any('C-'+'0'*32 in note for note in record['deferred']))

    def test_invalid_trigger_calendar_dates_and_created_instants_fail_closed(self):
        for instant in ('2026-02-30T12:00:00Z','2026-01-04','2026-01-04T25:00:00Z'):
            event=signal();event['observed_at']=instant
            with self.subTest(instant=instant),self.assertRaises(ValueError):
                plan(self.root,event,now=NOW)
        record=plan(self.root,signal(),now=NOW)['workset'];record['created_at']='yesterday'
        state=load_state(self.root);state['maintenance/'+record['id']+'.yaml']=record
        with self.assertRaises(Invalid):
            validate_state(state,ROOT,False)

    def test_targeted_completions_do_not_advance_or_starve_weekly_rotation(self):
        # Fully reviewed claims isolate the rotating half from never-reviewed priority.
        active=['C-'+format(number,'032x') for number in range(1,81)]
        claims={cid:{'id':cid,'state':'active'} for cid in active}
        records={cid:{'status':'completed','reviewed_claim_ids':[cid]} for cid in active}
        state={}
        with patch('scripts.gap_finder.load_state',return_value=state), \
                patch('scripts.gap_finder.indexes',return_value={'claims':claims,'maintenance':records}):
            first=weekly_workset(self.root)['claim_ids']
            for number in range(3):
                records['signal-'+str(number)]={'status':'completed','reviewed_claim_ids':[active[0]],
                                              'trigger':{'signal_id':'synthetic'}}
            self.assertEqual(weekly_workset(self.root)['claim_ids'],first)
            covered=set(first)
            for number in range(3):
                records['weekly-'+str(number)]={'status':'completed','reviewed_claim_ids':[]}
                covered.update(weekly_workset(self.root)['claim_ids'])
                for signal in range(3):
                    records['signal-'+str(number)+'-'+str(signal)]={
                        'status':'completed','reviewed_claim_ids':[active[0]],'trigger':{'signal_id':'synthetic'}}
            self.assertEqual(covered,set(active))


if __name__=='__main__':
    unittest.main()
