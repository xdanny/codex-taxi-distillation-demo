from __future__ import annotations

import shutil
from pathlib import Path

from .domain import sha256_file, write_json
from .fixture import prepare_fixture
from .paths import repository_root

BASE_SKILLS = ("dbt-data-product", "duckdb-analysis")


def copy_tree(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def prepare_run_workspace(
    destination: Path,
    *,
    distilled_skill: Path | None = None,
    root: Path | None = None,
) -> dict[str, object]:
    repo = root or repository_root()
    if destination.exists():
        raise FileExistsError(f"run workspace already exists: {destination}")
    destination.mkdir(parents=True)

    dataset = prepare_fixture(repo)
    shutil.copytree(dataset, destination / "input")
    shutil.copytree(repo / "contracts", destination / "model-inputs")

    skills_destination = destination / ".codex" / "skills"
    selected = list(BASE_SKILLS)
    for skill_name in BASE_SKILLS:
        copy_tree(repo / ".codex" / "skills" / skill_name, skills_destination / skill_name)

    if distilled_skill is not None:
        copy_tree(distilled_skill, skills_destination / "taxi-data-product-delivery")
        selected.append("taxi-data-product-delivery")

    shutil.copy2(repo / "pyproject.toml", destination / "pyproject.toml")
    shutil.copy2(repo / "uv.lock", destination / "uv.lock")
    (destination / ".gitignore").write_text(".venv/\nlogs/\n", encoding="utf-8")
    (destination / "README.md").write_text(
        "# Isolated Taxi candidate\n\nAll candidate work stays in this directory.\n",
        encoding="utf-8",
    )

    receipt_files = sorted(
        path
        for path in destination.rglob("*")
        if path.is_file() and ".git" not in path.parts and path.name != "workspace-receipt.json"
    )
    receipt = {
        "schemaVersion": 1,
        "selectedSkills": selected,
        "files": {str(path.relative_to(destination)): sha256_file(path) for path in receipt_files},
    }
    write_json(destination / "workspace-receipt.json", receipt)
    return receipt


def build_prompt(*, use_distilled_skill: bool) -> str:
    skills = "$dbt-data-product and $duckdb-analysis"
    if use_distilled_skill:
        skills += ", then $taxi-data-product-delivery"
    return (
        f"Invoke {skills}. Build the Taxi analytics product in this workspace from "
        "model-inputs/ANALYST-REQUIREMENT.md and model-inputs/product-contract.json. "
        "Use only the staged input and project-local skills. Run dbt and the frozen Analyst SQL. "
        "Write every required candidate file and export. Use `uv run` for Python and dbt commands. "
        "Do not edit model-inputs, .codex/skills, input, pyproject.toml, uv.lock, or "
        "workspace-receipt.json. Report only results you executed."
    )


def repair_prompt(findings_file: Path, *, routed_action: str | None = None) -> str:
    routing = f"The optimized DSPy router selected `{routed_action}`. " if routed_action else ""
    return (
        routing + "Repair the candidate using the verifier findings in "
        f"{findings_file.name}. Invoke the same project-local skills used for the build. "
        "Change only candidate implementation and output files. Rerun dbt and the relevant SQL. "
        "The verifier, inputs, contract, rubric, and skills remain unchanged."
    )
