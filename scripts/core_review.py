"""Verify actual independent review before publishing an upstream core release."""
from __future__ import annotations

import json
import subprocess


def read_api(*args,payload=None):
    result=subprocess.run(['gh',*args],input=None if payload is None else json.dumps(payload).encode(),
                          capture_output=True,check=True)
    return json.loads(result.stdout)


def review_state(provider,repository,number):
    owner,name=repository.split('/')
    query='''query($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name){
      pullRequest(number:$number){headRefOid baseRefOid reviewDecision
        reviews(last:100){nodes{state body author{__typename login} commit{oid}} pageInfo{hasPreviousPage}}
        reviewThreads(first:100){nodes{isResolved} pageInfo{hasNextPage}}}}}'''
    data=provider('api','graphql','--input','-',payload={
        'query':query,'variables':{'owner':owner,'name':name,'number':number}})
    if data.get('errors'):
        raise ValueError('Cannot establish current core review state')
    return data['data']['repository']['pullRequest']


def approved_upstream(provider,source):
    prefix='repos/autonomio/resolvent'
    pulls=provider('api',prefix+'/commits/'+source+'/pulls?per_page=100')
    if not isinstance(pulls,list) or len(pulls)>=100:
        raise ValueError('Cannot establish the upstream source review')
    for pr in pulls:
        if (pr.get('merge_commit_sha')!=source or not pr.get('merged_at') or
            pr.get('base',{}).get('ref')!='main' or
            pr.get('base',{}).get('repo',{}).get('full_name')!='autonomio/resolvent'):
            continue
        reviews=provider('api',prefix+'/pulls/'+str(pr['number'])+'/reviews?per_page=100')
        if not isinstance(reviews,list) or len(reviews)>=100:
            raise ValueError('Upstream review history exceeds the verification bound')
        if any(type(r.get('id')) is not int for r in reviews):
            raise ValueError('Upstream review identities are incomplete')
        latest={r['user']['login']:r for r in sorted(reviews,key=lambda r:r['id'])
                if r.get('user',{}).get('login')}
        if any(r.get('state')=='CHANGES_REQUESTED' and r.get('author_association') in
               ('OWNER','MEMBER','COLLABORATOR') for r in latest.values()):
            continue
        source_review=review_state(provider,'autonomio/resolvent',pr['number'])
        threads=source_review['reviewThreads']
        if (source_review.get('headRefOid')!=pr['head']['sha'] or threads['pageInfo']['hasNextPage'] or
            any(not t['isResolved'] for t in threads['nodes'])):
            continue
        for login,review in latest.items():
            if (review.get('state')=='APPROVED' and review.get('commit_id')==pr['head']['sha'] and
                login!=pr.get('user',{}).get('login') and review['user'].get('type')=='User' and
                review.get('author_association') in ('OWNER','MEMBER','COLLABORATOR')):
                return {'pull_request':pr['html_url'],'reviewer':login,'reviewed_head':pr['head']['sha']}
    raise ValueError('The fixed upstream release lacks an independent maintainer approval on its final PR head')
