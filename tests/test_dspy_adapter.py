from __future__ import annotations

import json
import sys
from pathlib import Path

import dspy
import pytest

import codex_taxi_distillation_demo.dspy_optimize as optimization_module
from codex_taxi_distillation_demo.domain import write_json
from codex_taxi_distillation_demo.dspy_optimize import (
    CodexLM,
    RepairRouter,
    optimize_prompt,
    route_repair,
)
from codex_taxi_distillation_demo.paths import artifacts_root, runs_root


def make_fake_lm_codex(path: Path) -> Path:
    path.write_text(
        f"""#!{sys.executable}
import json
import sys
from pathlib import Path

args = sys.argv[1:]
output = Path(args[args.index('--output-last-message') + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text('[[ ## action ## ]]\\naccept\\n[[ ## completed ## ]]\\n')
print(json.dumps({{'type':'turn.completed','usage':{{'input_tokens':10,'output_tokens':4}}}}))
""",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def test_codex_lm_is_usable_by_dspy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = make_fake_lm_codex(tmp_path / "fake-codex-lm")
    monkeypatch.setenv("CODEX_BIN", str(fake))
    lm = CodexLM("qwen3.8-27b", provider="lmstudio", call_root=tmp_path / "calls")
    dspy.configure(lm=lm, adapter=dspy.ChatAdapter(), num_threads=1)

    prediction = RepairRouter()(episode='{"candidateState":"accepted"}')

    assert prediction.action == "accept"
    assert list((tmp_path / "calls").glob("*/response.json"))

    program_path = tmp_path / "optimized-program.json"
    RepairRouter().save(program_path)
    decision = route_repair(
        {"findings": [{"name": "outside dbt build passed", "pass": False}]},
        program_path=program_path,
        call_root=tmp_path / "live-router" / "calls",
        qwen_model="qwen3.6-35b-a3b-ud-mlx",
    )
    assert decision["predictedAction"] == "accept"
    assert decision["appliedAction"] == "inspect_failure"
    assert decision["fallbackApplied"] is True
    assert decision["usage"]["input_tokens"] == 10
    assert decision["usage"]["output_tokens"] == 4
    request = next((tmp_path / "live-router" / "calls").glob("*/request.json"))
    assert json.loads(request.read_text(encoding="utf-8"))["model"] == (
        "qwen3.6-35b-a3b-ud-mlx"
    )


def test_optimize_prompt_publishes_loadable_program_without_synthetic_failures(
    demo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = make_fake_lm_codex(tmp_path / "fake-codex-lm")
    monkeypatch.setenv("CODEX_BIN", str(fake))
    for run_id in ("teacher-a", "teacher-b", "teacher-c"):
        run = runs_root(demo_root) / run_id
        run.mkdir(parents=True)
        write_json(
            run / "run.json",
            {
                "run_id": run_id,
                "arm": "terra",
                "accepted": True,
                "attempts": [{"accepted": True, "findings": []}],
            },
        )

    class FakeGEPA:
        def __init__(self, **_: object) -> None:
            pass

        def compile(self, program: RepairRouter, **_: object) -> RepairRouter:
            return program

    monkeypatch.setattr(optimization_module.dspy, "GEPA", FakeGEPA)

    prompt = optimize_prompt(
        root=demo_root,
        max_metric_calls=8,
        qwen_model="qwen3.6-35b-a3b-ud-mlx",
    )

    program = artifacts_root(demo_root) / "dspy" / "optimized-program.json"
    assert prompt.is_file() and program.is_file()
    RepairRouter().load(program)
    optimization = json.loads(
        (artifacts_root(demo_root) / "dspy" / "optimization.json").read_text(
            encoding="utf-8"
        )
    )
    assert optimization["studentModel"] == "qwen3.6-35b-a3b-ud-mlx"
