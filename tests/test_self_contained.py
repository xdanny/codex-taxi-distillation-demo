from __future__ import annotations

import json
import re
from pathlib import Path


def test_contract_declares_verifier_semantics(demo_root: Path) -> None:
    tables = json.loads(
        (demo_root / "contracts" / "product-contract.json").read_text()
    )["tableDefinitions"]
    assert tables["trip_facts"]["derivedColumns"]["total_revenue"] == "fare_amount + tip_amount"
    assert tables["hourly_zone_metrics"]["measures"]["total_revenue"] == "sum(total_revenue)"


def test_runtime_has_no_external_repository_reference(demo_root: Path) -> None:
    forbidden_fragments = ("/Users/", "/home/", "Documents/workspace/")
    roots = [demo_root / "src", demo_root / "contracts", demo_root / ".codex" / "skills"]
    for root in roots:
        for path in root.rglob("*"):
            if path.is_symlink():
                assert demo_root in path.resolve().parents
            if path.is_file():
                contents = path.read_text(encoding="utf-8", errors="ignore")
                assert all(fragment not in contents for fragment in forbidden_fragments)


def test_demo_instruction_declares_repository_as_sole_source(demo_root: Path) -> None:
    instruction = (
        demo_root / ".codex" / "skills" / "run-offline-data-loop-demo" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "sole source of truth" in instruction
    assert "Do not inspect or use\nglobal agent memory" in instruction


def test_documented_entrypoint_ignores_user_configuration() -> None:
    readme = (Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8")
    assert "--ephemeral --ignore-user-config" in readme
    assert "--sandbox danger-full-access" in readme
    assert "Every candidate model still runs" in readme


def test_readme_leads_with_live_qwen_38_demo() -> None:
    readme = (Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8")
    live_demo = readme.index("## Start here")
    experiment = readme.index("## What the experiment runs")

    assert live_demo < experiment
    opening = readme[live_demo:experiment]
    assert "qwen3.8-27b" in opening
    assert "git --version" in opening
    assert "uv sync --frozen --all-groups" in opening
    assert "taxi-demo doctor" in opening
    assert "taxi-demo use-example-skill" in opening
    assert "taxi-demo run qwen-skill --repairs 1" in opening
    assert "taxi-demo query-example terra" in opening
    assert "taxi-demo full" in opening


def test_start_guide_has_executable_newcomer_paths() -> None:
    guide = (
        Path(__file__).parents[1] / "docs" / "START_HERE.md"
    ).read_text(encoding="utf-8")

    assert "Last validated: 2026-08-26" in guide
    assert "uv sync --frozen --all-groups" in guide
    assert "taxi-demo query-example terra" in guide
    assert "taxi-demo use-example-skill" in guide
    assert "taxi-demo full" in guide
    assert "Success looks like this:" in guide
    assert "## Troubleshooting" in guide


def test_output_inspection_guide_states_current_iceberg_boundary() -> None:
    root = Path(__file__).parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")
    guide = (root / "docs" / "INSPECTING_OUTPUTS.md").read_text(encoding="utf-8")
    assert "docs/INSPECTING_OUTPUTS.md" in readme
    assert "does **not** publish Iceberg tables" in guide
    assert "$DEMO_RUN/workspace/models" in guide
    assert "iceberg_scan" in guide


def test_publishable_material_has_no_local_machine_paths() -> None:
    root = Path(__file__).parents[1]
    local_home = re.compile(r"/(?:Users|home)/[^/\s]+/")
    ignored_parts = {".ruff_cache", ".venv", "__pycache__", "assets", "logs", "target"}
    candidates = [root / "README.md", root / "docs", root / "examples", root / "demo-site"]

    for candidate in candidates:
        paths = [candidate] if candidate.is_file() else candidate.rglob("*")
        for path in paths:
            if not path.is_file() or ignored_parts.intersection(path.parts):
                continue
            contents = path.read_text(encoding="utf-8", errors="ignore")
            assert local_home.search(contents) is None, path
            assert "/private/var/" not in contents, path
