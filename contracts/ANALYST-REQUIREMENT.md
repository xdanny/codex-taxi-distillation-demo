# NYC Yellow Taxi operations product

Build a repeatable analytics product from the staged Taxi trips and zone lookup.
The default fixture is deterministic and synthetic so the demo works offline after
`uv sync`; users may replace it with a compatible dataset.

The product must answer three operational questions:

1. Which pickup zones and hours have the highest trip volume and revenue?
2. Which pickup-to-dropoff routes have the slowest average journeys by day?
3. How many rows were rejected, and why?

Use dbt for transformations and tests. Publish a DuckDB serving database plus one
Parquet export for every required serving table. Account for every input row:

`raw rows = accepted rows + quarantined rows`

A valid trip has a positive duration, known pickup and dropoff zone IDs, non-negative
distance, and non-negative fare. Quarantine invalid rows using the first applicable
reason in this order: `invalid_duration`, `unknown_pickup_zone`,
`unknown_dropoff_zone`, `negative_distance`, `negative_fare`.

Use these exact serving definitions:

- `trip_facts`: source columns plus `pickup_zone`, `dropoff_zone`,
  `service_date = cast(pickup_at as date)`, `pickup_hour = extract(hour from pickup_at)`,
  `trip_minutes = date_diff('minute', pickup_at, dropoff_at)`, and
  `total_revenue = fare_amount + tip_amount` for every valid trip.
- `quarantined_trips`: `trip_id` and the first applicable `reason` above.
- `hourly_zone_metrics`: `pickup_zone, pickup_hour, count(*) as trip_count,
  sum(total_revenue) as total_revenue`, grouped by pickup zone and hour.
- `daily_route_metrics`: `service_date, pickup_zone, dropoff_zone,
  count(*) as trip_count, avg(trip_minutes) as avg_trip_minutes`, grouped by the
  three dimensions shown.
- `data_quality_summary`: `reason, count(*) as row_count`, grouped by reason.

The candidate is complete only when the supplied verifier independently reruns dbt,
compares the serving rows and metrics with the contract, and passes. The model may repair
candidate files, but the requirement, rubric, questions, and verifier stay unchanged.
