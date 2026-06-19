"""Check: detect missing repo essentials (README, LICENSE, .gitignore, CI)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class EssentialsResult:
    """Result of essentials check."""

    missing: list[str]
    present: list[str]


ESSENTIAL_FILES = {
    "README": ["README.md", "README.rst", "README.txt", "README"],
    "LICENSE": ["LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"],
    ".gitignore": [".gitignore"],
}

CI_INDICATORS = [
    ".github/workflows",
    ".gitlab-ci.yml",
    ".circleci",
    "Jenkinsfile",
    ".travis.yml",
]


def check(repo_path: str | None = None) -> EssentialsResult:
    """Check for essential repo files and CI config."""
    base = Path(repo_path) if repo_path else Path.cwd()
    missing: list[str] = []
    present: list[str] = []

    for label, filenames in ESSENTIAL_FILES.items():
        if any((base / fn).exists() for fn in filenames):
            present.append(label)
        else:
            missing.append(label)

    # CI check
    has_ci = any(
        (base / indicator).exists()
        if not indicator.endswith(".yml") and not indicator.endswith(".txt")
        else (base / indicator).is_file()
        for indicator in CI_INDICATORS
    )
    if has_ci:
        present.append("CI")
    else:
        missing.append("CI")

    return EssentialsResult(missing=missing, present=present)
