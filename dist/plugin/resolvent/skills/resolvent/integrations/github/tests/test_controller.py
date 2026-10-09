"""Offline safety/lifecycle regressions. No GitHub or provider credentials needed."""
import base64
import copy
import datetime as dt
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1] / "overlay" / ".github" / "resolvent"
sys.path.insert(0, str(ROOT))
import controller as c
from schema_subset import Invalid, UnsupportedSchema, validate

HEAD, BASE, MERGE, NEW = (x * 40 for x in "abcd")
RUN = "RUN-" + "e" * 32
PATH = "input-artefacts/" + RUN + ".json"
CLOSURE = "briefs/closed/BC-" + RUN[4:] + ".yaml"
KEY = "test-state-key-never-a-real-secret-000000"


def policy():
    result = json.loads((ROOT / "policy.json").read_text())
    result.update(enabled=True, repository="owner/repo", controller_login="writer-app[bot]",
                  authoring_owner="bounded_worker",  # Legacy repair fixtures explicitly opt in.
                  allowed_authors=["writer"], enrollment_label="followup", provider="openai",
                  model="mock-model", expected_checks=[{"kind": "check", "name": "ci", "app_id": 101}],
                  admission_checks=[{"kind": "check", "name": "admit", "app_id": 202}],
                  admission_attests_entire_diff=True,
                  reviews={"reviewers": ["reviewer"], "minimum": 1, "feedback_authors": ["maintainer"]},
                  amendments={"authorized": True, "contract_paths": ["CONTRIBUTING.md"]})
    return result


def review(number=1, head=HEAD, body="LGTM", submitted="2026-10-07T12:00:00Z", state="APPROVED", login="reviewer"):
    return {"id": number, "user": {"login": login}, "state": state,
            "commit_id": head, "body": body, "submitted_at": submitted}


def snapshot(materialized=True):
    return {"repository": "owner/repo", "pr": 1, "observed_at": "2026-10-07T13:00:00+00:00",
            "head": HEAD, "base": BASE, "trusted_sha": BASE, "default_branch": "main",
            "same_repo": True, "complete": True, "labels": ["followup"],
            "contributors": ["writer"], "rules": [], "threads": [], "issue_comments": [],
            "files": [{"filename": PATH, "status": "added"}] + ([{"filename": CLOSURE, "status": "added"}] if materialized else []), "reviews": [review()],
            "admission_observation": {"contribution_path": PATH, "head": HEAD,
                "closure_path": CLOSURE, "closure_present": materialized,
                "closure_sha256": "f" * 64 if materialized else None},
            "checks": [{"kind": "check", "name": name, "app_id": app, "id": app,
                        "sha": HEAD, "result": "success"} for name, app in [("ci", 101), ("admit", 202)]],
            "pr_data": {"state": "OPEN", "merged": False, "isDraft": False,
                        "author": {"login": "writer"}, "baseRefName": "main",
                        "headRefName": "contribution", "headRefOid": HEAD, "baseRefOid": BASE,
                        "reviewDecision": "APPROVED", "mergeable": "MERGEABLE",
                        "mergeStateStatus": "CLEAN", "potentialMergeCommit": {"oid": MERGE,
                            "parents": {"nodes": [{"oid": HEAD}, {"oid": BASE}]}},
                        "baseRef": {"branchProtectionRule": None}}}


def feedback_snapshot():
    value = snapshot(materialized=False)
    value["issue_comments"] = [{"id": 9, "user": {"login": "reviewer"},
                                "body": "Correct the unsupported evidence attribution.",
                                "updated_at": "2026-10-07T12:30:00Z"}]
    return value


def proposal_fixture():
    p, s = policy(), feedback_snapshot()
    decision = c.evaluate(s, p, {})
    fingerprint = decision["fingerprint"]
    state = {"version": 1, "repository": p["repository"], "pr": 1, "revision": 1,
             "attempts": 1, "feedback_attempts": {fingerprint: 1},
             "handled_feedback_ids": [], "allowed_path": PATH,
             "inflight": {"head": HEAD, "base": BASE, "fingerprint": fingerprint,
                          "run_id": "123", "run_attempt": "1"}}
    before = {"id": RUN, "schema_version": "1.0", "input_method": "conversation",
              "created_at": "2026-10-01T00:00:00Z", "researcher": "writer",
              "parent_run_id": None, "title": "Before"}
    schema = {"type": "object", "required": ["id", "title"], "properties": {
        "id": {"type": "string", "pattern": "^RUN-[0-9a-f]{32}$"},
        "title": {"type": "string", "minLength": 1},
        "created_at": {"type": "string", "format": "date-time"}}}
    packet = {"version": 1, "repository": p["repository"], "pr": 1, "head": HEAD, "base": BASE,
              "policy_hash": c.digest(p), "allowed_path": PATH, "contribution_json": json.dumps(before),
              "schema": schema, "feedback": decision["feedback"], "trusted_contracts": []}
    plan = {"repair": True, "repository": p["repository"], "pr": 1,
            "policy_hash": c.digest(p), "work_digest": c.digest(packet),
            "snapshot": copy.deepcopy(s), "state": copy.deepcopy(state), "decision": decision}
    after = dict(before, title="Corrected")
    proposal = {"outcome": "replace", "summary": "Corrected the evidence attribution.",
                "replacement_json": json.dumps(after),
                "addressed_feedback_ids": [x["id"] for x in packet["feedback"]]}
    return p, s, state, packet, plan, proposal


class PublishingAPI:
    repo = "owner/repo"

    def __init__(self, packet):
        self.packet = packet
        self.mutations = []
        self.cleanup = []
        self.replacement = None
        self.bad_verification = False

    def file(self, sha, path):
        if path == policy()["schema_path"]:
            return json.dumps(self.packet["schema"]).encode()
        if path != PATH:
            raise AssertionError("unexpected file read: " + path)
        return self.replacement if sha == NEW else self.packet["contribution_json"].encode()

    def gql(self, query, variables):
        if "createCommitOnBranch" not in query:
            raise AssertionError("unexpected GraphQL operation")
        self.mutations.append(copy.deepcopy(variables["input"]))
        self.replacement = base64.b64decode(variables["input"]["fileChanges"]["additions"][0]["contents"])
        return {"createCommitOnBranch": {"commit": {"oid": NEW, "url": "https://example.invalid/commit"}}}

    def get(self, path):
        if not path.endswith("/commits/" + NEW):
            raise AssertionError("unexpected GET: " + path)
        return {"parents": [{"sha": BASE if self.bad_verification else HEAD}], "files": [{"filename": PATH}]}

    def api(self, path, payload=None, method="GET"):
        if method != "DELETE" or "/labels/" not in path:
            raise AssertionError("unexpected REST mutation")
        self.cleanup.append(path)
        return None, {}


