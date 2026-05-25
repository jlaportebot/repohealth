"""Tests for repohealth."""

import json
import subprocess
import tempfile
from pathlib import Path

import pytest


@pytest.fixture()
def git_repo(tmp_path: Path):
    """Create a minimal git repo for testing."""
    subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), check=True, capture_output=True)
    readme = tmp_path / "README.md"
    readme.write_text("# Test\n")
    lic = tmp_path / "LICENSE"
    lic.write_text("MIT\n")
    gi = tmp_path / ".gitignore"
    gi.write_text("__pycache__/\n")
    subprocess.run(["git", "add", "."], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), check=True, capture_output=True)
    return tmp_path


def test_cli_basic(git_repo):
    """repohealth runs on a healthy repo and exits 0."""
    r = subprocess.run(
        ["python3", "-m", "repohealth.cli", str(git_repo)],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0
    assert "Score" in r.stdout


def test_cli_json(git_repo):
    """repohealth --json-output returns valid JSON."""
    r = subprocess.run(
        ["python3", "-m", "repohealth.cli", str(git_repo), "--json-output"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert "score" in data
    assert "grade" in data
    assert 0 <= data["score"] <= 100


def test_dirty_tree_clean(git_repo):
    from repohealth.dirty_tree import check

    result = check(str(git_repo))
    assert not result.is_dirty


def test_dirty_tree_untracked(git_repo):
    from repohealth.dirty_tree import check

    (git_repo / "newfile.py").write_text("x = 1\n")
    result = check(str(git_repo))
    assert result.is_dirty
    assert result.has_untracked


def test_essentials(git_repo):
    from repohealth.essentials import check

    result = check(str(git_repo))
    assert "README" in result.present
    assert "LICENSE" in result.present
    assert ".gitignore" in result.present


def test_essentials_missing(tmp_path):
    from repohealth.essentials import check

    result = check(str(tmp_path))
    assert "README" in result.missing
    assert "LICENSE" in result.missing


def test_last_commit(git_repo):
    from repohealth.last_commit import check

    result = check(str(git_repo))
    assert result.days_since_last_commit >= 0


def test_stale_branches_clean(git_repo):
    from repohealth.stale_branches import check

    result = check(str(git_repo))
    # Only default branch, no stale
    assert len(result.stale_branches) == 0


def test_scoring_perfect():
    from repohealth.dirty_tree import DirtyTreeResult
    from repohealth.essentials import EssentialsResult
    from repohealth.large_files import LargeFilesResult
    from repohealth.last_commit import LastCommitResult
    from repohealth.outdated_deps import OutdatedDepsResult
    from repohealth.scoring import aggregate
    from repohealth.stale_branches import StaleBranchResult

    report = aggregate(
        path="/tmp/test",
        dirty=DirtyTreeResult(False, False, False, [], False),
        stale=StaleBranchResult("main", [], 0),
        essentials=EssentialsResult(missing=[], present=["README", "LICENSE", ".gitignore", "CI"]),
        deps=OutdatedDepsResult(source="pyproject.toml", outdated=[]),
        large=LargeFilesResult(threshold_kb=1024, large_files=[]),
        activity=LastCommitResult(last_commit_date="2026-05-25", days_since_last_commit=0),
    )
    assert report.score == 100
    assert report.grade == "A"
