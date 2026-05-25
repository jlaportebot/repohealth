"""Scoring engine — aggregate check results into a health score (0–100)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

from .dirty_tree import DirtyTreeResult
from .essentials import EssentialsResult
from .large_files import LargeFilesResult
from .last_commit import LastCommitResult
from .outdated_deps import OutdatedDepsResult
from .stale_branches import StaleBranchResult


@dataclass
class CheckReport:
    """Per-check report with score and detail."""

    name: str
    score: int  # 0–100
    weight: int
    detail: str
    status: str  # "pass", "warn", "fail"


@dataclass
class HealthReport:
    """Aggregate health report."""

    path: str
    score: int  # weighted average 0–100
    grade: str  # A/B/C/D/F
    checks: List[CheckReport] = field(default_factory=list)


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


def aggregate(
    path: str,
    dirty: DirtyTreeResult,
    stale: StaleBranchResult,
    essentials: EssentialsResult,
    deps: OutdatedDepsResult,
    large: LargeFilesResult,
    activity: LastCommitResult,
) -> HealthReport:
    """Compute the aggregate health report."""
    checks = [
        score_dirty_tree(dirty),
        score_stale_branches(stale),
        score_essentials(essentials),
        score_outdated_deps(deps),
        score_large_files(large),
        score_last_commit(activity),
    ]
    total_weight = sum(c.weight for c in checks)
    weighted = sum(c.score * c.weight for c in checks)
    overall = round(weighted / total_weight) if total_weight else 0
    return HealthReport(path=path, score=overall, grade=_grade(overall), checks=checks)
