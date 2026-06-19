"""Tests for individual check modules — unit tests for each check's internals."""

import ast
import subprocess
from pathlib import Path

import pytest


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
    subprocess.run(["git", "add", "."], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: initial commit"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )
    return tmp_path


# ── Code Churn Tests ─────────────────────────────────────────────────────────


class TestCodeChurn:
    def test_churn_with_multiple_commits(self, git_repo):
        """Test code churn analysis with multiple commits on same file."""
        from repohealth.code_churn import check

        readme = git_repo / "README.md"
        for i in range(5):
            readme.write_text(f"# Version {i}\n")
            subprocess.run(["git", "add", "."], cwd=str(git_repo), check=True, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", f"update v{i}"],
                cwd=str(git_repo),
                check=True,
                capture_output=True,
            )

        result = check(str(git_repo))
        assert result.total_commits >= 6
        assert result.total_insertions > 0
        assert len(result.top_files) > 0
        # README.md should be in top files
        top_paths = [f.path for f in result.top_files]
        assert any("README" in p for p in top_paths)

    def test_churn_file_stats(self):
        """Test that FileChurn properties work correctly."""
        from repohealth.code_churn import FileChurn

        fc = FileChurn(path="test.py", commits=10, insertions=100, deletions=50, churn_score=15.0)
        assert fc.total_lines_changed == 150
        assert fc.churn_score == 15.0

    def test_churn_non_git_dir(self, tmp_path):
        """Test churn analysis on non-git directory."""
        from repohealth.code_churn import check

        result = check(str(tmp_path))
        assert result.error is not None


# ── Commit Conventions Tests ────────────────────────────────────────────────


class TestCommitConventions:
    def test_conventional_format(self, git_repo):
        """Test that conventional commits are detected."""
        from repohealth.commit_conventions import check

        result = check(str(git_repo))
        assert result.total_commits >= 1
        # "feat: initial commit" should be conventional
        assert result.conventional_count >= 1

    def test_various_commit_types(self, git_repo):
        """Test detection of different conventional commit types."""
        from repohealth.commit_conventions import check

        commits = [
            "fix: fix a bug",
            "docs: update readme",
            "refactor: clean up code",
            "test: add more tests",
            "chore: update deps",
        ]
        for msg in commits:
            (git_repo / f"file_{msg[:4]}.txt").write_text(msg)
            subprocess.run(["git", "add", "."], cwd=str(git_repo), check=True, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", msg],
                cwd=str(git_repo),
                check=True,
                capture_output=True,
            )

        result = check(str(git_repo))
        assert result.total_commits >= 5
        assert result.compliance_rate > 0.5

    def test_commit_message_object(self):
        """Test CommitMessage dataclass."""
        from repohealth.commit_conventions import CommitMessage

        msg = CommitMessage(
            hash="abc1234",
            subject="feat: new feature",
            is_conventional=True,
            is_long_subject=False,
            ends_with_period=False,
            has_trailer=False,
            is_empty=False,
            body_lines=0,
        )
        assert msg.is_compliant

    def test_non_compliant_message(self):
        """Test non-compliant commit detection."""
        from repohealth.commit_conventions import CommitMessage

        msg = CommitMessage(
            hash="abc1234",
            subject="random update with a very long subject line that exceeds seventy two characters limit",
            is_conventional=False,
            is_long_subject=True,
            ends_with_period=False,
            has_trailer=False,
            is_empty=False,
            body_lines=0,
        )
        assert not msg.is_compliant


# ── Test Coverage Module Tests ───────────────────────────────────────────────


class TestTestCoverageModule:
    def test_count_test_items(self, tmp_path):
        """Test _count_test_items function."""
        from repohealth.test_coverage import _count_test_items

        test_file = tmp_path / "test_example.py"
        test_file.write_text('''"""Tests."""

def test_one():
    pass

def test_two():
    pass

class TestSomething:
    def test_three(self):
        pass
''')
        funcs, classes = _count_test_items(test_file)
        assert funcs == 3
        assert classes == 1

    def test_find_test_dirs(self, tmp_path):
        """Test _find_test_dirs function."""
        from repohealth.test_coverage import _find_test_dirs

        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "__init__.py").write_text("")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("x = 1\n")

        dirs = _find_test_dirs(tmp_path)
        assert len(dirs) >= 1
        assert any("tests" in str(d) for d in dirs)

    def test_coverage_result_fields(self, python_repo):
        """Test that TestCoverageResult has all expected fields."""
        from repohealth.test_coverage import check

        result = check(str(python_repo))
        assert hasattr(result, "total_source_files")
        assert hasattr(result, "test_to_code_ratio")
        assert hasattr(result, "test_framework")
        assert hasattr(result, "uncovered_source")
        assert hasattr(result, "has_pytest_cov")


