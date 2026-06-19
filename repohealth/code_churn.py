"""Check: code churn analysis — high-touch files and volatility metrics."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class FileChurn:
    """Churn stats for a single file."""

    path: str
    commits: int
    insertions: int
    deletions: int
    churn_score: float  # insertions + deletions / commits

    @property
    def total_lines_changed(self) -> int:
        return self.insertions + self.deletions


@dataclass
class CodeChurnResult:
    """Result of code-churn check."""

    top_files: list[FileChurn]
    total_commits: int
    total_insertions: int
    total_deletions: int
    avg_churn_per_commit: float
    high_churn_files: int  # files with churn_score > threshold
    error: str | None = None


def _git(args: list[str], cwd: str | None = None) -> str:
    r = subprocess.run(["git"] + args, capture_output=True, text=True, cwd=cwd)
    return r.stdout.strip()


def check(
    repo_path: str | None = None,
    since: str = "6 months ago",
    top_n: int = 10,
    high_churn_threshold: float = 50.0,
) -> CodeChurnResult:
    """Analyze code churn: which files change most often and by how much.

    Args:
        repo_path: Path to the git repository.
        since: Git log date-spec for how far back to look.
        top_n: Number of top-churn files to return.
        high_churn_threshold: Files above this churn_score are flagged.
    """
    # First check if repo has any commits
    log_test = _git(["log", "--oneline", "-1", f"--since={since}"], cwd=repo_path)
    if not log_test:
        return CodeChurnResult(
            top_files=[],
            total_commits=0,
            total_insertions=0,
            total_deletions=0,
            avg_churn_per_commit=0.0,
            high_churn_files=0,
            error="No commits in the specified time range",
        )

    # Get per-file stats using git log --numstat
    r = subprocess.run(
        ["git", "log", "--numstat", "--format=", f"--since={since}"],
        capture_output=True,
        text=True,
        cwd=repo_path,
    )

    if r.returncode != 0:
        return CodeChurnResult(
            top_files=[],
            total_commits=0,
            total_insertions=0,
            total_deletions=0,
            avg_churn_per_commit=0.0,
            high_churn_files=0,
            error=r.stderr.strip()[:200],
        )

    # Parse numstat output: each line is "insertions\tdeletions\tfilepath"
    file_stats: dict[str, dict] = {}
    total_insertions = 0
    total_deletions = 0

    for line in r.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        ins_str, del_str, filepath = parts
        # Binary files show as "-"
        if ins_str == "-" or del_str == "-":
            continue
        try:
            ins = int(ins_str)
            dele = int(del_str)
        except ValueError:
            continue

        total_insertions += ins
        total_deletions += dele

        if filepath not in file_stats:
            file_stats[filepath] = {"commits": 0, "insertions": 0, "deletions": 0}
        # We count per-occurrence as a commit touch
        file_stats[filepath]["commits"] += 1
        file_stats[filepath]["insertions"] += ins
        file_stats[filepath]["deletions"] += dele

    # Count total commits
    commit_count_str = _git(["rev-list", "--count", "HEAD", f"--since={since}"], cwd=repo_path)
    try:
        total_commits = int(commit_count_str)
    except ValueError:
        total_commits = 0

    # Build FileChurn objects
    churn_list: list[FileChurn] = []
    for filepath, stats in file_stats.items():
        commits = stats["commits"]
        ins = stats["insertions"]
        dele = stats["deletions"]
        churn_score = (ins + dele) / commits if commits > 0 else 0.0
        churn_list.append(
            FileChurn(
                path=filepath,
                commits=commits,
                insertions=ins,
                deletions=dele,
                churn_score=round(churn_score, 1),
            )
        )

    # Sort by total lines changed descending
    churn_list.sort(key=lambda f: f.total_lines_changed, reverse=True)
    top_files = churn_list[:top_n]
    high_churn_files = sum(1 for f in churn_list if f.churn_score > high_churn_threshold)

    avg_churn = (total_insertions + total_deletions) / total_commits if total_commits > 0 else 0.0

    return CodeChurnResult(
        top_files=top_files,
        total_commits=total_commits,
        total_insertions=total_insertions,
        total_deletions=total_deletions,
        avg_churn_per_commit=round(avg_churn, 1),
        high_churn_files=high_churn_files,
    )
