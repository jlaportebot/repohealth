"""Check: stale commits — how long since the last commit."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime, UTC


@dataclass
class LastCommitResult:
    """Result of last-commit recency check."""

    last_commit_date: str
    days_since_last_commit: int


def check(repo_path: str | None = None) -> LastCommitResult:
    """Return days since the last commit."""
    r = subprocess.run(
        ["git", "log", "-1", "--format=%cI"],
        capture_output=True,
        text=True,
        cwd=repo_path,
    )
    if r.returncode != 0 or not r.stdout.strip():
        return LastCommitResult(last_commit_date="unknown", days_since_last_commit=-1)

    iso = r.stdout.strip()
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        now = datetime.now(UTC)
        days = (now - dt).days
        # Handle edge case where commit timestamp is slightly in the future
        # (can happen in fast CI environments due to clock precision)
        if days < 0:
            days = 0
        return LastCommitResult(last_commit_date=iso[:10], days_since_last_commit=days)
    except (ValueError, TypeError):
        return LastCommitResult(last_commit_date=iso[:10], days_since_last_commit=-1)
