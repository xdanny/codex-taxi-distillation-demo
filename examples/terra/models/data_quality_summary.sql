{{ config(materialized='table') }}

select
    reason,
    count(*) as row_count
from {{ ref('quarantined_trips') }}
group by reason
order by reason
