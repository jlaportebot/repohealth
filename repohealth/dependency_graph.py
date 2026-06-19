"""Check: dependency graph analysis — dependency count, dev vs runtime, license diversity."""

from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set, Tuple


@dataclass
class DependencyInfo:
    """Info about a single dependency."""

    name: str
    version_spec: str
    is_dev: bool
    is_optional: bool
    category: str  # "runtime", "dev", "optional", "build"


@dataclass
class DependencyGraphResult:
    """Result of dependency graph analysis."""

    runtime_deps: list[DependencyInfo]
    dev_deps: list[DependencyInfo]
    optional_deps: list[DependencyInfo]
    build_deps: list[DependencyInfo]
    total_runtime: int
    total_dev: int
    total_optional: int
    total_build: int
    dep_file: str  # Which file was parsed
    has_version_pins: int  # Number with exact version pins
    has_upper_bounds: int  # Number with upper bound constraints
    has_wildcards: int  # Number with no version or wildcard
    license_types: set[str]  # License categories found
    imports_used: set[str]  # Third-party imports actually used in code
    unused_deps: list[str]  # Declared but not imported
    missing_deps: list[str]  # Imported but not declared
    error: str | None = None


# Map common package names to their import names
PACKAGE_TO_IMPORT = {
    "pillow": "PIL",
    "pyyaml": "yaml",
    "python-dateutil": "dateutil",
    "scikit-learn": "sklearn",
    "beautifulsoup4": "bs4",
    "opencv-python": "cv2",
    "pycrypto": "Crypto",
    "pygments": "pygments",
    "django": "django",
    "flask": "flask",
    "attrs": "attr",
    "yaml": "yaml",
    "setuptools": "setuptools",
}


def _parse_pyproject_toml(filepath: Path) -> tuple[list[DependencyInfo], str]:
    """Parse dependencies from pyproject.toml (simple parser, no toml dep needed)."""
    deps: list[DependencyInfo] = []
    try:
        content = filepath.read_text(errors="ignore")
    except OSError:
        return deps, "pyproject.toml"

    # Very basic parsing — find [project] dependencies and [project.optional-dependencies]
    in_project_deps = False
    in_optional = False
    current_optional_group = ""
    current_section = ""

    for line in content.splitlines():
        stripped = line.strip()

        # Section headers
        if stripped.startswith("[project]"):
            current_section = "project"
            in_project_deps = False
            in_optional = False
            continue
        if stripped.startswith("[project.optional-dependencies"):
            current_section = "optional"
            in_project_deps = False
            # Extract group name
            match = re.match(r"\[project\.optional-dependencies\.(\w+)\]", stripped)
            current_optional_group = match.group(1) if match else "optional"
            in_optional = True
            continue
        if stripped.startswith("[build-system]"):
            current_section = "build"
            in_project_deps = False
            in_optional = False
            continue
        if stripped.startswith("[tool.setuptools]"):
            current_section = "setuptools"
            continue
        if stripped.startswith("["):
            current_section = "other"
            in_project_deps = False
            in_optional = False
            continue

        # Parse dependency lines
        if current_section == "project" and stripped.startswith("dependencies"):
            in_project_deps = True
            # Check if deps are on the same line
            match = re.match(r"dependencies\s*=\s*\[(.*)\]", stripped)
            if match:
                inline = match.group(1)
                for dep_match in re.finditer(r'"([^"]+)"', inline):
                    _add_dep(deps, dep_match.group(1), "runtime", False, False)
            continue

        if in_project_deps and stripped.startswith('"'):
            # Dependency line in the dependencies array
            dep_match = re.match(r'"([^"]+)"', stripped)
            if dep_match:
                _add_dep(deps, dep_match.group(1), "runtime", False, False)
            continue

        if in_project_deps and stripped == "]":
            in_project_deps = False
            continue

        if in_optional and stripped.startswith('"'):
            dep_match = re.match(r'"([^"]+)"', stripped)
            if dep_match:
                is_dev = current_optional_group.lower() in (
                    "dev",
                    "test",
                    "testing",
                    "development",
                )
                _add_dep(deps, dep_match.group(1), current_optional_group, is_dev, True)
            continue

        if in_optional and stripped == "]":
            in_optional = False
            continue

        if current_section == "build" and stripped.startswith("requires"):
            match = re.match(r"requires\s*=\s*\[(.*)\]", stripped)
            if match:
                inline = match.group(1)
                for dep_match in re.finditer(r'"([^"]+)"', inline):
                    _add_dep(deps, dep_match.group(1), "build", False, False)

    return deps, "pyproject.toml"


def _add_dep(
    deps: list[DependencyInfo],
    spec: str,
    category: str,
    is_dev: bool,
    is_optional: bool,
) -> None:
    """Parse a dependency spec like 'click>=8.0,<9.0' and add it."""
    # Split name from version spec
    match = re.match(r"([a-zA-Z0-9_.-]+)\s*(.*)", spec.strip())
    if not match:
        return
    name = match.group(1).strip()
    version_spec = match.group(2).strip()

    deps.append(
        DependencyInfo(
            name=name,
            version_spec=version_spec,
            is_dev=is_dev,
            is_optional=is_optional,
            category=category,
        )
    )


def _parse_requirements_txt(filepath: Path, is_dev: bool = False) -> list[DependencyInfo]:
    """Parse requirements.txt format."""
    deps: list[DependencyInfo] = []
    try:
        content = filepath.read_text(errors="ignore")
    except OSError:
        return deps

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue

        match = re.match(r"([a-zA-Z0-9_.-]+)\s*(.*)", line)
        if match:
            deps.append(
                DependencyInfo(
                    name=match.group(1),
                    version_spec=match.group(2).strip(),
                    is_dev=is_dev,
                    is_optional=False,
                    category="dev" if is_dev else "runtime",
                )
            )

    return deps