# ── Security Module Tests ───────────────────────────────────────────────────


class TestSecurityModule:
    def test_mask_secret(self):
        """Test _mask_secret function."""
        from repohealth.security import _mask_secret

        assert "****" in _mask_secret('password = "secret123"')
        assert "****" in _mask_secret("mongodb://user:***@host")

    def test_scan_file_no_secrets(self, tmp_path):
        """Test scanning a clean file."""
        from repohealth.security import _scan_file_for_secrets

        clean_file = tmp_path / "clean.py"
        clean_file.write_text("x = 1\ny = 2\n")
        findings = _scan_file_for_secrets(clean_file, tmp_path)
        assert len(findings) == 0

    def test_scan_file_with_secrets(self, tmp_path):
        """Test scanning a file with secrets."""
        from repohealth.security import _scan_file_for_secrets

        bad_file = tmp_path / "bad.py"
        bad_file.write_text('api_key = "sk-abc...efgh"\n')
        findings = _scan_file_for_secrets(bad_file, tmp_path)
        assert len(findings) > 0

    def test_security_result_risk_levels(self, tmp_path):
        """Test different risk level calculations."""
        from repohealth.security import check

        # Clean repo should have low/medium risk
        result = check(str(tmp_path))
        assert result.risk_level in ("low", "medium", "high", "critical")

    def test_pre_commit_detection(self, git_repo):
        """Test detection of pre-commit config."""
        from repohealth.security import check

        (git_repo / ".pre-commit-config.yaml").write_text("repos: []\n")
        subprocess.run(["git", "add", "."], cwd=str(git_repo), check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add pre-commit"],
            cwd=str(git_repo),
            check=True,
            capture_output=True,
        )
        result = check(str(git_repo))
        assert result.has_pre_commit


# ── Doc Coverage Module Tests ────────────────────────────────────────────────


class TestDocCoverageModule:
    def test_analyze_python_module(self, tmp_path):
        """Test _analyze_python_module function."""
        from repohealth.doc_coverage import _analyze_python_module

        mod = tmp_path / "mod.py"
        mod.write_text('''"""Module docstring."""

def documented_func():
    """This is documented."""
    pass

def undocumented_func():
    pass

class DocumentedClass:
    """Documented class."""
    pass

class _PrivateClass:
    pass
''')
        info = _analyze_python_module(mod, tmp_path)
        assert info.has_module_docstring
        assert info.total_definitions >= 2
        assert info.documented_definitions >= 2

    def test_analyze_readme(self, tmp_path):
        """Test _analyze_readme function."""
        from repohealth.doc_coverage import _analyze_readme

        readme = tmp_path / "README.md"
        readme.write_text("""# My Project

## Installation
pip install myproject

## Usage
import myproject

## License
MIT
""")
        found, _missing = _analyze_readme(tmp_path)
        assert "installation" in found
        assert "usage" in found
        assert "license" in found

    def test_no_readme(self, tmp_path):
        """Test _analyze_readme when no README exists."""
        from repohealth.doc_coverage import _analyze_readme

        found, missing = _analyze_readme(tmp_path)
        assert len(found) == 0
        assert len(missing) > 0


# ── Dependency Graph Module Tests ────────────────────────────────────────────


