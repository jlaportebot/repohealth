"""CLI entry point for repohealth — comprehensive repository health assessment."""

from __future__ import annotations

import json as _json
from pathlib import Path
from typing import Any, Dict, Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from . import (
    code_churn,
    commit_conventions,
    config as config_mod,
    dependency_graph,
    dirty_tree,
    doc_coverage,
    essentials,
    history as history_mod,
    large_files,
    last_commit,
    outdated_deps,
    pr_review,
    scoring,
    security,
    stale_branches,
    tech_debt,
    test_coverage,
)
from .config import RepoHealthConfig, load_config
from .scoring import HealthReport


def _color_status(status: str) -> str:
    return {"pass": "[green]✓[/]", "warn": "[yellow]⚠[/]", "fail": "[red]✗[/]"}.get(status, "?")


def _color_grade(grade: str) -> str:
    colors = {"A": "green", "B": "cyan", "C": "yellow", "D": "red", "F": "bold red"}
    return f"[{colors.get(grade, 'white')}]{grade}[/]"


def _run_checks(repo_path: str, cfg: RepoHealthConfig) -> HealthReport:
    """Run all enabled checks and return the health report."""
    disabled = set(cfg.ignore_checks)
    weights = {name: c.weight for name, c in cfg.checks.items() if c.weight != 10}

    # Run each check (only if enabled)
    dirty_result = None
    if cfg.is_check_enabled("dirty_tree"):
        dirty_result = dirty_tree.check(repo_path)

    stale_result = None
    if cfg.is_check_enabled("stale_branches"):
        stale_result = stale_branches.check(repo_path)

    ess_result = None
    if cfg.is_check_enabled("essentials"):
        ess_result = essentials.check(repo_path)

    deps_result = None
    if cfg.is_check_enabled("outdated_deps"):
        deps_result = outdated_deps.check(repo_path)

    large_result = None
    if cfg.is_check_enabled("large_files"):
        large_result = large_files.check(repo_path, threshold_kb=cfg.large_file_threshold_kb)

    activity_result = None
    if cfg.is_check_enabled("activity"):
        activity_result = last_commit.check(repo_path)

    # New checks
    churn_result = None
    if cfg.is_check_enabled("code_churn"):
        churn_result = code_churn.check(
            repo_path,
            since=cfg.churn_since,
            top_n=cfg.churn_top_n,
            high_churn_threshold=cfg.high_churn_threshold,
        )

    conventions_result = None
    if cfg.is_check_enabled("commit_conventions"):
        conventions_result = commit_conventions.check(repo_path, since=cfg.conventions_since)

    pr_result = None
    if cfg.is_check_enabled("pr_review"):
        pr_result = pr_review.check(repo_path, stale_threshold_days=cfg.pr_stale_days)

    test_result = None
    if cfg.is_check_enabled("test_coverage"):
        test_result = test_coverage.check(repo_path)

    sec_result = None
    if cfg.is_check_enabled("security"):
        sec_result = security.check(repo_path, max_findings=cfg.security_max_findings)

    doc_result = None
    if cfg.is_check_enabled("doc_coverage"):
        doc_result = doc_coverage.check(repo_path)

    depgraph_result = None
    if cfg.is_check_enabled("dependency_graph"):
        depgraph_result = dependency_graph.check(repo_path)

    debt_result = None
    if cfg.is_check_enabled("tech_debt"):
        debt_result = tech_debt.check(repo_path, max_items=cfg.tech_debt_max_items)

    report = scoring.aggregate(  # type: ignore[arg-type]
        path=repo_path,
        dirty=dirty_result,
        stale=stale_result,
        essentials=ess_result,
        deps=deps_result,
        large=large_result,
        activity=activity_result,
        code_churn=churn_result,
        commit_conventions=conventions_result,
        pr_review=pr_result,
        test_coverage=test_result,
        security=sec_result,
        doc_coverage=doc_result,
        dependency_graph=depgraph_result,
        tech_debt=debt_result,
        weight_overrides=weights or None,
        disabled_checks=list(disabled),
    )

    return report


def _report_to_dict(report: HealthReport) -> dict[str, Any]:
    """Convert a HealthReport to a JSON-serializable dict."""
    return {
        "path": report.path,
        "score": report.score,
        "grade": report.grade,
        "checks": [
            {
                "name": c.name,
                "score": c.score,
                "weight": c.weight,
                "detail": c.detail,
                "status": c.status,
                "data": c.data,
            }
            for c in report.checks
        ],
    }


