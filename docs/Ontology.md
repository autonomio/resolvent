# Resolvent ontology

## Claims

An assertion is the shortest **self-contained** statement preserving the proposition.
Keep material dates, populations, units, conditions, quantifiers and comparisons.

`claims/C-<uuid>.yaml` has `statement`, `uncertainty`, and `evidence_ids`. Its `id`,
`class`, and `state` are record metadata. No owner, review cadence, business-specific
schema payload, or fixed sub-world hierarchy is required for an assertion.

Classes retain the useful distinctions from Resolvent: `observed_fact`,
`derived_inference`, `assumption`, `hypothesis`, `forecast`, `scenario_variable`,
and `decision`. A class is not a certainty rating. Questions are separate records;
retirement is lifecycle, not a claim class. `observed_fact` means an observation is
recorded, not that a proposition is infallible or universal.

Uncertainty is ordinal: **low** = comparatively well-supported within stated scope;
**medium** = material limitations/indirectness remain; **high** = substantial doubt,
sparse evidence or an untested assumption. Low uncertainty requires independent
inspected evidence in this MVP; it never means certainty. Do not translate these
labels into numerical probabilities without a separately reviewed calibration.

## Temporal semantics (schema/protocol 1.1)

Keep three clocks distinct:

- **Valid time:** when the proposition applies in the world, according to the
  cited evidence. It is optional, reviewed claim metadata, not a date inferred
  from the statement or the source's publication date.
- **Source/report time:** `sources.date` remains the date as reported for that
  source. It is not silently reinterpreted as an event's effective date. An
  observation's time, when material, belongs in its scoped assertion and evidence;
  timing of relationships can likewise be represented by an evidence-backed claim.
- **Knowledge/admission time:** the canonical state present in a selected admitted
  Git revision. Time selection uses recorded committer timestamps along that
  revision's first-parent history. Those timestamps are repository metadata, not
  independently verified wall-clock observations or source dates.

An optional claim `valid_time` has `status` (specified, unknown or disputed),
`intervals`, and limitation `notes`. Each interval requires `start`, `end`, explicit
inclusivity booleans, and nonempty `evidence_ids` drawn from the same claim's
evidence. Null bounds explicitly assert an open/unbounded side; absence of the
annotation means unknown, never unbounded validity. Unknown status has no intervals
and needs an explanation. Disputed status keeps at least two evidence-backed
alternatives and notes; the compiler does not pick the preferred account.

A bound is `{precision, value}`. Calendar precision is year (`YYYY`), month
(`YYYY-MM`) or day (`YYYY-MM-DD`). Partial precision is preserved as the range of
possible boundary days; it is not replaced by a guessed first or last effective
date. Instant precision uses a timestamp with an explicit numeric offset or `Z`,
up to microseconds. Calendar and instant bounds are separate domains: without an
explicit evidence-backed conversion, do not assume a timezone to combine them.
Invalid calendars, reversed/necessarily empty intervals and unsupported precision
are rejected. Preserve unsupported or ambiguous source dates as unknown/disputed
metadata with limitations, rather than truncating or inventing precision.

The query asks either for a full calendar day or a timezone-qualified instant.
An interval matches only when its boundary precision establishes inclusion.
Ambiguous partial boundaries or mixed query/interval domains are unresolved.
Overlapping specified intervals express a union; declared disputed alternatives
remain unresolved. Unknown/disputed claims appear in a separate unresolved group.
Temporal applicability does not establish truth or change class, uncertainty,
evidence access or lifecycle. Retired records remain inspectable at past world times.

Temporal scope is material to identity. Admission remaps its evidence IDs, merges
additional support only for the same supplied temporal scope, and cannot silently
overwrite an existing ID with another temporal proposition. A meaning-changing
replacement needs a new ID while preserving the original claim. Metadata-only
annotations preserving an already scoped statement may retain the ID through
reviewed maintenance. Dates still belong in the self-contained statement when
material; the annotation is not a substitute for that requirement.

