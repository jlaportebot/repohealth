"""Check: stale commits — how long since the last commit."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class LastCommitResult:
    """Result of last-commit recency check."""

    last_commit_date: str
    days_since_last_commit: int


def _parse_iso_datetime(iso: str) -> datetime | None:
    """Parse ISO datetime string with Python 3.10 compatibility."""
    try:
        # Python 3.11+ supports Z suffix; 3.10 requires +00:00
        if iso.endswith("Z"):
            iso = iso[:-1] + "+00:00"
        return datetime.fromisoformat(iso)
    except (ValueError, TypeError):
        # Fallback: parse without timezone
        try:
            return datetime.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S")
        except (ValueError, TypeError):
            return None


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
    dt = _parse_iso_datetime(iso)
    if dt is None:
        return LastCommitResult(last_commit_date=iso[:10], days_since_last_commit=-1)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    days = (now - dt).days
    # Handle edge case where commit timestamp is slightly in the future
    # (can happen in fast CI environments due to clock precision)
    if days < 0:
        days = 0
    return LastCommitResult(last_commit_date=iso[:10], days_since_last_commit=days)
