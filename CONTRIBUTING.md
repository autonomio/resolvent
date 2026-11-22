# Contributing to Resolvent

Start upstream work from `main`. In an existing checkout, run `git fetch origin`
and create your working branch from `origin/main`. Read the agent instructions on
the target base branch before making changes. [AGENTS.md](AGENTS.md)

## First checkout

Use Git and Python 3.12 to match CI. Run these commands from a directory where you
want to clone the repository.

```sh
git clone --branch main https://github.com/autonomio/resolvent.git
cd resolvent
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/compiler.py --require-closure
```

The compiler reports `structural_validation` as `passed` with empty `records`
on the upstream template. Local checks run without service credentials.

## Try a model read

Build a local package from the checked-out commit and list up to five claims.
The upstream template returns an empty list. Use a fresh output directory for
each build under the ignored `.resolvent/` directory.

```sh
python scripts/build_knowledge.py --revision HEAD --output .resolvent/onboarding
python scripts/query_knowledge.py --package .resolvent/onboarding search "" --limit 5
```

See a populated input example in the test fixtures.
[Synthetic submission](tests/fixtures/connector-v4-verified.json)

## Find your starting point

| Work | Start here |
| --- | --- |
| Model records, admission and maintenance | [Ontology](docs/Ontology.md) and [agent jobs](docs/AGENT_JOBS.md) |
| Local validation, writes and queries | [Compiler](scripts/compiler.py), [writer](scripts/world_control.py) and [repository operations](docs/OPERATIONS.md) |
| Installed plugin and live workflows | [Shared skill](skills/resolvent/), [live references](workflows/resolvent/) and [plugin releases](docs/PLUGIN_RELEASE.md) |
| Public workflow service | [Service setup and checks](scripts/workflow_mcp/README.md) |

## Before opening a pull request

Keep governance and world-model updates in separate PRs. Re-run the compiler
against your working tree after updating to the current base. For core Python
changes, run the unit suite. The release-copy test uses `rsync`.

```sh
python -m unittest discover -s tests -v
```

Record the installed plugin impact of system changes in the PR. Follow the
release guides for changes to managed core files or plugin inputs. See the
validation workflow for the complete CI checks.
[Core updates](docs/CORE_UPDATES.md) · [Plugin releases](docs/PLUGIN_RELEASE.md) ·
[CI workflow](.github/workflows/validate.yml)
