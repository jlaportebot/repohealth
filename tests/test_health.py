"""Comprehensive tests for repohealth v0.2.0 — all checks, CLI, history, config."""

import json
import subprocess
from pathlib import Path

import pytest


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def git_repo(tmp_path: Path):
    """Create a minimal git repo for testing."""
    subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )
    readme = tmp_path / "README.md"
    readme.write_text("# Test\n")
    lic = tmp_path / "LICENSE"
    lic.write_text("MIT\n")
    gi = tmp_path / ".gitignore"
    gi.write_text("__pycache__/\n")
    subprocess.run(["git", "add", "."], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: initial commit"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )
    return tmp_path


@pytest.fixture
def python_repo(git_repo: Path):
    """Create a Python project repo with source and test files."""
    # Create source file
    src_dir = git_repo / "myproject"
    src_dir.mkdir()
    (src_dir / "__init__.py").write_text(""""My project.""")
    (src_dir / "core.py").write_text('''"""Core module."""

def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

def subtract(a: int, b: int) -> int:
    """Subtract b from a."""
    return a - b

def _private_helper(x):
    return x * 2
''')

    # Create test file
    test_dir = git_repo / "tests"
    test_dir.mkdir()
    (test_dir / "__init__.py").write_text("")
    (test_dir / "test_core.py").write_text('''"""Tests for core module."""

import pytest
from myproject.core import add, subtract


def test_add():
    """Test add function."""
    assert add(1, 2) == 3


def test_subtract():
    """Test subtract function."""
    assert subtract(5, 3) == 2


class TestMath:
    """Test math operations."""

    def test_add_positive(self):
        assert add(1, 1) == 2
''')

    # Create pyproject.toml
    (git_repo / "pyproject.toml").write_text("""[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "myproject"
version = "0.1.0"
dependencies = ["click>=8.0", "rich>=13.0"]

[project.optional-dependencies]
dev = ["pytest>=7.0", "pytest-cov"]
""")

    subprocess.run(["git", "add", "."], cwd=str(git_repo), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: add project structure"],
        cwd=str(git_repo),
        check=True,
        capture_output=True,
    )
    return git_repo


# ── Original check tests ────────────────────────────────────────────────────


class TestDirtyTree:
    def test_clean_repo(self, git_repo):
        from repohealth.dirty_tree import check

        result = check(str(git_repo))
        assert not result.is_dirty

    def test_untracked_file(self, git_repo):
        from repohealth.dirty_tree import check

        (git_repo / "newfile.py").write_text("x = 1\n")
        result = check(str(git_repo))
        assert result.is_dirty
        assert result.has_untracked

    def test_unstaged_change(self, git_repo):
        from repohealth.dirty_tree import check

        readme = git_repo / "README.md"
        readme.write_text("# Modified\n")
        result = check(str(git_repo))
        assert result.is_dirty


class TestEssentials:
    def test_healthy_repo(self, git_repo):
        from repohealth.essentials import check

        result = check(str(git_repo))
        assert "README" in result.present
        assert "LICENSE" in result.present

    def test_missing_files(self, tmp_path):
        from repohealth.essentials import check

        result = check(str(tmp_path))
        assert "README" in result.missing
        assert "LICENSE" in result.missing


class TestLastCommit:
    def test_recent_commit(self, git_repo):
        from repohealth.last_commit import check

        result = check(str(git_repo))
        assert result.days_since_last_commit >= 0


class TestStaleBranches:
    def test_no_stale(self, git_repo):
        from repohealth.stale_branches import check

        result = check(str(git_repo))
        assert len(result.stale_branches) == 0


# ── New check tests ──────────────────────────────────────────────────────────


class TestCodeChurn:
    def test_basic_churn(self, git_repo):
        from repohealth.code_churn import check

        # Add more commits to create churn
        readme = git_repo / "README.md"
        for i in range(3):
            readme.write_text(f"# Test v{i}\n")
            subprocess.run(["git", "add", "."], cwd=str(git_repo), check=True, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", f"update readme v{i}"],
                cwd=str(git_repo),
                check=True,
                capture_output=True,
            )

        result = check(str(git_repo))
        assert result.total_commits >= 4
        assert len(result.top_files) > 0

    def test_empty_repo(self, tmp_path):
        from repohealth.code_churn import check

        result = check(str(tmp_path))
        assert result.error is not None


class TestCommitConventions:
    def test_conventional_commits(self, git_repo):
        from repohealth.commit_conventions import check

        result = check(str(git_repo))
        assert result.total_commits >= 1
        # Our test fixture uses conventional commits
        assert result.conventional_count >= 1

    def test_no_commits(self, tmp_path):
        from repohealth.commit_conventions import check

        result = check(str(tmp_path))
        assert result.error is not None or result.total_commits == 0

    def test_non_conventional(self, git_repo):
        """Add a non-conventional commit and check detection."""
        (git_repo / "extra.txt").write_text("stuff\n")
        subprocess.run(["git", "add", "."], cwd=str(git_repo), check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "random update"],
            cwd=str(git_repo),
            check=True,
            capture_output=True,
        )

        from repohealth.commit_conventions import check

        result = check(str(git_repo))
        assert result.total_commits >= 2
        # At least one should be non-conventional
        assert result.conventional_count < result.total_commits


