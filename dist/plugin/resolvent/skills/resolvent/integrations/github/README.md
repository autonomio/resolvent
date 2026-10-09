# GitHub observation for Resolvent

The **originating task owns all actual work**, retaining the research context that
produced the contribution. It assesses candidates and connections, materializes
canonical records and closure, validates the full permitted delta, addresses every
correction, and follows CI and independent external review. Under the applicable
user authorization, it then performs the ordinary merge after fresh gate checks
and verifies `MERGED`. `READY_FOR_MERGE` is an intermediate result.

Read [ADMISSION.md](../../references/ADMISSION.md),
[MERGE.md](../../references/MERGE.md),
[CONTINUATION.md](../../references/CONTINUATION.md), and the trusted
repository contracts. The task-selected destination and completion contract is in
[TARGET.md](../../references/TARGET.md). Independent review is
external to the substantive author; the originating task cannot approve itself.

This optional integration observes enrolled PRs with
`authoring_owner: "originating_task"` by default. It records current gates and
blockers, but does not author corrections, call a replacement model, merge, or
resume the originating session. Observation can continue after a chat stops;
the actual task cannot continue merely because this observer is installed.
Only a host-supported continuation verified under `CONTINUATION.md` can establish
resumption of the originating task. A checkpoint or successful workflow run alone
does not establish that resumption or transfer ownership.

An explicitly configured legacy `bounded_worker` mode remains available under
separate authorization. Before canonical/closure outputs exist, its tool-free
**GPT or Claude API model** can propose one eligible JSON correction. It receives
only a bounded packet, not the original research session. It cannot perform
admission, regenerate canonical outputs, independently review, or merge, and is
not used by the default originating-task workflow.

This is source to install in your repository. Nothing in this ZIP is running on
GitHub yet. The shared skill works during an active ChatGPT/Codex or Claude Code
task without this integration; an indefinitely running chat is not assumed.

## Contents

