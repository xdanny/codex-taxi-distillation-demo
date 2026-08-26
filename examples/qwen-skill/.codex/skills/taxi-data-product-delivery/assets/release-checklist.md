# Taxi data product release checklist

- [ ] Invoke `$duckdb-analysis` and inspect `input/taxi_trips.parquet` and `input/taxi_zones.csv` directly before transformation design.
- [ ] Invoke `$dbt-data-product` and configure the workspace profile to write `serving.duckdb`.
- [ ] Preserve the staged inputs, product contract, frozen Analyst SQL, and skills.
- [ ] Materialize `trip_facts`, `quarantined_trips`, `hourly_zone_metrics`, `daily_route_metrics`, and `data_quality_summary`.
- [ ] Classify invalid trips using the required first-match reason precedence.
- [ ] Add and pass key, accepted-value, measure, and row-accounting tests.
- [ ] Run `dbt build --profiles-dir .`; verify `target/run_results.json` contains no failures.
- [ ] Verify `raw rows = accepted rows + quarantined rows`.
- [ ] Publish `serving.duckdb` and `exports/<table>.parquet` for every required table.
- [ ] In a new DuckDB connection, read each serving table and export; confirm matching row counts and contents.
- [ ] Run every frozen statement in `model-inputs/analyst-questions.sql` against `serving.duckdb`.
- [ ] If the verifier reports a finding, repair the implicated implementation and repeat all affected gates before resubmitting.
