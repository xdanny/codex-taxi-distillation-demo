from __future__ import annotations

import subprocess
from pathlib import Path

import duckdb

from codex_taxi_distillation_demo.fixture import prepare_fixture
from codex_taxi_distillation_demo.paths import runs_root, start_experiment
from codex_taxi_distillation_demo.workspace import (
    build_prompt,
    candidate_environment,
    prepare_run_workspace,
)


def test_fixture_is_deterministic_and_has_1000_rows(demo_root: Path) -> None:
    first = prepare_fixture(demo_root)
    first_bytes = (first / "dataset-manifest.json").read_bytes()
    second = prepare_fixture(demo_root, force=True)
    assert first_bytes != b""
    count = (
        duckdb.connect()
        .execute("select count(*) from read_parquet(?)", [str(second / "taxi_trips.parquet")])
        .fetchone()[0]
    )
    assert count == 1_000


def test_workspace_receipt_exposes_selected_skills(demo_root: Path, tmp_path: Path) -> None:
    workspace = tmp_path / "candidate"
    receipt = prepare_run_workspace(workspace, root=demo_root)
    assert receipt["selectedSkills"] == ["dbt-data-product", "duckdb-analysis"]
    assert (workspace / ".codex/skills/dbt-data-product/SKILL.md").is_file()
    assert "$dbt-data-product" in build_prompt(use_distilled_skill=False)
    assert (workspace / "src" / "codex_taxi_distillation_demo" / "__init__.py").is_file()
    assert (workspace / "src" / "codex_taxi_distillation_demo" / "cli.py").is_file()
    assert "src/codex_taxi_distillation_demo/cli.py" in receipt["files"]


def test_candidate_has_preprovisioned_dbt_and_duckdb_tools(
    demo_root: Path, tmp_path: Path
) -> None:
    workspace = tmp_path / "candidate"
    prepare_run_workspace(workspace, root=demo_root)
    environment = candidate_environment(workspace)

    dbt = subprocess.run(
        ["dbt", "--version"],
        cwd=workspace,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    python = subprocess.run(
        ["python", "-c", "import duckdb; print(duckdb.__version__)"],
        cwd=workspace,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    duckdb_cli = subprocess.run(
        ["duckdb", "--version"],
        cwd=workspace,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    installer = subprocess.run(
        ["uv", "sync"],
        cwd=workspace,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert dbt.returncode == 0, dbt.stderr
    assert "installed:" in dbt.stdout
    assert python.returncode == 0, python.stderr
    assert python.stdout.strip()
    assert duckdb_cli.returncode == 0, duckdb_cli.stderr
    assert duckdb_cli.stdout.strip()
    assert installer.returncode == 2
    assert "already available" in installer.stderr
    prompt = build_prompt(use_distilled_skill=False)
    assert "run `dbt`, `python`, and `duckdb` directly" in prompt
    assert "Do not run uv or pip" in prompt


def test_start_experiment_selects_a_fresh_cohort(demo_root: Path) -> None:
    first_runs = runs_root(demo_root)
    second_id = start_experiment(demo_root)
    second_runs = runs_root(demo_root)

    assert second_runs != first_runs
    assert second_id in second_runs.parts
