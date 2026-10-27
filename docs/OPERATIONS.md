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
and branch deletion. Restrict new governance changes to human maintainer review.
Owner-enrolled exact upstream core copies use the upstream approval and automated
destination verification described in `docs/CORE_UPDATES.md`; they do not add a
per-fork human review requirement or bypass repository protections.

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

## Change-impact reports

Compare two locally available, admitted revisions without changing either model:

```sh
python scripts/change_impact.py --before <old-commit-sha> --after <new-commit-sha>
python scripts/change_impact.py --before <old-commit-sha> --after <new-commit-sha> --format text
```

`--repo PATH` selects another local repository. JSON is the default stdout format;
`--format text` provides a review/maintenance summary. The library operation is
`scripts.change_impact.compare_revisions(repo, before, after)`. Both revisions
pass the compiled package's structural/closure gate before a report is returned.
The report pins each full source revision, input-tree hash and compiled-manifest
hash. It runs offline and ignores uncommitted worktree edits.

Report format **1.0** contains `changes`, `dependency_impacts`, and
`contextual_impacts`. Changes include full before/after canonical records, their
IDs, changed fields and `added`, `edited`, `retired` or `removed` operations.
`support_changed` marks source/evidence changes and changes to evidence links.
The report compares all canonical fields, including statements, class, uncertainty,
limitations, sources, lifecycle, connectors and questions. Provenance remains in
the pinned compiled packages; a provenance-only edit does not invent a claim change.

Dependency impact follows declared source-to-evidence-to-claim links, connector
evidence, reverse active dependencies and evidence-premise sets. Paths retain the
whole joint premise set when crossing an evidential premise. Each result names the
changed record, affected claim, snapshot (`before` or `after`), before/after claim
state and the exact typed path with evidence/connector IDs. The first claim consumer
is `direct`; subsequent claim consumers are `transitive`. The changed claim itself
is listed under changes, rather than as its own consumer.

Each snapshot is traversed separately so removed and added edges cannot create a
path that never existed. Retired connectors do not propagate in that snapshot;
their earlier active paths remain inspectable in the before snapshot. For each
changed record and affected claim, the tool keeps one explanation per snapshot and
impact type: fewest claim consumers, then fewest steps, then lexical edge order.
Distinct changed-record causes are retained; all alternative paths are not enumerated.
An active coupling produces contextual exposure of its adjacent claims, including
couplings reached through support/dependency paths. Traversal stops at the coupling;
context never becomes dependency propagation. No links are inferred from text.

Every impact is `potentially_affected`. It is a reassessment prompt, not a finding
of invalidation. The tool makes no epistemic judgment and writes no canonical
record, maintenance workset or proposal. Corrections still require the existing
governed admission/maintenance and independent review.

## Revision-pinned retrieval

Query a compiled package locally:

```sh
python scripts/query_knowledge.py --package .resolvent/knowledge lookup C-<id> --level 2
python scripts/query_knowledge.py --package .resolvent/knowledge search "signal" --state active --limit 10
python scripts/query_knowledge.py --package .resolvent/knowledge traverse C-<id> --depth 2
python scripts/query_knowledge.py --package .resolvent/knowledge dependents C-<id> --depth 3
```

Use `--manifest-sha256 <digest>` before the subcommand to require an exact build,
using the digest printed by the build command. Every JSON response identifies the
source revision, manifest digest and input-tree digest under `build`. The loader
verifies artifact bytes, input-tree manifest consistency and format/schema 1.0;
it revalidates canonical records and closed provenance with the installed policy,
then checks the compiled reverse links against those records. Select a trusted
admitted build and retain its manifest pin: a self-declared hash or revision is
not independent evidence of authenticity or semantic approval.

The host-independent Python surface is `Knowledge(package, manifest_sha256=None)`
in `scripts/query_knowledge.py`, with `lookup`, `search`, `traverse`, `dependents`
and `rebuild_index` methods. It performs no provider, database or hosted API calls.
Queries and index rebuilds leave canonical records and package files untouched.

Claim disclosure levels (`--level 0`, `1`, or `2`) are progressive:

- **L0:** the full claim record: ID, scoped statement, class, uncertainty, lifecycle
  and evidence IDs. Lookup also accepts evidence, source, connector and question
  IDs, returning their native records.
- **L1:** related claim metadata, connector records, evidence summaries/limitations,
  source IDs, linked questions and recorded closure/maintenance gaps.
- **L2:** full evidence premise sets, source URIs/dates/locators/excerpts and explicit
  `inspected`/`not_retrieved` status, plus original contributions, closures, research
  archives, relevant maintenance and declared parent-run provenance.

