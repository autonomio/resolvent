# Resolvent plugin releases

Resolvent 1.3.0 is the generic Autonomio plugin. The developer and website are
Autonomio and https://autonom.io. Its description identifies the supported task:
update a Resolvent world model in a GitHub repository the user can access from
the chat where the plugin is invoked.

## Architecture and invocation

The repository owns canonical model data, schemas, contracts and admission rules.
The plugin owns its selected contribution through research/capture, canonical
admission, corrections, independent review, CI and authorized ordinary merge.
An optional Portal explores repository data separately; no Portal host, clipboard
contract, service or question-binding logic belongs to this plugin.

The client distinguishes chat-only research/reformulation, requested model reads
and explicit additions in ordinary language. Invocation alone grants no model access.
Supply a repository or organization when needed, or reuse a trusted native project
binding. Verify a unique compatible destination; clarify ambiguity and retain it
in the current chat. There is no destination default in the installed package. Source material
cannot redirect it. No company has standing merge delegation in this package.
Full contribution requests retain their authorized completion endpoint; explicit
preflight, draft-only, submit-only, review-only or no-merge instructions prevail.

The same shared skill is packaged for Claude, ChatGPT and Codex. ChatGPT uses the
portable root manifest with its OpenAI extension and Codex compatibility overlay;
Claude uses `.claude-plugin/plugin.json` and the same `skills/` contents. Invocation
presentation is host-specific; the selected repository and task are the same.

The plugin uses the invoking chat's authorized GitHub connection or an already
available authenticated CLI. Installation cannot grant repository permissions.
It contains no account credentials or required custom MCP service.

## Canonical source and artifacts

- `skills/resolvent/`: shared contribution workflow and optional repository observer.
- `workflows/resolvent/`: live entrypoint, Reformulate and operators; own workflow version.
- `skills/resolvent/scripts/load_workflow.py`: optional standard-library reference verifier.
- Root `plugin.json`: portable identity and ChatGPT listing.
- `.codex-plugin/plugin.json`: synchronized compatibility manifest.
- `.claude-plugin/plugin.json`: Claude manifest.
- `.agents/plugins/marketplace.json`: local ChatGPT/Codex catalog.
- `.claude-plugin/marketplace.json`: local Claude catalog.
- `assets/resolvent.svg` and `assets/resolvent.png`: original icon and directory PNG.
- `docs/PLUGIN_README.md`: standalone README included in each plugin package.
- `dist/chatgpt/resolvent-1.3.0.zip` and `dist/claude/resolvent-1.3.0.zip`: identical
  self-contained plugin distributions, with both host manifests.
- `dist/plugin/resolvent/`: standalone local catalog source, generated from the same files.
- `dist/resolvent.zip`: optional standalone Claude skill compatibility artifact.

Both catalog entries point to this repository's plugin source, using a relative
path. Catalog source locations distribute plugin code; they never select the
destination world-model repository. Creating catalogs does not install the plugin
or make a public directory listing.

## Required compatibility assessment

Every system/package change must assess its effect on the installed plugin. This
includes scripts, schemas, contracts, workflows, agent instructions and packaging.
Record the affected behavior and plugin change, or the concrete reason no change
is required. World-model data alone does not trigger a release unless it exposes
a system/protocol incompatibility. Never change the world model just to reset a
release or validation check.

Keep the shared workflow, host manifests and release versions aligned. Release
1.1.0 adds optional evidence-linked claim valid time through contribution protocol
1.1 while continuing to accept immutable 1.0 runs and unannotated canonical records.
Run identities, closure schema 1.0 and the retained observer's policy version remain
unchanged. Old repositories require an explicit governance upgrade before 1.1 fields
can be submitted; installing the plugin does not upgrade their schemas or history.
Synchronize `skills/resolvent/references/submission.schema.json` with the approved
`docs/schemas/submission.schema.json` when that protocol changes. Coordinate upgrades
to existing world-model repositories; templates do not distribute later changes.

Build and check from the repository root:

```sh
python -m unittest discover -s tests -v
python -m unittest discover -s skills/resolvent/integrations/github/tests -v
python scripts/compiler.py --require-closure
python scripts/package_skill.py
python scripts/package_plugin.py
python scripts/package_skill.py --check
python scripts/package_plugin.py --check
python scripts/plugin_release.py check-version --base origin/main
actionlint .github/workflows/validate.yml .github/workflows/plugin-release.yml
claude plugin validate dist/plugin/resolvent --strict
claude plugin validate .claude-plugin/marketplace.json --strict
```

