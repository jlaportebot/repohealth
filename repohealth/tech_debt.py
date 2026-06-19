"""Check: technical debt analysis — TODOs, FIXMEs, HACKs, deprecated code, complexity."""

from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


# Debt markers to search for
DEBT_MARKERS = {
    "TODO": re.compile(r"\bTODO\b[:\s]*(.*)", re.IGNORECASE),
    "FIXME": re.compile(r"\bFIXME\b[:\s]*(.*)", re.IGNORECASE),
    "HACK": re.compile(r"\bHACK\b[:\s]*(.*)", re.IGNORECASE),
    "XXX": re.compile(r"\bXXX\b[:\s]*(.*)", re.IGNORECASE),
    "DEPRECATED": re.compile(r"\bDEPRECATED\b[:\s]*(.*)", re.IGNORECASE),
    "NOQA": re.compile(r"#\s*noqa\b", re.IGNORECASE),
}

# Files to scan
SCAN_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".rb",
    ".go",
    ".rs",
    ".java",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".swift",
    ".yaml",
    ".yml",
    ".toml",
    ".sh",
    ".bash",
}


@dataclass
class DebtItem:
    """A single technical debt item."""

    file: str
    line: int
    marker: str  # TODO, FIXME, etc.
    message: str
    priority: str  # "high", "medium", "low"


@dataclass
class ComplexityInfo:
    """Cyclomatic complexity info for a function."""

    file: str
    function: str
    complexity: int
    lines: int


@dataclass
class TechDebtResult:
    """Result of technical debt analysis."""

    total_markers: int
    markers_by_type: dict[str, int]
    debt_items: list[DebtItem]
    high_complexity_functions: list[ComplexityInfo]  # Functions with complexity > 10
    max_complexity: int
    avg_complexity: float
    total_functions: int
    long_functions: int  # Functions > 50 lines
    deprecated_count: int
    noqa_count: int
    debt_score: float  # 0-100, higher = more debt
    error: str | None = None


SKIP_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "dist",
    "build",
    ".eggs",
    ".idea",
    ".vscode",
    ".hg",
}


def _compute_cyclomatic_complexity(tree: ast.AST) -> int:
    """Compute cyclomatic complexity of an AST node (function/method)."""
    complexity = 1  # Base complexity

    for node in ast.walk(tree):
        # Decision points
        if (
            isinstance(node, ast.If)
            or isinstance(node, ast.For)
            or isinstance(node, ast.While)
            or isinstance(node, ast.ExceptHandler)
            or isinstance(node, ast.With)
            or isinstance(node, ast.Assert)
            or isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp))
        ):
            complexity += 1
        elif isinstance(node, ast.BoolOp):
            # Each 'and'/'or' adds a decision point
            complexity += len(node.values) - 1
        elif isinstance(node, ast.IfExp):
            complexity += 1  # Ternary

    return complexity


def _scan_file_for_debt(filepath: Path, base: Path) -> list[DebtItem]:
    """Scan a file for debt markers."""
    items: list[DebtItem] = []

    try:
        lines = filepath.read_text(errors="ignore").splitlines()
    except OSError:
        return items

    for line_num, line in enumerate(lines, start=1):
        for marker, pattern in DEBT_MARKERS.items():
            match = pattern.search(line)
            if match:
                message = match.group(1).strip()[:80] if match.groups() else ""
                # Assign priority
                if marker in ("FIXME", "HACK", "DEPRECATED"):
                    priority = "high"
                elif marker in ("TODO", "XXX"):
                    priority = "medium"
                else:
                    priority = "low"

                items.append(
                    DebtItem(
                        file=str(filepath.relative_to(base)),
                        line=line_num,
                        marker=marker,
                        message=message,
                        priority=priority,
                    )
                )

    return items


