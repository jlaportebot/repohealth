"""Check: test coverage analysis — test-to-code ratio, test file detection."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple


@dataclass
class TestFileInfo:
    """Info about a test file."""

    path: str
    test_functions: int
    test_classes: int
    lines: int


@dataclass
class SourceFileInfo:
    """Info about a source file."""

    path: str
    lines: int
    has_corresponding_test: bool


@dataclass
class TestCoverageResult:
    """Result of test coverage analysis."""

    total_source_files: int
    total_test_files: int
    source_lines: int
    test_lines: int
    test_to_code_ratio: float  # test lines / source lines
    files_with_tests: int
    files_without_tests: int
    test_coverage_pct: float  # % of source files with corresponding tests
    test_files: List[TestFileInfo]
    uncovered_source: List[str]  # source files without matching tests
    test_framework: str  # "pytest", "unittest", "none", "mixed"
    has_pytest_cov: bool  # whether pytest-cov is installed
    error: Optional[str] = None


# Test file patterns
TEST_FILE_PATTERNS = [
    "test_", "_test.py", "tests.py",
]
TEST_DIR_PATTERNS = [
    "tests", "test", "spec", "__tests__",
]

# Source file extensions to consider
SOURCE_EXTENSIONS = {".py"}

# Directories to skip
SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    ".tox", ".mypy_cache", ".pytest_cache", "dist", "build",
    ".eggs", "*.egg-info",
}


def _count_test_items(filepath: Path) -> Tuple[int, int]:
    """Count test functions and test classes in a file."""
    test_funcs = 0
    test_classes = 0
    try:
        content = filepath.read_text(errors="ignore")
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("def test_") or stripped.startswith("async def test_"):
                test_funcs += 1
            elif stripped.startswith("class Test") and ":" in stripped:
                test_classes += 1
    except OSError:
        pass
    return test_funcs, test_classes


def _is_test_file(filepath: Path) -> bool:
    """Check if a file is a test file."""
    name = filepath.name
    return any(name.startswith(p.rstrip("_").rstrip("s")) or name.startswith(p)
               for p in ["test_", "test"])
    # Simpler check
    return (name.startswith("test_") or name.endswith("_test.py") or
            name == "tests.py" or filepath.parent.name in TEST_DIR_PATTERNS)


def _has_corresponding_test(source_path: str, test_dirs: List[Path], source_root: Path) -> bool:
    """Check if a source file has a corresponding test file."""
    # Derive expected test paths
    rel = Path(source_path).relative_to(source_root) if str(source_path).startswith(str(source_root)) else None
    if rel is None:
        return False

    stem = rel.stem
    # Possible test names
    test_names = [f"test_{stem}.py", f"{stem}_test.py"]

    for test_dir in test_dirs:
        for test_name in test_names:
            if (test_dir / test_name).exists():
                return True
            # Also check subdirectory matching
            parent = rel.parent
            if (test_dir / parent / test_name).exists():
                return True

    return False


def _find_test_dirs(base: Path) -> List[Path]:
    """Find all test directories in the repo."""
    test_dirs: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(base):
        # Skip hidden and common non-source dirs
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        if dirpath == base:
            dirname = ""
        else:
            dirname = Path(dirpath).name
        if dirname in TEST_DIR_PATTERNS:
            test_dirs.append(Path(dirpath))
    return test_dirs


def check(repo_path: str | None = None) -> TestCoverageResult:
    """Analyze test coverage by examining source and test files.

    This is a static analysis (doesn't run tests) that checks:
    - Number of source vs test files
    - Test-to-code line ratio
    - Which source files have corresponding test files
    - Test framework detection
    """
    base = Path(repo_path) if repo_path else Path.cwd()

    # Check if this is even a Python project
    has_pyproject = (base / "pyproject.toml").exists()
    has_setup = (base / "setup.py").exists() or (base / "setup.cfg").exists()
    has_requirements = (base / "requirements.txt").exists()

    if not any([has_pyproject, has_setup, has_requirements]):
        return TestCoverageResult(
            total_source_files=0, total_test_files=0,
            source_lines=0, test_lines=0, test_to_code_ratio=0.0,
            files_with_tests=0, files_without_tests=0,
            test_coverage_pct=0.0, test_files=[], uncovered_source=[],
            test_framework="none", has_pytest_cov=False,
            error="Not a Python project (no pyproject.toml/setup.py/requirements.txt)",
        )

    # Find test directories
    test_dirs = _find_test_dirs(base)

    # Walk the tree and classify files
    source_files: List[SourceFileInfo] = []
    test_files: List[TestFileInfo] = []
    source_lines = 0
    test_lines = 0

    # Detect test framework
    has_pytest = False
    has_unittest = False

    for dirpath, dirnames, filenames in os.walk(base):
        # Skip directories
        dirnames[:] = [d for d in dirnames
                       if d not in SKIP_DIRS and not d.startswith(".")]

        for fname in filenames:
            if not fname.endswith(".py"):
                continue

            fpath = Path(dirpath) / fname
            try:
                line_count = sum(1 for _ in fpath.open(errors="ignore"))
            except OSError:
                continue

            # Is it a test file?
            is_test = (
                fname.startswith("test_") or
                fname.endswith("_test.py") or
                fname == "tests.py" or
                any(part in TEST_DIR_PATTERNS for part in fpath.relative_to(base).parts)
            )

            if is_test:
                func_count, class_count = _count_test_items(fpath)
                test_files.append(TestFileInfo(
                    path=str(fpath.relative_to(base)),
                    test_functions=func_count,
                    test_classes=class_count,
                    lines=line_count,
                ))
                test_lines += line_count

                # Detect framework
                try:
                    content = fpath.read_text(errors="ignore")
                    if "import pytest" in content or "from pytest" in content:
                        has_pytest = True
                    if "import unittest" in content or "from unittest" in content:
                        has_unittest = True
                except OSError:
                    pass
            else:
                # Skip __init__.py and very small files
                if fname == "__init__.py":
                    continue
                source_files.append(SourceFileInfo(
                    path=str(fpath.relative_to(base)),
                    lines=line_count,
                    has_corresponding_test=False,
                ))
                source_lines += line_count

    # Check which source files have corresponding tests
    uncovered: List[str] = []
    files_with_tests = 0

    for sf in source_files:
        has_test = _has_corresponding_test(sf.path, test_dirs, base)
        sf.has_corresponding_test = has_test
        if has_test:
            files_with_tests += 1
        else:
            uncovered.append(sf.path)

    total_source = len(source_files)
    coverage_pct = (files_with_tests / total_source * 100) if total_source > 0 else 0.0
    ratio = test_lines / source_lines if source_lines > 0 else 0.0

    # Determine framework
    if has_pytest and has_unittest:
        framework = "mixed"
    elif has_pytest:
        framework = "pytest"
    elif has_unittest:
        framework = "unittest"
    else:
        framework = "none"

    # Check for pytest-cov
    cov_check = subprocess.run(
        ["python3", "-c", "import pytest_cov"],
        capture_output=True, text=True,
    )
    has_cov = cov_check.returncode == 0

    return TestCoverageResult(
        total_source_files=total_source,
        total_test_files=len(test_files),
        source_lines=source_lines,
        test_lines=test_lines,
        test_to_code_ratio=round(ratio, 2),
        files_with_tests=files_with_tests,
        files_without_tests=total_source - files_with_tests,
        test_coverage_pct=round(coverage_pct, 1),
        test_files=test_files,
        uncovered_source=uncovered[:20],  # Cap at 20
        test_framework=framework,
        has_pytest_cov=has_cov,
    )
