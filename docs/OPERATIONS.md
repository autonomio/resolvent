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
A world that opts in with `verified_contributions: true` in `resolvent.yaml`, through
a governance PR, admits verified contributions mechanically, and they merge without
review (see `docs/AGENT_JOBS.md`). To allow that, let the identity that merges them do
so without an approving review, for example with a pull-request-only ruleset bypass.
Keep the required checks and an up-to-date branch for every PR, and keep review
required for everyone else. CI checks a receipt against the statements it covers; it
does not authenticate the producer. Opt in only for a producer the world trusts, and
let the bypass identity merge only that producer's verified contribution PRs.
Without the opt-in, nothing changes.

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

## Data-file size

Core 1.3.1 accepts each model or provenance data file up to and including
10 MiB (10,485,760 bytes). The same byte limit applies to working-tree reads,
committed Git snapshots and serialized admission/maintenance writes. Larger
files fail before parsing or writing. Existing worlds adopt this limit through
their normal core update; installing a plugin alone does not update that policy.

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

Claim search indexes statements, linked evidence summaries
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
available for every linked canonical ID. The query format is version 1.1 and all
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

`Knowledge.lineage(evidence_id=None, limit=None)` retains the complete native
programmatic report. The default API/CLI now returns bounded cards (see below), pinned
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

### Nightly recent mode

Set the Actions repository variable `RESOLVENT_MAINTENANCE_SCHEDULE` to `nightly`
to prepare one recent workset a day (04:47 UTC) instead of the weekly selection.
The weekly Monday run then does nothing, and **Run workflow** prepares a recent
workset too. Unset, or any other value, keeps the weekly/manual behavior above.
The same token, permissions, concurrency group, branch prefix and one-open-PR
rule apply. While nightly is selected the weekly rotation does not run, including
its role as the change-signal backstop; `python scripts/gap_finder.py --write`
still prepares a weekly workset on request.

`python scripts/gap_finder.py --recent --write` prepares the same record locally:

- `claim_ids` are exactly the claims at `HEAD` that are absent from the window
  start's tree, with no never-reviewed claims and no rotating sample.
- The window starts at the `base_commit` of the last completed recent workset on
  `HEAD`'s first-parent history, so it never reaches back past the last completed
  one. Once a recent workset has completed, a late or failed night loses nothing:
  an open workset PR holds back the next night (one open maintenance PR at a
  time), and a workset closed unmerged is covered again by the next window.
- Until a recent workset has completed, nothing records a start. The window then
  starts at the last first-parent revision committed at or before 24 hours
  (`--hours`) before preparation, or at the empty model when history is younger.
  Complete that first workset rather than closing it. If a night before the first
  completion is missed or closed unmerged, re-cover it with **Run workflow** and a
  larger `hours` input (or `--hours` locally).
- A completed recent pass reviews every claim in its workset, so a completed
  window is covered in full. A pass that cannot finish leaves its workset pending.
- When nothing was added, nothing is written and the workflow opens no PR. There
  is one recent pass per UTC date: after a pass created that date has completed,
  no further recent workset is prepared until the next date.
- It reads committed Git objects and recorded committer times only. Uncommitted
  world data and shallow clones fail; the workflow fetches full history.

The record is maintenance profile 1.3. Its `window` records the start rule, the
previous recent workset (if any), the start revision and its committer time, the
base revision's committer time, the hours used, and the sources and questions the
window added (read from Git trees, never from record contents). Completed recent
worksets count as reviewed coverage but do not advance the weekly rotation cursor.
Agents read the whole input with the `recent` read below and follow the `recent`
mode of the maintenance contract and `docs/AGENT_JOBS.md`.

A completed recent pass adds its nightly brief, `nightly-briefs/YYYY-MM-DD.md`,
in the same PR. `world_control.py` generates its numbers from the completed record,
and the pass writes what moved per question and where the model is going. The
brief is a report kept beside the data, not knowledge: `load_state`, compiled
packages and the queries never read it as a record. The only read of a brief is
`previous_brief` in the next `recent` response.

