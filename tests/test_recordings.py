from __future__ import annotations

import json
from pathlib import Path

from codex_taxi_distillation_demo.domain import write_json
from codex_taxi_distillation_demo.recordings import (
    build_cast,
    select_demo_run_history,
    select_demo_runs,
)


def _recorded_run(
    root: Path,
    arm: str,
    model: str,
    provider: str,
    *,
    suffix: str = "test",
) -> None:
    run_id = f"20260826-120000-{arm}-{suffix}"
    run = root / ".demo" / "experiments" / "experiment-a" / "runs" / run_id
    run.mkdir(parents=True)
    write_json(
        run / "run.json",
        {
            "run_id": run_id,
            "arm": arm,
            "model": model,
            "provider": provider,
            "accepted": True,
            "elapsedSeconds": 12.5,
            "selected_skills": ["dbt-data-product", "duckdb-analysis"],
            "usage": {"input_tokens": 100, "cached_input_tokens": 80, "output_tokens": 20},
        },
    )
    write_json(
        run / "attempt-1.request.json",
        {"prompt": "Invoke the skills and build the Taxi product.", "sandbox": "workspace-write"},
    )
    write_json(
        run / "attempt-1.verification.json",
        {
            "accepted": True,
            "findings": [
                {
                    "name": "every input row is accounted for",
                    "pass": True,
                    "evidence": {"raw": 300, "accepted": 295, "quarantined": 5},
                }
            ],
        },
    )
    event = {
        "type": "item.completed",
        "item": {
            "type": "command_execution",
            "command": "uv run dbt build --profiles-dir .",
            "aggregated_output": "Completed successfully",
            "exit_code": 0,
        },
    }
    (run / "attempt-1.events.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")
    write_json(run / "input-receipt.json", {"selectedSkills": []})


def test_select_and_build_three_evidence_replays(tmp_path: Path) -> None:
    state = tmp_path / ".demo"
    state.mkdir()
    (state / "active-experiment").write_text("experiment-a\n", encoding="utf-8")
    _recorded_run(tmp_path, "qwen-bare", "qwen3.8-27b", "lmstudio", suffix="a")
    _recorded_run(tmp_path, "qwen-bare", "qwen3.8-27b", "lmstudio", suffix="b")
    _recorded_run(tmp_path, "qwen-skill", "qwen3.8-27b", "lmstudio", suffix="a")
    _recorded_run(tmp_path, "qwen-skill", "qwen3.8-27b", "lmstudio", suffix="b")
    _recorded_run(tmp_path, "terra", "gpt-5.6-terra", "openai")

    demos = select_demo_runs(tmp_path)

    assert [demo.arm for demo in demos] == ["qwen-bare", "qwen-skill", "terra"]
    cast = tmp_path / "bare.cast"
    timing = build_cast(demos[0], cast)
    text = cast.read_text(encoding="utf-8")
    assert timing["sceneCount"] >= 2
    assert "qwen3.8-27b" in text
    assert "every input row is accounted for" in text
    assert "300 raw = 295 accepted + 5 quarantined" in text
    assert len(select_demo_run_history(tmp_path)) == 5
