"""Check: detect uncommitted changes (dirty working tree)."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import List


@dataclass
class DirtyTreeResult:
    """Result of working-tree check."""

    has_unstaged: bool
    has_uncommitted: bool
    has_untracked: bool
    untracked_files: list[str]
    is_dirty: bool


def check(repo_path: str | None = None) -> DirtyTreeResult:
    """Check the working tree for uncommitted changes."""
    r = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        cwd=repo_path,
    )
    lines = r.stdout.strip().splitlines() if r.stdout.strip() else []

    has_unstaged = False
    has_uncommitted = False
    has_untracked = False
    untracked_files: list[str] = []

    for line in lines:
        xy = line[:2]
        path = line[3:]
        if xy[0] == "?":
            has_untracked = True
            untracked_files.append(path)
        if xy[0] in ("M", "D", "A", "R", "C"):
            has_uncommitted = True
        if xy[1] in ("M", "D"):
            has_unstaged = True

    return DirtyTreeResult(
        has_unstaged=has_unstaged,
        has_uncommitted=has_uncommitted,
        has_untracked=has_untracked,
        untracked_files=untracked_files,
        is_dirty=has_unstaged or has_uncommitted or has_untracked,
    )
