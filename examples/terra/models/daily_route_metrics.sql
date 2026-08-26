{{ config(materialized='table') }}

select
    service_date,
    pickup_zone,
    dropoff_zone,
    count(*) as trip_count,
    avg(trip_minutes) as avg_trip_minutes
from {{ ref('trip_facts') }}
group by service_date, pickup_zone, dropoff_zone
order by service_date, pickup_zone, dropoff_zone
