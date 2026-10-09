#!/usr/bin/env python3
"""Opt-in Resolvent PR observer with explicit legacy repair mode. Python 3.11+.

The originating task owns all authoring by default. Only separately configured
bounded_worker mode can call a model or publish a proposal repair. No mode merges.
"""
import argparse
import base64
import copy
import datetime as dt
import hashlib
import hmac
import html
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from schema_subset import Invalid, validate

MAX_FILE = 2 * 1024 * 1024
MAX_RESPONSE = 16 * 1024 * 1024
RUN_PATH = re.compile(r"input-artefacts/(RUN-[0-9a-f]{32})\.json\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")
STATE_MARKER = "<!-- resolvent-followup-state:v1\n"
HERE = Path(__file__).resolve().parent
WRITER_CREDENTIALS = ("GH_TOKEN", "GITHUB_TOKEN", "RESOLVENT_WRITER_TOKEN", "RESOLVENT_STATE_KEY", "RESOLVENT_APP_PRIVATE_KEY", "GH_APP_PRIVATE_KEY")


class Blocked(RuntimeError):
    pass


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def strict_json(data):
    def pairs(items):
        result = {}
        for key, val in items:
            if key in result:
                raise Blocked("Duplicate JSON object key")
            result[key] = val
        return result
    def bad(_):
        raise Blocked("Non-finite JSON value")
    try:
        return json.loads(data, object_pairs_hook=pairs, parse_constant=bad)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise Blocked("Invalid or excessively nested JSON") from error


def read_json(path, limit=MAX_RESPONSE):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise Blocked("Expected a bounded regular JSON file")
    return strict_json(path.read_bytes())


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def check_spec(spec):
    if not isinstance(spec, dict) or not isinstance(spec.get("name"), str) or not spec["name"].strip():
        raise Blocked("Each check needs an exact nonempty name")
    if spec.get("kind") not in ("check", "status"):
        raise Blocked("Each configured check needs kind=check or status")
    if spec["kind"] == "check" and (type(spec.get("app_id")) is not int or spec["app_id"] < 1):
        raise Blocked("Pin each configured check to its GitHub App database ID")
    accepted = spec.get("accepted_conclusions", ["success"])
    if not accepted or not set(accepted) <= {"success", "neutral", "skipped"}:
        raise Blocked("Checks can accept only success or explicitly justified neutral/skipped")
    if set(accepted) != {"success"} and not spec.get("reason"):
        raise Blocked("An explicit reason is required to accept neutral/skipped")


def authoring_owner(policy):
    owner = policy.get("authoring_owner")
    if owner not in ("originating_task", "bounded_worker"):
        raise Blocked("Configure authoring_owner explicitly as originating_task, or separately authorize legacy bounded_worker mode; older policies require a reviewed update")
    return owner


def require_bounded_worker(policy):
    if authoring_owner(policy) != "bounded_worker":
        raise Blocked("The originating task owns all corrections. This integration only observes; background model work and proposal publication are disabled")


def load_policy(path):
    p = read_json(path, 65536)
    if p.get("version") != 2:
        raise Blocked("Policy version 2 is required; older policies require a reviewed ownership update")
    if type(p.get("enabled")) is not bool:
        raise Blocked("Malformed policy enabled setting")
    repository = p.get("repository", "")
    if not (repository == "" and not p["enabled"]) and not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise Blocked("Configure repository as owner/name")
    owner = authoring_owner(p)
    if not p["enabled"]:
        return p
    if owner == "bounded_worker" and (p.get("provider") not in ("openai", "anthropic") or not p.get("model")):
        raise Blocked("Configure provider=openai|anthropic and an API model ID")
    if not p.get("allowed_authors") or not p.get("enrollment_label"):
        raise Blocked("Configure allowed_authors and an enrollment_label")
    if "REPLACE" in p.get("controller_login", "REPLACE") or not p["controller_login"].endswith("[bot]"):
        raise Blocked("Configure the dedicated GitHub App bot login")
    if not p.get("expected_checks") or not p.get("admission_checks"):
        raise Blocked("Configure nonempty expected_checks and independent admission_checks")
    reviews = p.get("reviews", {})
    if not reviews.get("reviewers") or type(reviews.get("minimum")) is not int or not 1 <= reviews["minimum"] <= len(set(reviews["reviewers"])):
        raise Blocked("Configure at least one independent reviewer and valid minimum")
    if p["controller_login"] in reviews["reviewers"]:
        raise Blocked("The contribution writer cannot count as independent reviewer")
    amendments = p.get("amendments", {})
    if type(amendments.get("authorized")) is not bool:
        raise Blocked("Set amendments.authorized explicitly")
    if amendments["authorized"] and not amendments.get("contract_paths"):
        raise Blocked("Amendment authorization requires trusted contract_paths")
    for path in amendments.get("contract_paths", []):
        if not isinstance(path, str) or not re.fullmatch(r"[A-Za-z0-9_./-]+\.(md|json)", path) or ".." in Path(path).parts or path.startswith("/"):
            raise Blocked("Amendment contracts must be explicit relative Markdown/JSON paths")
    for key in ("admission_attests_entire_diff", "admission_may_consume_proposal"):
        if type(p.get(key)) is not bool:
            raise Blocked("Set " + key + " explicitly")
    for spec in p["expected_checks"] + p["admission_checks"] + p.get("accepted_nonrequired_checks", []):
        check_spec(spec)
    for key, minimum, maximum in (("max_attempts_per_pr", 1, 20), ("max_attempts_per_feedback", 1, 3), ("max_open_prs", 1, 100), ("max_observation_seconds", 30, 900), ("max_input_bytes", 4096, 2097152), ("max_output_tokens", 1024, 64000)):
        if type(p.get(key)) is not int or not minimum <= p[key] <= maximum:
            raise Blocked("Invalid bounded policy setting: " + key)
    if not re.fullmatch(r"[A-Za-z0-9_./-]+\.json", p.get("schema_path", "")) or ".." in Path(p["schema_path"]).parts:
        raise Blocked("schema_path must be a relative repository JSON path")
    return p


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(url, headers, payload=None, method="GET", limit=MAX_RESPONSE, timeout=45):
    # Redirects are handled explicitly below so GitHub authorization cannot leak
    # to signed log-download hosts. Provider requests do not follow redirects.
    data = None if payload is None else canonical(payload).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        response = urllib.request.build_opener(NoRedirect).open(req, timeout=timeout)
        with response:
            body = response.read(limit + 1)
            if len(body) > limit:
                raise Blocked("HTTP response exceeded its configured size bound")
            return body, dict(response.headers)
    except urllib.error.HTTPError as error:
        # Do not include response bodies, URLs with signed queries, or credentials
        # in exceptions/logs. Return only status and safe metadata to the caller.
        raise HttpError(error.code, dict(error.headers)) from None
    except (urllib.error.URLError, TimeoutError) as error:
        raise Blocked("Network request failed or timed out") from error


class HttpError(Blocked):
    def __init__(self, status, headers):
        super().__init__("HTTP " + str(status))
        self.status, self.headers = status, headers