def mock_publish(p, s, state, packet, plan, proposal, api=None):
    api = api or PublishingAPI(packet)
    saved = []
    def save(_api, _policy, value):
        saved.append(copy.deepcopy(value))
        return copy.deepcopy(value)
    with patch.object(c, "collect", return_value=copy.deepcopy(s)), \
         patch.object(c, "get_state", return_value=copy.deepcopy(state)) as get_state, \
         patch.object(c, "verify_policy_at_default"), \
         patch.object(c, "save_state", side_effect=save):
        result = c.publish(api, 1, p, plan, packet, proposal)
    return result, api, saved, get_state


class OriginatingTaskTests(unittest.TestCase):
    def originating_policy(self):
        return dict(policy(), authoring_owner="originating_task")

    def test_shipped_owner_is_originating_task_and_integration_stays_disabled(self):
        shipped = c.load_policy(ROOT / "policy.json")
        self.assertEqual(shipped["version"], 2)
        self.assertEqual(shipped["authoring_owner"], "originating_task")
        self.assertIs(shipped["enabled"], False)

    def test_empty_repository_is_allowed_only_while_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "policy.json"
            for enabled in [False, True]:
                target.write_text(json.dumps(dict(policy(), repository="", enabled=enabled)))
                if enabled:
                    with self.assertRaisesRegex(c.Blocked, "Configure repository"):
                        c.load_policy(target)
                else:
                    self.assertEqual(c.load_policy(target)["repository"], "")
            target.write_text(json.dumps(dict(policy(), repository="malformed", enabled=False)))
            with self.assertRaisesRegex(c.Blocked, "Configure repository"):
                c.load_policy(target)

    def test_old_policy_version_fails_even_with_explicit_owner(self):
        for enabled in [False, True]:
            for owner in ["originating_task", "bounded_worker"]:
                with self.subTest(enabled=enabled, owner=owner), tempfile.TemporaryDirectory() as directory:
                    p = dict(policy(), version=1, enabled=enabled, authoring_owner=owner)
                    target = Path(directory) / "policy.json"
                    target.write_text(json.dumps(p))
                    with self.assertRaisesRegex(c.Blocked, "Policy version 2.*reviewed ownership update"):
                        c.load_policy(target)
        _, _, state, packet, plan, _ = proposal_fixture()
        self.assertEqual(state["version"], 1)
        self.assertEqual(packet["version"], 1)

    def test_old_or_unknown_owner_fails_policy_validation_even_when_disabled(self):
        for enabled in [False, True]:
            for owner in [None, "unknown"]:
                with self.subTest(enabled=enabled, owner=owner), tempfile.TemporaryDirectory() as directory:
                    p = dict(policy(), enabled=enabled)
                    if owner is None:
                        p.pop("authoring_owner")
                    else:
                        p["authoring_owner"] = owner
                    target = Path(directory) / "policy.json"
                    target.write_text(json.dumps(p))
                    with self.assertRaisesRegex(c.Blocked, "authoring_owner.*reviewed update"):
                        c.load_policy(target)

    def test_observer_requires_no_provider_while_legacy_mode_still_does(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "policy.json"
            p = dict(self.originating_policy(), provider="unconfigured", model="")
            target.write_text(json.dumps(p))
            self.assertEqual(c.load_policy(target)["authoring_owner"], "originating_task")
            p["authoring_owner"] = "bounded_worker"
            target.write_text(json.dumps(p))
            with self.assertRaisesRegex(c.Blocked, "Configure provider"):
                c.load_policy(target)

    def test_originating_task_retains_pre_admission_corrections(self):
        p = self.originating_policy()
        for trigger in ["review", "ci"]:
            with self.subTest(trigger=trigger):
                s = feedback_snapshot() if trigger == "review" else snapshot(materialized=False)
                if trigger == "ci":
                    s["checks"][0]["result"] = "failure"
                decision = c.evaluate(s, p, {})
                self.assertEqual(decision["status"], "BLOCKED")
                self.assertFalse(decision["repair"])
                self.assertNotIn("fingerprint", decision)
                self.assertIn("originating task", decision["reason"])
                self.assertIn("cannot resume", decision["reason"])
        ready = c.evaluate(snapshot(), p, {})
        self.assertEqual(ready["status"], "READY_FOR_MERGE")
        self.assertIn("intermediate observation", ready["reason"])

    def reviewed_correction(self):
        s = snapshot()
        s["reviews"] = [review(1, head=BASE, body="Fix the source.", state="CHANGES_REQUESTED"),
                        review(2, submitted="2026-10-07T12:30:00Z")]
        s["threads"] = [{"id": "old-thread", "isResolved": True, "isOutdated": True,
                         "comments": [{"databaseId": 8, "body": "Fix the source.",
                                       "updatedAt": "2026-10-07T12:00:00Z", "author": {"login": "reviewer"}}]}]
        return s

    def test_observer_recognizes_same_reviewer_current_head_reapproval(self):
        p, s = self.originating_policy(), self.reviewed_correction()
        result = c.evaluate(s, p, {})
        self.assertEqual(result["status"], "READY_FOR_MERGE")
        self.assertFalse(result["repair"])
        # Legacy workers retain their explicit receipt requirements.
        self.assertNotEqual(c.evaluate(s, policy(), {})["status"], "READY_FOR_MERGE")

    def test_observer_reapproval_never_clears_unresolved_threads_or_other_feedback(self):
        for mutation in ("thread", "issue", "mixed", "other-reviewer", "stale", "chronology"):
            with self.subTest(mutation=mutation):
                p, s = self.originating_policy(), self.reviewed_correction()
                if mutation == "thread":
                    s["threads"][0]["isResolved"] = False
                elif mutation == "issue":
                    s["issue_comments"] = feedback_snapshot()["issue_comments"]
                elif mutation == "mixed":
                    s["reviews"][1]["body"] = "LGTM, but fix another source."
                elif mutation == "other-reviewer":
                    p["reviews"]["reviewers"].append("another")
                    s["reviews"][1]["user"]["login"] = "another"
                elif mutation == "stale":
                    s["reviews"][1]["commit_id"] = BASE
                else:
                    s["reviews"][1]["submitted_at"] = "2026-10-07T11:00:00Z"
                self.assertNotEqual(c.evaluate(s, p, {})["status"], "READY_FOR_MERGE")

    def test_observer_reapproval_does_not_clear_a_newer_change_request(self):
        s = self.reviewed_correction()
        s["reviews"].append(review(3, state="CHANGES_REQUESTED", body="New issue.",
                                   submitted="2026-10-07T12:45:00Z"))
        self.assertNotEqual(c.evaluate(s, self.originating_policy(), {})["status"], "READY_FOR_MERGE")

    def test_observer_never_creates_packet_or_reserves_model_attempt(self):
        _, s, state, _, _, _ = proposal_fixture()
        p = self.originating_policy()
        state.pop("inflight")
        api = Mock(repo="owner/repo")
        api.pages.return_value = []
        api.get.return_value = {"user": {"login": "writer"}, "labels": [{"name": "followup"}]}
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(c, "collect", return_value=s), \
             patch.object(c, "get_state", return_value=copy.deepcopy(state)), \
             patch.object(c, "verify_policy_at_default"), \
             patch.object(c, "save_state", side_effect=lambda _api, _policy, value: copy.deepcopy(value)), \
             patch.object(c, "make_work") as make_work:
            plan = c.observe(api, 1, p, directory)
            self.assertFalse((Path(directory) / "work.json").exists())
        self.assertEqual(plan["decision"]["status"], "BLOCKED")
        self.assertFalse(plan["repair"])
        self.assertEqual(plan["state"]["attempts"], state["attempts"])
        self.assertEqual(plan["state"]["feedback_attempts"], state["feedback_attempts"])
        make_work.assert_not_called()

    def test_direct_packet_and_publisher_cannot_bypass_owner(self):
        _, s, _, packet, plan, proposal = proposal_fixture()
        p = self.originating_policy()
        # Even matching artifact hashes cannot authorize another owner to write.
        packet["policy_hash"] = c.digest(p)
        plan.update(policy_hash=c.digest(p), work_digest=c.digest(packet))
        api = Mock(repo="owner/repo")
        with self.assertRaisesRegex(c.Blocked, "originating task owns all corrections"):
            c.make_work(api, p, s, plan["decision"])
        with patch.object(c, "collect") as collect:
            with self.assertRaisesRegex(c.Blocked, "originating task owns all corrections"):
                c.publish(api, 1, p, plan, packet, proposal)
        collect.assert_not_called()
        self.assertEqual(api.mock_calls, [])

    def test_provider_and_work_cli_cannot_bypass_owner(self):
        _, _, _, packet, _, _ = proposal_fixture()
        p = self.originating_policy()
        with patch.object(c, "request") as request:
            with self.assertRaisesRegex(c.Blocked, "originating task owns all corrections"):
                c.call_provider(p, packet, "forged worker prompt")
        request.assert_not_called()
        with patch.object(sys, "argv", ["controller.py", "work", "--packet", "packet.json", "--proposal", "proposal.json"]), \
             patch.object(c, "load_policy", return_value=p), patch.object(c, "read_json") as read_json, \
             patch.object(c, "call_provider") as provider, patch.object(c, "GitHub") as github:
            with self.assertRaisesRegex(c.Blocked, "originating task owns all corrections"):
                c.main()
        read_json.assert_not_called()
        provider.assert_not_called()
        github.assert_not_called()

    def test_missing_owner_cannot_silently_select_a_writer_entrypoint(self):
        p, s, _, packet, plan, proposal = proposal_fixture()
        p.pop("authoring_owner")
        decision = c.evaluate(s, p, {})
        self.assertEqual(decision["status"], "BLOCKED")
        self.assertFalse(decision["repair"])
        api = Mock(repo="owner/repo")
        for operation in [lambda: c.make_work(api, p, s, plan["decision"]),
                          lambda: c.call_provider(p, packet, "prompt"),
                          lambda: c.publish(api, 1, p, plan, packet, proposal)]:
            with self.assertRaisesRegex(c.Blocked, "authoring_owner"):
                operation()
        self.assertEqual(api.mock_calls, [])


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.p, self.s = policy(), snapshot()

    def status(self, state=None):
        return c.evaluate(self.s, self.p, state or {})["status"]

    def test_ready_requires_all_evidence(self):
        self.assertEqual(self.status(), "READY_FOR_MERGE")
        self.s["complete"] = False
        self.assertEqual(self.status(), "BLOCKED")

    def test_no_vacuous_green_when_checks_missing(self):
        self.s["checks"] = []
        self.assertEqual(self.status(), "BLOCKED")
        self.s["checks"] = snapshot()["checks"][1:]
        self.assertEqual(self.status(), "WAITING_CI")

    def test_required_check_origin_is_pinned(self):
        self.s["checks"][0]["app_id"] = 999
        self.assertEqual(self.status(), "WAITING_CI")

    def test_dynamic_required_check_is_not_ignored(self):
        self.s["rules"] = [{"type": "required_status_checks", "parameters": {
            "required_status_checks": [{"context": "new-required", "integration_id": 303}]}}]
        self.assertEqual(self.status(), "WAITING_CI")

    def test_optional_failures_and_pending_checks_count(self):
        optional = {"kind": "check", "name": "optional", "app_id": 303, "id": 303, "sha": HEAD}
        for result, expected in [("failure", "NEEDS_FIX"), ("pending", "WAITING_CI"), ("neutral", "NEEDS_FIX"), ("skipped", "NEEDS_FIX")]:
            with self.subTest(result=result):
                self.s = snapshot(materialized=result == "pending")
                self.s["checks"] = snapshot()["checks"] + [dict(optional, result=result)]
                self.assertEqual(self.status(), expected)

    def test_neutral_requires_explicit_named_policy(self):
        self.s = snapshot(materialized=False)
        self.s["checks"][0]["result"] = "neutral"
        self.assertEqual(self.status(), "NEEDS_FIX")
        self.p["expected_checks"][0].update(accepted_conclusions=["success", "neutral"], reason="Audited nonblocking outcome")
        self.assertEqual(self.status(), "BLOCKED")  # A check exception cannot create admission.
        self.s["admission_observation"] = snapshot()["admission_observation"]
        self.s["files"] = snapshot()["files"]
        self.assertEqual(self.status(), "READY_FOR_MERGE")
        with self.assertRaises(c.Blocked):
            c.check_spec({"name": "x", "kind": "check", "app_id": 1, "accepted_conclusions": ["skipped"]})

    def test_unknown_blocked_behind_and_conflict_never_ready(self):
        for value in ["UNKNOWN", "BLOCKED", "BEHIND", "DIRTY", "UNSTABLE", "HAS_HOOKS"]:
            with self.subTest(value=value):
                self.s["pr_data"]["mergeStateStatus"] = value
                self.assertEqual(self.status(), "WAITING_RULES")

    def test_merge_commit_and_merge_queue_are_distinct_gates(self):
        self.s["pr_data"]["potentialMergeCommit"] = None
        self.assertEqual(self.status(), "WAITING_RULES")
        self.s = snapshot()
        self.s["rules"] = [{"type": "merge_queue"}]
        self.assertEqual(self.status(), "READY_FOR_QUEUE")

    def test_stale_approval_and_contributor_approval_do_not_count(self):
        self.s["reviews"][0]["commit_id"] = BASE
        self.assertEqual(self.status(), "WAITING_REVIEW")
        self.s = snapshot()
        self.s["contributors"].append("reviewer")
        self.assertNotEqual(self.status(), "READY_FOR_MERGE")

    def test_positive_approval_text_and_historical_benign_reviews(self):
        for body in ["", "LGTM", "Looks good.", "Looks good to me!", "Approved", " lgtm "]:
            with self.subTest(body=body):
                self.s["reviews"] = [review(head=BASE), review(2, body=body)]
                self.assertEqual(self.status(), "READY_FOR_MERGE")

    def test_mixed_approval_and_commented_review_are_actionable(self):
        for body, state in [("LGTM but fix the evidence", "APPROVED"), ("Please correct the source", "COMMENTED")]:
            with self.subTest(body=body):
                self.s = snapshot(materialized=False)
                self.s["reviews"] = [review(body=body, state=state)]
                self.assertEqual(self.status(), "NEEDS_FIX")

    def test_unresolved_threads_block_even_after_comment_addressed(self):
        comment = {"databaseId": 8, "body": "Fix this", "updatedAt": "2026-10-07T12:00:00Z", "author": {"login": "reviewer"}}
        self.s["threads"] = [{"id": "thread-1", "isResolved": False, "isOutdated": True, "comments": [comment]}]
        handled = c.feedback_items(self.s, self.p, {})[0]["id"]
        self.assertEqual(self.status({"handled_feedback_ids": [handled]}), "WAITING_REVIEW")

    def test_edited_feedback_is_new_work(self):
        self.s = feedback_snapshot()
        old = c.feedback_items(self.s, self.p, {})[0]["id"]
        self.s["issue_comments"][0]["body"] += " New evidence issue."
        new = c.feedback_items(self.s, self.p, {"handled_feedback_ids": [old]})
        self.assertEqual(len(new), 1)
        self.assertNotEqual(old, new[0]["id"])

    def test_amendment_authorization_is_required(self):
        self.s = snapshot(materialized=False)
        self.s["checks"][0]["result"] = "failure"
        self.p["amendments"]["authorized"] = False
        self.assertEqual(self.status(), "BLOCKED")

    def test_admission_extra_files_and_consumption_are_explicit(self):
        self.p["admission_attests_entire_diff"] = False
        self.s["files"].append({"filename": "claims/canonical.json", "status": "added"})
        self.assertEqual(self.status({"allowed_path": PATH}), "BLOCKED")
        self.p["admission_attests_entire_diff"] = True
        self.assertEqual(self.status({"allowed_path": PATH}), "READY_FOR_MERGE")
        self.s["files"] = self.s["files"][1:]
        self.assertEqual(self.status({"allowed_path": PATH}), "BLOCKED")
        self.p["admission_may_consume_proposal"] = True
        self.assertEqual(self.status({"allowed_path": PATH}), "READY_FOR_MERGE")
        self.s["checks"] = self.s["checks"][:1]
        self.assertEqual(self.status({"allowed_path": PATH}), "BLOCKED")

    def test_fork_opt_out_and_unenrolled_terminal(self):
        self.s["same_repo"] = False
        self.assertEqual(self.status(), "BLOCKED")
        self.s["labels"] = []
        self.assertEqual(self.status(), "DISABLED")
        self.s["pr_data"].update(state="CLOSED", merged=False)
        self.assertEqual(self.status(), "DISABLED")
        self.assertEqual(self.status({"allowed_path": PATH}), "CLOSED")

    def test_retry_fingerprint_and_total_budget(self):
        self.s = snapshot(materialized=False)
        self.s["checks"][0]["result"] = "failure"
        decision = c.evaluate(self.s, self.p, {})
        state = {"attempts": 1, "feedback_attempts": {decision["fingerprint"]: 1}}
        self.assertEqual(self.status(state), "BLOCKED")
        self.s["checks"][0]["id"] += 1
        self.assertEqual(self.status(state), "NEEDS_FIX")
        self.s["head"] = NEW
        self.s["admission_observation"]["head"] = NEW
        self.assertEqual(self.status(state), "NEEDS_FIX")
        state["attempts"] = self.p["max_attempts_per_pr"]
        self.assertEqual(self.status(state), "BLOCKED")

    def test_missing_closure_never_becomes_waiting_for_an_admission_agent(self):
        self.s = snapshot(materialized=False)
        for checks in [[], snapshot()["checks"], [dict(x, result="pending") for x in snapshot()["checks"]]]:
            with self.subTest(checks=checks):
                self.s["checks"] = checks
                decision = c.evaluate(self.s, self.p, {})
                self.assertEqual(decision["status"], "BLOCKED")
                self.assertFalse(decision["repair"])
                self.assertIn("authoring agent", decision["reason"])
                self.assertIn(CLOSURE, decision["reason"])

    def test_failed_admission_without_closure_is_not_a_proposal_repair(self):
        self.s = feedback_snapshot()
        self.s["checks"][1]["result"] = "failure"
        decision = c.evaluate(self.s, self.p, {})
        self.assertEqual(decision["status"], "BLOCKED")
        self.assertFalse(decision["repair"])
        self.assertNotIn("fingerprint", decision)
        self.assertIn("perform PR-side admission", decision["reason"])

    def test_materialized_outputs_require_full_amendment_even_with_attestation(self):
        for material in ["closure", "canonical"]:
            with self.subTest(material=material):
                self.s = feedback_snapshot()
                if material == "closure":
                    # An inherited/unchanged closure also forbids a JSON-only write.
                    self.s["admission_observation"] = snapshot()["admission_observation"]
                else:
                    self.s["files"].append({"filename": "claims/C-existing.yaml", "status": "modified"})
                decision = c.evaluate(self.s, self.p, {})
                self.assertEqual(decision["status"], "BLOCKED")
                self.assertFalse(decision["repair"])
                self.assertIn("full permitted file set", decision["reason"])

    def test_post_admission_failure_never_invokes_single_json_repair(self):
        for index in [0, 1]:
            with self.subTest(check=index):
                self.s = snapshot()
                self.s["checks"][index]["result"] = "failure"
                decision = c.evaluate(self.s, self.p, {})
                self.assertEqual(decision["status"], "BLOCKED")
                self.assertFalse(decision["repair"])
                self.assertIn("regenerate", decision["reason"])

    def test_missing_or_stale_closure_observation_fails_closed(self):
        for mode in ["missing", "head", "path", "digest"]:
            with self.subTest(mode=mode):
                self.s = snapshot()
                if mode == "missing":
                    self.s.pop("admission_observation")
                else:
                    self.s["admission_observation"][{"head": "head", "path": "closure_path", "digest": "closure_sha256"}[mode]] = "invalid"
                self.assertEqual(self.status(), "BLOCKED")

    def test_existing_closure_still_waits_for_validation_and_new_head_review(self):
        self.s["checks"] = snapshot()["checks"][:1]
        self.assertEqual(self.status(), "BLOCKED")
        self.s["checks"] = snapshot()["checks"]
        self.s["checks"][1]["result"] = "pending"
        self.assertEqual(self.status(), "WAITING_CI")
        self.s["checks"][1]["result"] = "success"
        self.s["reviews"][0]["commit_id"] = BASE
        self.assertEqual(self.status(), "WAITING_REVIEW")
        self.s["reviews"][0]["commit_id"] = HEAD
        self.assertEqual(self.status(), "READY_FOR_MERGE")


class PublicationTests(unittest.TestCase):
    def test_single_path_guarded_append_and_verified_feedback(self):
        p, s, state, packet, plan, proposal = proposal_fixture()
        after, api, saved, _ = mock_publish(p, s, state, packet, plan, proposal)
        self.assertEqual(len(api.mutations), 1)
        mutation = api.mutations[0]
        self.assertEqual(mutation["expectedHeadOid"], HEAD)
        self.assertEqual(mutation["branch"], {"repositoryNameWithOwner": "owner/repo", "refName": "contribution"})
        self.assertEqual(set(mutation["fileChanges"]), {"additions"})
        self.assertEqual([x["path"] for x in mutation["fileChanges"]["additions"]], [PATH])
        self.assertEqual(after["handled_feedback_ids"], proposal["addressed_feedback_ids"])
        self.assertEqual(after["status"], "WAITING_CI")
        self.assertEqual(after["head"], NEW)
        self.assertFalse(after["evidence"]["complete"])

    def test_stale_head_or_base_discards_without_mutation(self):
        for field in ["head", "base"]:
            with self.subTest(field=field):
                p, s, state, packet, plan, proposal = proposal_fixture()
                s[field] = NEW
                after, api, _, _ = mock_publish(p, s, state, packet, plan, proposal)
                self.assertEqual(after["status"], "BLOCKED")
                self.assertFalse(api.mutations)

    def test_new_feedback_and_opt_out_discard_proposal(self):
        for change in ["feedback", "opt_out"]:
            with self.subTest(change=change):
                p, s, state, packet, plan, proposal = proposal_fixture()
                if change == "feedback":
                    s["issue_comments"][0]["body"] += " New issue."
                else:
                    s["labels"] = []
                after, api, _, _ = mock_publish(p, s, state, packet, plan, proposal)
                self.assertFalse(api.mutations)
                self.assertIn(after["status"], ["BLOCKED", "DISABLED"])

    def test_already_ready_needs_no_correction(self):
        p, s, state, packet, plan, proposal = proposal_fixture()
        s = snapshot()  # Fresh observation includes materialization and all gates.
        after, api, _, _ = mock_publish(p, s, state, packet, plan, proposal)
        self.assertEqual(after["status"], "READY_FOR_MERGE")
        self.assertFalse(api.mutations)

    def test_noncode_output_requires_fresh_independent_confirmation(self):
        for outcome in ["no_change", "blocked"]:
            with self.subTest(outcome=outcome):
                p, s, state, packet, plan, proposal = proposal_fixture()
                proposal.update(outcome=outcome, replacement_json=None)
                after, api, _, _ = mock_publish(p, s, state, packet, plan, proposal)
                self.assertFalse(after["handled_feedback_ids"])
                self.assertFalse(api.mutations)
                self.assertNotEqual(c.evaluate(s, p, after)["status"], "READY_FOR_MERGE")
                same = after["assessment"]["recorded_at"].replace("+00:00", "Z")
                s["reviews"].append(review(2, submitted=same))
                self.assertNotEqual(c.evaluate(s, p, after)["status"], "READY_FOR_MERGE")
                when = dt.datetime.fromisoformat(after["assessment"]["recorded_at"]) + dt.timedelta(seconds=2)
                s["reviews"].append(review(3, submitted=when.isoformat()))
                self.assertEqual(c.confirmed_assessment(s, p, after), set(after["assessment"]["feedback_ids"]))
                decision = c.evaluate(s, p, after)
                self.assertEqual(decision["status"], "BLOCKED")
                self.assertIn("Materialized closure is missing", decision["reason"])
                s["issue_comments"][0]["body"] += " An edited unresolved request."
                self.assertTrue(c.feedback_items(s, p, after))
                self.assertNotEqual(c.evaluate(s, p, after)["status"], "READY_FOR_MERGE")

    def test_publisher_rechecks_closure_and_full_diff_before_a_json_write(self):
        for changed in ["closure", "canonical", "observation_missing", "admission_failed"]:
            with self.subTest(changed=changed):
                p, s, state, packet, plan, proposal = proposal_fixture()
                if changed == "closure":
                    s["admission_observation"] = snapshot()["admission_observation"]
                elif changed == "canonical":
                    s["files"].append({"filename": "claims/C-new.yaml", "status": "added"})
                elif changed == "observation_missing":
                    s.pop("admission_observation")
                else:
                    s["checks"][1]["result"] = "failure"
                after, api, _, _ = mock_publish(p, s, state, packet, plan, proposal)
                self.assertEqual(after["status"], "BLOCKED")
                self.assertFalse(api.mutations)
                self.assertFalse(after["handled_feedback_ids"])
                self.assertNotIn("inflight", after)

    def test_packet_creation_cannot_bypass_materialized_scope(self):
        p, s, _, _, plan, _ = proposal_fixture()
        s["admission_observation"] = snapshot()["admission_observation"]
        api = Mock(repo="owner/repo")
        with self.assertRaisesRegex(c.Blocked, "full permitted file set"):
            c.make_work(api, p, s, plan["decision"])
        api.file.assert_not_called()

    def test_unverified_commit_does_not_mark_feedback_handled(self):
        p, s, state, packet, plan, proposal = proposal_fixture()
        api = PublishingAPI(packet)
        api.bad_verification = True
        with self.assertRaisesRegex(c.Blocked, "verification failed"):
            mock_publish(p, s, state, packet, plan, proposal, api)
        self.assertEqual(state["handled_feedback_ids"], [])

    def test_newer_reservation_is_not_owned_by_old_plan(self):
        p, s, state, packet, plan, proposal = proposal_fixture()
        state["revision"] += 1
        state["inflight"]["run_id"] = "newer-run"
        with self.assertRaisesRegex(c.Blocked, "no longer belongs"):
            mock_publish(p, s, state, packet, plan, proposal)

    def test_cli_failure_handler_cannot_clear_a_newer_reservation(self):
        p, _, state, packet, plan, _ = proposal_fixture()
        state["revision"] += 1
        state["inflight"]["run_id"] = "newer-run"
        with patch.object(sys, "argv", ["controller.py", "publish", "--pr", "1", "--plan", "plan.json", "--packet", "packet.json"]), \
             patch.object(c, "load_policy", return_value=p), patch.object(c, "read_json", side_effect=[plan, packet]), \
             patch.object(c, "GitHub", return_value=Mock(repo="owner/repo")), \
             patch.object(c, "publish", side_effect=c.Blocked("reservation not owned")), \
             patch.object(c, "get_state", return_value=state), patch.object(c, "save_state") as save, \
             patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(c.Blocked, "Stale publisher cannot alter"):
                c.main()
        save.assert_not_called()

    def test_close_during_model_work_authenticates_state_and_finalizes(self):
        for merged in [False, True]:
            with self.subTest(merged=merged):
                p, s, state, packet, plan, proposal = proposal_fixture()
                s["pr_data"].update(state="MERGED" if merged else "CLOSED", merged=merged)
                s["issue_comments"] = []
                after, api, _, get_state = mock_publish(p, s, state, packet, plan, proposal)
                self.assertIsNone(get_state.call_args.args[3])
                self.assertEqual(after["status"], "MERGED" if merged else "CLOSED")
                self.assertFalse(api.mutations)
                self.assertEqual(len(api.cleanup), 1)

    def test_proposal_identity_schema_and_path_are_enforced(self):
        p, _, _, packet, _, proposal = proposal_fixture()
        for key in ["id", "researcher", "created_at", "schema_version"]:
            with self.subTest(key=key):
                value = json.loads(proposal["replacement_json"])
                value[key] = "altered"
                with self.assertRaises(c.Blocked):
                    c.validate_proposal(dict(proposal, replacement_json=json.dumps(value)), packet, p)
        value = json.loads(proposal["replacement_json"])
        value["title"] = ""
        with self.assertRaises(c.Blocked):
            c.validate_proposal(dict(proposal, replacement_json=json.dumps(value)), packet, p)
        with self.assertRaises(c.Blocked):
            c.validate_proposal(dict(proposal, addressed_feedback_ids=["unobserved"]), packet, p)
        with self.assertRaises(c.Blocked):
            c.validate_proposal(dict(proposal, shell_command="malicious"), packet, p)


class CollectionAPI:
    """Minimal complete fake; returns a changed final scope when requested."""
    repo = "owner/repo"

    def __init__(self):
        self.s = snapshot()
        self.graph_calls = 0
        self.rest_calls = 0
        self.final_graph_change = None
        self.final_rest_change = None
        self.closure_content = ("schema_version: '1.0'\nid: BC-" + RUN[4:] + "\nsubmission_id: " + RUN + "\n").encode()
        self.closure_error = None
        self.closure_reads = []

    def file(self, sha, path, missing_ok=False):
        self.closure_reads.append((sha, path, missing_ok))
        if (sha, path, missing_ok) != (HEAD, CLOSURE, True):
            raise AssertionError("unexpected closure snapshot read")
        if self.closure_error:
            raise self.closure_error
        return self.closure_content

    def graph(self):
        self.graph_calls += 1
        result = {"pullRequest": copy.deepcopy(self.s["pr_data"]), "defaultBranchRef": {"name": "main", "target": {"oid": BASE}}}
        if self.graph_calls > 1 and self.final_graph_change:
            self.final_graph_change(result)
        return result

    def get(self, path):
        if path != "/repos/owner/repo/pulls/1":
            raise AssertionError(path)
        self.rest_calls += 1
        value = {"head": {"sha": HEAD, "ref": "contribution", "repo": {"full_name": self.repo}},
                 "base": {"sha": BASE, "ref": "main"}, "labels": [{"name": "followup"}],
                 "changed_files": len(self.s["files"]), "commits": 1, "user": {"login": "writer"}, "draft": False, "state": "open"}
        if self.rest_calls > 1 and self.final_rest_change:
            self.final_rest_change(value)
        return value

    def pages(self, path, key=None):
        if path.endswith("/files"):
            return copy.deepcopy(self.s["files"])
        if path.endswith("/commits"):
            return [{"author": {"login": "writer"}, "committer": {"login": "reviewer"}}]
        if path.endswith("/reviews"):
            return copy.deepcopy(self.s["reviews"])
        if path.endswith("/comments") or "/rules/branches/" in path:
            return []
        raise AssertionError(path)


class CollectionTests(unittest.TestCase):
    def collect(self, api, enrolled_path=None):
        with patch.object(c, "pr_graph", side_effect=lambda _api, _n: api.graph()), \
             patch.object(c, "all_threads", return_value=[]), \
             patch.object(c, "checks_at", return_value=snapshot()["checks"]):
            return c.collect(api, 1, policy(), enrolled_path)

    def test_complete_collection_includes_committers_as_contributors(self):
        result = self.collect(CollectionAPI())
        self.assertTrue(result["complete"])
        self.assertIn("reviewer", result["contributors"])
        self.assertNotEqual(c.evaluate(result, policy(), {})["status"], "READY_FOR_MERGE")

    def test_closure_is_read_at_exact_head_even_when_not_in_diff(self):
        api = CollectionAPI()
        api.s["files"] = [{"filename": PATH, "status": "added"}]
        result = self.collect(api)
        self.assertEqual(api.closure_reads, [(HEAD, CLOSURE, True)])
        self.assertTrue(result["admission_observation"]["closure_present"])
        self.assertEqual(result["admission_observation"]["head"], HEAD)
        self.assertIsNotNone(c.proposal_repair_blocker(result, PATH))

    def test_consumed_proposal_uses_authenticated_enrollment_for_closure_read(self):
        api = CollectionAPI()
        api.s["files"] = [{"filename": CLOSURE, "status": "added"}]
        result = self.collect(api, PATH)
        self.assertEqual(api.closure_reads, [(HEAD, CLOSURE, True)])
        self.assertEqual(result["admission_observation"]["contribution_path"], PATH)

    def test_missing_closure_is_distinct_from_unreadable_or_empty_closure(self):
        api = CollectionAPI()
        api.closure_content = None
        self.assertFalse(self.collect(api)["admission_observation"]["closure_present"])
        for invalid in [b"", b" \n\t", b"\xef\xbb\xbf \n", b"\xff"]:
            with self.subTest(invalid=invalid):
                api = CollectionAPI()
                api.closure_content = invalid
                with self.assertRaises(c.Blocked):
                    self.collect(api)
        for error in [c.HttpError(403, {}), c.HttpError(404, {}), c.Blocked("Git tree response truncated")]:
            with self.subTest(error=error):
                api = CollectionAPI()
                api.closure_error = error
                with self.assertRaises(c.Blocked):
                    self.collect(api)

    def test_invalid_closure_content_cannot_replace_a_successful_admission_gate(self):
        api = CollectionAPI()
        api.closure_content = b"not: [valid yaml"
        result = self.collect(api)
        result["checks"][1]["result"] = "failure"
        decision = c.evaluate(result, policy(), {})
        self.assertEqual(decision["status"], "BLOCKED")
        self.assertFalse(decision["repair"])

    def test_missing_admission_does_not_reserve_a_provider_attempt(self):
        p, s, state, _, _, _ = proposal_fixture()
        state.pop("inflight")
        s["checks"][1]["result"] = "failure"
        api = Mock(repo="owner/repo")
        api.pages.return_value = []
        api.get.return_value = {"user": {"login": "writer"}, "labels": [{"name": "followup"}]}
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(c, "collect", return_value=s), \
             patch.object(c, "get_state", return_value=copy.deepcopy(state)), \
             patch.object(c, "verify_policy_at_default"), \
             patch.object(c, "save_state", side_effect=lambda _api, _policy, value: copy.deepcopy(value)), \
             patch.object(c, "make_work") as make_work:
            plan = c.observe(api, 1, p, directory)
        self.assertEqual(plan["decision"]["status"], "BLOCKED")
        self.assertFalse(plan["repair"])
        self.assertEqual(plan["state"]["attempts"], state["attempts"])
        self.assertEqual(plan["state"]["feedback_attempts"], state["feedback_attempts"])
        make_work.assert_not_called()

    def test_same_sha_retarget_during_observation_is_rejected(self):
        api = CollectionAPI()
        api.final_graph_change = lambda value: value["pullRequest"].update(baseRefName="unapproved")
        with self.assertRaises(c.Blocked):
            self.collect(api)

    def test_opt_out_or_repository_change_during_observation_is_rejected(self):
        for mode in ["label", "repo"]:
            with self.subTest(mode=mode):
                api = CollectionAPI()
                def mutate(value):
                    if mode == "label":
                        value["labels"] = []
                    else:
                        value["head"]["repo"]["full_name"] = "fork/repo"
                api.final_rest_change = mutate
                with self.assertRaises(c.Blocked):
                    self.collect(api)

    def test_executed_source_sha_must_equal_current_default_tip(self):
        api = Mock()
        api.file.return_value = json.dumps(policy()).encode()
        with patch.dict(os.environ, {"RESOLVENT_CODE_SHA": HEAD}):
            with self.assertRaisesRegex(c.Blocked, "Executed controller SHA"):
                c.verify_policy_at_default(api, policy(), snapshot())
        api.file.assert_not_called()

    def test_non_enrolled_pr_observation_makes_no_writes(self):
        api = Mock(repo="owner/repo")
        api.pages.return_value = []
        api.get.return_value = {"user": {"login": "stranger"}, "labels": []}
        with tempfile.TemporaryDirectory() as directory:
            plan = c.observe(api, 1, policy(), directory)
        self.assertEqual(plan["decision"]["status"], "DISABLED")
        api.api.assert_not_called()
        api.gql.assert_not_called()

    def test_discovery_includes_closed_prs_only_with_prior_controller_comment(self):
        api = Mock(repo="owner/repo")
        def pages(path):
            if path.endswith("/pulls?state=open"):
                return [{"number": 1, "user": {"login": "writer"}, "labels": [{"name": "followup"}]}]
            if "/issues?state=closed&labels=" in path:
                return [{"number": n, "user": {"login": "writer"}, "pull_request": {}} for n in [2, 3]]
            if path.endswith("/issues/2/comments"):
                return [{"user": {"login": "writer-app[bot]"}, "body": "candidate only; observer verifies signature"}]
            if path.endswith("/issues/3/comments"):
                return []
            raise AssertionError(path)
        api.pages.side_effect = pages
        api.get.side_effect = [{"default_branch": "main"}, {"object": {"sha": BASE}}]
        with patch.object(sys, "argv", ["controller.py", "discover"]), \
             patch.object(c, "load_policy", return_value=policy()), patch.object(c, "GitHub", return_value=api), \
             patch.object(c, "outputs") as outputs, patch.dict(os.environ, {}, clear=True), patch("builtins.print"):
            c.main()
        self.assertEqual(outputs.call_args.args[0]["matrix"], {"include": [{"pr": 1}, {"pr": 2}]})
        api.api.assert_not_called()


class StateTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"RESOLVENT_STATE_KEY": KEY})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.p = policy()
        self.state = {"version": 1, "repository": "owner/repo", "pr": 1, "revision": 2,
                      "attempts": 3, "handled_feedback_ids": [], "feedback_attempts": {}}

    def comment(self):
        envelope = {"data": self.state, "hmac_sha256": c.sign_state(self.state)}
        return {"id": 99, "node_id": "IC_99", "body": c.STATE_MARKER + c.canonical(envelope) + "\n-->\nVisible checkpoint",
                "user": {"login": self.p["controller_login"]}, "_editor_checked": True}

    def test_checkpoint_signature_identity_and_duplicate_state(self):
        comment = self.comment()
        self.assertEqual(c.state_from_comments([comment], self.p, 1)["attempts"], 3)
        comment["body"] = comment["body"].replace('"attempts":3', '"attempts":0')
        with self.assertRaises(c.Blocked):
            c.state_from_comments([comment], self.p, 1)
        with self.assertRaises(c.Blocked):
            c.state_from_comments([self.comment(), self.comment()], self.p, 1)
        with self.assertRaises(c.Blocked):
            c.state_from_comments([self.comment()], self.p, 2)

    def test_edited_or_marker_stripped_controller_comment_fails_closed(self):
        comment = self.comment()
        for body, editor in [(comment["body"], "maintainer"), ("marker removed", self.p["controller_login"]), (comment["body"], None)]:
            with self.subTest(editor=editor, marker=body.startswith(c.STATE_MARKER)):
                api = Mock(repo="owner/repo")
                api.gql.return_value = {"node": {"databaseId": 99, "body": body,
                    "author": {"login": self.p["controller_login"]}, "editor": {"login": editor} if editor else None,
                    "lastEditedAt": "2026-10-07T13:00:00Z"}}
                raw = dict(comment, body=body)
                with self.assertRaises(c.Blocked):
                    c.get_state(api, self.p, 1, [raw])
                api.gql.assert_called_once()

    def test_graphql_body_and_editor_are_verified_together(self):
        comment = self.comment()
        api = Mock(repo="owner/repo")
        api.gql.return_value = {"node": {"databaseId": 99, "body": comment["body"],
            "author": {"login": self.p["controller_login"]}, "editor": {"login": self.p["controller_login"]},
            "lastEditedAt": "2026-10-07T13:00:00Z"}}
        self.assertEqual(c.get_state(api, self.p, 1, [dict(comment, body="stale REST body")])["revision"], 2)


