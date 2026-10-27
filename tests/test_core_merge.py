"""Real Git trees exercise automated copies; only GitHub transport is simulated."""
import copy
import subprocess
import unittest
from unittest.mock import patch

import test_core_update as fixtures
from scripts import core_merge, core_update, core_release, core_review
from types import SimpleNamespace


class Provider:
    def __init__(self,fixture,head):
        self.fixture=fixture;self.calls=[];self.approvals=[];self.fail_merge=None;self.fail_approval=False
        self.endpoint='repos/example/world/pulls/1'
        self.meta={'state':'open','draft':False,'merged':False,'mergeable':True,'mergeable_state':'clean',
                   'head':{'sha':head,'ref':'resolvent/core/1.1.0','repo':{'full_name':'example/world'}},
                   'base':{'sha':fixture.base,'ref':'main','repo':{'full_name':'example/world'}}}
        self.review=self.review_record(head,fixture.base)
        self.source_review=self.review_record(fixture.v2,fixture.v1)
        self.source_reviews=[{'id':1,'user':{'login':'maintainer','type':'User'},'state':'APPROVED',
                              'commit_id':fixture.v2,'author_association':'MEMBER'}]
        self.source_pr={'number':5,'merge_commit_sha':fixture.v2,'merged_at':'2026-01-01T00:00:00Z',
                        'user':{'login':'upstream-author'},'head':{'sha':fixture.v2},
                        'base':{'ref':'main','repo':{'full_name':'autonomio/resolvent'}},
                        'html_url':'https://github.com/autonomio/resolvent/pull/5'}
        self.checks={'total_count':2,'check_runs':[
            {'name':name,'head_sha':head,'app':{'slug':'github-actions'},'status':'completed','conclusion':'success'}
            for name in sorted(core_merge.CHECKS)]}
        self.statuses={'total_count':0,'statuses':[]}

    @staticmethod
    def review_record(head,base):
        return {'headRefOid':head,'baseRefOid':base,'reviewDecision':None,
                'reviews':{'nodes':[],'pageInfo':{'hasPreviousPage':False}},
                'reviewThreads':{'nodes':[],'pageInfo':{'hasNextPage':False}}}

    def __call__(self,*args,payload=None):
        self.calls.append((args,payload))
        if args==('api',self.endpoint):
            return copy.deepcopy(self.meta)
        if args==('api','graphql','--input','-'):
            record=self.source_review if payload['variables']['owner']=='autonomio' else self.review
            return {'data':{'repository':{'pullRequest':copy.deepcopy(record)}}}
        if args[0]=='api' and '/check-runs?' in args[1]:
            return copy.deepcopy(self.checks)
        if args[0]=='api' and '/status?' in args[1]:
            return copy.deepcopy(self.statuses)
        if args==('api','repos/autonomio/resolvent/commits/'+self.fixture.v2+'/pulls?per_page=100'):
            return [copy.deepcopy(self.source_pr)]
        if args==('api','repos/autonomio/resolvent/pulls/5/reviews?per_page=100'):
            return copy.deepcopy(self.source_reviews)
        if args[:2]==('workflow','run'):
            return None
        if args==('api','--method','PUT',self.endpoint+'/merge','--input','-'):
            if self.fail_merge=='before':
                raise subprocess.CalledProcessError(1,['simulated-merge'])
            if payload['sha']!=self.meta['head']['sha']:
                raise AssertionError('Missing current-head merge precondition')
            tree=core_release.git(self.fixture.world,'rev-parse',payload['sha']+'^{tree}').decode().strip()
            merged=core_release.git(self.fixture.world,'commit-tree',tree,'-p',self.meta['base']['sha'],
                                    '-p',payload['sha'],input=b'Synthetic protected merge\n',extra_env={
                                        'GIT_AUTHOR_NAME':'Synthetic GitHub','GIT_COMMITTER_NAME':'Synthetic GitHub',
                                        'GIT_AUTHOR_EMAIL':'test@example.invalid','GIT_COMMITTER_EMAIL':'test@example.invalid'}).decode().strip()
            core_release.git(self.fixture.world,'push','origin',merged+':refs/heads/main')
            self.meta.update(merged=True,state='closed',merge_commit_sha=merged)
            if self.fail_merge=='after':
                raise subprocess.CalledProcessError(1,['simulated-lost-response'])
            return {'merged':True,'sha':merged}
        raise AssertionError(args)

    def approve(self,*args,payload=None):
        self.approvals.append((args,payload))
        if self.fail_approval:
            raise subprocess.CalledProcessError(1,['simulated-review-permission'])
        assert args==('api','--method','POST',self.endpoint+'/reviews','--input','-')
        assert payload['event']=='APPROVE' and payload['commit_id']==self.meta['head']['sha']
        self.review['reviews']['nodes'].append({'state':'APPROVED','body':payload['body'],
                                                'author':{'__typename':'Bot','login':'github-actions'},
                                                'commit':{'oid':payload['commit_id']}})
        self.review['reviewDecision']='APPROVED'


class AutoMergeTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.CoreTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.plan=self.fixture.planned();self.head=core_update.commit_plan(self.fixture.world,self.plan)
        self.branch='resolvent/core/1.1.0';self.url='https://github.com/example/world/pull/1'
        core_release.git(self.fixture.world,'push','origin',self.head+':refs/heads/'+self.branch)
        self.provider=Provider(self.fixture,self.head)

    def continue_update(self,*,head=None,result=None,provider=None,reviewer=None):
        return core_merge.continue_update(self.fixture.world,'example/world',self.branch,self.url,
                                          head or self.head,result or self.plan,self.fixture.index,
                                          provider=provider or self.provider,reviewer=reviewer)

    def writes(self,provider=None):
        return [c for c in (provider or self.provider).calls if c[0][:3]==('api','--method','PUT')]

    def test_reviewed_exact_copy_merges_and_preserves_all_other_git_blobs(self):
        before=core_update.tree_entries(self.fixture.world,self.fixture.base)
        result=self.continue_update()
        self.assertEqual(result['status'],'merged')
        after=core_update.tree_entries(self.fixture.world,result['merge_commit'])
        unmanaged=set(before)-set(self.plan['changes'])
        self.assertEqual({p:before[p] for p in unmanaged},{p:after[p] for p in unmanaged})
        self.assertEqual(len(self.writes()),1)
        self.assertEqual(self.writes()[0][1],{'sha':self.head,'merge_method':'merge'})
        self.assertFalse(self.fixture.marker.exists())
        self.assertEqual(core_release.git(self.fixture.world,'status','--porcelain'),b'')

    def test_each_required_check_must_be_current_successful_and_from_actions(self):
        for field,value in (('head_sha','0'*40),('status','in_progress'),('conclusion','failure'),
                            ('conclusion','cancelled'),('app',{'slug':'untrusted-app'})):
            with self.subTest(field=field,value=value):
                provider=Provider(self.fixture,self.head);provider.checks['check_runs'][0][field]=value
                self.assertEqual(self.continue_update(provider=provider)['status'],'waiting_checks')
                self.assertFalse(self.writes(provider))
        self.provider.checks={'total_count':0,'check_runs':[]}
        self.assertEqual(self.continue_update()['status'],'waiting_checks')

    def test_external_failure_or_incomplete_pagination_cannot_be_ignored(self):
        self.provider.statuses={'total_count':1,'statuses':[{'state':'failure'}]}
        self.assertEqual(self.continue_update()['status'],'waiting_checks')
        self.provider.statuses={'total_count':101,'statuses':[]}
        self.assertEqual(self.continue_update()['status'],'waiting_checks')
        self.provider.statuses={'total_count':0,'statuses':[]};self.provider.checks['total_count']=101
        self.assertEqual(self.continue_update()['status'],'waiting_checks')
        self.assertFalse(self.writes())

    def test_extra_data_or_organization_edits_are_rejected_even_with_a_valid_lock(self):
        core_release.git(self.fixture.world,'checkout','-b','synthetic-tamper',self.head)
        (self.fixture.world/'resolvent.yaml').write_text('project: Unauthorized organization change\n')
        self.fixture.commit(self.fixture.world,'Synthetic extra change')
        changed=core_release.git(self.fixture.world,'rev-parse','HEAD').decode().strip()
        core_release.git(self.fixture.world,'push','origin',changed+':refs/heads/'+self.branch)
        core_release.git(self.fixture.world,'checkout','main')
        self.provider.meta['head']['sha']=changed
        with self.assertRaisesRegex(ValueError,'differs from the exact'):
            self.continue_update(head=changed)
        self.assertFalse(self.writes());self.assertFalse(self.provider.approvals)

    def test_wrong_repo_draft_conflict_and_unresolved_threads_never_merge(self):
        self.provider.meta['head']['repo']['full_name']='attacker/world'
        with self.assertRaisesRegex(ValueError,'unexpected source'):
            self.continue_update()
        self.provider.meta['head']['repo']['full_name']='example/world';self.provider.meta['draft']=True
        with self.assertRaises(ValueError):self.continue_update()
        self.provider.meta['draft']=False;self.provider.meta['mergeable']=False
        self.assertEqual(self.continue_update()['status'],'waiting_merge_eligibility')
        self.provider.meta['mergeable']=True
        self.provider.review['reviewThreads']['nodes']=[{'isResolved':False}]
        self.assertEqual(self.continue_update()['status'],'waiting_repository_review_policy')
        self.assertFalse(self.writes())

    def test_maintainer_objection_is_never_automatically_approved(self):
        self.provider.review['reviewDecision']='CHANGES_REQUESTED'
        self.assertEqual(self.continue_update(reviewer=self.provider.approve)['status'],'waiting_repository_review_policy')
        self.assertFalse(self.provider.approvals);self.assertFalse(self.writes())


    def test_review_approval_is_explicitly_automated_and_bound_to_the_verified_head(self):
        self.provider.review['reviewDecision']='REVIEW_REQUIRED'
        first=self.continue_update(reviewer=self.provider.approve)
        self.assertEqual(first['status'],'automatically_approved_pr')
        self.assertFalse(self.writes());self.assertEqual(len(self.provider.approvals),1)
        body=self.provider.approvals[0][1]['body']
        self.assertTrue(body.startswith(core_merge.REVIEW_MARKER));self.assertIn('not a human assessment',body)
        self.assertIn(self.fixture.v2,body)
        self.assertIn((('workflow','run','core-update.yml','--repo','example/world','--ref','main'),None),self.provider.calls)
        self.assertEqual(self.continue_update()['status'],'merged')

    def test_approval_never_precedes_current_ci(self):
        self.provider.review['reviewDecision']='REVIEW_REQUIRED'
        self.provider.checks['check_runs'][0]['conclusion']='failure'
        self.assertEqual(self.continue_update(reviewer=self.provider.approve)['status'],'waiting_checks')
        self.assertFalse(self.provider.approvals);self.assertFalse(self.writes())

    def test_missing_review_permission_and_additional_owner_policy_are_not_bypassed(self):
        self.provider.review['reviewDecision']='REVIEW_REQUIRED'
        self.assertEqual(self.continue_update()['status'],'waiting_repository_review_policy')
        self.provider.fail_approval=True
        self.assertEqual(self.continue_update(reviewer=self.provider.approve)['status'],'blocked_automation_review_permission')
        self.provider.fail_approval=False
        self.continue_update(reviewer=self.provider.approve)
        self.provider.review['reviewDecision']='REVIEW_REQUIRED'  # e.g. an unmet CODEOWNER rule.
        approvals=len(self.provider.approvals)
        self.assertEqual(self.continue_update(reviewer=self.provider.approve)['status'],'waiting_repository_review_policy')
        self.assertEqual(len(self.provider.approvals),approvals)
        self.assertFalse(self.writes())
        self.provider.review['reviews']['nodes'][0]['state']='DISMISSED'
        self.assertEqual(self.continue_update(reviewer=self.provider.approve)['status'],'waiting_repository_review_policy')
        self.assertEqual(len(self.provider.approvals),approvals)

    def test_a_main_advance_refreshes_by_fast_forward_and_invalidates_old_ci(self):
        (self.fixture.world/'resolvent.yaml').write_text('project: New organization configuration\n')
        self.fixture.commit(self.fixture.world,'Synthetic current main change')
        new_base=core_release.git(self.fixture.world,'rev-parse','HEAD').decode().strip()
        core_release.git(self.fixture.world,'push','origin','HEAD:main')
        result=core_update.plan(self.fixture.world,self.fixture.v2,self.fixture.index)
        self.provider.meta['base']['sha']=new_base
        refreshed=self.continue_update(result=result)
        self.assertEqual(refreshed['status'],'refreshed_pr')
        self.assertEqual(core_release.git(self.fixture.world,'merge-base',self.head,refreshed['head']).decode().strip(),self.head)
        self.assertEqual(core_release.git(self.fixture.world,'show',refreshed['head']+':resolvent.yaml'),
                         (self.fixture.world/'resolvent.yaml').read_bytes())
        self.provider.meta['head']['sha']=refreshed['head']
        self.provider.review.update(headRefOid=refreshed['head'],baseRefOid=new_base)
        self.assertEqual(self.continue_update(head=refreshed['head'],result=result)['status'],'waiting_checks')
        self.assertFalse(self.writes())
        self.assertEqual(core_release.git(self.fixture.world,'rev-parse','HEAD').decode().strip(),new_base)

    def test_remote_change_at_the_final_gate_prevents_a_mutation(self):
        with patch.object(core_merge,'unchanged_remote',side_effect=[True,False]):
            self.assertEqual(self.continue_update()['status'],'deferred_stale_revision')
        self.assertFalse(self.writes());self.assertFalse(self.provider.approvals)

    def test_a_lost_merge_response_is_read_back_without_a_second_merge_request(self):
        self.provider.fail_merge='after'
        self.assertEqual(self.continue_update()['status'],'merged')
        self.assertEqual(len(self.writes()),1)

    def test_a_failed_merge_is_not_reported_as_completed_or_retried(self):
        self.provider.fail_merge='before'
        self.assertEqual(self.continue_update()['status'],'merge_not_confirmed')
        self.assertEqual(len(self.writes()),1)


