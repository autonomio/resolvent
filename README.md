# Resolvent

**A world-model repository and a generic research plugin by [Autonomio](https://autonom.io).**

Resolvent helps you research and refine questions in chat, read your world model
for context or answers, and explicitly add selected findings, questions or discussion.
One plugin serves compatible GitHub repositories through your authorized connection.
Invoking it alone authorizes neither model reads nor writes. Contributions preserve
evidence and uncertainty through admission, independent review, CI and authorized merge.

A claim's semantic core is a short self-contained statement, categorical uncertainty
and an evidence record. IDs, class and lifecycle are bookkeeping. This template
contains no world-model claims or inherited research data.

## Start a world model

1. Create a repository from this template. Choose its owner and visibility.
2. Install **Resolvent** from the ChatGPT or Claude directory once published.
   Use the authorized GitHub connection available in the invoking chat.
3. Select your destination together with your question:

   > @resolvent OWNER/REPOSITORY Research [my question] and update the world model.

For work already in the chat:

> @resolvent OWNER/REPOSITORY Capture the useful findings from this conversation. Do not do new research.

Name a repository or organization when model access is needed. Resolvent verifies
the destination, asks if ambiguous, and retains it in the current chat. An optional
native project instruction can reuse the selection across chats. Chat-only research
and reformulation need no destination. [Examples and setup](docs/PLUGIN_README.md).
A full contribution
finishes with verified merge under the user's actual authorization and repository
rules; explicit preflight, submit-only, review-only and no-merge limits prevail.

## Plugin releases and distributions

Plugin **1.2.0** adds a fixed client and separately versioned live workflow references,
including explicit read/write intent, distillation and integrated question reformulation.
The world-model protocol remains 1.1 with legacy 1.0 compatibility.
Its developer is Autonomio and its website is https://autonom.io. After a reviewed
main-branch change passes validation, CI publishes versioned GitHub assets and the
standalone `plugin-release` branch. Public directory setup is a separate first step.

- [Latest published packages](https://github.com/autonomio/resolvent/releases/latest)
- [ChatGPT plugin ZIP](dist/chatgpt/resolvent-1.2.0.zip)
- [Claude plugin ZIP](dist/claude/resolvent-1.2.0.zip)
- [Plugin release and compatibility instructions](docs/PLUGIN_RELEASE.md)

Both ZIPs contain identical code, skills, assets and synchronized host manifests.
Local catalogs are in `.agents/plugins/marketplace.json` and
`.claude-plugin/marketplace.json`; their source is the generated standalone plugin
at `dist/plugin/resolvent/`. Claude's public directory can scan the release branch
and automatically publish passing versions once enabled. ChatGPT workspace admins
can import the GitHub marketplace once and automatically sync `plugin-release`;
[setup instructions](docs/PLUGIN_RELEASE.md#public-directory-setup) explain the scope.
Public ChatGPT directory skill changes require ZIP upload, review and publication.
Data-only updates create no plugin release.
The client reads verified operational references from the separate `workflow-release`
branch. A routine workflow update changes that channel without replacing the installed
ZIP. Source content is pinned for each operation; fixed permission and destination
rules remain installed. This is an application design requiring host verification,
not a claim that the public ChatGPT directory polls arbitrary websites for packages.
For direct Claude marketplace distribution, the installation line is:

```text
/plugin install resolvent --marketplace autonomio/resolvent
```

The standalone `dist/resolvent.zip` skill remains an optional compatibility artifact.
A skill/plugin cannot grant GitHub permissions. File-sync-only access cannot create
contribution PRs. If needed operations are unavailable, Resolvent provides a truthful
incomplete receipt; installation alone is not evidence of research, admission or merge.

## Repository setup

Existing repository agents read [AGENTS.md](AGENTS.md) and
[their job instructions](docs/AGENT_JOBS.md). Give independent review agents access.
The originating chat owns its selected contribution's authoring and corrections;
external review remains independent. No agent provider, model key or new service
is required by the plugin.

Template copies do not inherit branch protections or app grants. Enable Actions,
require `World model integrity` and `Tests and skill package`, independent review,
stale-approval dismissal, resolved conversations and up-to-date branches. See
[operations](docs/OPERATIONS.md) for setup and weekly/manual maintenance.

## What lives where

| Path | Purpose |
|---|---|
| `skills/resolvent/` | Shared generic researcher-facing workflow and references. |
| `workflows/resolvent/` | Separately versioned live operational guidance. |
| `plugin.json`, `.codex-plugin/`, `.claude-plugin/` | Portable and host-compatible plugin metadata. |
| `dist/chatgpt/`, `dist/claude/`, `dist/plugin/` | Reproducible plugin distributions and local catalog source. |
| `input-artefacts/RUN-*.json` | Immutable retained research/capture contributions. |
| `claims/`, `evidence/`, `sources/` | Canonical assertions, evidence and source anchors. |
| `graph/R-*.yaml` | Justified claim-to-claim connectors, stored once. |
| `briefs/`, `questions/`, `maintenance/` | Research execution, closure, open questions and maintenance. |
| `docs/contracts/`, `docs/schemas/`, `scripts/` | Governed processes, executable schemas and deterministic tools. |

The skill routes research, conversation, interview, source material, simulation,
intra-model reasoning and liminal research. Existing-chat capture does no new topic
research. Admission creates justified immediate connections; maintenance discovers
broader old-to-new and old-to-old relationships. A no-connection finding is valid.

An optional Portal explores the repository through search and visualization. It is
separate from this generic plugin and is not required for contributions.

## Maintainers

Follow the plugin compatibility rule in [AGENTS.md](AGENTS.md) for every system/package
change. Assess whether installed plugin behavior needs updating; ordinary model-data
updates alone do not require a plugin release. Build and check both distributions
as documented in [plugin releases](docs/PLUGIN_RELEASE.md).

Resolvent software and the plugin use the [MIT License](LICENSE). Organization
world-model data and third-party source material are excluded and retain their
rights holders' terms. Forking or updating the software grants no rights to that data.