A recent pass merges on green CI alone, with no independent review, and `World
model integrity` is its only check. Besides the usual integrity and delta rules,
the gate re-derives the workset's window from Git history, so the integrity job
checks out the proposed state with full history. It refuses anything outside the
recent rules: an operation without an added claim as a subject, a reassessment
other than one that settles an equivalent merge of different grades, any change
beyond the record, its brief and its recorded operations' results, or a brief that
does not match the record. Keep the review requirement in branch protection for
every other PR. The identity that merges recent passes needs permission to merge
without an approval, and should merge only a PR that completes a recent workset.

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

## Model tooling for external agents

Core 1.3.0 / compiler 1.4.0 adds local model operations. External agents own
comparison, linkage and reassessment, including semantic judgments and execution.
Resolvent accepts valid supplied research; it does not implement those behaviors,
fetch sources, invoke providers or add a scheduler. The existing admission and
maintenance lanes, independent review and protected merge remain in place.

Build a pinned closed package with the existing builder. Available reads include:

```sh
python scripts/query_knowledge.py --package .resolvent/knowledge candidates "candidate wording" --kind claims
python scripts/query_knowledge.py --package .resolvent/knowledge candidates --kind questions --offset 20
python scripts/query_knowledge.py --package .resolvent/knowledge context C-<id> --purpose reassessment
python scripts/query_knowledge.py --package .resolvent/knowledge passage S-<id> --field excerpt
python scripts/query_knowledge.py --package .resolvent/knowledge assessments C-<id>
python scripts/query_knowledge.py --package .resolvent/knowledge changes --before-package .resolvent/earlier
python scripts/query_knowledge.py --package .resolvent/knowledge lineage
python scripts/query_knowledge.py --package .resolvent/knowledge lineage-flag <flag-id>
```

The Python methods use those names. New reads and default lineage return at most
20 cards (maximum 100) and 32 KiB of encoded JSON, including build metadata.
`--max-bytes` can lower the cap to 1 KiB. Responses include totals and `next_offset`;
continue against the same pinned package. `passage` offsets count characters,
while its output cap counts encoded bytes, preserving Unicode and escapes. Omit
`--field` to read an entire native record/operation JSON in chunks. An item that
cannot fit fails explicitly. Existing full lookup/search/traversal retain their
native disclosure interfaces; use cards/passages for bounded agent context.
The former complete lineage library report remains available only via explicit
`limit=None`; it is not the bounded agent surface.

`candidates` accepts each canonical kind. Empty text enumerates by ID; nonempty
text ranks any keyword overlap, with selection reasons. It does not infer meaning,
truth or independence. `search --kind sources|evidence|questions` returns grouped
cards; ordinary claim search and valid-time reads group accepted equivalents too.
Existing lineage flags supply source-origin/hash/URI/excerpt cues; `lineage-flag`
returns bounded member cards. Context returns a selected group neighbourhood,
with evidence, declared premises, relationship endpoints, questions and operation
references. Use passage/lookup for details and the existing traversal/impact tools
for further investigation. No read implies exhaustive coverage.

Query envelope 1.1 retains build pins and adds `model_sha256` (canonical records
plus accepted operation contents). The compiled artifact wrapper stays 1.0.
Supplied assessments are visible at `RUN-ID#candidate-id`; operation references
are `BC-ID#local-id` or `M-ID#local-id`. Grouped views combine provenance, list
member IDs and legacy states, and expose differing assessments as disputed.
Every original record remains directly addressable. The representative can change
when members join; use an original member ID as the stable group address.

### Recent-additions read

`Knowledge.recent(repo, hours=24, at=None, to=None, overlap_limit=20)` and the
`recent` CLI return the whole input of a recent maintenance pass as one complete
JSON response. It has no paging and is the exception to the 32 KiB card bound:

```sh
python scripts/query_knowledge.py --package .resolvent/knowledge recent --repo . --at <created_at> --to <base_commit>
```

