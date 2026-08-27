from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shlex
import shutil
import sys
import tempfile
import time
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from .domain import Arm, AttemptRecord, RunRecord, Usage, sha256_file, write_json
from .paths import active_experiment_id, artifacts_root, repository_root, runs_root
from .verify import verify_candidate
from .workspace import (
    build_prompt,
    candidate_environment,
    prepare_run_workspace,
    repair_prompt,
)

TERRA_MODEL = "gpt-5.6-terra"
QWEN_MODEL = "qwen3.8-27b"
CODEX_BUNDLE_CANDIDATES = (
    Path("/Applications/ChatGPT.app/Contents/Resources/codex"),
    Path.home() / "Applications/ChatGPT.app/Contents/Resources/codex",
    Path("/Applications/Codex.app/Contents/Resources/codex"),
    Path.home() / "Applications/Codex.app/Contents/Resources/codex",
)


def resolve_codex_executable() -> str | None:
    configured = os.environ.get("CODEX_BIN")
    if configured:
        return shutil.which(configured)

    on_path = shutil.which("codex")
    if on_path:
        return on_path

    for candidate in CODEX_BUNDLE_CANDIDATES:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def now() -> str:
    return datetime.now(UTC).isoformat()


def make_run_id(arm: Arm) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{arm}-{uuid.uuid4().hex[:8]}"


def parse_usage(events: str) -> Usage:
    total = Usage()
    for line in events.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or event.get("type") != "turn.completed":
            continue
        usage = event.get("usage")
        if not isinstance(usage, dict):
            continue
        total = total.plus(
            Usage(
                input_tokens=int(usage.get("input_tokens", 0) or 0),
                cached_input_tokens=int(usage.get("cached_input_tokens", 0) or 0),
                output_tokens=int(usage.get("output_tokens", 0) or 0),
            )
        )
    return total


def format_live_event(line: str) -> list[str]:
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return []
    if not isinstance(event, dict):
        return []

    item = event.get("item")
    if isinstance(item, dict):
        item_type = item.get("type")
        event_type = event.get("type")
        if item_type == "agent_message" and event_type == "item.completed":
            text = str(item.get("text", "")).strip()
            return [f"\nCodex: {text}"] if text else []
        if item_type == "todo_list":
            tasks = item.get("items")
            if not isinstance(tasks, list):
                return []
            rendered = ["\nCodex tasks:"]
            for task in tasks:
                if not isinstance(task, dict):
                    continue
                marker = "x" if task.get("completed") else " "
                rendered.append(f"  [{marker}] {task.get('text', '')}")
            return rendered
        if item_type == "command_execution" and event_type == "item.started":
            command = str(item.get("command", "")).strip()
            return [f"\n→ {command}"] if command else []
        if item_type == "command_execution" and event_type == "item.completed":
            output = str(item.get("aggregated_output", "")).rstrip()
            exit_code = item.get("exit_code")
            marker = "✓" if exit_code == 0 else "✗"
            rendered = [output] if output else []
            rendered.append(f"{marker} command exited {exit_code}")
            return rendered
        if item_type == "error" and event_type == "item.completed":
            return [f"\n! {item.get('message', 'Codex reported an error')}"]

    if event.get("type") == "turn.completed":
        usage = event.get("usage")
        if isinstance(usage, dict):
            total = int(usage.get("input_tokens", 0) or 0) + int(
                usage.get("output_tokens", 0) or 0
            )
            return [f"\n✓ Codex turn completed · {total:,} input + output tokens"]
    return []


def command_for(*, model: str, provider: str, workspace: Path, output: Path) -> list[str]:
    configured_codex = os.environ.get("CODEX_BIN", "codex")
    codex = resolve_codex_executable()
    if codex is None:
        raise FileNotFoundError(
            f"Codex CLI {configured_codex!r} was not found; install it or set CODEX_BIN"
        )
    command = [
        codex,
        "--ask-for-approval",
        "never",
        "exec",
        "--json",
        "--ephemeral",
        "--ignore-user-config",
        "--model",
        model,
        "--sandbox",
        "workspace-write",
        "--skip-git-repo-check",
        "--cd",
        str(workspace),
        "--output-last-message",
        str(output),
    ]
    if provider == "lmstudio":
        command.extend(("--oss", "--local-provider", "lmstudio"))
    command.append("-")
    return command


