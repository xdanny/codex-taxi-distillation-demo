select
    location_id::varchar as zone_id,
    zone as zone_name
from read_csv_auto('input/taxi_zones.csv', header=true)
