from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from codex_taxi_distillation_demo.codex_runner import command_for, parse_usage, run_arm
from codex_taxi_distillation_demo.domain import read_json
from codex_taxi_distillation_demo.dspy_optimize import RepairRouter
from codex_taxi_distillation_demo.paths import artifacts_root, repository_root


def test_qwen_command_uses_exact_lmstudio_route(tmp_path: Path) -> None:
    command = command_for(
        model="qwen3.8-27b",
        provider="lmstudio",
        workspace=tmp_path,
        output=tmp_path / "final.md",
    )
    assert command[command.index("--model") + 1] == "qwen3.8-27b"
    assert command[command.index("--local-provider") + 1] == "lmstudio"
    assert "--oss" in command
    assert command.index("--ask-for-approval") < command.index("exec")


def test_usage_counts_only_completed_turns() -> None:
    events = "\n".join(
        (
            '{"type":"item.completed","usage":{"input_tokens":999}}',
            '{"type":"turn.completed","usage":{"input_tokens":100,"cached_input_tokens":20,"output_tokens":30}}',
        )
    )
    usage = parse_usage(events)
    assert usage.input_tokens == 100
    assert usage.cached_input_tokens == 20
    assert usage.output_tokens == 30


def test_fake_codex_arm_records_accepted_evidence(
    demo_root: Path, fake_codex: Path, monkeypatch: object
) -> None:
    monkeypatch.setenv("CODEX_BIN", str(fake_codex))
    record = asyncio.run(run_arm("terra", root=demo_root, repairs=0))
    assert record.accepted is True
    assert record.usage.total_tokens == 150
    run_directory = Path(record.workspace).parent
    assert (run_directory / "attempt-1.request.json").is_file()
    assert (run_directory / "attempt-1.events.jsonl").is_file()
    request = read_json(run_directory / "attempt-1.request.json")
    assert not Path(str(request["workingDirectory"])).is_relative_to(demo_root)
    assert Path(record.workspace).is_relative_to(run_directory)


def test_dspy_router_usage_is_charged_to_repaired_run(
    demo_root: Path, tmp_path: Path, monkeypatch: object
) -> None:
    program_dir = artifacts_root(demo_root) / "dspy"
    program_dir.mkdir(parents=True)
    RepairRouter().save(program_dir / "optimized-program.json")
    fake = tmp_path / "fake-repair-codex"
    fake.write_text(
        f"""#!{sys.executable}
import json
import sys
from pathlib import Path
sys.path.insert(0, {str(repository_root())!r})
from tests.conftest import make_valid_candidate

args = sys.argv[1:]
workspace = Path(args[args.index('--cd') + 1])
output = Path(args[args.index('--output-last-message') + 1])
prompt = sys.stdin.read()
output.parent.mkdir(parents=True, exist_ok=True)
if '[[ ## episode ## ]]' in prompt:
    output.write_text('[[ ## action ## ]]\\nrepair_dbt\\n[[ ## completed ## ]]\\n')
    usage = {{'input_tokens': 10, 'output_tokens': 4}}
elif (workspace / 'verifier-findings-1.json').is_file():
    make_valid_candidate(workspace)
    output.write_text('repaired\\n')
    usage = {{'input_tokens': 120, 'output_tokens': 30}}
else:
    output.write_text('incomplete\\n')
    usage = {{'input_tokens': 100, 'output_tokens': 10}}
print(json.dumps({{'type': 'turn.completed', 'usage': usage}}))
""",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    monkeypatch.setenv("CODEX_BIN", str(fake))

    record = asyncio.run(run_arm("qwen-dspy", root=demo_root, repairs=1))

    assert record.accepted is True
    assert record.usage.input_tokens == 230
    assert record.usage.output_tokens == 44
    assert (Path(record.workspace).parent / "attempt-1.router" / "router-decision.json").is_file()
