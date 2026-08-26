# Symptom-to-repair guide

The accepted evidence contains no verifier findings. It does show the same environment repair in all three runs: directing an inaccessible default uv cache to a writable temporary location. The remaining rows apply when a verifier reports an acceptance symptom.

| Verifier symptom | Repair | Recheck |
| --- | --- | --- |
| Default uv cache is inaccessible | Set `UV_CACHE_DIR` to a writable temporary directory and retry the local command. Do not change product inputs or controls. | Continue source inspection or `dbt build --profiles-dir .`. |
| A required candidate file or serving table is missing | Restore the dbt profile or model that produces the missing artifact; ensure all five contract tables materialize in `serving.duckdb`. | Run `dbt build --profiles-dir .`, then inspect the database in a new connection. |
| Serving rows or metrics do not match the contract | Correct the affected serving model's selected columns, derivation, or grouping to match the contract. | Rebuild; compare serving relations with independent source aggregations. |
| Input-row accounting fails | Correct the accepted/quarantined split so every raw trip is in exactly one relation. | Run the row-accounting dbt test and verify raw equals accepted plus quarantined. |
| Quarantine reason is wrong | Correct the classification CASE or joins so validity checks use the required first-match precedence. | Rebuild and inspect `quarantined_trips` and `data_quality_summary`. |
| A dbt model or test fails | Repair the model or test configuration that produced the failure; retain the required test categories. | Run `dbt build --profiles-dir .` and confirm no failed result in `target/run_results.json`. |
| A Parquet export is unreadable or differs from its serving table | Re-export the affected serving relation to its corresponding `exports/<table>.parquet` file using deterministic ordering. | Read the export and serving relation in a new DuckDB connection; compare row counts and content. |
| Frozen Analyst SQL fails | Restore the contract table, column, or metric required by the unchanged SQL; do not edit the frozen SQL. | Run every statement in `model-inputs/analyst-questions.sql` against `serving.duckdb`. |
| Protected inputs or controls changed | Revert the unintended change to staged inputs, contract, frozen SQL, or skills, then repair only implementation artifacts. | Rerun the verifier's unchanged-control check and the full release checklist. |
