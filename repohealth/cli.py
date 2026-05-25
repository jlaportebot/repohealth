"""CLI entry point for repohealth."""

from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from . import dirty_tree, essentials, large_files, last_commit, outdated_deps, stale_branches, scoring
from .scoring import HealthReport


def _run_checks(repo_path: str, threshold_kb: int) -> HealthReport:
    dirty = dirty_tree.check(repo_path)
    stale = stale_branches.check(repo_path)
    ess = essentials.check(repo_path)
    deps = outdated_deps.check(repo_path)
    large = large_files.check(repo_path, threshold_kb=threshold_kb)
    activity = last_commit.check(repo_path)
    return scoring.aggregate(repo_path, dirty, stale, ess, deps, large, activity)


def _color_status(status: str) -> str:
    return {"pass": "[green]✓[/]", "warn": "[yellow]⚠[/]", "fail": "[red]✗[/]"}.get(status, "?")


def _color_grade(grade: str) -> str:
    colors = {"A": "green", "B": "cyan", "C": "yellow", "D": "red", "F": "bold red"}
    return f"[{colors.get(grade, 'white')}]{grade}[/]"


@click.command()
@click.argument("path", default=".")
@click.option("--threshold", "-t", default=1024, help="Large-file threshold in KB (default 1024)")
@click.option("--json-output", "-j", "json_fmt", is_flag=True, help="Output as JSON")
@click.version_option(package_name="repohealth")
def main(path: str, threshold: int, json_fmt: bool) -> None:
    """Assess the health of a Git repository.

    Runs a suite of checks and produces a score (0–100) with letter grade.
    """
    import json as _json

    report = _run_checks(path, threshold)

    if json_fmt:
        data = {
            "path": report.path,
            "score": report.score,
            "grade": report.grade,
            "checks": [
                {"name": c.name, "score": c.score, "weight": c.weight, "detail": c.detail, "status": c.status}
                for c in report.checks
            ],
        }
        click.echo(_json.dumps(data, indent=2))
        return

    console = Console()
    table = Table(title=None, show_header=True, header_style="bold")
    table.add_column("Check", style="bold")
    table.add_column("Score", justify="right")
    table.add_column("Status", justify="center")
    table.add_column("Detail")

    for c in report.checks:
        table.add_row(c.name, str(c.score), _color_status(c.status), c.detail)

    grade_text = Text(f"  {report.grade}  ", style="bold")
    console.print()
    console.print(
        Panel(
            f"[bold]Score:[/bold] {report.score}/100   [bold]Grade:[/bold] {_color_grade(report.grade)}",
            title=f"🩺  repohealth — {report.path}",
            border_style="green" if report.score >= 80 else "yellow" if report.score >= 60 else "red",
        )
    )
    console.print(table)
    console.print()

    # Exit with non-zero if grade is D or F
    if report.grade in ("D", "F"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
