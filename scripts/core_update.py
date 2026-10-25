#!/usr/bin/env python3
"""Prepare a reviewed core upgrade without checking out or executing upstream code."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import yaml

if __package__ in (None, ''):
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from scripts.core_release import (CHANNEL, LOCK, UPSTREAM, checked_lock, core_path, decode, git,
                                  json_bytes, validate_index, validate_lock, version)


def tree_entries(root,revision):
    result={}
    for raw in git(root,'ls-tree','-r','-z','--full-tree',revision).split(b'\0'):
        if raw:
            metadata,path=raw.split(b'\t',1);mode,kind,oid=metadata.decode().split()
            result[path.decode()]={'mode':mode,'kind':kind,'oid':oid}
    return result


def matches(root,entry,item):
    if entry is None or entry['kind']!='blob' or entry['mode']!=item['mode'] or entry['oid']!=item['git_blob']:
        return False
    data=git(root,'cat-file','blob',entry['oid'])
    return len(data)==item['bytes'] and hashlib.sha256(data).hexdigest()==item['sha256']


def readonly_candidate_workflows(root,source,files):
    """Candidate PR/dispatch jobs must not acquire secrets or a write token."""
    import re
    for path in files:
        if not path.startswith('.github/workflows/') or not path.endswith(('.yml','.yaml')):
            continue
        raw=git(root,'show',source+':'+path).decode()
        workflow=yaml.load(raw,Loader=yaml.BaseLoader)
        if not isinstance(workflow,dict):
            raise ValueError('Malformed candidate workflow')
        events=workflow.get('on',{})
        events=[events] if isinstance(events,str) else events
        immediate={'pull_request','pull_request_target','merge_group'}.intersection(events)
        if path=='.github/workflows/validate.yml' and 'workflow_dispatch' in events:
            immediate.add('workflow_dispatch')  # The only dispatch this updater performs.
        if 'push' in events and (not isinstance(events,dict) or
                                (events.get('push') or {}).get('branches')!=['main']):
            immediate.add('push')
        if not immediate:
            continue  # Other workflow definitions activate only after reviewed main merge.
        if re.search(r'\$\{\{(?:(?!\}\}).)*\bsecrets\b',raw,re.I|re.S):
            raise ValueError('Candidate PR/dispatch workflow cannot request secrets')
        top=workflow.get('permissions')
        if not isinstance(top,dict) or any(value not in ('read','none') for value in top.values()):
            raise ValueError('Candidate workflow requires explicit read-only permissions')
        for job in workflow.get('jobs',{}).values():
            permissions=job.get('permissions',top)
            if (not isinstance(permissions,dict) or 'secrets' in job or
                    any(value not in ('read','none') for value in permissions.values())):
                raise ValueError('Candidate validation jobs cannot acquire write permissions or secrets')
            for step in job.get('steps',[]):
                if (step.get('uses','').startswith('actions/checkout@') and
                        step.get('with',{}).get('persist-credentials')!='false'):
                    raise ValueError('Candidate validation checkout must not persist credentials')


def plan(root,source,index):
    validate_index(index)
    if source!=index['source_commit']:
        raise ValueError('Candidate source does not match the fixed release index')
    base=git(root,'rev-parse','HEAD').decode().strip()
    if git(root,'status','--porcelain').strip():
        raise ValueError('Core updates require a clean checkout')
    local=tree_entries(root,base)
    if local.get(LOCK,{}).get('mode')!='100644':
        raise ValueError('Adopt a reviewed regular core lock before enabling automatic updates')
    installed=validate_lock(decode(git(root,'show',base+':'+LOCK)))
    raw=git(root,'show',source+':'+LOCK)
    if tree_entries(root,source).get(LOCK,{}).get('mode')!='100644':
        raise ValueError('Upstream core lock must be a regular file')
    if hashlib.sha256(raw).hexdigest()!=index['lock_sha256']:
        raise ValueError('Candidate core lock digest mismatch')
    candidate=checked_lock(root,source)
    if candidate['core_version']!=index['core_version']:
        raise ValueError('Candidate core version mismatch')
    readonly_candidate_workflows(root,source,candidate['files'])
    if version(candidate['core_version'])<version(installed['core_version']):
        raise ValueError('Upstream core version is older than this world')
    if version(candidate['core_version'])==version(installed['core_version']):
        if candidate!=installed:
            raise ValueError('An installed core version cannot be replaced')
        return {'status':'current','base':base}
    for path,item in installed['files'].items():
        if candidate['files'].get(path)!=item and not matches(root,local.get(path),item):
            raise ValueError('Locally modified managed core file: '+path)
    changes={}
    for path in sorted(set(installed['files'])|set(candidate['files'])):
        item=candidate['files'].get(path)
        if item is None:
            changes[path]=None
            continue
        if path not in installed['files']:
            # Never absorb or overwrite organization-owned files, even at a new upstream path.
            components=path.split('/')
            if (path in local or any('/'.join(components[:i]) in local for i in range(1,len(components)))
                    or any(existing.startswith(path+'/') for existing in local)):
                raise ValueError('New core path collides with an unmanaged organization file: '+path)
        if installed['files'].get(path)!=item:
            changes[path]=(item['mode'],item['git_blob'])
    candidate_lock=tree_entries(root,source)[LOCK]['oid']
    changes[LOCK]=('100644',candidate_lock)
    return {'status':'planned','base':base,'source_commit':source,
            'from_version':installed['core_version'],'to_version':candidate['core_version'],'changes':changes}


def commit_plan(root,result):
    if result['status']!='planned':
        raise ValueError('No core update planned')
    if git(root,'rev-parse','HEAD').decode().strip()!=result['base'] or git(root,'status','--porcelain').strip():
        raise ValueError('World advanced or changed; replan before publishing')
    if any(path!=LOCK and not core_path(path) for path in result['changes']):
        raise ValueError('The plan includes a protected path')
    with tempfile.TemporaryDirectory() as temporary:
        env={'GIT_INDEX_FILE':str(Path(temporary)/'index')}
        git(root,'read-tree',result['base'],extra_env=env)
        lines=[]
        for path,entry in sorted(result['changes'].items()):
            mode,oid=entry if entry else ('0','0'*40)
            lines.append((mode+' '+oid+'\t'+path+'\0').encode())
        git(root,'update-index','-z','--index-info',input=b''.join(lines),extra_env=env)
        tree=git(root,'write-tree',extra_env=env).decode().strip()
    before,after=tree_entries(root,result['base']),tree_entries(root,tree)
    actual={path for path in set(before)|set(after) if before.get(path)!=after.get(path)}
    if actual!=set(result['changes']):
        raise ValueError('Proposed core tree differs from the bounded plan')
    message='Update Resolvent core '+result['from_version']+' to '+result['to_version']+'\n'
    return git(root,'commit-tree',tree,'-p',result['base'],input=message.encode(),extra_env={
        'GIT_AUTHOR_NAME':'github-actions[bot]','GIT_COMMITTER_NAME':'github-actions[bot]',
        'GIT_AUTHOR_EMAIL':'41898282+github-actions[bot]@users.noreply.github.com',
        'GIT_COMMITTER_EMAIL':'41898282+github-actions[bot]@users.noreply.github.com'}).decode().strip()


def api(*args,payload=None):
    response=subprocess.run(['gh',*args],input=None if payload is None else json_bytes(payload),
                            capture_output=True,check=True)
    return decode(response.stdout) if response.stdout.strip() else None


def publish(root,repository,*,provider=api):
    import re
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository):
        raise ValueError('Expected an explicit GitHub owner/repository')
    if repository=='autonomio/resolvent':
        return {'status':'skipped_upstream'}
    metadata=provider('api','repos/'+repository)
    if metadata['is_template']:
        return {'status':'skipped_template'}
    if metadata['default_branch']!='main':
        raise ValueError('Adopt the main-branch update workflow before enabling it')
    remote=git(root,'ls-remote','origin','refs/heads/main').decode().split()
    if not remote or remote[0]!=git(root,'rev-parse','HEAD').decode().strip():
        return {'status':'deferred_stale_revision'}
    pending=provider('pr','list','--repo',repository,'--state','open','--limit','1000','--json','headRefName')
    if len(pending)>=1000:
        return {'status':'deferred_pending_core_pr'}
    # Fetch Git objects only from the fixed public source. No downloaded scripts run here.
    git(root,'-c','protocol.file.allow=never','fetch','--no-tags',UPSTREAM,'refs/heads/'+CHANNEL)
    index=validate_index(decode(git(root,'show','FETCH_HEAD:core.json')))
    git(root,'-c','protocol.file.allow=never','fetch','--no-tags',UPSTREAM,index['source_commit'])
    result=plan(root,index['source_commit'],index)
    if result['status']!='planned':
        return result
    branch='resolvent/core/'+result['to_version']
    old=provider('pr','list','--repo',repository,'--state','all','--head',branch,'--limit','1','--json','state,url')
    if old:
        if old[0]['state']=='OPEN':
            provider('workflow','run','validate.yml','--repo',repository,'--ref',branch)
        return {'status':'existing_pr','pull_request':old[0]['url']}
    if any(pr['headRefName'].startswith('resolvent/core/') for pr in pending):
        return {'status':'deferred_pending_core_pr'}
    commit=commit_plan(root,result)
    remote_branch=git(root,'ls-remote','origin','refs/heads/'+branch).decode().split()
    if remote_branch:
        git(root,'fetch','--no-tags','origin','refs/heads/'+branch)
        saved=git(root,'rev-parse','FETCH_HEAD').decode().strip()
        if (git(root,'rev-list','--parents','-n','1',saved).decode().split()[1:]!=[result['base']] or
                git(root,'rev-parse',saved+'^{tree}')!=git(root,'rev-parse',commit+'^{tree}')):
            raise ValueError('Existing update branch differs; no overwrite performed')
    else:
        if git(root,'ls-remote','origin','refs/heads/main').decode().split()[0]!=result['base']:
            return {'status':'deferred_stale_revision'}
        git(root,'push','origin',commit+':refs/heads/'+branch)
    if git(root,'ls-remote','origin','refs/heads/main').decode().split()[0]!=result['base']:
        return {'status':'deferred_stale_revision'}
    response=provider('api','--method','POST','repos/'+repository+'/pulls','--input','-',payload={
        'base':'main','head':branch,'draft':False,'title':'Update Resolvent core to '+result['to_version'],
        'body':'Governance update from autonomio/resolvent commit `'+result['source_commit']+'`. '
               'Affected core hashes match the installed lock. World-model data, resolvent.yaml and '
               'unmanaged organization files retain their exact Git blobs and modes. '
               'The candidate compiler must validate this populated world in CI without write credentials. '
               'Human maintainer review is required. No data migration or automatic merge is performed.'})
    provider('workflow','run','validate.yml','--repo',repository,'--ref',branch)
    return {'status':'pr_created','pull_request':response['html_url'],'core_version':result['to_version']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path('.'))
    parser.add_argument('--repository',required=True)
    args=parser.parse_args()
    try:
        result=publish(args.root,args.repository)
        sys.stdout.buffer.write(json_bytes(result))
        if os.environ.get('GITHUB_STEP_SUMMARY'):
            with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as stream:
                stream.write('Core update: '+result['status']+'\n')
    except (ValueError,OSError,subprocess.CalledProcessError,KeyError,yaml.YAMLError,TypeError):
        parser.exit(1,'Core update stopped; data and main were not changed. Inspect the locked core and retry.\n')


if __name__=='__main__':
    main()
