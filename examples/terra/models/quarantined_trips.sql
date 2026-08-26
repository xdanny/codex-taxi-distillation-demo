{{ config(materialized='table') }}

select trip_id, quarantine_reason as reason
from {{ ref('int_trip_classification') }}
where quarantine_reason is not null
order by trip_id