def _analyze_python_complexity(filepath: Path, base: Path) -> list[ComplexityInfo]:
    """Analyze cyclomatic complexity of Python functions in a file."""
    results: list[ComplexityInfo] = []

    try:
        content = filepath.read_text(errors="ignore")
        tree = ast.parse(content)
    except (SyntaxError, OSError):
        return results

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            complexity = _compute_cyclomatic_complexity(node)
            # Count lines
            end_line = (
                node.end_lineno if hasattr(node, "end_lineno") and node.end_lineno else node.lineno
            )
            func_lines = end_line - node.lineno + 1

            if complexity > 10 or func_lines > 50:
                results.append(
                    ComplexityInfo(
                        file=str(filepath.relative_to(base)),
                        function=node.name,
                        complexity=complexity,
                        lines=func_lines,
                    )
                )

    return results


def check(repo_path: str | None = None, max_items: int = 50) -> TechDebtResult:
    """Analyze technical debt in the repository.

    Scans for:
    - TODO/FIXME/HACK/XXX/DEPRECATED markers
    - NOQA suppression comments
    - Cyclomatic complexity of Python functions
    - Long functions (> 50 lines)
    """
    base = Path(repo_path) if repo_path else Path.cwd()

    all_debt: list[DebtItem] = []
    all_complex: list[ComplexityInfo] = []
    markers_by_type: dict[str, int] = {m: 0 for m in DEBT_MARKERS}
    deprecated_count = 0
    noqa_count = 0
    total_functions = 0
    long_functions = 0

    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]

        for fname in filenames:
            ext = Path(fname).suffix.lower()
            if ext not in SCAN_EXTENSIONS:
                continue

            filepath = Path(dirpath) / fname

            # Scan for debt markers
            debt = _scan_file_for_debt(filepath, base)
            all_debt.extend(debt)

            # Count by type
            for item in debt:
                if item.marker in markers_by_type:
                    markers_by_type[item.marker] += 1
                if item.marker == "DEPRECATED":
                    deprecated_count += 1
                if item.marker == "NOQA":
                    noqa_count += 1

            # Analyze complexity for Python files
            if ext == ".py":
                complex_funcs = _analyze_python_complexity(filepath, base)
                all_complex.extend(complex_funcs)

                # Count all functions
                try:
                    content = filepath.read_text(errors="ignore")
                    tree = ast.parse(content)
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            total_functions += 1
                            end = (
                                node.end_lineno
                                if hasattr(node, "end_lineno") and node.end_lineno
                                else node.lineno
                            )
                            if (end - node.lineno + 1) > 50:
                                long_functions += 1
                except (SyntaxError, OSError):
                    pass

    # Sort debt items by priority
    priority_order = {"high": 0, "medium": 1, "low": 2}
    all_debt.sort(key=lambda d: priority_order.get(d.priority, 3))

    # Sort complexity by complexity descending
    all_complex.sort(key=lambda c: c.complexity, reverse=True)

    max_complexity = max((c.complexity for c in all_complex), default=0)
    avg_complexity = (
        sum(c.complexity for c in all_complex) / len(all_complex) if all_complex else 0.0
    )

    # Compute debt score (0-100, higher = more debt)
    total_markers = len(all_debt)
    high_complex = len([c for c in all_complex if c.complexity > 10])

    # Base score from markers (capped at 50)
    marker_score = min(total_markers * 2, 50)
    # Complexity contribution (capped at 30)
    complexity_score = min(high_complex * 5, 30)
    # Long function contribution (capped at 20)
    long_score = min(long_functions * 2, 20)

    debt_score = min(marker_score + complexity_score + long_score, 100)

    return TechDebtResult(
        total_markers=total_markers,
        markers_by_type=markers_by_type,
        debt_items=all_debt[:max_items],
        high_complexity_functions=all_complex[:20],
        max_complexity=max_complexity,
        avg_complexity=round(avg_complexity, 1),
        total_functions=total_functions,
        long_functions=long_functions,
        deprecated_count=deprecated_count,
        noqa_count=noqa_count,
        debt_score=debt_score,
    )