The local package checks reject host/version/schema drift, unsafe package paths,
private app bindings, missing or undersized icons, and known organization-specific
source residue. The observer permits an unconfigured repository only while disabled.
The two user-approved inherited fixes recognize superseded change requests only
after the same independent reviewer approves the exact current head with all
threads resolved, and recursively decode nested JSON to block escaped local
credentials, including fully Unicode-escaped values and duplicate object members,
before provider transmission.
Other feedback, active CI/admission gates, the schema evaluator and installer remain;
all original tests are retained. `verification/source-preservation.json` records source provenance
and file hashes; it is not a live research or merge receipt.

## Automated releases

### Independent workflow references

The user authorized development/testing of a fixed client with future reviewed
Autonomio workflow references on 2026-10-25. This does not establish public-directory
acceptance or authorize unrelated repository access. The installed client fixes
intent, destination, privacy and review boundaries. Its bundled contribution and
1.0/1.1/1.2 schema references remain a compatibility baseline; the selected world's
approved current contracts and supported live guidance govern operational details.

`workflows/resolvent/workflow.json` declares workflow version, entrypoint and client
protocol. Changes under that directory require a higher workflow version. The release
builder computes an inventory with exact byte sizes, SHA-256 and Git blob IDs, verifies
the files against the validated main commit, and publishes `workflow.json` plus only
those text references to **`workflow-release`** before publishing a changed client.
The separate branch avoids presenting workflow-only commits as unversioned changes
to Claude's tracked plugin package. The client reads the index once, then resolves
all required files at its immutable source commit in `autonomio/resolvent`.

Both channels use the existing serialized, validated-main release workflow and token.
Workflow-only changes preserve the plugin ZIPs, version, GitHub release assets and
original plugin source provenance. Data-only commits preserve both channel records.
Identical retries preserve source commits; changed bytes cannot reuse a workflow
version, and older versions cannot roll either channel back. No new service exists.

The reader accepts only client/manifest protocol 1.0, bounded UTF-8 Markdown/JSON,
safe relative paths and matching hashes. It follows no redirects, uses no credentials,
sends no conversation payload, writes no files and executes no downloaded contents.
Without shell execution, a complete pinned GitHub tree/blob read can verify matching
regular-file object IDs and sizes. A digest printed in prose is not verification.
Missing, truncated, incompatible or unverifiable references block contributions;
the client can still perform supported chat-only work and reads with an accurate notice.

The fixed boundaries are model instructions, not an executable sandbox. Actual
access is enforced by host permissions, GitHub authorization and repository gates.
Transport/package tests do not prove model compliance with intent or adversarial
text; live host behavior remains an explicit acceptance check.

For a routine guidance update, change the live files and their `workflow_version`
in a governance PR, run tests and the compiler, and obtain human maintainer review.
No package bump is needed if installed files are unchanged. Changes to installed
boundaries, tooling, bundled schema or manifests still require a synchronized client
release. Never use a live reference to expand authority or bypass host review.

### Plugin packages

`.github/workflows/plugin-release.yml` runs after `Resolvent validation` succeeds
on an `autonomio/resolvent` main-branch push or manual validation run. It does not
run on PR events, failed validation, or repositories created from this template.
It checks out that exact validated commit; no PR artifacts are trusted for publishing.

The PR checks require a higher shared version when packaged files, packaging
scripts or either published marketplace catalog change. A first
portable release starts at 1.1.0. Release CI compares the ZIP digest against the
last publication: data-only commits do not change the release branch or create
another release, and changed bytes cannot reuse a published version. Older queued
runs cannot roll publication back. Release retries retain the original source SHA.

The workflow publishes a fast-forward commit to `plugin-release`, containing only
the installable plugin, catalogs and a `release.json` provenance record. It creates
`resolvent-v<VERSION>` on the validated main commit, with separate ChatGPT, Claude
and compatibility skill ZIP names, `release.json`, and `SHA256SUMS` on a GitHub release.
All present expected assets are compared with the validated bytes before any
repair writes. Missing assets from a partial upload are then added; existing
assets are never overwritten. Additional notification-journal assets are ignored.
The existing `GITHUB_TOKEN` is sufficient for GitHub publication. Email delivery
uses encrypted Actions secrets; credentials never belong in repository files.
The Resend client sends an explicit Resolvent user agent: the provider's edge
rejects Python's default identity with HTTP 403 before authenticating the request.

