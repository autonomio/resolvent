# Guarded completion through merge

Apply this contract in ChatGPT, Codex and Claude. `TARGET.md` defines task-selected
destination and completion. Establish merge authority from the user's actual request
for this selected repository and contribution; this generic plugin carries no
standing owner delegation. Honour narrower stopping instructions and all actual
host approval requirements.

## Contents

- [Establish the merge scope](#establish-the-merge-scope)
- [Verify the current revision](#verify-the-current-revision)
- [Perform the ordinary guarded operation](#perform-the-ordinary-guarded-operation)
- [Reconcile responses and races](#reconcile-responses-and-races)
- [Verify actual completion](#verify-actual-completion)

## Establish the merge scope

Keep the expected repository, PR number, contribution/run identity, target branch
and the user's delegated or explicit merge authority with the originating task.
Complete the selected contribution on that PR; do not apply the delegation to an
unrelated or governance PR. A request to inspect or update the skill itself does
not authorize merging existing contribution PRs.

For an authorized full task, do not ask again at the end whether to merge. External
review agents perform independent review; the originating task implements all
substantive changes and, after the required approvals/checks, executes the ordinary
merge. Repository instructions prohibiting merging one's corrections **without
independent review** are satisfied by actual independent review; they are not a
blanket ban on the authorized normal merge after that review.

Discover the actual connected merge operation and read its input schema. The GitHub
MCP merge tool inspected for this release exposes `expected_head_sha`; supply the
freshly verified PR head there, even if the tool declares it optional. An existing
authenticated CLI is an alternative only when this host actually exposes it and
its existing authorization covers the task. Inspect its installed help for a
supported equivalent head precondition. Do not invent arguments, use an unguarded
merge as a fallback, or install/access the user's local CLI by assumption.

Read the repository's live enabled merge methods and applicable convention before
choosing a method. Do not hardcode a remembered squash/rebase/merge setting or
change repository settings to enable one. No new credentials, privileges, branch
protections, workflow changes or administrator bypass are authorized by this step.
Do not enable GitHub auto-merge as a substitute for the originating task's loop.
If an actually exposed asynchronous interface includes `bypass_rules`, explicitly
set it to `false`. Do not invent that parameter or an asynchronous feature when the
current tool does not expose it.

## Verify the current revision

Use `PR_FOLLOWUP.md` to collect the complete current state. Immediately before a
merge or required queue operation, verify all of these together:

1. **Identity and scope:** The expected PR remains open against the intended base;
   its complete delta belongs to this task's authorized contribution. Reconcile
   unfamiliar collaborator changes. Do not merge an intentionally draft-only task.
2. **Materialized admission:** The input, canonical records and matching closure
   have passed trusted state and actual-delta validation for the relevant revision.
   Closure presence, a compiler log from an older revision, or a proposal alone
   cannot establish completion.
3. **Checks:** Every current required check/status and every additional applicable
   CI gate has its policy-accepted result from the expected producer. Include the
   full required-check list exposed by the branch summary; do not check only the
   world-model compiler while another visible required check remains red/pending.
   Require the correct current head and relevant test-merge/queue revision.
4. **Independent review:** Read actual external reviewer decisions and substantive
   feedback. Required approvals must still cover the current revision under policy;
   no outstanding changes-requested decision or unresolved required discussion may
   be ignored. The author's own producing task or identity does not replace review.
5. **Base freshness:** Read the current target tip. Satisfy the repository's actual
   up-to-date-branch or merge-queue requirements and revalidate if the base advanced.
   A textually clean merge is not proof of a clean knowledge-model delta.
6. **Normal eligibility:** GitHub's current ordinary merge state and applicable
   rules permit the operation. Unknown/conflicting/draft/blocked state must be
   resolved through authorized work, not overridden.

Read required checks through authorized branch summaries and live PR/check state,
and review requirements through trusted base instructions and available rule data.
An administration-only protection endpoint returning 403 does not by itself prove
that ordinary merge permission is absent or that known requirements cannot be
verified. Use sufficient authorized alternative evidence instead. Do not seek new
admin scope or probe a forbidden route. If a material requirement genuinely remains
unknown, or live evidence conflicts, report that precise blocker; do not infer an
all-clear from incomplete data or a green badge.

Record the observed head/base, check/review evidence and observation time. If either
revision changes before the operation, discard readiness and repeat the affected
validation and review steps. The head precondition protects the reviewed source
revision; it does not claim an atomic target-base precondition. Rely on the normal
repository-enforced update/queue gates for their actual guarantees. If the required
base-freshness guarantee cannot be established, do not bypass it.

## Perform the ordinary guarded operation

Treat `READY_FOR_MERGE` as an internal action trigger in an authorized full task. Make one
ordinary merge request using the verified repository/PR, an enabled method and the
exact expected head. Honour an actual host approval prompt if the tool requires it;
do not create an additional permission question when the user already authorized
the action. Never approve the PR yourself, invoke a bypass, weaken a gate, force a
ref update, or directly write data to the base branch to simulate a merge.

If the repository requires a merge queue, use its supported ordinary queue path
with the required current-head protection. Inspect the actual tool capabilities;
do not invent an enqueue operation or claim that a direct merge call automatically
enqueues. If a guard or required operation is unavailable, report that exact missing
capability. A verified queue entry is `QUEUED`, not `MERGED`. Keep the originating
task active, inspect queue/check progress, and handle any ejection or requested
correction. Do not resubmit an existing queue entry merely to poll it.

Where the normal tool reports asynchronous acceptance, observe the returned job/PR
until it actually merges or reports a concrete failure. An accepted request does
not establish completion. Continue under `CONTINUATION.md` if real host limits
require resuming this same task.

## Reconcile responses and races

Use reads to observe progress. Never repeatedly call merge as a polling mechanism.
After any unexpected response, first re-read the PR and relevant state; a request
may have succeeded even if the response was lost.

| Observation | Required action |
|---|---|
| Head changed or a head-precondition/409 conflict occurs | Re-read head/base and the full delta. Reconcile authorized changes, refresh correlated artifacts if needed, rerun affected checks and obtain review of substantive changes. Attempt again only after new verified readiness. |
| Base changed | Recompute validation against the current base and satisfy current update/queue rules. Do not reuse an old readiness verdict. |
| 403 on the merge operation | Inspect the actual error and current PR/gates. Distinguish an ordinary permission denial, host restriction or unmet rule; fix only work already authorized. If denied, report the exact blocker without privilege escalation or bypass. |
| 405 or other not-mergeable response | Re-read current mergeability, method settings, checks, review and queue requirements. Resolve the stated condition before considering another attempt; do not cycle through methods to evade a gate. |
| Timeout, lost response or incomplete success payload | Read the PR's merged state and resulting revision before any retry. If still open, re-establish readiness and absence of accepted asynchronous/queue work first. If the outcome cannot be read, report `BLOCKED` with an unverified merge outcome. |
| Queue entry accepted or merge job pending | Record the actual entry/job and keep observing. Return to authoring/verification after a failure or ejection. Acceptance alone is not success. |
| Another authorized actor already merged the PR | Verify the actual merge into the expected base and finish `MERGED`; do not submit another request. |
| PR closed without merge | Stop writes and report `CLOSED`, without claiming the authorized merge objective succeeded. |

A new tool request is justified only by a resolved condition or fresh reconciled
state. Respect rate limits and host/user budgets; persist accurate context and any
ambiguous operation before an execution interruption.

## Verify actual completion

After the operation, independently re-read GitHub's PR state. Require an actual
merged result for the intended repository/PR and base, with the reported merge
revision and time. A `closed` flag without merged evidence, a check badge, queued
entry, or tool message saying "accepted" is insufficient. If returned fields or
revisions disagree, reconcile them before claiming success.

Record the verified merge result, last reviewed source revision, target base and
observation time with the originating task. Preserve the original run's provenance;
do not rewrite its immutable closure to add a merge receipt. In the final user
receipt, link the merged PR and report the verified merge revision/time, with any
material remaining research uncertainties. Merging does not turn uncertain claims
into facts or imply completion of deferred discovery.
