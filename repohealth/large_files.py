"""Check: large files in the repo (potential bloat)."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import List


@dataclass
class LargeFile:
    """A file exceeding the size threshold."""

    path: str
    size_kb: int


@dataclass
class LargeFilesResult:
    """Result of large-files check."""

    threshold_kb: int
    large_files: list[LargeFile]


def check(repo_path: str | None = None, threshold_kb: int = 1024) -> LargeFilesResult:
    """Find files in the working tree exceeding *threshold_kb*."""
    r = subprocess.run(
        ["git", "ls-files", "-z"],
        capture_output=True,
        text=True,
        cwd=repo_path,
    )
    if r.returncode != 0 or not r.stdout:
        return LargeFilesResult(threshold_kb=threshold_kb, large_files=[])

    # Use find with -size for efficiency
    files = [f for f in r.stdout.split("\0") if f]
    large: list[LargeFile] = []
    for f in files:
        try:
            r2 = subprocess.run(
                ["stat", "--format=%s", f],
                capture_output=True,
                text=True,
                cwd=repo_path,
            )
            if r2.returncode == 0 and r2.stdout.strip().isdigit():
                size_kb = int(r2.stdout.strip()) // 1024
                if size_kb >= threshold_kb:
                    large.append(LargeFile(path=f, size_kb=size_kb))
        except (ValueError, OSError):
            continue

    return LargeFilesResult(threshold_kb=threshold_kb, large_files=large)
