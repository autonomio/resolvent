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

The proposed validation workflow runs the candidate compiler against the actual
populated world in the tests job, with read-only permissions and no persisted Git
credential. The existing integrity job still uses base-branch policy. Incompatible
core/data combinations fail CI; compatibility requiring a data migration is a
separate explicitly scoped, reviewed change. A green check does not establish truth.

Before publishing a new upstream release index, the publisher verifies the merged
main PR, a non-author maintainer approval on its final head and resolved upstream
threads. This happens once in the upstream repository, using its own read permission.
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
blindly retried. Policy, permission, conflict and compatibility exceptions remain
explicit pending/blocked outcomes.

The initial public channel still needs an authorized upstream publication. Built,
published, proposed and merged core versions are different states; an open update
PR does not mean the organization has installed it.

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
