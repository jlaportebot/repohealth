"""Check: commit message conventions — conventional commits, format compliance."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional


# Conventional commit pattern: type(scope)!: description
CONVENTIONAL_RE = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)"
    r"(\([^)]+\))?"
    r"(!)?"
    r":\s.+"
)

# Common bad patterns
NO_PERIOD_END_RE = re.compile(r"^[^.]+\.$")  # ends with period
LONG_LINE_RE = re.compile(r"^.{73,}")  # subject line > 72 chars

# Git trailer pattern (Signed-off-by, Co-authored-by, etc.)
TRAILER_RE = re.compile(r"^[A-Z][a-z]+-by:.*")


@dataclass
class CommitMessage:
    """A single commit message with its analysis."""

    hash: str
    subject: str
    is_conventional: bool
    is_long_subject: bool
    ends_with_period: bool
    has_trailer: bool
    is_empty: bool
    body_lines: int

    @property
    def is_compliant(self) -> bool:
        """Check if commit follows conventional commit format."""
        return self.is_conventional and not self.is_long_subject and not self.ends_with_period


@dataclass
class CommitConventionsResult:
    """Result of commit-conventions check."""

    total_commits: int
    conventional_count: int
    long_subject_count: int
    period_end_count: int
    trailer_count: int
    empty_message_count: int
    compliance_rate: float  # 0.0 - 1.0
    sample_non_compliant: List[CommitMessage]
    error: Optional[str] = None


def _git(args: List[str], cwd: str | None = None) -> str:
    r = subprocess.run(["git"] + args, capture_output=True, text=True, cwd=cwd)
    return r.stdout.strip()


def check(
    repo_path: str | None = None,
    since: str = "3 months ago",
    sample_n: int = 5,
) -> CommitConventionsResult:
    """Check commit message conventions.

    Analyzes recent commits for:
    - Conventional commit format compliance
    - Subject line length (<=72 chars)
    - Trailing periods in subjects
    - Presence of git trailers
    - Empty messages
    """
    # Get commit log with hash and subject
    r = subprocess.run(
        ["git", "log", f"--since={since}", "--format=%H|%s|%b"],
        capture_output=True,
        text=True,
        cwd=repo_path,
    )

    if r.returncode != 0:
        return CommitConventionsResult(
            total_commits=0, conventional_count=0, long_subject_count=0,
            period_end_count=0, trailer_count=0, empty_message_count=0,
            compliance_rate=0.0, sample_non_compliant=[],
            error=r.stderr.strip()[:200],
        )

    if not r.stdout.strip():
        return CommitConventionsResult(
            total_commits=0, conventional_count=0, long_subject_count=0,
            period_end_count=0, trailer_count=0, empty_message_count=0,
            compliance_rate=0.0, sample_non_compliant=[],
            error="No commits found in range",
        )

    commits: List[CommitMessage] = []
    non_compliant_samples: List[CommitMessage] = []

    for line in r.stdout.strip().splitlines():
        parts = line.split("|", 2)
        if len(parts) < 2:
            continue
        commit_hash = parts[0]
        subject = parts[1]
        body = parts[2] if len(parts) > 2 else ""

        is_empty = len(subject.strip()) == 0
        is_conventional = bool(CONVENTIONAL_RE.match(subject))
        is_long = bool(LONG_LINE_RE.match(subject))
        ends_period = bool(NO_PERIOD_END_RE.match(subject)) and not is_empty

        # Check for trailers in body
        body_lines_list = body.strip().splitlines() if body.strip() else []
        has_trailer = any(TRAILER_RE.match(bl) for bl in body_lines_list)
        body_count = len([bl for bl in body_lines_list if bl.strip()])

        msg = CommitMessage(
            hash=commit_hash[:7],
            subject=subject[:80],
            is_conventional=is_conventional,
            is_long_subject=is_long,
            ends_with_period=ends_period,
            has_trailer=has_trailer,
            is_empty=is_empty,
            body_lines=body_count,
        )
        commits.append(msg)

        if not msg.is_compliant and len(non_compliant_samples) < sample_n:
            non_compliant_samples.append(msg)

    total = len(commits)
    conventional = sum(1 for c in commits if c.is_conventional)
    long_subject = sum(1 for c in commits if c.is_long_subject)
    period_end = sum(1 for c in commits if c.ends_with_period)
    trailers = sum(1 for c in commits if c.has_trailer)
    empty = sum(1 for c in commits if c.is_empty)

    compliance = conventional / total if total > 0 else 0.0

    return CommitConventionsResult(
        total_commits=total,
        conventional_count=conventional,
        long_subject_count=long_subject,
        period_end_count=period_end,
        trailer_count=trailers,
        empty_message_count=empty,
        compliance_rate=round(compliance, 3),
        sample_non_compliant=non_compliant_samples,
    )
