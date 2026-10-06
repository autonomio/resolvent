# Repository operations

## Bootstrap

Use the Autonomio template to create a private or otherwise deliberately scoped
repository. No replacement of hardcoded business names is required. Keep `main`
empty of claims until real contributions are admitted. Test fixtures are synthetic
and are never copied into canonical data directories.

Template-generated repositories do not inherit branch protections, organization
app grants, secrets or repository permissions. The owner must make sure the existing
PR-triggered agents and researchers' GitHub connections have access to the new repo.
Require `World model integrity`, independent review, stale-approval dismissal,
conversation resolution and an up-to-date branch before merge. Disable force pushes
and branch deletion. Restrict governance changes to human maintainer review.

The bootstrap owner may initialize an empty repository with the template files.
Subsequent research and maintenance changes use PRs. No sample research is merged.

## CI

The workflow installs pinned validation dependencies on GitHub-hosted runners.
`World model integrity` runs trusted base-branch code against the proposed model;
it checks exact delta coverage and fails while admission or maintenance is pending.
`Tests and skill package` runs candidate tests without secrets or write privileges.
A separate policy job never executes contributor code with a write token.

A workflow/code/schema change goes in its own governance PR. After approval, the
new policy applies to future contributions. Structural green status is not semantic
approval. External review agents need their own proper review identity/permissions.

## Scheduled maintenance

The weekly Monday workflow and its **Run workflow** button create one workset PR
when claims exist and there is no open `resolvent/maintenance/…` PR. It uses the
repository's scoped `GITHUB_TOKEN`: contents write, pull-requests write, actions
write only to explicitly dispatch validation on the new branch. Enable GitHub's
**Allow GitHub Actions to create and approve pull requests** repository setting if
permitted by organization policy. The workflow creates PRs; it never approves one.

GitHub suppresses some workflow triggers for token-authored changes. The scheduler
therefore explicitly dispatches validation. Existing external agent infrastructure
must react to the created PR; an agent that itself only runs through suppressed
GitHub Actions events needs an authorized dispatch or its own app trigger. Do not
assume a scheduled PR proves an agent actually ran. The pending-workset check blocks
merging an unprocessed run. A configured `RESOLVENT_AUTOMATION_TOKEN` secret is an
optional organization-approved alternative when your trigger integration needs an
app/user token; it is not required for researchers or ordinary contribution CI.

The scheduling job never checks out untrusted PR content, never reads external
source URLs, and does not mutate canonical claims. Empty model = no-op. Complete or
close an existing maintenance PR before the next one is created. Review summaries
and deferrals remain in immutable maintenance records.

## Skill releases

`skills/resolvent/` is canonical; `dist/resolvent.zip` is a reproducible build:

```sh
python scripts/package_skill.py
python scripts/package_skill.py --check
```

For a pre-bound distribution (no impact on the generic template):

```sh
python scripts/package_skill.py --repository OWNER/REPOSITORY --output /tmp/resolvent-for-team.zip
```

The generic skill is reusable across repos; explicit target selection prevents
cross-company misrouting. An installed skill is not a live GitHub checkout. It loads
current repository contracts through the connector, and contributions record schema
version. Re-upload after an incompatible skill/protocol release. Distribute via your
existing Claude organization settings when supported; no custom deployment service.

## Scope and privacy

Do not import the template's predecessor history, company claims, evidence, reports,
funding simulations or source material. Do not submit unrelated chat turns, secrets,
patient records, or other sensitive personal information without explicit authority
and suitable repository access controls. A private repository is not a substitute
for applicable data-handling obligations. Full transcripts are not required.
