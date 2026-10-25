"""Real local Git remotes and a fake GitHub provider; no external writes."""
from datetime import timedelta
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

from scripts.change_signals import workset_id
from scripts.model import Invalid
from scripts.signal_contract import signal_id
from scripts.signal_maintenance import model_signal, publish
from test_change_signals import NOW
from test_model import write_state
from test_query_knowledge import query_state


class Provider:
    def __init__(self):
        self.calls=[];self.previous=[];self.pending=[];self.fail=None
        self.metadata={'is_template':False,'default_branch':'main'}

    def __call__(self,*args,payload=None):
        self.calls.append((args,payload))
        if args[:2]==('api','repos/example/world'):
            return self.metadata
        if args[:2]==('pr','list'):
            return self.previous if '--head' in args else self.pending
        if args[:3]==('api','--method','POST'):
            if self.fail=='create':
                raise subprocess.CalledProcessError(1,['gh','api'])
            self.previous=[{'state':'OPEN','url':'https://github.com/example/world/pull/1'}]
            return {'html_url':self.previous[0]['url']}
        if args[:2]==('workflow','run'):
            if self.fail=='dispatch':
                raise subprocess.CalledProcessError(1,['gh','workflow'])
            return None
        raise AssertionError(args)


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'world';self.root.mkdir()
        self.remote=Path(self.temp.name)/'remote.git'
        subprocess.run(['git','init','--bare','-q',str(self.remote)],check=True)
        self.git('init','-q','--initial-branch=main')
        (self.root/'.gitignore').write_text('.resolvent/\n')
        self.commit('Synthetic empty world')
        self.before=self.git('rev-parse','HEAD')
        write_state(self.root,query_state())
        self.commit('Synthetic admitted model')
        self.revision=self.git('rev-parse','HEAD')
        self.git('remote','add','origin',str(self.remote))
        self.git('push','-q','origin','HEAD:main')
        self.api=Provider()

    def git(self,*args):
        return subprocess.check_output(['git','-C',str(self.root),*args],text=True).strip()

    def commit(self,message):
        self.git('add','.')
        self.git('-c','user.name=Synthetic test','-c','user.email=test@example.invalid','commit','-qm',message)

    def branch(self):
        event=model_signal(self.root,'example/world')
        return 'resolvent/maintenance/'+workset_id(self.revision,signal_id(event))

    def clean_retry(self):
        self.git('reset','--hard','-q','HEAD')

    def test_new_admitted_run_creates_only_a_pending_record_and_ready_pr(self):
        event=model_signal(self.root,'example/world')
        self.assertEqual(event['before_revision'],self.before)
        self.assertEqual(event['revision'],self.revision)
        self.assertEqual(event['affected_ids'],[])
        result=publish(self.root,'example/world',api=self.api,now=NOW)
        self.assertEqual(result['status'],'pr_created')
        branch=self.branch()
        self.git('fetch','-q','origin',branch)
        self.assertEqual(self.git('rev-parse','HEAD'),self.revision)
        self.assertEqual(self.git('rev-parse','FETCH_HEAD^'),self.revision)
        changed=self.git('diff','--name-only',self.revision,'FETCH_HEAD').splitlines()
        self.assertEqual(changed,['maintenance/'+result['workset_id']+'.yaml'])
        body=self.git('show','FETCH_HEAD:'+changed[0])
        self.assertIn('status: pending',body)
        create=[payload for args,payload in self.api.calls if args[:3]==('api','--method','POST')]
        self.assertEqual(len(create),1)
        self.assertFalse(create[0]['draft'])
        self.assertEqual(create[0]['base'],'main')
        self.assertNotIn('merge',[part for args,_ in self.api.calls for part in args])

    def test_failed_creation_reuses_original_remote_commit_without_overwrite(self):
        self.api.fail='create'
        with self.assertRaises(subprocess.CalledProcessError):
            publish(self.root,'example/world',api=self.api,now=NOW)
        branch=self.branch()
        original=self.git('ls-remote','origin','refs/heads/'+branch)
        self.clean_retry();self.api.fail=None
        result=publish(self.root,'example/world',api=self.api,now=NOW+timedelta(seconds=30))
        self.assertEqual(result['status'],'pr_created')
        self.assertEqual(self.git('ls-remote','origin','refs/heads/'+branch),original)

    def test_dispatch_failure_and_closed_pr_replays_do_not_create_another_pr(self):
        self.api.fail='dispatch'
        with self.assertRaises(subprocess.CalledProcessError):
            publish(self.root,'example/world',api=self.api,now=NOW)
        self.clean_retry();self.api.fail=None
        self.assertEqual(publish(self.root,'example/world',api=self.api,now=NOW)['status'],'duplicate_pr')
        self.api.previous[0]['state']='CLOSED'
        self.assertEqual(publish(self.root,'example/world',api=self.api,now=NOW)['status'],'duplicate_pr')
        self.assertEqual(sum(args[:3]==('api','--method','POST') for args,_ in self.api.calls),1)

    def test_existing_weekly_workset_and_stale_head_defer_without_writes(self):
        self.api.pending=[{'headRefName':'resolvent/maintenance/M-'+'1'*32,'url':'synthetic'}]
        self.assertEqual(publish(self.root,'example/world',api=self.api,now=NOW)['status'],'deferred_pending_workset')
        self.assertEqual(self.git('status','--porcelain'),'')
        (self.root/'README.md').write_text('Synthetic new main.\n');self.commit('Advance')
        self.git('push','-q','origin','HEAD:main');self.git('reset','--hard','-q',self.revision)
        self.assertEqual(publish(self.root,'example/world',api=self.api,now=NOW)['status'],'deferred_stale_revision')

    def test_template_and_governance_or_maintenance_only_merges_do_not_loop(self):
        self.api.metadata['is_template']=True
        self.assertEqual(publish(self.root,'example/world',api=self.api,now=NOW)['status'],'skipped_template')
        (self.root/'README.md').write_text('Synthetic governance-only change.\n');self.commit('Governance')
        self.assertIsNone(model_signal(self.root,'example/world'))
        self.assertEqual(publish(self.root,'example/world',api=self.api,now=NOW)['status'],'skipped_no_new_contribution')
        self.assertEqual(self.git('status','--porcelain'),'')

    def test_unfamiliar_remote_branch_is_never_overwritten(self):
        branch=self.branch()
        self.git('push','-q','origin',self.before+':refs/heads/'+branch)
        original=self.git('ls-remote','origin','refs/heads/'+branch)
        with self.assertRaisesRegex(Invalid,'original workset'):
            publish(self.root,'example/world',api=self.api,now=NOW)
        self.assertEqual(self.git('ls-remote','origin','refs/heads/'+branch),original)
        self.assertFalse(any(args[:3]==('api','--method','POST') for args,_ in self.api.calls))

    def test_privileged_trigger_uses_validated_main_and_the_existing_maintenance_lane(self):
        root=Path(__file__).resolve().parent.parent
        workflow=yaml.load((root/'.github/workflows/signal-maintenance.yml').read_text(),Loader=yaml.BaseLoader)
        weekly=yaml.load((root/'.github/workflows/maintenance.yml').read_text(),Loader=yaml.BaseLoader)
        self.assertEqual(set(workflow['on']),{'workflow_run'})
        self.assertEqual(workflow['on']['workflow_run'],{
            'workflows':['Resolvent validation'],'types':['completed'],'branches':['main']})
        self.assertEqual(workflow['concurrency'],weekly['concurrency'])
        self.assertEqual(workflow['permissions'],weekly['permissions'])
        job=workflow['jobs']['prepare']
        for guard in ("vars.RESOLVENT_CHANGE_SIGNALS == 'true'","workflow_run.event == 'push'",
                      "workflow_run.conclusion == 'success'",'workflow_run.head_repository.full_name == github.repository'):
            self.assertIn(guard,job['if'])
        checkout=job['steps'][0]['with']
        self.assertEqual(checkout['ref'],'${{ github.event.workflow_run.head_sha }}')
        self.assertEqual(checkout['fetch-depth'],'0')
        self.assertIn('schedule',weekly['on'])
        self.assertIn('workflow_dispatch',weekly['on'])


if __name__=='__main__':
    unittest.main()