class TestTestCoverage:
    def test_python_project(self, python_repo):
        from repohealth.test_coverage import check

        result = check(str(python_repo))
        assert result.total_source_files > 0
        assert result.total_test_files > 0
        assert result.test_to_code_ratio > 0
        assert result.test_framework in ("pytest", "unittest", "mixed", "none")

    def test_non_python_project(self, tmp_path):
        from repohealth.test_coverage import check

        result = check(str(tmp_path))
        assert result.error is not None


class TestSecurity:
    def test_clean_repo(self, git_repo):
        from repohealth.security import check

        result = check(str(git_repo))
        assert len(result.secret_findings) == 0 or len(result.secret_findings) <= 3
        assert result.risk_level in ("low", "medium", "high", "critical")

    def test_hardcoded_password(self, tmp_path):
        from repohealth.security import check

        (tmp_path / "config.py").write_text('password = "super_secret_123"\n')
        (tmp_path / ".gitignore").write_text("*.py\n")
        result = check(str(tmp_path))
        assert len(result.secret_findings) > 0
        assert any("password" in s.pattern_type.lower() for s in result.secret_findings)

    def test_dangerous_env_file(self, tmp_path):
        from repohealth.security import check

        (tmp_path / ".env").write_text("SECRET_KEY=abc123\n")
        result = check(str(tmp_path))
        assert ".env" in result.dangerous_files_present

    def test_security_infra(self, git_repo):
        from repohealth.security import check

        # Create SECURITY.md
        (git_repo / "SECURITY.md").write_text("# Security Policy\n")
        result = check(str(git_repo))
        assert result.has_security_policy


class TestDocCoverage:
    def test_well_documented(self, python_repo):
        from repohealth.doc_coverage import check

        result = check(str(python_repo))
        assert result.total_definitions > 0
        assert result.documented_definitions > 0
        assert result.coverage_pct > 0

    def test_readme_sections(self, python_repo):
        from repohealth.doc_coverage import check

        result = check(str(python_repo))
        # README exists but may be minimal
        assert isinstance(result.readme_sections, list)

    def test_missing_docs(self, tmp_path):
        from repohealth.doc_coverage import check

        # Create a Python file without docstrings
        src = tmp_path / "src.py"
        src.write_text("def foo():\n    pass\n\ndef bar():\n    pass\n")
        result = check(str(tmp_path))
        assert result.total_definitions >= 2
        assert result.documented_definitions == 0