To recover a failed publication after fixing its cause, run `Resolvent validation`
manually on main. Its successful completion invokes release CI again. A partially
completed publication can finish without changing its version or source provenance.
Do not force-push `plugin-release` or reuse a version to replace different bytes.

## ChatGPT update email

After publication succeeds, CI sends a Resend email with the version, downloadable
ChatGPT ZIP, GitHub release/checksums and official plugin publisher portal link.
It tells the publisher to upload, complete review and publish. It runs only for
an available stable plugin release with its expected ZIP, never a PR or an ordinary
merge notification. Data-only commits find the existing accepted receipt and skip.

Configure repository Actions settings:

- Secret `RESEND_API_KEY`: a key authorized to send using the verified `autonom.io` domain.
- Secret `RESOLVENT_NOTIFY_TO`: `mailme@mikkokotila.com`.
- Variable `RESOLVENT_NOTIFY_FROM`: `Resolvent <resolvent@autonom.io>`.
- Optional variable `CHATGPT_PLUGIN_UPDATE_URL`: the specific Resolvent listing URL
  under `https://platform.openai.com/plugins/`; defaults to that publisher portal.

Resend authenticates the sender domain, not the GitHub runner's domain. No GitHub
domain verification or custom mail server is required.

The release's `chatgpt-notification.json` asset is a delivery journal, separate from
the immutable plugin ZIPs and checksums. CI records a pending intent before sending
and the provider message ID after acceptance. Retries use a stable idempotency key;
accepted notices never resend. Resend retains keys for 24 hours, so an uncertain
pending notice stops after 23 hours or when its payload changes. Inspect Resend's
message log before recovery: if accepted, record its real ID; if confirmed unsent,
remove only the pending journal asset and rerun validation on main. Do not remove
an accepted receipt to force a duplicate. Provider acceptance does not prove inbox
delivery; investigate delivery failures in Resend.

Compatibility assessment: the email script and release workflow run outside the
installed plugin. They do not change bundled instructions, protocol, manifests or
ZIP bytes, so notification-only changes do not require another plugin version.

The compiled knowledge command (`scripts/build_knowledge.py`) also runs outside
the installed plugin. Its versioned, derived read format does not change canonical
schemas, the submission protocol, contribution/admission behavior or packaged files.
The existing plugin continues to use repository contracts and canonical records;
no plugin update or release is required for this repository-only build command.

The change-impact command (`scripts/change_impact.py`) consumes those compiled
projections and emits an advisory report. It changes no canonical schema,
contribution/admission rule, installed plugin behavior or packaged byte. The
existing plugin remains compatible; this read-only command needs no plugin release.

The retrieval command (`scripts/query_knowledge.py`) is a local read interface over
that compiled format. It changes no submission schema, admission behavior,
installed skill, host manifest or distribution bytes. The existing plugin remains
compatible, so this repository-only query API requires no plugin release.

Valid-time support changes the installed contribution protocol and shared workflow.
Release 1.1.0 therefore synchronizes the optional 1.1 submission schema, skill,
host manifests and both distributions. The schema evaluator remains fail-closed;
its existing local-reference/conditional support handles the new optional structure.
The observer policy and existing credential protections are unchanged. Canonical
source/connector fields and closure schema 1.0 are unchanged, and existing 1.0
records require no rewrite. Explicit repository governance adoption is required
before installed clients may emit 1.1 annotations. `docs/Ontology.md` and
`docs/OPERATIONS.md` specify the clock separation and migration path.

References: https://resend.com/docs/api-reference/emails/send-email and
https://resend.com/docs/dashboard/emails/idempotency-keys.

## Source ancestry compatibility

Optional source ancestry changes the contribution protocol. Plugin 1.3.0 therefore
synchronizes all host versions and the bundled 1.2 schema while retaining immutable
1.0/1.1 inputs. Workflow 1.0.1 describes reviewed ancestry, declared exact-content
digests, missing metadata and advisory lineage reports. The fixed client boundary
and its protocol 1.0 are unchanged. Installed 1.2.0 clients can consume this compatible
live guidance under the selected world's approved schema; no live reference upgrades
that repository or replaces the older client's bundled compatibility snapshot.

