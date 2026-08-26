from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from .domain import read_json
from .paths import active_experiment_id, state_root


@dataclass(frozen=True)
class ExperimentInfo:
    experiment_id: str
    active: bool
    started_at: str
    completed_runs: int
    accepted_runs: int
    interrupted_runs: int
    report_exists: bool


@dataclass(frozen=True)
class RunInfo:
    run_id: str
    arm: str
    model: str
    status: str
    attempts: int
    total_tokens: int
    elapsed_seconds: float


@dataclass(frozen=True)
class QueryResult:
    statement: str
    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    truncated: bool


def _selected_experiment(root: Path, experiment_id: str | None) -> tuple[str, Path]:
    selected = experiment_id or active_experiment_id(root)
    experiments = (state_root(root) / "experiments").resolve()
    experiment = (experiments / selected).resolve()
    if experiment.parent != experiments or not experiment.is_dir():
        raise FileNotFoundError(f"experiment does not exist: {selected}")
    return selected, experiment


def _usage_tokens(record: dict[str, Any]) -> int:
    usage = record.get("usage")
    if not isinstance(usage, dict):
        return 0
    return int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0))


def _infer_arm(run_id: str) -> str:
    for arm in ("qwen-skill", "qwen-dspy", "qwen-both", "qwen-bare", "terra"):
        if f"-{arm}-" in run_id:
            return arm
    return "unknown"


def list_experiments(root: Path) -> list[ExperimentInfo]:
    experiments = state_root(root) / "experiments"
    if not experiments.is_dir():
        return []
    try:
        active = active_experiment_id(root)
    except RuntimeError:
        active = ""
    results: list[ExperimentInfo] = []
    for experiment in sorted(experiments.iterdir(), reverse=True):
        metadata_path = experiment / "experiment.json"
        if not experiment.is_dir() or not metadata_path.is_file():
            continue
        metadata = read_json(metadata_path)
        run_directories = [path for path in (experiment / "runs").glob("*") if path.is_dir()]
        completed = [path for path in run_directories if (path / "run.json").is_file()]
        accepted = sum(read_json(path / "run.json").get("accepted") is True for path in completed)
        results.append(
            ExperimentInfo(
                experiment_id=experiment.name,
                active=experiment.name == active,
                started_at=str(metadata.get("startedAt", "")),
                completed_runs=len(completed),
                accepted_runs=accepted,
                interrupted_runs=len(run_directories) - len(completed),
                report_exists=(experiment / "artifacts" / "report" / "comparison.json").is_file(),
            )
        )
    return results


def list_runs(root: Path, experiment_id: str | None = None) -> list[RunInfo]:
    _, experiment = _selected_experiment(root, experiment_id)
    results: list[RunInfo] = []
    for run_directory in sorted((experiment / "runs").glob("*")):
        if not run_directory.is_dir():
            continue
        record_path = run_directory / "run.json"
        if not record_path.is_file():
            request_path = run_directory / "attempt-1.request.json"
            request = read_json(request_path) if request_path.is_file() else {}
            attempted_requests = len(list(run_directory.glob("attempt-*.request.json")))
            results.append(
                RunInfo(
                    run_id=run_directory.name,
                    arm=_infer_arm(run_directory.name),
                    model=str(request.get("model", "")),
                    status="interrupted",
                    attempts=attempted_requests,
                    total_tokens=0,
                    elapsed_seconds=0,
                )
            )
            continue
        record = read_json(record_path)
        attempts = record.get("attempts")
        results.append(
            RunInfo(
                run_id=run_directory.name,
                arm=str(record.get("arm", "unknown")),
                model=str(record.get("model", "")),
                status="accepted" if record.get("accepted") is True else "failed",
                attempts=len(attempts) if isinstance(attempts, list) else 0,
                total_tokens=_usage_tokens(record),
                elapsed_seconds=float(record.get("elapsedSeconds", 0)),
            )
        )
    return results


def resolve_run_workspace(
    root: Path,
    *,
    run_id: str | None = None,
    experiment_id: str | None = None,
) -> tuple[str, Path]:
    _, experiment = _selected_experiment(root, experiment_id)
    runs = (experiment / "runs").resolve()
    if run_id is None:
        completed = sorted(
            path.parent
            for path in runs.glob("*/run.json")
            if path.parent.is_dir()
            and read_json(path).get("accepted") is True
            and (path.parent / "workspace" / "serving.duckdb").is_file()
        )
        if not completed:
            raise FileNotFoundError("the selected experiment has no accepted queryable runs")
        run_directory = completed[-1]
    else:
        run_directory = (runs / run_id).resolve()
        if run_directory.parent != runs:
            raise FileNotFoundError(f"run does not exist: {run_id}")
    record = run_directory / "run.json"
    workspace = run_directory / "workspace"
    database = workspace / "serving.duckdb"
    if not record.is_file():
        raise FileNotFoundError(f"run is not complete: {run_directory.name}")
    if not database.is_file():
        raise FileNotFoundError(f"run has no serving database: {run_directory.name}")
    return run_directory.name, workspace


def _execute_read_queries(
    connection: duckdb.DuckDBPyConnection,
    sql: str,
    *,
    max_rows: int,
) -> list[QueryResult]:
    statements = connection.extract_statements(sql)
    if not statements:
        raise ValueError("query is empty")
    results: list[QueryResult] = []
    for statement in statements:
        if statement.type.name not in {"SELECT", "EXPLAIN"}:
            raise ValueError(f"only read queries are allowed; received {statement.type.name}")
        cursor = connection.execute(statement.query)
        columns = tuple(item[0] for item in (cursor.description or []))
        fetched = cursor.fetchmany(max_rows + 1)
        results.append(
            QueryResult(
                statement=statement.query.strip(),
                columns=columns,
                rows=tuple(tuple(row) for row in fetched[:max_rows]),
                truncated=len(fetched) > max_rows,
            )
        )
    return results


def query_run(workspace: Path, sql: str, *, max_rows: int = 100) -> list[QueryResult]:
    connection = duckdb.connect(str(workspace / "serving.duckdb"), read_only=True)
    try:
        return _execute_read_queries(connection, sql, max_rows=max_rows)
    finally:
        connection.close()


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def query_iceberg(
    table: str,
    sql_template: str,
    *,
    max_rows: int = 100,
) -> list[QueryResult]:
    if "{table}" not in sql_template:
        raise ValueError("Iceberg SQL must contain the {table} placeholder")
    table_function = (
        f"iceberg_scan({_sql_literal(table)}, allow_moved_paths = true)"
    )
    sql = sql_template.replace("{table}", table_function)
    connection = duckdb.connect()
    try:
        connection.execute("install iceberg")
        connection.execute("load iceberg")
        return _execute_read_queries(connection, sql, max_rows=max_rows)
    finally:
        connection.close()