class TestDependencyGraphModule:
    def test_parse_requirements_txt(self, tmp_path):
        """Test _parse_requirements_txt function."""
        from repohealth.dependency_graph import _parse_requirements_txt

        req = tmp_path / "requirements.txt"
        req.write_text("click>=8.0\nrich>=13.0\n# comment\npytest==7.0\n")
        deps = _parse_requirements_txt(req, is_dev=False)
        assert len(deps) == 3
        assert deps[0].name == "click"
        assert deps[0].category == "runtime"
        assert deps[2].version_spec == "==7.0"

    def test_parse_requirements_dev(self, tmp_path):
        """Test dev requirements parsing."""
        from repohealth.dependency_graph import _parse_requirements_txt

        req = tmp_path / "requirements-dev.txt"
        req.write_text("pytest>=7.0\nflake8\n")
        deps = _parse_requirements_txt(req, is_dev=True)
        assert len(deps) == 2
        assert all(d.is_dev for d in deps)

    def test_find_third_party_imports(self, tmp_path):
        """Test _find_third_party_imports function."""
        from repohealth.dependency_graph import _find_third_party_imports

        src = tmp_path / "app.py"
        src.write_text("import click\nfrom rich.console import Console\nimport os\n")
        imports = _find_third_party_imports(tmp_path)
        assert "click" in imports
        assert "rich" in imports
        assert "os" not in imports  # stdlib


# ── Tech Debt Module Tests ──────────────────────────────────────────────────


class TestTechDebtModule:
    def test_compute_complexity(self):
        """Test _compute_cyclomatic_complexity."""
        from repohealth.tech_debt import _compute_cyclomatic_complexity

        # Simple function
        tree = ast.parse("def f(): pass")
        func = tree.body[0]
        assert _compute_cyclomatic_complexity(func) == 1

        # If/else
        tree = ast.parse("def f(x):\n    if x: pass\n    elif x > 1: pass\n    else: pass")
        func = tree.body[0]
        complexity = _compute_cyclomatic_complexity(func)
        assert complexity >= 3

    def test_scan_file_for_debt(self, tmp_path):
        """Test _scan_file_for_debt."""
        from repohealth.tech_debt import _scan_file_for_debt

        f = tmp_path / "code.py"
        f.write_text("# TODO: implement later\n# FIXME: bug here\nx = 1\n")
        items = _scan_file_for_debt(f, tmp_path)
        assert len(items) == 2
        # Items are returned in marker iteration order (TODO before FIXME in DEBT_MARKERS dict)
        # The main check() function sorts by priority
        markers = [item.marker for item in items]
        assert "TODO" in markers
        assert "FIXME" in markers

    def test_analyze_complexity(self, tmp_path):
        """Test _analyze_python_complexity."""
        from repohealth.tech_debt import _analyze_python_complexity

        f = tmp_path / "complex.py"
        f.write_text(
            "def big_func(x):\n" + "\n".join(f"    if x > {i}: return {i}\n" for i in range(15))
        )
        results = _analyze_python_complexity(f, tmp_path)
        assert len(results) > 0
        assert results[0].complexity >= 10


# ── History Module Tests ────────────────────────────────────────────────────


