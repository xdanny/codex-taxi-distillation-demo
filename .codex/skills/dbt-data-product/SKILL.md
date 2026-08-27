---
name: dbt-data-product
description: Build and verify the staged Taxi transformations with dbt-duckdb when the demo asks for a dbt analytics product.
---

# dbt data product

Use the staged `input/taxi_trips.parquet` and `input/taxi_zones.csv` as sources.
The candidate toolchain is already provisioned. Run `dbt` directly. Do not run `uv`,
`pip`, install dependencies, or copy package caches.

1. Create a dbt-duckdb project targeting `serving.duckdb` in the workspace root.
2. Separate accepted and quarantined trips without dropping rows silently.
3. Materialize every table named in `model-inputs/product-contract.json`.
4. Add dbt tests for keys, accepted values, non-negative measures, and row accounting.
5. Run dbt build. Completion means `target/run_results.json` exists and contains no
   failing result.

Keep profiles inside the workspace and invoke `dbt build --profiles-dir .`.
