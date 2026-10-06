# Ingestion routing

All routes produce one normalized contribution and use GitHub-side admission.
Read the actual contract path from the selected repository's contract registry.

| Input | Route | Required route metadata / guardrail |
|---|---|---|
| New investigation/literature review | research | Prospective brief; result with an outcome for every acceptance criterion. |
| Existing current chat | conversation | origin.mode=retrospective, coverage complete/partial, new_research_performed=false; no new topic research; no fabricated brief. |
| Interview material | interview | participants and interview_date; anchored quotes/notes; distinguish statement from inference. |
| Supplied source material | source_material | Evidence quality, source independence, date and scoped referents. |
| Simulation outputs | simulation | spec_id, spec_version, run_id, parameters; preserve assumptions; outputs alone are not independent confirmation. |
| Existing canonical claims | intra_model | source_claim_ids, source_commit; preserve premise IDs; no circular self-validation or automatic confidence improvement. |
| Explicit liminal ideation | liminal_research | topic, perspective, stage_outputs, external_search_performed=false, world_model_read_during_generation=false; assumption/high uncertainty only. |

**Capture an existing chat is not an instruction to research its topic again.**
Already visible citations may be preserved, but an inaccessible/uninspected cited
source must remain not_retrieved and cannot be labeled independent confirmation.
When the existing chat was a literature review, capture its available result as
conversation input rather than inventing a brief dated before it happened.

## Research discipline

Establish the question and criteria before investigating. Seek primary evidence and
material disconfirmation. Distinguish observations, inferences, assumptions,
hypotheses and forecasts. Preserve mechanisms, timescales, populations, limitations,
conflicting findings, evidence needs and unanswered questions. Do not manufacture
triangulation by counting repeated reports of the same underlying source.

## Liminal directive

Fetch `docs/directives/liminal_research.md` before generation and follow its stages.
Repository admission happens afterward. Reading governance before generation is not
a license to query the model during the ideation stages. Public analytical stage
summaries suffice; never serialize private chain-of-thought.
