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

For an offline install, use a local wheelhouse containing wheels for your
Python version and platform, including transitive dependencies. After installing,
run the compiler check above.

```sh
python -m pip install --no-index --find-links "/path/to/wheelhouse" -r requirements.txt
```

## Try a model read

Build a local package from the checked-out commit and list up to five claims.
The upstream template returns an empty list. Use a fresh output directory for
each build under the ignored `.resolvent/` directory.

```sh
python scripts/build_knowledge.py --revision HEAD --output .resolvent/onboarding
python scripts/query_knowledge.py --package .resolvent/onboarding search "" --limit 5
```

Run the focused suite when working on the research-state export.
[Research-state export](docs/OPERATIONS.md#per-question-research-state-export)

```sh
python -m unittest discover -s tests -p test_research_state.py -v
```

## Try verified admission

Run this from the repository root with the Python environment from First checkout
active. The smoke test exercises the local writer with a synthetic submission.

```sh
python -m unittest discover -s tests -p test_verified_admission.py \
  -k test_writer_command_admits_only_where_the_world_opts_in -v
```

The test creates a disposable world, confirms the opt-in gate, then sets
`verified_contributions: true` in that world's `resolvent.yaml`. It dry-runs and
applies admission, validates closure, and confirms the run is already processed
on retry. Expect one passing test with two supported claims admitted.
[Synthetic submission](tests/fixtures/connector-v4-verified.json) ·
[Mechanical admission](docs/AGENT_JOBS.md#mechanical-admission-of-verified-contributions)

## Find your starting point

| Work | Start here |
| --- | --- |
| Model records, admission and maintenance | [Ontology](docs/Ontology.md) and [agent jobs](docs/AGENT_JOBS.md) |
| Local validation, writes and queries | [Compiler](scripts/compiler.py), [writer](scripts/world_control.py) and [repository operations](docs/OPERATIONS.md) |
| Installed plugin and live workflows | [Shared skill](skills/resolvent/), [live references](workflows/resolvent/) and [plugin releases](docs/PLUGIN_RELEASE.md) |
| Public workflow service | Run `node --version` and use Node 24.11 or later. [Service setup and checks](scripts/workflow_mcp/README.md) |

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
