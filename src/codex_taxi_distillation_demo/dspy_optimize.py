from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import dspy  # type: ignore[import-untyped]

from .codex_runner import QWEN_MODEL, TERRA_MODEL, command_for, parse_usage
from .domain import read_json, write_json
from .paths import artifacts_root, repository_root, runs_root

ACTIONS = (
    "accept",
    "repair_dbt",
    "repair_row_accounting",
    "repair_serving",
    "repair_analysis",
    "repair_exports",
    "inspect_failure",
)


class CodexLM(dspy.BaseLM):  # type: ignore[misc]
    """DSPy LM adapter that routes every call through the installed Codex CLI."""

    def __init__(self, model: str, *, provider: str, call_root: Path, max_tokens: int = 4000):
        super().__init__(model=model, model_type="chat", max_tokens=max_tokens, cache=False)
        self.provider = provider
        self.call_root = call_root
        self._lock = threading.Lock()
        self._counter = 0

    def forward(
        self,
        prompt: str | None = None,
        messages: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> Any:
        del kwargs
        if messages:
            rendered = "\n\n".join(
                f"{message.get('role', 'user')}: {message.get('content', '')}"
                for message in messages
            )
        else:
            rendered = prompt or ""
        rendered += "\n\nReturn only the response requested by the task format."

        with self._lock:
            self._counter += 1
            call_id = f"{self._counter:04d}-{uuid.uuid4().hex[:8]}"
        workspace = self.call_root / call_id
        workspace.mkdir(parents=True)
        (workspace / ".git").mkdir()
        output = workspace / "final.txt"
        command = command_for(
            model=self.model,
            provider=self.provider,
            workspace=workspace,
            output=output,
        )
        started = time.monotonic()
        completed = subprocess.run(
            command,
            input=rendered,
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ},
            timeout=float(os.environ.get("CODEX_TIMEOUT_SECONDS", "3600")),
        )
        elapsed = time.monotonic() - started
        (workspace / "events.jsonl").write_text(completed.stdout, encoding="utf-8")
        (workspace / "stderr.log").write_text(completed.stderr, encoding="utf-8")
        write_json(
            workspace / "request.json",
            {
                "schemaVersion": 1,
                "model": self.model,
                "provider": self.provider,
                "prompt": rendered,
                "exitCode": completed.returncode,
            },
        )
        if completed.returncode != 0 or not output.is_file():
            raise RuntimeError(
                f"Codex-backed DSPy call failed for {self.model}: {completed.stderr[-1000:]}"
            )
        text = output.read_text(encoding="utf-8").strip()
        usage = parse_usage(completed.stdout)
        write_json(
            workspace / "response.json",
            {
                "schemaVersion": 1,
                "exitCode": completed.returncode,
                "elapsedSeconds": elapsed,
                "usage": {
                    "input_tokens": usage.input_tokens,
                    "cached_input_tokens": usage.cached_input_tokens,
                    "output_tokens": usage.output_tokens,
                },
            },
        )
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=text,
                        reasoning_content=None,
                        tool_calls=None,
                        provider_specific_fields={},
                    ),
                    logprobs=None,
                )
            ],
            usage={
                "prompt_tokens": usage.input_tokens,
                "completion_tokens": usage.output_tokens,
                "total_tokens": usage.total_tokens,
            },
            model=self.model,
            _hidden_params={},
        )


class RepairDecision(dspy.Signature):  # type: ignore[misc]
    """Choose one allowed next action from verifier evidence; prefer the narrowest repair."""

    episode: str = dspy.InputField(desc="Candidate state and verifier findings")
    action: str = dspy.OutputField(desc=f"Exactly one of: {', '.join(ACTIONS)}")


class RepairRouter(dspy.Module):  # type: ignore[misc]
    def __init__(self) -> None:
        super().__init__()
        self.route = dspy.Predict(RepairDecision)

    def forward(self, episode: str) -> dspy.Prediction:
        return self.route(episode=episode)


def action_for_finding(name: str) -> str:
    mapping = {
        "outside dbt build passed": "repair_dbt",
        "dbt build and tests passed": "repair_dbt",
        "every input row is accounted for": "repair_row_accounting",
        "serving rows and metrics match the contract": "repair_serving",
        "five serving tables exist": "repair_serving",
        "frozen Analyst SQL executes": "repair_analysis",
        "Parquet exports match serving tables": "repair_exports",
    }
    return mapping.get(name, "inspect_failure")


