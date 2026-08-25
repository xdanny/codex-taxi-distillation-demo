from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from .domain import read_json, write_json
from .paths import artifacts_root, repository_root, runs_root


def build_report(*, root: Path | None = None) -> tuple[Path, Path]:
    repo = root or repository_root()
    rows: list[dict[str, Any]] = []
    for run_file in sorted(runs_root(repo).glob("*/run.json")):
        record = read_json(run_file)
        usage = record.get("usage", {})
        input_tokens = int(usage.get("input_tokens", 0) or 0)
        output_tokens = int(usage.get("output_tokens", 0) or 0)
        accepted = bool(record.get("accepted"))
        rows.append(
            {
                "runId": record.get("run_id"),
                "arm": record.get("arm"),
                "model": record.get("model"),
                "provider": record.get("provider"),
                "accepted": accepted,
                "attempts": len(record.get("attempts", [])),
                "inputTokens": input_tokens,
                "outputTokens": output_tokens,
                "totalTokens": input_tokens + output_tokens,
                "elapsedSeconds": float(record.get("elapsedSeconds", 0.0) or 0.0),
                "tokensPerAcceptedTask": input_tokens + output_tokens if accepted else None,
                "monetaryExpense": None,
            }
        )

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["arm"])].append(row)
    arms: list[dict[str, Any]] = []
    for arm, arm_rows in sorted(grouped.items()):
        accepted_count = sum(bool(row["accepted"]) for row in arm_rows)
        total_tokens = sum(int(row["totalTokens"]) for row in arm_rows)
        total_elapsed = sum(float(row["elapsedSeconds"]) for row in arm_rows)
        arms.append(
            {
                "arm": arm,
                "runs": len(arm_rows),
                "accepted": accepted_count,
                "completionRate": accepted_count / len(arm_rows),
                "totalTokens": total_tokens,
                "totalElapsedSeconds": total_elapsed,
                "tokensPerAcceptedTask": (
                    total_tokens / accepted_count if accepted_count else None
                ),
                "expensePerAcceptedTask": None,
            }
        )

    output = artifacts_root(repo) / "report"
    output.mkdir(parents=True, exist_ok=True)
    learning: dict[str, Any] = {}
    skill_validation = artifacts_root(repo) / "distilled-skill" / "skill-validation.json"
    if skill_validation.is_file():
        validation = read_json(skill_validation)
        usage = validation.get("usage", {})
        learning["skillDistillation"] = {
            "inputTokens": int(usage.get("input_tokens", 0)),
            "outputTokens": int(usage.get("output_tokens", 0)),
            "elapsedSeconds": float(validation.get("elapsedSeconds", 0)),
        }
    optimization_file = artifacts_root(repo) / "dspy" / "optimization.json"
    if optimization_file.is_file():
        learning["dspyOptimization"] = read_json(optimization_file).get("learningOverhead", {})
    json_path = output / "comparison.json"
    write_json(
        json_path,
        {
            "schemaVersion": 1,
            "runs": rows,
            "arms": arms,
            "learningOverhead": learning,
            "economicUnit": "expense per accepted workflow task",
            "claimBoundary": (
                "Provider bills, local hardware, energy, and human-review receipts are "
                "not inferred. "
                "Monetary expense remains unknown until those receipts are supplied."
            ),
        },
    )

    lines = [
        "# Taxi demo comparison",
        "",
        "The unit is one accepted workflow task. Failed attempts keep their tokens and",
        "elapsed time in the numerator and contribute no accepted product.",
        "",
        "| Arm | Runs | Accepted | Completion | Tokens | Tokens / accepted task | Elapsed |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for arm_summary in arms:
        per_accepted = arm_summary["tokensPerAcceptedTask"]
        template = (
            "| {arm} | {runs} | {accepted} | {completion:.0%} | {tokens:,} | "
            "{per} | {elapsed:.1f}s |"
        )
        lines.append(
            template.format(
                arm=arm_summary["arm"],
                runs=arm_summary["runs"],
                accepted=arm_summary["accepted"],
                completion=arm_summary["completionRate"],
                tokens=arm_summary["totalTokens"],
                per=f"{per_accepted:,.0f}" if per_accepted is not None else "n/a",
                elapsed=arm_summary["totalElapsedSeconds"],
            )
        )
    lines.extend(
        (
            "",
            "Learning overhead is reported separately and is not silently amortized into a",
            "single treatment run. See comparison.json for skill-distillation and DSPy totals.",
            "",
            "Monetary expense is intentionally blank until hosted charges, local compute, energy,",
            "maintenance, concurrency, and human-review receipts are available.",
        )
    )
    markdown_path = output / "comparison.md"
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, markdown_path
