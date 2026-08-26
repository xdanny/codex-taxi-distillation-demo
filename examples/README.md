# Accepted dbt build examples

These are two preserved outputs from the same Taxi contract and source fixture. They let
you inspect and query a completed build without depending on `.demo/` state from another
machine.

| Example | Source run | Model route | Mounted skills |
| --- | --- | --- | --- |
| [`terra/`](terra/) | `20260826-135934-terra-8dfdf37a` | `gpt-5.6-terra` through Codex | dbt, DuckDB |
| [`qwen-skill/`](qwen-skill/) | `20260826-142447-qwen-skill-fe42bfa8` | `qwen3.8-27b` through LM Studio and Codex | dbt, DuckDB, distilled Taxi delivery skill |

List and inspect them from the repository root:

```bash
uv run taxi-demo examples
uv run taxi-demo inspect-example terra
uv run taxi-demo inspect-example qwen-skill
```

Query either preserved `serving.duckdb` through the repository CLI:

```bash
uv run taxi-demo query-example terra \
  'select pickup_zone, pickup_hour, trip_count from hourly_zone_metrics order by trip_count desc, pickup_zone, pickup_hour limit 5'

uv run taxi-demo query-example qwen-skill \
  'select reason, row_count from data_quality_summary order by row_count desc, reason'
```

Both queries are read-only. Each example includes its generated dbt files, 1,000-row
fixture, Parquet exports, serving database, compact source-run provenance, and a fresh
outside-verifier result for the checked-in example. The model originally produced the code
against the 300-row fixture recorded in `provenance.json`; this repository republishes and
revalidates that code against 1,000 rows. The two examples do not establish that one model
or treatment is generally better.