Search returns claims only. It indexes their statements, linked evidence summaries
and limitations, and linked source title/URI/date/locator/excerpt text. It requires
all query words, ranks by whole-word occurrence count, and breaks ties by claim ID.
`relevance` means keyword retrieval relevance only. Rebuilding the in-memory index
preserves IDs, records, provenance and deterministic results. An empty query provides
filtered discovery; `--class`, `--uncertainty`, and `--state` restrict claims. Both
active and retired claims are included unless explicitly filtered. Rejected/deferred
candidate text and open proposals are never indexed as admitted claims. Missing
records or search matches do not establish that a proposition is false.

Traversal follows declared connectors using `--direction incoming|outgoing|both`
and optional `--connector-type dependency|coupling`. Direction refers to canonical
connector endpoints: a dependency goes from dependent to premise. `dependents`
instead walks reverse dependencies and evidential premise sets, including premises
of evidence supporting dependency connectors without a direct claim backlink.
Paths preserve joint premises and the supporting evidence/connector IDs; coupling
is excluded. Active connectors are used
by default. `--include-retired` adds retired connectors and exposes their state in
each step. Claim lifecycle and uncertainty remain visible at every level.

Search and graph queries return at most `--limit` items (default 20, maximum 100).
Search supports `--offset`; graph depth is explicit (default 1, maximum 10), and
`truncated` signals a result limit. Each related/provenance collection has its own
`total` and `next_offset`: `--related-limit` defaults to 50 (maximum 1000), and lookup
supports `--related-offset` to fetch later pages. Direct record lookup remains
available for every linked canonical ID. The query format is version 1.0 and all
returned data belongs to the selected build, independently of later repository edits.

## Historical knowledge and world-valid time

Use separate operations for the two questions:

```sh
python scripts/build_knowledge.py --revision <admitted-tip> --known-at 2026-04-01T12:00:00Z --output .resolvent/historical
python scripts/query_knowledge.py --package .resolvent/historical search
python scripts/query_knowledge.py --package .resolvent/current valid-at 2026-01-15 --level 2
```

`--known-at` selects the nearest ancestor on the pinned tip's first-parent chain
whose recorded Git committer timestamp is at or before the supplied instant. It
requires a timezone-qualified timestamp. It reads local history without fetching;
unavailable history or no eligible commit fails explicitly. Record the returned
full revision for reproducibility. Git clock skew can affect time selection: the
timestamp is recorded admission-history metadata, not an independently verified
clock. Exact revision selection remains the unambiguous historical interface.
The API is `knowledge_revision(repo, revision, known_at)`, or the optional
`known_at=` argument to `compile_revision`/`build`. Building by time produces the
same bytes as building the exact selected revision, without adding a build timestamp.

`Knowledge.valid_at(at, ...)` / `valid-at` asks about the world time described by
the selected package's evidence, even when that world time predates discovery,
source publication and admission. It accepts a full calendar day or an explicit
offset-qualified instant. It returns separately paged `matches` and `unresolved`
collections, with temporal reasons and an `outside_recorded_intervals` count.
All claim classes, uncertainty and lifecycle remain visible. The usual disclosure,
limit/offset and related-record controls apply to each collection. Dates with
insufficient precision, incompatible calendar/instant domains, absent annotations
and declared disputes are unresolved; no query retires or promotes a claim.

For migration, adopt this governance and optional claim schema on each existing
repository through its own reviewed PR. Existing 1.0 runs and unannotated canonical
records need no rewrite; they remain usable, with unknown applicability shown
separately. New temporal contributions use protocol 1.1. Preserve original source
dates, merged provenance and run IDs. The shared plugin 1.1.0 understands both
protocols and must use legacy 1.0 on a repository that has not adopted 1.1.
See `docs/Ontology.md` for reviewed interval semantics and identity rules.

## Source lineage reports

From an existing verified compiled package, inspect all recorded source/evidence
lineage or focus on a canonical evidence item:

```sh
python scripts/query_knowledge.py --package .resolvent/knowledge lineage
python scripts/query_knowledge.py --package .resolvent/knowledge lineage --evidence E-<uuid>
```

`Knowledge.lineage(evidence_id=None)` returns a deterministic read-only report pinned
to the package's build/revision. It retains source/evidence records and anchors,
declared source ancestors, unknown/unretrieved nodes, upstream evidence through
joint claim premises, associated claims and connector-only evidence. A focused
report includes related evidence sharing an origin plus the required upstream nodes.
Unfiltered reports preserve unused source records too. L2 retrieval and keyword
discovery include declared source ancestors without changing relevance into confidence.

Flags distinguish `deterministic_metadata` (same declared source/ancestor or identical
declared SHA-256) from `heuristic` (same normalized HTTP(S) URI or repeated substantial
excerpt). Hash equality is a declaration about exact content, not proof of truth or
inspection. Source URIs are never fetched. Excerpt comparison normalizes case and
whitespace and requires 80 characters/12 words; common boilerplate can match.
Flags include source/evidence IDs, claim associations, access and an unresolved
independence assessment. No flag or missing flag changes canonical independence,
uncertainty, lifecycle or admission. Missing ancestry remains usable and unresolved.

