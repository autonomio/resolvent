# Resolvent

**An empty, governed world-model template by Autonomio.**

Conduct research in Claude, or capture an existing conversation. One skill turns
that work into a contribution PR. Your repository agents admit and review claims;
regular maintenance improves connections across the accumulated model.

A claim's semantic core is **a short self-contained statement, categorical
uncertainty, and an evidence record**. IDs, class and lifecycle are bookkeeping.
This template contains **no world-model claims or inherited research data**.

## Start a world model

1. Use **Use this template → Create a new repository**. Choose its owner and
   visibility. There are no organization names, paths, or secrets to replace.
2. Upload [`dist/resolvent.zip`](dist/resolvent.zip) in Claude's **Customize →
   Skills**, and enable it. Authorize a **write-capable GitHub connection** for
   the new repository in Claude. No terminal, local clone, Docker, or desktop
   extension is required on a researcher's computer.
3. In your chat, name the target repository and ask:

   > Use Resolvent with OWNER/REPOSITORY. Research [my question] and contribute the findings.

For work already in the chat:

> Use Resolvent with OWNER/REPOSITORY. Capture the useful findings from this conversation. Do not do new research.

The researcher receives their normal answer and a PR receipt. A submission is not
an admitted claim until repository review and merge. The skill never merges.

**One-time connection requirement:** Claude's “Add from GitHub” file-sync feature
is not a PR-writing tool. A skill cannot grant itself write access. Use the
[no-local-install connection guide](docs/CLAUDE_SETUP.md). If writes are unavailable,
the skill returns the contribution file and explicitly says **not submitted**.
Do not interpret that fallback as automatic ingestion.

## Repository-side setup

Your existing trigger-based agents read [AGENTS.md](AGENTS.md) and
[their job instructions](docs/AGENT_JOBS.md). No agent provider, model key, or new
orchestration service is bundled. Give those agents access to each new repository.

GitHub copies files from a template, **not branch protections or app grants**.
Enable Actions and require the `World model integrity` check plus independent PR
review on the default branch. Dismiss stale approvals and require up-to-date
branches. Do not give researchers direct canonical-branch write access.

The included weekly/manual maintenance workflow opens a bounded workset PR once
claims exist. Your existing agent completes it. Empty models are a no-op. See
[operations](docs/OPERATIONS.md) for the single GitHub permission this workflow uses.

## What lives where

| Path | Purpose |
|---|---|
| `skills/resolvent/` | The one researcher-facing skill; distributable ZIP in `dist/`. |
| `input-artefacts/RUN-*.json` | Researcher contribution packages; immutable after merge. |
| `claims/`, `evidence/`, `sources/` | Canonical assertions, evidence records, and source anchors. |
| `graph/R-*.yaml` | Justified claim-to-claim connectors, stored once. |
| `briefs/` | Research briefs, results, and final closure manifests. |
| `questions/`, `maintenance/` | Open questions and auditable maintenance coverage. |
| `docs/contracts/`, `docs/schemas/` | Routed process contracts and executable schemas. |
| `scripts/` | Small repository-side admission and integrity tools. |

## Input routes

The skill selects **research, conversation, interview, source material,
simulation, intra-model reasoning, or liminal research** from the request.
Ordinary literature review uses research. Existing-chat capture uses conversation
and does **not** browse, rerun investigations, or fabricate a prospective brief.

Admission makes the immediate, justified connections. Maintenance discovers
broader connections—including new relationships between older claims—and revises
existing ones. More edges are not automatically better; an explicit no-connection
finding is valid. A connection has its own evidence, reason and uncertainty.

## For maintainers

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/compiler.py --require-closure
```

These commands run in CI or an agent workspace, not on researchers' computers.
See [ontology](docs/Ontology.md), [extraction notes](docs/EXTRACTION.md), and
[release/update instructions](docs/OPERATIONS.md).

Resolvent is an access-controlled Autonomio project. No public open-source license
is assigned by this bootstrap. Decide wider redistribution terms before publishing.
