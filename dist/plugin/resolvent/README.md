# Resolvent

Update a Resolvent world model in a GitHub repository you can access, from the
chat where you invoke Resolvent. Developed by [Autonomio](https://autonom.io).

## Use

Invoke Resolvent with `OWNER/REPOSITORY` and your question, for example:

```text
@resolvent vaquum/resolvent What evidence supports our assumptions?
```

You can also supply a selected conversation, sources, an interview, simulation
results or reasoning. Resolvent reads the selected repository's contracts,
prepares the contribution, handles admission and corrections, follows independent
review and CI, and completes an authorized merge. Explicit narrower instructions
keep their endpoint. If no repository is supplied, Resolvent asks once.

GitHub access comes from your authorized connection or an authenticated CLI in
the invoking chat. Installing the plugin does not grant repository permissions.
No organization, destination repository or Portal service is preconfigured.

## Updates

Install from the host's directory to receive its published releases. Directory
checks and refresh timing apply; a running chat may retain its loaded version.
Claude directory updates are scanned from the release branch. ChatGPT bundled
skill updates require a new package review and publication.

The repository's optional Portal is a separate frontend for exploring its data.
