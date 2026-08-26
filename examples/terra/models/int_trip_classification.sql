{{ config(materialized='view') }}

with trips as (
    select *
    from read_parquet('input/taxi_trips.parquet')
),
zones as (
    select location_id, zone
    from read_csv_auto('input/taxi_zones.csv')
),
classified as (
    select
        trips.*,
        pickup_zones.zone as pickup_zone,
        dropoff_zones.zone as dropoff_zone,
        case
            when dropoff_at <= pickup_at then 'invalid_duration'
            when pickup_zones.location_id is null then 'unknown_pickup_zone'
            when dropoff_zones.location_id is null then 'unknown_dropoff_zone'
            when trip_distance < 0 then 'negative_distance'
            when fare_amount < 0 then 'negative_fare'
        end as quarantine_reason
    from trips
    left join zones as pickup_zones on trips.pickup_location_id = pickup_zones.location_id
    left join zones as dropoff_zones on trips.dropoff_location_id = dropoff_zones.location_id
)

select *
from classified
