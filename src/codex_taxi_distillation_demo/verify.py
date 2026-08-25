from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import duckdb

from .domain import read_json, sha256_file, write_json

REQUIRED_TABLES = (
    "trip_facts",
    "quarantined_trips",
    "hourly_zone_metrics",
    "daily_route_metrics",
    "data_quality_summary",
)
REQUIRED_FILES = (
    "dbt_project.yml",
    "profiles.yml",
    "serving.duckdb",
    "target/run_results.json",
)


def finding(name: str, passed: bool, evidence: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "pass": passed, "evidence": evidence}


def parse_questions(path: Path) -> list[tuple[str, str]]:
    text = path.read_text(encoding="utf-8")
    matches = list(re.finditer(r"^-- name: ([a-z0-9_]+)\s*$", text, flags=re.MULTILINE))
    statements: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sql = text[start:end].strip()
        if sql.endswith(";"):
            sql = sql[:-1]
        statements.append((match.group(1), sql))
    return statements


def scalar_int(
    connection: duckdb.DuckDBPyConnection, sql: str, parameters: list[str] | None = None
) -> int:
    row = connection.execute(sql, parameters or []).fetchone()
    if row is None:
        raise ValueError(f"query returned no scalar row: {sql}")
    return int(row[0])


def sql_path(path: Path) -> str:
    return path.as_posix().replace("'", "''")


def run_outside_dbt(workspace: Path) -> dict[str, Any]:
    executable = shutil.which("dbt")
    if executable is None:
        return finding("outside dbt build passed", False, {"error": "dbt not found on PATH"})
    try:
        completed = subprocess.run(
            [
                executable,
                "build",
                "--project-dir",
                str(workspace),
                "--profiles-dir",
                str(workspace),
                "--target-path",
                str(workspace / "target"),
            ],
            cwd=workspace,
            text=True,
            capture_output=True,
            check=False,
            timeout=180,
        )
    except subprocess.TimeoutExpired as exc:
        return finding(
            "outside dbt build passed",
            False,
            {"error": f"dbt timed out after {exc.timeout}s"},
        )
    return finding(
        "outside dbt build passed",
        completed.returncode == 0,
        {
            "exitCode": completed.returncode,
            "stdoutTail": completed.stdout[-2000:],
            "stderrTail": completed.stderr[-2000:],
        },
    )


