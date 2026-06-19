"""Configuration system for repohealth — YAML-based config with sensible defaults."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

# Try to import yaml, fall back to basic parsing if not available
try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False


# Default config values
DEFAULTS: dict[str, Any] = {
    "large_file_threshold_kb": 1024,
    "stale_branch_days": 30,
    "high_churn_threshold": 50.0,
    "churn_since": "6 months ago",
    "churn_top_n": 10,
    "conventions_since": "3 months ago",
    "pr_stale_days": 30,
    "pr_large_threshold": 400,
    "security_max_findings": 50,
    "tech_debt_max_items": 50,
    "complexity_threshold": 10,
    "long_function_lines": 50,
    "history_keep": 100,
    "save_history": True,
    "checks": {
        "dirty_tree": {"enabled": True, "weight": 15},
        "stale_branches": {"enabled": True, "weight": 10},
        "essentials": {"enabled": True, "weight": 20},
        "outdated_deps": {"enabled": True, "weight": 15},
        "large_files": {"enabled": True, "weight": 10},
        "activity": {"enabled": True, "weight": 15},
        "code_churn": {"enabled": True, "weight": 10},
        "commit_conventions": {"enabled": True, "weight": 10},
        "pr_review": {"enabled": True, "weight": 5},
        "test_coverage": {"enabled": True, "weight": 10},
        "security": {"enabled": True, "weight": 15},
        "doc_coverage": {"enabled": True, "weight": 5},
        "dependency_graph": {"enabled": True, "weight": 5},
        "tech_debt": {"enabled": True, "weight": 5},
    },
    "output": {
        "format": "rich",  # "rich", "json", "github-action"
        "fail_on_grade": ["D", "F"],
        "show_tips": True,
    },
    "ignore": {
        "paths": [],
        "checks": [],
    },
}


@dataclass
class CheckConfig:
    """Configuration for a single check."""

    enabled: bool = True
    weight: int = 10
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class RepoHealthConfig:
    """Full configuration for repohealth."""

    large_file_threshold_kb: int = 1024
    stale_branch_days: int = 30
    high_churn_threshold: float = 50.0
    churn_since: str = "6 months ago"
    churn_top_n: int = 10
    conventions_since: str = "3 months ago"
    pr_stale_days: int = 30
    pr_large_threshold: int = 400
    security_max_findings: int = 50
    tech_debt_max_items: int = 50
    complexity_threshold: int = 10
    long_function_lines: int = 50
    history_keep: int = 100
    save_history: bool = True
    checks: dict[str, CheckConfig] = field(default_factory=dict)
    output_format: str = "rich"
    fail_on_grade: list[str] = field(default_factory=lambda: ["D", "F"])
    show_tips: bool = True
    ignore_paths: list[str] = field(default_factory=list)
    ignore_checks: list[str] = field(default_factory=list)

    def is_check_enabled(self, name: str) -> bool:
        """Check if a specific check is enabled."""
        if name in self.ignore_checks:
            return False
        check = self.checks.get(name)
        if check is None:
            return True  # Default to enabled for unknown checks
        return check.enabled

    def get_weight(self, name: str) -> int:
        """Get the weight for a specific check."""
        check = self.checks.get(name)
        if check is None:
            return 10  # Default weight
        return check.weight

    def get_check_option(self, check_name: str, option: str, default: Any = None) -> Any:
        """Get a specific option for a check."""
        check = self.checks.get(check_name)
        if check is None:
            return default
        return check.options.get(option, default)


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge two dicts, override takes precedence."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(repo_path: str | None = None) -> RepoHealthConfig:
    """Load configuration from repo directory.

    Looks for:
    1. .repohealth.yml
    2. .repohealth.yaml
    3. pyproject.toml [tool.repohealth]
    4. Defaults
    """
    base = Path(repo_path) if repo_path else Path.cwd()
    config_data: dict[str, Any] = {}

    # Try YAML configs
    for config_file in [".repohealth.yml", ".repohealth.yaml"]:
        config_path = base / config_file
        if config_path.exists() and HAS_YAML:
            try:
                with open(config_path) as f:
                    file_data = yaml.safe_load(f) or {}
                config_data = _deep_merge(config_data, file_data)
            except (yaml.YAMLError, OSError):
                pass

    # Try pyproject.toml
    pyproject = base / "pyproject.toml"
    if pyproject.exists() and not config_data:
        try:
            content = pyproject.read_text(errors="ignore")
            # Very basic TOML parsing for [tool.repohealth]
            in_section = False
            for line in content.splitlines():
                stripped = line.strip()
                if stripped == "[tool.repohealth]":
                    in_section = True
                    continue
                if stripped.startswith("[") and in_section:
                    in_section = False
                    continue
                if in_section and "=" in stripped:
                    key, _, value = stripped.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    config_data[key] = value
        except OSError:
            pass

    # Merge with defaults
    merged = _deep_merge(DEFAULTS, config_data)

    # Build config object
    checks = {}
    for name, check_data in merged.get("checks", {}).items():
        if isinstance(check_data, dict):
            checks[name] = CheckConfig(
                enabled=check_data.get("enabled", True),
                weight=check_data.get("weight", 10),
                options=check_data.get("options", {}),
            )
        elif isinstance(check_data, bool):
            checks[name] = CheckConfig(enabled=check_data)

    output = merged.get("output", {})
    ignore = merged.get("ignore", {})

    return RepoHealthConfig(
        large_file_threshold_kb=int(merged.get("large_file_threshold_kb", 1024)),
        stale_branch_days=int(merged.get("stale_branch_days", 30)),
        high_churn_threshold=float(merged.get("high_churn_threshold", 50.0)),
        churn_since=str(merged.get("churn_since", "6 months ago")),
        churn_top_n=int(merged.get("churn_top_n", 10)),
        conventions_since=str(merged.get("conventions_since", "3 months ago")),
        pr_stale_days=int(merged.get("pr_stale_days", 30)),
        pr_large_threshold=int(merged.get("pr_large_threshold", 400)),
        security_max_findings=int(merged.get("security_max_findings", 50)),
        tech_debt_max_items=int(merged.get("tech_debt_max_items", 50)),
        complexity_threshold=int(merged.get("complexity_threshold", 10)),
        long_function_lines=int(merged.get("long_function_lines", 50)),
        history_keep=int(merged.get("history_keep", 100)),
        save_history=bool(merged.get("save_history", True)),
        checks=checks,
        output_format=str(output.get("format", "rich")),
        fail_on_grade=list(output.get("fail_on_grade", ["D", "F"])),
        show_tips=bool(output.get("show_tips", True)),
        ignore_paths=list(ignore.get("paths", [])),
        ignore_checks=list(ignore.get("checks", [])),
    )


def generate_default_config(filepath: str | Path) -> Path:
    """Generate a default .repohealth.yml config file."""
    path = Path(filepath)

    if HAS_YAML:
        import yaml as _yaml

        content = _yaml.dump(DEFAULTS, default_flow_style=False, sort_keys=True)
    else:
        # Manual YAML generation for common settings
        lines = [
            "# repohealth configuration",
            "# See https://github.com/jlaportebot/repohealth for docs",
            "",
            f"large_file_threshold_kb: {DEFAULTS['large_file_threshold_kb']}",
            f"stale_branch_days: {DEFAULTS['stale_branch_days']}",
            f"high_churn_threshold: {DEFAULTS['high_churn_threshold']}",
            f'churn_since: "{DEFAULTS["churn_since"]}"',
            f"save_history: {DEFAULTS['save_history']}",
            "",
            "checks:",
        ]
        for name, cfg in DEFAULTS["checks"].items():
            lines.append(f"  {name}:")
            lines.append(f"    enabled: {cfg['enabled']}")
            lines.append(f"    weight: {cfg['weight']}")
        lines.extend(
            [
                "",
                "output:",
                f"  format: {DEFAULTS['output']['format']}",
                f"  fail_on_grade: {DEFAULTS['output']['fail_on_grade']}",
                f"  show_tips: {DEFAULTS['output']['show_tips']}",
                "",
                "ignore:",
                "  paths: []",
                "  checks: []",
            ]
        )
        content = "\n".join(lines) + "\n"

    path.write_text(content)
    return path
