"""Check: PR review metrics — review coverage, time to merge, stale PRs."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class PRMetrics:
    """Metrics for a single PR."""

    number: int
    title: str
    state: str  # "open", "merged", "closed"
    age_days: int
    review_count: int
    comment_count: int
    additions: int
    deletions: int
    changed_files: int
    days_to_merge: Optional[int]  # None if still open


@dataclass
class PRReviewResult:
    """Result of PR review analysis."""

    total_prs: int
    open_prs: int
    merged_prs: int
    closed_without_merge: int
    avg_reviews_per_pr: float
    avg_days_to_merge: float
    stale_prs: int  # open PRs older than 30 days
    unreviewed_prs: int  # open PRs with 0 reviews
    large_prs: int  # PRs with > 400 line changes
    recent_prs: List[PRMetrics]
    error: Optional[str] = None


def _gh(args: List[str], cwd: str | None = None) -> str:
    r = subprocess.run(["gh"] + args, capture_output=True, text=True, cwd=cwd)
    return r.stdout.strip()


def check(
    repo_path: str | None = None,
    stale_threshold_days: int = 30,
    large_pr_threshold: int = 400,
    recent_n: int = 10,
) -> PRReviewResult:
    """Analyze PR review metrics using gh CLI.

    Requires 'gh' to be authenticated and the repo to have a remote on GitHub.
    """
    # Determine the remote URL
    r = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        cwd=repo_path,
    )
    if r.returncode != 0:
        return PRReviewResult(
            total_prs=0,
            open_prs=0,
            merged_prs=0,
            closed_without_merge=0,
            avg_reviews_per_pr=0.0,
            avg_days_to_merge=0.0,
            stale_prs=0,
            unreviewed_prs=0,
            large_prs=0,
            recent_prs=[],
            error="No GitHub remote found",
        )

    remote = r.stdout.strip()
    # Parse owner/repo from remote URL
    if remote.startswith("https://github.com/"):
        parts = remote.rstrip(".git").split("/")[-2:]
    elif remote.startswith("git@github.com:"):
        parts = remote.rstrip(".git").split(":")[-1].split("/")[-2:]
    else:
        return PRReviewResult(
            total_prs=0,
            open_prs=0,
            merged_prs=0,
            closed_without_merge=0,
            avg_reviews_per_pr=0.0,
            avg_days_to_merge=0.0,
            stale_prs=0,
            unreviewed_prs=0,
            large_prs=0,
            recent_prs=[],
            error="Not a GitHub repository",
        )

    repo_slug = "/".join(parts)

    # Fetch recent PRs via gh api
    api_result = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{repo_slug}/pulls",
            "--method",
            "GET",
            "-f",
            "state=all",
            "-f",
            "per_page=50",
            "-f",
            "sort=updated",
            "-f",
            "direction=desc",
            "--jq",
            '.[] | "{number}\t{title}\t{state}\t{created_at}\t{merged_at}\t{review_comments}\t{comments}\t{additions}\t{deletions}\t{changed_files}"',
        ],
        capture_output=True,
        text=True,
        cwd=repo_path,
    )

    if api_result.returncode != 0:
        return PRReviewResult(
            total_prs=0,
            open_prs=0,
            merged_prs=0,
            closed_without_merge=0,
            avg_reviews_per_pr=0.0,
            avg_days_to_merge=0.0,
            stale_prs=0,
            unreviewed_prs=0,
            large_prs=0,
            recent_prs=[],
            error=f"gh api failed: {api_result.stderr.strip()[:200]}",
        )

    from datetime import datetime, timezone

    prs: List[PRMetrics] = []
    open_count = 0
    merged_count = 0
    closed_no_merge = 0
    total_reviews = 0
    days_to_merge_list: List[int] = []
    stale = 0
    unreviewed = 0
    large = 0

    for line in api_result.stdout.strip().splitlines():
        fields = line.split("\t")
        if len(fields) != 10:
            continue
        try:
            number = int(fields[0])
            title = fields[1]
            state = fields[2]
            created_at = fields[3]
            merged_at = fields[4]
            review_comments = int(fields[5])
            comments = int(fields[6])
            additions = int(fields[7])
            deletions = int(fields[8])
            changed_files = int(fields[9])
        except (ValueError, IndexError):
            continue

        # Compute age in days
        try:
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            age_days = (now - created).days
        except (ValueError, AttributeError):
            age_days = 0

        # Days to merge
        days_to_merge = None
        if merged_at and merged_at != "None" and merged_at != "null":
            try:
                merged_dt = datetime.fromisoformat(merged_at.replace("Z", "+00:00"))
                created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                days_to_merge = (merged_dt - created).days
                days_to_merge_list.append(days_to_merge)
            except (ValueError, AttributeError):
                pass

        pr = PRMetrics(
            number=number,
            title=title[:60],
            state=state,
            age_days=age_days,
            review_count=review_comments + comments,
            comment_count=comments,
            additions=additions,
            deletions=deletions,
            changed_files=changed_files,
            days_to_merge=days_to_merge,
        )
        prs.append(pr)

        if state == "open":
            open_count += 1
            if age_days > stale_threshold_days:
                stale += 1
            if review_comments == 0 and comments == 0:
                unreviewed += 1
        elif state == "closed" and merged_at and merged_at != "None":
            merged_count += 1
        else:
            closed_no_merge += 1

        total_reviews += review_comments + comments
        if (additions + deletions) > large_pr_threshold:
            large += 1

    total = len(prs)
    avg_reviews = total_reviews / total if total > 0 else 0.0
    avg_merge = (
        sum(days_to_merge_list) / len(days_to_merge_list) if days_to_merge_list else 0.0
    )

    return PRReviewResult(
        total_prs=total,
        open_prs=open_count,
        merged_prs=merged_count,
        closed_without_merge=closed_no_merge,
        avg_reviews_per_pr=round(avg_reviews, 1),
        avg_days_to_merge=round(avg_merge, 1),
        stale_prs=stale,
        unreviewed_prs=unreviewed,
        large_prs=large,
        recent_prs=prs[:recent_n],
    )