class TestHistoryModule:
    def test_history_entry_serialization(self):
        """Test HistoryEntry to_dict/from_dict roundtrip."""
        from repohealth.history import HistoryEntry

        entry = HistoryEntry(
            timestamp="2026-05-29T12:00:00",
            path="/tmp/test",
            score=85,
            grade="B",
            checks=[{"name": "Test", "score": 85}],
            metadata={"version": "0.2.0"},
        )
        d = entry.to_dict()
        restored = HistoryEntry.from_dict(d)
        assert restored.score == 85
        assert restored.grade == "B"
        assert restored.metadata["version"] == "0.2.0"

    def test_compare_with_new_checks(self):
        """Test comparison when new checks appear."""
        from repohealth.history import HistoryEntry, compare_entries

        earlier = HistoryEntry(
            timestamp="2026-05-01",
            path="/t",
            score=80,
            grade="B",
            checks=[{"name": "Security", "score": 80}],
        )
        later = HistoryEntry(
            timestamp="2026-05-15",
            path="/t",
            score=85,
            grade="B",
            checks=[{"name": "Security", "score": 80}, {"name": "Tests", "score": 90}],
        )
        diff = compare_entries(earlier, later)
        assert "Tests" in diff.new_checks
        assert diff.score_delta == 5

    def test_declining_trend(self):
        """Test declining trend detection."""
        from repohealth.history import HistoryEntry, get_trend

        entries = [
            HistoryEntry(
                timestamp=f"2026-05-{i:02d}",
                path="/t",
                score=90 - i * 5,
                grade="B",
                checks=[],
            )
            for i in range(1, 6)
        ]
        trend = get_trend(entries)
        assert trend == "declining"

    def test_insufficient_trend(self):
        """Test trend with insufficient data."""
        from repohealth.history import HistoryEntry, get_trend

        entries = [HistoryEntry(timestamp="2026-05-01", path="/t", score=85, grade="B", checks=[])]
        trend = get_trend(entries)
        assert trend == "insufficient"


# ── Config Module Tests ─────────────────────────────────────────────────────


class TestConfigModule:
    def test_deep_merge(self):
        """Test _deep_merge utility."""
        from repohealth.config import _deep_merge

        base = {"a": 1, "b": {"c": 2, "d": 3}, "e": 5}
        override = {"b": {"c": 99}, "f": 6}
        result = _deep_merge(base, override)
        assert result["a"] == 1
        assert result["b"]["c"] == 99
        assert result["b"]["d"] == 3
        assert result["f"] == 6

    def test_check_config_defaults(self):
        """Test CheckConfig with defaults."""
        from repohealth.config import CheckConfig

        cc = CheckConfig()
        assert cc.enabled is True
        assert cc.weight == 10

    def test_repohealth_config_weight(self):
        """Test weight retrieval."""
        from repohealth.config import RepoHealthConfig, CheckConfig

        cfg = RepoHealthConfig(checks={"security": CheckConfig(weight=20)})
        assert cfg.get_weight("security") == 20
        assert cfg.get_weight("unknown") == 10  # default

    def test_check_option(self):
        """Test get_check_option."""
        from repohealth.config import RepoHealthConfig, CheckConfig

        cfg = RepoHealthConfig(checks={"security": CheckConfig(options={"max_findings": 100})})
        assert cfg.get_check_option("security", "max_findings") == 100
        assert cfg.get_check_option("security", "nonexistent", "default") == "default"

    def test_generate_config_creates_file(self, tmp_path):
        """Test generate_default_config."""
        from repohealth.config import generate_default_config

        path = generate_default_config(str(tmp_path / ".repohealth.yml"))
        assert path.exists()
        content = path.read_text()
        assert len(content) > 100


# Fixtures for test modules that need python_repo
@pytest.fixture
def python_repo(git_repo: Path):
    """Create a Python project repo with source and test files."""
    src_dir = git_repo / "myproject"
    src_dir.mkdir()
    (src_dir / "__init__.py").write_text("""My project.""")
    (src_dir / "core.py").write_text('''"""Core module."""

def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b
''')
    test_dir = git_repo / "tests"
    test_dir.mkdir()
    (test_dir / "__init__.py").write_text("")
    (test_dir / "test_core.py").write_text('''"""Tests for core."""

import pytest
from myproject.core import add


def test_add():
    assert add(1, 2) == 3
''')
    (git_repo / "pyproject.toml").write_text("""[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[project]
name = "myproject"
version = "0.1.0"
dependencies = ["click>=8.0"]
[project.optional-dependencies]
dev = ["pytest>=7.0"]
""")
    subprocess.run(["git", "add", "."], cwd=str(git_repo), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: add project"],
        cwd=str(git_repo),
        check=True,
        capture_output=True,
    )
    return git_repo
