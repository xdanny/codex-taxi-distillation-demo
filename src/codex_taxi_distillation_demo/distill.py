from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any

from .codex_runner import TERRA_MODEL, invoke_codex
from .domain import read_json, write_json
from .paths import artifacts_root, repository_root, runs_root

REQUIRED_SKILL_FILES = (
    "SKILL.md",
    "assets/evidence-map.json",
    "assets/release-checklist.md",
    "assets/symptom-to-repair.md",
)

EVIDENCE_WORKSPACE_PATTERNS = (
    "dbt_project.yml",
    "profiles.yml",
    "models/**/*.sql",
    "models/**/*.yml",
    "models/**/*.yaml",
    "tests/**/*.sql",
    "macros/**/*.sql",
    "model-inputs/ANALYST-REQUIREMENT.md",
    "model-inputs/product-contract.json",
    "model-inputs/analyst-questions.sql",
    "model-inputs/review-rubric.md",
)


def accepted_teacher_runs(root: Path | None = None) -> list[Path]:
    repo = root or repository_root()
    accepted: list[Path] = []
    for run_file in sorted(runs_root(repo).glob("*/run.json")):
        record = read_json(run_file)
        if record.get("arm") == "terra" and record.get("accepted") is True:
            accepted.append(run_file.parent)
    return accepted


def collect_evidence(destination: Path, *, root: Path | None = None) -> dict[str, Any]:
    sources = accepted_teacher_runs(root)
    if len(sources) < 2:
        raise RuntimeError("distillation needs at least two accepted Terra teacher runs")
    evidence_root = destination / "evidence"
    evidence_root.mkdir(parents=True)
    index: list[dict[str, Any]] = []
    for source in sources:
        record = read_json(source / "run.json")
        run_id = str(record["run_id"])
        target = evidence_root / run_id
        target.mkdir()
        copied: list[str] = []
        for initial_relative in ("run.json", "workspace/target/run_results.json"):
            source_file = source / initial_relative
            if source_file.is_file():
                destination_file = target / Path(initial_relative).name
                shutil.copy2(source_file, destination_file)
                copied.append(destination_file.name)
        for attempt in record.get("attempts", []):
            if not isinstance(attempt, dict):
                continue
            for key in ("verification_file", "events_file", "final_message_file"):
                relative = attempt.get(key)
                source_file = source / str(relative)
                if source_file.is_file():
                    destination_file = target / source_file.name
                    shutil.copy2(source_file, destination_file)
                    copied.append(destination_file.name)
            snapshot_name = attempt.get("workspace_snapshot")
            snapshot = source / str(snapshot_name)
            if snapshot.is_dir():
                destination_snapshot = target / str(snapshot_name)
                for pattern in EVIDENCE_WORKSPACE_PATTERNS:
                    for source_file in snapshot.glob(pattern):
                        if not source_file.is_file():
                            continue
                        relative = source_file.relative_to(snapshot)
                        destination_file = destination_snapshot / relative
                        destination_file.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source_file, destination_file)
                        copied.append(f"{snapshot_name}/{relative}")
        index.append(
            {
                "runId": run_id,
                "accepted": True,
                "attemptCount": len(record.get("attempts", [])),
                "files": copied,
            }
        )
    payload = {
        "schemaVersion": 1,
        "sourceRunIds": [item["runId"] for item in index],
        "runs": index,
        "claimBoundary": "Source evidence supports procedure extraction, not Qwen transfer.",
    }
    write_json(evidence_root / "index.json", payload)
    return payload