def _find_third_party_imports(base: Path) -> set[str]:
    """Scan Python source files to find third-party imports actually used."""
    imports: set[str] = set()
    stdlib_names = {
        "os",
        "sys",
        "re",
        "json",
        "ast",
        "io",
        "math",
        "time",
        "datetime",
        "pathlib",
        "subprocess",
        "collections",
        "typing",
        "functools",
        "itertools",
        "operator",
        "dataclasses",
        "abc",
        "contextlib",
        "copy",
        "hashlib",
        "hmac",
        "logging",
        "pprint",
        "tempfile",
        "traceback",
        "unittest",
        "argparse",
        "csv",
        "email",
        "html",
        "http",
        "xml",
        "urllib",
        "socket",
        "threading",
        "multiprocessing",
        "queue",
        "struct",
        "random",
        "secrets",
        "shutil",
        "signal",
        "stat",
        "string",
        "textwrap",
        "warnings",
        "weakref",
        "decimal",
        "fractions",
        "enum",
        "importlib",
        "inspect",
        "dis",
        "codecs",
        "gettext",
        "locale",
        "platform",
        "gc",
        "atexit",
        "fnmatch",
        "glob",
        "linecache",
        "fileinput",
        "selectors",
        "mmap",
        "zlib",
        "gzip",
        "bz2",
        "lzma",
        "zipfile",
        "tarfile",
        "pickle",
        "shelve",
        "sqlite3",
        "heapq",
        "bisect",
        "array",
        "types",
        "pdb",
        "profile",
        "cProfile",
        "timeit",
    }

    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [
            d
            for d in dirnames
            if d
            not in {
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
            }
            and not d.startswith(".")
        ]
        for fname in filenames:
            if not fname.endswith(".py") or fname == "__init__.py":
                continue
            if fname.startswith("test_") or fname.endswith("_test.py"):
                continue

            filepath = Path(dirpath) / fname
            try:
                content = filepath.read_text(errors="ignore")
                tree = ast.parse(content)
            except (SyntaxError, OSError):
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        top = alias.name.split(".")[0]
                        if top not in stdlib_names:
                            imports.add(top.lower())
                elif isinstance(node, ast.ImportFrom):
                    if node.module and node.level == 0:  # Not relative import
                        top = node.module.split(".")[0]
                        if top not in stdlib_names:
                            imports.add(top.lower())

    return imports


def check(repo_path: str | None = None) -> DependencyGraphResult:
    """Analyze the dependency graph.

    Checks:
    - Runtime vs dev vs optional vs build dependencies
    - Version constraint quality (pins, bounds, wildcards)
    - Unused and missing dependencies
    """
    base = Path(repo_path) if repo_path else Path.cwd()

    all_deps: list[DependencyInfo] = []
    dep_file = "none"

    # Try pyproject.toml first
    pyproject = base / "pyproject.toml"
    if pyproject.exists():
        all_deps, dep_file = _parse_pyproject_toml(pyproject)

    # Also check requirements files
    for req_file, is_dev in [
        ("requirements.txt", False),
        ("requirements-dev.txt", True),
        ("requirements/dev.txt", True),
        ("requirements/test.txt", True),
    ]:
        req_path = base / req_file
        if req_path.exists():
            all_deps.extend(_parse_requirements_txt(req_path, is_dev))
            if dep_file == "none":
                dep_file = req_file

    if not all_deps:
        return DependencyGraphResult(
            runtime_deps=[],
            dev_deps=[],
            optional_deps=[],
            build_deps=[],
            total_runtime=0,
            total_dev=0,
            total_optional=0,
            total_build=0,
            dep_file=dep_file,
            has_version_pins=0,
            has_upper_bounds=0,
            has_wildcards=0,
            license_types=set(),
            imports_used=set(),
            unused_deps=[],
            missing_deps=[],
            error="No dependency file found",
        )

    # Categorize
    runtime = [d for d in all_deps if d.category == "runtime"]
    dev = [d for d in all_deps if d.is_dev]
    optional = [d for d in all_deps if d.is_optional and not d.is_dev]
    build = [d for d in all_deps if d.category == "build"]

    # Version constraint analysis
    pins = 0
    upper_bounds = 0
    wildcards = 0

    for d in all_deps:
        spec = d.version_spec
        if not spec or spec == "*":
            wildcards += 1
        elif "==" in spec:
            pins += 1
        if "<" in spec or "^" in spec or "~" in spec:
            upper_bounds += 1

    # Find third-party imports in code
    imports_used = _find_third_party_imports(base)

    # Map dependency names to import names
    declared_imports: set[str] = set()
    for d in all_deps:
        name_lower = d.name.lower().replace("-", "_")
        # Check if there's a known mapping
        if d.name.lower() in PACKAGE_TO_IMPORT:
            declared_imports.add(PACKAGE_TO_IMPORT[d.name.lower()].lower())
        else:
            declared_imports.add(name_lower)

    # Find unused and missing
    unused = sorted(declared_imports - imports_used)
    missing = sorted(imports_used - declared_imports)

    return DependencyGraphResult(
        runtime_deps=runtime,
        dev_deps=dev,
        optional_deps=optional,
        build_deps=build,
        total_runtime=len(runtime),
        total_dev=len(dev),
        total_optional=len(optional),
        total_build=len(build),
        dep_file=dep_file,
        has_version_pins=pins,
        has_upper_bounds=upper_bounds,
        has_wildcards=wildcards,
        license_types=set(),  # Would need license checking
        imports_used=imports_used,
        unused_deps=unused[:20],
        missing_deps=missing[:20],
    )
