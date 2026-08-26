from __future__ import annotations

import json
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


def test_output_inspection_guide_states_current_iceberg_boundary() -> None:
    root = Path(__file__).parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")
    guide = (root / "docs" / "INSPECTING_OUTPUTS.md").read_text(encoding="utf-8")
    assert "docs/INSPECTING_OUTPUTS.md" in readme
    assert "does **not** publish Iceberg tables" in guide
    assert "$DEMO_RUN/workspace/models" in guide
    assert "iceberg_scan" in guide