def semantic_checks(connection: duckdb.DuckDBPyConnection, workspace: Path) -> dict[str, Any]:
    trips = sql_path(workspace / "input" / "taxi_trips.parquet")
    zones = sql_path(workspace / "input" / "taxi_zones.csv")
    connection.execute(
        f"""
        create or replace temp view expected_valid as
        with source as (select * from read_parquet('{trips}')),
        zone_lookup as (select * from read_csv_auto('{zones}', header=true))
        select s.*, p.zone as pickup_zone, d.zone as dropoff_zone,
               cast(s.pickup_at as date) as service_date,
               extract(hour from s.pickup_at)::integer as pickup_hour,
               date_diff('minute', s.pickup_at, s.dropoff_at)::double as trip_minutes,
               (s.fare_amount + s.tip_amount)::double as total_revenue
        from source s
        join zone_lookup p on s.pickup_location_id = p.location_id
        join zone_lookup d on s.dropoff_location_id = d.location_id
        where s.dropoff_at > s.pickup_at
          and s.trip_distance >= 0 and s.fare_amount >= 0
        """
    )
    connection.execute(
        f"""
        create or replace temp view expected_quarantine as
        with source as (select * from read_parquet('{trips}')),
        zone_lookup as (select * from read_csv_auto('{zones}', header=true))
        select s.trip_id,
               case
                 when s.dropoff_at <= s.pickup_at then 'invalid_duration'
                 when p.location_id is null then 'unknown_pickup_zone'
                 when d.location_id is null then 'unknown_dropoff_zone'
                 when s.trip_distance < 0 then 'negative_distance'
                 when s.fare_amount < 0 then 'negative_fare'
               end as reason
        from source s
        left join zone_lookup p on s.pickup_location_id = p.location_id
        left join zone_lookup d on s.dropoff_location_id = d.location_id
        where s.dropoff_at <= s.pickup_at or p.location_id is null or d.location_id is null
           or s.trip_distance < 0 or s.fare_amount < 0
        """
    )
    comparisons = {
        "trip_facts": """
            select trip_id, pickup_at, dropoff_at, pickup_location_id, dropoff_location_id,
                   trip_distance, fare_amount, tip_amount, passenger_count, pickup_zone,
                   dropoff_zone, service_date, pickup_hour, trip_minutes, total_revenue
            from trip_facts
        """,
        "expected_trip_facts": """
            select trip_id, pickup_at, dropoff_at, pickup_location_id, dropoff_location_id,
                   trip_distance, fare_amount, tip_amount, passenger_count, pickup_zone,
                   dropoff_zone, service_date, pickup_hour, trip_minutes, total_revenue
            from expected_valid
        """,
    }
    trip_delta = scalar_int(
        connection,
        "select count(*) from (({actual} except all {expected}) union all "
        "({expected} except all {actual}))".format(
            actual=comparisons["trip_facts"], expected=comparisons["expected_trip_facts"]
        ),
    )
    quarantine_delta = scalar_int(
        connection,
        """select count(*) from (
          (select trip_id, reason from quarantined_trips
           except all select trip_id, reason from expected_quarantine)
          union all
          (select trip_id, reason from expected_quarantine
           except all select trip_id, reason from quarantined_trips)
        )""",
    )
    hourly_delta = scalar_int(
        connection,
        """with expected as (
          select pickup_zone, pickup_hour, count(*)::bigint as trip_count,
                 sum(total_revenue) as total_revenue
          from expected_valid group by pickup_zone, pickup_hour
        )
        select count(*) from (
          (select * from hourly_zone_metrics except all select * from expected)
          union all (select * from expected except all select * from hourly_zone_metrics)
        )""",
    )
    daily_delta = scalar_int(
        connection,
        """with expected as (
          select service_date, pickup_zone, dropoff_zone, count(*)::bigint as trip_count,
                 avg(trip_minutes) as avg_trip_minutes
          from expected_valid group by service_date, pickup_zone, dropoff_zone
        )
        select count(*) from (
          (select * from daily_route_metrics except all select * from expected)
          union all (select * from expected except all select * from daily_route_metrics)
        )""",
    )
    quality_delta = scalar_int(
        connection,
        """with expected as (
          select reason, count(*)::bigint as row_count
          from expected_quarantine group by reason
        )
        select count(*) from (
          (select * from data_quality_summary except all select * from expected)
          union all (select * from expected except all select * from data_quality_summary)
        )""",
    )
    deltas = {
        "tripFacts": trip_delta,
        "quarantine": quarantine_delta,
        "hourlyMetrics": hourly_delta,
        "dailyMetrics": daily_delta,
        "qualitySummary": quality_delta,
    }
    return finding("serving rows and metrics match the contract", not any(deltas.values()), deltas)


