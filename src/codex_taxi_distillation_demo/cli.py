from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from .codex_runner import run_arm, run_parallel_teachers
from .distill import run_distillation
from .doctor import run_doctor
from .domain import Arm, RunRecord
from .dspy_optimize import optimize_prompt
from .fixture import prepare_fixture
from .paths import active_experiment_id, experiment_root, repository_root, start_experiment
from .report import build_report
from .verify import verify_candidate

app = typer.Typer(
    no_args_is_help=True,
    help="Run the portable Codex Taxi analysis, distillation, DSPy, and Qwen demo.",
)
console = Console()


def print_run(run: RunRecord) -> None:
    table = Table("Run", "Arm", "Accepted", "Attempts", "Tokens", "Elapsed")
    table.add_row(
        run.run_id,
        run.arm,
        "yes" if run.accepted else "no",
        str(len(run.attempts)),
        f"{run.usage.total_tokens:,}",
        f"{run.elapsed_seconds:.1f}s",
    )
    console.print(table)


@app.command()
def doctor() -> None:
    """Check uv, Codex, the repository, and the loaded LM Studio Qwen model."""
    report = run_doctor()
    console.print_json(data=report)
    if not report["pass"]:
        raise typer.Exit(1)


@app.command()
def start() -> None:
    """Start a fresh experiment cohort without deleting previous evidence."""
    experiment_id = start_experiment(repository_root())
    console.print(f"Started experiment [bold]{experiment_id}[/bold]")


@app.command()
def current() -> None:
    """Print the active experiment and its evidence directory."""
    console.print_json(
        data={
            "experimentId": active_experiment_id(repository_root()),
            "path": str(experiment_root(repository_root())),
        }
    )


@app.command()
def prepare(force: bool = False) -> None:
    """Create the deterministic Taxi fixture."""
    path = prepare_fixture(force=force)
    console.print(f"Prepared [bold]{path}[/bold]")


@app.command()
def teachers(
    count: Annotated[int, typer.Option(min=2)] = 3,
    parallel: Annotated[int, typer.Option(min=1)] = 3,
    repairs: Annotated[int, typer.Option(min=0, max=2)] = 1,
) -> None:
    """Run independent Terra teacher candidates concurrently."""
    records = asyncio.run(
        run_parallel_teachers(count, parallel=parallel, root=repository_root(), repairs=repairs)
    )
    for record in records:
        print_run(record)


@app.command("run")
def run_one(
    arm: Annotated[
        Arm,
        typer.Argument(help="terra, qwen-bare, qwen-skill, qwen-dspy, or qwen-both"),
    ],
    repairs: Annotated[int, typer.Option(min=0, max=2)] = 1,
) -> None:
    """Run one isolated candidate arm under the unchanged verifier."""
    print_run(asyncio.run(run_arm(arm, root=repository_root(), repairs=repairs)))


@app.command()
def distill() -> None:
    """Extract and validate a project-local skill from accepted Terra candidates."""
    path = run_distillation(root=repository_root())
    console.print(f"Published distilled skill: [bold]{path}[/bold]")


@app.command()
def optimize(
    max_metric_calls: Annotated[int, typer.Option(min=8, max=200)] = 18,
) -> None:
    """Run genuine DSPy GEPA with Qwen as student and Terra as reflection LM."""
    path = optimize_prompt(root=repository_root(), max_metric_calls=max_metric_calls)
    console.print(f"Published DSPy program and readable instruction: [bold]{path}[/bold]")


@app.command()
def verify(workspace: Path) -> None:
    """Run the unchanged deterministic verifier against a candidate workspace."""
    resolved = workspace.resolve()
    receipt = resolved.parent / "input-receipt.json"
    report = verify_candidate(
        resolved,
        expected_receipt=receipt if receipt.is_file() else None,
    )
    console.print_json(data=report)
    if not report["accepted"]:
        raise typer.Exit(1)


@app.command()
def report() -> None:
    """Compare completion, attempts, tokens, and elapsed time by arm."""
    json_path, markdown_path = build_report(root=repository_root())
    console.print(f"Report: [bold]{markdown_path}[/bold]\nEvidence: {json_path}")


@app.command()
def full(
    teachers_count: Annotated[int, typer.Option("--teachers", min=3)] = 3,
    parallel: Annotated[int, typer.Option(min=1)] = 3,
    repairs: Annotated[int, typer.Option(min=0, max=2)] = 1,
    max_metric_calls: Annotated[int, typer.Option(min=8, max=200)] = 18,
) -> None:
    """Run the complete demonstration from fresh candidates to comparison report."""
    preflight = run_doctor()
    if not preflight["pass"]:
        console.print_json(data=preflight)
        raise typer.Exit(1)
    experiment_id = start_experiment(repository_root())
    console.print(f"Started fresh experiment [bold]{experiment_id}[/bold]")
    prepare_fixture()
    terra = asyncio.run(
        run_parallel_teachers(
            teachers_count,
            parallel=parallel,
            root=repository_root(),
            repairs=repairs,
        )
    )
    for record in terra:
        print_run(record)
    additional = 0
    while sum(record.accepted for record in terra) < 3 and additional < 2:
        record = asyncio.run(run_arm("terra", root=repository_root(), repairs=repairs))
        terra.append(record)
        additional += 1
        print_run(record)
    if sum(record.accepted for record in terra) < 3:
        raise RuntimeError(
            "full demo stopped after five candidates without three accepted Terra sources"
        )
    print_run(asyncio.run(run_arm("qwen-bare", root=repository_root(), repairs=repairs)))
    optimize_prompt(root=repository_root(), max_metric_calls=max_metric_calls)
    print_run(asyncio.run(run_arm("qwen-dspy", root=repository_root(), repairs=repairs)))
    run_distillation(root=repository_root())
    print_run(asyncio.run(run_arm("qwen-skill", root=repository_root(), repairs=repairs)))
    print_run(asyncio.run(run_arm("qwen-both", root=repository_root(), repairs=repairs)))
    _, markdown_path = build_report(root=repository_root())
    console.print(f"Complete comparison: [bold]{markdown_path}[/bold]")


@app.command("show-config")
def show_config() -> None:
    """Print the fixed model routes and state paths without running a model."""
    console.print_json(
        data={
            "terra": {"model": "gpt-5.6-terra", "provider": "OpenAI via Codex"},
            "qwen": {"model": "qwen3.8-27b", "provider": "LM Studio via Codex --oss"},
            "state": str(repository_root() / ".demo"),
        }
    )


if __name__ == "__main__":
    app()
