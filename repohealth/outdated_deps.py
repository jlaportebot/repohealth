"""Check: detect outdated Python dependencies."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class OutdatedDep:
    """A single outdated dependency."""

    name: str
    installed: str
    latest: str


@dataclass
class OutdatedDepsResult:
    """Result of outdated-dependencies check."""

    source: str  # "requirements.txt", "pyproject.toml", etc.
    outdated: List[OutdatedDep]
    error: Optional[str] = None


def _find_dep_file(repo_path: str | None = None) -> Optional[Path]:
    base = Path(repo_path) if repo_path else Path.cwd()
    candidates = [
        base / "requirements.txt",
        base / "pyproject.toml",
        base / "setup.cfg",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def check(repo_path: str | None = None) -> OutdatedDepsResult:
    """Check for outdated pip packages listed in the repo."""
    dep_file = _find_dep_file(repo_path)
    source = dep_file.name if dep_file else "none"

    if dep_file is None:
        return OutdatedDepsResult(
            source="none", outdated=[], error="No dependency file found"
        )

    try:
        r = subprocess.run(
            ["pip", "list", "--outdated", "--format=json"],
            capture_output=True,
            text=True,
            cwd=repo_path,
            timeout=30,
        )
        if r.returncode != 0:
            return OutdatedDepsResult(
                source=source, outdated=[], error=r.stderr.strip()
            )

        items = json.loads(r.stdout) if r.stdout.strip() else []
        # Only report deps that appear in our dep file
        dep_text = dep_file.read_text(errors="ignore")
        outdated: List[OutdatedDep] = []
        for item in items:
            name = item.get("name", "")
            if name.lower() in dep_text.lower():
                outdated.append(
                    OutdatedDep(
                        name=name,
                        installed=item.get("version", "?"),
                        latest=item.get("latest_version", "?"),
                    )
                )
        return OutdatedDepsResult(source=source, outdated=outdated)
    except Exception as exc:
        return OutdatedDepsResult(source=source, outdated=[], error=str(exc))