async def invoke_codex(
    *,
    prompt: str,
    model: str,
    provider: str,
    workspace: Path,
    events_file: Path,
    stderr_file: Path,
    final_message_file: Path,
) -> tuple[int, float, Usage]:
    command = command_for(
        model=model, provider=provider, workspace=workspace, output=final_message_file
    )
    request_file = (
        events_file.parent / f"{events_file.name.removesuffix('.events.jsonl')}.request.json"
    )
    write_json(
        request_file,
        {
            "schemaVersion": 1,
            "command": [*command[:-1], "<prompt-via-stdin>"],
            "workingDirectory": str(workspace),
            "model": model,
            "provider": provider,
            "sandbox": "workspace-write",
            "toolchain": {
                "pathPrefix": ".tools/bin",
                "commands": ["dbt", "duckdb", "python"],
                "installers": "disabled",
            },
            "prompt": prompt,
            "promptSha256": hashlib.sha256(prompt.encode()).hexdigest(),
        },
    )
    started = time.monotonic()
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            env=candidate_environment(workspace),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=16 * 1024 * 1024,
        )
    except PermissionError as error:
        raise RuntimeError(
            "The Codex CLI cannot start inside the current macOS sandbox. "
            "Run this command in a normal Terminal window, or launch the outer Codex "
            "orchestrator with --sandbox danger-full-access so it can create the "
            "candidate's nested workspace-write sandbox."
        ) from error
    if process.stdin is None or process.stdout is None or process.stderr is None:
        raise RuntimeError("Codex subprocess streams were not created")
    stdin = process.stdin
    stdout = process.stdout
    stderr = process.stderr

    async def stream_stdout() -> None:
        with events_file.open("wb") as handle:
            while line := await stdout.readline():
                handle.write(line)
                handle.flush()
                for rendered in format_live_event(line.decode("utf-8", errors="replace")):
                    print(rendered, flush=True)

    async def stream_stderr() -> None:
        with stderr_file.open("wb") as handle:
            while chunk := await stderr.read(64 * 1024):
                handle.write(chunk)
                handle.flush()
                sys.stderr.write(chunk.decode("utf-8", errors="replace"))
                sys.stderr.flush()

    print(f"\nStarting Codex · {model} via {provider}\n", flush=True)
    stdout_task = asyncio.create_task(stream_stdout())
    stderr_task = asyncio.create_task(stream_stderr())
    stdin.write(prompt.encode("utf-8"))
    await stdin.drain()
    stdin.close()

    timeout_seconds = float(os.environ.get("CODEX_TIMEOUT_SECONDS", "3600"))
    timed_out = False
    try:
        await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
    except TimeoutError:
        timed_out = True
        process.kill()
        await process.wait()
    await asyncio.gather(stdout_task, stderr_task)
    if timed_out:
        timeout_message = f"\nCodex call timed out after {timeout_seconds:.0f}s\n"
        with stderr_file.open("ab") as handle:
            handle.write(timeout_message.encode())
        sys.stderr.write(timeout_message)
    elapsed = time.monotonic() - started
    return_code = process.returncode
    if return_code is None:
        raise RuntimeError("Codex process ended without a return code")
    if timed_out:
        return_code = 124
    return return_code, elapsed, parse_usage(events_file.read_text(encoding="utf-8"))


def arm_configuration(arm: Arm, root: Path) -> tuple[str, str, Path | None, Path | None, list[str]]:
    distilled = artifacts_root(root) / "distilled-skill" / "taxi-data-product-delivery"
    optimized = artifacts_root(root) / "dspy" / "optimized-program.json"
    if arm == "terra":
        return TERRA_MODEL, "openai", None, None, ["dbt-data-product", "duckdb-analysis"]
    if arm == "qwen-bare":
        return QWEN_MODEL, "lmstudio", None, None, ["dbt-data-product", "duckdb-analysis"]
    if arm == "qwen-skill":
        if not distilled.is_dir():
            raise FileNotFoundError(
                "distilled skill is missing. For the short demo, run "
                "`uv run taxi-demo use-example-skill`. For fresh distillation, run "
                "`uv run taxi-demo teachers --count 3 --parallel 3 --repairs 1`, then "
                "`uv run taxi-demo distill`."
            )
        return (
            QWEN_MODEL,
            "lmstudio",
            distilled,
            None,
            [
                "dbt-data-product",
                "duckdb-analysis",
                "taxi-data-product-delivery",
            ],
        )
    if arm == "qwen-dspy":
        if not optimized.is_file():
            raise FileNotFoundError(
                "optimized DSPy program is missing; run `taxi-demo optimize` first"
            )
        return (
            QWEN_MODEL,
            "lmstudio",
            None,
            optimized,
            [
                "dbt-data-product",
                "duckdb-analysis",
            ],
        )
    if not distilled.is_dir() or not optimized.is_file():
        raise FileNotFoundError("the combined arm requires both distilled skill and DSPy program")
    return (
        QWEN_MODEL,
        "lmstudio",
        distilled,
        optimized,
        [
            "dbt-data-product",
            "duckdb-analysis",
            "taxi-data-product-delivery",
        ],
    )


