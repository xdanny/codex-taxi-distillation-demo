---
name: duckdb-analysis
description: Query, export, and validate the demo's Taxi data with DuckDB when the task requires inspectable serving evidence.
---

# DuckDB analysis

Use DuckDB for source inspection and the final serving release.

1. Query Parquet directly before designing transformations.
2. Keep `serving.duckdb` as the single serving database.
3. Export every required serving table to `exports/<table>.parquet`.
4. Use deterministic `ORDER BY` clauses before serializing query results.
5. Run the frozen SQL in `model-inputs/analyst-questions.sql` against the final database.

Completion means the database and every export are readable in a new connection.
