# Contribution protocol 1.0

Normalized input: `input-artefacts/RUN-<32 lowercase hexadecimal UUID>.json`.
The authoritative machine schema is `docs/schemas/submission.schema.json` in the
selected repository; a compatible copy is bundled beside this reference.
The run JSON is the source package. Complete the same contribution's PR-side
admission under `ADMISSION.md`, producing the canonical YAML and required
brief/result/closure artifacts. A proposal-only PR is unfinished authoring work
when the invoking agent can perform that approved job.

Required fields: schema_version="1.0", id, input_method, created_at (ISO datetime
with timezone), researcher, title, scope, origin, parent_run_id (null for first run),
brief, result, sources, evidence, claims, connectors, questions, handoff,
method_metadata. `researcher` is an attributed name/handle from known context;
do not invent a GitHub identity. Ask only when attribution is genuinely unavailable.

`origin`: mode live/retrospective; coverage complete/partial/not_applicable; limitations list.
`brief`: null outside prospective research, otherwise question, assumption_to_test,
evidence_requirements, questions, acceptance_criteria [{id, criterion}],
created_before_research=true.
`result`: summary, acceptance_outcomes [{criterion_id, result: pass/fail/inconclusive,
notes}], limitations, artifacts [{name, content}] (an empty artifacts list is valid).
`sources`: [{id, kind: publication/web/conversation/interview/simulation/model/reasoning,
title, uri: string/null, date: string/null, locator, excerpt, access: inspected/not_retrieved}].
`evidence`: [{id, kind: external/statement/simulation/derivation/assumption, summary,
source_ids, independent: boolean, limitations, premise_claim_ids}].
`claims`: [{id, class, statement, uncertainty: low/medium/high, evidence_ids}].
`connectors`: [{id, from, to, type: dependency/coupling, spec, reason, uncertainty,
evidence_ids}]. Include justified immediate connections after a bounded assessment
of candidate claims and the relevant existing model; no fixed edge count is required.
`questions`: [{id, question, claim_ids}].
`handoff`: summary, no_claims_reason: string/null, suggested_follow_up: string list.
`method_metadata`: route-specific fields from ROUTES.md. Keep
`schema_version="1.0"` and every ordinary route field. Run the authoritative
submission and canonical validators before publication. The plugin does not
install or weaken repository governance.

Classes: observed_fact, derived_inference, assumption, hypothesis, forecast,
scenario_variable, decision. Low uncertainty requires independent inspected
external evidence. This mechanical floor does not prove source quality; independent
repository review remains mandatory. Every claim references evidence in this package;
every evidence record references a source in this package. Claims referenced as joint
premises may be local candidate IDs or existing canonical C-IDs.

Use the JSON example in `assets/conversation-example.json` for field structure,
replacing every illustrative value with actual selected material. It is a synthetic
example, never a seed claim to submit. Do not submit placeholder evidence.

File size limit: 2 MiB. Keep excerpts focused; store links/anchors rather than entire
papers or chat histories. Split material at meaningful boundaries when necessary.
After input preparation, act as the repository's PR-side admission worker under the
approved contracts. Generate the closure through the approved tool from actual
materialized changes; never fabricate a closure or imply independent approval.
An "admission agent" is a role, not evidence that an external worker will appear.

## Submission, retry and revision identity

Complete materialization under `ADMISSION.md` and follow the PR under
`PR_FOLLOWUP.md`; opening it does not complete the workflow. Keep the original run
ID, target, branch, PR number, submitted content digest, head revision and base revision available
through the active task. Read back the remote file and PR before reporting delivery.
The originating task retains the selected research context and all authoring duties.
For an authorized full task under `TARGET.md`, continue through external independent
review, current CI and the guarded merge in `MERGE.md`; submission or readiness is
not completion. Preserve/resume that same task under `CONTINUATION.md` when supported.

**Transport retry:** A timeout, connection error or uncertain API response is not
evidence that a write failed. First find and verify the existing branch, file and PR.
Retry only the missing operation, using the same run ID and identical JSON bytes.
Reuse the saved package; do not regenerate research as a transport repair.
A substantive continuation uses a new run linked through `parent_run_id`.
If the remote file differs, stop the blind retry and reconcile the actual state;
never overwrite an unfamiliar revision or open a duplicate PR to escape an error.

**Review revision:** A substantive correction changes the package and is not an
identical-byte retry. Follow the selected repository's explicit amendment rules. If
they permit updates to an open contribution, revise that run on its existing branch,
rebuild its correlated canonical and closure artifacts, preserve provenance, and
record the new content digest/head. The current admission tool will not regenerate
an existing closure simply because it is run again; use the safe reconstruction
procedure in `ADMISSION.md`. If the rules require immutable submissions, create the
prescribed successor run linked through
`parent_run_id` and reconcile the original PR according to that contract. Do not
invent an amendment convention when the contract is missing or ambiguous; report
that specific blocker. Do not modify the submitted `created_at`, fabricate a new
prospective brief, or add fields rejected by the authoritative schema to disguise a
revision as the original submission.

Correct schema defects, unresolved references, evidence/provenance gaps, uncertainty,
scope or claims only when the available material justifies the change. Preserve the
selected input route's limits: conversation capture cannot conduct new topic
research to satisfy a reviewer. Changes requiring new research need an authorized
research route with its own prospective brief and appropriate linked run.

Every new head invalidates previous follow-up conclusions. Revalidate the package
and restart freshness checks, required reviews and admission assessment on the new
head. Authoring includes the normalized input, its justified canonical additions or
updates, and required brief/result/closure records. Preserve unrelated model data
and collaborator changes; never rewrite merged provenance. Do not change governance,
schemas, workflows, branch rules or the skill as part of contribution follow-up.
External independent reviewers still own their judgments. The originating task
implements corrections using its research context, then repeats checks/review before
the delegated merge. The legacy proposal-repair worker is outside this ownership
model; do not delegate any authoring or correlated revision work to a contextless
model. Merged provenance remains immutable; record merge evidence with the task's
receipt rather than modifying its admitted closure.
