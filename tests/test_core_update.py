"""Populated worlds and local remotes exercise guarded core upgrades without network."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import shutil
import tempfile
import unittest
from unittest.mock import patch

import yaml

from scripts import core_release, core_update
from scripts.build_knowledge import json_bytes
from scripts.model import DATA_ROOTS, Invalid, validate_state, load_state
from test_model import ROOT, write_state
from test_query_knowledge import query_state


class Provider:
    def __init__(self):
        self.calls=[];self.previous=[];self.pending=[];self.fail=None

    def __call__(self,*args,payload=None):
        self.calls.append((args,payload))
        if args==('api','repos/example/world'):
            return {'is_template':False,'default_branch':'main'}
        if args[:2]==('pr','list'):
            return self.previous if '--head' in args else self.pending
        if args[:3]==('api','--method','POST'):
            if self.fail=='create':
                raise subprocess.CalledProcessError(1,['gh','api'])
            self.previous=[{'state':'OPEN','url':'https://github.com/example/world/pull/1'}]
            self.pending=[{'headRefName':payload['head']}]
            return {'html_url':self.previous[0]['url']}
        if args[:2]==('workflow','run'):
            if self.fail=='dispatch':
                raise subprocess.CalledProcessError(1,['gh','workflow'])
            return None
        raise AssertionError(args)


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.upstream=Path(self.temp.name)/'upstream';self.upstream.mkdir()
        self.world=Path(self.temp.name)/'world';self.world.mkdir()
        self.remote=Path(self.temp.name)/'world.git'
        self.channel=Path(self.temp.name)/'upstream.git'
        for repo in (self.upstream,self.world):
            core_release.git(repo,'init','-q','--initial-branch=main')
        for repo in (self.remote,self.channel):
            core_release.git(Path(self.temp.name),'init','--bare','-q',str(repo))
        for name,content in {'scripts/compiler.py':b'# Synthetic baseline compiler.\n',
                             'scripts/retained.py':b'# Synthetic retained file.\n',
                             'scripts/removed.py':b'# Synthetic removable file.\n',
                             '.github/workflows/validate.yml':b'on: [pull_request, workflow_dispatch]\npermissions:\n  contents: read\njobs:\n  tests:\n    permissions:\n      contents: read\n    runs-on: ubuntu-latest\n    steps:\n      - run: python scripts/compiler.py --require-closure\n',
                             'docs/guide.md':b'Synthetic core guide.\n'}.items():
            path=self.upstream/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content)
        self.commit(self.upstream,'Synthetic core baseline')
        self.lock(self.upstream,'1.0.0');self.commit(self.upstream,'Synthetic core lock')
        self.v1=core_release.git(self.upstream,'rev-parse','HEAD').decode().strip()
        self.installed=core_release.checked_lock(self.upstream)
        for path in list(self.installed['files'])+[core_release.LOCK]:
            target=self.world/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((self.upstream/path).read_bytes())
        write_state(self.world,query_state())
        (self.world/'resolvent.yaml').write_text('project: Synthetic organization\n')
        (self.world/'docs'/'organization.md').write_text('Synthetic organization-owned material.\n')
        self.commit(self.world,'Synthetic populated world')
        self.base=core_release.git(self.world,'rev-parse','HEAD').decode().strip()
        core_release.git(self.world,'remote','add','origin',str(self.remote))
        core_release.git(self.world,'push','origin','HEAD:main')
        core_release.git(self.upstream,'remote','add','origin',str(self.channel))
        marker=Path(self.temp.name)/'candidate-must-not-execute'
        (self.upstream/'scripts/compiler.py').write_text('from pathlib import Path\nPath('+repr(str(marker))+').touch()\n')
        self.marker=marker
        (self.upstream/'scripts/removed.py').unlink()
        (self.upstream/'scripts/new.py').write_text('# Synthetic new core file.\n')
        self.lock(self.upstream,'1.1.0');self.commit(self.upstream,'Synthetic core upgrade')
        self.v2=core_release.git(self.upstream,'rev-parse','HEAD').decode().strip()
        self.candidate=core_release.checked_lock(self.upstream)
        self.index=core_release.release_index(self.upstream)
        core_release.git(self.upstream,'push','origin','HEAD:main')
        core_release.publish_channel(self.upstream,'autonomio/resolvent')
        core_release.git(self.world,'fetch',str(self.upstream),self.v2)

    def commit(self,repo,message):
        core_release.git(repo,'add','.')
        core_release.git(repo,'-c','user.name=Synthetic test','-c','user.email=test@example.invalid','commit','-qm',message)

    def lock(self,repo,version):
        core_release.git(repo,'add','.')
        tree=core_release.git(repo,'write-tree').decode().strip()
        (repo/core_release.LOCK).write_bytes(json_bytes({'format_version':'1.0','core_version':version,
                                                       'files':core_release.inventory(repo,tree)}))

    def local_fetch(self,root,*args,**kwargs):
        # Production calls must name the fixed public origin, never an event URL.
        if core_release.UPSTREAM in args:
            args=tuple(str(self.channel) if item==core_release.UPSTREAM else item for item in args)
            args=tuple('protocol.file.allow=always' if item=='protocol.file.allow=never' else item for item in args)
        return core_release.git(root,*args,**kwargs)

    def planned(self):
        return core_update.plan(self.world,self.v2,self.index)

    def test_upgrade_preserves_all_world_bytes_modes_config_and_unmanaged_files(self):
        plan=self.planned();commit=core_update.commit_plan(self.world,plan)
        before=core_update.tree_entries(self.world,self.base);after=core_update.tree_entries(self.world,commit)
        protected=[path for path in before if path.split('/')[0] in DATA_ROOTS or
                   path in ('resolvent.yaml','docs/organization.md')]
        self.assertTrue(protected)
        self.assertEqual({p:before[p] for p in protected},{p:after[p] for p in protected})
        self.assertNotIn('scripts/removed.py',after)
        self.assertIn('scripts/new.py',after)
        self.assertEqual(core_release.git(self.world,'status','--porcelain'),b'')
        self.assertEqual(core_release.git(self.world,'rev-parse','HEAD').decode().strip(),self.base)
        self.assertFalse(self.marker.exists())
        validate_state(load_state(self.world),ROOT,True)

    def test_release_inventory_stays_inside_the_v1_updater_namespace(self):
        # Frozen path policy shipped with core 1.0.0. A release must remain
        # readable before its new updater can itself be installed.
        roots={'.gitignore','AGENTS.md','CLAUDE.md','LICENSE','README.md',
               'plugin.json','pyproject.toml','requirements.txt'}
        prefixes={'.github','.agents','.claude-plugin','.codex-plugin','scripts',
                  'tests','docs','skills','workflows','assets','dist','verification'}
        lock=json.loads((ROOT/core_release.LOCK).read_text())
        for path in lock['files']:
            with self.subTest(path=path):
                self.assertTrue(path in roots or ('/' in path and path.split('/')[0] in prefixes))
        self.assertIn('dist/plugin/resolvent/mcp.json',lock['files'])
        self.assertIn('dist/plugin/resolvent/.mcp.json',lock['files'])

    def test_only_affected_local_core_edits_block_and_unaffected_edits_survive(self):
        retained=self.world/'scripts/retained.py';retained.write_text('# Local organization customization.\n')
        self.commit(self.world,'Local retained customization')
        plan=self.planned();commit=core_update.commit_plan(self.world,plan)
        self.assertEqual(core_release.git(self.world,'show',commit+':scripts/retained.py'),retained.read_bytes())
        (self.world/'scripts/compiler.py').write_text('# Local affected customization.\n')
        self.commit(self.world,'Local affected customization')
        with self.assertRaisesRegex(ValueError,'Locally modified'):
            self.planned()

    def test_new_upstream_path_never_overwrites_an_unmanaged_file_or_symlink(self):
        new=self.world/'scripts/new.py';new.write_text('Organization-owned file.\n')
        self.commit(self.world,'Organization file at new upstream path')
        with self.assertRaisesRegex(ValueError,'unmanaged'):
            self.planned()
        new.unlink();new.symlink_to('../resolvent.yaml');self.commit(self.world,'Organization symlink')
        with self.assertRaisesRegex(ValueError,'unmanaged'):
            self.planned()

    def test_data_paths_traversal_unsafe_blob_modes_and_bad_hashes_fail(self):
        item=next(iter(self.installed['files'].values()))
        for path in ('claims/C-'+'0'*32+'.yaml','resolvent.yaml','docs/../resolvent.yaml',
                     '/scripts/a.py','docs/.git/config','docs/a\nscript.py'):
            lock=copy.deepcopy(self.installed);lock['files'][path]=item
            with self.subTest(path=path),self.assertRaises(Invalid):
                core_release.validate_lock(lock)
        for mutation in ({'mode':'120000'},{'bytes':2**30},{'sha256':'unknown'}):
            lock=copy.deepcopy(self.installed);name=next(iter(lock['files']))
            lock['files'][name].update(mutation)
            with self.assertRaises(Invalid):
                core_release.validate_lock(lock)
        bad=dict(self.index,lock_sha256='0'*64)
        with self.assertRaisesRegex(ValueError,'digest'):
            core_update.plan(self.world,self.v2,bad)
        with self.assertRaisesRegex(ValueError,'source'):
            core_update.plan(self.world,self.v1,self.index)

    def test_version_reuse_rollback_and_unlocked_commits_cannot_publish(self):
        for previous in (dict(self.index,core_version='2.0.0'),dict(self.index,lock_sha256='0'*64)):
            with self.assertRaises(Invalid):
                core_release.release_index(self.upstream,previous)
        (self.upstream/'scripts/compiler.py').write_text('# Changed without core lock.\n')
        self.commit(self.upstream,'Synthetic unlocked source')
        with self.assertRaisesRegex(Invalid,'lock does not match'):
            core_release.release_index(self.upstream)
        self.lock(self.upstream,'1.0.0');self.commit(self.upstream,'Synthetic rollback')
        with self.assertRaises(Invalid):
            core_release.check_version(self.upstream,self.v2)

    def test_data_only_and_retries_preserve_the_original_release_source(self):
        before=core_release.git(self.upstream,'ls-remote','origin','refs/heads/core-release')
        (self.upstream/'claims').mkdir();(self.upstream/'claims/synthetic.txt').write_text('Synthetic data only.\n')
        self.commit(self.upstream,'Data-only source advance')
        self.assertEqual(core_release.release_index(self.upstream,self.index),self.index)
        self.assertEqual(core_release.publish_channel(self.upstream,'autonomio/resolvent')['status'],'current')
        self.assertEqual(core_release.git(self.upstream,'ls-remote','origin','refs/heads/core-release'),before)

    def test_failed_pr_creation_reuses_branch_and_dispatch_retry_is_idempotent(self):
        provider=Provider();provider.fail='create'
        with patch.object(core_update,'git',side_effect=self.local_fetch):
            with self.assertRaises(subprocess.CalledProcessError):
                core_update.publish(self.world,'example/world',provider=provider)
            original=core_release.git(self.world,'ls-remote','origin','refs/heads/resolvent/core/1.1.0')
            provider.fail='dispatch'
            with self.assertRaises(subprocess.CalledProcessError):
                core_update.publish(self.world,'example/world',provider=provider)
            provider.fail=None
            self.assertEqual(core_update.publish(self.world,'example/world',provider=provider)['status'],'existing_pr')
        self.assertEqual(core_release.git(self.world,'ls-remote','origin','refs/heads/resolvent/core/1.1.0'),original)
        self.assertFalse(self.marker.exists())
        self.assertFalse(any('merge' in args for args,_ in provider.calls))
        self.assertFalse([p for args,p in provider.calls if p and p.get('draft')])

    def test_unrelated_open_update_and_unfamiliar_branch_block_publication(self):
        provider=Provider();provider.pending=[{'headRefName':'resolvent/core/1.0.1'}]
        with patch.object(core_update,'git',side_effect=self.local_fetch):
            self.assertEqual(core_update.publish(self.world,'example/world',provider=provider)['status'],'deferred_pending_core_pr')
            provider.pending=[]
            core_release.git(self.world,'push','origin',self.base+':refs/heads/resolvent/core/1.1.0')
            with self.assertRaisesRegex(ValueError,'Existing update branch differs'):
                core_update.publish(self.world,'example/world',provider=provider)

    def test_candidate_validation_is_unprivileged_and_updates_are_opt_in(self):
        load=lambda path:yaml.load((ROOT/path).read_text(),Loader=yaml.BaseLoader)
        workflow=load('.github/workflows/core-update.yml')
        self.assertIn("vars.RESOLVENT_CORE_UPDATES == 'true'",workflow['jobs']['prepare']['if'])
        self.assertEqual(set(workflow['on']),{'schedule','workflow_dispatch'})
        validate=load('.github/workflows/validate.yml')['jobs']['tests']
        self.assertEqual(validate['permissions'],{'contents':'read'})
        self.assertEqual(validate['steps'][0]['with']['persist-credentials'],'false')
        self.assertIn('python scripts/compiler.py --require-closure',[step.get('run') for step in validate['steps']])
        inventory=next(step for step in validate['steps'] if step.get('name')=='Verify committed core inventory')
        version=next(step for step in validate['steps'] if step.get('name')=='Require a version bump for core changes')
        self.assertEqual(inventory['if'],"github.repository == 'autonomio/resolvent'")
        self.assertIn("github.repository == 'autonomio/resolvent'",version['if'])
        release=load('.github/workflows/core-release.yml')['jobs']['publish']
        self.assertIn("github.repository == 'autonomio/resolvent'",release['if'])
        self.assertIn("workflow_run.conclusion == 'success'",release['if'])
        self.assertEqual(release['steps'][0]['with']['ref'],'${{ github.event.workflow_run.head_sha }}')

    def test_incompatible_candidate_schema_rejects_the_populated_world_without_rewriting_it(self):
        policy=Path(self.temp.name)/'candidate-policy';(policy/'docs').mkdir(parents=True)
        shutil.copytree(ROOT/'docs/schemas',policy/'docs/schemas')
        path=policy/'docs/schemas/claims.schema.json';schema=json.loads(path.read_text())
        schema['properties']['statement']={'type':'integer'};path.write_text(json.dumps(schema))
        before=core_update.tree_entries(self.world,'HEAD')
        with self.assertRaises(Invalid):
            validate_state(load_state(self.world),policy,True)
        self.assertEqual(core_update.tree_entries(self.world,'HEAD'),before)
        self.assertEqual(core_release.git(self.world,'status','--porcelain'),b'')

    def test_head_or_worktree_changes_invalidate_a_plan(self):
        result=self.planned()
        (self.world/'resolvent.yaml').write_text('Uncommitted organization change.\n')
        with self.assertRaisesRegex(ValueError,'changed'):
            core_update.commit_plan(self.world,result)
        self.commit(self.world,'Concurrent configuration commit')
        with self.assertRaisesRegex(ValueError,'advanced'):
            core_update.commit_plan(self.world,result)

    def test_candidate_cannot_raise_pr_workflow_permissions_or_expose_secrets(self):
        workflow=self.upstream/'.github/workflows/validate.yml'
        workflow.write_text('on: pull_request\npermissions:\n  contents: write\njobs: {}\n')
        self.lock(self.upstream,'1.2.0');self.commit(self.upstream,'Unsafe synthetic candidate workflow')
        source=core_release.git(self.upstream,'rev-parse','HEAD').decode().strip()
        index=core_release.release_index(self.upstream)
        core_release.git(self.world,'fetch',str(self.upstream),source)
        with self.assertRaisesRegex(ValueError,'read-only'):
            core_update.commit_plan(self.world,core_update.plan(self.world,source,index))
        workflow.write_text('on: workflow_dispatch\npermissions:\n  contents: read\n'
                            'jobs:\n  test:\n    env:\n      TOKEN: ${{ format(\'}}{0}\', toJSON(secrets)) }}\n')
        self.lock(self.upstream,'1.3.0');self.commit(self.upstream,'Unsafe synthetic candidate secret access')
        source=core_release.git(self.upstream,'rev-parse','HEAD').decode().strip()
        index=core_release.release_index(self.upstream)
        core_release.git(self.world,'fetch',str(self.upstream),source)
        with self.assertRaisesRegex(ValueError,'secrets'):
            core_update.commit_plan(self.world,core_update.plan(self.world,source,index))

    def test_preserved_local_and_unmanaged_workflows_cannot_grant_candidate_credentials(self):
        workflow=self.world/'.github/workflows/validate.yml'
        baseline=workflow.read_text()
        for unsafe,reason in ((baseline.replace('      contents: read','      contents: write'),'write permissions'),
                              (baseline+'    env:\n      TOKEN: ${{ secrets.PRIVATE_TOKEN }}\n','secrets')):
            workflow.write_text(unsafe);self.commit(self.world,'Synthetic local workflow customization')
            result=self.planned()
            self.assertNotIn('.github/workflows/validate.yml',result['changes'])
            with self.assertRaisesRegex(ValueError,reason):
                core_update.commit_plan(self.world,result)
        workflow.write_text(baseline)
        (workflow.parent/'organization.yml').write_text(baseline.replace('contents: read','contents: write'))
        self.commit(self.world,'Synthetic organization-owned workflow')
        with self.assertRaisesRegex(ValueError,'read-only'):
            core_update.commit_plan(self.world,self.planned())
        self.assertFalse(self.marker.exists())

    def test_existing_pr_retries_check_the_actual_branch_before_dispatch(self):
        provider=Provider()
        with patch.object(core_update,'git',side_effect=self.local_fetch):
            self.assertEqual(core_update.publish(self.world,'example/world',provider=provider)['status'],'pr_created')
            core_release.git(self.world,'fetch','origin','refs/heads/resolvent/core/1.1.0')
            core_release.git(self.world,'checkout','-b','synthetic-pr','FETCH_HEAD')
            workflow=self.world/'.github/workflows/validate.yml'
            workflow.write_text(workflow.read_text().replace('contents: read','contents: write'))
            self.commit(self.world,'Synthetic unsafe edit on the pending PR')
            core_release.git(self.world,'push','origin','HEAD:refs/heads/resolvent/core/1.1.0')
            core_release.git(self.world,'checkout','main')
            with self.assertRaisesRegex(ValueError,'read-only'):
                core_update.publish(self.world,'example/world',provider=provider)
        self.assertEqual(sum(args[:2]==('workflow','run') for args,_ in provider.calls),1)
        self.assertFalse(self.marker.exists())


if __name__=='__main__':
    unittest.main()
