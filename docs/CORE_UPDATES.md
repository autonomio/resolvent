# Guarded core updates

Plugin workflows and repository core are separate updates. Installed plugin clients
can read compatible live guidance immediately. A world's compiler, schemas, contracts
and Actions workflows update through an exact-copy PR. After one-time enrollment,
the installed updater prepares, validates and merges compatible reviewed upstream
releases automatically. There is no routine per-fork human review or manual patch.

## One-time setup

New repositories made from a template containing this updater already carry
`resolvent-core.lock.json`. An authorized owner or its agent enrolls each repository
once with the current updater, its exact matching upstream lock and the copy-review
policy below. An older prepare-only updater needs that initial policy adoption;
it cannot acquire new execution or review permissions from downloaded metadata.
Preserve all data and configuration during enrollment. Resolve existing core
customizations explicitly; do not regenerate an upstream lock from an organization's
customized tree or force-sync a fork. Templates do not modify existing repositories.

The owner then configures:

1. Its existing `RESOLVENT_AUTOMATION_TOKEN` Actions secret, scoped to this repository,
   with contents, pull requests, Actions dispatch and **Workflows** write permission.
   It also needs **Checks** and **Commit statuses** read permission to verify CI
   on private repositories; these permissions are separate from Actions access.
   A repository-approved app/user credential owns execution; there is no central
   Autonomio account or service. GitHub's built-in token cannot be assigned the
   separate workflow-file update permission. See [GitHub's app permissions](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app#choosing-permissions-for-git-access).
2. Actions variable `RESOLVENT_CORE_UPDATES=true`, enabling Actions for a fork if
   GitHub has disabled them. Keep required checks, current-base validation,
   stale-approval dismissal and branch protections.
3. If the branch requires a PR approval, allow GitHub Actions to submit reviews
   once, retaining read-only default token permissions. The trusted updater uses
   its ephemeral `github.token` for a clearly labelled automated copy approval;
   it does not need another permanent review credential. The existing automation
   credential creates and merges the PR. It cannot approve its own PR.
   See [GitHub's repository setting](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository#preventing-github-actions-from-creating-or-approving-pull-requests).

Enrollment must make the repository's protection policy compatible with that
approved automation. Additional human-only or CODEOWNER requirements remain
enforced and are reported as a policy block; the updater never disables them.

That is ongoing opt-in: the daily job discovers releases, and successful core-PR
validation resumes completion automatically. No release needs another button press.
**Run workflow** is available for an immediate check. Disabling the variable stops
the updater. Token renewal follows the organization's credential
policy; missing/expired permissions stop the run without changing main or data.

## Update boundaries

The installed updater fetches only Git objects from
`https://github.com/autonomio/resolvent.git`, reads `core-release:core.json`, then
pins its full source commit and lock digest. Release metadata has strict fields,
versions and inventory bounds. Each explicit managed file has mode, size, SHA-256
and Git blob identity checked against that source. The upstream release publisher
only advances after successful main validation; rollback/version reuse is rejected.

The updater compares affected local core files with the installed lock. Modified or
missing affected files stop publication. Unaffected local edits survive. New paths
colliding with organization-owned files/directories/symlinks stop publication.
Tracked upstream files outside the fixed generic core paths cannot enter the plan.

The proposed Git tree preserves **every other blob and mode**, including all
canonical/provenance data roots, `resolvent.yaml`, and unmanaged organization files.
The updater never checks out or executes candidate code with its write credential.
It also checks the actual proposed tree, including preserved local and unmanaged
workflows, and rejects PR/validation-dispatch jobs requesting secrets or write tokens,
and requires their checkouts to disable persisted credentials. Changing those
boundaries needs explicit governance adoption, not an automatic update.
Retries reconstruct the entire expected PR tree from its original main base and
the fixed upstream source. A matching lock alone is insufficient: any extra core,
data or organization edit stops automation. Only one core-update PR is open at a
time; existing and closed PRs deduplicate. If main advances, a fresh bounded plan
is committed with the previous bot head and current main as parents. This is an
ordinary fast-forward of the bot branch, preserves its history and current data,
and dispatches new validation. Old CI cannot authorize the refreshed head.

The native validation-dispatch command may return no output or a run URL. Its
successful exit acknowledges dispatch; it does not establish completed validation.
Command failures and malformed JSON responses still stop the updater. Before
retrying an uncertain outcome, inspect the actual PR, head and workflow runs;
an error does not establish that the preceding mutation was rolled back.

The proposed validation workflow runs the candidate compiler against the actual
populated world in the tests job, with read-only permissions and no persisted Git
credential. The existing integrity job still uses base-branch policy. Incompatible
core/data combinations fail CI; compatibility requiring a data migration is a
separate explicitly scoped, reviewed change. A green check does not establish truth.

Before publishing a new upstream release index, the publisher verifies the merged
main PR, a non-author maintainer approval on its final head and resolved upstream
threads. Repository write, maintain or admin permission establishes maintainer
authority; organization membership alone does not. This happens once upstream,
using its own read permission.
Forks verify the resulting fixed-origin release and its exact Git objects; their
credentials need no additional upstream API permission. The updater requires all
latest destination checks/statuses to succeed, both
named validation checks to come from GitHub Actions on the exact candidate head,
resolved destination threads, no changes-requested review, a current main base,
and ordinary merge eligibility. Missing or unverified checks never count as success.

When needed, a separate ephemeral Actions identity submits an automated approval
bound to that verified head and cites the reviewed published source revision.
It neither claims another human review nor approves a new substantive correction.
After GitHub updates eligibility, the trusted job resumes automatically and uses
an enabled ordinary merge method with the exact expected head. Protections still
apply. Main is never force-pushed or written directly. A merge is reported only
after its actual merged PR and commit are read back; an uncertain response is not
blindly retried or reported as leaving main unchanged. Pending PRs finish against
their original published release, even when a newer release becomes available;
the next scheduled run then prepares that newer release. Policy, permission,
conflict and compatibility exceptions remain
explicit pending/blocked outcomes.

The initial public channel still needs an authorized upstream publication. Built,
published, proposed and merged core versions are different states; an open update
PR does not mean the organization has installed it.

## Read-only readiness inspection (contract 1.0)

The supported status-only alternative is the inspection recipe below. It works
from an external trusted reader, including before a project has adopted an updater.
There is currently no status-only `core_update.py` invocation: omitting
`--auto-merge` still permits branches, PRs and validation dispatches. Do not probe
readiness by calling `publish()`, `continue_update()`, preparing a disposable PR,
or running scripts from the inspected project or candidate release.

Select an explicit `OWNER/REPOSITORY` and full installed commit. Record observation
time, the repository's main SHA, each inspected PR's base/head, and the selected
published channel/source/lock digest. Read local Git objects without checkout,
fetching into the destination, or changing its refs, index, configuration or files:

```sh
WORLD_ROOT=/path/to/selected/project
WORLD_REPOSITORY=OWNER/REPOSITORY
WORLD_COMMIT=$(GIT_NO_LAZY_FETCH=1 GIT_ALLOW_PROTOCOL='' git --no-replace-objects -C "$WORLD_ROOT" rev-parse --verify 'HEAD^{commit}')
GIT_NO_LAZY_FETCH=1 GIT_ALLOW_PROTOCOL='' git --no-replace-objects -C "$WORLD_ROOT" ls-tree "$WORLD_COMMIT" -- resolvent-core.lock.json
GIT_NO_LAZY_FETCH=1 GIT_ALLOW_PROTOCOL='' git --no-replace-objects -C "$WORLD_ROOT" show "$WORLD_COMMIT:resolvent-core.lock.json"
gh api --method GET "repos/$WORLD_REPOSITORY"
gh api --method GET "repos/$WORLD_REPOSITORY/git/ref/heads/main"
```

An absent lock makes the `show` command fail; record that observation and continue
with useful remote facts. The selected commit excludes uncommitted edits; identify
that scope explicitly. Disable lazy fetching and replacement objects in an automated
reader, as the existing trusted Git reader does. Use disposable storage for any
upstream fetch, reconstructed Git tree or copy assessment. Never expose credentials
to inspected code. Re-read main and PR heads after inspection; moved identities
make dependent findings stale rather than authorizing an update.

Report these facts separately; a successful inspection is not a ready installation:

| Fact | Supported interpretation |
| --- | --- |
| Installed baseline | A missing/malformed lock leaves the installed version unknown. Validate a regular lock against its matching fixed-origin published source, not just its declared version. Compare installed core blobs/modes with that baseline and report local differences. Do not use upstream whole-tree inventory equality as a downstream readiness test. |
| Published release | Read only `autonomio/resolvent`'s `core-release:core.json`, pin its source commit and verify the source lock digest, inventory, modes, sizes and object/hash identities using the existing release rules. Main, plugin/compiler versions and GitHub release tags are not the core channel. An unavailable channel is not evidence that the world is current. |
| Updater capability | Verify the installed updater scripts and workflow against a recognized published baseline and its adopted policy. Lock format `1.0` alone does not distinguish the older prepare-only updater from guarded completion. Missing, modified, prepare-only and unrecognized/future implementations remain distinct; a flag or filename is not capability proof. |
| Enrollment | Report the effective opt-in, workflow availability, configured automation-secret name and automated-review setting independently. Being current does not establish enrollment, and enrollment does not establish a particular release can be copied. |
| Copy feasibility | For the selected release, compare affected core files to the installed baseline, detect new-path collisions and inspect preserved workflow safety. Unaffected local customizations may survive. `plan()` returning `current` only establishes lock equality; it skips drift/enrollment checks. Any use of trusted copy-planning helpers belongs in disposable Git storage, never as a destination mutation probe. |
| Data compatibility | Until suitable unprivileged candidate validation has run on this world's actual proposed state, report not checked. Neither copy feasibility nor green upstream tests proves compatibility. Attribute a known compiler failure only when that step actually failed; another CI failure is not proof of incompatible data. |
| Pending update | Identify its own release target independently of the latest channel; older pending PRs deliberately finish first. Verify the full expected core-copy tree and unchanged data/configuration/unmanaged blobs, not its branch name, prose or lock alone. Report closed-unmerged, merged, multiple/conflicting PRs and orphaned/unrecognized update branches separately. |
| Completion conditions | Inspect exact-head checks/statuses, reviews/threads, current base, conflicts and ordinary merge eligibility under the installed updater's gates. Report independently observed blockers and unassessed conditions separately; the inspector never approves, refreshes, dispatches or merges. |

Contract 1.0's recognized guarded-completion reference is published core 1.3.2,
source `f87165009edb8d3540091ae77f2e463fa3b4dbed`. Verify the installed
`scripts/core_update.py`, `core_merge.py`, `core_release.py`, `core_review.py`,
`.github/workflows/core-update.yml` and `validate.yml` against that source's
published lock before attributing its capabilities. Other recognized baselines
need the same byte verification and their own policy interpretation; an older or
future implementation is not granted this reference's capabilities by its version.

### Selected-repository GitHub reads

The following are GET-only observation sources, relative to `repos/OWNER/REPO`.
They are optional according to the observer's existing access; do not acquire
administrative permissions merely to obtain a partial report. Follow all returned
pagination or mark the bounded result incomplete. Variables use at most 30 entries
per page; use each endpoint's documented bounds for other lists.

| Observation | Read source and meaning |
| --- | --- |
| Repository/main identity | Repository metadata and `git/ref/heads/main`: default branch, template/upstream exclusions, ordinary merge methods and current SHA. The automatic updater expects downstream non-template repositories with main. |
| Opt-in | `actions/variables` plus `actions/organization-variables`, filtered to `RESOLVENT_CORE_UPDATES`: resolve the repository override before the inherited value, and compare the effective value to `true`. Retain no unrelated variable values. Without a confirmed repository override, unknown inherited access prevents asserting the effective value or absence. See [variable reads](https://docs.github.com/en/rest/actions/variables#list-repository-organization-variables). |
| Automation secret metadata | `actions/secrets` and `actions/organization-secrets`, filtered to `RESOLVENT_AUTOMATION_TOKEN`: shared secret names/metadata only. Resolve repository precedence, and assert absence only with complete authorized observations of both applicable scopes. A masked 404 or 403 means unknown, not missing. Metadata cannot establish the stored credential's identity, expiry, permissions or usability. See [secret metadata reads](https://docs.github.com/en/rest/actions/secrets#list-repository-organization-secrets). |
| Actions/workflows | `actions/permissions`, `actions/workflows/core-update.yml` and `actions/workflows/validate.yml`: enabled/active state and applicable action restrictions. Inspect their pinned installed definitions for adopted guards, events and identities; customized/unknown definitions cannot inherit capability merely from the workflow names. |
| Copy-review identity | `actions/permissions/workflow`: observe `can_approve_pull_request_reviews` when accessible, preserving read-only default permissions. This concerns ephemeral `github.token`, not the stored automation credential. Unknown access remains unknown. See [workflow permissions](https://docs.github.com/en/rest/actions/permissions#get-default-workflow-permissions-for-a-repository). |
| PRs and branches | Paginated `pulls?state=all` and matching Git branch refs: select `resolvent/core/` candidates, then inspect only those PRs. Read `pulls/N`, exact base/head refs and paginated GraphQL reviews/review threads; incomplete history cannot establish approval or resolution. |
| CI evidence | `commits/HEAD/check-runs?filter=latest`, `commits/HEAD/status` and the relevant run/job metadata: both named validation checks must be successful GitHub Actions checks on that exact head, and additional current failures matter. Preserve missing, pending, failed, unreadable and incomplete outcomes. Respect the installed gate's own limits; collecting more pages does not change its behavior. |
| Repository protections | `branches/main/protection`, `rules/branches/main`, PR review/mergeability metadata and merge-method settings: rules may be inherited from the organization. Unreadable protection or an empty repository-only ruleset does not prove unrestricted merging. Retain human/CODEOWNER and merge-queue requirements; indeterminate mergeability stays unknown. See [effective branch rules](https://docs.github.com/en/rest/repos/rules#get-rules-for-a-branch). |

Keep credential configuration, the observer's read capabilities and actual automation
authority separate. The required automation permissions remain those in
[one-time setup](#one-time-setup); a successful repository read or a configured
secret does not verify them. Read-only inspection cannot test a stored token by
using it. Do not retrieve secret values, scan unrelated repositories, return raw
credential-bearing errors, or suggest disabling protections as remediation.

Each finding must distinguish observed facts, confirmed absence, unknown,
unsupported, unavailable, not checked and stale observations, with its identity and
reason. Preserve useful partial results when one source is inaccessible. This
recipe defines supported objects and interpretation, not a new CLI/JSON report or
an exit code that certifies readiness. Future machine-readable output needs its own
versioned field/reason-code and pagination contract; internal exception strings
are not that interface. All later updater writes must re-establish their gates.

For a legacy, prepare-only or unverified installation, the supported next step is
a separately reviewed governance PR establishing the upstream baseline, reconciling
local core customizations and adopting the current updater, matching upstream lock
and approved copy-review policy. Preserve model data, configuration and unmanaged
files. Never manufacture an upstream lock from a customized tree or force-sync it.
The chat plugin does not enroll a repository. The downstream application continues
to own provisioning, credentials, organization layout, scheduling and aggregation.

Compatibility: this inspection contract adds no runtime behavior, permissions,
canonical fields, schema or plugin/MCP capability. No plugin package or live-workflow
release is needed; only the independently versioned core documentation changes.

## Upstream release preparation

Only the upstream project regenerates its lock. Stage the intended generic changes,
then increase the independent core version and commit the resulting lock:

```sh
git add <intended-core-files>
python scripts/core_release.py lock --version <next-core-version>
git add resolvent-core.lock.json
```

The generator inventories staged regular Git files under explicit core paths,
excluding data, configuration, the lock itself and all unlisted paths. CI checks
the committed inventory and requires a version increase for changed core bytes in
the upstream release repository only. Organization repositories retain their
unmanaged files and unaffected local customizations; their CI validates the model
without requiring their whole tree to equal the upstream release inventory.
Existing plugin/workflow version requirements still apply independently. After
reviewed merge and successful main validation, the upstream-only publisher advances
`core-release` by an ordinary fast-forward. Data-only commits and retries preserve
the original released source commit; the branch carries only the release index.

This is repository maintenance. Only the owner-enrolled core-copy job gains
completion behavior. The generic chat plugin does not run that job or receive new
permissions. Submission protocol 1.2, canonical admission/review, installed plugin
behavior and workflow-reference format do not change; no plugin ZIP or live-workflow
update is needed. The selected world's contracts continue to govern contributions.
