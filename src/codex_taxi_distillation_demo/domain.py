from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

Arm = Literal["terra", "qwen-bare", "qwen-skill", "qwen-dspy", "qwen-both"]
Example = Literal["terra", "qwen-skill"]


def json_default(value: object) -> str | float:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=json_default,
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=json_default) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected an object in {path}")
    return value


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def plus(self, other: Usage) -> Usage:
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            cached_input_tokens=self.cached_input_tokens + other.cached_input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )


@dataclass
class AttemptRecord:
    attempt: int
    exit_code: int
    elapsed_seconds: float
    usage: Usage
    events_file: str
    final_message_file: str
    verification_file: str
    workspace_snapshot: str
    accepted: bool
    findings: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RunRecord:
    schema_version: int
    experiment_id: str
    run_id: str
    arm: Arm
    model: str
    provider: str
    started_at: str
    finished_at: str
    workspace: str
    input_receipt_sha256: str
    prompt_sha256: str
    selected_skills: list[str]
    treatment_artifacts: dict[str, str]
    attempts: list[AttemptRecord]
    accepted: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def usage(self) -> Usage:
        total = Usage()
        for attempt in self.attempts:
            total = total.plus(attempt.usage)
        return total

    @property
    def elapsed_seconds(self) -> float:
        return sum(attempt.elapsed_seconds for attempt in self.attempts)
