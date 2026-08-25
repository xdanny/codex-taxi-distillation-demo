from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def state_root(root: Path | None = None) -> Path:
    return (root or repository_root()) / ".demo"


def start_experiment(root: Path | None = None) -> str:
    repo = root or repository_root()
    experiment_id = f"{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    experiment = state_root(repo) / "experiments" / experiment_id
    experiment.mkdir(parents=True)
    contract_digest = hashlib.sha256()
    for path in sorted((repo / "contracts").glob("*")):
        if path.is_file():
            contract_digest.update(path.name.encode())
            contract_digest.update(path.read_bytes())
    verifier = repo / "src" / "codex_taxi_distillation_demo" / "verify.py"
    if not verifier.is_file():
        verifier = Path(__file__).with_name("verify.py")
    metadata = {
        "schemaVersion": 1,
        "experimentId": experiment_id,
        "startedAt": datetime.now(UTC).isoformat(),
        "contractSha256": contract_digest.hexdigest(),
        "verifierSha256": hashlib.sha256(verifier.read_bytes()).hexdigest(),
    }
    (experiment / "experiment.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    active = state_root(repo) / "active-experiment"
    active.parent.mkdir(parents=True, exist_ok=True)
    active.write_text(experiment_id + "\n", encoding="utf-8")
    return experiment_id


def active_experiment_id(root: Path | None = None) -> str:
    active = state_root(root) / "active-experiment"
    if not active.is_file() or not active.read_text(encoding="utf-8").strip():
        raise RuntimeError("no active experiment; run `taxi-demo start` first")
    return active.read_text(encoding="utf-8").strip()


def experiment_root(root: Path | None = None) -> Path:
    repo = root or repository_root()
    return state_root(repo) / "experiments" / active_experiment_id(repo)


def runs_root(root: Path | None = None) -> Path:
    return experiment_root(root) / "runs"


def artifacts_root(root: Path | None = None) -> Path:
    return experiment_root(root) / "artifacts"
