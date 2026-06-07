"""Scoring engine — aggregate check results into a health score (0–100)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .code_churn import CodeChurnResult
from .commit_conventions import CommitConventionsResult
from .dependency_graph import DependencyGraphResult
from .dirty_tree import DirtyTreeResult
from .doc_coverage import DocCoverageResult
from .essentials import EssentialsResult
from .large_files import LargeFilesResult
from .last_commit import LastCommitResult
from .outdated_deps import OutdatedDepsResult
from .pr_review import PRReviewResult
from .security import SecurityResult
from .stale_branches import StaleBranchResult
from .tech_debt import TechDebtResult
from .test_coverage import TestCoverageResult


@dataclass
class CheckReport:
    """Per-check report with score and detail."""

    name: str
    score: int  # 0–100
    weight: int
    detail: str
    status: str  # "pass", "warn", "fail"
    data: Optional[Dict[str, Any]] = field(default=None, repr=False)


@dataclass
class HealthReport:
    """Aggregate health report."""

    path: str
    score: int  # weighted average 0–100
    grade: str  # A/B/C/D/F
    checks: List[CheckReport] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


def _grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


# ── Original check scorers ──────────────────────────────────────────────────


def score_dirty_tree(result: DirtyTreeResult) -> CheckReport:
    if not result.is_dirty:
        return CheckReport("Working Tree", 100, 15, "Clean working tree", "pass")
    parts = []
    if result.has_uncommitted:
        parts.append("uncommitted changes")
    if result.has_unstaged:
        parts.append("unstaged changes")
    if result.has_untracked:
        parts.append(f"{len(result.untracked_files)} untracked files")
    return CheckReport("Working Tree", 40, 15, "Dirty: " + ", ".join(parts), "warn")


def score_stale_branches(result: StaleBranchResult) -> CheckReport:
    n = len(result.stale_branches)
    if n == 0:
        return CheckReport("Stale Branches", 100, 10, "No stale branches", "pass")
    score = max(0, 100 - n * 10)
    return CheckReport("Stale Branches", score, 10, f"{n} merged branch(es) can be deleted", "warn")


def score_essentials(result: EssentialsResult) -> CheckReport:
    n_missing = len(result.missing)
    if n_missing == 0:
        return CheckReport("Essentials", 100, 20, "All essentials present", "pass")
    score = max(0, 100 - n_missing * 25)
    return CheckReport("Essentials", score, 20, f"Missing: {', '.join(result.missing)}", "fail")


def score_outdated_deps(result: OutdatedDepsResult) -> CheckReport:
    if result.error:
        return CheckReport("Dependencies", 75, 15, f"Skipped ({result.error})", "warn")
    n = len(result.outdated)
    if n == 0:
        return CheckReport("Dependencies", 100, 15, "All deps up-to-date", "pass")
    score = max(0, 100 - n * 15)
    detail = ", ".join(f"{d.name} ({d.installed} → {d.latest})" for d in result.outdated)
    return CheckReport("Dependencies", score, 15, f"{n} outdated: {detail}", "warn")


def score_large_files(result: LargeFilesResult) -> CheckReport:
    n = len(result.large_files)
    if n == 0:
        return CheckReport("Large Files", 100, 10, f"No files ≥{result.threshold_kb}KB", "pass")
    score = max(0, 100 - n * 20)
    detail = ", ".join(f"{f.path} ({f.size_kb}KB)" for f in result.large_files)
    return CheckReport("Large Files", score, 10, f"{n} large: {detail}", "warn")


def score_last_commit(result: LastCommitResult) -> CheckReport:
    days = result.days_since_last_commit
    if days < 0:
        return CheckReport("Activity", 50, 15, "No commits found", "fail")
    if days <= 7:
        return CheckReport("Activity", 100, 15, f"Last commit {days}d ago", "pass")
    if days <= 30:
        return CheckReport("Activity", 70, 15, f"Last commit {days}d ago", "warn")
    if days <= 90:
        return CheckReport("Activity", 40, 15, f"Last commit {days}d ago", "warn")
    return CheckReport("Activity", 20, 15, f"Last commit {days}d ago — stale!", "fail")


# ── New check scorers ───────────────────────────────────────────────────────


def score_code_churn(result: CodeChurnResult) -> CheckReport:
    """Score based on code churn analysis."""
    if result.error:
        return CheckReport("Code Churn", 75, 10, f"Skipped ({result.error})", "warn")
    if result.total_commits == 0:
        return CheckReport("Code Churn", 50, 10, "No commits to analyze", "warn")

    # Higher churn files = lower score
    n_high = result.high_churn_files
    if n_high == 0:
        return CheckReport(
            "Code Churn", 100, 10,
            f"{result.total_commits} commits, no high-churn files", "pass",
            data={"avg_churn": result.avg_churn_per_commit},
        )
    if n_high <= 2:
        score = max(0, 100 - n_high * 10)
        return CheckReport(
            "Code Churn", score, 10,
            f"{n_high} high-churn file(s), avg {result.avg_churn_per_commit} lines/commit", "warn",
            data={"avg_churn": result.avg_churn_per_commit},
        )
    score = max(0, 100 - n_high * 15)
    return CheckReport(
        "Code Churn", score, 10,
        f"{n_high} high-churn files — consider refactoring", "fail",
        data={"avg_churn": result.avg_churn_per_commit},
    )


def score_commit_conventions(result: CommitConventionsResult) -> CheckReport:
    """Score based on commit message convention compliance."""
    if result.error:
        return CheckReport("Commit Conventions", 75, 10, f"Skipped ({result.error})", "warn")
    if result.total_commits == 0:
        return CheckReport("Commit Conventions", 50, 10, "No commits to analyze", "warn")

    score = int(result.compliance_rate * 100)
    status = "pass" if score >= 80 else "warn" if score >= 50 else "fail"
    detail = f"{result.conventional_count}/{result.total_commits} conventional"

    if result.long_subject_count > 0:
        detail += f", {result.long_subject_count} long subjects"
    if result.empty_message_count > 0:
        detail += f", {result.empty_message_count} empty"

    return CheckReport(
        "Commit Conventions", score, 10, detail, status,
        data={"compliance_rate": result.compliance_rate},
    )


def score_pr_review(result: PRReviewResult) -> CheckReport:
    """Score based on PR review metrics."""
    if result.error:
        return CheckReport("PR Review", 75, 5, f"Skipped ({result.error})", "warn")
    if result.total_prs == 0:
        return CheckReport("PR Review", 100, 5, "No PRs found", "pass")

    score = 100
    # Deductions
    if result.stale_prs > 0:
        score -= min(result.stale_prs * 10, 30)
    if result.unreviewed_prs > 0:
        score -= min(result.unreviewed_prs * 10, 30)
    if result.large_prs > 0:
        score -= min(result.large_prs * 5, 20)
    score = max(0, score)

    status = "pass" if score >= 80 else "warn" if score >= 50 else "fail"
    parts = []
    if result.stale_prs:
        parts.append(f"{result.stale_prs} stale")
    if result.unreviewed_prs:
        parts.append(f"{result.unreviewed_prs} unreviewed")
    if result.large_prs:
        parts.append(f"{result.large_prs} oversized")
    detail = ", ".join(parts) if parts else "PRs well-managed"

    return CheckReport(
        "PR Review", score, 5, detail, status,
        data={"avg_days_to_merge": result.avg_days_to_merge},
    )


def score_test_coverage(result: TestCoverageResult) -> CheckReport:
    """Score based on static test coverage analysis."""
    if result.error:
        return CheckReport("Test Coverage", 75, 10, f"Skipped ({result.error})", "warn")

    if result.total_source_files == 0:
        return CheckReport("Test Coverage", 50, 10, "No source files found", "warn")

    # Score based on test-to-code ratio and file coverage
    ratio_score = min(100, int(result.test_to_code_ratio * 50))  # type: ignore[arg-type]  # 2:1 ratio = 100
    file_cov_score = int(result.test_coverage_pct)

    # Weighted: 60% file coverage, 40% ratio
    score = int(file_cov_score * 0.6 + ratio_score * 0.4)
    status = "pass" if score >= 70 else "warn" if score >= 40 else "fail"

    uncovered = result.files_without_tests
    detail = f"{result.test_coverage_pct:.0f}% file coverage, {result.test_to_code_ratio:.1f}x ratio"
    if uncovered > 0:
        detail += f", {uncovered} files untested"

    return CheckReport(
        "Test Coverage", score, 10, detail, status,
        data={
            "file_coverage_pct": result.test_coverage_pct,
            "test_to_code_ratio": result.test_to_code_ratio,
            "framework": result.test_framework,
        },
    )


def score_security(result: SecurityResult) -> CheckReport:
    """Score based on security analysis."""
    total = result.total_findings

    if total == 0 and result.risk_level == "low":
        return CheckReport("Security", 100, 15, "No issues found", "pass")

    score = 100
    # Critical deductions for secrets
    secret_count = len(result.secret_findings)
    score -= min(secret_count * 20, 60)
    # Deductions for dangerous files
    score -= min(len(result.dangerous_files_present) * 10, 20)
    # Bonus for security infra
    if result.has_dependabot:
        score = min(100, score + 5)
    if result.has_security_policy:
        score = min(100, score + 5)
    if result.has_pre_commit:
        score = min(100, score + 3)

    score = max(0, score)
    status = "pass" if score >= 80 else "warn" if score >= 50 else "fail"

    parts = []
    if secret_count:
        parts.append(f"{secret_count} secret(s)")
    if result.dangerous_files_present:
        parts.append(f"{len(result.dangerous_files_present)} dangerous file(s)")
    if result.pip_audit_result:
        parts.append(result.pip_audit_result)
    detail = ", ".join(parts) if parts else "Security infra present"

    return CheckReport(
        "Security", score, 15, detail, status,
        data={"risk_level": result.risk_level},
    )


def score_doc_coverage(result: DocCoverageResult) -> CheckReport:
    """Score based on documentation coverage."""
    if result.total_definitions == 0:
        return CheckReport("Documentation", 75, 5, "No definitions to document", "warn")

    score = int(result.coverage_pct)
    status = "pass" if score >= 70 else "warn" if score >= 40 else "fail"

    parts = [f"{result.coverage_pct:.0f}% docstring coverage"]
    if result.missing_readme_sections:
        n_missing = len(result.missing_readme_sections)
        parts.append(f"{n_missing} README section(s) missing")
    if not result.has_changelog:
        parts.append("no changelog")
    detail = ", ".join(parts)

    return CheckReport(
        "Documentation", score, 5, detail, status,
        data={
            "coverage_pct": result.coverage_pct,
            "module_docstring_pct": result.module_docstring_pct,
        },
    )


def score_dependency_graph(result: DependencyGraphResult) -> CheckReport:
    """Score based on dependency graph analysis."""
    if result.error:
        return CheckReport("Dependency Graph", 75, 5, f"Skipped ({result.error})", "warn")

    score = 100
    parts = []

    # Deductions for unused deps
    if result.unused_deps:
        score -= min(len(result.unused_deps) * 5, 20)
        parts.append(f"{len(result.unused_deps)} unused")
    # Deductions for missing deps
    if result.missing_deps:
        score -= min(len(result.missing_deps) * 10, 30)
        parts.append(f"{len(result.missing_deps)} undeclared")
    # Deductions for wildcard versions
    if result.has_wildcards > 0:
        score -= min(result.has_wildcards * 5, 15)
        parts.append(f"{result.has_wildcards} unpinned")

    score = max(0, score)
    status = "pass" if score >= 80 else "warn" if score >= 50 else "fail"
    detail = ", ".join(parts) if parts else f"{result.total_runtime} runtime deps, well-managed"

    return CheckReport(
        "Dependency Graph", score, 5, detail, status,
        data={
            "runtime": result.total_runtime,
            "dev": result.total_dev,
        },
    )


def score_tech_debt(result: TechDebtResult) -> CheckReport:
    """Score based on technical debt analysis."""
    # Invert the debt_score (0 = no debt, 100 = max debt)
    score = max(0, 100 - result.debt_score)
    status = "pass" if score >= 70 else "warn" if score >= 40 else "fail"

    parts = []
    if result.total_markers > 0:
        parts.append(f"{result.total_markers} marker(s)")
    if result.high_complexity_functions:
        parts.append(f"{len(result.high_complexity_functions)} complex func(s)")
    if result.long_functions > 0:
        parts.append(f"{result.long_functions} long func(s)")

    detail = ", ".join(parts) if parts else "No significant debt markers"

    return CheckReport(
        "Tech Debt", score, 5, detail, status,
        data={"debt_score": result.debt_score},
    )


# ── Aggregation ─────────────────────────────────────────────────────────────


def aggregate(
    path: str,
    dirty: DirtyTreeResult,
    stale: StaleBranchResult,
    essentials: EssentialsResult,
    deps: OutdatedDepsResult,
    large: LargeFilesResult,
    activity: LastCommitResult,
    # New checks (optional with None for backward compat)
    code_churn: Optional[CodeChurnResult] = None,
    commit_conventions: Optional[CommitConventionsResult] = None,
    pr_review: Optional[PRReviewResult] = None,
    test_coverage: Optional[TestCoverageResult] = None,
    security: Optional[SecurityResult] = None,
    doc_coverage: Optional[DocCoverageResult] = None,
    dependency_graph: Optional[DependencyGraphResult] = None,
    tech_debt: Optional[TechDebtResult] = None,
    # Config overrides for weights
    weight_overrides: Optional[Dict[str, int]] = None,
    disabled_checks: Optional[List[str]] = None,
) -> HealthReport:
    """Compute the aggregate health report."""
    disabled = set(disabled_checks or [])
    weights = weight_overrides or {}

    # Build all check reports
    all_check_funcs: List[Tuple[str, Any, Any]] = [
        ("dirty_tree", dirty, score_dirty_tree),
        ("stale_branches", stale, score_stale_branches),
        ("essentials", essentials, score_essentials),
        ("outdated_deps", deps, score_outdated_deps),
        ("large_files", large, score_large_files),
        ("activity", activity, score_last_commit),
        ("code_churn", code_churn, score_code_churn),
        ("commit_conventions", commit_conventions, score_commit_conventions),
        ("pr_review", pr_review, score_pr_review),
        ("test_coverage", test_coverage, score_test_coverage),
        ("security", security, score_security),
        ("doc_coverage", doc_coverage, score_doc_coverage),
        ("dependency_graph", dependency_graph, score_dependency_graph),
        ("tech_debt", tech_debt, score_tech_debt),
    ]

    checks: List[CheckReport] = []
    for name, result, scorer in all_check_funcs:
        if name in disabled:
            continue
        if result is None:
            continue

        report = scorer(result)

        # Apply weight override
        if name in weights:
            report = CheckReport(
                name=report.name,
                score=report.score,
                weight=weights[name],
                detail=report.detail,
                status=report.status,
                data=report.data,
            )

        checks.append(report)

    total_weight = sum(c.weight for c in checks)
    weighted = sum(c.score * c.weight for c in checks)
    overall = round(weighted / total_weight) if total_weight else 0
    return HealthReport(path=path, score=overall, grade=_grade(overall), checks=checks)