The format remains derived wrapper 1.0; native optional source ancestry is retained.
Compiler 1.2.0 fingerprints the updated schema/policy. New contributions use protocol
1.2 only after that world's reviewed governance upgrade; no old record rewrite is
required. See `docs/Ontology.md` for field semantics and `docs/PLUGIN_RELEASE.md` for
client/workflow compatibility. Reports and rebuilt indexes never write model data.

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

## Change-signal maintenance

After adopting this governance, a repository owner can enable the native trigger
once by setting the Actions repository variable `RESOLVENT_CHANGE_SIGNALS` to
`true`. No per-contribution action is needed. A successful `Resolvent validation`
main **push** run triggers one bounded pending workset after newly admitted
`input-artefacts/RUN-*.json` material appears. The template skips itself. Governance
and maintenance-only merges do not loop back into maintenance.

The workflow checks out the exact validated main revision, shares the existing
`resolvent-maintenance` concurrency group/branch prefix and uses the existing token
permissions. It reads only the bounded push-range metadata emitted by that exact
successful validation run, checks repository/head identity, and never executes PR
code or fetches source URLs. It checks current remote main before publishing; a newer head is explicitly
deferred. It reuses change-impact analysis across the full before/after range of
the push, including rebased multi-commit contributions,
then opens a ready PR containing only `maintenance/M-*.yaml`.
Existing agents must process that pending workset; structural validation blocks
merge until completion and independent review remains required.

For an explicit local signal, use a JSON object matching
`docs/schemas/change-signal.schema.json`:

```sh
python scripts/change_signals.py --signal .resolvent/signal.json
python scripts/change_signals.py --signal .resolvent/signal.json --apply
```

The first command reports a plan. `--apply` atomically creates only its pending
maintenance record on the selected checkout; commit that record on a PR branch
through the usual path. Source/agent/manual signals need known affected IDs; an
unknown or unavailable source is recorded without pretending it was inspected.
There are no external watchers or account grants. Do not include secrets, unrelated
chat history or private reasoning in a signal. Its metadata becomes PR provenance.

The default is 40 claims (maximum 200), one pending workset across weekly/event
maintenance, and an hour between processed event worksets. `--limit` and
`--debounce-seconds` bound explicit local runs. Ranking favors declared/changed
claims, declared dependency impact, then recorded question/follow-up gaps within
the affected set; source ancestry expands advisory source discovery. Contextual
exposure stays distinct from dependency. No heuristic creates a justified link,
uncertainty upgrade or accepted claim. Overflow and unknown IDs are explicit
deferrals. Unrelated gaps do not authorize expanding the affected set.
Completed targeted worksets count as reviewed coverage but do not advance the
weekly rotation cursor; only completed weekly/manual worksets advance that cursor.

Replays deduplicate against recorded trigger identities. A changed upstream version
has a distinct identity but cannot bypass the pending-workset or debounce checks.
The native publisher also remembers existing/closed workset PRs and resumes its
exact original branch after a failed PR creation without overwriting it. A failed
validation dispatch can be retried without creating another PR. Unfamiliar branches
stop publication. Deferred signals are logged, not queued in a new service; the
unchanged weekly rotating maintenance remains the backstop. Disable the variable
to stop event preparation without disabling weekly/manual maintenance.

Compiler 1.3.0 fingerprints the signal validator and maintenance profile 1.1.
This changes repository maintenance only: submission protocol 1.2, canonical
records, installed plugin authority and workflow reference protocol are unchanged.
The installed plugin reads the selected world's approved contracts; no plugin
package or live-workflow update is required for this change.

## Skill releases

For automatic, data-preserving core updates in opted-in forks/template copies,
see [CORE_UPDATES.md](CORE_UPDATES.md). This is separate from plugin distribution.

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

The generic plugin has no default world repository. Users select a repository or
organization when model access is requested, optionally via native project instructions.
Chat research/reformulation alone grants no model access. The fixed client verifies
separately versioned live references from `workflow-release`; installed instructions load current
repository contracts through authorized access; contributions retain schema version.
System changes require assessing plugin compatibility and issuing a new plugin
release when necessary. Validated main changes publish GitHub release assets and
the standalone `plugin-release` branch through release CI. Claude directory updates
can follow that branch automatically after initial setup. ChatGPT workspace admins
can import that GitHub marketplace once and receive automatic syncs; public ChatGPT
directory skill updates still require upload/review/publication. These are different
distribution routes. See `docs/PLUGIN_RELEASE.md` for exact setup and limitations.

## Scope and privacy

Do not import the template's predecessor history, company claims, evidence, reports,
funding simulations or source material. Do not submit unrelated chat turns, secrets,
patient records, or other sensitive personal information without explicit authority
and suitable repository access controls. A private repository is not a substitute
for applicable data-handling obligations. Full transcripts are not required.