def changed_paths(before: Path, after: Path) -> list[str]:
    def inventory(root: Path) -> dict[str, str]:
        values: dict[str, str] = {}
        for path in root.rglob("*"):
            if not path.is_file() or any(
                part in {"target", "logs", ".venv"} for part in path.parts
            ):
                continue
            relative = str(path.relative_to(root))
            if relative.startswith("verifier-findings-"):
                continue
            values[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        return values

    before_files = inventory(before)
    after_files = inventory(after)
    return sorted(
        path
        for path in set(before_files) | set(after_files)
        if before_files.get(path) != after_files.get(path)
    )


def action_for_changed_paths(paths: list[str]) -> str:
    if any(
        path == "dbt_project.yml" or path == "profiles.yml" or path.startswith("models/")
        for path in paths
    ):
        return "repair_dbt"
    if any(path.startswith("exports/") for path in paths):
        return "repair_exports"
    if "serving.duckdb" in paths:
        return "repair_serving"
    return "inspect_failure"


def _episode_payload(failed_findings: list[dict[str, Any]]) -> str:
    return json.dumps(
        {
            "episodeKind": "observed-verifier-result",
            "candidateState": "rejected" if failed_findings else "accepted",
            "failedFindings": failed_findings,
            "policy": "Choose one narrow next action. Do not weaken the verifier.",
        },
        sort_keys=True,
    )


def extract_evals(*, root: Path | None = None) -> dict[str, list[dict[str, str]]]:
    repo = root or repository_root()
    by_run: dict[str, list[dict[str, str]]] = {}
    for run_file in sorted(runs_root(repo).glob("*/run.json")):
        record = read_json(run_file)
        if record.get("arm") != "terra" or record.get("accepted") is not True:
            continue
        run_id = str(record["run_id"])
        episodes: list[dict[str, str]] = []
        attempts = record.get("attempts", [])
        for index, attempt in enumerate(attempts[:-1]):
            if not isinstance(attempt, dict):
                continue
            next_attempt = attempts[index + 1]
            if not isinstance(next_attempt, dict):
                continue
            before = run_file.parent / str(attempt.get("workspace_snapshot", ""))
            after = run_file.parent / str(next_attempt.get("workspace_snapshot", ""))
            if not before.is_dir() or not after.is_dir():
                continue
            paths = changed_paths(before, after)
            failed_findings = [
                finding for finding in attempt.get("findings", []) if isinstance(finding, dict)
            ]
            episodes.append(
                {
                    "episode": _episode_payload(failed_findings),
                    "action": action_for_changed_paths(paths),
                    "sourceRunId": run_id,
                    "kind": "observed-repair-transition",
                    "observedChangedPaths": json.dumps(paths),
                    "nextAttemptAccepted": json.dumps(bool(next_attempt.get("accepted"))),
                }
            )
        episodes.append(
            {
                "episode": _episode_payload([]),
                "action": "accept",
                "sourceRunId": run_id,
                "kind": "observed",
            }
        )
        by_run[run_id] = episodes

    run_ids = sorted(by_run)
    if len(run_ids) < 3:
        raise RuntimeError("DSPy needs at least three accepted, independent Terra candidates")
    repaired_ids = [
        run_id
        for run_id in run_ids
        if any(episode["action"] != "accept" for episode in by_run[run_id])
    ]
    split_order = [run_id for run_id in run_ids if run_id not in repaired_ids] + repaired_ids
    development_id = split_order[-2]
    heldout_id = split_order[-1]
    train_ids = [run_id for run_id in run_ids if run_id not in {development_id, heldout_id}]
    split = {
        "train": [episode for run_id in train_ids for episode in by_run[run_id]],
        "development": by_run[development_id],
        "heldout": by_run[heldout_id],
    }
    output = artifacts_root(repo) / "dspy"
    output.mkdir(parents=True, exist_ok=True)
    write_json(
        output / "evals.json",
        {
            "schemaVersion": 1,
            "splitBySourceRun": {
                "train": train_ids,
                "development": [development_id],
                "heldout": [heldout_id],
            },
            "episodes": split,
            "claimBoundary": (
                "Every episode comes from an observed candidate result. Repair labels describe "
                "changed-file scope between attempts, not a proven causal decision. Held-out "
                "routing scores do not establish accepted-product or economic lift."
            ),
        },
    )
    return split


def metric(
    gold: dspy.Example,
    pred: dspy.Prediction,
    trace: Any = None,
    pred_name: Any = None,
    pred_trace: Any = None,
) -> dspy.Prediction:
    del trace, pred_name, pred_trace
    expected = str(gold.action).strip()
    actual = str(getattr(pred, "action", "")).strip()
    score = 1.0 if actual == expected else 0.0
    feedback = (
        f"Correct narrow action: {expected}."
        if score
        else f"Expected exactly {expected}, but received {actual or '<empty>'}."
    )
    return dspy.Prediction(score=score, feedback=feedback)


def make_examples(values: list[dict[str, str]]) -> list[dspy.Example]:
    return [
        dspy.Example(episode=value["episode"], action=value["action"]).with_inputs("episode")
        for value in values
    ]


def evaluate(program: RepairRouter, examples: list[dspy.Example]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for example in examples:
        prediction = program(episode=example.episode)
        actual = str(prediction.action).strip()
        rows.append(
            {
                "expected": str(example.action),
                "actual": actual,
                "pass": actual == str(example.action),
            }
        )
    return {"score": sum(row["pass"] for row in rows) / len(rows), "rows": rows}


def optimize_prompt(
    *,
    root: Path | None = None,
    max_metric_calls: int = 18,
    qwen_model: str = QWEN_MODEL,
) -> Path:
    repo = root or repository_root()
    output = artifacts_root(repo) / "dspy"
    calls = output / "codex-calls"
    if calls.exists():
        import shutil

        shutil.rmtree(calls)
    calls.mkdir(parents=True)
    split = extract_evals(root=repo)
    train = make_examples(split["train"])
    development = make_examples(split["development"])
    heldout = make_examples(split["heldout"])

    student_lm = CodexLM(qwen_model, provider="lmstudio", call_root=calls / "qwen")
    reflection_lm = CodexLM(TERRA_MODEL, provider="openai", call_root=calls / "terra")
    dspy.configure(lm=student_lm, adapter=dspy.ChatAdapter(), num_threads=1)
    baseline = RepairRouter()
    baseline_result = evaluate(baseline, heldout)

    optimizer = dspy.GEPA(
        metric=metric,
        max_metric_calls=max_metric_calls,
        reflection_lm=reflection_lm,
        reflection_minibatch_size=min(3, len(train)),
        num_threads=1,
        use_merge=False,
        track_stats=True,
        seed=7,
        log_dir=str(output / "gepa-logs"),
    )
    optimized = optimizer.compile(baseline, trainset=train, valset=development)
    optimized_result = evaluate(optimized, heldout)
    instructions = optimized.route.signature.instructions.strip()
    program_path = output / "optimized-program.json"
    optimized.save(program_path)
    prompt_path = output / "optimized-prompt.md"
    prompt_path.write_text(
        "# Optimized verifier-recovery instruction\n\n" + instructions + "\n",
        encoding="utf-8",
    )
    call_receipts = [read_json(path) for path in calls.glob("**/response.json")]
    learning_usage = {
        "calls": len(call_receipts),
        "inputTokens": sum(
            int(receipt.get("usage", {}).get("input_tokens", 0)) for receipt in call_receipts
        ),
        "outputTokens": sum(
            int(receipt.get("usage", {}).get("output_tokens", 0)) for receipt in call_receipts
        ),
        "elapsedSeconds": sum(float(receipt.get("elapsedSeconds", 0)) for receipt in call_receipts),
    }
    write_json(
        output / "optimization.json",
        {
            "schemaVersion": 1,
            "optimizer": "dspy.GEPA",
            "dspyVersion": dspy.__version__,
            "reflectionModel": TERRA_MODEL,
            "studentModel": qwen_model,
            "maxMetricCalls": max_metric_calls,
            "baselineHeldout": baseline_result,
            "optimizedHeldout": optimized_result,
            "heldoutLift": optimized_result["score"] - baseline_result["score"],
            "prompt": instructions,
            "program": str(program_path),
            "learningOverhead": learning_usage,
            "claimBoundary": (
                "This measures held-out verifier-action routing only. Product completion and "
                "economics require separate Qwen arms under the unchanged candidate verifier."
            ),
        },
    )
    return prompt_path


def route_repair(
    findings: dict[str, Any],
    *,
    program_path: Path,
    call_root: Path,
    qwen_model: str = QWEN_MODEL,
) -> dict[str, Any]:
    student_lm = CodexLM(qwen_model, provider="lmstudio", call_root=call_root)
    dspy.configure(lm=student_lm, adapter=dspy.ChatAdapter(), num_threads=1)
    program = RepairRouter()
    program.load(program_path)
    episode = json.dumps(
        {
            "episodeKind": "observed-verifier-result",
            "candidateState": "rejected",
            "failedFindings": [
                item for item in findings.get("findings", []) if not item.get("pass")
            ],
            "policy": "Choose one narrow next action. Do not weaken the verifier.",
        },
        sort_keys=True,
    )
    prediction = str(program(episode=episode).action).strip()
    action = prediction if prediction in ACTIONS and prediction != "accept" else "inspect_failure"
    call_receipts = [read_json(path) for path in call_root.glob("*/response.json")]
    usage = {
        "input_tokens": sum(
            int(receipt.get("usage", {}).get("input_tokens", 0)) for receipt in call_receipts
        ),
        "cached_input_tokens": sum(
            int(receipt.get("usage", {}).get("cached_input_tokens", 0)) for receipt in call_receipts
        ),
        "output_tokens": sum(
            int(receipt.get("usage", {}).get("output_tokens", 0)) for receipt in call_receipts
        ),
    }
    result = {
        "schemaVersion": 1,
        "predictedAction": prediction,
        "appliedAction": action,
        "fallbackApplied": action != prediction,
        "program": str(program_path),
        "usage": usage,
        "elapsedSeconds": sum(float(receipt.get("elapsedSeconds", 0)) for receipt in call_receipts),
    }
    write_json(call_root.parent / "router-decision.json", result)
    return result