`--repo` (default `.`) is a local repository holding the package revision and its
complete first-parent history. Only Git objects and committer times are read; no
checkout, fetch or worktree read happens and nothing is written.

- `window`: `start` rule, `previous_workset_id`, `from_revision` and
  `from_committed_at` (null at the empty model), `to_revision` and
  `to_committed_at`, `new_source_ids` and `question_ids` (as recorded in the
  workset), plus `hours`, the evaluation instant `at` and its `cutoff`.
  The rule is the recent workset's own, evaluated as of `to_revision`. That is the
  package revision unless `--to` names one of its ancestors. With `--at` set to a
  workset's `created_at` and `--to` to its `base_commit`, the window and added
  claims are that workset's exactly, even from a later package. Claims admitted
  after `--to` remain comparison targets. Without `--at`, the instant is now.
- `added`: each claim present at `to_revision` but absent from the window start, in
  ID order. Each entry carries the statement, class, temporal scope, uncertainty,
  state, valid time, evidence, source and question IDs, plus the full evidence,
  source (with declared ancestors) and question records. `added_in_window_ids`
  lists those that are also new. It also lists the run admissions, incident
  connectors and comparisons.
- `compare_with` (per added claim): every other active claim that shares a source,
  belongs to the same question, or overlaps in wording, with `reasons` saying which
  apply. A shared source is the same record, a record in the same accepted
  equivalence group, a declared ancestor, or the same declared content SHA-256. A
  shared question is the same record or an equivalent one. Each entry carries the
  statement, class, temporal scope, uncertainty, state, evidence and source IDs,
  group members, current assessment and `added_in_window`, and `links`: connectors
  between the two with their record digests, comparisons with whether each is
  current, and premise evidence linking them. Shared sources and questions are
  never capped. Claims related only by wording are ranked by the Jaccard overlap of
  distinct statement words, then by shared-word count, then by ID. The first
  `--overlap-limit` (default 20, 0 to 1000) are kept, and `wording_overlap.omitted`
  counts the rest.
- `decisions`: `expected_model_sha256`, `reviewed_claim_ids` and an empty
  `nightly_brief` (`what_moved`, `course`) for the decisions file. Current
  comparison IDs (`supersedes`), current assessments (`predecessors`) and connector
  digests (`previous_sha256`) are in the entries, so a pass needs no other read.
