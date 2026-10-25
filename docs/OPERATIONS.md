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

## Compiled knowledge packages

Build a disposable, offline read view from a locally available admitted Git commit:

```sh
python scripts/build_knowledge.py --revision <full-commit-sha> --output .resolvent/knowledge
```

`--repo PATH` selects another local repository. A ref such as `main` is resolved
once to a full commit. The command reads committed Git objects, ignoring working
tree edits, and never executes code from the selected revision. It uses the
installed compiler's schemas and existing `validate_state(..., require_closure=True)`
gate. Pending admission, pending maintenance, invalid references, missing provenance
and stale closures fail before package output is written. Selecting a revision
with independent semantic approval remains the caller's responsibility; structural
closure cannot prove that a commit was reviewed or merged.

The output must be a new directory under the ignored `.resolvent/` directory, or
outside the repository. The command stages the complete package before exposing
the output directory. It never writes canonical records or updates an existing
package. The Python API is `scripts.build_knowledge.compile_revision(repo, revision)`
for package bytes, or `build(repo, revision, output)` for the same files on disk.

Format/schema **1.0** consists of two UTF-8 JSON files, with sorted object keys,
two-space indentation and a final newline:

- `knowledge.json`: `derived: true`, `format_version`, and `records` maps keyed by
  canonical ID under `claims`, `evidence`, `sources`, `graph`, and `questions`.
  All canonical fields, list order, uncertainty, limitations, inspection status,
  premise sets and lifecycle states are preserved. `record_paths` maps each
  canonical ID to its repository path. `provenance` contains the original
  contributions, closures, research archives and completed maintenance records,
  keyed by repository path; their candidate claims are not accepted claim records.
  `reverse_links` provides sorted, unique source-to-evidence, evidence-to-claim,
  evidence-to-connector, premise-to-evidence, claim-to-incoming/outgoing-connector,
  and claim-to-question IDs. Reverse links include retired records: consumers
  must inspect the referenced lifecycle and connector type. No inferred links
  are added, and contextual coupling remains distinct from dependency.
- `manifest.json`: artifact-format/schema/compiler versions, `derived: true`, the
  full `source_revision`, `input_files` SHA-256 hashes, `input_tree_sha256`,
  structural validation results, installed validation-policy file hashes and
  dependency versions, plus each artifact's byte length and SHA-256. Source data
  files include canonical records and provenance; ignored placeholders and data
  READMEs are excluded. `input_tree_sha256` is SHA-256 of the `input_files` object
  encoded as UTF-8 JSON with sorted keys, separators `(',', ':')`, no ASCII escaping
  and no trailing newline. Policy hashes identify the installed compiler, schemas
  and requirements; schemas from a historical data revision do not replace them.

Verify artifact hashes against their exact file bytes and input hashes against
`git show <source_revision>:<path>`. The command also prints the manifest's SHA-256
for consumers that pin a whole build. The manifest does not contain its own hash.
The same revision and compiler/policy/dependency bytes produce identical packages
across output paths; no build timestamps or local paths are added. Incompatible
output-contract changes require a new format/schema version. Transformation changes
require a compiler-version update. These views are derived and rebuildable; canonical
YAML and merged provenance remain authoritative. No database, provider key, LLM,
network access or additional dependency is required.

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

`skills/resolvent/` is the canonical shared workflow. Root `plugin.json`,
`.codex-plugin/plugin.json` and `.claude-plugin/plugin.json` describe the same generic
Autonomio plugin. The ChatGPT and Claude distributions contain identical source.
See `docs/PLUGIN_RELEASE.md` for compatibility assessment and release preparation.

```sh
python scripts/package_skill.py
python scripts/package_plugin.py
python scripts/package_skill.py --check
python scripts/package_plugin.py --check
```

The generic plugin has no pre-bound distribution or repository setting. Users
select OWNER/REPOSITORY in the invoking chat. Installed instructions load current
repository contracts through authorized access; contributions retain schema version.
System changes require assessing plugin compatibility and issuing a new plugin
release when necessary. Validated main changes publish GitHub release assets and
the standalone `plugin-release` branch through release CI. Claude directory updates
can follow that branch automatically after initial setup; ChatGPT skill updates
still require a publisher upload/review/publish step. See `docs/PLUGIN_RELEASE.md`.

## Scope and privacy

Do not import the template's predecessor history, company claims, evidence, reports,
funding simulations or source material. Do not submit unrelated chat turns, secrets,
patient records, or other sensitive personal information without explicit authority
and suitable repository access controls. A private repository is not a substitute
for applicable data-handling obligations. Full transcripts are not required.
