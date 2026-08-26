-- name: busiest_pickup_hours
select pickup_zone, pickup_hour, trip_count, round(total_revenue, 2) as total_revenue
from hourly_zone_metrics
order by trip_count desc, total_revenue desc, pickup_zone, pickup_hour
limit 10;

-- name: slowest_daily_routes
select service_date, pickup_zone, dropoff_zone, trip_count,
       round(avg_trip_minutes, 2) as avg_trip_minutes
from daily_route_metrics
where trip_count >= 2
order by avg_trip_minutes desc, service_date, pickup_zone, dropoff_zone
limit 10;

-- name: quarantine_reasons
select reason, row_count
from data_quality_summary
order by row_count desc, reason;
