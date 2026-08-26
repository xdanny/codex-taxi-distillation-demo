select
    trip_id,
    quarantine_reason as reason
from {{ ref('trip_classification') }}
where quarantine_reason is not null
