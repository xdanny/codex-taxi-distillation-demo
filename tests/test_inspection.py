from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from codex_taxi_distillation_demo.domain import write_json
from codex_taxi_distillation_demo.inspection import (
    list_experiments,
    list_runs,
    query_iceberg,
    query_run,
    resolve_example_workspace,
    resolve_run_workspace,
)
from codex_taxi_distillation_demo.paths import active_experiment_id, experiment_root


def create_completed_run(root: Path, run_id: str = "20260826-120000-qwen-bare-test") -> Path:
    run = experiment_root(root) / "runs" / run_id
    workspace = run / "workspace"
    workspace.mkdir(parents=True)
    connection = duckdb.connect(str(workspace / "serving.duckdb"))
    connection.execute("create table trip_facts as select 1 as trip_id, 12.5 as revenue")
    connection.close()
    write_json(
        run / "run.json",
        {
            "accepted": True,
            "arm": "qwen-bare",
            "attempts": [{"attempt": 1}],
            "elapsedSeconds": 2.5,
            "model": "qwen3.8-27b",
            "usage": {"input_tokens": 100, "output_tokens": 20},
        },
    )
    return run


def test_lists_experiments_and_completed_runs(demo_root: Path) -> None:
    create_completed_run(demo_root)
    interrupted = experiment_root(demo_root) / "runs" / "20260826-120001-qwen-skill-test"
    interrupted.mkdir(parents=True)
    write_json(interrupted / "attempt-1.request.json", {"model": "qwen3.8-27b"})

    experiments = list_experiments(demo_root)
    assert len(experiments) == 1
    assert experiments[0].experiment_id == active_experiment_id(demo_root)
    assert experiments[0].completed_runs == 1
    assert experiments[0].accepted_runs == 1
    assert experiments[0].interrupted_runs == 1

    runs = list_runs(demo_root)
    assert [(run.arm, run.status) for run in runs] == [
        ("qwen-bare", "accepted"),
        ("qwen-skill", "interrupted"),
    ]
    assert runs[0].total_tokens == 120
    assert runs[1].attempts == 1


def test_resolves_latest_run_and_executes_read_queries(demo_root: Path) -> None:
    run = create_completed_run(demo_root)
    selected, workspace = resolve_run_workspace(demo_root)
    assert selected == run.name

    results = query_run(workspace, "show tables; select * from trip_facts", max_rows=10)
    assert len(results) == 2
    assert results[1].columns == ("trip_id", "revenue")
    assert results[1].rows == ((1, 12.5),)


def test_query_rejects_writes_and_run_path_escape(demo_root: Path) -> None:
    create_completed_run(demo_root)
    _, workspace = resolve_run_workspace(demo_root)
    with pytest.raises(ValueError, match="only read queries"):
        query_run(workspace, "copy (select 1) to '/tmp/not-allowed.parquet'")
    with pytest.raises(FileNotFoundError, match="run does not exist"):
        resolve_run_workspace(demo_root, run_id="../outside")
    with pytest.raises(ValueError, match=r"must contain the \{table\} placeholder"):
        query_iceberg("s3://example/table", "select 1")


def test_repository_example_resolves_and_is_queryable(demo_root: Path) -> None:
    example = demo_root / "examples" / "terra"
    example.mkdir(parents=True)
    (example / "dbt_project.yml").write_text("name: example\n", encoding="utf-8")
    database = duckdb.connect(str(example / "serving.duckdb"))
    database.execute("create table metrics as select 7 as trip_count")
    database.close()

    workspace = resolve_example_workspace(demo_root, "terra")
    result = query_run(workspace, "select trip_count from metrics")

    assert result[0].rows == ((7,),)
