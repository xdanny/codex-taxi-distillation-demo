from __future__ import annotations

import csv
import shutil
from pathlib import Path

import duckdb

from .domain import sha256_file, write_json
from .paths import repository_root, state_root


def prepare_fixture(root: Path | None = None, *, force: bool = False) -> Path:
    repo = root or repository_root()
    destination = state_root(repo) / "dataset" / "default"
    if destination.exists() and not force:
        return destination
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)

    zones = [
        (1, "Newark Airport"),
        (4, "Alphabet City"),
        (13, "Battery Park City"),
        (48, "Clinton East"),
        (79, "East Village"),
        (161, "Midtown Center"),
        (230, "Times Sq/Theatre District"),
    ]
    zones_path = destination / "taxi_zones.csv"
    with zones_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("location_id", "zone"))
        writer.writerows(zones)

    trips_path = destination / "taxi_trips.parquet"
    connection = duckdb.connect()
    connection.execute(
        """
        create table trips as
        with generated as (
          select i,
                 timestamp '2025-01-01 00:00:00' + (i * interval 17 minute) as pickup_at,
                 timestamp '2025-01-01 00:00:00' + (i * interval 17 minute)
                   + ((8 + (i % 44)) * interval 1 minute) as dropoff_at,
                 [4, 13, 48, 79, 161, 230][1 + (i % 6)]::integer as pickup_location_id,
                 [13, 48, 79, 161, 230, 4][1 + ((i * 3) % 6)]::integer as dropoff_location_id,
                 round(1.2 + (i % 37) * 0.31, 2) as trip_distance,
                 round(7.0 + (i % 51) * 1.17, 2) as fare_amount,
                 round((i % 12) * 0.65, 2) as tip_amount,
                 1 + (i % 4) as passenger_count
          from range(0, 300) as r(i)
        )
        select
          i::bigint as trip_id,
          case when i in (17, 117) then dropoff_at else pickup_at end as pickup_at,
          case when i in (17, 117) then pickup_at else dropoff_at end as dropoff_at,
          case when i = 217 then 999 else pickup_location_id end as pickup_location_id,
          dropoff_location_id,
          case when i = 33 then -1.0 else trip_distance end as trip_distance,
          case when i = 44 then -5.0 else fare_amount end as fare_amount,
          tip_amount,
          passenger_count
        from generated
        """
    )
    connection.execute("copy trips to ? (format parquet)", [str(trips_path)])
    connection.close()

    manifest = {
        "schemaVersion": 1,
        "fixtureRevision": "taxi-shaped-v1",
        "classification": "deterministic synthetic NYC Yellow Taxi-shaped fixture",
        "files": {
            "taxi_trips.parquet": {"sha256": sha256_file(trips_path), "rows": 300},
            "taxi_zones.csv": {"sha256": sha256_file(zones_path), "rows": len(zones)},
        },
    }
    write_json(destination / "dataset-manifest.json", manifest)
    return destination
