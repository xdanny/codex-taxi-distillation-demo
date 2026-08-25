from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

from .codex_runner import QWEN_MODEL
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


def lmstudio_check() -> dict[str, Any]:
    base = os.environ.get("LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1").rstrip("/")
    try:
        with urllib.request.urlopen(f"{base}/models", timeout=5) as response:
            payload = json.load(response)
        ids = [item.get("id") for item in payload.get("data", []) if isinstance(item, dict)]
        matching = [
            model_id
            for model_id in ids
            if isinstance(model_id, str)
            and (model_id == QWEN_MODEL or model_id.endswith(f"/{QWEN_MODEL}"))
        ]
        return {
            "pass": bool(matching),
            "endpoint": base,
            "expectedModel": QWEN_MODEL,
            "loadedModelIds": ids,
            "matchingModelIds": matching,
        }
    except Exception as exc:
        return {
            "pass": False,
            "endpoint": base,
            "expectedModel": QWEN_MODEL,
            "error": str(exc),
        }


def run_doctor(root: Path | None = None) -> dict[str, Any]:
    repo = root or repository_root()
    checks = {
        "uv": command_version(["uv", "--version"]),
        "codex": command_version(["codex", "--version"]),
        "gitRepository": {"pass": (repo / ".git").exists(), "path": str(repo)},
        "lmstudio": lmstudio_check(),
    }
    return {"pass": all(check["pass"] for check in checks.values()), "checks": checks}
