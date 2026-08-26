from __future__ import annotations

import json
from pathlib import Path


def test_contract_declares_verifier_semantics(demo_root: Path) -> None:
    tables = json.loads(
        (demo_root / "contracts" / "product-contract.json").read_text()
    )["tableDefinitions"]
    assert tables["trip_facts"]["derivedColumns"]["total_revenue"] == "fare_amount + tip_amount"
    assert tables["hourly_zone_metrics"]["measures"]["total_revenue"] == "sum(total_revenue)"


def test_runtime_has_no_external_hyperplane_reference(demo_root: Path) -> None:
    forbidden = "hyper" + "plane"
    roots = [demo_root / "src", demo_root / "contracts", demo_root / ".codex" / "skills"]
    for root in roots:
        for path in root.rglob("*"):
            if path.is_symlink():
                assert demo_root in path.resolve().parents
            if path.is_file():
                assert forbidden not in path.read_text(encoding="utf-8", errors="ignore").lower()
