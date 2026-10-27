"""Complete an opted-in core update using trusted base code and ordinary PR gates."""
from __future__ import annotations

import re
import subprocess
from urllib.parse import urlsplit

from scripts.core_update import git, plan, planned_tree
from scripts.core_review import review_state

CHECKS={'World model integrity','Tests and skill package'}
REVIEW_MARKER='Automated core-release verification:'


def unchanged_remote(root,base,branch,head):
    for ref,expected in (('main',base),(branch,head)):
        remote=git(root,'ls-remote','origin','refs/heads/'+ref).decode().split()
        if not remote or remote[0]!=expected:
            return False
    return True


def checks_pass(provider,repository,head):
    prefix='repos/'+repository+'/commits/'+head
    runs=provider('api',prefix+'/check-runs?filter=latest&per_page=100')
    checks=runs.get('check_runs',[])
    if runs.get('total_count')!=len(checks) or not checks:
        return False
    trusted={c['name'] for c in checks if c.get('head_sha')==head and
             c.get('app',{}).get('slug')=='github-actions' and
             c.get('status')=='completed' and c.get('conclusion')=='success'}
    if not CHECKS.issubset(trusted):
        return False
    if any(c.get('head_sha')!=head or c.get('status')!='completed' or
           c.get('conclusion')!='success' for c in checks):
        return False
    statuses=provider('api',prefix+'/status?per_page=100')
    contexts=statuses.get('statuses',[])
    return statuses.get('total_count')==len(contexts) and all(s.get('state')=='success' for s in contexts)


def continue_update(root,repository,branch,url,head,result,index,*,provider,merge_method='merge',reviewer=None):
    if merge_method not in ('merge','squash','rebase'):
        raise ValueError('Unsupported ordinary core merge method')
    parsed=urlsplit(url)
    match=re.fullmatch('/'+re.escape(repository)+r'/pull/([1-9][0-9]*)',parsed.path)
    if parsed.scheme!='https' or parsed.netloc!='github.com' or not match or parsed.query or parsed.fragment:
        raise ValueError('Core PR identity does not match the selected repository')
    number=int(match[1]);endpoint='repos/'+repository+'/pulls/'+str(number)
    meta=provider('api',endpoint)
    if (meta.get('state')!='open' or meta.get('draft') or meta.get('head',{}).get('sha')!=head or
        meta.get('head',{}).get('ref')!=branch or meta.get('base',{}).get('ref')!='main' or
        meta.get('head',{}).get('repo',{}).get('full_name')!=repository or
        meta.get('base',{}).get('repo',{}).get('full_name')!=repository):
        raise ValueError('Core PR changed or has an unexpected source or destination')
    # Reconstruct the complete expected tree at its original main base. Neither
    # PR prose nor a matching lock alone can authorize extra changes.
    previous_base=git(root,'merge-base',result['base'],head).decode().strip()
    previous=plan(root,result['source_commit'],index,base=previous_base)
    if previous.get('status')!='planned' or git(root,'rev-parse',head+'^{tree}').decode().strip()!=planned_tree(root,previous):
        raise ValueError('Pending core PR differs from the exact upstream update')
    if not unchanged_remote(root,result['base'],branch,head):
        return {'status':'deferred_stale_revision','pull_request':url}
    if previous_base!=result['base']:
        tree=planned_tree(root,result)
        refreshed=git(root,'commit-tree',tree,'-p',head,'-p',result['base'],
                      input=b'Refresh exact core update against current main\n',extra_env={
                          'GIT_AUTHOR_NAME':'github-actions[bot]','GIT_COMMITTER_NAME':'github-actions[bot]',
                          'GIT_AUTHOR_EMAIL':'41898282+github-actions[bot]@users.noreply.github.com',
                          'GIT_COMMITTER_EMAIL':'41898282+github-actions[bot]@users.noreply.github.com'}).decode().strip()
        # The old head is a parent: this is a normal fast-forward of the bot
        # branch, preserving its history and all current world data.
        git(root,'push','origin',refreshed+':refs/heads/'+branch)
        provider('workflow','run','validate.yml','--repo',repository,'--ref',branch)
        return {'status':'refreshed_pr','pull_request':url,'head':refreshed}
    review=review_state(provider,repository,number)
    threads=review['reviewThreads']
    if review.get('headRefOid')!=head or review.get('baseRefOid')!=result['base']:
        return {'status':'deferred_stale_revision','pull_request':url}
    if (review.get('reviewDecision')=='CHANGES_REQUESTED' or
        threads['pageInfo']['hasNextPage'] or any(not t['isResolved'] for t in threads['nodes'])):
        return {'status':'waiting_repository_review_policy','pull_request':url}
    if meta.get('mergeable') is not True:
        return {'status':'waiting_merge_eligibility','pull_request':url}
    if not checks_pass(provider,repository,head):
        return {'status':'waiting_checks','pull_request':url}
    if not unchanged_remote(root,result['base'],branch,head):
        return {'status':'deferred_stale_revision','pull_request':url}
    source_url='https://github.com/autonomio/resolvent/commit/'+result['source_commit']
    if review.get('reviewDecision')=='REVIEW_REQUIRED':
        history=review['reviews']
        already_approved=any(r.get('state') in ('APPROVED','DISMISSED') and r.get('commit',{}).get('oid')==head and
                             r.get('author',{}).get('__typename')=='Bot' and
                             r.get('body','').startswith(REVIEW_MARKER) for r in history['nodes'])
        if reviewer is None or history['pageInfo']['hasPreviousPage'] or already_approved:
            return {'status':'waiting_repository_review_policy','pull_request':url}
        # This is explicitly a machine verification of an independently reviewed
        # upstream copy. It is never described as a new human review.
        try:
            reviewer('api','--method','POST',endpoint+'/reviews','--input','-',payload={
                'event':'APPROVE','commit_id':head,'body':REVIEW_MARKER+' exact core '+result['to_version']+
                ' copy from '+result['source_commit']+'. Verified published upstream release: '+source_url+
                '. Upstream publication requires independent final-head maintainer review. Complete destination tree, preserved world data and successful current-head CI verified. '
                'This is an automated copy check, not a human assessment of new changes.'})
        except subprocess.CalledProcessError:
            return {'status':'blocked_automation_review_permission','pull_request':url}
        # GITHUB_TOKEN review events do not recursively trigger Actions. Resume
        # once with the existing dispatch credential after GitHub recomputes gates.
        provider('workflow','run','core-update.yml','--repo',repository,'--ref','main')
        return {'status':'automatically_approved_pr','pull_request':url,'head':head}
    if meta.get('mergeable_state')!='clean':
        return {'status':'waiting_merge_eligibility','pull_request':url}
    try:
        provider('api','--method','PUT',endpoint+'/merge','--input','-',
                 payload={'sha':head,'merge_method':merge_method})
    except subprocess.CalledProcessError:
        # A lost response is not permission to repeat a mutation. Read its
        # actual outcome; a later run must re-establish every gate.
        pass
    receipt=provider('api',endpoint)
    if receipt.get('merged') is True and re.fullmatch(r'[0-9a-f]{40}',receipt.get('merge_commit_sha','')):
        return {'status':'merged','pull_request':url,'merge_commit':receipt['merge_commit_sha'],
                'core_version':result['to_version']}
    return {'status':'merge_not_confirmed','pull_request':url}
