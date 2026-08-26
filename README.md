# Codex Taxi Distillation Demo

This repository runs one data-engineering task through several model treatments, then
compares the expense of producing an accepted result. Codex is the only agent interface:
Python prepares evidence and checks outputs, Terra and Qwen do the model work, and no
workflow server is required.

The task uses a deterministic, synthetic dataset shaped like NYC Yellow Taxi data. Each
candidate must use dbt to turn the staged trips and zone lookup into accepted trips,
quarantined trips, hourly pickup metrics, daily route metrics, and a data-quality summary.
An outside verifier reruns dbt, checks every row against the validity rules, recomputes the
metrics, executes three fixed Analyst queries, and checks the Parquet exports.

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

- `uv`
- Codex CLI, authenticated for hosted Terra calls
- LM Studio already serving the exact model ID `qwen3.8-27b` at
  `http://127.0.0.1:1234/v1`

Confirm the local setup before spending model time:

```bash
uv sync --all-groups
uv run taxi-demo doctor
```

The doctor prints the installed commands, the LM Studio endpoint, every advertised model
ID, and whether the required Qwen ID matches.

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
uv run taxi-demo run qwen-bare --repairs 1
uv run taxi-demo optimize --max-metric-calls 18
uv run taxi-demo run qwen-dspy --repairs 1
uv run taxi-demo distill
uv run taxi-demo run qwen-skill --repairs 1
uv run taxi-demo run qwen-both --repairs 1
uv run taxi-demo report
```

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