Protocol 1.1 adds this optional claim field; old 1.0 submissions and canonical
records remain valid and immutable. Source and connector schemas are unchanged.
Upgrade repository governance before using the extension; installing a plugin does
not migrate existing repositories or reinterpret their dates. The compiled wrapper
format stays 1.0, preserving native fields, with compiler/policy fingerprints updated.

Timestamp reference: [RFC 3339](https://www.rfc-editor.org/rfc/rfc3339.html) and
its [RFC 9557 offset clarification](https://www.rfc-editor.org/rfc/rfc9557.html#section-2).
`-00:00` retains unknown local-zone context while specifying a known UTC instant;
the original offset spelling remains in the source annotation.

## Evidence and sources

Every claim has an evidence record, including assumptions. Evidence can explicitly
record an unsupported assumption and its origin; a required field is not permission
to fabricate external support. Source records preserve title, source type, URI where
available, date where known, a location anchor, the relevant excerpt and whether the
source was actually inspected. An inaccessible citation is `not_retrieved`.

Evidence records distinguish external observation, reported statement, simulation,
derivation and assumption. They preserve limitations, source IDs, independence,
claim backlinks and **joint premise sets**. A conversation can establish that a
person/agent stated something; it is not independent verification of its content.
A second paper copying the first is not independent replication.

Claims and evidence link both ways; the admission tool maintains those backlinks.
A source may be referenced by several evidence records. Never promote confidence by
counting repeated summaries of the same underlying observation.

## Source ancestry (schema/protocol 1.2)

A source may have optional reviewed `ancestry` metadata: `status` (`original`,
`derived` or `unknown`), `parent_source_ids`, and nonempty limitation `notes`.
Absence means unknown. A declared original has no reused parents; a derived source
requires at least one known parent. Unknown may preserve partially known parents
without inventing the missing lineage. All references resolve to source records;
self-links and cycles are invalid. Existing IDs, excerpts, locators and inspection
status remain unchanged. An unavailable upstream source may remain unknown or be
represented by an honestly anchored `not_retrieved` source; never invent its passage.

Optional `version` identifies the source version; `content_sha256` is a lowercase
SHA-256 digest of explicitly identified exact content bytes. Do not present a hash
of a title, normalized excerpt or guessed content as a whole-source fingerprint.
A publisher-declared digest can be retained without pretending that the source was
retrieved; preserve the limitation in notes and the actual access status.

Declared parent links and matching declared digests establish metadata relationships,
not truth or independent observation. Same-URI and repeated-excerpt cues remain
heuristics. Different URLs, missing flags or declared originals do not establish
independence either. Reviewers inspect supplied support and scope; reports never
automatically promote evidence, alter uncertainty or retire a record. Preserve joint
premise sets when tracing evidence through earlier claims.

Protocol 1.2 adds only this optional source field. Immutable 1.0/1.1 inputs and older
canonical records remain valid; old inputs cannot retroactively acquire new fields.
Adopt the extension through repository governance before submitting it.

## Connectors

Keep two canonical types initially:

- **dependency**: `from` is the dependent claim, `to` its premise; failure of the
  premise may invalidate the dependent. The active dependency graph is acyclic.
- **coupling**: contextual influence while both assertions can remain independently
  valid. Couplings may form cycles; no duplicate reverse record is required.

Retain `spec` as `nature:weight:direction`: structural/economic/regulatory/narrative/
temporal, strong/moderate/weak, inward/outward/balanced. Direction is interpreted
from `from`; dependency direction is always determined by its endpoints.

Each connector has `reason`, its own `uncertainty`, `evidence_ids`, and lifecycle.
A `reason` must explain the mechanism. A shared topic, word, or source is a discovery
hint, not proof of a substantive relationship. Do not force a support/challenge
relationship into these types when it does not fit; record an open question and a
proposed ontology change instead. The types can expand through governance review.

`graph/R-*.yaml` is the single canonical edge representation. No manually maintained
TTL copy or mandatory graph database is needed. Reverse traversal is derived.

## Identity and history

UUID-based global IDs avoid collisions between concurrent researchers. Each
contribution is a `RUN-<32hex>` UUID, with local candidate IDs (`c1`, `e1`, `s1`).
Admission deterministically maps them into globally unique IDs. Retrying the same
run is idempotent. Continued or corrected research uses a new run and `parent_run_id`.

Merged contributions, closures, archived research phases and completed maintenance
records are immutable. Canonical assertions may gain evidence or be reassessed via
PR. Meaning-changing replacement gets a new ID; preserve the original. New claim
retirements are rejected; legacy retired claims remain readable. Neither a new ID
nor an equivalence decision redirects existing dependencies or moves evidence.
Different propositions coexist; explicit reassessment changes their credibility.
There is no new replacement-status field or automatic choice of a current proposition.

## Research artifacts

During research the contribution contains a prospective brief, result and proposed
handoff. On admission, archive the brief to `briefs/open/done/BR-*.yaml`, the result
to `briefs/ready/BR-*.yaml`, and generate `briefs/closed/BC-*.yaml` from the actual
changes. These are different artifacts, not duplicate mutable model truth.

For retrospective chat capture, `brief` is null: never pretend criteria existed
before the work. All routes still receive a closure manifest after admission.

## Change signals

A change signal is observation metadata that can suggest reassessment, not an
assertion in the world model. Schema 1.0 records event type, origin, reference,
upstream revision, observed instant, content/event fingerprint, explicit affected
IDs, reason and limitations. The instant describes observation, not claim valid
time. A `model_changed` signal also identifies its prior full Git revision.

Signal identity hashes version/type/origin/reference/revision/fingerprint, sorted
affected IDs and optional prior revision. Observation time, reason and limitations
do not make the same upstream event new. The fingerprint is declared metadata; it
does not establish that content was fetched or independently confirmed.

Maintenance profile 1.1 adds required `trigger: {signal_id, signal}`. Legacy 1.0
records cannot gain a trigger. The compiler validates the payload and recomputes
its identity. New records remain pending until the usual agent processing and
independent review; the pending record cannot merge. Completed records retain the
existing immutability rule. Contribution protocol 1.2 and canonical record formats
are unchanged.

## Recorded comparison and reassessment

Admission closure 1.1 and maintenance 1.2 may contain typed `model_operations`.
Their permanent address is the receipt ID plus `#` plus local operation ID. Results
name canonical subjects, supplied basis IDs, a reason and writer-captured read
digests. These are externally supplied judgments, not independent observations.

A comparison records `equivalent`, `overlap`, `distinct` or `unresolved` for two
claims, questions, sources or evidence records of the same kind. A correction names
the current comparison in `supersedes`; one current decision per pair and no
branching or circular history. Current equivalences form transitive read groups.
No current non-equivalence pair may occur within a group. Claims must share class
and recorded temporal scope. Source grouping preserves anchored passages, dates and
known versions; evidence grouping preserves origins, independence and joint
premises. Semantic identity remains the external agent's responsibility.

Every original ID is a stable address into its current group. The derived `id`
shown for a group is its smallest member, not a new persistent identity; it can
change as membership changes. Native records and raw relationship endpoints remain
intact. Grouping checks connector self-links and dependency/evidential cycles too.
Different legacy lifecycle states remain visible as group states; grouping never
reactivates a record or resolves a question.

Supplied grades are addressed as `RUN-ID#candidate-id` through their immutable
closure dispositions. Reassessment appends a reason, basis, new uncertainty,
previous uncertainty and current predecessor per claim. The first predecessor is
null: its previous grade is the actual base claim's legacy baseline, not a guessed
historical assessment. Exactly one new reassessment per claim per PR is allowed;
the current stored grade must equal the head result. `low` still requires that
claim's own independent inspected evidence. Connector uncertainty remains ordinary
relationship maintenance, outside claim assessment history.

Differing current member grades, or legacy merged supplied grades without a later
explicit reassessment, appear as disputed. No averaging or automatic uncertainty
change occurs. New exact claim reuse requires matching uncertainty as well as
statement, class and temporal scope. Otherwise preserve a separate claim; an
external comparison may group it. History remains retrievable after reassessment.
