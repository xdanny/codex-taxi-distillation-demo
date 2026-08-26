from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import duckdb

from codex_taxi_distillation_demo.fixture import prepare_fixture
from codex_taxi_distillation_demo.verify import verify_candidate
from codex_taxi_distillation_demo.workspace import prepare_run_workspace

from .conftest import make_valid_candidate


def test_valid_candidate_passes(demo_root: Path, tmp_path: Path) -> None:
    prepare_fixture(demo_root)
    workspace = tmp_path / "candidate"
    prepare_run_workspace(workspace, root=demo_root)
    make_valid_candidate(workspace)
    report = verify_candidate(workspace)
    assert report["accepted"] is True
    assert all(item["pass"] for item in report["findings"])


def test_same_size_but_changed_export_fails(demo_root: Path, tmp_path: Path) -> None:
    workspace = tmp_path / "candidate"
    prepare_run_workspace(workspace, root=demo_root)
    make_valid_candidate(workspace)
    export = workspace / "exports" / "hourly_zone_metrics.parquet"
    connection = duckdb.connect()
    connection.execute("create table altered as select * from read_parquet(?)", [str(export)])
    connection.execute("update altered set total_revenue = total_revenue + 1 where rowid = 0")
    connection.execute("copy altered to ? (format parquet, overwrite true)", [str(export)])
    connection.close()

    report = verify_candidate(workspace)

    exports = next(
        item
        for item in report["findings"]
        if item["name"] == "Parquet exports match serving tables"
    )
    assert exports["pass"] is False


def test_decimal_revenue_is_cent_equivalent(demo_root: Path, tmp_path: Path) -> None:
    workspace = tmp_path / "candidate"
    prepare_run_workspace(workspace, root=demo_root)
    make_valid_candidate(workspace)
    model = workspace / "models" / "hourly_zone_metrics.sql"
    model.write_text(
        model.read_text().replace(
            "sum(total_revenue) as total_revenue",
            "cast(round(sum(total_revenue), 2) as decimal(38, 2)) as total_revenue",
        )
    )
    subprocess.run(
        [shutil.which("dbt") or "dbt", "build", "--project-dir", str(workspace),
         "--profiles-dir", str(workspace)],
        cwd=workspace, check=True, capture_output=True, text=True,
    )
    database = workspace / "serving.duckdb"
    export = workspace / "exports" / "hourly_zone_metrics.parquet"
    connection = duckdb.connect(str(database))
    connection.execute(
        "copy hourly_zone_metrics to ? (format parquet, overwrite true)",
        [str(export)],
    )
    connection.close()
    assert verify_candidate(workspace)["accepted"] is True


def test_missing_serving_database_fails_with_findings(demo_root: Path, tmp_path: Path) -> None:
    prepare_fixture(demo_root)
    workspace = tmp_path / "candidate"
    prepare_run_workspace(workspace, root=demo_root)
    report = verify_candidate(workspace)
    assert report["accepted"] is False
    assert any(item["name"] == "five serving tables exist" for item in report["findings"])


def test_changed_staged_input_fails_against_external_receipt(
    demo_root: Path, tmp_path: Path
) -> None:
    workspace = tmp_path / "candidate"
    prepare_run_workspace(workspace, root=demo_root)
    expected_receipt = tmp_path / "input-receipt.json"
    shutil.copy2(workspace / "workspace-receipt.json", expected_receipt)
    make_valid_candidate(workspace)
    requirement = workspace / "model-inputs" / "ANALYST-REQUIREMENT.md"
    requirement.write_text("changed\n", encoding="utf-8")

    report = verify_candidate(workspace, expected_receipt=expected_receipt)

    assert report["accepted"] is False
    immutable = next(
        item
        for item in report["findings"]
        if item["name"] == "staged inputs and skills are unchanged"
    )
    assert immutable["evidence"]["changed"] == ["model-inputs/ANALYST-REQUIREMENT.md"]


def test_wrong_taxi_logic_fails_semantic_oracle(demo_root: Path, tmp_path: Path) -> None:
    workspace = tmp_path / "candidate"
    prepare_run_workspace(workspace, root=demo_root)
    make_valid_candidate(workspace)
    model = workspace / "models" / "trip_facts.sql"
    model.write_text(
        model.read_text(encoding="utf-8") + "\nand trip_id < 295\n",
        encoding="utf-8",
    )

    report = verify_candidate(workspace)

    assert report["accepted"] is False
    semantics = next(
        item
        for item in report["findings"]
        if item["name"] == "serving rows and metrics match the contract"
    )
    assert semantics["pass"] is False
