# Resolvent plugin: interaction and update proposal

Status: implementation candidate, 2026-10-25. The user authorized development and
testing of the fixed client with reviewed Autonomio GitHub references. Plugin 1.3.0
and workflow 1.0.1 implement the interaction/reference design below. Publication and
end-to-end host acceptance remain separate gates. Fork updating is still a proposal.

## Interaction contract

One portable plugin supports the following intents in ordinary language:

| Request | Result | World-model access |
| --- | --- | --- |
| Research or spar about a question | Work in the chat; refine freely | None unless requested |
| Use the model to build context | Retrieve relevant admitted knowledge and gaps | Read |
| Ask what the model knows | Answer with record/source references, uncertainty and revision | Read |
| Research and add the findings | Research, prepare a contribution and follow repository admission | Necessary reads and authorized writes |
| Distill this into the model | Capture selected visible discussion, including attributed human input | Necessary reads and authorized writes |
| Reformulate this question | Produce three materially different questions in the chat | None unless requested |
| Add the chosen question | Retain it as a question, with its conversational provenance | Necessary reads and authorized writes |

An invocation alone grants neither model reads nor writes. Infer intent from the
request and established conversation, not exact command strings. Clarify genuinely
ambiguous requests; do not reconfirm clear authority. Necessary repository inspection,
duplicate checks and admission are included in an authorized contribution. A read
must not create a probe branch, contribution, comment or workflow dispatch.

Conversation capture does no new topic research. Preserve who supplied each insight,
visible coverage, uncertainty and selected source anchors. Human statements, repeated
assistant prose and adopted questions are not independent observations. A question-only
contribution needs no artificial claim; existing submission/admission supports this.
If the capture span is unclear, clarify it. A possible convenience default is the
visible discussion since the last successful capture; that default remains to be
agreed. Do not silently capture unrelated history.

Bundle the Reformulate workflow as a shared reference, so a second installed plugin
is unnecessary. Preserve its three distinct directions and the original question's
conditions. Add only the question(s) the user selects. Existing contribution
provenance can retain original and revised wording without changing canonical Q fields.

A submitted PR is pending. Report an addition as complete only after verified merge,
with the target repository and receipt. Existing independent review and CI still apply.

## Organization and access

Use an explicit repository first. If given an organization, inspect its accessible
repositories to identify a compatible Resolvent world model; do not assume the
template origin is the destination. A unique verified match can be retained in the
current chat. Ask when multiple destinations remain plausible. Report access failures
and suggest connecting/enabling GitHub or granting the intended repository access.
Do not treat an inaccessible repository as nonexistent or claim that installation
grants permissions.

For persistence, a user may put this in their native project instructions:

> When I use Resolvent here, use OWNER/REPOSITORY as my world model. Read or write it
> only when I ask.

