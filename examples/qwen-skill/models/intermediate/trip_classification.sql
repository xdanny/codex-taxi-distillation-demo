with trips as (
    select * from {{ ref('stg_trips') }}
),
zones as (
    select zone_id from {{ ref('stg_zones') }} group by 1
)
select
    t.trip_id,
    t.pickup_at,
    t.dropoff_at,
    t.pickup_location_id,
    t.dropoff_location_id,
    t.trip_distance,
    t.fare_amount,
    t.tip_amount,
    t.passenger_count,
    case
        when not (t.dropoff_at > t.pickup_at) then 'invalid_duration'
        when zp.zone_id is null then 'unknown_pickup_zone'
        when zd.zone_id is null then 'unknown_dropoff_zone'
        when t.trip_distance < 0 then 'negative_distance'
        when t.fare_amount < 0 then 'negative_fare'
    end as quarantine_reason
from trips as t
left join zones as zp on t.pickup_location_id::varchar = zp.zone_id
left join zones as zd on t.dropoff_location_id::varchar = zd.zone_id
