with counts as (
    select
        (select count(*) from read_parquet('input/taxi_trips.parquet')) as raw_rows,
        (select count(*) from {{ ref('trip_facts') }}) as accepted_rows,
        (select count(*) from {{ ref('quarantined_trips') }}) as quarantined_rows
)

select *
from counts
where raw_rows <> accepted_rows + quarantined_rows
