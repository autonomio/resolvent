# Authorized GitHub access

This access contract is shared by ChatGPT, Codex and Claude. Provider names do not
prove that an integration can write or that an assistant can access the user's
computer. Inspect the capabilities actually exposed in the current host.

## Contents

- [Prefer the connected integration](#prefer-the-connected-integration)
- [Combine connector access with host execution](#combine-connector-access-with-host-execution)
- [Observe gates and perform the delegated merge](#observe-gates-and-perform-the-delegated-merge)
- [Existing authenticated gh fallback](#existing-authenticated-gh-fallback)
- [Capability boundaries and preflight](#capability-boundaries-and-preflight)

## Prefer the connected integration

Use the available authorized GitHub connector when it supplies the necessary
operations. Check separately for complete revision-pinned repository/file reads,
branch creation, multi-file commits or conditional file writes,
PR creation/reads, checks/statuses, reviews/threads, applicable rules, admission
evidence and ordinary guarded merge/read-back. A file-sync connection can supply source files without supplying GitHub
mutations or live review state. Do not describe it as write access.

Keep the selected `OWNER/REPOSITORY` explicit for every operation. Confirm the
authenticated account and repository access through nonsecret metadata. Access to
one account, repository or host does not establish access to another.

## Combine connector access with host execution

GitHub authentication and local computation are separate capabilities. An authorized
connector can read the trusted base and PR files, while the host execution tool
materializes those returned bytes and runs Python. That route does not require an
authenticated `gh` binary in the execution workspace or credentials copied from the
connector. Use it for `ADMISSION.md` when available; absence of local CLI access alone
is not an admission blocker.

Read complete file/tree data at explicit commit revisions and verify completeness.
Construct the trusted base and proposed-state snapshots described in `ADMISSION.md`,
preserving exact paths/bytes and using trusted base code/policy. Execute only that
approved code with its required dependencies in the host's available workspace.
Keep tokens and other credentials out of files, prompts and command output. Do not
assume that reading a repository creates a checkout or transfers the user's local
machine authentication into this host.

For publication, prefer a supported atomic multi-file GitHub commit with the expected
current branch head, covering the validated input, canonical and execution-artifact
delta. A GitHub `createCommitOnBranch` interface, when exposed and authorized, can
apply additions/deletions with `expectedHeadOid`; inspect the actual tool schema
before use. An exposed Git Data interface can also publish the full delta: create
the required blobs, build a tree from the verified current head's tree while
preserving unrelated paths, create a commit with that head as its parent, then
update the contribution branch with `expected_sha` set to that head and `force`
false. The guarded ref update publishes the prepared commit; creating objects alone
does not change the branch. Inspect the actual schemas and supported deletion
representation. If a head guard fails, re-read and reconcile before retrying.
If only individual conditional writes are available, preserve current
content preconditions, reconcile changes between writes, and keep the PR pending
until the entire delta is published and verified. Never label a partially written
contribution ready or force-update a branch to resolve a race.

Re-read the head/base before writing and verify the returned commit(s), complete file
inventory and remote bytes afterward. If a needed execution or write capability is
actually unavailable, report that exact boundary and preserve the prepared work.
Do not substitute a fictional admission service or ask the user to do routine
decomposition merely because a connector and execution tool are separate.

## Observe gates and perform the delegated merge

Read `TARGET.md` for the actual task's merge authority and `MERGE.md` for the exact
preconditions, guarded operation and result verification. In the configured full
workflow, use existing authorized ordinary merge access after external review and
current CI; do not ask for already-delegated permission again. The exposed MCP merge
tool's `expected_head_sha` must carry the freshly verified head. Use a CLI equivalent
only if actually available and confirmed by installed help. An unguarded operation
is not an acceptable fallback, and an observed green badge is not a merge receipt.

Use authorized branch summaries, checks/reviews, trusted base policy and normal
GitHub eligibility to establish the material requirements. A 403 from an admin-only
protection endpoint is not automatically a denial of ordinary merge access. Prefer
sufficient authorized alternative evidence; do not seek admin privileges. If an
important rule or current result still cannot be verified, identify that precise
gap. Honour actual host approval prompts and never bypass repository rules.

## Existing authenticated `gh` fallback

If the connector is absent, lacks a needed operation, or returns a target-specific
read error/404, check whether a separately authorized existing GitHub CLI route is
available. A connector's 404 or failed read alone does not prove that the selected
repository is missing: the routes may have different authenticated visibility.
An already-installed CLI is a permitted fallback **only** when the host exposes an
executable environment that actually contains it and its existing authentication is
authorized for this task. This may be a hosted workspace or an explicitly connected
development environment; never assume it is the user's computer. An alternate route
does not override an explicit host/user access restriction or authorization denial.

Use read-only availability/authentication checks and a read of the explicit target
repository before any mutation. Existing `gh auth status` and `gh api` capabilities
can establish access; consult the installed CLI's help for supported syntax. Never
print tokens, run a token-export command, copy credentials between environments,
start a login flow without authorization, install the CLI, or bypass host approval
requirements. Do not switch accounts to guess which identity might work.

Use only the already-authorized operations and scopes. Changing transport carries
the task's existing scoped merge delegation; it does not create new authorization,
administrator privileges, workflow changes, permission escalation or writes outside
the contribution and its correlated admission outputs. Preserve the same review,
admission, guarded-merge and retry contract
regardless of transport. Reconfirm repository, head and base when changing transport
so that a connector and CLI cannot silently act on different targets.

## Capability boundaries and preflight

A preflight is strictly read-only: inspect available tools/authentication, target
files, repository rules and any existing continuation setup. Do not start research,
write local delivery packages, create branches/PRs, post comments, rerun checks or
dispatch a workflow merely to test permission. A read-only success establishes read
access; report unproven write or follow-up operations as unverified rather than
testing them with disposable remote changes.

For an actual authorized contribution, proceed with supported operations and verify
their results. If submission access is unavailable, still perform the requested
work, prepare its package and any supported validated admission outputs, and report
**not submitted** with the missing
capability. If a PR exists but required live rules/checks/reviews/admission evidence
cannot be read, report that precise verification blocker; do not infer readiness
from a partial view or a previous green check.

Durable continuation is separate from ordinary GitHub file access. Follow
`CONTINUATION.md` to verify persistent context and accepted resumption of the same
originating task. An integration token, PR comment or a separate model reading GitHub
does not establish that capability. Do not hand corrections or merge to the legacy
proposal-repair worker; that mode is outside originating-task ownership. An
authorized observer may assist with state observation or a verified host resumption,
but cannot claim access to the original chat merely because it reads the repository.
This skill bundle's `integrations/github/README.md` describes separate setup; using this
skill does not install or activate it. Keep working in the active task, or report an
actual execution interruption without inventing background monitoring/resumption.
