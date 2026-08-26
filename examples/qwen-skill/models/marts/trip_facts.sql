with classified as (
    select * from {{ ref('trip_classification') }} where quarantine_reason is null
),
zones as (
    select zone_id, max(zone_name) as zone_name from {{ ref('stg_zones') }} group by 1
)
select
    c.trip_id,
    c.pickup_at,
    c.dropoff_at,
    c.pickup_location_id,
    c.dropoff_location_id,
    c.trip_distance,
    c.fare_amount,
    c.tip_amount,
    c.passenger_count,
    pz.zone_name as pickup_zone,
    dz.zone_name as dropoff_zone,
    cast(c.pickup_at as date) as service_date,
    extract(hour from c.pickup_at) as pickup_hour,
    date_diff('minute', c.pickup_at, c.dropoff_at) as trip_minutes,
    c.fare_amount + c.tip_amount as total_revenue
from classified as c
left join zones as pz on c.pickup_location_id::varchar = pz.zone_id
left join zones as dz on c.dropoff_location_id::varchar = dz.zone_id