def _print_rich_report(report: HealthReport, console: Console, show_tips: bool = True) -> None:
    """Print a rich-formatted health report."""
    table = Table(title=None, show_header=True, header_style="bold")
    table.add_column("Check", style="bold")
    table.add_column("Score", justify="right")
    table.add_column("Weight", justify="right")
    table.add_column("Status", justify="center")
    table.add_column("Detail")

    for c in report.checks:
        table.add_row(c.name, str(c.score), str(c.weight), _color_status(c.status), c.detail)

    border_style = "green" if report.score >= 80 else "yellow" if report.score >= 60 else "red"
    console.print()
    console.print(
        Panel(
            f"[bold]Score:[/bold] {report.score}/100 [bold]Grade:[/bold] {_color_grade(report.grade)}",
            title=f"🩺 repohealth — {report.path}",
            border_style=border_style,
        )
    )
    console.print(table)

    # Tips
    if show_tips:
        tips = []
        for c in report.checks:
            if c.status == "fail":
                if c.name == "Security":
                    tips.append("[red]🔒[/] Remove hardcoded secrets and add SECURITY.md")
                elif c.name == "Test Coverage":
                    tips.append("[red]🧪[/] Add tests for uncovered source files")
                elif c.name == "Essentials":
                    tips.append("[red]📄[/] Add missing essential files (README, LICENSE, CI)")
                elif c.name == "Commit Conventions":
                    tips.append(
                        "[yellow]📝[/] Adopt conventional commit format (feat|fix|docs: ...)"
                    )
                elif c.name == "Tech Debt":
                    tips.append("[yellow]🔧[/] Address FIXMEs and high-complexity functions")
            elif c.status == "warn":
                if c.name == "Code Churn":
                    tips.append("[yellow]🔄[/] Refactor high-churn files to reduce volatility")
                elif c.name == "Documentation":
                    tips.append("[yellow]📖[/] Add docstrings to public APIs")
                elif c.name == "Dependency Graph":
                    tips.append("[yellow]📦[/] Pin dependency versions and remove unused deps")

        if tips:
            console.print()
            console.print("[bold]💡 Tips:[/]")
            for tip in tips[:5]:
                console.print(f"  {tip}")

    console.print()


def _print_github_action_report(report: HealthReport) -> None:
    """Print a GitHub Actions-compatible report."""
    for c in report.checks:
        symbol = "✓" if c.status == "pass" else "⚠" if c.status == "warn" else "✗"
        print(
            f"::{c.status} file=repohealth,title={c.name}::{symbol} {c.name}: {c.score}/100 — {c.detail}"
        )
    print(f"::notice file=repohealth,title=Overall::Score {report.score}/100, Grade {report.grade}")


# ── CLI Commands ─────────────────────────────────────────────────────────────


@click.group()
@click.version_option(package_name="repohealth")
def main() -> None:
    """🩺 repohealth — Comprehensive repository health assessment.

    Run 'repohealth check' to assess a repository, or use subcommands
    for history, comparisons, and configuration.
    """


@main.command()
@click.argument("path", default=".")
@click.option("--threshold", "-t", default=1024, help="Large-file threshold in KB (default 1024)")
@click.option("--json-output", "-j", "json_fmt", is_flag=True, help="Output as JSON")
@click.option("--github-action", "-g", is_flag=True, help="Output for GitHub Actions")
@click.option("--save", "-s", is_flag=True, help="Save report to history")
@click.option("--no-tips", is_flag=True, help="Hide improvement tips")
@click.option("--config", "config_file", default=None, help="Path to .repohealth.yml config")
def check(
    path: str,
    threshold: int,
    json_fmt: bool,
    github_action: bool,
    save: bool,
    no_tips: bool,
    config_file: str | None,
) -> None:
    """Assess the health of a Git repository.

    Runs a comprehensive suite of checks and produces a score (0–100)
    with letter grade (A–F).
    """
    # Load config
    cfg = load_config(path)
    if config_file:
        # Override with specific config file
        try:
            import yaml

            with open(config_file) as f:
                file_data = yaml.safe_load(f) or {}
            # Merge on top of defaults
            from .config import _deep_merge, DEFAULTS

            merged = _deep_merge(DEFAULTS, file_data)
            # Rebuild config... simplified: just update threshold
            if "large_file_threshold_kb" in merged:
                cfg.large_file_threshold_kb = int(merged["large_file_threshold_kb"])
        except Exception:
            pass

    # Override threshold if specified on command line
    if threshold != 1024:
        cfg.large_file_threshold_kb = threshold

    console = Console() if not json_fmt and not github_action else None

    if console:
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold]Running checks...[/]"),
            console=console,
            transient=True,
        ):
            report = _run_checks(path, cfg)
    else:
        report = _run_checks(path, cfg)

    # Save to history if requested
    if save or cfg.save_history:
        try:
            history_mod.save_report(_report_to_dict(report), repo_path=path)
        except Exception:
            pass  # History save is best-effort

    # Output
    if github_action:
        _print_github_action_report(report)
    elif json_fmt:
        data = _report_to_dict(report)
        click.echo(_json.dumps(data, indent=2))
    else:
        assert console is not None
        _print_rich_report(report, console, show_tips=not no_tips)

    # Exit with non-zero if grade is in fail list
    if report.grade in cfg.fail_on_grade:
        raise SystemExit(1)


