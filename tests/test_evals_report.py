from __future__ import annotations

from pathlib import Path

from codex_taxi_distillation_demo.domain import write_json
from codex_taxi_distillation_demo.dspy_optimize import action_for_finding, extract_evals
from codex_taxi_distillation_demo.paths import runs_root
from codex_taxi_distillation_demo.report import build_report


def write_teacher(root: Path, run_id: str, finding_name: str | None = None) -> None:
    run = runs_root(root) / run_id
    run.mkdir(parents=True)
    findings = [] if finding_name is None else [{"name": finding_name, "pass": False}]
    write_json(
        run / "run.json",
        {
            "run_id": run_id,
            "arm": "terra",
            "model": "gpt-5.6-terra",
            "provider": "openai",
            "accepted": True,
            "attempts": [{"findings": findings}],
            "usage": {"input_tokens": 100, "output_tokens": 20},
            "elapsedSeconds": 4.0,
        },
    )


def test_eval_split_is_by_independent_source_run(demo_root: Path) -> None:
    write_teacher(demo_root, "run-a", "dbt build and tests passed")
    write_teacher(demo_root, "run-b", "every input row is accounted for")
    write_teacher(demo_root, "run-c", "frozen Analyst SQL executes")
    split = extract_evals(root=demo_root)
    train_ids = {row["sourceRunId"] for row in split["train"]}
    development_ids = {row["sourceRunId"] for row in split["development"]}
    heldout_ids = {row["sourceRunId"] for row in split["heldout"]}
    assert train_ids.isdisjoint(development_ids | heldout_ids)
    assert development_ids.isdisjoint(heldout_ids)
    assert action_for_finding("frozen Analyst SQL executes") == "repair_analysis"


def test_repair_label_comes_from_observed_file_diff(demo_root: Path) -> None:
    for run_id in ("run-a", "run-b", "run-c"):
        write_teacher(demo_root, run_id)
    run = runs_root(demo_root) / "run-a"
    for attempt, content in ((1, "select 1"), (2, "select 2")):
        models = run / f"attempt-{attempt}.workspace" / "models"
        models.mkdir(parents=True)
        (models / "trip_facts.sql").write_text(content, encoding="utf-8")
    write_json(
        run / "run.json",
        {
            "run_id": "run-a",
            "arm": "terra",
            "accepted": True,
            "attempts": [
                {
                    "accepted": False,
                    "findings": [{"name": "five serving tables exist", "pass": False}],
                    "workspace_snapshot": "attempt-1.workspace",
                },
                {
                    "accepted": True,
                    "findings": [],
                    "workspace_snapshot": "attempt-2.workspace",
                },
            ],
        },
    )

    split = extract_evals(root=demo_root)
    episodes = [row for values in split.values() for row in values]
    transition = next(row for row in episodes if row["kind"] == "observed-repair-transition")
    assert transition["action"] == "repair_dbt"
    assert "models/trip_facts.sql" in transition["observedChangedPaths"]
    assert "observedChangedPaths" not in transition["episode"]


def test_report_keeps_failed_tokens_in_numerator(demo_root: Path) -> None:
    write_teacher(demo_root, "accepted")
    failed = runs_root(demo_root) / "failed"
    failed.mkdir(parents=True)
    write_json(
        failed / "run.json",
        {
            "run_id": "failed",
            "arm": "terra",
            "model": "gpt-5.6-terra",
            "provider": "openai",
            "accepted": False,
            "attempts": [{}, {}],
            "usage": {"input_tokens": 200, "output_tokens": 40},
            "elapsedSeconds": 8.0,
        },
    )
    json_path, markdown_path = build_report(root=demo_root)
    assert json_path.is_file() and markdown_path.is_file()
    content = markdown_path.read_text(encoding="utf-8")
    assert "360" in content
    assert "50%" in content
