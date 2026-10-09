# Resolvent plugin releases

Resolvent 1.0.0 is the generic Autonomio plugin. The developer and website are
Autonomio and https://autonom.io. Its description identifies the supported task:
update a Resolvent world model in a GitHub repository the user can access from
the chat where the plugin is invoked.

## Architecture and invocation

The repository owns canonical model data, schemas, contracts and admission rules.
The plugin owns its selected contribution through research/capture, canonical
admission, corrections, independent review, CI and authorized ordinary merge.
An optional Portal explores repository data separately; no Portal host, clipboard
contract, service or question-binding logic belongs to this plugin.

The normal ChatGPT prompt is `@resolvent OWNER/REPOSITORY [question]`.
For example: `@resolvent vaquum/resolvent What evidence supports our assumptions?`
The repository is supplied in chat, never configured in the installed package.
If omitted, ask once and retain it for the current task. Existing source material
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
- Root `plugin.json`: portable identity and ChatGPT listing.
- `.codex-plugin/plugin.json`: synchronized compatibility manifest.
- `.claude-plugin/plugin.json`: Claude manifest.
- `.agents/plugins/marketplace.json`: local ChatGPT/Codex catalog.
- `.claude-plugin/marketplace.json`: local Claude catalog.
- `assets/resolvent.svg` and `assets/resolvent.png`: original icon and directory PNG.
- `docs/PLUGIN_README.md`: standalone README included in each plugin package.
- `dist/chatgpt/resolvent-1.0.0.zip` and `dist/claude/resolvent-1.0.0.zip`: identical
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

Keep the shared workflow, host manifests and release versions aligned. Protocol
1.0 remains protocol 1.0 in this release: resetting the public plugin version does
not reset run identities, schema semantics or the retained observer's policy version.
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
source residue. The observer only changes its unconfigured disabled-policy handling; active gates,
schema evaluator, installer and all original test cases remain. `verification/source-preservation.json` records source provenance
and file hashes; it is not a live research or merge receipt.

## Automated releases

`.github/workflows/plugin-release.yml` runs after `Resolvent validation` succeeds
on an `autonomio/resolvent` main-branch push or manual validation run. It does not
run on PR events, failed validation, or repositories created from this template.
It checks out that exact validated commit; no PR artifacts are trusted for publishing.

The PR checks require a higher shared version when packaged files, packaging
scripts or either published marketplace catalog change. A first
portable release starts at 1.0.0. Release CI compares the ZIP digest against the
last publication: data-only commits do not change the release branch or create
another release, and changed bytes cannot reuse a published version. Older queued
runs cannot roll publication back. Release retries retain the original source SHA.

The workflow publishes a fast-forward commit to `plugin-release`, containing only
the installable plugin, catalogs and a `release.json` provenance record. It creates
`resolvent-v<VERSION>` on the validated main commit, with separate ChatGPT, Claude
and compatibility skill ZIP names, `release.json`, and `SHA256SUMS` on a GitHub release.
An existing release is compared with the expected assets, never overwritten.
The existing `GITHUB_TOKEN` is sufficient for GitHub publication. Email delivery
uses encrypted Actions secrets; credentials never belong in repository files.

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

References: https://resend.com/docs/api-reference/emails/send-email and
https://resend.com/docs/dashboard/emails/idempotency-keys.

## Public directory setup

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

For ChatGPT, upload the ChatGPT ZIP to the existing Resolvent listing after the
initial listing has been created. Bundle updates require a new ZIP, checks, review
and publisher action. No public CI submission API is documented for this skills-only
flow. Automatic MCP server updates do not apply to this package.

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
