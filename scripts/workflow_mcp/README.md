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

`build` is a dry run. A local operator can deploy with their existing authorized
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

## Automatic deployment

In `autonomio/resolvent`, `.github/workflows/mcp-deploy.yml` deploys after a
successful main-push validation run. It checks out that exact validated revision
and skips it if main has advanced. Pull requests and forks do not deploy this
service. Dependency installation has no deployment credential.

One-time setup requires an account-owned Cloudflare API token with **Individual
Workers Editor** access restricted to the existing `resolvent-workflows` Worker.
Store it as the encrypted repository Actions secret
`RESOLVENT_CLOUDFLARE_DEPLOY_TOKEN`; set the account ID as repository variable
`RESOLVENT_CLOUDFLARE_ACCOUNT_ID`. This credential must not grant access to other
Workers, DNS or storage. Do not reuse a personal login token or another project's
credential. Missing configuration fails the deployment without changing the Worker.

The job uploads a version tagged with the validated Git revision, preserving
deployment variables with `--keep-vars`, then deploys that tag to 100% of traffic.
Version upload/deployment does not apply routes or domains, so existing hostnames
and the public OpenAI ownership challenge stay in place. Deployment commands run
serially; a failed run remains visible in Actions and can be rerun after correction.

This deployment workflow changes no service code, tools, accepted inputs, installed
skill, protocol, host manifest or distribution bytes. Plugin 1.4.0 remains compatible
and requires no rebuild, reupload or new release for this repository-only automation.
