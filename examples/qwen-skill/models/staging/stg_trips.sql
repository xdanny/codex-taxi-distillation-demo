select
    trip_id,
    pickup_at,
    dropoff_at,
    pickup_location_id,
    dropoff_location_id,
    trip_distance,
    fare_amount,
    tip_amount,
    passenger_count
from read_parquet('input/taxi_trips.parquet')