@main.command()
@click.argument("path", default=".")
@click.option("--limit", "-n", default=20, help="Max history entries to show")
@click.option("--json-output", "-j", "json_fmt", is_flag=True, help="Output as JSON")
def history(path: str, limit: int, json_fmt: bool) -> None:
    """View health report history for a repository.

    Shows saved report snapshots with scores, grades, and trends.
    """
    entries = history_mod.load_history(repo_path=path, limit=limit)

    if not entries:
        click.echo("No history found. Run 'repohealth check --save' first.", err=True)
        return

    if json_fmt:
        data = [
            {
                "timestamp": e.timestamp,
                "score": e.score,
                "grade": e.grade,
                "path": e.path,
            }
            for e in entries
        ]
        click.echo(_json.dumps(data, indent=2))
        return

    console = Console()
    table = Table(title="📈 repohealth history", show_header=True, header_style="bold")
    table.add_column("Date", style="cyan")
    table.add_column("Score", justify="right")
    table.add_column("Grade", justify="center")
    table.add_column("Path")

    for entry in entries:
        grade_str = _color_grade(entry.grade)
        table.add_row(entry.timestamp[:10], str(entry.score), grade_str, entry.path)

    console.print(table)

    # Show trend
    trend = history_mod.get_trend(entries)
    trend_icons = {
        "improving": "📈",
        "stable": "➡️",
        "declining": "📉",
        "insufficient": "❓",
    }
    console.print(f"\n{trend_icons.get(trend, '❓')} Trend: [bold]{trend}[/]")

    # Prune old entries
    pruned = history_mod.prune_history(repo_path=path)
    if pruned > 0:
        console.print(f"[dim]Pruned {pruned} old entries[/]")


@main.command()
@click.argument("path", default=".")
@click.option("--since", "-s", default=None, help="Compare to specific timestamp (YYYY-MM-DD)")
@click.option("--json-output", "-j", "json_fmt", is_flag=True, help="Output as JSON")
def compare(path: str, since: str | None, json_fmt: bool) -> None:
    """Compare current health to a previous report.

    Shows score delta and per-check changes.
    """
    entries = history_mod.load_history(repo_path=path)

    if len(entries) < 2:
        click.echo(
            "Need at least 2 history entries to compare. Run 'repohealth check --save' multiple times.",
            err=True,
        )
        return

    # Find the "earlier" entry
    if since:
        earlier = None
        for e in entries:
            if e.timestamp.startswith(since):
                earlier = e
                break
        if earlier is None:
            click.echo(f"No history entry found for {since}", err=True)
            return
    else:
        earlier = entries[-2]  # Second-to-last

    later = entries[-1]  # Latest
    diff = history_mod.compare_entries(earlier, later)

    if json_fmt:
        data = {
            "earlier": {
                "timestamp": earlier.timestamp,
                "score": earlier.score,
                "grade": earlier.grade,
            },
            "later": {
                "timestamp": later.timestamp,
                "score": later.score,
                "grade": later.grade,
            },
            "score_delta": diff.score_delta,
            "grade_changed": diff.grade_changed,
            "improved": diff.improved,
            "regressed": diff.regressed,
            "new_checks": diff.new_checks,
            "removed_checks": diff.removed_checks,
            "check_deltas": diff.check_deltas,
        }
        click.echo(_json.dumps(data, indent=2))
        return

    console = Console()

    # Header
    delta_str = f"+{diff.score_delta}" if diff.score_delta > 0 else str(diff.score_delta)
    delta_color = "green" if diff.score_delta > 0 else "red" if diff.score_delta < 0 else "white"

    console.print()
    console.print(
        Panel(
            f"[bold]Score change:[/bold] {earlier.score} → {later.score} ([{delta_color}]{delta_str}[/])\n"
            f"[bold]Grade:[/bold] {_color_grade(earlier.grade)} → {_color_grade(later.grade)}"
            + (" [yellow](changed)[/]" if diff.grade_changed else " (same)"),
            title=f"📊 repohealth compare — {path}",
            border_style="green"
            if diff.score_delta > 0
            else "red"
            if diff.score_delta < 0
            else "blue",
        )
    )

    # Check deltas table
    if diff.check_deltas:
        table = Table(show_header=True, header_style="bold")
        table.add_column("Check")
        table.add_column("Delta", justify="right")
        table.add_column("Direction")

        for name, delta in sorted(diff.check_deltas.items()):
            if delta > 0:
                direction = "[green]↑ improved[/]"
            elif delta < 0:
                direction = "[red]↓ regressed[/]"
            else:
                direction = "[dim]→ unchanged[/]"
            delta_str = f"+{delta}" if delta > 0 else str(delta)
            table.add_row(name, delta_str, direction)

        console.print(table)

    if diff.new_checks:
        console.print(f"\n[green]New checks:[/green] {', '.join(diff.new_checks)}")
    if diff.regressed:
        console.print(f"[red]Regressed:[/red] {', '.join(diff.regressed)}")
    if diff.improved:
        console.print(f"[green]Improved:[/green] {', '.join(diff.improved)}")

    console.print()


