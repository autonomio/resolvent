# Public workflow MCP

This stateless service delivers verified public Resolvent workflows and compares
protocol versions. It has no GitHub credentials, repository access, user account,
database, AI inference or world-model write operation. User repository operations
continue through the invoking host's authorized GitHub connection or local CLI.

`get_resolvent_workflow` takes no arguments. It retrieves the approved public
`workflow-release` manifest, pins its source revision and verifies every listed
file's byte length, SHA-256, Git blob identity and UTF-8 content. Redirects,
unexpected fields, unsafe paths, duplicate JSON keys, oversized responses and
incompatible manifests fail closed. No downloaded content is executed.

`check_resolvent_compatibility` accepts only the client and world submission
protocol versions. It reports this verifier's supported versions, not repository
adoption, access, approval, evidence quality or truth. Unsupported versions are
reported explicitly; no world or client is upgraded.

The service requires no authentication. It rejects bearer credentials, unknown
tool arguments and HTTP request bodies above 4 KiB. Workflow reads use fixed
public GitHub URLs and forward no caller headers or content. Application logging
and analytics are disabled. Cloudflare still processes infrastructure metadata;
the public privacy page explains this separately from chat/GitHub data handling.
Private contact correspondence is retained for the owner-confirmed one year.

## Run and deploy

Use Node 24.11 or later:

```sh
npm ci
npm test
npm run check
npm run build
npm run dev
```

`build` is a dry run. Production deployment uses the operator's existing authorized
Cloudflare session: `npx wrangler deploy --keep-vars`. Do not copy that session or
GitHub credentials into this service or a CI secret. No paid resource or plan
upgrade is needed. Autonomio's account was verified as Workers Free on 2026-10-27;
the service shares that account's free request/CPU limits and can become unavailable
when limits are exhausted. It does not automatically upgrade the account.

Configuration declares the Worker name and its public hostnames. An organization
can deploy the same source under its own name/domain and change those settings;
this does not select any world-model repository. The initial Autonomio endpoint is
`https://resolvent.autonom.io/mcp`. Public listing pages use `/`, `/support`,
`/privacy` and `/terms`. `/health` reports the service version.

For OpenAI domain verification, set `OPENAI_PLUGIN_CHALLENGE` to the exact public
token supplied by the selected MCP submission as a deployment variable. It is
intentionally omitted from source configuration so `--keep-vars` preserves it.
The well-known challenge route returns only that token. An unset value returns
404 and does not establish verification.

Compatible workflow releases arrive through the existing reviewed GitHub channel;
they require no service redeployment or user action. Server code/protocol changes
still require source review, tests and an authorized deployment. Public-directory
approval and eligible host updates remain OpenAI's decisions.
