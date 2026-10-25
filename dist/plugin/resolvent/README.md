# Resolvent

Research in your chat. Read your organization's world model when you need it.
Add selected findings, questions or discussion when you ask.
Developed by [Autonomio](https://autonom.io).

Software and plugin: [MIT License](LICENSE). Organization world-model data and
third-party source material are excluded; their rights holders retain control.

## Use ordinary language

| Ask | What happens |
| --- | --- |
| “Research this question with me.” | Research and spar in the chat. |
| “Use our world model to frame this.” | Read relevant context, with evidence and gaps. |
| “What does our world model know about this?” | Answer from its recorded knowledge and sources. |
| “Research this and add the findings.” | Prepare and follow a governed contribution. |
| “Distill this into our world model.” | Capture selected visible discussion, including attributed human insights. |
| “Reformulate this question.” | Return three materially different questions in the chat. |
| “Add the second question.” | Contribute that question without inventing a claim. |

Invoking Resolvent alone authorizes neither world-model reads nor writes. No command
syntax is required. Resolvent clarifies only when intent, selection or destination
is unclear. Plain “distill this” can mean a chat summary; adding it to the model
must be clear from context. Conversation capture performs no new topic research.
A submitted contribution remains pending until independent review, CI and authorized
merge are complete. Resolvent reports the actual status.

## Connect your world

Name your repository, such as `OWNER/REPOSITORY`, when model access is needed. You
can give an organization instead; Resolvent looks for a compatible world and asks if
more than one destination is plausible. It keeps the selection in the current chat.
GitHub access uses your existing authorized connection. If missing or inaccessible,
Resolvent explains the issue and suggests connecting GitHub or enabling that repository.
Installing the plugin does not grant repository permissions.

For reuse across chats in a project, add this to that host's project instructions:

> Use OWNER/REPOSITORY for Resolvent here; read or write it only when I ask.

This is an optional host setting, not a portable installation-time preference.
Chat-only research and reformulation require no repository. No Autonomio account,
custom MCP service, Portal or local software installation is required.

## Updates

The fixed plugin loads versioned workflow guidance from Autonomio's reviewed GitHub
`workflow-release` branch. It pins and verifies the selected references for each
operation. They cannot expand permissions, change your destination or bypass your
organization's approved repository rules. Fetching them sends no chat content to
Autonomio. Retrieval/compatibility failures are reported; an unverified workflow
cannot submit a contribution. Changing installed capabilities still needs a package
update. A workflow version is distinct from the installed plugin version.

Get the [latest published package](https://github.com/autonomio/resolvent/releases/latest)
from GitHub. Public directory availability and acceptance must be verified separately.
ChatGPT workspace admins can import the GitHub marketplace once and receive automatic
syncs. Claude directory updates follow the tracked plugin branch and its publishing
settings. Public ChatGPT package updates require review/publication; routine live
workflow updates do not replace the installed package.

The optional bundled Python reader can verify references where the host already has
execution. GitHub's pinned tree/blob reads provide a no-shell verification route.
If a host cannot supply either, Resolvent explains the limit and can still help in
chat; installing this package alone does not prove host runtime compatibility.
