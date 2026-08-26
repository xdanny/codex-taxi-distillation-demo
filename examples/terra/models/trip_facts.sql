{{ config(materialized='table') }}

select
    trip_id,
    pickup_at,
    dropoff_at,
    pickup_location_id,
    dropoff_location_id,
    trip_distance,
    fare_amount,
    tip_amount,
    passenger_count,
    pickup_zone,
    dropoff_zone,
    cast(pickup_at as date) as service_date,
    extract(hour from pickup_at) as pickup_hour,
    date_diff('minute', pickup_at, dropoff_at) as trip_minutes,
    fare_amount + tip_amount as total_revenue
from {{ ref('int_trip_classification') }}
where quarantine_reason is null
order by trip_id