class ProviderAndDataTests(unittest.TestCase):
    def test_provider_payloads_are_tool_free_and_bounded(self):
        p, _, _, packet, _, _ = proposal_fixture()
        proposal = {"outcome": "no_change", "summary": "Requires confirmation.", "replacement_json": None, "addressed_feedback_ids": []}
        for provider in ["openai", "anthropic"]:
            with self.subTest(provider=provider):
                p["provider"] = provider
                response = {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(proposal)}]}]} if provider == "openai" else {"stop_reason": "end_turn", "content": [{"type": "text", "text": json.dumps(proposal)}]}
                with patch.object(c, "request", return_value=(json.dumps(response).encode(), {})) as request, \
                     patch.dict(os.environ, {"OPENAI_API_KEY": "provider-fixture-key", "ANTHROPIC_API_KEY": "provider-fixture-key"}):
                    self.assertEqual(c.call_provider(p, packet, "trusted prompt"), proposal)
                    body = request.call_args.args[2]
                    self.assertNotIn("tools", body)
                    self.assertNotIn("tool_choice", body)
                    self.assertEqual(body.get("max_output_tokens", body.get("max_tokens")), p["max_output_tokens"])
                    self.assertTrue(request.call_args.args[0].startswith("https://api."))

    def test_incomplete_provider_output_cannot_publish(self):
        p, _, _, packet, _, _ = proposal_fixture()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "provider-fixture-key"}), \
             patch.object(c, "request", return_value=(b'{"status":"incomplete"}', {})):
            with self.assertRaises(c.Blocked):
                c.call_provider(p, packet, "prompt")

    def test_input_budget_includes_trusted_instructions(self):
        p, _, _, packet, _, _ = proposal_fixture()
        p["max_input_bytes"] = 4096
        with patch.object(c, "request") as request:
            with self.assertRaises(c.Blocked):
                c.call_provider(p, packet, "x" * 4096)
        request.assert_not_called()

    def test_worker_refuses_checkpoint_or_writer_credentials(self):
        for key in c.WRITER_CREDENTIALS:
            with self.subTest(key=key), patch.dict(os.environ, {key: "fixture-secret"}, clear=True):
                with self.assertRaises(c.Blocked):
                    c.assert_worker_environment()
        with patch.dict(os.environ, {"RESOLVENT_STATE_KEY": KEY}, clear=True):
            with self.assertRaises(c.Blocked):
                c.ensure_no_local_secrets('diagnostic contains ' + KEY)

    def test_json_escaped_credentials_never_reach_provider_packets(self):
        for suffix in ('"quoted"', '\\backslash', '\nnewline', 'é-unicode'):
            with self.subTest(suffix=suffix), patch.dict(os.environ, {"RESOLVENT_STATE_KEY": KEY + suffix}, clear=True):
                secret = KEY + suffix
                packets = [c.canonical({"diagnostics": [{"logs": "error " + secret}]}),
                           c.canonical({"contribution_json": json.dumps({"title": secret})})]
                for text in packets:
                    with self.assertRaisesRegex(c.Blocked, "Local credential"):
                        c.ensure_no_local_secrets(text)
                c.ensure_no_local_secrets(c.canonical({"diagnostics": [{"logs": "ordinary failure"}]}))

    def test_github_log_redirect_never_forwards_authorization(self):
        api = c.GitHub("owner/repo", token="fake-github-token")
        def responder(url, headers, *args, **kwargs):
            if url.startswith("https://api.github.com"):
                self.assertIn("Authorization", headers)
                raise c.HttpError(302, {"Location": "https://logs.example.invalid/signed?query=private"})
            self.assertNotIn("Authorization", headers)
            return b"failure details", {}
        with patch.object(c, "request", side_effect=responder):
            self.assertEqual(api.logs(12), "failure details")

    def test_symlinked_git_file_is_rejected_without_blob_read(self):
        api = c.GitHub("owner/repo", token="fixture-token")
        def get(path):
            if "/git/commits/" in path:
                return {"tree": {"sha": BASE}}
            if "/git/trees/" in path:
                return {"tree": [{"path": "proposal.json", "type": "blob", "mode": "120000", "sha": HEAD}]}
            raise AssertionError("must not follow symlink")
        with patch.object(api, "get", side_effect=get):
            with self.assertRaises(c.Blocked):
                api.file(HEAD, "proposal.json")

    def test_strict_json_and_schema_reject_unsupported_data(self):
        for raw in ['{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}']:
            with self.subTest(raw=raw), self.assertRaises(c.Blocked):
                c.strict_json(raw)
        with self.assertRaises(UnsupportedSchema):
            validate({}, {"unevaluatedProperties": False})
        with self.assertRaises(UnsupportedSchema):
            validate({}, {"$ref": "https://example.invalid/schema"})

    def test_rfc3339_date_time_shape(self):
        schema = {"type": "string", "format": "date-time"}
        for good in ["2026-10-07T12:00:00Z", "2026-10-07t12:00:00.125+01:30"]:
            validate(good, schema)
        for bad in ["2026-W41-3T12:00:00+00:00", "20261007T120000+0000", "2026-10-07T12:00Z", "2026-10-07T12:00:00", "2026-02-30T12:00:00Z"]:
            with self.subTest(bad=bad), self.assertRaises(Invalid):
                validate(bad, schema)

    def test_disabled_configuration_does_no_network_work(self):
        with patch.object(sys, "argv", ["controller.py", "discover"]), patch.object(c, "GitHub") as github, \
             patch.object(c, "outputs"), patch("builtins.print"):
            c.main()
        github.assert_not_called()


if __name__ == "__main__":
    unittest.main()
