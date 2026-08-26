# Inspect the generated data products

Each model run has its own preserved workspace. That workspace contains the dbt source,
dbt build evidence, serving database, Parquet exports, model inputs, and the exact skills
staged for that candidate.

## Choose a completed run

First print the active experiment:

```bash
uv run taxi-demo current
```

The command returns an experiment ID and its absolute path. List its completed runs:

```bash
find .demo/experiments/<experiment-id>/runs \
  -mindepth 2 -maxdepth 2 -name run.json -print | sort
```

Set a short variable for the run you want to inspect:

```bash
export DEMO_RUN=.demo/experiments/<experiment-id>/runs/<run-id>
```

Only a directory with `run.json` is complete. A directory containing only a request and
input receipt is an interrupted attempt and is not included in the comparison report.

## Where the dbt files are

The accepted candidate is under `$DEMO_RUN/workspace/`:

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

Query them read-only with the locked project environment:

```bash
uv run python <<'PY'
import os
from pathlib import Path

import duckdb

database = Path(os.environ["DEMO_RUN"]) / "workspace" / "serving.duckdb"
connection = duckdb.connect(str(database), read_only=True)

connection.sql("show tables").show()
connection.sql("""
    select pickup_zone, sum(trip_count) as trips
    from hourly_zone_metrics
    group by pickup_zone
    order by trips desc, pickup_zone
    limit 10
""").show()
PY
```

Query a Parquet release directly, without opening `serving.duckdb`:

```bash
uv run python <<'PY'
import os
from pathlib import Path

import duckdb

export = Path(os.environ["DEMO_RUN"]) / "workspace" / "exports" / "trip_facts.parquet"
duckdb.sql(
    "select trip_id, pickup_zone, dropoff_zone, total_revenue "
    "from read_parquet(?) order by trip_id limit 20",
    params=[str(export)],
).show()
PY
```

The fixed Analyst queries are in `$DEMO_RUN/workspace/model-inputs/analyst-questions.sql`.
The independent results, row counts, and samples are recorded under the finding named
`frozen Analyst SQL executes` in `attempt-1.verification.json`.

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

For a table stored at a local or object-storage path, point `ICEBERG_TABLE` at the table
root containing its `metadata/` directory:

```bash
export ICEBERG_TABLE=/absolute/path/to/iceberg/table

uv run python <<'PY'
import os

import duckdb

connection = duckdb.connect()
connection.execute("install iceberg")
connection.execute("load iceberg")

table = os.environ["ICEBERG_TABLE"]
connection.sql(
    "select * from iceberg_scan(?, allow_moved_paths = true) limit 20",
    params=[table],
).show()
connection.sql(
    "select * from iceberg_snapshots(?) order by timestamp_ms desc",
    params=[table],
).show()
PY
```

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