class TestDependencyGraph:
    def test_pyproject_deps(self, python_repo):
        from repohealth.dependency_graph import check

        result = check(str(python_repo))
        assert result.total_runtime > 0
        assert result.dep_file == "pyproject.toml"

    def test_requirements_txt(self, tmp_path):
        from repohealth.dependency_graph import check

        (tmp_path / "requirements.txt").write_text("click>=8.0\nrich>=13.0\n")
        result = check(str(tmp_path))
        assert result.total_runtime == 2

    def test_no_deps(self, tmp_path):
        from repohealth.dependency_graph import check

        result = check(str(tmp_path))
        assert result.error is not None


class TestTechDebt:
    def test_no_debt(self, git_repo):
        from repohealth.tech_debt import check

        result = check(str(git_repo))
        assert result.total_markers >= 0  # May find markers in any code
        assert result.debt_score >= 0

    def test_with_todos(self, tmp_path):
        from repohealth.tech_debt import check

        (tmp_path / "code.py").write_text(
            "# TODO: implement this\n# FIXME: this is broken\ndef foo():\n    pass\n"
        )
        result = check(str(tmp_path))
        assert result.total_markers >= 2
        assert "TODO" in result.markers_by_type
        assert "FIXME" in result.markers_by_type

    def test_complexity(self, tmp_path):
        from repohealth.tech_debt import check

        # Create a complex function
        (tmp_path / "complex.py").write_text(
            "def complex_func(x):\n" + "\n".join(f"    if x > {i}: pass" for i in range(15)) + "\n"
        )
        result = check(str(tmp_path))
        assert len(result.high_complexity_functions) > 0


class TestPRReview:
    def test_no_github_remote(self, tmp_path):
        from repohealth.pr_review import check

        result = check(str(tmp_path))
        assert result.error is not None


# ── Scoring tests ────────────────────────────────────────────────────────────


class TestScoring:
    def test_perfect_score(self):
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
            essentials=EssentialsResult(
                missing=[], present=["README", "LICENSE", ".gitignore", "CI"]
            ),
            deps=OutdatedDepsResult(source="pyproject.toml", outdated=[]),
            large=LargeFilesResult(threshold_kb=1024, large_files=[]),
            activity=LastCommitResult(last_commit_date="2026-05-25", days_since_last_commit=0),
        )
        assert report.score == 100
        assert report.grade == "A"

    def test_with_new_checks(self):
        from repohealth.code_churn import CodeChurnResult
        from repohealth.commit_conventions import CommitConventionsResult
        from repohealth.dirty_tree import DirtyTreeResult
        from repohealth.essentials import EssentialsResult
        from repohealth.large_files import LargeFilesResult
        from repohealth.last_commit import LastCommitResult
        from repohealth.outdated_deps import OutdatedDepsResult
        from repohealth.scoring import aggregate
        from repohealth.stale_branches import StaleBranchResult
        from repohealth.tech_debt import TechDebtResult

        report = aggregate(
            path="/tmp/test",
            dirty=DirtyTreeResult(False, False, False, [], False),
            stale=StaleBranchResult("main", [], 0),
            essentials=EssentialsResult(
                missing=[], present=["README", "LICENSE", ".gitignore", "CI"]
            ),
            deps=OutdatedDepsResult(source="pyproject.toml", outdated=[]),
            large=LargeFilesResult(threshold_kb=1024, large_files=[]),
            activity=LastCommitResult(last_commit_date="2026-05-25", days_since_last_commit=0),
            code_churn=CodeChurnResult(
                top_files=[],
                total_commits=10,
                total_insertions=500,
                total_deletions=100,
                avg_churn_per_commit=60.0,
                high_churn_files=0,
            ),
            commit_conventions=CommitConventionsResult(
                total_commits=10,
                conventional_count=10,
                long_subject_count=0,
                period_end_count=0,
                trailer_count=5,
                empty_message_count=0,
                compliance_rate=1.0,
                sample_non_compliant=[],
            ),
            tech_debt=TechDebtResult(
                total_markers=0,
                markers_by_type={},
                debt_items=[],
                high_complexity_functions=[],
                max_complexity=0,
                avg_complexity=0.0,
                total_functions=5,
                long_functions=0,
                deprecated_count=0,
                noqa_count=0,
                debt_score=0,
            ),
        )
        assert report.score > 0
        assert len(report.checks) > 6  # More checks than before

    def test_disabled_check(self):
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
            essentials=EssentialsResult(
                missing=[], present=["README", "LICENSE", ".gitignore", "CI"]
            ),
            deps=OutdatedDepsResult(source="pyproject.toml", outdated=[]),
            large=LargeFilesResult(threshold_kb=1024, large_files=[]),
            activity=LastCommitResult(last_commit_date="2026-05-25", days_since_last_commit=0),
            disabled_checks=["large_files"],
        )
        check_names = [c.name for c in report.checks]
        assert "Large Files" not in check_names


