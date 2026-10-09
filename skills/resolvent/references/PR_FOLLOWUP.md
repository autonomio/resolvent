# Shared PR completion contract

Apply this contract in ChatGPT, Codex and Claude, using either authorized connector
tools or the existing authenticated CLI described in `GITHUB_ACCESS.md`. Opening a
pull request is an intermediate checkpoint. Read `TARGET.md` for the task-selected
destination, actual scope and user authorization. In a full contribution workflow, the
originating task owns all authoring and the ordinary authorized merge after external
independent review; successful completion is verified **MERGED**. `READY_FOR_MERGE`
is an internal action trigger under `MERGE.md`. Honour an explicit narrower stopping
instruction. Never bypass rules, self-approve or enable GitHub auto-merge as a shortcut.

## Contents

- [Establish the evidence](#establish-the-evidence-for-this-pr)
- [Follow the current revision](#follow-the-current-revision)
- [Complete admission and correct the contribution](#complete-admission-and-correct-the-contribution)
- [Act on verified readiness](#act-on-verified-readiness)
- [Keep waiting honest and bounded](#keep-waiting-honest-and-bounded)
- [Status and user receipt](#status-and-user-receipt)

## Establish the evidence for this PR

Read the target repository's approved contracts, applicable `AGENTS.md`/`CLAUDE.md`
instructions, admission process and branch/ruleset requirements. Read `ADMISSION.md`
to perform the invoking agent's PR-side admission duties. Determine which
CI checks/statuses, independent approvals, conversation resolutions, admission
results, base freshness requirements and merge-queue rules actually apply. Include
all CI that the repository's explicit policy expects to be green, even if GitHub
does not mark it as a required branch check. Exclusions and accepted skipped/neutral
conclusions must come from deliberate, auditable repository policy; the contributor
cannot infer them from an optional label or to ignore a red result. If a material
requirement cannot be established from sufficient authorized evidence, preserve
that as a verification blocker. An administration-only endpoint denial is not
automatically such a blocker; use the alternative evidence procedure in `MERGE.md`.

Verify the repository, PR number/URL, contribution branch, base branch, run ID and
the provenance of changed-file paths. Contributor-authored edits may include the
normalized input, authorized canonical additions/updates and the run's required
brief/result/closure artifacts. Preserve and inspect collaborator changes, including
other legitimate admission work. Verify their provenance and contract scope;
arbitrary extra files are not automatically authorized admission. Record the current
head commit, current target-base tip, relevant test-merge/queue revision where
applicable, and observation time. Inspect the complete applicable CI/check/status,
review and thread results, including paginated records. A summary badge or previously
returned PR URL is insufficient.

## Follow the current revision

During the active task, finish missing admission work, handle justified contribution
corrections, observe progress and re-read the actual GitHub state. A proposal-only PR
or "Awaiting admission agent" check is a prompt to inspect and execute the approved
admission job, not a reason to assume another worker. Evaluate these conditions together:

| Area | Evidence needed before the guarded merge |
|---|---|
| PR identity and scope | Expected repository/base and an open PR eligible for normal merge. The input, canonical records and required execution artifacts belong to the authorized contribution. Collaborator work is accounted for and preserved; governance/unrelated changes are excluded by actual-delta validation. |
| Check freshness | All applicable CI and every required check/status have their policy-accepted terminal result for the expected current head or required test-merge revision, from the required producer. No applicable check is missing, pending, failed, cancelled, stale or unverified; an optional label alone cannot exclude a red check. |
| Base freshness | Checks and mergeability satisfy the repository's update policy for the currently observed base tip. An earlier head/base pair cannot establish freshness after either changes. |
| Independent review | All required approvals remain valid for the current revision under repository policy, with no outstanding changes-requested decision. The contributor or its own producing agent cannot substitute for an independent reviewer. |
| Review threads | Required conversations are resolved and material reviewer requests are demonstrably addressed. A new commit or an author reply alone does not resolve a review requirement. |
| Admission | Every candidate has an explicit disposition; justified canonical records and the matching closure are materialized and pass trusted state/delta validation. Required admission checks refer to the relevant run/revision. This execution evidence does not establish independent semantic review. |
| Normal merge eligibility | GitHub's current mergeability and repository gates allow the user's ordinary merge action. Unknown, conflicting, blocked, draft or queue-only eligibility is not direct merge readiness. |

Use the repository's explicit accepted conclusions and audited exclusions for every
applicable check; do not turn neutral/skipped/optional results into approval by
assumption. Inspect failing checks and requested changes before acting. Preserve
uncertainty if checks certify only a head commit and the required relationship to
the current base cannot be established. A cached approval or a dismissed review does not manufacture independent
review; apply the repository's rules for subsequent changes and stale approvals.

Immediately before acting on readiness, re-read the PR's head, base tip and gating
state. If they changed, invalidate the previous result and repeat the relevant
verification. Record checked revisions and observation time; readiness describes
that observed snapshot and may change afterward. The merge requires an expected-head
guard, not just this preflight observation.

## Complete admission and correct the contribution

Own the normalized input and its authorized materialized outputs. Finish missing
canonical decomposition under `ADMISSION.md`; do not ask the researcher to perform
routine admission work that your tools/contracts permit. Fix defects in the input,
canonical records, evidence links and closure when the user's scope, supplied
evidence and live contract justify the change. Follow `SUBMISSION.md` to distinguish
identical-byte transport retries from amended/successor submissions. Preserve source
anchors, uncertainty and route restrictions. Do not manufacture evidence, rerun a
conversation's research, or approve an assumption merely to satisfy a check.

An input amendment or changed admission decision requires rebuilding correlated
artifacts under the live tool's supported behavior. Never retain a stale closure,
patch its digest to match new input, or rewrite merged immutable records. Validate
the complete proposed state and actual base delta, not just a corrected JSON file.

After a correction, verify the new remote content/head and reassess all required
checks, independent review, threads and admission. Do not assume an old success or
approval covers the new revision. Do not dismiss an unfavorable review, declare a
blocking thread resolved without its issue being addressed, or alter a required
gate. Any permitted review-thread action must follow repository policy and the
current task's authorization; the contributor cannot replace the reviewer's judgment.

Do not alter governance, schemas, workflows, branch protection, runner setup or this
skill to make the contribution pass. Canonical corrections must stay within this
contribution's approved admission/maintenance scope and preserve provenance. If a
fix requires a separate governance or maintenance job, identify the exact contract
boundary and required action rather than weakening the gate.
Do not overwrite unfamiliar collaborator changes or force-update shared history.

## Act on verified readiness

When the authorized full task reaches `READY_FOR_MERGE`, perform the ordinary guarded
merge under `MERGE.md` and independently verify the actual result. Do not return a
successful final answer inviting the user to merge work they already delegated.
External agents provide real independent reviews; the originating task makes the
substantive corrections and merge. Preserve actual host approval requirements.

Use the currently enabled repository merge method and exact expected head. If a
required queue or asynchronous operation accepts the request, keep observing until
`MERGED` or a concrete failure. A timeout or lost response requires read-back before
retrying. Never use merge requests as polling or confuse accepted/queued with merged.
If the user explicitly stopped this task before merge or the repository/PR falls
outside the authorized full task, respect that boundary and report the authorized endpoint.

## Keep waiting honest and bounded

Use `CONTINUATION.md`. Keep this originating task active through pending CI/review
and required queue processing within real host/user budgets. Use bounded read-only
waits, reasonable backoff and progress updates; ordinary waiting is not completion.
Continue every available authorized correction. Do not invent a short stopping
deadline merely because review has not arrived, or promise infinite execution.

Before a genuine execution interruption, save and verify the selected research
context, evidence/decisions, revisions, pending feedback and any unresolved merge
request. Verify any actual resumption of this same task and its durable checkpoint.
A scheduler, PR comment or contextless model is not proof of that capability. The
legacy proposal-repair worker is outside this ownership model; do not hand it
corrections or merge. An observer may assist only within its verified capabilities.

If execution truly cannot continue, report the exact interruption, last verified
state and actual checkpoint/resumption handle. A verified continuation is pending,
not success. Do not claim background work without an accepted capable resumption.

## Status and user receipt

Keep the substantive research answer primary. Use working statuses in progress
updates while continuing the task. Give a successful final receipt only after the
authorized merge is verified, or at an explicitly narrower requested endpoint.
Any forced interruption must be stated as incomplete and supported by live evidence:

| Status | Meaning |
|---|---|
| READY_FOR_MERGE | Fresh checks, independent review, threads, admission and normal eligibility are verified. In an authorized full task, perform the guarded merge; this is not final success. |
| READY_FOR_QUEUE | Required queue eligibility is verified but enrollment has not yet been confirmed. Use the actual supported guarded operation; remain pending. |
| QUEUED | An actual correlated queue entry has accepted this PR/revision. Keep observing until merge or ejection; entry alone is not success. |
| MERGING | An actual supported asynchronous merge operation is accepted and still pending. Preserve its returned identifier/status and verify the PR; do not invent this state for an ordinary lost response. |
| WAITING_CI | Required current checks, including admission validation, are still pending. Continue observing and handling new results in the originating task. |
| WAITING_REVIEW | Independent review or required conversation resolution is still pending. A human response time is not guaranteed. |
| WAITING_ADMISSION | A genuinely separate, authorized admission job is verified as accepted/running for this exact PR/run, and its result is pending. Include that job's evidence. Missing canonical work alone does not justify this state: perform it under ADMISSION.md or report the concrete BLOCKED reason. |
| WAITING_RULES | Applicable rules or their current verification remain unresolved; readiness has not been established. |
| NEEDS_FIX | A concrete contribution defect, missing materialization or change request needs your justified correction, followed by fresh verification. Continue authorized work during the active task. |
| DISABLED | An optional observer/continuation is not enabled. This does not stop available work in the active originating task or transfer ownership. |
| BLOCKED | A concrete permission, policy, failing gate, unavailable runner or external decision prevents completion. Give the precise action/actor needed and last verified state. |
| MERGED | GitHub verifies this PR actually merged into the intended base. Report the merge revision/time and PR URL; do not infer certainty or completion of deferred research. |
| CLOSED | GitHub reports the PR closed without merge. State any recorded reason and do not claim completion of admission. |
| NOT_SUBMITTED | No verified PR exists. Provide the JSON package and the exact submission failure or missing capability. |

The optional controller reports only states its actual observations establish; its
checkpoint cannot expand capabilities or replace the originating research context.
An observer's `BLOCKED` does not stop work that the originating task can perform
with its own authorized tools.
Readiness from an observer is evidence to recheck, not permission to skip the merge
preconditions. If execution is interrupted without verified resumption, report the
explicit blocker and preserved context rather than ending as if the PR were merged.

When the request is preflight-only, report the capability findings and that no
research or writes were performed; do not start this follow-up loop. Never issue a
MERGED receipt merely because a PR was opened, checks passed or a merge was requested.
