"""Check: security analysis — known vulnerable patterns, secrets detection, dependency audit."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


# Patterns that look like secrets/credentials
SECRET_PATTERNS = [
    (
        re.compile(r'(?:password|passwd|pwd)\s*[:=]\s*["\'][^"\']{4,}["\']', re.I),
        "Hardcoded password",
    ),
    (
        re.compile(
            r'(?:api_?key|apikey|api_secret)\s*[:=]\s*["\'][^"\']{8,}["\']', re.I
        ),
        "Hardcoded API key",
    ),
    (
        re.compile(r'(?:secret|token|auth_token)\s*[:=]\s*["\'][^"\']{8,}["\']', re.I),
        "Hardcoded secret/token",
    ),
    (
        re.compile(
            r'(?:aws_access_key_id|aws_secret_access_key)\s*[:=]\s*["\'][^"\']+["\']',
            re.I,
        ),
        "AWS credential",
    ),
    (
        re.compile(r'(?:private_key)\s*[:=]\s*["\']-----BEGIN', re.I),
        "Embedded private key",
    ),
    (
        re.compile(r"mongodb(?:\+srv)?://[^:\s]+:[^@\s]+@", re.I),
        "MongoDB URI with credentials",
    ),
    (
        re.compile(r"postgres(?:ql)?://[^:\s]+:[^@\s]+@", re.I),
        "PostgreSQL URI with credentials",
    ),
    (re.compile(r"mysql://[^:\s]+:[^@\s]+@", re.I), "MySQL URI with credentials"),
    (re.compile(r"redis://[^:\s]+:[^@\s]+@", re.I), "Redis URI with credentials"),
    (re.compile(r"sk-[a-zA-Z0-9]{20,}"), "OpenAI API key pattern"),
    (re.compile(r"ghp_[a-zA-Z0-9]{36,}"), "GitHub personal access token"),
    (re.compile(r"glpat-[a-zA-Z0-9\-]{20,}"), "GitLab personal access token"),
]

# Dangerous file patterns
DANGEROUS_FILES = [
    ".env",
    ".env.local",
    ".env.production",
    ".env.staging",
    ".npmrc",
    ".pypirc",
    ".netrc",
    ".cvsignore",
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
    ".htpasswd",
    ".ssh/config",
]

# Skip directories
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
}

# File extensions to scan for secrets
SCAN_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".rb",
    ".go",
    ".rs",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".env",
    ".sh",
    ".bash",
    ".zsh",
}


@dataclass
class SecretFinding:
    """A potential secret/credential found in code."""

    file: str
    line: int
    pattern_type: str
    line_preview: str  # Sanitized — secret value is masked


@dataclass
class SecurityResult:
    """Result of security analysis."""

    secret_findings: List[SecretFinding]
    dangerous_files_present: List[str]
    has_gitignore_entry: bool  # .gitignore has entries for dangerous files
    has_pre_commit: bool  # pre-commit config exists
    has_dependabot: bool  # Dependabot or Renovate configured
    has_security_policy: bool  # SECURITY.md exists
    pip_audit_available: bool
    pip_audit_result: Optional[str]  # Summary from pip-audit if available
    total_findings: int
    risk_level: str  # "low", "medium", "high", "critical"
    error: Optional[str] = None


def _mask_secret(line: str) -> str:
    """Mask potential secret values in a line for safe display."""
    # Replace anything that looks like a quoted value after = or :
    masked = re.sub(
        r'([=:]\s*["\'])[^"\']{4,}(["\'])',
        r"\1****\2",
        line,
    )
    # Mask URL credentials
    masked = re.sub(r"://([^:\s]+):([^@\s]+)@", r"://\1:****@", masked)
    return masked


def _scan_file_for_secrets(filepath: Path, base: Path) -> List[SecretFinding]:
    """Scan a single file for secret patterns."""
    findings: List[SecretFinding] = []

    try:
        lines = filepath.read_text(errors="ignore").splitlines()
    except OSError:
        return findings

    for line_num, line in enumerate(lines, start=1):
        stripped = line.strip()
        # Skip comments
        if stripped.startswith("#") or stripped.startswith("//"):
            continue

        for pattern, description in SECRET_PATTERNS:
            if pattern.search(stripped):
                findings.append(
                    SecretFinding(
                        file=str(filepath.relative_to(base)),
                        line=line_num,
                        pattern_type=description,
                        line_preview=_mask_secret(stripped[:120]),
                    )
                )
                break  # One finding per line max

    return findings


def check(repo_path: str | None = None, max_findings: int = 50) -> SecurityResult:
    """Perform security analysis on the repository.

    Scans for:
    - Hardcoded secrets and credentials
    - Dangerous files that should not be committed
    - Security infrastructure (dependabot, SECURITY.md, pre-commit)
    - Optional pip-audit integration
    """
    base = Path(repo_path) if repo_path else Path.cwd()

    # Scan files for secrets
    all_findings: List[SecretFinding] = []

    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [
            d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")
        ]

        for fname in filenames:
            ext = Path(fname).suffix.lower()
            if ext not in SCAN_EXTENSIONS and fname not in DANGEROUS_FILES:
                continue

            filepath = Path(dirpath) / fname

            # Skip files in .git directory
            try:
                filepath.relative_to(base / ".git")
                continue
            except ValueError:
                pass

            findings = _scan_file_for_secrets(filepath, base)
            all_findings.extend(findings)

            if len(all_findings) >= max_findings:
                break

        if len(all_findings) >= max_findings:
            break

    # Check for dangerous files
    dangerous_present: List[str] = []
    for df in DANGEROUS_FILES:
        if (base / df).exists():
            dangerous_present.append(df)

    # Check .gitignore for entries
    has_gitignore_entries = False
    gitignore_path = base / ".gitignore"
    if gitignore_path.exists():
        try:
            gi_content = gitignore_path.read_text(errors="ignore")
            has_gitignore_entries = any(
                df_name in gi_content
                for df_name in [".env", ".npmrc", ".pypirc", "id_rsa", "*.pem"]
            )
        except OSError:
            pass

    # Check for pre-commit config
    has_pre_commit = (base / ".pre-commit-config.yaml").exists()

    # Check for Dependabot or Renovate
    has_dependabot = (base / ".github" / "dependabot.yml").exists()
    has_renovate = (base / "renovate.json").exists() or (
        base / ".github" / "renovate.json"
    ).exists()
    has_dep_bot = has_dependabot or has_renovate

    # Check for SECURITY.md
    has_security_policy = (base / "SECURITY.md").exists()

    # Try pip-audit
    pip_audit_available = False
    pip_audit_result = None
    try:
        audit_check = subprocess.run(
            ["pip-audit", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if audit_check.returncode == 0:
            pip_audit_available = True
            # Run audit on the repo's requirements if available
            req_file = None
            for candidate in ["requirements.txt", "requirements.lock", "Pipfile.lock"]:
                if (base / candidate).exists():
                    req_file = base / candidate
                    break

            if req_file:
                audit_run = subprocess.run(
                    ["pip-audit", "-r", str(req_file), "--desc"],
                    capture_output=True,
                    text=True,
                    cwd=repo_path,
                    timeout=60,
                )
                if audit_run.returncode == 0:
                    pip_audit_result = "No known vulnerabilities"
                else:
                    # pip-audit exits non-zero if vulnerabilities found
                    vuln_count = audit_run.stdout.count("ID: ")
                    pip_audit_result = (
                        f"{vuln_count} known vulnerabilities"
                        if vuln_count
                        else "Audit completed with warnings"
                    )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    # Determine risk level
    total = len(all_findings) + len(dangerous_present)
    if total == 0 and has_dep_bot and has_security_policy:
        risk = "low"
    elif total == 0:
        risk = "medium"
    elif total <= 3:
        risk = "medium"
    elif total <= 10:
        risk = "high"
    else:
        risk = "critical"

    return SecurityResult(
        secret_findings=all_findings[:max_findings],
        dangerous_files_present=dangerous_present,
        has_gitignore_entry=has_gitignore_entries,
        has_pre_commit=has_pre_commit,
        has_dependabot=has_dep_bot,
        has_security_policy=has_security_policy,
        pip_audit_available=pip_audit_available,
        pip_audit_result=pip_audit_result,
        total_findings=total,
        risk_level=risk,
    )
