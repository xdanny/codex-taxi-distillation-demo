with raw as (
    select count(*) as n from {{ ref('stg_trips') }}
),
accepted as (
    select count(*) as n from {{ ref('trip_facts') }}
),
quarantined as (
    select count(*) as n from {{ ref('quarantined_trips') }}
)
select
    raw.n as raw_rows,
    accepted.n as accepted_rows,
    quarantined.n as quarantined_rows
from raw
cross join accepted
cross join quarantined
where raw.n <> accepted.n + quarantined.n
