# Claude setup — no software installation on the researcher's computer

## Enable the one skill

Download `dist/resolvent.zip` from this repository and upload it in Claude's
**Customize → Skills** (older interfaces may place Skills under Settings). Enable
code execution/file creation when Claude requires it for Skills. This uses Claude's
hosted capability; it is not a local terminal or package installation.

Select the repository once in the conversation, or in project/account instructions:

> My world model is OWNER/REPOSITORY. Use the Resolvent skill for research and evidence-seeking work within [scope]. Follow its process without asking me to manage briefs, claims, evidence records or GitHub. When I ask to capture this chat, use conversation ingestion and do no new research. Submit only the relevant selected material, respect explicit exclusions, and report submission failures.

Do not default to the template repository. A template is for creating new models,
not collecting everyone's research. An explicit target in the current request wins.

## Authorize GitHub writes inside Claude

Claude's **Add from GitHub** feature imports files for context. That is insufficient
for a skill to create branches, write contribution files and open PRs. The required
capabilities are repository read, create branch, write files, create/read PRs. The
skill needs no merge, administration, Actions-secret, or workflow-edit permission.

Use an already approved write-capable GitHub connector where available. Otherwise,
the no-local-install route is **GitHub's hosted remote MCP server**, added through
Claude's own connector settings:

```text
Remote server: https://api.githubcopilot.com/mcp/
```

Claude's current connector interface supports request headers for servers using
fixed credentials. When permitted by your organization, authenticate using a
fine-grained GitHub token restricted to the world-model repository, with **Contents:
read/write**, **Pull requests: read/write**, and the required metadata read access.
Put `Authorization: Bearer <token>` only in the connector's encrypted credential /
request-header settings. Do not paste tokens in chat, the skill, repository files,
URLs, or personalization. Do not request workflow or administration permission.
Use individual authentication where practical. A shared organization connector
credential grants everyone using it that credential's permissions; restrict scope.
GitHub organization approval/SSO or a policy enabling its hosted MCP server may be
required. Do not bypass a workplace restriction.

If an OAuth connection is supported in your account, prefer the approved sign-in
flow. Older GitHub Claude instructions describe an OAuth compatibility limitation;
the request-header path depends on the newer Claude connector settings being
available to your account. Verify the actual tools once rather than assuming.

Team/Enterprise owners may need to authorize the connector and repository access;
members then enable it. Nothing needs to be installed on a researcher's machine.

## First-use check

Ask the skill to check access to the target repository and available GitHub write
tools without writing anything. Then do the first real research or chat-capture run.
A successful contribution returns a real PR URL, not merely a generated filename.
Skill activation alone does not prove delivery. Personalization is an activation
hint, not a guaranteed interception of every research request.

If the account has only file sync and no authorized write connector, research and
packaging still work, but automated PR delivery does not. The skill returns the
JSON package marked **not submitted**. Do not claim the world model was updated.

The repository can be fully tested without a Claude account, but testing actual
skill activation, permissions and the first chat-to-PR round trip requires that
researcher's authenticated Claude session. No such account setup is implied by
creating the GitHub repositories.

## Official capability references (checked 2026-10-06)

- Claude skill packaging and enabling: https://support.claude.com/en/articles/12512198-how-to-create-custom-skills
- Claude GitHub file synchronization: https://support.claude.com/en/articles/10167454-use-the-github-integration
- Claude remote connectors and request-header authentication: https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp
- GitHub hosted MCP documentation: https://github.com/github/github-mcp-server/blob/main/docs/remote-server.md
- Portable skill format: https://agentskills.io/specification
