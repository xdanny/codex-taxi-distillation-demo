# Accepted Terra Taxi build

Terra produced this dbt project in run `20260826-135934-terra-8dfdf37a`. The unchanged
outside verifier accepted the candidate after one attempt.

- Generated dbt code: [`models/`](models/)
- Singular tests: [`tests/`](tests/)
- Macros: [`macros/`](macros/)
- Queryable release: `serving.duckdb`
- Parquet release: [`exports/`](exports/)
- Model inputs and Analyst rubric: [`model-inputs/`](model-inputs/)
- Source-run provenance and 1,000-row validation: [`evidence/`](evidence/)

From the repository root:

```bash
uv run taxi-demo inspect-example terra
uv run taxi-demo query-example terra 'show tables'
uv run taxi-demo query-example terra \
  'select pickup_zone, pickup_hour, trip_count from hourly_zone_metrics order by trip_count desc, pickup_zone, pickup_hour limit 5'
```

To rerun this checked-in dbt project against its checked-in input:

```bash
cd examples/terra
uv run dbt build --profiles-dir .
```

Terra originally produced this code against a 300-row fixture. The checked-in database and
exports were rebuilt and independently validated against the repository's 1,000-row
fixture. This does not establish general Terra performance across new datasets.