def validate_skill(
    package: Path,
    source_run_ids: list[str],
    *,
    evidence_root: Path | None = None,
) -> dict[str, Any]:
    missing = [relative for relative in REQUIRED_SKILL_FILES if not (package / relative).is_file()]
    errors: list[str] = []
    if missing:
        errors.append(f"missing files: {', '.join(missing)}")

    all_text = ""
    for relative in REQUIRED_SKILL_FILES:
        path = package / relative
        if path.is_file():
            all_text += path.read_text(encoding="utf-8") + "\n"
    if "/Users/" in all_text or "\\Users\\" in all_text:
        errors.append("skill contains a machine-specific absolute path")
    if "transfer is proven" in all_text.lower():
        errors.append("skill makes an unsupported transfer claim")
    if "$dbt-data-product" not in all_text or "$duckdb-analysis" not in all_text:
        errors.append("skill must route implementation to the bundled dbt and DuckDB skills")

    evidence_map_path = package / "assets" / "evidence-map.json"
    procedure_count = 0
    if evidence_map_path.is_file():
        try:
            evidence_map = read_json(evidence_map_path)
            mapped_ids = evidence_map.get("sourceRunIds")
            if sorted(mapped_ids or []) != sorted(source_run_ids):
                errors.append("evidence map does not bind the complete selected source-run set")
            procedures = evidence_map.get("procedures")
            if not isinstance(procedures, list) or not procedures:
                errors.append("evidence map has no reusable procedures")
            else:
                procedure_count = len(procedures)
                for procedure in procedures:
                    if not isinstance(procedure, dict):
                        errors.append("evidence map procedure is not an object")
                        continue
                    bound = procedure.get("sourceRuns")
                    if not isinstance(bound, list) or len(set(bound)) < 2:
                        errors.append("every procedure needs evidence from at least two runs")
                    elif not set(bound).issubset(source_run_ids):
                        errors.append("procedure cites a run outside the selected source set")
                    evidence_files = procedure.get("evidenceFiles")
                    if not isinstance(evidence_files, list) or not evidence_files:
                        errors.append("every procedure needs cited evidence files")
                    else:
                        provenance = evidence_root or package / "assets" / "source-evidence"
                        existing_evidence: list[str] = []
                        for relative in evidence_files:
                            if (provenance / str(relative)).is_file():
                                existing_evidence.append(str(relative))
                            else:
                                errors.append(f"procedure evidence file does not exist: {relative}")
                        if isinstance(bound, list):
                            for run_id in bound:
                                if not any(
                                    relative.startswith(f"{run_id}/")
                                    for relative in existing_evidence
                                ):
                                    errors.append(
                                        f"procedure cites run {run_id} without a file from that run"
                                    )
        except (ValueError, json.JSONDecodeError) as exc:
            errors.append(f"invalid evidence map: {exc}")

    report = {
        "schemaVersion": 1,
        "valid": not errors,
        "errors": errors,
        "sourceRunIds": source_run_ids,
        "procedureCount": procedure_count,
        "transferEstablished": False,
    }
    return report


async def distill_skill(*, root: Path | None = None) -> Path:
    repo = root or repository_root()
    workspace = artifacts_root(repo) / "distillation-workspace"
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)
    index = collect_evidence(workspace, root=repo)
    prompt = """Read evidence/index.json and every copied source artifact. Extract procedures that
are supported by at least two independent accepted Terra runs. Write exactly this package:

output/taxi-data-product-delivery/SKILL.md
output/taxi-data-product-delivery/assets/evidence-map.json
output/taxi-data-product-delivery/assets/release-checklist.md
output/taxi-data-product-delivery/assets/symptom-to-repair.md

The skill must be a portable Codex skill named taxi-data-product-delivery. It must explicitly
invoke $dbt-data-product and $duckdb-analysis. It must explain how to inspect the staged data,
account for every row, build and test dbt, publish DuckDB and Parquet outputs, run frozen Analyst
SQL, and respond to verifier findings. The evidence map must contain sourceRunIds and a procedures
array; every procedure object must contain name, instruction, sourceRuns, and evidenceFiles, with
at least two distinct sourceRuns. Each evidenceFiles entry must be a real file path relative to
the evidence directory, such as RUN_ID/attempt-1.verification.json. Capture repeated repairs only
when the copied evidence shows them. Keep candidate answers, absolute paths, and unsupported
transfer claims out of the package.
Do not write outside output/taxi-data-product-delivery.
"""
    events = workspace / "distillation.events.jsonl"
    message = workspace / "distillation.final.md"
    exit_code, elapsed, usage = await invoke_codex(
        prompt=prompt,
        model=TERRA_MODEL,
        provider="openai",
        workspace=workspace,
        events_file=events,
        stderr_file=workspace / "distillation.stderr.log",
        final_message_file=message,
    )
    package = workspace / "output" / "taxi-data-product-delivery"
    report = validate_skill(
        package,
        list(index["sourceRunIds"]),
        evidence_root=workspace / "evidence",
    )
    report.update(
        {
            "model": TERRA_MODEL,
            "exitCode": exit_code,
            "elapsedSeconds": elapsed,
            "usage": {
                "input_tokens": usage.input_tokens,
                "cached_input_tokens": usage.cached_input_tokens,
                "output_tokens": usage.output_tokens,
            },
        }
    )
    write_json(workspace / "skill-validation.json", report)
    if exit_code != 0 or not report["valid"]:
        raise RuntimeError(f"skill distillation failed: {report['errors']}")

    published = artifacts_root(repo) / "distilled-skill" / "taxi-data-product-delivery"
    if published.exists():
        shutil.rmtree(published)
    published.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(package, published)
    shutil.copy2(workspace / "skill-validation.json", published.parent / "skill-validation.json")
    provenance = published.parent / "provenance" / "source-evidence"
    if provenance.exists():
        shutil.rmtree(provenance)
    provenance.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(workspace / "evidence", provenance)
    return published


def run_distillation(*, root: Path | None = None) -> Path:
    return asyncio.run(distill_skill(root=root))
