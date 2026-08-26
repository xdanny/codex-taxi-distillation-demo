# Start the Taxi distillation demo from scratch

- Owner: Dan Suman
- Last updated: 2026-08-26
- Last validated: 2026-08-26
- Writes: generated experiment state under `.demo/` only
- Cost boundary: inspecting examples makes no model calls; fresh Terra and DSPy runs use
  hosted model capacity, while Qwen runs consume local compute

This guide starts with an empty machine and ends at one of three visible outcomes. Pick the
shortest path that demonstrates what you need. You do not need to read the Python source.

## 1. Install the tools

You need Git, `uv`, Codex CLI, and LM Studio. The included examples require only Git and
`uv`; live model runs require all four.

Install `uv` using the
[official uv instructions](https://docs.astral.sh/uv/getting-started/installation/). Install
and sign in to Codex using the
[official Codex CLI guide](https://developers.openai.com/codex/cli/). Confirm both commands:

```bash
git --version
uv --version
codex --version
codex login status
```

For local Qwen runs, open LM Studio, load a Qwen model, and start the local API server on
port `1234`. LM Studio documents both the graphical and command-line setup in its
[Codex integration guide](https://lmstudio.ai/docs/integrations/codex). The repository does
not download a model or start LM Studio.

## 2. Clone and install the repository

```bash
git clone https://github.com/xdanny/codex-taxi-distillation-demo.git
cd codex-taxi-distillation-demo
uv sync --frozen --all-groups
```

`uv` installs the locked Python version and dependencies into `.venv`. You do not need to
activate that environment; every command below begins with `uv run`.

## 3. Choose a path

The primary live demo uses Qwen `qwen3.8-27b`. Start with Path A when that model is loaded
in LM Studio. Path B is a zero-cost installation check; Path C reproduces the complete
experiment.

### Path A: run Qwen 3.8 locally with the checked-in skill

This path exercises Codex, LM Studio, the candidate sandbox, dbt, and the outside verifier.
It uses a previously extracted skill, so it does not make hosted Terra calls.

First ask the doctor which model IDs LM Studio advertises:

```bash
uv run taxi-demo doctor
```

When every doctor check says `"pass": true`, create a fresh cohort and run the treatment:

```bash
uv run taxi-demo start
uv run taxi-demo prepare
uv run taxi-demo use-example-skill
uv run taxi-demo run qwen-skill --repairs 1
```

The terminal shows the live Codex task list and commands. Completion ends with a table
containing the run ID, acceptance result, attempt count, reported tokens, and elapsed time.

If `qwen3.8-27b` is not loaded, `doctor` exits with failure but prints `loadedModelIds`.
You can deliberately select another exact Qwen ID for both commands:

```bash
uv run taxi-demo doctor --model YOUR_MODEL_ID
uv run taxi-demo run qwen-skill --model YOUR_MODEL_ID --repairs 1
```

Inspect that exact run:

```bash
uv run taxi-demo runs
uv run taxi-demo inspect-run --run YOUR_RUN_ID
uv run taxi-demo query --run YOUR_RUN_ID 'show tables'
uv run taxi-demo query-file --run YOUR_RUN_ID contracts/analyst-questions.sql
```

Replace `YOUR_RUN_ID` with the full ID printed by `runs`. The receipt marks the skill origin
as `checked-in-example`. This is a live Qwen product build with a previously learned skill;
it is not a new distillation experiment.

### Path B: inspect accepted products without model calls

Use this path to confirm the repository works without spending model time:

```bash
uv run taxi-demo examples
uv run taxi-demo query-example terra \
  'select count(*) as accepted_rows from trip_facts'
uv run taxi-demo query-example qwen-skill \
  'select reason, row_count from data_quality_summary order by reason'
```

Success looks like this:

- the Terra query returns `995` accepted rows;
- the Qwen query returns four rejection reasons totalling `5` rows;
- together they account for all `1,000` fixture rows.

Inspect the generated dbt files and verification receipts:

```bash
uv run taxi-demo inspect-example terra
uv run taxi-demo inspect-example qwen-skill
```

The output prints the exact local paths. Open `models/`, `tests/`,
`evidence/example-validation.json`, and `serving.duckdb` under either example. See
[`examples/README.md`](../examples/README.md) for dbt rebuild commands.

### Path C: run the complete experiment from fresh evidence

This path makes multiple hosted Terra calls and multiple local Qwen calls. It starts three
independent teachers, extracts eval episodes, runs DSPy GEPA, distils a new skill, executes
the four Qwen treatments, and writes a comparison report. Runtime and resource use depend
on the selected models and hardware.

The agent-managed entrypoint can inspect failed phases and resume deliberately:

```bash
codex --ask-for-approval never exec --ephemeral --ignore-user-config \
  --sandbox danger-full-access \
  -C . \
  '$run-offline-data-loop-demo Run the complete demo.'
```

This uses `qwen3.8-27b`. On macOS, the outer `danger-full-access` setting is required because
the harness starts separate Codex processes with their own `workspace-write` candidate
sandboxes.

You can also run the fixed sequence directly:

```bash
uv run taxi-demo full \
  --teachers 3 \
  --parallel 3 \
  --repairs 1 \
  --max-metric-calls 18
```

To use another model, pass the same exact `--model YOUR_MODEL_ID` to `doctor` and `full`, or
name that model ID in the agent instruction.

Success produces `.demo/experiments/EXPERIMENT_ID/artifacts/report/comparison.md`. Inspect
the cohort with:

```bash
uv run taxi-demo current
uv run taxi-demo runs
uv run taxi-demo report
```

Do not start a new cohort when resuming an interrupted experiment. Follow the manual phase
order in the main [`README.md`](../README.md), beginning with the first missing artifact.

## Troubleshooting

### `Codex CLI 'codex' was not found`

Run `codex --version`. If Codex is installed outside `PATH`, point the harness to it:

```bash
export CODEX_BIN=/absolute/path/to/codex
uv run taxi-demo doctor --model YOUR_MODEL_ID
```

### `codexAuth` fails

Run `codex` once and choose a sign-in method, then verify with `codex login status`.

### `lmstudio` fails or the expected model does not match

Start LM Studio's server on port `1234`, load the model, and rerun `doctor`. Copy the exact
identifier from `loadedModelIds`; aliases are not treated as proof that the requested model
was loaded.

### `no active experiment; run taxi-demo start first`

Run `uv run taxi-demo start`, then `uv run taxi-demo prepare`.

### `distilled skill is missing`

For Path B, run `uv run taxi-demo use-example-skill`. For a fresh distillation, run at least
two accepted Terra teachers and then `uv run taxi-demo distill`; the complete experiment
uses three teachers so DSPy can keep train, development, and held-out source runs separate.

### A run fails verification

The failure is retained as evidence. Run `uv run taxi-demo inspect-run --run YOUR_RUN_ID`
and open the printed verification file. `--repairs 1` allows one model repair using those
findings; it does not weaken the verifier.

## Reset or remove generated state

Starting a new experiment preserves old cohorts. To return to a clean clone, remove the
ignored `.demo/` directory yourself after copying any receipts you want to keep. No command
in this repository deletes previous experiment evidence automatically.
