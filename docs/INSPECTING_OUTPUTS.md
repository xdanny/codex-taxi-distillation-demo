# Inspect the generated data products

Each model run has its own preserved workspace. That workspace contains the dbt source,
dbt build evidence, serving database, Parquet exports, model inputs, and the exact skills
staged for that candidate.

## Choose a completed run

List every preserved experiment:

```bash
uv run taxi-demo experiments
```

The leading `*` marks the active experiment. Add `--json` when another command or script
needs to consume the list.

List the active experiment's completed and interrupted runs:

```bash
uv run taxi-demo runs
```

List a different experiment or request JSON output:

```bash
uv run taxi-demo runs --experiment <experiment-id>
uv run taxi-demo runs --experiment <experiment-id> --json
```

Only a directory with `run.json` is complete. A directory containing only a request and
input receipt is an interrupted attempt and is not included in the comparison report.

Print every important path for the latest accepted run:

```bash
uv run taxi-demo inspect-run
```

Select a specific run when comparing arms:

```bash
uv run taxi-demo inspect-run --run <run-id>
```

## Where the dbt files are

`inspect-run` prints the selected workspace. The accepted candidate's dbt files are under
that `workspace/` directory:

| Path | What it contains |
| --- | --- |
| `dbt_project.yml` | dbt project name, model paths, and materialization defaults |
| `profiles.yml` | local `dbt-duckdb` profile pointing at `serving.duckdb` |
| `models/` | model SQL and schema tests written by the candidate |
| `tests/` | singular dbt tests, including row-accounting checks |
| `macros/` | custom generic tests or helper macros, when the candidate created them |
| `target/manifest.json` | dbt's parsed graph and model metadata |
| `target/run_results.json` | the result and status of every executed model and test |
| `target/compiled/` | compiled SQL; inspect it, but edit files under `models/` or `tests/` |
| `serving.duckdb` | the final serving database |
| `exports/` | one Parquet export for each required serving table |

Candidates can organize `models/` differently. Inspect the preserved tree instead of
assuming a particular staging or marts directory:

```bash
export DEMO_RUN=.demo/experiments/<experiment-id>/runs/<run-id>
find "$DEMO_RUN/workspace/models" "$DEMO_RUN/workspace/tests" \
  -type f -print | sort
```

List dbt resources using the candidate's own project and profile:

```bash
(
  cd "$DEMO_RUN/workspace"
  uv run dbt ls --profiles-dir . --output name
)
```

Rerun the same dbt build from the preserved workspace:

```bash
(
  cd "$DEMO_RUN/workspace"
  uv run dbt build --profiles-dir .
)
```

The outside verifier already reran this build after the model exited. Its result is stored
in `$DEMO_RUN/attempt-1.verification.json`; the candidate's own dbt result is stored in
`$DEMO_RUN/workspace/target/run_results.json`.

## Query the DuckDB serving tables

The current contract requires these tables:

- `trip_facts`
- `quarantined_trips`
- `hourly_zone_metrics`
- `daily_route_metrics`
- `data_quality_summary`

Query the latest accepted run. The command prints the selected run ID before the result:

```bash
uv run taxi-demo query 'show tables'
uv run taxi-demo query \
  'select reason, row_count from data_quality_summary order by row_count desc, reason'
```

Select a particular arm using the full ID printed by `taxi-demo runs`:

```bash
uv run taxi-demo query --run <run-id> \
  'select trip_id, pickup_zone, dropoff_zone, total_revenue
   from trip_facts order by trip_id limit 20'
```

Execute every fixed Analyst query and print each result separately:

```bash
uv run taxi-demo query-file contracts/analyst-questions.sql
uv run taxi-demo query-file --run <run-id> contracts/analyst-questions.sql
```

`query` and `query-file` open `serving.duckdb` read-only and reject non-query statements.
They display at most 100 rows per statement by default; use `--max-rows` to raise the limit.
The independent results are also stored under the finding named `frozen Analyst SQL
executes` in `attempt-1.verification.json`.

## Inspect what the model received

Use these files when you need to explain an arm during the demo:

| Path | Question it answers |
| --- | --- |
| `input-receipt.json` | Which dataset, requirements, and skill files were mounted? |
| `attempt-1.request.json` | Which model, provider, sandbox, workspace, and prompt were used? |
| `attempt-1.events.jsonl` | Which model and tool events occurred? |
| `attempt-1.final.md` | What did the model report when it stopped? |
| `attempt-1.verification.json` | Which independent checks passed or failed? |
| `run.json` | What were the final outcome, attempts, tokens, duration, and treatment? |

The model edits `$DEMO_RUN/workspace/models/`, `tests/`, configuration, and release outputs.
It must not edit the staged dataset, requirements, fixed Analyst SQL, rubric, or skills.

## Query an Iceberg table

The current standalone Taxi contract does **not** publish Iceberg tables. Its accepted
release consists of `serving.duckdb` and the five Parquet exports. The commands below are
for an Iceberg table produced outside the current contract, or for a future version of this
demo that explicitly adds Iceberg publication and verification.

For a table stored at a local or object-storage path, pass the table root containing its
`metadata/` directory:

```bash
uv run taxi-demo query-iceberg /absolute/path/to/iceberg/table
uv run taxi-demo query-iceberg s3://bucket/path/to/table \
  --sql 'select count(*) as rows from {table}'
```

The command replaces `{table}` with a read-only `iceberg_scan(...)` call, installs and
loads DuckDB's Iceberg extension, and rejects write statements.

For an Iceberg REST catalog, create a DuckDB Iceberg secret and attach the catalog. Replace
the placeholders with the catalog's own warehouse, endpoint, and credentials:

```sql
INSTALL iceberg;
LOAD iceberg;
LOAD httpfs;

CREATE SECRET iceberg_secret (
    TYPE iceberg,
    CLIENT_ID '<client-id>',
    CLIENT_SECRET '<client-secret>',
    OAUTH2_SERVER_URI '<oauth-token-endpoint>'
);

ATTACH '<warehouse>' AS taxi_catalog (
    TYPE iceberg,
    SECRET iceberg_secret,
    ENDPOINT '<iceberg-rest-endpoint>'
);

SHOW ALL TABLES;
SELECT * FROM taxi_catalog.<namespace>.<table> LIMIT 20;
SELECT * FROM iceberg_snapshots(taxi_catalog.<namespace>.<table>);
```

Do not put real credentials in this repository. DuckDB catalog attachments last only for
the current connection, so reconnecting requires attaching the catalog again.

Adding Iceberg to the measured Taxi demo is a product change, not a documentation switch.
It requires adding Iceberg tables to the contract, teaching every arm how to publish them,
checking snapshots and table contents in the outside verifier, and rerunning the comparison.

DuckDB reference material:

- [Iceberg extension overview](https://duckdb.org/docs/current/core_extensions/iceberg/overview)
- [Iceberg REST catalogs](https://duckdb.org/docs/current/core_extensions/iceberg/iceberg_rest_catalogs)
- [Iceberg functions and settings](https://duckdb.org/docs/current/core_extensions/iceberg/reference)
