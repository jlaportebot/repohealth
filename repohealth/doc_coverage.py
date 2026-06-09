"""Check: documentation coverage — docstrings, README sections, API docs."""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple


@dataclass
class ModuleDocInfo:
    """Documentation info for a single Python module."""

    path: str
    total_definitions: int  # classes + functions
    documented_definitions: int
    has_module_docstring: bool
    missing_docstrings: List[str]  # Names of undocumented items


@dataclass
class DocCoverageResult:
    """Result of documentation coverage analysis."""

    total_modules: int
    total_definitions: int
    documented_definitions: int
    coverage_pct: float  # 0-100
    module_docstring_pct: float  # % of modules with docstrings
    missing_items: List[str]  # Top undocumented items
    readme_sections: List[str]  # Sections found in README
    missing_readme_sections: List[str]  # Important sections not in README
    has_api_docs: bool  # docs/ directory or similar
    has_changelog: bool
    has_contributing: bool
    has_code_of_conduct: bool
    modules: List[ModuleDocInfo]
    error: Optional[str] = None


# README sections that should exist
IMPORTANT_README_SECTIONS = [
    "installation",
    "usage",
    "contributing",
    "license",
    "changelog",
    "examples",
    "api",
    "configuration",
    "faq",
    "credits",
]


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


def _analyze_python_module(filepath: Path, base: Path) -> ModuleDocInfo:
    """Analyze a Python module for docstring coverage."""
    try:
        content = filepath.read_text(errors="ignore")
        tree = ast.parse(content)
    except (SyntaxError, OSError):
        return ModuleDocInfo(
            path=str(filepath.relative_to(base)),
            total_definitions=0,
            documented_definitions=0,
            has_module_docstring=False,
            missing_docstrings=[],
        )

    has_module_doc = ast.get_docstring(tree) is not None
    total = 0
    documented = 0
    missing: List[str] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Skip private/dunder methods from coverage requirement
            if node.name.startswith("_") and not node.name.startswith("__"):
                continue
            total += 1
            if ast.get_docstring(node):
                documented += 1
            else:
                missing.append(f"{filepath.name}::{node.name}")
        elif isinstance(node, ast.ClassDef):
            # Skip private classes
            if node.name.startswith("_"):
                continue
            total += 1
            if ast.get_docstring(node):
                documented += 1
            else:
                missing.append(f"{filepath.name}::class {node.name}")

    return ModuleDocInfo(
        path=str(filepath.relative_to(base)),
        total_definitions=total,
        documented_definitions=documented,
        has_module_docstring=has_module_doc,
        missing_docstrings=missing[:10],  # Cap per module
    )


def _analyze_readme(base: Path) -> Tuple[List[str], List[str]]:
    """Analyze README for sections present and missing."""
    readme_path = None
    for name in ["README.md", "README.rst", "README.txt", "README"]:
        if (base / name).exists():
            readme_path = base / name
            break

    if readme_path is None:
        return [], list(IMPORTANT_README_SECTIONS)

    try:
        content = readme_path.read_text(errors="ignore").lower()
    except OSError:
        return [], list(IMPORTANT_README_SECTIONS)

    found: List[str] = []
    missing: List[str] = []

    for section in IMPORTANT_README_SECTIONS:
        # Check for markdown headers or RST underlines
        if f"## {section}" in content or f"# {section}" in content:
            found.append(section)
        elif (
            f"{section}\n{'=' * len(section)}" in content
            or f"{section}\n{'-' * len(section)}" in content
        ):
            found.append(section)
        elif section in content:
            found.append(section)
        else:
            missing.append(section)

    return found, missing


def check(repo_path: str | None = None) -> DocCoverageResult:
    """Analyze documentation coverage.

    Checks:
    - Python docstring coverage for public classes and functions
    - README section completeness
    - Presence of API docs, changelog, contributing guide
    """
    base = Path(repo_path) if repo_path else Path.cwd()

    # Analyze Python modules
    modules: List[ModuleDocInfo] = []
    total_defs = 0
    documented_defs = 0
    modules_with_doc = 0
    all_missing: List[str] = []

    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [
            d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")
        ]

        for fname in filenames:
            if not fname.endswith(".py") or fname == "__init__.py":
                continue

            filepath = Path(dirpath) / fname

            # Skip test files
            if fname.startswith("test_") or fname.endswith("_test.py"):
                continue

            # Skip files in test directories
            parts = filepath.relative_to(base).parts
            if any(p in ("tests", "test", "spec") for p in parts):
                continue

            info = _analyze_python_module(filepath, base)
            modules.append(info)
            total_defs += info.total_definitions
            documented_defs += info.documented_definitions
            if info.has_module_docstring:
                modules_with_doc += 1
            all_missing.extend(info.missing_docstrings)

    coverage_pct = (documented_defs / total_defs * 100) if total_defs > 0 else 0.0
    module_doc_pct = (modules_with_doc / len(modules) * 100) if modules else 0.0

    # Analyze README
    readme_sections, missing_readme_sections = _analyze_readme(base)

    # Check for docs directory
    has_api_docs = any(
        (base / d).exists() for d in ["docs", "doc", "documentation", "api_docs"]
    )

    # Check for changelog
    has_changelog = any(
        (base / f).exists()
        for f in [
            "CHANGELOG.md",
            "CHANGELOG.rst",
            "CHANGELOG.txt",
            "CHANGELOG",
            "HISTORY.md",
        ]
    )

    # Check for contributing guide
    has_contributing = any(
        (base / f).exists()
        for f in [
            "CONTRIBUTING.md",
            "CONTRIBUTING.rst",
            "CONTRIBUTING.txt",
            "CONTRIBUTING",
        ]
    )

    # Check for code of conduct
    has_coc = any(
        (base / f).exists()
        for f in [
            "CODE_OF_CONDUCT.md",
            "CODE_OF_CONDUCT.rst",
            "CODE_OF_CONDUCT.txt",
            "CODE_OF_CONDUCT",
        ]
    )

    return DocCoverageResult(
        total_modules=len(modules),
        total_definitions=total_defs,
        documented_definitions=documented_defs,
        coverage_pct=round(coverage_pct, 1),
        module_docstring_pct=round(module_doc_pct, 1),
        missing_items=all_missing[:30],
        readme_sections=readme_sections,
        missing_readme_sections=missing_readme_sections,
        has_api_docs=has_api_docs,
        has_changelog=has_changelog,
        has_contributing=has_contributing,
        has_code_of_conduct=has_coc,
        modules=modules,
    )
