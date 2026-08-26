select
    reason,
    count(*) as row_count
from {{ ref('quarantined_trips') }}
group by 1
