from __future__ import annotations

import os
import shlex
import shutil
import sys
from pathlib import Path

from .domain import sha256_file, write_json
from .fixture import prepare_fixture
from .paths import repository_root

BASE_SKILLS = ("dbt-data-product", "duckdb-analysis")

DUCKDB_CLI = """\
import sys
import duckdb

args = sys.argv[1:]
if not args or args[0] in {"-h", "--help"}:
    print("usage: duckdb [DATABASE] -c SQL | duckdb --version")
    raise SystemExit(0)
if args[0] in {"-version", "--version"}:
    print(duckdb.__version__)
    raise SystemExit(0)
database = ":memory:"
if args and not args[0].startswith("-"):
    database = args.pop(0)
if len(args) != 2 or args[0] not in {"-c", "--command"}:
    print("usage: duckdb [DATABASE] -c SQL | duckdb --version", file=sys.stderr)
    raise SystemExit(2)
cursor = duckdb.connect(database).execute(args[1])
if cursor.description:
    print("\\t".join(column[0] for column in cursor.description))
    for row in cursor.fetchall():
        print("\\t".join("" if value is None else str(value) for value in row))
"""


def copy_tree(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def write_executable(path: Path, contents: str) -> None:
    path.write_text(contents, encoding="utf-8")
    path.chmod(0o755)


def stage_candidate_toolchain(destination: Path) -> None:
    tools = destination / ".tools"
    binary = tools / "bin"
    binary.mkdir(parents=True)
    write_executable(binary / "python", '#!/bin/sh\nexec "$TAXI_DEMO_PYTHON" "$@"\n')
    write_executable(binary / "python3", '#!/bin/sh\nexec "$TAXI_DEMO_PYTHON" "$@"\n')
    write_executable(binary / "dbt", '#!/bin/sh\nexec "$TAXI_DEMO_DBT" "$@"\n')
    write_executable(
        binary / "duckdb",
        f'#!/bin/sh\nexec "$TAXI_DEMO_PYTHON" -c {shlex.quote(DUCKDB_CLI)} "$@"\n',
    )
    installer_block = (
        "#!/bin/sh\n"
        'echo "dbt and DuckDB are already available; run dbt, python, or duckdb directly. '
        'Candidate installs are disabled." >&2\n'
        "exit 2\n"
    )
    for command in ("uv", "uvx", "pip", "pip3"):
        write_executable(binary / command, installer_block)
    write_json(
        tools / "toolchain.json",
        {
            "schemaVersion": 1,
            "commands": {
                "dbt": ".tools/bin/dbt",
                "duckdb": ".tools/bin/duckdb",
                "python": ".tools/bin/python",
            },
            "installers": "disabled",
            "instruction": "Run dbt, duckdb, and python directly; do not install packages.",
        },
    )


def candidate_environment(workspace: Path) -> dict[str, str]:
    python = Path(sys.executable)
    dbt = python.parent / "dbt"
    if not dbt.is_file() or not os.access(dbt, os.X_OK):
        raise FileNotFoundError(f"dbt executable is missing from the demo environment: {dbt}")
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{workspace / '.tools' / 'bin'}:{environment.get('PATH', '')}",
            "TAXI_DEMO_PYTHON": str(python),
            "TAXI_DEMO_DBT": str(dbt),
            "PIP_NO_INDEX": "1",
            "UV_OFFLINE": "1",
        }
    )
    return environment


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
    stage_candidate_toolchain(destination)
    package = destination / "src" / "codex_taxi_distillation_demo"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(
        '"""Installable stub for the isolated Taxi candidate workspace."""\n',
        encoding="utf-8",
    )
    (package / "cli.py").write_text(
        '"""The experiment CLI runs outside candidate workspaces."""\n\n'
        "import typer\n\n"
        'app = typer.Typer(help="Candidate workspace runtime stub.")\n',
        encoding="utf-8",
    )
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
        "The toolchain is already on PATH: run `dbt`, `python`, and `duckdb` directly. "
        "Do not run uv or pip, install dependencies, or copy package caches. "
        "Write every required candidate file and export. "
        "Do not edit model-inputs, .codex/skills, .tools, input, the staged src runtime stub, "
        "pyproject.toml, uv.lock, or workspace-receipt.json. Report only results you executed."
    )


def repair_prompt(findings_file: Path, *, routed_action: str | None = None) -> str:
    routing = f"The optimized DSPy router selected `{routed_action}`. " if routed_action else ""
    return (
        routing + "Repair the candidate using the verifier findings in "
        f"{findings_file.name}. Invoke the same project-local skills used for the build. "
        "Change only candidate implementation and output files. Rerun dbt and the relevant SQL. "
        "The verifier, inputs, contract, rubric, and skills remain unchanged."
    )
