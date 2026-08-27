from __future__ import annotations

import sys
from pathlib import Path

from codex_taxi_distillation_demo.doctor import candidate_toolchain_check, codex_auth_check


def test_codex_auth_check_reports_authenticated_cli(tmp_path: Path) -> None:
    fake = tmp_path / "codex"
    fake.write_text(
        f"#!{sys.executable}\nimport sys\n"
        "assert sys.argv[1:] == ['login', 'status']\n"
        "print('Logged in using ChatGPT')\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)

    result = codex_auth_check(str(fake))

    assert result["pass"] is True
    assert result["status"] == "Logged in using ChatGPT"


def test_candidate_toolchain_check_proves_dbt_and_duckdb_are_installed() -> None:
    result = candidate_toolchain_check()

    assert result["pass"] is True
    assert result["dbtAvailable"] is True
    assert result["duckdbVersion"]
