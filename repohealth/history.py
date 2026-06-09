"""History tracking — store and compare health reports over time."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


# Default history directory
DEFAULT_HISTORY_DIR = ".repohealth_history"


@dataclass
class HistoryEntry:
    """A single health report snapshot."""

    timestamp: str  # ISO 8601
    path: str
    score: int
    grade: str
    checks: List[Dict[str, Any]]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "path": self.path,
            "score": self.score,
            "grade": self.grade,
            "checks": self.checks,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HistoryEntry":
        return cls(
            timestamp=data.get("timestamp", ""),
            path=data.get("path", ""),
            score=data.get("score", 0),
            grade=data.get("grade", ""),
            checks=data.get("checks", []),
            metadata=data.get("metadata", {}),
        )


@dataclass
class HistoryDiff:
    """Difference between two history entries."""

    earlier: HistoryEntry
    later: HistoryEntry
    score_delta: int
    grade_changed: bool
    check_deltas: Dict[str, int]  # check name -> score delta
    improved: List[str]
    regressed: List[str]
    new_checks: List[str]
    removed_checks: List[str]


def _history_dir(repo_path: str) -> Path:
    """Get the history directory for a repo."""
    return Path(repo_path) / DEFAULT_HISTORY_DIR


def save_report(
    report_data: Dict[str, Any],
    repo_path: str = ".",
) -> Path:
    """Save a health report to history.

    Args:
        report_data: The report dict (from JSON output mode).
        repo_path: Path to the repository.

    Returns:
        Path to the saved file.
    """
    hist_dir = _history_dir(repo_path)
    hist_dir.mkdir(exist_ok=True)

    # Also create .gitignore for history dir
    gitignore = hist_dir / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("# repohealth history data\n*\n!.gitignore\n")

    now = datetime.now(timezone.utc)
    # Use microseconds to ensure unique filenames when saving rapidly
    filename = f"report_{now.strftime('%Y%m%d_%H%M%S')}_{now.microsecond:06d}.json"
    filepath = hist_dir / filename

    # Add timestamp if not present
    if "timestamp" not in report_data:
        report_data["timestamp"] = now.isoformat()

    filepath.write_text(json.dumps(report_data, indent=2, sort_keys=True))
    return filepath


def load_history(repo_path: str = ".", limit: int = 50) -> List[HistoryEntry]:
    """Load history entries from the history directory.

    Returns entries sorted by timestamp (oldest first).
    """
    hist_dir = _history_dir(repo_path)
    if not hist_dir.exists():
        return []

    entries: List[HistoryEntry] = []
    for filepath in sorted(hist_dir.glob("report_*.json")):
        try:
            data = json.loads(filepath.read_text())
            entries.append(HistoryEntry.from_dict(data))
        except (json.JSONDecodeError, OSError):
            continue

    # Sort by timestamp
    entries.sort(key=lambda e: e.timestamp)
    return entries[-limit:]


def compare_entries(earlier: HistoryEntry, later: HistoryEntry) -> HistoryDiff:
    """Compare two history entries and compute the diff."""
    score_delta = later.score - earlier.score
    grade_changed = earlier.grade != later.grade

    # Build check lookup dicts
    earlier_checks = {
        c["name"]: c.get("score", 0) for c in earlier.checks if isinstance(c, dict)
    }
    later_checks = {
        c["name"]: c.get("score", 0) for c in later.checks if isinstance(c, dict)
    }

    # Compute deltas
    check_deltas: Dict[str, int] = {}
    improved: List[str] = []
    regressed: List[str] = []
    new_checks: List[str] = []
    removed_checks: List[str] = []

    all_names = set(earlier_checks.keys()) | set(later_checks.keys())

    for name in sorted(all_names):
        old_score = earlier_checks.get(name)
        new_score = later_checks.get(name)

        if old_score is None and new_score is not None:
            new_checks.append(name)
            check_deltas[name] = new_score
        elif new_score is None and old_score is not None:
            removed_checks.append(name)
            check_deltas[name] = -old_score
        elif old_score is not None and new_score is not None:
            delta = new_score - old_score
            check_deltas[name] = delta
            if delta > 0:
                improved.append(name)
            elif delta < 0:
                regressed.append(name)

    return HistoryDiff(
        earlier=earlier,
        later=later,
        score_delta=score_delta,
        grade_changed=grade_changed,
        check_deltas=check_deltas,
        improved=improved,
        regressed=regressed,
        new_checks=new_checks,
        removed_checks=removed_checks,
    )


def get_trend(entries: List[HistoryEntry]) -> str:
    """Compute the overall trend from history entries.

    Returns: "improving", "stable", "declining", "insufficient"
    """
    if len(entries) < 2:
        return "insufficient"

    # Look at last 5 entries
    recent = entries[-5:]
    scores = [e.score for e in recent]

    if len(scores) < 2:
        return "insufficient"

    # Simple linear regression slope
    n = len(scores)
    x_mean = (n - 1) / 2
    y_mean = sum(scores) / n

    numerator = sum((i - x_mean) * (scores[i] - y_mean) for i in range(n))
    denominator = sum((i - x_mean) ** 2 for i in range(n))

    if denominator == 0:
        return "stable"

    slope = numerator / denominator

    if slope > 2:
        return "improving"
    elif slope < -2:
        return "declining"
    else:
        return "stable"


def prune_history(repo_path: str = ".", keep: int = 100) -> int:
    """Remove oldest history entries, keeping only the most recent `keep`.

    Returns the number of entries removed.
    """
    hist_dir = _history_dir(repo_path)
    if not hist_dir.exists():
        return 0

    files = sorted(hist_dir.glob("report_*.json"))
    if len(files) <= keep:
        return 0

    to_remove = files[:-keep]
    removed = 0
    for f in to_remove:
        try:
            f.unlink()
            removed += 1
        except OSError:
            continue

    return removed
