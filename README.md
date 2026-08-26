# Codex Taxi Distillation Demo

[![CI](https://github.com/xdanny/codex-taxi-distillation-demo/actions/workflows/ci.yml/badge.svg)](https://github.com/xdanny/codex-taxi-distillation-demo/actions/workflows/ci.yml)

This repository runs one data-engineering task through several model treatments, then
compares the expense of producing an accepted result. Codex is the only agent interface:
Python prepares evidence and checks outputs, Terra and Qwen do the model work, and no
workflow server is required.

The task uses a deterministic 1,000-row synthetic fixture shaped like NYC Yellow Taxi
data. It is deliberately small enough for a local live demo and does not measure
large-dataset performance. Each candidate must use dbt to turn the staged trips and zone lookup into accepted trips,
quarantined trips, hourly pickup metrics, daily route metrics, and a data-quality summary.
An outside verifier reruns dbt, checks every row against the validity rules, recomputes the
metrics, executes three fixed Analyst queries, and checks the Parquet exports.

## Start here

If this is your first time in the repository, follow
[`docs/START_HERE.md`](docs/START_HERE.md). It separates three paths:

1. inspect the included accepted products without making model calls;
2. run one local Qwen candidate with the checked-in distilled skill;
3. create fresh Terra evidence, distill a new skill, optimize a DSPy router, and compare
   all Qwen treatments.

The shortest working path is:

```bash
git clone https://github.com/xdanny/codex-taxi-distillation-demo.git
cd codex-taxi-distillation-demo
uv sync --frozen --all-groups
uv run taxi-demo query-example terra 'select count(*) as accepted_rows from trip_facts'
uv run taxi-demo query-example qwen-skill \
  'select reason, row_count from data_quality_summary order by reason'
```

The first query returns `995` accepted rows. The second accounts for the five deliberately
invalid rows. Reaching those results proves that the installation and included DuckDB
products work; it does not run or compare the models.

## What the experiment runs

One fresh experiment contains:

1. three independent Terra candidates, started in parallel;
2. bare Qwen, before either learned artifact exists;
3. DSPy GEPA over observed verifier outcomes and the files Terra changed during repairs,
   followed by Qwen whose real repair is routed through the saved optimized program;
4. a Terra-produced skill distilled from repeated accepted evidence, followed by Qwen with
   that skill;
5. Qwen with both the distilled skill and the optimized DSPy repair router;
6. one comparison of completion, attempts, tokens, elapsed time, and learning overhead.

The default comparison has one Qwen run per arm. It is a demo receipt, not a statistical
transfer claim. Monetary expense stays blank until provider charges, local compute, energy,
maintenance, concurrency, and human-review receipts are supplied.

## Prerequisites

- Git
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/)
- [Codex CLI](https://developers.openai.com/codex/cli/), authenticated for hosted Terra
  calls (`codex login status`)
- LM Studio at `http://127.0.0.1:1234/v1`. The complete demo defaults to the exact
  model ID `qwen3.8-27b`; the full demo and individual Qwen arms can use another
  advertised model ID through `--model`.

Confirm the local setup before spending model time:

```bash
uv sync --frozen --all-groups
uv run taxi-demo doctor
```

The default local route is `qwen3.8-27b`. To verify another exact model ID advertised by
LM Studio, pass it explicitly:

```bash
uv run taxi-demo doctor --model qwen3.6-35b-a3b-ud-mlx
```

The doctor prints the installed commands, the LM Studio endpoint, every advertised model
ID, Codex authentication state, and whether the required Qwen ID matches. The repository
does not download or load an LLM for you. See the
[LM Studio Codex guide](https://lmstudio.ai/docs/integrations/codex) if the server or model
is not ready.

## Run the complete demo through one agent instruction

From the repository root:

```bash
codex --ask-for-approval never exec --ephemeral --ignore-user-config \
  --sandbox danger-full-access \
  -C . \
  '$run-offline-data-loop-demo Run the complete demo.'
```

The project-local `$run-offline-data-loop-demo` skill owns the sequence and stops when the
active experiment has a comparison report or when it reaches a concrete prerequisite or
evidence boundary. The complete run makes several hosted and local model calls and may take
a long time; the exact duration depends on the machine, model responses, repairs, and DSPy
search. Set `CODEX_TIMEOUT_SECONDS` to change the one-hour per-call timeout.
The outer process needs `danger-full-access` because macOS cannot nest the candidate
`workspace-write` sandboxes inside another Seatbelt sandbox. The outer agent only
orchestrates this repository. Every candidate model still runs in a separate random
workspace under its own `workspace-write` sandbox and receives only explicitly staged
inputs and skills.

The same instruction works in an interactive `codex` session:

```text
$run-offline-data-loop-demo Run the complete demo.
```

To use another Qwen model loaded in LM Studio, include its exact advertised ID:

```text
$run-offline-data-loop-demo Run the complete demo using qwen3.6-35b-a3b-ud-mlx.
```

## Run local Qwen with the distilled skill

Use this path when you want to show the treatment arm live without rerunning DSPy or the
other Qwen arms. By default, LM Studio must already be serving `qwen3.8-27b`.

First confirm the model route and inspect the active experiment:

```bash
uv run taxi-demo doctor
uv run taxi-demo current
```

If that experiment already has a distilled skill, start the local Qwen run with:

```bash
uv run taxi-demo run qwen-skill --repairs 1
```

To run the same treatment against the Qwen 3.6 model currently advertised by LM Studio:

```bash
uv run taxi-demo doctor --model qwen3.6-35b-a3b-ud-mlx
uv run taxi-demo run qwen-skill \
  --model qwen3.6-35b-a3b-ud-mlx \
  --repairs 1
```

Omitting `--model` preserves the original `qwen3.8-27b` route. The exact selected slug is
stored in the request and run receipts, so runs made with different local models remain
distinguishable.

Run these `uv run taxi-demo run ...` commands in a normal Terminal window. If an outer
Codex agent is orchestrating the demo, it must use `--sandbox danger-full-access`; macOS
otherwise blocks the harness from starting the inner Codex candidate process and its own
`workspace-write` sandbox.

The harness discovers `codex` from `PATH` first and then checks the standard ChatGPT.app
and Codex.app bundle locations. For a nonstandard installation, set
`CODEX_BIN=/absolute/path/to/codex`.

This is a real treatment run, not a replay. The harness creates a new isolated candidate
workspace, mounts the dbt, DuckDB, and distilled Taxi skills under its local
`.codex/skills/` directory, and explicitly tells Qwen to invoke all three. Qwen is routed
to LM Studio; Terra is not called by this command. After Qwen exits, the unchanged outside
verifier runs the dbt build and Analyst queries. If the first candidate fails, `--repairs
1` gives Qwen the verifier findings and allows one repair attempt.

The command prints the new run ID and whether the result was accepted. Use that full ID to
show exactly what Qwen received and produced:

```bash
uv run taxi-demo runs
uv run taxi-demo inspect-run --run <qwen-skill-run-id>
uv run taxi-demo query --run <qwen-skill-run-id> 'show tables'
uv run taxi-demo query-file --run <qwen-skill-run-id> \
  contracts/analyst-questions.sql
```

The run receipt records the exact selected model ID, the LM Studio route, the three selected
skills, the prompt hash, token usage, elapsed time, and each verifier result. The preserved
candidate workspace contains the generated dbt project and serving database.

While a candidate is running, the terminal streams its Codex task list, agent messages,
commands, command output, errors, and completion usage. The same untouched JSON events are
written to the run's `attempt-*.events.jsonl` file as they arrive.

### Create the distilled skill first

A fresh clone has no learned artifact. Build one from independent accepted Terra
candidates before starting the local Qwen treatment:

```bash
uv run taxi-demo start
uv run taxi-demo prepare
uv run taxi-demo teachers --count 3 --parallel 3 --repairs 1
uv run taxi-demo distill
uv run taxi-demo run qwen-skill --repairs 1
```

`distill` requires at least two accepted Terra teacher runs. It publishes the generated
skill inside the active experiment under
`artifacts/distilled-skill/taxi-data-product-delivery/`. The final command mounts only that
published skill into Qwen's candidate workspace; it does not expose the teacher workspaces
or their source evidence to Qwen.

### Use the checked-in skill for a shorter local demonstration

To show a real local Qwen build without first paying for new Terra teacher runs:

```bash
uv run taxi-demo doctor --model qwen3.6-35b-a3b-ud-mlx
uv run taxi-demo start
uv run taxi-demo prepare
uv run taxi-demo use-example-skill
uv run taxi-demo run qwen-skill \
  --model qwen3.6-35b-a3b-ud-mlx \
  --repairs 1
```

Replace the model ID with the exact ID shown by your LM Studio server. The run receipt
records `skillOrigin` as `checked-in-example`, so this route cannot be mistaken for fresh
distillation or evidence of transfer.

## Inspect accepted Terra and Qwen dbt examples

The repository includes two accepted builds under [`examples/`](examples/): one produced
by Terra and one produced by Qwen with the distilled Taxi skill. Each directory contains
the generated dbt project, source fixture, serving database, Parquet exports, model inputs,
and compact evidence receipts. You can inspect and query them without relying on `.demo/`
state from the machine that produced the runs.

```bash
uv run taxi-demo examples
uv run taxi-demo inspect-example terra
uv run taxi-demo inspect-example qwen-skill

uv run taxi-demo query-example terra 'show tables'
uv run taxi-demo query-example qwen-skill \
  'select reason, row_count from data_quality_summary order by row_count desc, reason'
```

See [`examples/README.md`](examples/README.md) for the source run IDs, model routes, mounted
skills, dbt rerun commands, and evidence boundaries.

## Record and open the model-run video player

After an experiment has accepted `qwen-bare`, `qwen-skill`, and `terra` runs, render a
short terminal replay for each treatment:

```bash
uv run taxi-demo record-demos
uv run taxi-demo serve-demos
```

The second command opens `http://127.0.0.1:8765/`. Use a different port or keep the browser
closed with:

```bash
uv run taxi-demo serve-demos --port 9000 --no-open-browser
```

The player shows the model route, mounted skills, elapsed time, reported tokens, acceptance
result, and links to the exact request, raw Codex JSONL, verifier result, run receipt, and
terminal cast. When two accepted Qwen takes exist for an arm, the player keeps both so the
audience can see run-to-run variance instead of one selected comparison. Each MP4 is an
edited evidence replay made from a completed run. It is labelled as a replay on the page
and inside the video; it is not presented as fresh live execution. The generated videos
and receipts stay under `demo-site/assets/`.

`record-demos` requires `agg` and `ffmpeg` on `PATH`. It does not make new model calls. To
record a particular preserved experiment instead of the active one:

```bash
uv run taxi-demo record-demos --experiment <experiment-id>
```

## Inspect or resume a run

Every complete invocation starts a new experiment cohort. Old evidence remains available
but is never mixed into the active cohort.

```bash
uv run taxi-demo current
uv run taxi-demo report
```

If the agent stops between phases, inspect the active experiment and run the remaining
manual commands from the point where it stopped. Do not run `taxi-demo start` or
`taxi-demo full` while resuming: both deliberately select a new cohort.

Start a new manual experiment with:

```bash
uv run taxi-demo start
uv run taxi-demo prepare
```

Then run or resume the remaining phases in this order:

```bash
uv run taxi-demo teachers --count 3 --parallel 3 --repairs 1
uv run taxi-demo run qwen-bare --model YOUR_MODEL_ID --repairs 1
uv run taxi-demo optimize --model YOUR_MODEL_ID --max-metric-calls 18
uv run taxi-demo run qwen-dspy --model YOUR_MODEL_ID --repairs 1
uv run taxi-demo distill
uv run taxi-demo run qwen-skill --model YOUR_MODEL_ID --repairs 1
uv run taxi-demo run qwen-both --model YOUR_MODEL_ID --repairs 1
uv run taxi-demo report
```

Replace `YOUR_MODEL_ID` with the same exact LM Studio ID that passed `taxi-demo doctor`.

Generated state stays under `.demo/`:

- `.demo/active-experiment` names the current cohort;
- `.demo/experiments/<experiment-id>/runs/<run-id>/` contains the exact request, raw Codex
  JSONL, stderr, immutable input receipt, every verifier result, and a snapshot of every
  candidate attempt;
- `.demo/experiments/<experiment-id>/artifacts/distilled-skill/` contains the generated
  deployable skill and validation result. Its separate `provenance/source-evidence/`
  directory retains the teacher evidence for audit, but is never mounted into a treatment
  candidate;
- `.demo/experiments/<experiment-id>/artifacts/dspy/` contains observed eval splits, raw
  Codex-backed GEPA calls, the saved router, its readable instruction, and held-out scores;
- `.demo/experiments/<experiment-id>/artifacts/report/` contains the JSON evidence and the
  readable comparison.

See [Inspect the generated data products](docs/INSPECTING_OUTPUTS.md) for the exact dbt
paths, commands for querying the DuckDB and Parquet releases, the model-input receipts, and
Iceberg query examples. The current measured contract publishes DuckDB and Parquet; it does
not claim that these runs published Iceberg tables.

The shortest inspection path is:

```bash
uv run taxi-demo experiments
uv run taxi-demo runs
uv run taxi-demo inspect-run
uv run taxi-demo query 'show tables'
uv run taxi-demo query-file contracts/analyst-questions.sql
uv run taxi-demo query-iceberg /path/to/iceberg/table \
  --sql 'select count(*) as rows from {table}'
```

Each candidate runs from a random temporary directory outside the repository and receives
only its staged dataset, contracts, and selected project-local skills. The DSPy program runs
in the harness and passes only its selected repair action to the candidate. An external
receipt detects changes to staged files, and the finished workspace is moved into the active
experiment. This removes sibling runs and learned artifacts from the candidate's working
tree. Codex's standard workspace sandbox controls writes; the repository still does not
claim machine-wide filesystem read isolation against a deliberately probing model.

## Verify the repository without running real model arms

```bash
uv run ruff check .
uv run mypy src
uv run pytest -q
```

The tests use a fake Codex executable to exercise parallel candidates, outside dbt
verification, semantic Taxi checks, evidence-preserving repairs, skill publication, all four
Qwen treatment configurations, and report generation. Separate DSPy tests exercise the
Codex-backed LM response shape, saved-program loading, and a no-fabricated-failures path.
The recorded live project-skill discovery check is in
`docs/verification/skill-discovery-smoke.md`.

## Project status

This is a reproducible conference demo, not a production data-platform framework. The
checked-in examples let readers inspect accepted dbt products without making model calls;
the experiment commands create fresh evidence on the reader's own machine. The 1,000-row
fixture is intentionally sized for a live local demo and is not a performance benchmark.

Issues and pull requests are welcome, especially when they include a reproducible run
receipt or a failing test.

## License

[MIT](LICENSE)
