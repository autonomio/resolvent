# Contribution protocol 1.0

One JSON file: `input-artefacts/RUN-<32 lowercase hexadecimal UUID>.json`.
The authoritative machine schema is `docs/schemas/submission.schema.json` in the
selected repository; a compatible copy is bundled beside this reference.

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
evidence_ids}]. Usually empty on desktop; only include justified immediate connections.
`questions`: [{id, question, claim_ids}].
`handoff`: summary, no_claims_reason: string/null, suggested_follow_up: string list.
`method_metadata`: route-specific fields from ROUTES.md.

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
A PR containing only this proposal will await the admission agent; that is normal.
The researcher does not generate a final closure claiming canonical changes occurred.
