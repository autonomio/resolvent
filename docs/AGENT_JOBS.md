# Jobs for the existing repository agents

## Admission

Read the incoming contribution and selected route contract. A red `World model
integrity` gate with “Awaiting admission agent” is expected until closure exists.

Inspect the cited evidence (within granted access), its anchors, independence,
dates and scope. Correct the handoff on the PR branch where necessary. If a source
cannot be verified, preserve that limitation and adjust uncertainty or defer/reject
the claim; do not mark it inspected. The raw contribution becomes immutable on merge.

Resolve obvious duplicates and identities. Add immediately justified connectors.
Consider at least exact/near statement matches and relevant existing claims using
the available repository search; do not demand an exhaustive world scan at admission.
A first claim in an empty model can validly have no connector. Record material
outstanding work for maintenance. No claim is admitted merely because it parses.

Create `.resolvent/decisions.json` in the agent workspace (not a canonical artifact):

```json
{
  "claims": {
    "c1": {"action": "accept", "reason": "Evidence supports the scoped claim; uncertainty reviewed."}
  },
  "connection_review": {
    "c1": {
      "considered_claim_ids": [],
      "outcome": "no_justified_connection",
      "reason": "The model is empty; there is no older claim to connect yet."
    }
  },
  "follow_up_gaps": []
}
```

Actions are `accept`, `merge` (also supply `target: C-...`), `reject`, or `defer`.
Every candidate needs a reason. Every accepted/merged candidate needs a connection
assessment: `linked`, `no_justified_connection`, or `deferred`; deferred discovery
also belongs in `follow_up_gaps`. Use actual findings, not the example's rationale.
For a zero-claim package use empty claims/connection_review maps and preserve the
package's explanation. Do not create artificial assertions to make a run nonempty.

Run, in order:

```sh
python scripts/world_control.py input-artefacts/RUN-UUID.json --decisions .resolvent/decisions.json
python scripts/world_control.py input-artefacts/RUN-UUID.json --decisions .resolvent/decisions.json --apply
python scripts/compiler.py --require-closure
```

The first command is a dry run. The tool validates the whole planned state before
writing, maintains evidence backlinks, resolves exact duplicates of the same class,
archives research phases and generates a closure matching the actual delta. It
does not assess truth or approve the PR. Merge into an existing claim adds evidence
without automatically changing that claim's class or uncertainty.

Commit all materialized files on the contribution PR. A substantive correction
invalidates prior approval and requires independent re-review. Corrections after
merge are new contributions; do not rewrite the original provenance.

## Independent review

Review evidence quality, completeness, atomicity, material scope, class, uncertainty,
source independence, immediate connectors, closure dispositions, and outstanding
discovery. Check the underlying sources rather than merely trusting a prior agent's
summary. Uncertainty can remain unresolved; known structural errors cannot.

Submit a real GitHub review. Leave actionable comments or request changes. Never
claim a review happened without a submitted review. The reviewer must not approve
its own substantive edits. Governance changes require a human maintainer.

The deterministic gate uses base-branch rules. It verifies schemas, references,
bidirectional evidence links, dependency/derivation cycles, research outcomes,
route constraints, closure coverage and immutability. It does not establish truth.

## Maintenance

A weekly/manual workflow opens one pending `maintenance/M-*.yaml` workset PR.
A workset combines never-reviewed claims with a rotating sample of the whole model.
Empty repositories do not open maintenance PRs. The run is bounded, not exhaustive.

Read the workset and the `maintenance` contract. Search outside existing graph
neighbours. Look for old-to-new **and old-to-old** relationships revealed by new
information; reassess older connectors, aliases, contradictions and evidence
independence. Preserve disagreements. Do not change uncertainty just because a
claim became more connected. Do not create cyclic evidential self-validation.

Make necessary canonical edits on the workset PR. Fill `reviewed_claim_ids`,
`findings`, `deferred`, and exact `touched_files`. Set `status: completed` only when
the recorded work is complete; explicitly defer anything not assessed. A no-change
run needs `no_change_reason`. Run the compiler and request independent review.

`python scripts/gap_finder.py --write` prepares a workset for a manual agent run too.
It is a candidate selector, not a relationship-inference algorithm.

## Governance

A governance PR changes the system, not research data. Keep canonical model changes
out of that PR. Assess plugin compatibility for every system/package change and
record the affected behavior or evidenced reason that no plugin update is needed.
Follow `docs/PLUGIN_RELEASE.md`, run the relevant tests, and regenerate the shared
skill and both host distributions after plugin changes. Update the bundled
protocol/version when changing the contribution schema.
Coordinate deployment to existing world models explicitly; GitHub templates do not
push future changes to repositories created from them.