class PublisherReviewTests(unittest.TestCase):
    def setUp(self):
        self.fixture=SimpleNamespace(v1='1'*40,v2='2'*40,base='3'*40)
        self.head='4'*40;self.provider=Provider(self.fixture,self.head)

    def verify_source(self,provider=None):
        return core_review.approved_upstream(provider or self.provider,self.fixture.v2)

    def writes(self,provider=None):
        return [c for c in (provider or self.provider).calls if c[0][:3]==('api','--method','PUT')]

    def test_publisher_records_only_an_actual_final_head_maintainer_approval(self):
        proof=self.verify_source()
        self.assertEqual(proof,{'pull_request':'https://github.com/autonomio/resolvent/pull/5',
                                'reviewer':'maintainer','reviewed_head':self.fixture.v2})
        self.assertFalse(self.writes())

    def test_upstream_approval_must_be_independent_current_and_a_maintainer(self):
        for mutation in ({'commit_id':'0'*40},{'state':'COMMENTED'},{'author_association':'NONE'},
                         {'user':{'login':'upstream-author','type':'User'}},
                         {'user':{'login':'some-bot','type':'Bot'}}):
            with self.subTest(mutation=mutation):
                provider=Provider(self.fixture,self.head);provider.source_reviews[0].update(mutation)
                with self.assertRaisesRegex(ValueError,'lacks an independent'):
                    self.verify_source(provider)
                self.assertFalse(self.writes(provider))


    def test_upstream_objections_and_open_threads_block_the_copy(self):
        self.provider.source_reviews.append({'id':2,'user':{'login':'another-maintainer','type':'User'},
                                              'state':'CHANGES_REQUESTED','author_association':'MEMBER',
                                              'commit_id':self.fixture.v2})
        with self.assertRaises(ValueError):self.verify_source()
        self.provider.source_reviews.pop()
        self.provider.source_review['reviewThreads']['nodes']=[{'isResolved':False}]
        with self.assertRaises(ValueError):self.verify_source()
        self.assertFalse(self.writes())


    def test_latest_upstream_review_wins_even_when_transport_order_is_reversed(self):
        newer=dict(self.provider.source_reviews[0],id=2,state='CHANGES_REQUESTED')
        self.provider.source_reviews.insert(0,newer)
        with self.assertRaisesRegex(ValueError,'lacks an independent'):
            self.verify_source()
        self.assertFalse(self.writes())

    def test_later_comments_preserve_approval_but_a_dismissal_removes_it(self):
        self.provider.source_reviews.append(dict(self.provider.source_reviews[0],id=2,state='COMMENTED'))
        self.assertEqual(self.verify_source()['reviewer'],'maintainer')
        self.provider.source_reviews[0]['state']='DISMISSED'
        with self.assertRaisesRegex(ValueError,'lacks an independent'):
            self.verify_source()
        self.assertFalse(self.writes())


if __name__=='__main__':unittest.main()
