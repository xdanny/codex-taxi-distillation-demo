from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

from codex_taxi_distillation_demo.paths import repository_root, start_experiment


@pytest.fixture
def demo_root(tmp_path: Path) -> Path:
    root = tmp_path / "demo"
    root.mkdir()
    source = repository_root()
    shutil.copytree(source / "contracts", root / "contracts")
    shutil.copytree(source / ".codex", root / ".codex")
    shutil.copy2(source / "pyproject.toml", root / "pyproject.toml")
    shutil.copy2(source / "uv.lock", root / "uv.lock")
    (root / ".git").mkdir()
    start_experiment(root)
    return root


def make_valid_candidate(workspace: Path) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "dbt_project.yml").write_text(
        """name: taxi_demo
version: 1.0.0
config-version: 2
profile: taxi_demo
model-paths: [models]
models:
  taxi_demo:
    +materialized: table
""",
        encoding="utf-8",
    )
    (workspace / "profiles.yml").write_text(
        """taxi_demo:
  target: dev
  outputs:
    dev:
      type: duckdb
      path: serving.duckdb
      threads: 1
""",
        encoding="utf-8",
    )
    models = workspace / "models"
    models.mkdir()
    (models / "trip_facts.sql").write_text(
        """with source as (select * from read_parquet('input/taxi_trips.parquet')),
zones as (select * from read_csv_auto('input/taxi_zones.csv', header=true))
select s.*, p.zone as pickup_zone, d.zone as dropoff_zone,
       cast(s.pickup_at as date) as service_date,
       extract(hour from s.pickup_at)::integer as pickup_hour,
       date_diff('minute', s.pickup_at, s.dropoff_at)::double as trip_minutes,
       (s.fare_amount + s.tip_amount)::double as total_revenue
from source s
join zones p on s.pickup_location_id = p.location_id
join zones d on s.dropoff_location_id = d.location_id
where s.dropoff_at > s.pickup_at and s.trip_distance >= 0 and s.fare_amount >= 0
""",
        encoding="utf-8",
    )
    (models / "quarantined_trips.sql").write_text(
        """with source as (select * from read_parquet('input/taxi_trips.parquet')),
zones as (select * from read_csv_auto('input/taxi_zones.csv', header=true))
select s.*,
case when s.dropoff_at <= s.pickup_at then 'invalid_duration'
     when p.location_id is null then 'unknown_pickup_zone'
     when d.location_id is null then 'unknown_dropoff_zone'
     when s.trip_distance < 0 then 'negative_distance'
     when s.fare_amount < 0 then 'negative_fare' end as reason
from source s
left join zones p on s.pickup_location_id = p.location_id
left join zones d on s.dropoff_location_id = d.location_id
where s.dropoff_at <= s.pickup_at or p.location_id is null or d.location_id is null
   or s.trip_distance < 0 or s.fare_amount < 0
""",
        encoding="utf-8",
    )
    (models / "hourly_zone_metrics.sql").write_text(
        """select pickup_zone, pickup_hour, count(*)::bigint as trip_count,
sum(total_revenue) as total_revenue from {{ ref('trip_facts') }}
group by pickup_zone, pickup_hour
""",
        encoding="utf-8",
    )
    (models / "daily_route_metrics.sql").write_text(
        """select service_date, pickup_zone, dropoff_zone, count(*)::bigint as trip_count,
avg(trip_minutes) as avg_trip_minutes from {{ ref('trip_facts') }}
group by service_date, pickup_zone, dropoff_zone
""",
        encoding="utf-8",
    )
    (models / "data_quality_summary.sql").write_text(
        """select reason, count(*)::bigint as row_count from {{ ref('quarantined_trips') }}
group by reason
""",
        encoding="utf-8",
    )
    subprocess.run(
        [
            shutil.which("dbt") or "dbt",
            "build",
            "--project-dir",
            str(workspace),
            "--profiles-dir",
            str(workspace),
        ],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )
    database = workspace / "serving.duckdb"
    connection = duckdb.connect(str(database))
    exports = workspace / "exports"
    exports.mkdir()
    for table in (
        "trip_facts",
        "quarantined_trips",
        "hourly_zone_metrics",
        "daily_route_metrics",
        "data_quality_summary",
    ):
        connection.execute(
            f"copy {table} to ? (format parquet)", [str(exports / f"{table}.parquet")]
        )
    connection.close()


@pytest.fixture
def fake_codex(tmp_path: Path) -> Path:
    script = tmp_path / "fake-codex"
    script.write_text(
        f"""#!{sys.executable}
import json
import sys
from pathlib import Path
sys.path.insert(0, {str(repository_root())!r})
from tests.conftest import make_valid_candidate

args = sys.argv[1:]
workspace = Path(args[args.index('--cd') + 1])
output = Path(args[args.index('--output-last-message') + 1])
prompt = sys.stdin.read()
if 'Read evidence/index.json' in prompt:
    index = json.loads((workspace / 'evidence' / 'index.json').read_text())
    run_ids = index['sourceRunIds']
    package = workspace / 'output' / 'taxi-data-product-delivery'
    (package / 'assets').mkdir(parents=True)
    (package / 'SKILL.md').write_text('---\\nname: taxi-data-product-delivery\\ndescription: Deliver the Taxi product from repeated evidence.\\n---\\nInvoke $dbt-data-product and $duckdb-analysis.\\n')
    evidence_files = [f"{{run_id}}/run.json" for run_id in run_ids[:2]]
    evidence_map = {{'sourceRunIds': run_ids, 'procedures': [{{'name': 'build and verify', 'instruction': 'Build dbt, publish DuckDB, and run the verifier.', 'sourceRuns': run_ids[:2], 'evidenceFiles': evidence_files}}]}}
    (package / 'assets' / 'evidence-map.json').write_text(json.dumps(evidence_map))
    (package / 'assets' / 'release-checklist.md').write_text('# Release\\nRun the outside verifier.\\n')
    (package / 'assets' / 'symptom-to-repair.md').write_text('# Repair\\nUse verifier findings.\\n')
else:
    make_valid_candidate(workspace)
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text('complete\\n')
print(json.dumps({{'type':'turn.completed','usage':{{'input_tokens':120,'cached_input_tokens':20,'output_tokens':30}}}}))
""",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script