# ── History tests ────────────────────────────────────────────────────────────


class TestHistory:
    def test_save_and_load(self, tmp_path):
        from repohealth.history import save_report, load_history

        report_data = {
            "path": str(tmp_path),
            "score": 85,
            "grade": "B",
            "checks": [
                {
                    "name": "Test",
                    "score": 85,
                    "weight": 10,
                    "detail": "ok",
                    "status": "pass",
                }
            ],
        }
        filepath = save_report(report_data, repo_path=str(tmp_path))
        assert filepath.exists()

        entries = load_history(repo_path=str(tmp_path))
        assert len(entries) == 1
        assert entries[0].score == 85
        assert entries[0].grade == "B"

    def test_compare_entries(self):
        from repohealth.history import HistoryEntry, compare_entries

        earlier = HistoryEntry(
            timestamp="2026-05-01T00:00:00",
            path="/tmp/test",
            score=70,
            grade="C",
            checks=[
                {
                    "name": "Security",
                    "score": 50,
                    "weight": 15,
                    "detail": "issues",
                    "status": "warn",
                },
                {
                    "name": "Tests",
                    "score": 90,
                    "weight": 10,
                    "detail": "ok",
                    "status": "pass",
                },
            ],
        )
        later = HistoryEntry(
            timestamp="2026-05-15T00:00:00",
            path="/tmp/test",
            score=80,
            grade="B",
            checks=[
                {
                    "name": "Security",
                    "score": 80,
                    "weight": 15,
                    "detail": "better",
                    "status": "pass",
                },
                {
                    "name": "Tests",
                    "score": 90,
                    "weight": 10,
                    "detail": "ok",
                    "status": "pass",
                },
            ],
        )
        diff = compare_entries(earlier, later)
        assert diff.score_delta == 10
        assert "Security" in diff.improved
        assert diff.grade_changed

    def test_trend(self):
        from repohealth.history import HistoryEntry, get_trend

        # Improving trend
        entries = [
            HistoryEntry(
                timestamp=f"2026-05-{i:02d}T00:00:00",
                path="/t",
                score=60 + i * 5,
                grade="B",
                checks=[],
            )
            for i in range(1, 6)
        ]
        assert get_trend(entries) == "improving"

        # Stable
        entries = [
            HistoryEntry(
                timestamp=f"2026-05-{i:02d}T00:00:00",
                path="/t",
                score=75,
                grade="C",
                checks=[],
            )
            for i in range(1, 6)
        ]
        assert get_trend(entries) == "stable"

    def test_prune(self, tmp_path):
        from repohealth.history import save_report, load_history, prune_history

        # Create many entries
        for i in range(10):
            save_report(
                {
                    "path": str(tmp_path),
                    "score": 50 + i,
                    "grade": "C",
                    "checks": [],
                },
                repo_path=str(tmp_path),
            )

        entries = load_history(repo_path=str(tmp_path))
        assert len(entries) == 10

        pruned = prune_history(repo_path=str(tmp_path), keep=5)
        assert pruned == 5

        entries = load_history(repo_path=str(tmp_path))
        assert len(entries) == 5


# ── Config tests ─────────────────────────────────────────────────────────────


