select f.trip_id
from {{ ref('trip_facts') }} as f
inner join {{ ref('quarantined_trips') }} as q using (trip_id)