class GitHub:
    def __init__(self, repo, token=None):
        self.repo = repo
        token = token or os.environ.get("GH_TOKEN")
        if not token:
            raise Blocked("GH_TOKEN is missing; no anonymous fallback")
        self.headers = {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json", "User-Agent": "resolvent-followup/1.3.0"}

    def api(self, path, payload=None, method="GET"):
        if not path.startswith("/") or path.startswith("//"):
            raise Blocked("Only GitHub API paths are accepted")
        body, headers = request("https://api.github.com" + path, self.headers, payload, method)
        return strict_json(body) if body else None, headers

    def get(self, path):
        return self.api(path)[0]

    def pages(self, path, key=None):
        result, page = [], 1
        while page <= 100:
            sep = "&" if "?" in path else "?"
            data, headers = self.api(path + sep + "per_page=100&page=" + str(page))
            rows = data if key is None else data[key]
            if not isinstance(rows, list):
                raise Blocked("Unexpected paginated GitHub response")
            result.extend(rows)
            link = headers.get("Link", headers.get("link", ""))
            if 'rel="next"' not in link:
                return result
            page += 1
        raise Blocked("Pagination limit reached; observation incomplete")

    def gql(self, query, variables):
        result = self.api("/graphql", {"query": query, "variables": variables}, "POST")[0]
        if result.get("errors") or "data" not in result:
            raise Blocked("GitHub GraphQL response incomplete or denied")
        return result["data"]

    def file(self, sha, path, missing_ok=False):
        if not SHA.fullmatch(sha):
            raise Blocked("File reads require an exact commit SHA")
        # Walk Git tree entries instead of the Contents API, which may dereference
        # a symlink. Neither symlinked directories nor symlinked JSON are allowed.
        tree = self.get(f"/repos/{self.repo}/git/commits/{sha}")["tree"]["sha"]
        parts = path.split("/")
        for i, part in enumerate(parts):
            data = self.get(f"/repos/{self.repo}/git/trees/{tree}")
            if data.get("truncated"):
                raise Blocked("Git tree response truncated")
            entry = next((x for x in data["tree"] if x["path"] == part), None)
            if entry is None:
                if missing_ok:
                    return None
                raise Blocked("Required repository file is missing: " + path)
            if i < len(parts) - 1:
                if entry["mode"] != "040000" or entry["type"] != "tree":
                    raise Blocked("File path traverses a non-directory")
                tree = entry["sha"]
            else:
                if entry["mode"] != "100644" or entry["type"] != "blob":
                    raise Blocked("Contribution/schema must be a regular non-executable file")
                if entry.get("size", 0) > MAX_FILE:
                    raise Blocked("Repository JSON exceeds 2 MiB")
                blob = self.get(f"/repos/{self.repo}/git/blobs/{entry['sha']}")
                if blob.get("encoding") != "base64":
                    raise Blocked("Unexpected blob encoding")
                raw = base64.b64decode(blob["content"])
                if len(raw) > MAX_FILE:
                    raise Blocked("Repository JSON exceeds 2 MiB")
                return raw

    def logs(self, job_id, limit=65536):
        path = f"https://api.github.com/repos/{self.repo}/actions/jobs/{int(job_id)}/logs"
        try:
            body, _ = request(path, self.headers, limit=limit)
            return body.decode("utf-8", "replace")
        except HttpError as error:
            if error.status not in (301, 302, 303, 307, 308):
                return "Logs unavailable (HTTP " + str(error.status) + ")"
            location = error.headers.get("Location", error.headers.get("location", ""))
            parts = urllib.parse.urlsplit(location)
            if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
                return "Log redirect rejected"
            # Signed redirects are supplied by GitHub, not PR data. No GitHub
            # credential is sent to the download host, and no further redirects.
            try:
                body, _ = request(location, {"User-Agent": "resolvent-followup"}, limit=limit)
                return body.decode("utf-8", "replace")
            except Blocked:
                return "Logs unavailable or exceed bounded diagnostic limit"


PR_QUERY = """query($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name){
 defaultBranchRef{name target{oid}} pullRequest(number:$number){
 id number state merged isDraft headRefOid baseRefOid headRefName baseRefName
 author{login} mergeable mergeStateStatus reviewDecision
 potentialMergeCommit{oid parents(first:2){nodes{oid}}}
 baseRef{branchProtectionRule{requiresApprovingReviews requiredApprovingReviewCount
 requiredStatusCheckContexts requiredStatusChecks{context app{databaseId}}
 requiresStrictStatusChecks requiresConversationResolution requiresCodeOwnerReviews}}
 }}}"""


def pr_graph(api, number):
    owner, name = api.repo.split("/")
    result = api.gql(PR_QUERY, {"owner": owner, "name": name, "number": number})["repository"]
    if result is None or result.get("pullRequest") is None or result.get("defaultBranchRef") is None:
        raise Blocked("Repository, PR, or default branch is unavailable")
    return result


def all_threads(api, number):
    owner, name = api.repo.split("/")
    cursor, result = None, []
    for _ in range(100):
        query = """query($owner:String!,$name:String!,$number:Int!,$after:String){repository(owner:$owner,name:$name){pullRequest(number:$number){reviewThreads(first:100,after:$after){nodes{id isResolved isOutdated comments(first:100){nodes{databaseId body createdAt updatedAt author{login}} pageInfo{hasNextPage endCursor}}} pageInfo{hasNextPage endCursor}}}}}"""
        group = api.gql(query, {"owner": owner, "name": name, "number": number, "after": cursor})["repository"]["pullRequest"]["reviewThreads"]
        for thread in group["nodes"]:
            comments = thread["comments"]
            nodes = comments["nodes"][:]
            for _ in range(100):
                if not comments["pageInfo"]["hasNextPage"]:
                    break
                cq = """query($id:ID!,$after:String){node(id:$id){... on PullRequestReviewThread{comments(first:100,after:$after){nodes{databaseId body createdAt updatedAt author{login}} pageInfo{hasNextPage endCursor}}}}}"""
                comments = api.gql(cq, {"id": thread["id"], "after": comments["pageInfo"]["endCursor"]})["node"]["comments"]
                nodes.extend(comments["nodes"])
            else:
                raise Blocked("Review-comment pagination incomplete")
            thread["comments"] = nodes
            result.append(thread)
        if not group["pageInfo"]["hasNextPage"]:
            return result
        cursor = group["pageInfo"]["endCursor"]
    raise Blocked("Review-thread pagination incomplete")


def checks_at(api, sha):
    result = []
    runs = api.pages(f"/repos/{api.repo}/commits/{sha}/check-runs?filter=latest", "check_runs")
    for r in runs:
        result.append({"kind": "check", "name": r["name"], "app_id": r.get("app", {}).get("id"), "id": r["id"], "sha": sha, "result": r.get("conclusion") if r["status"] == "completed" else "pending", "url": r.get("html_url")})
    newest = {}
    for item in result:
        key = (item["name"], item["app_id"])
        if key not in newest or item["id"] > newest[key]["id"]:
            newest[key] = item
    result = list(newest.values())
    statuses = api.pages(f"/repos/{api.repo}/commits/{sha}/statuses")
    latest = {}
    for r in statuses:
        if r["context"] not in latest or r["id"] > latest[r["context"]]["id"]:
            latest[r["context"]] = r
    for r in latest.values():
        result.append({"kind": "status", "name": r["context"], "app_id": None, "id": r["id"], "sha": sha, "result": r["state"], "url": r.get("target_url")})
    return result


def closure_path(contribution_path):
    match = RUN_PATH.fullmatch(contribution_path)
    if not match:
        raise Blocked("Invalid contribution path for admission observation")
    return "briefs/closed/BC-" + match.group(1)[4:] + ".yaml"


def inspect_closure(api, head, contribution_path):
    path = closure_path(contribution_path)
    # Read the exact immutable head, including closures inherited from the base
    # or absent from the PR diff. Git tree absence is the only missing result;
    # denied/truncated/non-regular reads must fail, never mean "not admitted".
    raw = api.file(head, path, missing_ok=True)
    if raw is not None:
        try:
            text = raw.decode("utf-8")
        except UnicodeError:
            raise Blocked("Closure is not UTF-8; the authoring agent must regenerate and validate admission") from None
        if not text.lstrip("\ufeff").strip():
            raise Blocked("Closure is empty; the authoring agent must regenerate and validate admission")
    # Presence is not semantic validation. Readiness still requires the trusted
    # compiler/admission check, including schema, digest, and actual-delta checks.
    return {"contribution_path": contribution_path, "head": head,
            "closure_path": path, "closure_present": raw is not None,
            "closure_sha256": hashlib.sha256(raw).hexdigest() if raw is not None else None}


def observed_closure(snapshot, contribution_path):
    observation = snapshot.get("admission_observation") or {}
    if (observation.get("contribution_path"), observation.get("head"), observation.get("closure_path")) != (contribution_path, snapshot["head"], closure_path(contribution_path)) or type(observation.get("closure_present")) is not bool:
        raise Blocked("Current-head closure observation is incomplete; recollect before follow-up")
    if observation["closure_present"] and not re.fullmatch(r"[0-9a-f]{64}", observation.get("closure_sha256") or ""):
        raise Blocked("Current-head closure digest is unavailable; recollect before follow-up")
    return observation["closure_present"]


def proposal_repair_blocker(snapshot, contribution_path):
    if observed_closure(snapshot, contribution_path) or any(x["filename"] != contribution_path for x in snapshot["files"]):
        return ("The PR includes a closure or nonproposal outputs. A JSON-only correction can invalidate admission; "
                "the authoring agent must amend, regenerate, and validate the full permitted file set, then obtain independent re-review")
    return None


def collect(api, number, policy, enrolled_path=None):
    start = time.monotonic()
    initial = pr_graph(api, number)
    pr = initial["pullRequest"]
    rest = api.get(f"/repos/{api.repo}/pulls/{number}")
    if (rest["head"]["sha"], rest["base"]["sha"], rest["head"]["ref"], rest["base"]["ref"], rest["user"]["login"], rest["draft"]) != (pr["headRefOid"], pr["baseRefOid"], pr["headRefName"], pr["baseRefName"], pr["author"]["login"], pr["isDraft"]):
        raise Blocked("PR advanced during observation; retry on next reconciliation")
    snapshot = {"repository": api.repo, "pr": number, "observed_at": now(), "head": pr["headRefOid"], "base": pr["baseRefOid"], "default_branch": initial["defaultBranchRef"]["name"], "trusted_sha": initial["defaultBranchRef"]["target"]["oid"], "pr_data": pr, "same_repo": (rest["head"].get("repo") or {}).get("full_name", "").lower() == api.repo.lower(), "labels": [x["name"] for x in rest["labels"]], "checks": [], "reviews": [], "threads": [], "issue_comments": [], "files": [], "rules": [], "contributors": [], "admission_observation": None, "complete": False}
    if pr["state"] != "OPEN":
        snapshot["complete"] = True
        return snapshot
    snapshot["files"] = api.pages(f"/repos/{api.repo}/pulls/{number}/files")
    if len(snapshot["files"]) != rest["changed_files"]:
        raise Blocked("PR files response incomplete")
    candidates = [x["filename"] for x in snapshot["files"] if RUN_PATH.fullmatch(x["filename"]) and x["status"] == "added"]
    target = enrolled_path or (candidates[0] if len(candidates) == 1 else None)
    if target:
        snapshot["admission_observation"] = inspect_closure(api, snapshot["head"], target)
    commits = api.pages(f"/repos/{api.repo}/pulls/{number}/commits")
    if len(commits) != rest["commits"]:
        raise Blocked("PR commits response incomplete")
    snapshot["contributors"] = sorted({x[role]["login"] for x in commits for role in ("author", "committer") if x.get(role)})
    snapshot["reviews"] = api.pages(f"/repos/{api.repo}/pulls/{number}/reviews")
    snapshot["threads"] = all_threads(api, number)
    snapshot["issue_comments"] = api.pages(f"/repos/{api.repo}/issues/{number}/comments")
    snapshot["rules"] = api.pages(f"/repos/{api.repo}/rules/branches/" + urllib.parse.quote(pr["baseRefName"], safe=""))
    snapshot["checks"] = checks_at(api, snapshot["head"])
    merge = pr.get("potentialMergeCommit")
    if merge:
        if {x["oid"] for x in merge["parents"]["nodes"]} != {snapshot["head"], snapshot["base"]}:
            raise Blocked("GitHub test-merge commit is not for the current head and base")
        snapshot["checks"] += checks_at(api, merge["oid"])
    end = pr_graph(api, number)
    for field in ("headRefOid", "baseRefOid", "headRefName", "baseRefName", "author", "state", "isDraft", "mergeable", "mergeStateStatus", "reviewDecision", "baseRef", "potentialMergeCommit"):
        if end["pullRequest"][field] != pr[field]:
            raise Blocked("PR gates changed while observing; retry on next reconciliation")
    final_rest = api.get(f"/repos/{api.repo}/pulls/{number}")
    def scope(value):
        return (value["head"]["sha"], value["base"]["sha"], value["head"]["ref"], value["base"]["ref"], (value["head"].get("repo") or {}).get("full_name"), value["user"]["login"], value["state"], value["draft"], sorted(x["name"] for x in value["labels"]))
    if scope(final_rest) != scope(rest):
        raise Blocked("PR enrollment, branch scope, or state changed while observing")
    if end["defaultBranchRef"]["target"]["oid"] != snapshot["trusted_sha"] or time.monotonic() - start > policy["max_observation_seconds"]:
        raise Blocked("Observation became stale")
    snapshot["observed_at"] = now()
    snapshot["complete"] = True
    return snapshot


def state_from_comments(comments, policy, number):
    found = []
    for comment in comments:
        body = comment.get("body", "")
        if comment.get("user", {}).get("login") != policy["controller_login"]:
            continue
        if not comment.get("_editor_checked"):
            raise Blocked("Checkpoint editor has not been verified")
        if not body.startswith(STATE_MARKER) or "\n-->" not in body:
            raise Blocked("Dedicated controller comment is missing its checkpoint marker; operator recovery required")
        try:
            envelope = strict_json(body[len(STATE_MARKER):].split("\n-->", 1)[0])
            state = envelope["data"]
            expected = sign_state(state)
            if not isinstance(envelope.get("hmac_sha256"), str) or not hmac.compare_digest(expected, envelope["hmac_sha256"]):
                raise Blocked("Controller checkpoint signature does not match")
        except (Blocked, KeyError, TypeError, AttributeError):
            raise Blocked("Controller checkpoint is malformed; operator recovery required") from None
        if state.get("repository") != policy["repository"] or state.get("pr") != number or state.get("version") != 1:
            raise Blocked("Controller checkpoint identity mismatch")
        state["comment_id"] = comment["id"]
        found.append(state)
    if len(found) > 1:
        raise Blocked("Multiple controller checkpoints; resolve ownership before continuing")
    return found[0] if found else {"version": 1, "repository": policy["repository"], "pr": number, "revision": 0, "attempts": 0, "feedback_attempts": {}, "handled_feedback_ids": []}


def get_state(api, policy, number, comments=None):
    if comments is None:
        comments = api.pages(f"/repos/{api.repo}/issues/{number}/comments")
    verified = []
    for comment in comments:
        if comment.get("user", {}).get("login") != policy["controller_login"]:
            continue
        q = """query($id:ID!){node(id:$id){... on IssueComment{databaseId body author{login} editor{login} lastEditedAt}}}"""
        node = api.gql(q, {"id": comment["node_id"]})["node"]
        if not node or (node.get("author") or {}).get("login") != policy["controller_login"]:
            raise Blocked("Checkpoint author could not be verified")
        if node.get("lastEditedAt") and (node.get("editor") or {}).get("login") != policy["controller_login"]:
            raise Blocked("Checkpoint was edited outside the dedicated controller App")
        # Author, latest editor, and signed body are one GraphQL observation.
        verified.append({"id": node["databaseId"], "body": node["body"], "user": node["author"], "_editor_checked": True})
    return state_from_comments(verified, policy, number)


def sign_state(state):
    secret = os.environ.get("RESOLVENT_STATE_KEY", "")
    if len(secret) < 32:
        raise Blocked("RESOLVENT_STATE_KEY must contain at least 32 characters")
    return hmac.new(secret.encode(), canonical(state).encode(), hashlib.sha256).hexdigest()


def feedback_id(kind, number, body, updated=None):
    return kind + ":" + str(number) + ":" + digest([body, updated])[:16]


def independent_logins(snapshot, policy):
    return set(policy["reviews"]["reviewers"]) - set(snapshot["contributors"]) - {snapshot["pr_data"]["author"]["login"], policy["controller_login"]}


def benign_approval(body):
    normalized = " ".join((body or "").strip().casefold().split())
    return re.fullmatch(r"(?:lgtm|looks good|looks good to me|approved)?[.!]?", normalized) is not None


def later_than(first, second):
    try:
        return dt.datetime.fromisoformat(first.replace("Z", "+00:00")) > dt.datetime.fromisoformat(second.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return False


def confirmed_assessment(snapshot, policy, state):
    assessment = state.get("assessment")
    if not assessment or assessment["head"] != snapshot["head"]:
        return set()
    # A non-code disposition needs a fresh independent empty/benign approval.
    # Any other nonempty approval body remains new feedback to be inspected.
    confirmations = {r["user"]["login"] for r in snapshot["reviews"] if r["state"] == "APPROVED" and r.get("commit_id") == snapshot["head"] and benign_approval(r.get("body", "")) and r["id"] > assessment.get("last_review_id", 0) and later_than(r.get("submitted_at", ""), assessment["recorded_at"]) and r["user"]["login"] in independent_logins(snapshot, policy)}
    if len(confirmations) >= policy["reviews"]["minimum"]:
        return set(assessment["feedback_ids"])
    return set()


def specs_from_rules(snapshot):
    p = snapshot["pr_data"]
    protection = (p.get("baseRef") or {}).get("branchProtectionRule") or {}
    specs = []
    described = set()
    for item in protection.get("requiredStatusChecks") or []:
        specs.append({"name": item["context"], "kind": None, "app_id": (item.get("app") or {}).get("databaseId")})
        described.add(item["context"])
    specs += [{"name": name, "kind": None, "app_id": None} for name in protection.get("requiredStatusCheckContexts") or [] if name not in described]
    for rule in snapshot["rules"]:
        if rule["type"] == "required_status_checks":
            specs += [{"name": x["context"], "kind": None, "app_id": x.get("integration_id")} for x in rule.get("parameters", {}).get("required_status_checks", [])]
    return specs


def matches_spec(check, spec):
    return check["name"] == spec["name"] and (not spec.get("kind") or check["kind"] == spec["kind"]) and (not spec.get("app_id") or check["app_id"] == spec["app_id"])


def check_groups(snapshot, policy):
    configured = policy["expected_checks"] + policy["admission_checks"]
    required = configured + specs_from_rules(snapshot)
    statuses = {"failed": [], "pending": [], "missing": [], "ambiguous": []}
    for spec in required:
        found = [x for x in snapshot["checks"] if matches_spec(x, spec)]
        if not found:
            statuses["missing"].append(spec["name"])
            continue
        sources = {(x["kind"], x["app_id"]) for x in found}
        if len(sources) > 1 and not spec.get("kind"):
            # GitHub requires both when status and check share a required context;
            # all are evaluated below. Multiple apps with an unpinned context are
            # ambiguous until the operator pins it in expected_checks.
            if len({x["app_id"] for x in found if x["kind"] == "check"}) > 1 and not any(x["name"] == spec["name"] and x.get("app_id") for x in configured):
                statuses["ambiguous"].append(spec["name"])
    for check in snapshot["checks"]:
        specs = [x for x in configured + policy.get("accepted_nonrequired_checks", []) if matches_spec(check, x)]
        accepted = set(specs[0].get("accepted_conclusions", ["success"])) if specs else {"success"}
        # Every observed applicable check is included, even optional checks. No
        # implicit success for neutral, skipped, missing, or an empty list.
        if check["result"] == "pending" or check["result"] is None:
            statuses["pending"].append(check["name"])
        elif check["result"] not in accepted:
            statuses["failed"].append(check)
    return statuses


def feedback_items(snapshot, policy, state):
    allowed = set(policy["reviews"].get("feedback_authors", [])) | set(policy["reviews"]["reviewers"])
    handled = set(state.get("handled_feedback_ids", [])) | confirmed_assessment(snapshot, policy, state)
    # In observer mode the originating task owns correction receipts. A later
    # benign approval by the requesting independent reviewer, on this exact
    # head with every thread resolved, confirms their old review is concluded.
    # This never clears issue comments or permits the observer to author/merge.
    latest = {}
    for review in sorted(snapshot["reviews"], key=lambda value: value["id"]):
        if review["state"] in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
            latest[review["user"]["login"]] = review
    items = []
    for thread in snapshot["threads"]:
        if thread["isResolved"]:
            continue
        for c in thread["comments"]:
            key = feedback_id("thread-comment", c["databaseId"], c["body"], c.get("updatedAt"))
            if (c.get("author") or {}).get("login") in allowed and key not in handled:
                items.append({"id": key, "body": c["body"], "author": c["author"]["login"], "thread": thread["id"], "outdated": thread["isOutdated"]})
    for c in snapshot["issue_comments"]:
        key = feedback_id("issue-comment", c["id"], c.get("body", ""), c.get("updated_at"))
        if c.get("user", {}).get("login") in allowed and key not in handled and not c.get("body", "").startswith(STATE_MARKER):
            items.append({"id": key, "body": c["body"], "author": c["user"]["login"]})
    for r in snapshot["reviews"]:
        key = feedback_id("review", r["id"], r.get("body", ""), r.get("updated_at", r.get("submitted_at")))
        if r["state"] == "APPROVED" and r["user"]["login"] in independent_logins(snapshot, policy) and benign_approval(r.get("body", "")):
            continue
        confirming = latest.get(r.get("user", {}).get("login"), {})
        if (authoring_owner(policy) == "originating_task" and r["state"] == "CHANGES_REQUESTED"
                and r["user"]["login"] in independent_logins(snapshot, policy)
                and confirming.get("state") == "APPROVED"
                and confirming.get("commit_id") == snapshot["head"]
                and benign_approval(confirming.get("body", ""))
                and confirming["id"] > r["id"]
                and later_than(confirming.get("submitted_at", ""), r.get("updated_at") or r.get("submitted_at", ""))
                and all(thread["isResolved"] for thread in snapshot["threads"])):
            continue
        if r.get("user", {}).get("login") in allowed and key not in handled and (r.get("body", "").strip() or r["state"] == "CHANGES_REQUESTED"):
            items.append({"id": key, "body": r.get("body", ""), "author": r["user"]["login"]})
    return sorted(items, key=lambda x: x["id"])


def evaluate(snapshot, policy, state):
    result = {"status": "BLOCKED", "reason": "", "repair": False, "feedback": [], "failures": []}
    def finish(status, reason):
        result.update(status=status, reason=reason)
        return result
    try:
        owner = authoring_owner(policy)
    except Blocked as error:
        return finish("BLOCKED", str(error))
    if not policy["enabled"]:
        return finish("DISABLED", "Integration is disabled")
    if not snapshot.get("complete"):
        return finish("BLOCKED", "Observation is incomplete")
    pr = snapshot["pr_data"]
    enrolled = pr["author"]["login"] in policy["allowed_authors"] and policy["enrollment_label"] in snapshot["labels"]
    if not enrolled and not (state.get("allowed_path") and pr["state"] != "OPEN"):
        return finish("DISABLED", "PR is not opted in with an allowed author and enrollment label")
    if pr["state"] != "OPEN" and not state.get("allowed_path"):
        return finish("DISABLED", "Closed PR has no previous authenticated enrollment")
    if pr["state"] != "OPEN":
        return finish("MERGED" if pr["merged"] else "CLOSED", "Observed terminal PR state; no merge action taken")
    if not snapshot["same_repo"]:
        return finish("BLOCKED", "Only same-repository contribution branches are supported")
    if pr["baseRefName"] != (policy.get("base_branch") or snapshot["default_branch"]):
        return finish("BLOCKED", "PR targets a different base branch")
    if pr["headRefName"] == pr["baseRefName"]:
        return finish("BLOCKED", "Refusing to write to the base branch")
    path = state.get("allowed_path")
    if path is None:
        candidates = [x["filename"] for x in snapshot["files"] if RUN_PATH.fullmatch(x["filename"]) and x["status"] == "added"]
        if len(candidates) != 1:
            return finish("BLOCKED", "Enrollment requires exactly one newly added RUN contribution JSON")
        path = candidates[0]
    if not RUN_PATH.fullmatch(path):
        return finish("BLOCKED", "Invalid enrolled contribution path")
    result["allowed_path"] = path
    try:
        closure_present = observed_closure(snapshot, path)
    except Blocked as error:
        return finish("BLOCKED", str(error))
    remaining = next((x for x in snapshot["files"] if x["filename"] == path), None)
    extra = [x for x in snapshot["files"] if x["filename"] != path]
    if extra and not policy["admission_attests_entire_diff"]:
        return finish("BLOCKED", "Nonproposal changes require a configured independent admission attestation covering the entire diff and its provenance")
    if remaining is None or remaining["status"] in ("removed", "renamed"):
        if not (policy["admission_attests_entire_diff"] and policy["admission_may_consume_proposal"]):
            return finish("BLOCKED", "Enrolled contribution disappeared without explicit admission-consumption policy")
    if pr["isDraft"]:
        return finish("WAITING_REVIEW", "Draft PR; a maintainer must mark it ready for review")
    groups = check_groups(snapshot, policy)
    result["checks"] = groups
    result["feedback"] = feedback_items(snapshot, policy, state)
    result["failures"] = groups["failed"]
    if groups["ambiguous"]:
        return finish("BLOCKED", "Required check origin is ambiguous; pin the expected App")
    missing_closure_reason = ("Materialized closure is missing at " + closure_path(path) + ". "
                              "The authoring agent must perform PR-side admission, commit the canonical outputs and closure, "
                              "and run the trusted compiler. This optional worker cannot perform or hand off that job")
    if result["feedback"] or groups["failed"]:
        scope_blocker = proposal_repair_blocker(snapshot, path)
        if scope_blocker:
            return finish("BLOCKED", scope_blocker)
        if not closure_present and any(matches_spec(check, spec) for check in groups["failed"] for spec in policy["admission_checks"]):
            return finish("BLOCKED", missing_closure_reason)
        if owner == "originating_task":
            return finish("BLOCKED", "The originating task must address the observed CI/review feedback and retain its research context. This integration observes only; it cannot resume that task or launch a replacement authoring model")
        if not policy["amendments"]["authorized"]:
            return finish("BLOCKED", "Contribution amendments are not authorized by configured repository policy")
        fp = digest({"head": snapshot["head"], "feedback": result["feedback"], "failures": sorted({(x["kind"], x["name"], str(x["app_id"]), str(x["id"]), str(x["result"])) for x in groups["failed"]})})
        result["fingerprint"] = fp
        if state.get("attempts", 0) >= policy["max_attempts_per_pr"] or state.get("feedback_attempts", {}).get(fp, 0) >= policy["max_attempts_per_feedback"]:
            return finish("BLOCKED", "Repair budget consumed for this PR or unchanged feedback; independent intervention required")
        changed = next((x for x in snapshot["files"] if x["filename"] == path), None)
        if not changed or changed["status"] not in ("added", "modified"):
            return finish("BLOCKED", "Enrolled contribution was removed or renamed; the authoring agent must handle the full admission amendment")
        result["repair"] = True
        return finish("NEEDS_FIX", "New actionable CI failure or review feedback")
    if not closure_present:
        return finish("BLOCKED", missing_closure_reason)
    admission_names = {x["name"] for x in policy["admission_checks"]}
    if admission_names.intersection(groups["missing"]):
        return finish("BLOCKED", "Closure file exists, but configured admission validation has not been observed. The authoring agent must verify the actual workflow/run; no admission worker is assumed")
    if admission_names.intersection(groups["pending"]):
        return finish("WAITING_CI", "Closure file exists; observed admission validation is pending. The authoring agent retains responsibility.")
    if groups["missing"] or groups["pending"]:
        return finish("WAITING_CI", "Applicable CI is missing or pending")
    decisive = {}
    for review in sorted(snapshot["reviews"], key=lambda x: x["id"]):
        if review["state"] in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
            decisive[review["user"]["login"]] = review
    if any(x["state"] == "CHANGES_REQUESTED" for x in decisive.values()):
        return finish("WAITING_REVIEW", "An independent review still requests changes")
    approvals = [login for login, x in decisive.items() if login in independent_logins(snapshot, policy) and x["state"] == "APPROVED" and x.get("commit_id") == snapshot["head"]]
    result["independent_approvals"] = approvals
    if len(approvals) < policy["reviews"]["minimum"] or pr["reviewDecision"] in ("REVIEW_REQUIRED", "CHANGES_REQUESTED"):
        return finish("WAITING_REVIEW", "Independent approval of the current head is still required")
    if any(not t["isResolved"] for t in snapshot["threads"]):
        return finish("WAITING_REVIEW", "Review threads remain unresolved; only independent confirmation can close them")
    if pr["mergeable"] != "MERGEABLE" or pr["mergeStateStatus"] != "CLEAN":
        return finish("WAITING_RULES", "GitHub normal merge eligibility is " + str(pr["mergeable"]) + "/" + str(pr["mergeStateStatus"]))
    if not pr.get("potentialMergeCommit"):
        return finish("WAITING_RULES", "GitHub is still generating the current test-merge commit")
    if any(r["type"] == "merge_queue" for r in snapshot["rules"]):
        return finish("READY_FOR_QUEUE", "Underlying checks pass; required merge-queue processing is still pending")
    return finish("READY_FOR_MERGE", "Fresh current-head/base observation satisfies explicit policy and GitHub normal merge eligibility. This is an intermediate observation; the originating task must carry out any user-authorized ordinary merge and verify MERGED")


def save_state(api, policy, state):
    state = copy.deepcopy(state)
    comment_id = state.pop("comment_id", None)
    if comment_id:
        current = api.get(f"/repos/{api.repo}/issues/comments/{comment_id}")
        actual = get_state(api, policy, state["pr"], [current])
        if actual["revision"] != state["revision"]:
            raise Blocked("Controller checkpoint changed concurrently")
    state["revision"] += 1
    encoded = canonical({"data": state, "hmac_sha256": sign_state(state)}).replace("<", "\\u003c").replace(">", "\\u003e")
    if len(encoded.encode()) > 48000:
        raise Blocked("Durable checkpoint exceeded size limit; operator recovery required")
    reason = html.escape(state.get("reason", "")).replace("@", "&#64;")
    summary = html.escape(state.get("worker_summary", "")).replace("@", "&#64;")
    body = STATE_MARKER + encoded + "\n-->\n## Resolvent follow-up: " + state["status"] + "\n\n" + reason + "\n\n"
    body += "Observed: `" + state.get("observed_at", "unknown") + "`  \nHead: `" + state.get("head", "unknown") + "`  \nBase: `" + state.get("base", "unknown") + "`  \n"
    body += "Policy: `" + state.get("policy_hash", "unknown") + "`  \nAttempts: " + str(state.get("attempts", 0)) + "\n\n"
    if summary:
        body += "Latest worker assessment: " + summary + "\n\n"
    if state.get("assessment"):
        body += "For a non-code disposition, an independent reviewer must inspect this assessment, resolve the relevant threads, and submit a new approval with an empty body or an exact benign approval such as LGTM. Other review text is new feedback.\n\n"
    body += "This is an observation, not an approval or a merge. Required reviewer threads remain under independent review. The originating task retains completion ownership; this integration cannot resume its session.\n"
    if comment_id:
        data = api.api(f"/repos/{api.repo}/issues/comments/{comment_id}", {"body": body}, "PATCH")[0]
    else:
        data = api.api(f"/repos/{api.repo}/issues/{state['pr']}/comments", {"body": body}, "POST")[0]
    if data.get("user", {}).get("login") != policy["controller_login"]:
        raise Blocked("Checkpoint writer does not match configured dedicated App identity")
    state["comment_id"] = data["id"]
    return state


def finish_terminal(api, policy, state):
    state = save_state(api, policy, state)
    if state["status"] in ("MERGED", "CLOSED") and state.get("allowed_path"):
        # The dedicated enrollment label is also the reconciliation registry.
        # Remove it only after the authenticated terminal checkpoint is saved.
        try:
            api.api(f"/repos/{api.repo}/issues/{state['pr']}/labels/" + urllib.parse.quote(policy["enrollment_label"], safe=""), method="DELETE")
        except Blocked:
            # A later scheduled run will retry label cleanup. Terminal evidence
            # remains valid even when this housekeeping request fails.
            print("Terminal checkpoint saved; enrollment-label cleanup will be retried")
    return state


def checkpoint(state, snapshot, decision, policy):
    state = copy.deepcopy(state)
    state.update(status=decision["status"], reason=decision["reason"], observed_at=snapshot["observed_at"], head=snapshot["head"], base=snapshot["base"], policy_hash=digest(policy), trusted_sha=snapshot["trusted_sha"], executed_code_sha=os.environ.get("RESOLVENT_CODE_SHA", "unknown"), run_id=os.environ.get("GITHUB_RUN_ID", "local"), run_attempt=os.environ.get("GITHUB_RUN_ATTEMPT", "1"))
    if decision.get("allowed_path"):
        state["allowed_path"] = decision["allowed_path"]
    evidence = {"complete": snapshot["complete"], "checks": snapshot["checks"], "review_count": len(snapshot["reviews"]), "unresolved_threads": sum(not t["isResolved"] for t in snapshot["threads"]), "normal_merge_state": snapshot["pr_data"]["mergeStateStatus"], "independent_approvals": decision.get("independent_approvals", []), "rule_types": sorted({r["type"] for r in snapshot["rules"]}), "admission_observation": snapshot.get("admission_observation")}
    state["evidence"] = {"complete": evidence["complete"], "sha256": digest(evidence), "check_count": len(snapshot["checks"]), "unresolved_threads": evidence["unresolved_threads"], "normal_merge_state": evidence["normal_merge_state"], "independent_approvals": evidence["independent_approvals"], "admission_observation": evidence["admission_observation"]}
    return state


def diagnostics(api, snapshot, failures):
    result = []
    for check in failures[:5]:
        if check["kind"] == "check":
            try:
                annotations = api.pages(f"/repos/{api.repo}/check-runs/{check['id']}/annotations")
                result.append({"check": check["name"], "annotations": annotations[:20], "annotations_truncated": len(annotations) > 20})
            except Blocked:
                result.append({"check": check["name"], "annotations": "unavailable"})
    try:
        runs = api.pages(f"/repos/{api.repo}/actions/runs?head_sha={snapshot['head']}", "workflow_runs")
        count = 0
        for run in sorted(runs, key=lambda x: x["id"], reverse=True):
            if run["conclusion"] not in ("failure", "timed_out", "cancelled", "action_required"):
                continue
            jobs = api.pages(f"/repos/{api.repo}/actions/runs/{run['id']}/jobs?filter=latest", "jobs")
            for job in jobs:
                if job.get("conclusion") in ("failure", "timed_out", "cancelled", "action_required"):
                    result.append({"job": job["name"], "run_id": run["id"], "job_id": job["id"], "log": api.logs(job["id"])})
                    count += 1
                    if count >= 3:
                        return result
    except Blocked:
        result.append({"logs": "Actions diagnostics unavailable; do not invent their contents"})
    return result


def verify_policy_at_default(api, policy, snapshot):
    if os.environ.get("RESOLVENT_CODE_SHA") != snapshot["trusted_sha"]:
        raise Blocked("Executed controller SHA differs from the current trusted default branch; rerun with fresh code")
    raw = api.file(snapshot["trusted_sha"], ".github/resolvent/policy.json")
    if digest(strict_json(raw)) != digest(policy):
        raise Blocked("Trusted default-branch policy changed; next run must reload it")


def make_work(api, policy, snapshot, decision):
    require_bounded_worker(policy)
    path = decision["allowed_path"]
    scope_blocker = proposal_repair_blocker(snapshot, path)
    if scope_blocker:
        raise Blocked(scope_blocker)
    raw = api.file(snapshot["head"], path)
    contribution = strict_json(raw)
    if not isinstance(contribution, dict) or contribution.get("id") != RUN_PATH.fullmatch(path).group(1):
        raise Blocked("Contribution identity does not match its enrolled filename")
    schema = strict_json(api.file(snapshot["base"], policy["schema_path"]))
    from schema_subset import inspect_schema
    inspect_schema(schema)
    packet = {"version": 1, "repository": api.repo, "pr": snapshot["pr"], "head": snapshot["head"], "base": snapshot["base"], "policy_hash": digest(policy), "allowed_path": path, "contribution_json": raw.decode("utf-8"), "schema": schema, "feedback": decision["feedback"], "failed_checks": decision["failures"], "diagnostics": diagnostics(api, snapshot, decision["failures"])}
    packet["trusted_contracts"] = [{"path": p, "base": snapshot["base"], "content": api.file(snapshot["base"], p).decode("utf-8")} for p in policy["amendments"]["contract_paths"]]
    if len(canonical(packet).encode()) > policy["max_input_bytes"]:
        raise Blocked("Work packet exceeds max_input_bytes; a foreground agent must narrow the contribution/context")
    # A secret accidentally present in an untrusted diagnostic is never sent on.
    ensure_no_local_secrets(canonical(packet))
    return packet


def ensure_no_local_secrets(text):
    candidates = []
    pending = [text]
    while pending:
        value = pending.pop()
        if isinstance(value, str):
            candidates.append(value)
            try:
                # Packets contain serialized JSON in contribution_json and can
                # nest it again. Decode each JSON string through to its leaves.
                # Preserve duplicate members so none can hide a credential.
                pending.append(json.loads(value, object_pairs_hook=lambda pairs: [part for pair in pairs for part in pair]))
            except (ValueError, TypeError):
                pass
            except RecursionError:
                raise Blocked("Nested work packet cannot be safely screened for credentials") from None
        elif isinstance(value, dict):
            pending.extend(value.keys())
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
    for key in WRITER_CREDENTIALS + ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        secret = os.environ.get(key)
        # Inspect decoded strings and serialized forms, including JSON nested
        # inside contribution_json. Quotes, backslashes, controls and Unicode
        # escaping cannot hide a locally available credential.
        forms = (secret, json.dumps(secret, ensure_ascii=False)[1:-1], json.dumps(secret, ensure_ascii=True)[1:-1]) if secret else ()
        if any(form in candidate for form in forms for candidate in candidates):
            raise Blocked("Local credential found in work packet; refusing provider transmission")


def worker_prompt():
    prompt = (HERE / "worker_prompt.md").read_text()
    for name in ("PR_FOLLOWUP.md", "SUBMISSION.md", "GITHUB_ACCESS.md", "ADMISSION.md"):
        path = HERE / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 131072:
            raise Blocked("Installed trusted shared contract is missing or oversized: " + name)
        prompt += "\n\nShared portable contract " + name + ":\n" + path.read_text()
    prompt += "\n\nYour role is the explicitly opted-in legacy bounded data-only proposal worker. The default originating_task mode never invokes you. Foreground admission, continuation, and merge instructions apply to the originating task, not to your capabilities. You cannot materialize or regenerate canonical records or closure, resume a session, launch another agent, merge a PR, or promise future work. The trusted controller performs GitHub observation and permitted proposal publication. Do not claim to have run tools, submitted a review, published a commit, or merged anything."
    return prompt


def assert_worker_environment():
    if any(os.environ.get(key) for key in WRITER_CREDENTIALS):
        raise Blocked("Provider job must not receive GitHub writer or checkpoint credentials")


def observe(api, number, policy, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    state = None
    authorized = False
    try:
        existing_comments = api.pages(f"/repos/{api.repo}/issues/{number}/comments")
        state = get_state(api, policy, number, existing_comments)
        existing_pr = api.get(f"/repos/{api.repo}/pulls/{number}")
        authorized = bool(state.get("allowed_path")) or (existing_pr["user"]["login"] in policy["allowed_authors"] and policy["enrollment_label"] in {x["name"] for x in existing_pr["labels"]})
        if not authorized:
            plan = {"version": 1, "repository": api.repo, "pr": number, "policy_hash": digest(policy), "repair": False, "decision": {"status": "DISABLED", "reason": "No authorized enrollment; no checkpoint written"}}
            write_json(out / "plan.json", plan)
            return plan
        snapshot = collect(api, number, policy, state.get("allowed_path"))
        comments = snapshot["issue_comments"] if snapshot["pr_data"]["state"] == "OPEN" else api.pages(f"/repos/{api.repo}/issues/{number}/comments")
        state = get_state(api, policy, number, comments)
        decision = evaluate(snapshot, policy, state)
        plan = {"version": 1, "repository": api.repo, "pr": number, "policy_hash": digest(policy), "snapshot": snapshot, "decision": decision, "state": state, "repair": False}
        if decision["status"] == "DISABLED":
            if state.get("comment_id"):
                plan["state"] = save_state(api, policy, checkpoint(state, snapshot, decision, policy))
            write_json(out / "plan.json", plan)
            return plan
        verify_policy_at_default(api, policy, snapshot)
        state = checkpoint(state, snapshot, decision, policy)
        if decision["repair"]:
            packet = make_work(api, policy, snapshot, decision)
            state["attempts"] += 1
            fp = decision["fingerprint"]
            state["feedback_attempts"][fp] = state["feedback_attempts"].get(fp, 0) + 1
            state["inflight"] = {"head": snapshot["head"], "base": snapshot["base"], "fingerprint": fp, "run_id": state["run_id"], "run_attempt": state["run_attempt"]}
            plan["repair"] = True
            plan["work_digest"] = digest(packet)
            write_json(out / "work.json", packet)
        plan["state"] = finish_terminal(api, policy, state)
        write_json(out / "plan.json", plan)
        return plan
    except Blocked as error:
        # Persist a failure checkpoint when possible, never a stale green result.
        if not authorized:
            raise
        if state is None:
            state = get_state(api, policy, number)
        state.update(status="BLOCKED", reason=str(error), observed_at=now(), policy_hash=digest(policy), run_id=os.environ.get("GITHUB_RUN_ID", "local"), run_attempt=os.environ.get("GITHUB_RUN_ATTEMPT", "1"))
        state["evidence"] = {"complete": False}
        state = save_state(api, policy, state)
        plan = {"version": 1, "repository": api.repo, "pr": number, "policy_hash": digest(policy), "state": state, "repair": False, "decision": {"status": "BLOCKED", "reason": str(error)}}
        write_json(out / "plan.json", plan)
        return plan


def validate_proposal(proposal, packet, policy):
    if not isinstance(proposal, dict) or set(proposal) != {"outcome", "summary", "replacement_json", "addressed_feedback_ids"}:
        raise Blocked("Provider output does not match the proposal contract")
    if proposal["outcome"] not in ("replace", "no_change", "blocked"):
        raise Blocked("Unknown provider outcome")
    if not isinstance(proposal["summary"], str) or not 1 <= len(proposal["summary"]) <= 4000:
        raise Blocked("Provider summary is missing or too large")
    ids = proposal["addressed_feedback_ids"]
    if not isinstance(ids, list) or not all(isinstance(x, str) for x in ids) or len(ids) > 200 or not set(ids) <= {x["id"] for x in packet["feedback"]}:
        raise Blocked("Provider claimed feedback outside the observed work packet")
    if proposal["outcome"] != "replace":
        if proposal["replacement_json"] is not None:
            raise Blocked("Non-replacement outcome must not supply replacement bytes")
        return None
    content = proposal["replacement_json"]
    if not isinstance(content, str) or len(content.encode()) > min(MAX_FILE, policy["max_input_bytes"]):
        raise Blocked("Replacement JSON is missing or exceeds its size bound")
    value, before = strict_json(content), strict_json(packet["contribution_json"])
    if not isinstance(value, dict):
        raise Blocked("Contribution must be a JSON object")
    for key in ("id", "schema_version", "input_method", "created_at", "researcher", "parent_run_id"):
        if value.get(key) != before.get(key):
            raise Blocked("Replacement alters immutable contribution identity/attribution: " + key)
    if value.get("id") != RUN_PATH.fullmatch(packet["allowed_path"]).group(1):
        raise Blocked("Replacement ID does not match enrolled path")
    try:
        validate(value, packet["schema"])
    except Invalid as error:
        raise Blocked("Replacement does not satisfy trusted schema: " + str(error)) from None
    if canonical(value) == canonical(before):
        raise Blocked("Replacement contains no substantive JSON change")
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


def call_provider(policy, packet, prompt):
    require_bounded_worker(policy)
    prompt += "\n\nRepository-authorized amendment contracts, read from the trusted base commit:\n" + canonical(packet.get("trusted_contracts", []))
    data = canonical(packet)
    if len(data.encode()) + len(prompt.encode()) > policy["max_input_bytes"]:
        raise Blocked("Provider input limit exceeded")
    ensure_no_local_secrets(data)
    provider = policy["provider"]
    if provider == "openai":
        token = os.environ.get("OPENAI_API_KEY")
        if not token:
            raise Blocked("OPENAI_API_KEY is not configured")
        body = {"model": policy["model"], "instructions": prompt, "input": data, "max_output_tokens": policy["max_output_tokens"], "store": False}
        raw, _ = request("https://api.openai.com/v1/responses", {"Authorization": "Bearer " + token, "Content-Type": "application/json"}, body, "POST", timeout=600)
        response = strict_json(raw)
        if response.get("status") != "completed":
            raise Blocked("OpenAI response was not complete")
        text = "".join(c["text"] for item in response.get("output", []) if item.get("type") == "message" for c in item.get("content", []) if c.get("type") == "output_text")
    elif provider == "anthropic":
        token = os.environ.get("ANTHROPIC_API_KEY")
        if not token:
            raise Blocked("ANTHROPIC_API_KEY is not configured")
        body = {"model": policy["model"], "system": prompt, "messages": [{"role": "user", "content": data}], "max_tokens": policy["max_output_tokens"]}
        raw, _ = request("https://api.anthropic.com/v1/messages", {"x-api-key": token, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}, body, "POST", timeout=600)
        response = strict_json(raw)
        if response.get("stop_reason") != "end_turn":
            raise Blocked("Claude response was not complete")
        text = "".join(c["text"] for c in response.get("content", []) if c.get("type") == "text")
    else:
        raise Blocked("Provider is not configured")
    # The model has no tools. This string is parsed as JSON, never executed.
    proposal = strict_json(text)
    validate_proposal(proposal, packet, policy)
    return proposal


def publish(api, number, policy, plan, packet, proposal):
    require_bounded_worker(policy)
    if not plan.get("repair") or plan.get("repository") != api.repo or plan.get("pr") != number or plan.get("policy_hash") != digest(policy) or plan.get("work_digest") != digest(packet):
        raise Blocked("Publisher received an invalid or mismatched observation artifact")
    original = plan["snapshot"]
    # Freshly reacquire current PR, rules, checks, reviews and threads. Never trust
    # a worker's readiness claim or a branch name supplied by its output.
    fresh = collect(api, number, policy, packet["allowed_path"])
    state = get_state(api, policy, number, fresh["issue_comments"] if fresh["pr_data"]["state"] == "OPEN" else None)
    expected = plan["state"].get("inflight")
    if state.get("inflight") != expected or state.get("revision") != plan["state"]["revision"]:
        raise Blocked("Repair reservation no longer belongs to this run")
    verify_policy_at_default(api, policy, fresh)
    evaluation_state = copy.deepcopy(state)
    # The current reservation already consumed one attempt. Re-evaluate real
    # current actionability without mistaking our own reservation for exhaustion.
    if expected:
        evaluation_state["attempts"] -= 1
        evaluation_state["feedback_attempts"][expected["fingerprint"]] -= 1
    decision = evaluate(fresh, policy, evaluation_state)
    state = checkpoint(state, fresh, decision, policy)
    if fresh["pr_data"]["state"] != "OPEN" or decision["status"] == "DISABLED":
        state.pop("inflight", None)
        return finish_terminal(api, policy, state)
    if (fresh["head"], fresh["base"]) != (original["head"], original["base"]):
        state.update(status="BLOCKED", reason="Head or base advanced while the provider worked; stale proposal discarded")
        state.pop("inflight", None)
        return save_state(api, policy, state)
    if not decision.get("repair"):
        state.pop("inflight", None)
        return save_state(api, policy, state)
    if decision.get("fingerprint") != plan["decision"].get("fingerprint"):
        state.update(status="BLOCKED", reason="CI/review feedback changed while the provider worked; stale proposal discarded")
        state.pop("inflight", None)
        return save_state(api, policy, state)
    if fresh["pr_data"]["isDraft"] or not fresh["same_repo"] or fresh["pr_data"]["baseRefName"] != (policy.get("base_branch") or fresh["default_branch"]):
        raise Blocked("PR scope changed before publication")
    if not policy["amendments"]["authorized"]:
        raise Blocked("Amendments are not authorized")
    if packet["allowed_path"] != state.get("allowed_path") or not RUN_PATH.fullmatch(packet["allowed_path"]):
        raise Blocked("Worker attempted a path outside the enrolled contribution")
    raw = api.file(fresh["head"], packet["allowed_path"])
    if raw.decode("utf-8") != packet["contribution_json"]:
        raise Blocked("Enrolled contribution bytes changed")
    schema = strict_json(api.file(fresh["base"], policy["schema_path"]))
    if digest(schema) != digest(packet["schema"]):
        raise Blocked("Authoritative schema changed")
    replacement = validate_proposal(proposal, packet, policy)
    state["worker_summary"] = proposal["summary"]
    state.pop("inflight", None)
    if replacement is None:
        state.update(status="BLOCKED", reason="Provider returned " + proposal["outcome"] + "; independent review/intervention is required")
        state["assessment"] = {"head": fresh["head"], "recorded_at": now(), "last_review_id": max((r["id"] for r in fresh["reviews"]), default=0), "feedback_ids": [x["id"] for x in packet["feedback"]], "outcome": proposal["outcome"]}
        return save_state(api, policy, state)
    # GraphQL atomically checks the current branch head and appends one commit.
    # No force push, merge, branch-protection bypass, or PR-controlled script.
    q = """mutation($input:CreateCommitOnBranchInput!){createCommitOnBranch(input:$input){commit{oid url}}}"""
    variables = {"input": {"branch": {"repositoryNameWithOwner": api.repo, "refName": fresh["pr_data"]["headRefName"]}, "expectedHeadOid": fresh["head"], "message": {"headline": "Address Resolvent contribution CI/review feedback"}, "fileChanges": {"additions": [{"path": packet["allowed_path"], "contents": base64.b64encode(replacement).decode()}]}, "clientMutationId": "resolvent-" + str(number) + "-" + fresh["head"]}}
    commit = api.gql(q, variables)["createCommitOnBranch"]["commit"]
    verified = api.get(f"/repos/{api.repo}/commits/{commit['oid']}")
    files = verified.get("files", [])
    if [x["sha"] for x in verified["parents"]] != [fresh["head"]] or len(files) != 1 or files[0]["filename"] != packet["allowed_path"] or api.file(commit["oid"], packet["allowed_path"]) != replacement:
        raise Blocked("Published commit verification failed; inspect before further work")
    state["handled_feedback_ids"] = sorted(set(state.get("handled_feedback_ids", [])) | set(proposal["addressed_feedback_ids"]))
    state.pop("assessment", None)
    state.update(status="WAITING_CI", reason="Proposal correction committed; new-head CI is pending. The authoring agent must complete PR-side admission and obtain independent review", head=commit["oid"], observed_at=now(), published_commit=commit["oid"])
    state["evidence"]["complete"] = False
    return save_state(api, policy, state)


def outputs(values):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            for key, val in values.items():
                value = val if isinstance(val, str) else canonical(val)
                if "\n" in value or "\r" in value:
                    raise Blocked("Multiline workflow output rejected")
                handle.write(key + "=" + value + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["discover", "observe", "work", "publish", "validate-policy"])
    parser.add_argument("--policy", default=str(HERE / "policy.json"))
    parser.add_argument("--pr", type=int)
    parser.add_argument("--out", default="resolvent-work")
    parser.add_argument("--plan")
    parser.add_argument("--packet")
    parser.add_argument("--proposal")
    args = parser.parse_args()
    policy = load_policy(args.policy)
    if args.command == "validate-policy":
        print("Policy is structurally valid; enabled=" + str(policy["enabled"]).lower())
        return
    if not policy["enabled"]:
        outputs({"enabled": "false", "matrix": {"include": []}, "repair": "false"})
        print("DISABLED: no network calls or writes")
        return
    if args.command == "work":
        require_bounded_worker(policy)
        # Run in its own Actions job. Credentials for committing/checkpoints must
        # not be passed in even though no shell/model tools exist in this adapter.
        assert_worker_environment()
        packet = read_json(args.packet, policy["max_input_bytes"])
        try:
            proposal = call_provider(policy, packet, worker_prompt())
        except (Blocked, Invalid) as error:
            proposal = {"outcome": "blocked", "summary": "Provider attempt failed: " + str(error), "replacement_json": None, "addressed_feedback_ids": []}
        write_json(args.proposal, proposal)
        print("Provider outcome: " + proposal["outcome"])
        return
    if os.environ.get("GITHUB_REPOSITORY") and os.environ["GITHUB_REPOSITORY"].lower() != policy["repository"].lower():
        raise Blocked("Workflow repository differs from configured target")
    api = GitHub(policy["repository"])
    if args.command == "discover":
        rows = api.pages(f"/repos/{api.repo}/pulls?state=open")
        selected = [x["number"] for x in rows if policy["enrollment_label"] in {l["name"] for l in x["labels"]} and x["user"]["login"] in policy["allowed_authors"]]
        closed = api.pages(f"/repos/{api.repo}/issues?state=closed&labels=" + urllib.parse.quote(policy["enrollment_label"], safe=""))
        for issue in closed:
            if "pull_request" not in issue or issue["user"]["login"] not in policy["allowed_authors"]:
                continue
            # Discovery uses only read credentials. This is a candidate filter;
            # the per-PR observer authenticates the entire checkpoint before any
            # terminal write or cleanup. Never enroll a closed PR from a label.
            comments = api.pages(f"/repos/{api.repo}/issues/{issue['number']}/comments")
            if any(c.get("user", {}).get("login") == policy["controller_login"] for c in comments):
                selected.append(issue["number"])
        # Include a directly referenced terminal PR for its final checkpoint.
        if args.pr and args.pr not in selected:
            selected.append(args.pr)
        if len(selected) > policy["max_open_prs"]:
            raise Blocked("Enrolled PR count exceeds max_open_prs; narrow enrollment")
        metadata = api.get(f"/repos/{api.repo}")
        branch = api.get(f"/repos/{api.repo}/git/ref/heads/" + urllib.parse.quote(metadata["default_branch"], safe=""))
        outputs({"enabled": "true" if selected else "false", "matrix": {"include": [{"pr": n} for n in selected]}, "trusted_sha": branch["object"]["sha"]})
        print("Enrolled PRs: " + ", ".join(map(str, selected)))
        return
    if not args.pr or args.pr < 1:
        raise Blocked("A positive --pr is required")
    slug = os.environ.get("RESOLVENT_APP_SLUG")
    if slug is not None and slug + "[bot]" != policy["controller_login"]:
        raise Blocked("GitHub App identity does not match controller_login")
    if args.command == "observe":
        plan = observe(api, args.pr, policy, args.out)
        outputs({"repair": str(plan["repair"]).lower(), "status": plan["decision"]["status"]})
        print(plan["decision"]["status"] + ": " + plan["decision"]["reason"])
    elif args.command == "publish":
        plan, packet = read_json(args.plan), read_json(args.packet, policy["max_input_bytes"])
        if args.proposal and Path(args.proposal).is_file():
            proposal = read_json(args.proposal, MAX_FILE * 2)
        else:
            proposal = {"outcome": "blocked", "summary": "Provider job produced no valid artifact; attempt remains counted", "replacement_json": None, "addressed_feedback_ids": []}
        try:
            state = publish(api, args.pr, policy, plan, packet, proposal)
        except (Blocked, Invalid) as error:
            state = get_state(api, policy, args.pr)
            if state.get("revision") != plan.get("state", {}).get("revision") or state.get("inflight") != plan.get("state", {}).get("inflight"):
                raise Blocked("Stale publisher cannot alter a newer controller checkpoint") from error
            state.update(status="BLOCKED", reason="Publication stopped: " + str(error), observed_at=now())
            state["evidence"] = {"complete": False}
            state.pop("inflight", None)
            state = save_state(api, policy, state)
        print(state["status"] + ": " + state["reason"])


if __name__ == "__main__":
    try:
        main()
    except (Blocked, Invalid, KeyError, TypeError, ValueError) as error:
        print("BLOCKED: " + str(error), file=sys.stderr)
        sys.exit(2)