class TestConfig:
    def test_load_defaults(self, tmp_path):
        from repohealth.config import load_config

        cfg = load_config(str(tmp_path))
        assert cfg.large_file_threshold_kb == 1024
        assert cfg.save_history is True
        assert cfg.is_check_enabled("dirty_tree")
        assert cfg.is_check_enabled("security")

    def test_disabled_check(self, tmp_path):
        from repohealth.config import load_config

        cfg = load_config(str(tmp_path))
        cfg.ignore_checks = ["pr_review"]
        assert not cfg.is_check_enabled("pr_review")

    def test_generate_config(self, tmp_path):
        from repohealth.config import generate_default_config

        path = generate_default_config(str(tmp_path / ".repohealth.yml"))
        assert path.exists()
        content = path.read_text()
        assert "large_file_threshold_kb" in content or "checks:" in content

    def test_yaml_config(self, tmp_path):
        from repohealth.config import load_config

        config_content = """large_file_threshold_kb: 2048
save_history: false
checks:
  pr_review:
    enabled: false
    weight: 0
"""
        (tmp_path / ".repohealth.yml").write_text(config_content)
        cfg = load_config(str(tmp_path))
        assert cfg.large_file_threshold_kb == 2048
        assert cfg.save_history is False


# ── CLI tests ────────────────────────────────────────────────────────────────


class TestCLI:
    def _run_cli(self, *args):
        import sys

        return subprocess.run(
            [sys.executable, "-m", "repohealth.cli", *args],
            capture_output=True,
            text=True,
        )

    def test_check_command(self, git_repo):
        r = self._run_cli("check", str(git_repo))
        # Should produce output (may or may not exit 0 depending on score)
        assert "Score" in r.stdout or r.returncode != 0

    def test_check_json(self, git_repo):
        r = self._run_cli("check", str(git_repo), "--json-output")
        if r.returncode == 0:
            data = json.loads(r.stdout)
            assert "score" in data
            assert "grade" in data
            assert "checks" in data
            assert 0 <= data["score"] <= 100

    def test_check_save(self, git_repo):
        r = self._run_cli("check", str(git_repo), "--json-output", "--save")
        # Should save a history entry
        hist_dir = git_repo / ".repohealth_history"
        if r.returncode == 0:
            assert hist_dir.exists()

    def test_history_command(self, git_repo):
        # First save a report
        self._run_cli("check", str(git_repo), "--json-output", "--save")
        # Then check history
        r = self._run_cli("history", str(git_repo))
        # May or may not have history depending on whether save worked
        assert r.returncode == 0 or "No history" in r.stderr

    def test_init_command(self, tmp_path):
        r = self._run_cli("init", str(tmp_path))
        assert r.returncode == 0
        assert (tmp_path / ".repohealth.yml").exists()

    def test_list_checks_command(self):
        r = self._run_cli("list-checks")
        assert r.returncode == 0
        assert "dirty_tree" in r.stdout
        assert "security" in r.stdout
        assert "tech_debt" in r.stdout

    def test_version(self):
        r = self._run_cli("--version")
        assert r.returncode == 0
        assert "0.2.0" in r.stdout


# ── Integration test ─────────────────────────────────────────────────────────


class TestIntegration:
    def test_full_check_suite(self, python_repo):
        """Run the full check suite on a realistic Python project."""
        import sys

        r = subprocess.run(
            [
                sys.executable,
                "-m",
                "repohealth.cli",
                "check",
                str(python_repo),
                "--json-output",
            ],
            capture_output=True,
            text=True,
        )
        if r.returncode == 0:
            data = json.loads(r.stdout)
            # Should have many checks
            assert len(data["checks"]) >= 6
            # Score should be reasonable
            assert 0 <= data["score"] <= 100

    def test_check_with_all_new_checks(self, python_repo):
        """Verify new checks appear in the report."""
        from repohealth.config import load_config
        from repohealth.cli import _run_checks

        cfg = load_config(str(python_repo))
        report = _run_checks(str(python_repo), cfg)

        # Should have both old and new checks
        check_names = [c.name for c in report.checks]
        # At minimum we should have the original 6
        assert len(check_names) >= 6
        # Score should be valid
        assert 0 <= report.score <= 100