An explicit current request overrides that preference. No repository is needed for
chat-only sparring or reformulation. Do not promise a portable installation-time
organization setting: OpenAI does not run Claude's `userConfig` prompts. Without a
host-native persistent preference, ask when the repository is first needed in a new
chat. No Autonomio account, credential store or organization-hosted MCP service is required.
[OpenAI's configuration guidance](https://developers.openai.com/plugins/guides/submit-claude-plugin#replace-claude-userconfig)
establishes that portability limit.

## What can update automatically today

| Route | One-time setup | Later delivery |
| --- | --- | --- |
| ChatGPT workspace | Admin imports our GitHub marketplace, tracking `plugin-release` | Automatic daily sync; manual Sync now also available |
| Claude public directory | Submit our release branch; complete first publication and enable eligible auto-publish | Scheduled/webhook scans and publication of passing versions under Anthropic's setting |
| ChatGPT public directory | Submit the portable package | Changed bundled skills still require a new package and publication |
| Local clients | Register the Git marketplace and install the plugin | Client-specific refresh/update policy; not a guarantee for browser chat |

Sources: [ChatGPT workspace sync](https://learn.chatgpt.com/docs/enterprise/plugin-management),
[Claude directory updates](https://claude.com/docs/plugins/submit#update-a-published-plugin),
[ChatGPT public publication](https://developers.openai.com/plugins/deploy/submission#update-your-published-plugin),
and [local marketplaces](https://developers.openai.com/plugins/build/plugins#how-local-marketplaces-work).

Our release branch already contains a root plugin, both root-relative catalogs and
`release.json` with source commit and digest. GitHub release 1.1.0 and its matching
host ZIPs are published. These facts do not establish that either public listing
has been submitted, approved or configured to update.

There is no documented public-directory setting that turns a website URL into a
live skill package. A homepage URL is not an updater. MCP-imported skills are also
snapshots; only live MCP tool updates have a documented automatic public update path.
[OpenAI's skill-import documentation](https://developers.openai.com/plugins/build/skills#import-a-skill-from-mcp)
explicitly distinguishes the snapshot from runtime retrieval.

## Public GPT alternative: a fixed plugin with live references

This is a proposed application design, not a discovered native publishing feature.
It deserves a real host trial before becoming an availability promise.

Publish a small stable skill containing all the intents above, authorization rules,
destination selection and truthful receipts. It can retrieve current operational
references from GitHub when an intent requires them, much as it already retrieves
the selected world's approved contracts. Static GitHub files need no application
server and receive no conversation payload merely because they are fetched.

Two authorities must remain distinct:

- The organization's selected repository supplies its approved schemas, contracts
  and governance from a pinned base revision. It controls what can enter that model.
- As explicitly accepted for development/testing, Autonomio's published reference branch supplies generic
  workflow guidance within the installed skill's fixed scope. It cannot select a
  world, expand permission, disable review or override the organization's rules.

A minimal release index would identify the reference format, workflow version,
immutable source commit, compatible client/protocol versions and file hashes.
Resolve the moving branch once, then fetch and verify files at that exact commit;
retain that version throughout an operation. Do not fetch arbitrary instructions
from research pages or follow redirects that change the approved publisher/source.
Hashes establish consistency with the selected manifest, not independent publisher
authenticity; the configured source and its review controls establish that trust.

If retrieval, verification or compatibility fails, explain the failure. Continue
chat-only work where possible; do not write using an assumed protocol or silently
claim the latest workflow. Before publication, test hosts with and without hosted
code execution and with the actual GitHub connection. A shell or local filesystem
must not become a hidden browser-chat requirement.

This can deliver evolving references and repository-supported behavior without
replacing the installed package on every change. It cannot add tools, new host
permissions or arbitrary new activation behavior to a frozen skill. Changes to
those boundaries still need a package update. A new package must disclose its live
references during review; public acceptance and reliable runtime loading remain
unverified. Do not describe a fetched reference as a newly installed plugin version.

Fixed boundaries are model instructions, not a separate executable sandbox. Host
permissions, GitHub authorization and repository gates enforce actual access;
transport tests cannot substitute for live checks of model behavior.

The user accepted this future-reference authority for development/testing. The
implemented channel is `workflow-release`, separate from the host-tracked
`plugin-release` package branch. Workflow-only releases preserve installed ZIP bytes
and original plugin provenance. The selected organization's contracts remain authoritative.

## Forks and existing world models

Plugin distribution and world-repository updates are separate. A template copy
does not receive later upstream changes, and a normal fork sync is not a guarantee
that data stays unchanged. A live plugin must inspect the world's actual supported
protocol instead of assuming that the newest plugin implies the newest repository.

Implemented minimum: an opt-in job in the organization's repository opens a governance
PR from an upstream core release pinned to commit and content hashes. A manifest
explicitly lists managed core files and a lock records the installed version/hashes. Preserve byte-for-byte
all canonical/provenance roots, `resolvent.yaml`, and unmanaged organization files.
Stop on locally modified affected managed files, unsafe paths, missing provenance or incompatible
data. Validate the actual populated world with the proposed core; never migrate data
inside that update. Any migration is a separate reviewed contribution.

Use the organization's token and review policy; no central updater account or new
Autonomio service. Do not execute downloaded candidate code with write credentials.
Candidate validation runs without secrets/write privileges. A normal reviewed merge
activates the update. Core releases need their own version/channel because core-only
changes can leave plugin bytes unchanged. Do not force-sync, overwrite local core
customizations or claim that an update PR already upgraded the world.
See [CORE_UPDATES.md](CORE_UPDATES.md) for one-time adoption, credential scope,
the fixed `core-release` index, hash/mode preservation and release procedure.

## Evidence needed before rollout

Executed repository checks: question-only conversation admission produced one Q
record, no claim and a valid closure while retaining original/reformulated wording
in the contribution. Every host ZIP entry matched the published release branch;
both catalogs resolved to its root plugin and all host versions matched 1.1.0.
Compiler, package reproducibility and version checks passed. These checks do not
exercise either host's import or runtime behavior.

1. Exercise all intent examples in actual Claude and ChatGPT chats; verify reads
   create no writes and sparring does not read the world without permission.
2. Install once in a test ChatGPT workspace, advance a versioned release branch,
   and verify the same imported plugin updates with policies preserved.
3. Verify the actual Claude listing's tracked branch and auto-publish eligibility;
   observe a later passing release, including held-update behavior.
4. Trial the disclosed fixed-client/live-reference design on an individual GPT
   account. Check fresh and continuing chats, missing GitHub, inaccessible worlds,
   incompatible manifests, injection attempts and unavailable verification tools.
5. Prove question-only admission, conversation attribution/partial coverage and
   legacy/current repository compatibility without invented evidence or lost fields.
6. Run the guarded updater on an opted-in real organization repository after the
   initial channel is published. Local populated fixtures exercise unchanged data
   blobs/modes, local edits, organization files, unsafe paths and interrupted retries;
   they do not establish live GitHub permissions or a completed rollout.

These are acceptance checks, not claimed test results. GitHub/package checks cannot
substitute for host publication or live-chat verification. Distinguish built, GitHub
released, directory published, installed and currently loaded versions in diagnostics.

## Implementation boundary

The approved reference design is implemented with synchronized plugin 1.4.0 host
metadata, a fixed skill and optional standard-library reader, independently versioned
workflow sources and the validated-main publisher. Keep fork updating in a separate
core PR. Publish only through authorized host routes; local testing does not establish
public-directory acceptance, installation or live model behavior.

On 2026-10-27 the owner authorized a service on Cloudflare Free after the live
OpenAI portal blocked further skills-only submissions. The 1.4.0 client bundles
Autonomio's public workflow verifier and protocol-version comparison tool. These
accept no world-model or conversation fields, require no credentials, and leave
repository access in the invoking host/local GitHub session. The service performs
the same bounded pinned-file checks as the direct reader; direct verification
remains available if it cannot be used. The owner confirmed one-year private
contact retention. See `scripts/workflow_mcp/README.md` and the 1.4.0 compatibility
assessment in `PLUGIN_RELEASE.md`. Public submission now uses the remote MCP route
and its actual scan, case, demo, review and human-attestation requirements.