- [Install the files](#1-install-the-files)
- [Configure GitHub access](#2-configure-github-access)
- [Configure the repository policy](#3-configure-the-repository-policy)
- [Enable and enroll](#4-enable-and-enroll)
- [Verify observation and task ownership](#5-verify-observation-and-task-ownership)
- [Behavior and limits](#behavior-and-limits)
- [Test and recover](#test-and-recover)
- [References](#references)

## 1. Install the files

Use a local checkout of the intended repository and Python 3.11 or later. From the
extracted skill directory (the folder containing `SKILL.md`), preview and then prepare the changes:

```bash
python3 integrations/github/install.py /absolute/path/to/Resolvent --dry-run
python3 integrations/github/install.py /absolute/path/to/Resolvent
```

The installer performs no network calls, commits, PR creation, credential setup, or
workflow activation. It copies the controller, policy, prompts, shared references,
and two workflows into `.github/resolvent/` and `.github/workflows/`. It appends a
scoped reference to the shared completion contract in existing `AGENTS.md` and
`CLAUDE.md`, preserving their original bytes. Identical files are left intact;
different existing integration files or symlinked destinations stop installation.

Review the diff and submit these setup changes through the repository's normal
process. The workflows must be on the **default branch** to provide observation.
Keep both enable switches off until setup is complete. This setup is
separate from an ordinary research contribution and its permitted PR-side
admission files. The legacy single-JSON write restriction belongs to that optional
worker; it does not limit the originating task's repository-authorized admission,
correction, or merge work.

For an existing configured installation, compare the new source and apply a
reviewed update while retaining your policy values and secrets. The installer
deliberately does not overwrite a customized policy or append a new instruction
block beside an older Resolvent block; review and replace that scoped block as
part of the upgrade while preserving all unrelated instructions.
Version 1.3.0 requires policy `version: 2` and an explicit `authoring_owner`.
Old controllers reject this policy version, and the new controller rejects old
policies even if the owner field was added: a partial upgrade cannot silently
re-enable the legacy writer. Missing/unknown owners also fail clearly; there is
no automatic migration into a writer mode. Keep an upgrade disabled while
reviewing it, update the controller and policy together, retain existing deployment
values, and set `authoring_owner` to `originating_task` for this workflow.
Checkpoint, packet, and contribution protocol versions do not change. Separately
authorizing `bounded_worker` changes execution ownership and must be an explicit
setup choice.

## 2. Configure GitHub access

Create a dedicated GitHub App and install it with access to the target repository.
The existing ChatGPT GitHub connector and an authentication on your computer do not
supply credentials to a GitHub Actions runner.

The shipped workflows retain these repository permission requests. In the default
originating-task mode, only observer jobs run; model and publisher jobs are skipped:

| Permission | Access | Purpose |
|---|---|---|
| Contents | Read; write only for explicitly enabled legacy publisher | Read trusted source. The legacy publisher alone may append its permitted single-file commit. |
| Issues | Read and write | Read PR issue comments and maintain the controller checkpoint. |
| Pull requests | Read | Inspect PR metadata, files, commits, reviews, and threads. |
| Actions | Read | Read failed run/job diagnostics. |
| Checks | Read | Inspect check runs and annotations. |
| Commit statuses | Read | Inspect legacy commit status contexts on private repositories. |
| Metadata | Read | Repository identity and metadata (included by GitHub Apps). |

The observer requests read-only contents access; only the explicitly enabled
legacy publisher requests contents write access. No merge permission or merge
operation is added to this integration. Third-party Actions dependencies
are pinned to verified commits, recorded in `action-pins.json`.

Ensure that the token can read the branch protection and repository rules used by
this repository. If the repository's GitHub policy denies any required read, the
controller reports a blocker. Do not grant bypass, merge, administrator-write, or
workflow-edit privileges as a substitute for a missing gate.

Create the `resolvent-followup` Actions environment and restrict it to deployments
from the repository's default branch. Only legacy `bounded_worker` mode needs the
second environment, `resolvent-followup-model`; restrict that environment to the
default branch too if used. Keep App/state secrets in the first environment and
any legacy model secret in the second:

| Environment | Secret | Value |
|---|---|---|
| `resolvent-followup` | `RESOLVENT_APP_PRIVATE_KEY` | The dedicated App's private key. |
| `resolvent-followup` | `RESOLVENT_STATE_KEY` | A new independent random secret of at least 32 characters, used to sign checkpoints. |
| `resolvent-followup-model` | `OPENAI_API_KEY` | Legacy `bounded_worker` only, when `provider` is `openai`. |
| `resolvent-followup-model` | `ANTHROPIC_API_KEY` | Legacy `bounded_worker` only, when `provider` is `anthropic`. |

Default observer mode needs **no model provider key**. Legacy mode needs one selected
provider key. Put the App ID in a repository Actions variable
named `RESOLVENT_APP_ID`. Leave `RESOLVENT_FOLLOWUP_ENABLED` unset or `false` for now.

Use GitHub's secret settings or an already authorized CLI; never put these values
in policy files, source control, PR comments, or chat. If you add required approvals
to the Actions environments, those approvals are another explicit wait condition.
For unattended observation, configure environment access according to your
repository's approved automation policy.

The legacy publisher uses a GitHub App token so that its correction commits can trigger
the repository's ordinary CI. The default `GITHUB_TOKEN` has event-trigger
restrictions and can produce approval-required PR workflow runs. Existing GitHub
and organization approval requirements still apply; the worker does not bypass
them. See [GitHub's workflow-trigger documentation](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow).

## 3. Configure the repository policy

Edit the installed `.github/resolvent/policy.json` using the actual repository's
approved contracts. The bundled policy remains intentionally unconfigured.
Before installation, verify the selected repository's current admission contracts,
check names, review actors, amendment rules and credentials. Preserve existing
configured values and assess them against the current base.

| Setting | What to supply |
|---|---|
| `version` | `2`, the ownership-aware integration policy contract. Older controllers reject this version, and this controller rejects older policies. |
| `repository` | The exact `owner/name`; must be configured for the observer; the chat plugin has no default target. |
| `authoring_owner` | Required. `originating_task` is the shipped default: all corrections stay with the originating task and the integration only observes. `bounded_worker` explicitly enables the separately authorized legacy single-JSON repair path. Missing/unknown values fail. |
| `base_branch` | `null` to use the current default branch, or an explicitly authorized branch. The shipped workflow environments must still allow only trusted default-branch execution. |
| `allowed_authors` | GitHub logins whose contribution PRs may be enrolled. |
| `enrollment_label` | The explicit opt-in label, default `resolvent-followup`. |
| `controller_login` | Your dedicated App's exact bot login, such as `your-app-slug[bot]`. |
| `provider` | Legacy mode only: `openai` for a GPT API model, or `anthropic` for a Claude API model. May remain unconfigured in originating-task mode. |
| `model` | Legacy mode only: an exact model ID available to the selected API account. No model is silently selected or called in originating-task mode. |
| `expected_checks` | Nonempty list of the expected CI checks, with exact names and producers. |
| `admission_checks` | Nonempty list of independent admission gates for this contribution. |
| `reviews.reviewers` | Allowed independent approving GitHub logins; at least one is required. Authors, commit authors/committers, and the controller cannot supply independent approval. |
| `reviews.minimum` | Required independent approvals of the current head; at least one. GitHub's additional review rules still apply. |
| `reviews.feedback_authors` | Additional trusted feedback actors whose comments should trigger assessment. Configured reviewers are included automatically. |
| `amendments.authorized` | Legacy mode only: `true` only if repository-approved contracts permit amendment of an open contribution. It cannot override `authoring_owner=originating_task`; no single-JSON repair is allowed after canonical/closure outputs exist. |
| `amendments.contract_paths` | Paths to the actual approved amendment/activity contracts, read from the current base and supplied to the worker. |
| `admission_attests_entire_diff` | Enable only if the configured independent admission gate certifies all PR changes and their provenance, including canonical additions. This permits observing that full diff; it never authorizes the worker to alter canonical files or amend their source JSON. |
| `admission_may_consume_proposal` | Enable only if that admission process may legitimately remove/consume the original proposal. |
| `schema_path` | The authoritative schema in the repository, default `docs/schemas/submission.schema.json`. |

Each configured check has this shape; replace these illustrative values with
observed values:

```json
{
  "name": "EXACT_CHECK_NAME",
  "kind": "check",
  "app_id": 123456,
  "accepted_conclusions": ["success"]
}
```

For a legacy commit status, use `"kind": "status"`; its context must match exactly.
Check runs must be pinned to the producing GitHub App's numeric ID. Obtain names
and App IDs from the actual current PR checks/API response. Do not assume the
example number identifies any particular App.

The controller also reads live branch-protection/ruleset requirements and includes
all observed current-head/current-test-merge CI, including optional failures.
Configure intentional `neutral` or `skipped` conclusions with an explicit reason.
The `accepted_nonrequired_checks` list can document such acceptance for other
observed checks; it does not allow failures or erase required checks.

Retain bounded settings unless there is an approved reason to adjust them:

- At most four provider attempts per PR by default; one per unchanged feedback set.
- At most 20 enrolled open PRs and two simultaneous PR reconciliations.
- A 512 KiB work packet and 16,000 output tokens by default.
- A collected observation must finish within five minutes to remain fresh.

In legacy mode the provider cap is per PR across revisions, not a fresh allowance after every
push. A new revision or fresh CI run can justify another attempt within that cap.
Oversized packets, unsupported schema features, missing access, exhausted budgets,
or a need for new evidence become explicit blockers.

The bundled validator supports the supplied protocol 1.0 schema using the Python
standard library. It rejects unsupported schema keywords and remote references;
it does not silently downgrade a changed repository schema.

If your admission/review system attests independent review only through checks and
does not produce GitHub APPROVED reviews, adapt this integration through a separate
reviewed setup change. The shipped controller deliberately requires a configured
independent GitHub approval as well as admission checks. It does not invent that
repository-specific adaptation.

## 4. Enable and enroll

In `.github/workflows/resolvent-followup.yml`, replace the two
`workflow_run.workflows` placeholders with the exact **display names** of the CI
and admission workflows whose completion should prompt a new observation. Names
are available in GitHub's Actions tab or `gh workflow list --repo OWNER/REPOSITORY`.
Do not add the follow-up workflows to that list or make their own running jobs
required PR gates. The follow-up worker must not wait for itself.

Validate the completed policy locally from the repository root:

```bash
python3 .github/resolvent/controller.py validate-policy
```

This validates structure and bounds, not live permissions or the truth of your
review/admission declarations. Finish reviewing and merging the setup, set
`policy.enabled` to `true` on the default branch, and set the repository Actions
variable `RESOLVENT_FOLLOWUP_ENABLED` to the string `true`.

Create the enrollment label if needed and apply it to a contribution PR whose
author is in `allowed_authors`. Initial enrollment requires exactly one newly
added `input-artefacts/RUN-<32 lowercase hex>.json` proposal. A materialized PR can
be enrolled when that input is still newly added and the explicit full-diff
admission policy is configured. The controller reads the expected
`briefs/closed/BC-<same UUID>.yaml` from the immutable current head, including
when it is absent from the changed-file list. Closure presence never proves
validity: the configured compiler/admission check must verify it and the full delta.

The originating task retains admission, corrections, and authorized merge work
when observation is enabled. A proposal-only PR with a missing closure remains
that task's unfinished work. In originating-task mode, the controller returns
correction signals to that owner without creating a model packet, reserving a
model attempt, or publishing a correction. It never reserves attempts to generate
canonical outputs in either mode.

For an existing open PR, apply the label and then use GitHub's
**Run workflow** control for `Resolvent follow-up`, entering the PR number.
With an existing authorized CLI, the equivalent is (replace `123` with the PR number):

```bash
gh workflow run resolvent-followup.yml --repo OWNER/REPOSITORY -f pr=123
```

No separate GitHub App webhook server or continuously running local client is needed
for observation. GitHub Actions runs the observer, not the originating task.
The shipped integration reacts to configured
CI completions and issue comments, with scheduled reconciliation every five minutes
for missed events, reviews, new heads, and changed base state. Review submissions
are picked up by reconciliation; their workflow code is not loaded from a PR.
GitHub schedules are best effort and may run late, so five minutes is a requested
cadence, not a response-time guarantee.

Reconciliation also finalizes previously enrolled PRs that were merged or closed.
After writing their authenticated terminal checkpoint, it removes the enrollment
label so those PRs are not repeatedly scanned as active work.

## 5. Verify observation and task ownership

Before claiming that observation is active, verify all of these. None constitutes
a handoff of the originating task's authoring or merge responsibility:

1. PR-side admission is materialized and its trusted compiler validation passed.
   The optional observer cannot receive ownership of missing canonicalization.
2. The matching workflow run exists and actually reached observation for the
   intended PR. A successful dispatch response alone is insufficient.
3. The dedicated App's checkpoint on that PR identifies the observed head and
   base, policy hash, observation time, GitHub run ID, and pending/blocked/ready state.
4. If a correction is needed, the checkpoint directs the originating task to
   address it with its research context, including regeneration and validation of
   the full permitted file set where necessary. A workflow never proves the
   originating session was resumed. Verify any actual host continuation separately
   using `CONTINUATION.md`.
5. A new head invalidates the prior readiness result; resolving one failure or
   posting the checkpoint never substitutes for independent approval.

The checkpoint records the actual state, remaining gate, worker assessment, and
bounded attempt count. `READY_FOR_MERGE` means the inspected snapshot satisfies the
explicit policy and GitHub's normal merge state. It contains no merge command and
does not enqueue or enable auto-merge. `READY_FOR_QUEUE` remains pending.
Observer `READY_FOR_MERGE` is **not final task completion**: the originating task
must follow `MERGE.md`, recheck current state, perform the user-authorized ordinary
merge, and verify GitHub reports `MERGED`. The observer may later record that
terminal state, but never performs the merge itself.

An observed closure with an actual configured validation check still pending is
`WAITING_CI`. The shared `WAITING_ADMISSION` status is reserved for a separate
admission authoring job whose acceptance and execution have been verified; this
optional worker neither performs nor establishes such a job and never emits that
status. Missing canonicalization or an unobserved admission validation check is
reported as `BLOCKED` with the authoring agent's next action; reconciliation can
continue observing for that action's result.

A ready result can change after a new commit, review, base update, or repository
rule change. The originating task must inspect the current GitHub state before
its authorized merge. The controller never uses an administrator bypass to manufacture readiness.

## Behavior and limits

The observer executes trusted default-branch code. In originating-task mode,
`evaluate`, packet creation, the provider call, the work CLI, and publication all
enforce ownership. A stale legacy plan cannot override the current owner's
policy. This observer neither retains the original research session nor exposes a
session-resume mechanism; it cannot provide the task continuity described in the
shared skill.

Only the separately enabled legacy publisher and model jobs execute the repair
path. The model runs in
a separate job and receives a bounded JSON packet and trusted instructions; PR
files, diagnostics, source excerpts, and comment text are treated as untrusted
data. It has no tool access, never checks out a PR for execution, and cannot run
its output. The publisher re-reads current state, validates schema/identity/path,
and uses an atomic expected-head check when appending the one-file commit. It
recollects the full changed-file list and the closure at the current head before
publication. A closure or any nonproposal output blocks a JSON-only correction,
even when the full-diff attestation setting permits monitoring. Head or base
changes cause an old proposal to be discarded, preserving other agents' work.

Every PR uses a shared concurrency group. Duplicate or stale events read the
current GitHub state; legacy attempts are reserved durably before calling a model.
Originating-task observations never reserve attempts or call a model. A repeated observation of unchanged legacy work does not
continually consume provider calls. Model API use and GitHub Actions usage remain
subject to the accounts' normal billing; this ZIP includes no credentials or quota.

The explicitly enabled legacy worker can fix pre-admission contribution defects supported by the existing packet. It
cannot conduct a new literature review, invent evidence, correct repository
workflows or canonical claims, independently approve itself, or supply a missing
human decision. A failed configured admission check with an absent closure is
returned to the authoring agent without a provider call, even if other feedback
also exists. The model never receives that as an instruction to create admission.
Once a closure or other outputs exist, every correction requiring a write is
returned to the authoring agent to preserve canonical content and closure digests.
The controller remains available to observe subsequent authoring-agent commits,
fresh independent review, and the current CI/rule results.

Closure inspection checks a bounded regular UTF-8 file at the exact head and rejects
empty content, access errors, or incomplete tree reads. It is not a YAML validator
or a second admission compiler. Invalid schema, stale digests, and incorrect delta
coverage must fail the configured trusted compiler/admission gate; file presence
alone cannot establish admission completion or make the PR ready.

New and materially edited authorized comments/reviews are considered separately.
Exact benign approval text such as `LGTM` is informational. Mixed text such as
`LGTM, but fix the evidence` remains feedback for the originating task. In the
originating-task observer mode, a historical change request is concluded only by a later benign
approval from that same independent reviewer on the current head, with all threads
resolved. Issue comments and other feedback remain actionable. This observation
does not replace the originating task's correction receipts or authorize a merge.
In legacy
mode, if the worker answers without a code
change, it records an assessment; an independent reviewer must confirm that
assessment with a later current-head approval and resolve required threads. A
model's `no_change` or `blocked` result cannot erase a reviewer request.

The signed checkpoint is durable working state, not an immutable audit ledger.
Protect the dedicated App and signing secret and retain its checkpoint. Arbitrary
body edits or another actor editing an App checkpoint are rejected. A maintainer
can still change trusted source, delete state, rotate secrets, or disable Actions;
those are operator-controlled interventions. Do not describe the checkpoint as
tamper-proof or proof that future work is guaranteed.

## Test and recover

Run the bundled offline test suite from the extracted skill root:

```bash
python3 -m unittest discover -s integrations/github/tests -v
```

For an installation preview, use `install.py --dry-run`. For an actual deployment
test, use an authorized test contribution/PR and verify one induced CI defect and
one independent review correction remain owned by the originating task, with no
provider job or proposal publication. Verify its new head, renewed external
approval, authorized ordinary merge, and actual merged state separately from the
observer. An explicitly enabled legacy deployment also needs its own bounded
repair-path test. Do
not use the bundled synthetic research example as a production contribution.

To stop new work, disable the Actions variable, disable policy, or remove a PR's
enrollment label according to your repository's process. An already running legacy
job may still be finishing its guarded publication; inspect the run and checkpoint.
Do not delete a checkpoint to silently reset budgets. On an exhausted budget or
corrupted checkpoint, an operator should inspect the PR and Actions logs, fix the
underlying issue, and make a documented policy/state recovery. Uncertain commits
must be reconciled with the remote branch before any retry.

A failed Actions job or missing checkpoint means observation is unverified. Fix the
reported access/policy/environment problem and dispatch a new run on the default
branch. After a worker correction, independently verify that normal CI starts;
approval-required, disabled, or skipped workflows stay blockers.

## References

- [GitHub protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
- [GitHub workflow triggers and token behavior](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)
- [GitHub workflow events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
- [GitHub App tokens in Actions](https://github.com/actions/create-github-app-token)
- [GitHub CLI workflow dispatch](https://cli.github.com/manual/gh_workflow_run)
- [OpenAI Responses API](https://platform.openai.com/docs/api-reference/responses)
- [Anthropic Messages API](https://docs.anthropic.com/en/api/messages)
- [Shared completion contract](../../references/PR_FOLLOWUP.md)
- [Authoring-agent admission procedure](../../references/ADMISSION.md)
- [Originating-task continuation](../../references/CONTINUATION.md)
- [Authorized ordinary merge](../../references/MERGE.md)
- [Scoped target preference](../../references/TARGET.md)

This standalone skill archive contains the Resolvent 1.3.0 implementation, with source paths adapted to the skill layout.
Live repository/provider operation must be verified after setup.
