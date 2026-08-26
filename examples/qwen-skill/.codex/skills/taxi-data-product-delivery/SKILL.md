---
name: taxi-data-product-delivery
description: Deliver and verify a dbt-DuckDB Taxi data product with row accounting, Parquet releases, frozen Analyst SQL, and verifier-led remediation.
---

# Taxi data product delivery

Use this skill to deliver the staged Taxi product. Treat the product contract, frozen Analyst SQL, and staged inputs as release controls; do not change them while responding to a verification failure.

## Required skills

1. Invoke `$duckdb-analysis` before designing transformations and again for the serving release.
2. Invoke `$dbt-data-product` to create the dbt-duckdb project, implement the models and tests, and run the build.

## Build procedure

If the default `uv` cache is inaccessible, set `UV_CACHE_DIR` to a writable temporary directory before invoking the local tooling. This is an environment repair; it does not alter the product inputs or release controls.

1. Read `model-inputs/product-contract.json`, `model-inputs/analyst-questions.sql`, and the staged inputs. Use DuckDB to query `input/taxi_trips.parquet` and `input/taxi_zones.csv` directly, with an `ORDER BY` on any persisted or reported result.
2. Configure the local dbt profile to write the single serving database, `serving.duckdb`. Keep `profiles.yml` in the workspace and run dbt with `--profiles-dir .`.
3. Materialize every contract table: `trip_facts`, `quarantined_trips`, `hourly_zone_metrics`, `daily_route_metrics`, and `data_quality_summary`.
4. Classify each source trip once. A valid trip has positive duration, known pickup and dropoff zone IDs, non-negative distance, and non-negative fare. For an invalid trip, assign only the first applicable reason in this order: `invalid_duration`, `unknown_pickup_zone`, `unknown_dropoff_zone`, `negative_distance`, `negative_fare`.
5. Build `trip_facts` from valid trips with the contract-derived columns and zone names. Build `quarantined_trips` with `trip_id` and its classification reason. Aggregate the other three tables from those serving relations exactly as specified by the contract.
6. Add dbt tests for identifiers and required fields, allowed quarantine reasons, non-negative or positive measures as applicable, and the accounting invariant: `raw rows = accepted rows + quarantined rows`.
7. Run `dbt build --profiles-dir .`. Do not release until `target/run_results.json` exists and has no failed result.

## Release procedure

1. Keep `serving.duckdb` as the release database.
2. Export each required serving table to `exports/<table>.parquet`. Use deterministic `ORDER BY` clauses for serialized query output.
3. Open a new DuckDB connection. Confirm every required table in `serving.duckdb` is readable, every export is readable, and each export matches its serving table in row count and content.
4. Run every unchanged statement in `model-inputs/analyst-questions.sql` against `serving.duckdb`. Record that each named query executes successfully.

## Verifier response

When a verifier reports a finding, map it to the affected contract rule, model, test, database table, or export. Repair only the implementation artifact implicated by the finding; keep the staged inputs, contract, frozen SQL, and skills unchanged. Then rerun `dbt build --profiles-dir .`, recreate affected release outputs, recheck the new connection, rerun the frozen SQL, and submit the verifier again. Use `assets/symptom-to-repair.md` as the response map and `assets/release-checklist.md` as the release gate.
