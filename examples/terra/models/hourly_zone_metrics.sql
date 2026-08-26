{{ config(materialized='table') }}

select
    pickup_zone,
    pickup_hour,
    count(*) as trip_count,
    sum(total_revenue) as total_revenue
from {{ ref('trip_facts') }}
group by pickup_zone, pickup_hour
order by pickup_zone, pickup_hour
