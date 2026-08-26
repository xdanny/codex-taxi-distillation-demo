from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from codex_taxi_distillation_demo.codex_runner import run_arm, run_parallel_teachers
from codex_taxi_distillation_demo.distill import run_distillation, validate_skill
from codex_taxi_distillation_demo.dspy_optimize import RepairRouter
from codex_taxi_distillation_demo.paths import artifacts_root
from codex_taxi_distillation_demo.report import build_report


def test_skill_validation_requires_repeated_evidence(tmp_path: Path) -> None:
    package = tmp_path / "taxi-data-product-delivery"
    assets = package / "assets"
    assets.mkdir(parents=True)
    (package / "SKILL.md").write_text(
        "---\nname: taxi-data-product-delivery\ndescription: Deliver Taxi data products.\n---\n"
        "Invoke $dbt-data-product and $duckdb-analysis.\n",
        encoding="utf-8",
    )
    (assets / "release-checklist.md").write_text("# Release\n", encoding="utf-8")
    (assets / "symptom-to-repair.md").write_text("# Repairs\n", encoding="utf-8")
    (assets / "evidence-map.json").write_text(
        json.dumps(
            {
                "sourceRunIds": ["one", "two"],
                "procedures": [
                    {
                        "name": "account rows",
                        "instruction": "reconcile raw rows",
                        "sourceRuns": ["one"],
                        "evidenceFiles": ["one/verification.json"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    report = validate_skill(package, ["one", "two"])
    assert report["valid"] is False
    assert "every procedure needs evidence from at least two runs" in report["errors"]


def test_skill_validation_accepts_two_run_procedure(tmp_path: Path) -> None:
    package = tmp_path / "taxi-data-product-delivery"
    assets = package / "assets"
    assets.mkdir(parents=True)
    (package / "SKILL.md").write_text(
        "---\nname: taxi-data-product-delivery\ndescription: Deliver Taxi data products.\n---\n"
        "Invoke $dbt-data-product and $duckdb-analysis.\n",
        encoding="utf-8",
    )
    (assets / "release-checklist.md").write_text("# Release\n", encoding="utf-8")
    (assets / "symptom-to-repair.md").write_text("# Repairs\n", encoding="utf-8")
    evidence = assets / "source-evidence"
    for run_id in ("one", "two"):
        run_evidence = evidence / run_id
        run_evidence.mkdir(parents=True)
        (run_evidence / "verification.json").write_text("{}\n", encoding="utf-8")
    (assets / "evidence-map.json").write_text(
        json.dumps(
            {
                "sourceRunIds": ["one", "two"],
                "procedures": [
                    {
                        "name": "account rows",
                        "instruction": "reconcile raw rows",
                        "sourceRuns": ["one", "two"],
                        "evidenceFiles": ["one/verification.json", "two/verification.json"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    report = validate_skill(package, ["one", "two"])
    assert report["valid"] is True
    (evidence / "two" / "verification.json").unlink()
    missing_coverage = validate_skill(package, ["one", "two"], evidence_root=evidence)
    assert missing_coverage["valid"] is False
    assert any("run two" in error for error in missing_coverage["errors"])


def test_fake_codex_teachers_feed_validated_distillation(
    demo_root: Path, fake_codex: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CODEX_BIN", str(fake_codex))
    teachers = asyncio.run(run_parallel_teachers(3, parallel=3, root=demo_root, repairs=0))
    assert all(record.accepted for record in teachers)

    skill = run_distillation(root=demo_root)

    assert (skill / "SKILL.md").is_file()
    assert not (skill / "assets" / "source-evidence").exists()
    assert (
        artifacts_root(demo_root) / "distilled-skill" / "provenance" / "source-evidence"
    ).is_dir()

    dspy_output = artifacts_root(demo_root) / "dspy"
    dspy_output.mkdir(parents=True)
    RepairRouter().save(dspy_output / "optimized-program.json")

    async def run_treatments() -> list[object]:
        return await asyncio.gather(
            *(
                run_arm(arm, root=demo_root, repairs=0)
                for arm in ("qwen-bare", "qwen-skill", "qwen-dspy", "qwen-both")
            )
        )

    treatments = asyncio.run(run_treatments())
    assert all(record.accepted for record in treatments)
    _, report = build_report(root=demo_root)
    assert report.is_file()
