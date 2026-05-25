"""Check: detect stale local branches merged into the default branch."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import List


@dataclass
class StaleBranchResult:
    """Result of stale-branch check."""

    default_branch: str
    stale_branches: List[str]
    max_stale_age_days: int


def _git(args: List[str], cwd: str | None = None) -> str:
    r = subprocess.run(["git"] + args, capture_output=True, text=True, cwd=cwd)
    return r.stdout.strip()


def get_default_branch(repo_path: str | None = None) -> str:
    """Return the repo's default branch name (main or master)."""
    remote = _git(["symbolic-ref", "refs/remotes/origin/HEAD"], cwd=repo_path)
    if remote:
        return remote.split("/")[-1]
    # fallback: check local HEAD
    head = _git(["symbolic-ref", "HEAD"], cwd=repo_path)
    return head.split("/")[-1] if head else "main"


def list_merged_branches(repo_path: str | None = None) -> List[str]:
    """Return local branches that have been merged into the default branch."""
    default = get_default_branch(repo_path)
    out = _git(["branch", "--merged", default], cwd=repo_path)
    branches = []
    for line in out.splitlines():
        name = line.strip().lstrip("* ").strip()
        if name and name != default:
            branches.append(name)
    return branches


def list_local_branches(repo_path: str | None = None) -> List[str]:
    """Return all local branch names."""
    out = _git(["branch"], cwd=repo_path)
    branches = []
    for line in out.splitlines():
        name = line.strip().lstrip("* ").strip()
        if name:
            branches.append(name)
    return branches


def check(repo_path: str | None = None) -> StaleBranchResult:
    """Return stale branches (merged into default)."""
    default = get_default_branch(repo_path)
    stale = list_merged_branches(repo_path)
    return StaleBranchResult(
        default_branch=default,
        stale_branches=stale,
        max_stale_age_days=0,
    )