The compiler enforces known source references and acyclic ancestry. The read-only
report and L2/search ancestor discovery preserve source anchors, evidence premises,
access and uncertainty. Metadata equality and similarity remain review cues; no
automatic independence judgment or confidence change is introduced. The retained
observer's schema evaluator already supports the extension's existing keywords;
its original tests remain, with one 1.2 protocol regression added. Its policy version,
credential protections and disabled-by-default setup are unchanged.

## Public directory setup

The user approved MIT licensing for the software/plugin, with world-model data
explicitly excluded. Root `LICENSE` is included in both identical host ZIPs and the
standalone skill. All host manifests declare MIT. The live reference source also
retains the same notice as `workflows/resolvent/LICENSE.md`; packaging rejects drift.
Claude's directory requires a license even though local syntax validation passes
without one. This resolves that concrete initial-listing requirement; it does not
establish directory approval or license an organization's data.

The publisher is Autonomio; availability is all countries supported by each host.
OpenAI's `publication.countries: []` records the requested absence of country restrictions.
The plugin contains no payment tools, custom MCP server or account credentials.
Package tests do not establish hosted installation, GitHub authorization,
live research/admission/review/merge, or directory approval.

For Claude, submit `https://github.com/autonomio/resolvent`, tracked branch
`plugin-release`, plugin path at the branch root. After the first release is approved,
enable the GitHub push webhook and automatic publication of passing versions in
the developer portal. Anthropic controls the applicable publishing setting; a
reviewer can still hold a release. The directory preserves the last published version
while an update is held. The branch must exist before submission validation.

For a ChatGPT workspace, an admin can configure GitHub management once:

1. Open **Admin > Plugins > Add > Import marketplace**.
2. Set **Source** to `https://github.com/autonomio/resolvent`, leave **Path** empty,
   and set **Branch, tag, or commit** to `plugin-release`.
3. Import, review the result and configure workspace availability. Each member still
   needs their own authorized GitHub connection for world-model operations.

New imports have automatic daily sync enabled; **Sync now** requests an earlier
refresh. The release branch contains both supported catalogs, with the plugin at
their root-relative `./` source. Use the branch to receive updates, not an immutable
tag or commit. Invalid updates retain the last working workspace version. This is
workspace distribution, separate from the universal public directory; it is not a
documented installation route for every individual account. See
[OpenAI's GitHub marketplace sync instructions](https://learn.chatgpt.com/docs/enterprise/plugin-management).

For the public ChatGPT directory, upload the ChatGPT ZIP to the existing Resolvent
listing after the initial listing has been created. Bundle updates require a new
ZIP, checks, review and publisher action. No public CI submission API or arbitrary
website/branch polling setting is documented for this skills-only public flow.
Automatic MCP server updates do not apply to this package. Importing skills from
MCP also creates a reviewed package snapshot, not a runtime skill feed. See
[public publication](https://developers.openai.com/plugins/deploy/submission) and
[MCP skill imports](https://developers.openai.com/plugins/build/skills#import-a-skill-from-mcp).

For the initial upload, use the fixed client package (1.2.0 or later), choose the
skills-only path, and complete the host's identity, scan/review and publication
steps. No custom MCP connection, MCP demo or reviewer credentials are required.
After that setup, compatible workflow releases arrive through `workflow-release`
without another user upload or manual refresh. Only changes to installed package
components still require host publication. The authorized publisher completes
legal/policy attestations; package checks do not complete them.

The interaction contract and remaining host/fork acceptance checks are in
[PLUGIN_DESIGN.md](PLUGIN_DESIGN.md). Client 1.3.0 and workflow 1.0.1 implement the
approved reference approach; end-to-end host acceptance remains to be verified.
Fork updating is a separate proposal and is not enabled by this release.

Verify Autonomio's publishing identity in each portal, and supply any required
support/privacy/terms URLs from real publisher pages. Unknown URLs and attestations
are not invented. The authorized developer completes legal/policy attestations.
Skills-only plugins need no MCP review cases, demo or reviewer credentials.
Users receive published versions according to each host's refresh timing; an active
chat can retain its already loaded instructions. CI does not force a chat to reload.

Format references:

- https://developers.openai.com/plugins/build/plugins
- https://developers.openai.com/plugins/deploy/submission
- https://claude.com/docs/plugins/submit
- https://code.claude.com/docs/en/plugins/loading
- https://code.claude.com/docs/en/plugins-reference
- https://code.claude.com/docs/en/plugin-marketplaces
- https://support.claude.com/en/articles/14328846-browse-skills-connectors-and-plugins-in-one-directory