async def run_arm(
    arm: Arm,
    *,
    root: Path | None = None,
    repairs: int = 1,
    model: str | None = None,
) -> RunRecord:
    repo = root or repository_root()
    configured_model, provider, distilled, optimized, selected_skills = arm_configuration(arm, repo)
    if model is not None and provider != "lmstudio":
        raise ValueError("--model is only supported for Qwen arms routed through LM Studio")
    selected_model = model or configured_model
    run_id = make_run_id(arm)
    run_directory = runs_root(repo) / run_id
    run_directory.mkdir(parents=True)
    temporary_root = Path(tempfile.mkdtemp(prefix=f"codex-taxi-{run_id}-"))
    workspace = temporary_root / "workspace"
    prepare_run_workspace(workspace, distilled_skill=distilled, root=repo)
    input_receipt = run_directory / "input-receipt.json"
    shutil.copy2(workspace / "workspace-receipt.json", input_receipt)
    prompt = build_prompt(use_distilled_skill=distilled is not None)
    started_at = now()
    attempts: list[AttemptRecord] = []

    current_prompt = prompt
    for attempt_number in range(1, repairs + 2):
        events = run_directory / f"attempt-{attempt_number}.events.jsonl"
        stderr = run_directory / f"attempt-{attempt_number}.stderr.log"
        message = run_directory / f"attempt-{attempt_number}.final.md"
        exit_code, elapsed, usage = await invoke_codex(
            prompt=current_prompt,
            model=selected_model,
            provider=provider,
            workspace=workspace,
            events_file=events,
            stderr_file=stderr,
            final_message_file=message,
        )
        verification_path = run_directory / f"attempt-{attempt_number}.verification.json"
        report = verify_candidate(
            workspace,
            output=verification_path,
            expected_receipt=input_receipt,
        )
        snapshot = run_directory / f"attempt-{attempt_number}.workspace"
        shutil.copytree(
            workspace,
            snapshot,
            ignore=shutil.ignore_patterns(".venv", "logs", "*.log"),
        )
        findings = [item for item in report["findings"] if not item["pass"]]
        attempts.append(
            AttemptRecord(
                attempt=attempt_number,
                exit_code=exit_code,
                elapsed_seconds=elapsed,
                usage=usage,
                events_file=events.name,
                final_message_file=message.name,
                verification_file=verification_path.name,
                workspace_snapshot=snapshot.name,
                accepted=bool(report["accepted"]),
                findings=findings,
            )
        )
        if report["accepted"]:
            break
        if attempt_number <= repairs:
            staged_findings = workspace / f"verifier-findings-{attempt_number}.json"
            write_json(staged_findings, report)
            routed_action: str | None = None
            if optimized is not None:
                from .dspy_optimize import route_repair

                decision = route_repair(
                    report,
                    program_path=optimized,
                    call_root=run_directory / f"attempt-{attempt_number}.router" / "calls",
                    qwen_model=selected_model,
                )
                routed_action = str(decision["appliedAction"])
                router_usage = decision.get("usage", {})
                attempts[-1].usage = attempts[-1].usage.plus(
                    Usage(
                        input_tokens=int(router_usage.get("input_tokens", 0)),
                        cached_input_tokens=int(router_usage.get("cached_input_tokens", 0)),
                        output_tokens=int(router_usage.get("output_tokens", 0)),
                    )
                )
                attempts[-1].elapsed_seconds += float(decision.get("elapsedSeconds", 0))
            current_prompt = repair_prompt(
                staged_findings,
                routed_action=routed_action,
            )

    final_workspace = run_directory / "workspace"
    shutil.move(str(workspace), final_workspace)
    shutil.rmtree(temporary_root, ignore_errors=True)
    treatment_artifacts: dict[str, str] = {}
    if optimized is not None:
        treatment_artifacts["dspyProgramSha256"] = sha256_file(optimized)
    if distilled is not None:
        example_receipt = distilled.parent / "example-skill-receipt.json"
        treatment_artifacts["skillOrigin"] = (
            "checked-in-example"
            if example_receipt.is_file()
            else "distilled-in-active-experiment"
        )
        if example_receipt.is_file():
            treatment_artifacts["exampleSkillReceiptSha256"] = sha256_file(example_receipt)

    record = RunRecord(
        schema_version=1,
        experiment_id=active_experiment_id(repo),
        run_id=run_id,
        arm=arm,
        model=selected_model,
        provider=provider,
        started_at=started_at,
        finished_at=now(),
        workspace=str(final_workspace),
        input_receipt_sha256=sha256_file(input_receipt),
        prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
        selected_skills=selected_skills,
        treatment_artifacts=treatment_artifacts,
        attempts=attempts,
        accepted=bool(attempts and attempts[-1].accepted),
    )
    payload = record.as_dict()
    payload["usage"] = asdict(record.usage)
    payload["elapsedSeconds"] = record.elapsed_seconds
    write_json(run_directory / "run.json", payload)
    return record


async def run_parallel_teachers(
    count: int,
    *,
    parallel: int,
    root: Path | None = None,
    repairs: int = 1,
) -> list[RunRecord]:
    if count < 2:
        raise ValueError("skill distillation requires at least two independent teacher runs")
    semaphore = asyncio.Semaphore(max(1, parallel))

    async def bounded() -> RunRecord:
        async with semaphore:
            return await run_arm("terra", root=root, repairs=repairs)

    return await asyncio.gather(*(bounded() for _ in range(count)))


def shell_command(command: list[str]) -> str:
    return " ".join(shlex.quote(value) for value in command)