- `shape`: the whole model as generated counts over active claims only:
  `claims`, `claims_per_question` (keyed by question reference, the smallest ID of
  a question's equivalence group), `claims_without_question`, `grade_spread`,
  `disputed_groups` (equivalent claims whose grades differ) and
  `source_concentration` (cited source groups, the ten supporting the most claims,
  the claims citing any of those ten, and how many sources support each number of
  claims).
- `previous_brief`: the text of the nightly brief of the recent workset the window
  starts from, read from Git at `to_revision`, or null when the window has no
  previous recent workset. `shape` and `previous_brief` serve only the brief's last
  section.

Keyword overlap and shared metadata are comparison cues, not identity, support,
truth or semantic similarity. Semantic matching is not performed. A claim with no
cue is not shown to be unrelated.

Compatibility: core 1.6.0 / compiler 1.7.0 adds maintenance profile 1.3, maintenance
contract 1.4, model-operations contract 1.3 and nightly briefs. Existing profiles
and records still validate unchanged, and a world behaves as before until it adopts
this core and sets the variable. For existing worksets the writer newly accepts only
the merged-group reassessment described below; for a recent workset it applies the
recent rules and writes the nightly brief. `compiler.py` also checks
each brief against its pass. Submission protocol 1.2, canonical record formats,
compiled package format 1.0 and query envelope 1.1 are unchanged. The generic plugin
performs contributions only and never prepares or runs maintenance, and no packaged
file changes, so no plugin package or live-workflow release is needed.

### Per-question research-state export

`Knowledge.research_state(reference, repository=..., reference_pointer=None)` and
the `research-state` CLI expose portable schema 1.1 in
`docs/schemas/research-state.schema.json`. Use a closed package built from the
selected admitted/reviewed revision. Package validation checks structure; it does
not certify maintainer approval. The repository identity is supplied by the caller
from its selected destination, not guessed from the package or an external page.

```sh
python scripts/query_knowledge.py --package .resolvent/knowledge research-state Q-<id> --repository owner/world
python scripts/query_knowledge.py --package .resolvent/knowledge research-state external-question-9 --repository owner/world --reference-pointer /method_metadata/external/question --source-repo . --complete > .resolvent/research-state.json
```

For an external question without a Q record, supply the JSON pointer to its
existing reference in preserved RUN submissions. Matching is exact and includes
all matching submissions at the pinned revision. The pointer is a local field
address, never a URL to fetch. For example, a producer that already stored a
reference under `method_metadata.portal_context.question_ref` can select
`/method_metadata/portal_context/question_ref`; no Portal service is needed or
consulted. An absent reference fails instead of inventing a question binding.
Each preserved brief's question text remains separately attributed.

`--source-repo` (Python `source_repo=Path(...)`) optionally reads the original RUN
JSON from the package's exact Git commit using the existing local object reader.
It disables replacement objects and lazy fetching, verifies each original blob
against the package's input-file hash and requires equal compiled JSON values.
This preserves the original object-field order for producer checksums that cover
embedded JSON strings. Compiled values alone normalize field order and can make
those checksums unverifiable; without original objects that coverage stays unknown.
No selected-revision code is executed and no source, URI or missing object is fetched.

The continuation view exposes native `claims`, `evidence`, `sources`, `graph`
and `questions` arrays, with original IDs, source passages and current assessment
views. Selection retains only the question's admitted claims and their complete
evidence/premise/source support chains. Context supplies relationships within
those claims. Other graph neighbours and unused producer sources are omitted
explicitly. No relevance or new contradiction is inferred.

`references` contains publication identities and recorded discovery, citation,
retrieval and review stages. `reviewed_papers` contains only documented,
producer-selected core/supporting reviews with read-passage IDs, investigated
sections, a substantive note and no recorded preview warning. Other review records,
access limitations and unknown coverage stay under `review_coverage`. These are
producer declarations; source inspection, matching hashes and citation alone do
not establish substantive review or independent evidence. References without
review records remain unknown, not never-reviewed.

An identity is a non-empty string. `review_coverage.unidentified_references` is
always present, and empty for a clean report. It discloses each reference without
an identity, with its recorded display fields, computed stages and row-level
`#/references/<i>` origin. Such a row is explicit unknown coverage. It never joins
a review by DOI or URL, its `substantively_reviewed` stage stays `unknown`, and the
run's other records and `preserved_producer_report` status do not change. A review
without a usable `work_id` stays in `review_coverage.other_reviews` as
`unmatched_reference`.

Only submissions explicitly bound to the selected question contribute paper-review
history, contradictions, gaps, caveats and next questions. Parent-lineage metadata
is retained as `lineage_only`; it never imports another question's paper reviews.
`rejected_deferred_findings` preserves proposal statements, dispositions, evidence
and source-access records separately from admitted claims. Source excerpts for
those unadmitted proposals remain at their pinned origins rather than being copied
into continuation context. Canonical supporting passages remain included.

The existing `canary-research.json` and `canary.references` version 1 extension are
read locally with a checked reconstruction checksum and a conservative 32 MiB
decoding budget. No Canary installation, provider, credentials or filesystem/URL
reference resolution is required. Missing, malformed or unsupported reports yield
unknown coverage with pinned provenance. In producer `basis` strings, a pointer
after a second `#` addresses the decoded embedded JSON document.

Exact repeats of the selected reference, review and gap display fields share one
display entry with every occurrence's provenance. Differing coverage and review
notes remain separate. This compacts repeated data; it neither equates canonical
records nor establishes independent observations. `provenance` retains submission
and receipt IDs, paths, original input-file hashes and selected record IDs. Full
RUN/receipt bodies, producer UI/encoding payloads, file inventories and download
metadata are omitted. The same pinned repository objects retain those originals.

Default responses use the existing passage transport: at most 32 KiB of encoded
JSON, `text`, `total_chars`, `offset`, `next_offset`, `truncated` and a digest of
the complete serialized view. Keep repository, selector and package fixed;
concatenate page text by character offset, verify `state_sha256`, then parse JSON.
`--max-bytes` can lower the transport cap to 1 KiB. `--complete` (Python
`complete=True`) explicitly returns this complete continuation view for a local
file or consumer. It does not include omitted archive data or remove selection
omissions, and consumers still enforce their own input limits.

Compatibility: this adds a local core read only. The compiled package format,
submission protocol, canonical admission and generic plugin's existing operations
are unchanged. The public workflow MCP still receives no repository data or chat
content. No plugin ZIP, manifest or live-workflow release is needed.

Schema 1.1 requires `review_coverage.unidentified_references` and a non-empty
`references[].id`, so 1.1 exports do not validate against the published 1.0 schema.
Other fields keep their 1.0 meaning, except that an empty `id` or `work_id` is no
longer an identity. The research-state read is not part of the shared skill, either
host distribution or the plugin manifests, so no plugin change is needed.

To accompany admission, add `expected_model_sha256` from the reader and a
`model_operations` list to the existing decisions. Local operation IDs match
`[a-z][a-z0-9_-]{0,63}` and are unique within the receipt. Each decision supplies
`kind`, `subject_ids`, `basis_ids` and `reason`, plus the kind-specific fields in
`docs/contracts/activity/model_operations.json`. Subjects must intersect the
selected contribution or workset; reassessment targets must all be selected,
already admitted claims. In maintenance, an `equivalent` comparison of a workset
claim in the same decisions also selects every claim of the group it forms for
reassessment, so a merge that joins different grades can settle them, as the merge
rule for reviewed claims requires. A recent pass is narrower: every operation names
an added claim, and a reassessment is accepted only for claims of a group that such
a merge formed when that group's grades differed. At most 200 operations belong in
one receipt.

Comparison requires two same-kind records and `outcome`, with `supersedes: null`
for the first decision. Correct a decision by naming the current pair reference;
prior decisions remain immutable. Claims need matching class and temporal scope
for equivalence. Source equivalence preserves dates, versions and anchored
passages; evidence equivalence preserves origins, independence and joint premises.
Questions, sources and evidence keep per-run records and compact only in reads.
Exact claim reuse also requires matching uncertainty. Otherwise admission preserves
a separate claim and an external comparison can explicitly group it.

Reassessment supplies a new `uncertainty` and `predecessors` map for every target.
Null means no prior typed reassessment; the writer captures the actual legacy
baseline grade. Later results must name the current head. Only one new result per
claim per PR is allowed. Linkage supplies a complete graph-schema `record` with
an R-ID and `previous_sha256` (null if new); it uses the existing dependency and
coupling types. The predecessor is the admitted base record, including when the
same contribution creates and adjusts a connector. A new connector can cite its
input run as basis, rather than citing itself. Connector uncertainty is outside
claim reassessment history.
Neither comparison nor linkage changes claim uncertainty as a side effect.

For maintenance, use an existing pending M record; optional `subject_ids` selects
non-claim records without changing the existing claim-coverage fields. The decisions
contain `expected_model_sha256`, `model_operations` and `reviewed_claim_ids`, with
optional actual `findings`, `deferred` or `no_change_reason`. Run the same writer:

```sh
python scripts/world_control.py M-<id> --decisions .resolvent/decisions.json
python scripts/world_control.py M-<id> --decisions .resolvent/decisions.json --apply
python scripts/compiler.py --require-closure
```

The writer validates before applying, captures per-record read digests and previous
grades, and writes closure 1.1 or completed maintenance 1.2. Retry the same receipt
and decisions for no changes; changed decisions cannot rewrite a closed receipt.
CI checks read digests against the actual base, current predecessors, history
branching, grouped cycles, exact canonical deltas and legacy provenance integrity.
Unrelated base changes do not invalidate recorded per-record reads; changed basis
requires fresh decisions. Compiler green status certifies structure, not judgment.
Recent-change queries include provenance-only model operations. Existing recent,
targeted and rotating maintenance can use these interfaces without new scheduling.
No bulk migration, production-data rewrite or contribution protocol change is needed.

### Producer uncertainty metadata and reviewed merges

Core 1.4.0 / compiler 1.5.0 reads each candidate's preserved
`method_metadata.claim_metadata` `uncertainty` (the writer's grade),
`uncertainty_review` and `freshness` without any producer runtime. Admission
decisions and closures are unchanged: each candidate keeps its exported grade.

`query_knowledge.py assessments C-<id>` (`Knowledge.assessments`) adds to each
supplied grade that carries this metadata:

- `writer_uncertainty`: the original label and its ordinal grade.
- `uncertainty_review`: `status`, `recommended_uncertainty`, canonical and original
  evidence IDs, `producer_audit` (`complete`, `partial`, `ambiguous` or `absent`),
  the raw row's `audit_verdict`, limitations and any `prior`. `assessed` needs a
  reason, evidence in this contribution and a complete audit without duplicate rows;
  anything else is `not_assessed` and never compared. A prior shows the
  auditor-reported grade, a `destination` check against the package revision
  (`comparable`, `missing`, `stale`, `scope_differs` or `no_match_reason`), the
  recomputed `uncertainty_change` and the producer's own change.
- `review_horizon`: policy, dates, triggers, rationale and the fixed interpretation
  that a passed date changes nothing.

Free text is previewed and long lists are shortened with a note; the pinned run keeps
the originals. Contributions without this metadata report nothing extra.

A merge is a current `equivalent` claim comparison. When it joins claims whose
grades differ and any carries an `uncertainty_review`, admission refuses it. A
maintenance record performs it and reassesses every claim of the merged group, so
all of them must be in the workset:

```json
[{"id": "merge1", "kind": "comparison", "subject_ids": ["C-old", "C-new"], "basis_ids": ["E-old", "E-new"],
  "outcome": "equivalent", "supersedes": null, "reason": "Same proposition, class and scope."},
 {"id": "merge1-grade", "kind": "reassessment", "subject_ids": ["C-old", "C-new"],
  "basis_ids": ["E-old", "E-new", "RUN-new"], "uncertainty": "high",
  "predecessors": {"C-old": null, "C-new": null}, "reason": "Merged outcome on the cited evidence."}]
```

The writer captures `previous_uncertainty` for both claims: the old and incoming
grades. `basis_ids` cite every run whose review covers a merged claim. No merged
claim may end more confident than the most confident merged grade, and a merged
claim whose uncertainty falls must cite independent inspected evidence of the merged
claims. When one member cannot hold `low`, give it its own reassessment and outcome.
The writer and PR delta validation apply the same rule. Equal-grade merges, and
merges without producer reviews, keep the existing behaviour.

### Verified contributions

Core 1.5.0 / compiler 1.6.0 adds an opt-in mechanical admission for
`source_material` contributions with a version 1 `method_metadata.verification`
receipt, such as a connector v4 bundle. A world turns it on with
`verified_contributions: true` in `resolvent.yaml`; it is off by default. With it
off, the writer refuses `--verified` and CI adds no check.

`world_control.py RUN-ID --verified [--apply]` takes no decisions file. The writer
checks that each candidate has a supported final verdict, for the producer claim
mapped to it, bound to its exact statement's SHA-256, and that withheld claims stay
out. It accepts every candidate with the recorded verdict as its reason, keeps each
exported grade, defers relationships to existing claims to maintenance, and writes
an ordinary closure 1.0. With the opt-in on in the base branch's `resolvent.yaml`,
PR delta validation recomputes the admission on the actual base and fails unless
the delta is exactly that result, so an agent closure, an edited record or a stale
base cannot pass as mechanical. Contributions without a receipt, and closures
already merged, are unaffected.