@main.command()
@click.argument("path", default=".")
def init(path: str) -> None:
    """Initialize repohealth configuration for a repository.

    Creates a .repohealth.yml with default settings.
    """
    base = Path(path)
    config_path = base / ".repohealth.yml"

    if config_path.exists():
        click.echo(f"Config already exists: {config_path}", err=True)
        click.echo("Use --force to overwrite (not implemented yet).")
        return

    generated = config_mod.generate_default_config(config_path)
    console = Console()
    console.print(f"[green]✓[/] Created [bold]{generated}[/]")
    console.print("[dim]Edit this file to customize checks, weights, and thresholds.[/]")


@main.command(name="list-checks")
def list_checks() -> None:
    """List all available health checks with descriptions."""
    console = Console()
    table = Table(title="Available Checks", show_header=True, header_style="bold")
    table.add_column("Check Name", style="bold cyan")
    table.add_column("Description")
    table.add_column("Default Weight", justify="right")

    checks_info = [
        ("dirty_tree", "Uncommitted/unstaged/untracked changes", "15"),
        ("stale_branches", "Merged branches that can be deleted", "10"),
        ("essentials", "README, LICENSE, .gitignore, CI config", "20"),
        ("outdated_deps", "Outdated Python package dependencies", "15"),
        ("large_files", "Files exceeding size threshold", "10"),
        ("activity", "Time since last commit", "15"),
        ("code_churn", "High-touch files and commit volatility", "10"),
        ("commit_conventions", "Conventional commit format compliance", "10"),
        ("pr_review", "PR review coverage, stale/oversized PRs", "5"),
        ("test_coverage", "Test-to-code ratio, file coverage", "10"),
        ("security", "Hardcoded secrets, dangerous files, audit", "15"),
        ("doc_coverage", "Docstring coverage, README completeness", "5"),
        ("dependency_graph", "Unused/undeclared deps, version pinning", "5"),
        ("tech_debt", "TODO/FIXME markers, complexity, long functions", "5"),
    ]

    for name, desc, weight in checks_info:
        table.add_row(name, desc, weight)

    console.print(table)


# ── Backward compatibility: running repohealth without subcommand ────────────


# If invoked as `repohealth PATH` (no subcommand), default to `check`
@main.command(hidden=True, deprecated=True)
@click.argument("path", default=".")
@click.option("--threshold", "-t", default=1024)
@click.option("--json-output", "-j", "json_fmt", is_flag=True)
def scan(path: str, threshold: int, json_fmt: bool) -> None:
    """Deprecated: use 'repohealth check' instead."""
    ctx = click.get_current_context()
    ctx.invoke(
        check,
        path=path,
        threshold=threshold,
        json_fmt=json_fmt,
        github_action=False,
        save=False,
        no_tips=False,
        config_file=None,
    )


# Register main as the default click command when run as `python -m repohealth.cli`
if __name__ == "__main__":
    main()