def verify_candidate(
    workspace: Path,
    *,
    output: Path | None = None,
    expected_receipt: Path | None = None,
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    if expected_receipt is not None:
        receipt = read_json(expected_receipt)
        expected_files = receipt.get("files", {})
        if not isinstance(expected_files, dict):
            raise ValueError(f"invalid workspace receipt: {expected_receipt}")
        changed: list[str] = []
        missing_inputs: list[str] = []
        for relative, expected_hash in expected_files.items():
            path = workspace / str(relative)
            if not path.is_file():
                missing_inputs.append(str(relative))
            elif sha256_file(path) != expected_hash:
                changed.append(str(relative))
        findings.append(
            finding(
                "staged inputs and skills are unchanged",
                not changed and not missing_inputs,
                {"changed": changed, "missing": missing_inputs},
            )
        )
    findings.append(run_outside_dbt(workspace))
    missing = [path for path in REQUIRED_FILES if not (workspace / path).is_file()]
    findings.append(finding("required candidate files exist", not missing, {"missing": missing}))

    run_results_path = workspace / "target" / "run_results.json"
    if run_results_path.is_file():
        try:
            results = read_json(run_results_path).get("results", [])
            failures = [
                result
                for result in results
                if isinstance(result, dict) and result.get("status") not in {"success", "pass"}
            ]
            findings.append(
                finding(
                    "dbt build and tests passed",
                    bool(results) and not failures,
                    {"resultCount": len(results), "failureCount": len(failures)},
                )
            )
        except (ValueError, json.JSONDecodeError) as exc:
            findings.append(finding("dbt build and tests passed", False, {"error": str(exc)}))
    else:
        findings.append(
            finding("dbt build and tests passed", False, {"missing": str(run_results_path)})
        )

    database = workspace / "serving.duckdb"
    connection: duckdb.DuckDBPyConnection | None = None
    try:
        if database.is_file():
            connection = duckdb.connect(str(database), read_only=True)
            tables = {
                row[0]
                for row in connection.execute(
                    "select table_name from information_schema.tables where table_schema='main'"
                ).fetchall()
            }
            missing_tables = sorted(set(REQUIRED_TABLES) - tables)
            findings.append(
                finding(
                    "five serving tables exist", not missing_tables, {"missing": missing_tables}
                )
            )
            if not missing_tables:
                findings.append(semantic_checks(connection, workspace))

            raw = scalar_int(
                connection,
                "select count(*) from read_parquet(?)",
                [str(workspace / "input" / "taxi_trips.parquet")],
            )
            accepted = scalar_int(connection, "select count(*) from trip_facts")
            quarantined = scalar_int(connection, "select count(*) from quarantined_trips")
            findings.append(
                finding(
                    "every input row is accounted for",
                    raw == accepted + quarantined,
                    {"raw": raw, "accepted": accepted, "quarantined": quarantined},
                )
            )

            query_results: dict[str, Any] = {}
            query_errors: dict[str, str] = {}
            questions = parse_questions(workspace / "model-inputs" / "analyst-questions.sql")
            for name, sql in questions:
                try:
                    rows = connection.execute(sql).fetchall()
                    query_results[name] = {"rowCount": len(rows), "sample": rows[:3]}
                except Exception as exc:  # DuckDB exposes several provider-specific exceptions.
                    query_errors[name] = str(exc)
            findings.append(
                finding(
                    "frozen Analyst SQL executes",
                    bool(questions) and not query_errors,
                    {"queries": query_results, "errors": query_errors},
                )
            )

            export_errors: dict[str, str] = {}
            export_counts: dict[str, dict[str, int]] = {}
            for table in REQUIRED_TABLES:
                export = workspace / "exports" / f"{table}.parquet"
                if not export.is_file():
                    export_errors[table] = "missing export"
                    continue
                serving_count = scalar_int(connection, f'select count(*) from "{table}"')
                export_count = scalar_int(
                    connection,
                    "select count(*) from read_parquet(?)",
                    [str(export)],
                )
                escaped_export = sql_path(export)
                content_delta = scalar_int(
                    connection,
                    f"""select count(*) from (
                      (select * from "{table}" except all
                       select * from read_parquet('{escaped_export}'))
                      union all
                      (select * from read_parquet('{escaped_export}') except all
                       select * from "{table}")
                    )""",
                )
                export_counts[table] = {
                    "serving": serving_count,
                    "parquet": export_count,
                    "contentDelta": content_delta,
                }
                if serving_count != export_count or content_delta:
                    export_errors[table] = "content mismatch"
            findings.append(
                finding(
                    "Parquet exports match serving tables",
                    not export_errors,
                    {"counts": export_counts, "errors": export_errors},
                )
            )
        else:
            for name in (
                "five serving tables exist",
                "every input row is accounted for",
                "frozen Analyst SQL executes",
                "Parquet exports match serving tables",
            ):
                findings.append(finding(name, False, {"missing": str(database)}))
    except Exception as exc:  # Verification must report evidence instead of crashing.
        findings.append(finding("serving database is readable", False, {"error": str(exc)}))
    finally:
        if connection is not None:
            connection.close()

    report = {
        "schemaVersion": 1,
        "accepted": bool(findings) and all(item["pass"] for item in findings),
        "findings": findings,
    }
    if output is not None:
        write_json(output, report)
    return report
