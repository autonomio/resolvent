# Guarded core updates

Plugin workflows and repository core are separate updates. Installed plugin clients
can read compatible live guidance immediately. A world's compiler, schemas, contracts
and Actions workflows change only through its own reviewed governance PR.

## One-time setup

New repositories made from a template containing this updater already carry
`resolvent-core.lock.json`. Existing forks/template copies first need one reviewed
governance PR adopting the updater and a matching upstream core lock. Preserve their
data and configuration during that adoption. Resolve existing core customizations
explicitly; do not regenerate an upstream lock from an organization's customized
tree or force-sync a fork. Templates do not install updates into existing repositories.

The owner then configures:

1. Its existing `RESOLVENT_AUTOMATION_TOKEN` Actions secret, scoped to this repository,
   with contents, pull requests, Actions dispatch and **Workflows** write permission.
   A repository-approved app/user credential owns execution; there is no central
   Autonomio account or service. GitHub's built-in token cannot be assigned the
   separate workflow-file update permission. See [GitHub's app permissions](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app#choosing-permissions-for-git-access).
2. Actions variable `RESOLVENT_CORE_UPDATES=true`, enabling Actions for a fork if
   GitHub has disabled them. Keep the existing required checks, human maintainer
   review, stale-approval dismissal and branch protections.

That is ongoing opt-in: the daily job prepares new update PRs without another
button press. **Run workflow** is available for an immediate check. Disabling the
variable stops preparation. Token renewal follows the organization's credential
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
It also rejects candidate PR/dispatch workflows requesting secrets or write tokens,
and requires their checkouts to disable persisted credentials. Changing those
boundaries needs explicit governance adoption, not an automatic update.
It creates Git objects and a ready `resolvent/core/<version>` PR, never a main write,
data migration, force push or merge. Existing/closed PRs deduplicate; an interrupted
publication can resume only an identical original branch. An unfamiliar branch stops.
Only one core-update PR is open at a time. A newer main revision requires a fresh plan.

The proposed validation workflow runs the candidate compiler against the actual
populated world in the tests job, with read-only permissions and no persisted Git
credential. The existing integrity job still uses base-branch policy. Incompatible
core/data combinations fail CI; compatibility requiring a data migration is a
separate explicitly scoped, reviewed change. A green check does not establish truth
or replace the human maintainer review. Review all governance/workflow changes.

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
the committed inventory and requires a version increase for changed core bytes.
Existing plugin/workflow version requirements still apply independently. After
reviewed merge and successful main validation, the upstream-only publisher advances
`core-release` by an ordinary fast-forward. Data-only commits and retries preserve
the original released source commit; the branch carries only the release index.

This is repository maintenance. Submission protocol 1.2, installed plugin behavior,
plugin permissions and workflow-reference format do not change; no plugin ZIP or
live-workflow update is needed. The selected world's approved contracts continue
to govern contributions.
