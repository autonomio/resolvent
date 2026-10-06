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
PR. Meaning-changing replacement gets a new ID; retire, do not delete, old records.

## Research artifacts

During research the contribution contains a prospective brief, result and proposed
handoff. On admission, archive the brief to `briefs/open/done/BR-*.yaml`, the result
to `briefs/ready/BR-*.yaml`, and generate `briefs/closed/BC-*.yaml` from the actual
changes. These are different artifacts, not duplicate mutable model truth.

For retrospective chat capture, `brief` is null: never pretend criteria existed
before the work. All routes still receive a closure manifest after admission.
