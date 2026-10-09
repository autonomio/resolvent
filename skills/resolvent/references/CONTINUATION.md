# Preserve the originating task through completion

Use this contract in ChatGPT, Codex and Claude. The originating research/capture
task owns all authoring, canonical admission, substantive corrections and the
authorized guarded merge described by `TARGET.md` and `MERGE.md`. External review
agents supply independent review. Reading the same PR does not give a replacement
model the originating task's research context or transfer its responsibility.

## Contents

- [Keep the active task working](#keep-the-active-task-working)
- [Preserve an explicit checkpoint](#preserve-an-explicit-checkpoint)
- [Verify real resumption](#verify-real-resumption)
- [Handle execution limits honestly](#handle-execution-limits-honestly)
- [Keep the legacy worker outside authoring ownership](#keep-the-legacy-worker-outside-authoring-ownership)

## Keep the active task working

After publishing, observe actual CI, external reviews and required conversations;
inspect failures, implement justified corrections, rebuild correlated admission
artifacts and repeat verification. When eligible, perform the guarded merge and
verify `MERGED`. Do not end the task merely because CI or a reviewer is currently
pending, or because the PR became `READY_FOR_MERGE`. Those are working states in
an authorized full contribution workflow, not reasons to return successful completion.

Use event-driven waits where the actual host supports them, otherwise bounded
read-only polling with reasonable backoff. Give progress updates and respect rate
limits. Use short waits that permit communication and interruption; a long blocking
sleep does not create a durable task. Keep working within actual host, user and
execution/cost budgets. Do not invent a short arbitrary deadline for routine CI or
review merely to stop early. Conversely, do not promise infinite runtime or a fixed
response time from external reviewers.

The user's narrower scope or stop instruction remains controlling. Preflight never
starts research, creates checkpoints/delivery artifacts, writes to GitHub, or
dispatches/resumes a job merely to test capabilities.

## Preserve an explicit checkpoint

Before a real execution limit, context compaction, host resumption boundary, or a
potentially ambiguous write, preserve the explicit work product needed by this same
task. Refresh it after material changes. It must contain or reliably reference:

- The user's selected scope, exclusions, input route, target repository, run/PR
  identity, contribution branch, intended base and applicable user authorization.
- The selected research question or capture context, evidence/source anchors,
  inspected/not-retrieved status, limitations, uncertainties, counterexamples,
  candidate decisions, duplicate/connection assessments and their stated rationale.
- The normalized input, canonical/closure file inventory and content digests,
  local working changes not yet published, and provenance of collaborator changes.
- Trusted policy/code revisions, validation commands and real results, last known
  head/base/test-merge revisions, and observation timestamps.
- External review IDs and decisions, requested changes, what was actually addressed,
  unresolved threads, pending checks and the next concrete action.
- Any submitted publication, merge or queue operation whose result is unresolved,
  including its actual request/job/queue identifiers and known response.

If the exposed interface supports an asynchronous merge request, preserve its real
returned request identifier and status so resumption observes that same request.
Do not fabricate an asynchronous handle for a synchronous response or timeout.

Use concise decision summaries and verifiable artifacts, never private chain of
thought, authentication tokens, credentials or unrelated private chat content.
Preserve enough selected research context to justify a correction; a PR URL and
"continue until green" are insufficient. Do not claim that truncated or missing
research context was preserved. If essential evidence cannot be recovered, keep
that as a specific limitation rather than inventing it.

Use a real host-supported persistent task store or other authorized durable storage.
Confirm the write succeeded, record its stable identifier/version or content digest,
and read back the relevant saved content. A transient workspace path, an unsaved
draft, a promised future save or an ordinary process left running is not evidence
of persistence. Do not add unrecognized checkpoint files to the canonical PR delta
or alter repository governance to store them. Existing authorized run/closure and
source artifacts can be referenced without duplicating whole transcripts.

## Verify real resumption

A skill tells an agent what to do; it does not itself keep a host session alive or
wake a stopped conversation. Only claim durable continuation when the actual host
provides and has accepted a mechanism to resume **this originating task/session**
with its selected context and existing authorization. Do not substitute a new,
contextless model call or independent repository agent for that task.

Before claiming resumption has been arranged, verify all of these:

1. A real supported continuation/scheduled execution exists and is enabled; inspect
   its actual nonsecret task/session identity and applicable trigger.
2. It accepted this exact originating task, repository and PR. Preserve the returned
   stable task/job handle, acceptance state and corresponding trigger/run evidence.
   A dispatch response with no correlated accepted job is insufficient.
3. The verified durable checkpoint is available to that continuation, with the
   selected research context, evidence/decisions, outstanding work and authority.
   Record its identity/version or digest; do not merely assume access to this chat.
4. The resumed task has the needed authorized read, execution, contribution-write
   and guarded-merge capabilities. Observer-only access does not cover corrections
   or merge. Do not export credentials to bridge a capability gap.
5. The continuation reacquires current GitHub state before acting. Its saved
   head/base/check/review snapshot is a checkpoint, not permission to use stale
   readiness or retry an ambiguous write blindly.

On resumption, load that checkpoint and the current live contracts, re-read the
PR/head/base/reviews/checks, reconcile intervening work and uncertain operations,
then continue the existing contribution. Do not open a replacement PR or create
a new run merely because the execution session resumed.

Report a verified scheduled/resumed task as pending with its actual handle and
outstanding action; it is not merge success. An ordinary CI workflow, an observer's
checkpoint, a local plan, or an instruction saying "keep waiting" does not prove
resumption. If a host has no suitable persistent execution capability, state that
fact precisely instead of claiming portability alone supplies it.

## Handle execution limits honestly

If a concrete host limit, exhausted user budget, user stop, denied permission or
unavailable capability prevents further execution, preserve what can actually be
saved and report `BLOCKED` or the observed pending state with that interruption.
Include the PR, last verified head/base, unresolved action and real checkpoint or
continuation handle when one exists. Distinguish "context saved" from "resumption
accepted" and from "merged". Do not call an interrupted full task complete.

Before stopping, complete available authorized work that does not depend on the
blocked action. Ordinary pending CI/review is not itself a hard capability failure;
keep the active loop going unless a real execution constraint intervenes. Never
promise another background turn when no accepted resumption exists.

## Keep the legacy worker outside authoring ownership

The bundled GitHub integration's legacy proposal-repair worker uses a separate
bounded model without this chat's research context. That authoring mode is outside
the originating-task workflow. Do not enroll or configure it to write this task's
proposal, canonical records, closure or corrections, and do not give it merge
ownership. A label or GitHub token does not change this boundary.

An authorized observation-only configuration may report CI/review/PR state and
support a verified host wake/resume mechanism. Verify that it cannot make conflicting
writes and that any claimed wake actually resumes the originating task as above.
An observer's `BLOCKED` describes its own limitation; continue a correction when
the originating task's tools can perform it. Its `READY_FOR_MERGE` is evidence to
recheck and act on, not successful completion of the originating task.
The integration's files and setup instructions do not install a host resumer, grant
access to this chat, or activate an automation. Installation or configuration changes
remain separate authorized setup work; they are not an implicit contribution fix.
