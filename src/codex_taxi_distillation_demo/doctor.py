from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

from .codex_runner import QWEN_MODEL, resolve_codex_executable
from .paths import repository_root


def command_version(command: list[str]) -> dict[str, Any]:
    executable = shutil.which(command[0])
    if executable is None:
        return {"pass": False, "command": command[0], "error": "not found on PATH"}
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    output = (completed.stdout or completed.stderr).strip().splitlines()
    return {
        "pass": completed.returncode == 0,
        "command": command[0],
        "path": executable,
        "version": output[0] if output else "unknown",
        "exitCode": completed.returncode,
    }


def lmstudio_check(model: str = QWEN_MODEL) -> dict[str, Any]:
    base = os.environ.get("LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1").rstrip("/")
    try:
        with urllib.request.urlopen(f"{base}/models", timeout=5) as response:
            payload = json.load(response)
        ids = [item.get("id") for item in payload.get("data", []) if isinstance(item, dict)]
        matching = [
            model_id
            for model_id in ids
            if isinstance(model_id, str)
            and (model_id == model or model_id.endswith(f"/{model}"))
        ]
        return {
            "pass": bool(matching),
            "endpoint": base,
            "expectedModel": model,
            "loadedModelIds": ids,
            "matchingModelIds": matching,
        }
    except Exception as exc:
        return {
            "pass": False,
            "endpoint": base,
            "expectedModel": model,
            "error": str(exc),
        }


def codex_auth_check(codex: str | None) -> dict[str, Any]:
    if codex is None:
        return {"pass": False, "command": "codex login status", "error": "Codex not found"}
    completed = subprocess.run(
        [codex, "login", "status"], text=True, capture_output=True, check=False
    )
    output = (completed.stdout or completed.stderr).strip()
    return {
        "pass": completed.returncode == 0,
        "command": "codex login status",
        "status": output or "unknown",
        "exitCode": completed.returncode,
    }


def candidate_toolchain_check() -> dict[str, Any]:
    python = Path(sys.executable)
    dbt = python.parent / "dbt"
    python_result = subprocess.run(
        [str(python), "-c", "import duckdb; print(duckdb.__version__)"],
        text=True,
        capture_output=True,
        check=False,
    )
    dbt_result = subprocess.run(
        [str(dbt), "--version"], text=True, capture_output=True, check=False
    ) if dbt.is_file() else None
    return {
        "pass": python_result.returncode == 0
        and dbt_result is not None
        and dbt_result.returncode == 0,
        "python": str(python),
        "duckdbVersion": python_result.stdout.strip() or None,
        "duckdbError": python_result.stderr.strip() or None,
        "dbt": str(dbt),
        "dbtAvailable": dbt_result is not None and dbt_result.returncode == 0,
        "dbtError": dbt_result.stderr.strip() if dbt_result is not None else "not found",
    }


def run_doctor(root: Path | None = None, *, model: str = QWEN_MODEL) -> dict[str, Any]:
    repo = root or repository_root()
    codex = resolve_codex_executable()
    checks = {
        "uv": command_version(["uv", "--version"]),
        "codex": (
            command_version([codex, "--version"])
            if codex is not None
            else {
                "pass": False,
                "command": "codex",
                "error": "not found on PATH or in an app bundle",
            }
        ),
        "codexAuth": codex_auth_check(codex),
        "candidateToolchain": candidate_toolchain_check(),
        "gitRepository": {"pass": (repo / ".git").exists(), "path": str(repo)},
        "lmstudio": lmstudio_check(model),
    }
    return {"pass": all(check["pass"] for check in checks.values()), "checks": checks}
