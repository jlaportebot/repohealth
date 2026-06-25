# 🩺 repohealth

**Assess the health of any Git repository from the command line.**

```bash
pip install repohealth
repohealth .
```

```
🩺  repohealth — .
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Score: 92/100   Grade: A
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Check                    Score  Status  Detail
 ──────────────────────── ────── ─────── ──────────────────────
  Working Tree                100    ✓     Clean working tree
  Stale Branches              100    ✓     No stale branches
  Essentials                  100    ✓     All essentials present
  Dependencies                100    ✓     All deps up-to-date
  Large Files                 100    ✓     No files ≥1024KB
  Activity                    100    ✓     Last commit 0d ago
  Code Churn                  90     ✓     Low churn rate
  Commit Conventions          95     ✓     Conventional commits
  Dependency Graph            85     ✓     Good dep management
  Doc Coverage                88     ✓     Good docstring coverage
  History                     95     ✓     Healthy history trend
  Last Commit                 100    ✓     Recent commit
  Large Files                 100    ✓     No large files
  Outdated Dependencies       100    ✓     All deps current
  PR Review                   90     ✓     Good review practices
  Security                    92     ✓     No secrets, good practices
  Tech Debt                   85     ✓     Manageable debt
  Test Coverage               90     ✓     Good test coverage
```

## What it checks

repohealth runs **18 independent checks** grouped into categories:

### Core Repository Health (Weight: 100%)

| Check | Weight | What it detects |
|-------|--------|-----------------|
| **Working Tree** | 15 | Uncommitted, unstaged, or untracked changes |
| **Stale Branches** | 10 | Local branches already merged into default |
| **Essentials** | 20 | Missing README, LICENSE, .gitignore, or CI config |
| **Dependencies** | 15 | Outdated pip packages in requirements/pyproject |
| **Large Files** | 10 | Files exceeding size threshold (default 1MB) |
| **Activity** | 15 | How recently the last commit was made |
| **History** | 10 | Tracks health trends over time (local .repohealth_history) |
| **Last Commit** | 5 | Days since last commit |

### Code Quality (Weight: 100%)

| Check | What it measures |
|-------|------------------|
| **Code Churn** | Insertions + deletions per file — high churn indicates instability |
| **Commit Conventions** | Percentage of conventional commit messages (feat:, fix:, etc.) |
| **Dependency Graph** | Runtime vs dev deps, version pinning, unused/missing deps |
| **Doc Coverage** | Python docstring coverage, README sections, API docs, CHANGELOG |
| **Tech Debt** | TODO/FIXME/HACK comment density, complexity hints |

### Security & Process (Weight: 100%)

| Check | What it detects |
|-------|-----------------|
| **Security** | Hardcoded secrets, dangerous files, missing SECURITY.md, pre-commit, Dependabot |
| **PR Review** | Review coverage, time-to-merge, stale PRs, large PRs (via gh CLI) |
| **Outdated Dependencies** | pip packages newer than requirements files |

### Testing & Quality (Weight: 100%)

| Check | What it measures |
|-------|------------------|
| **Test Coverage** | Coverage from pytest --cov, coverage.py, or coverage badge |

## Installation

```bash
pip install repohealth
```

Or with [uv](https://github.com/astral-sh/uv):

```bash
uv add repohealth
```

## Usage

```bash
# Check current directory
repohealth

# Check a specific repo
repohealth /path/to/repo

# JSON output (great for CI)
repohealth --json-output

# Custom large-file threshold (KB)
repohealth --threshold 512
```

### Exit codes

- **0** — Grade A, B, or C (passing)
- **1** — Grade D or F (failing) — useful for CI gates

### CI integration

```yaml
# GitHub Actions example
- name: Check repo health
  run: |
    pip install repohealth
    repohealth --json-output
```

## Output Formats

### Terminal (default)

Rich table with color-coded grades:
- 🟢 **A** (90-100) — Excellent
- 🟢 **B** (80-89) — Good
- 🟡 **C** (70-79) — Acceptable
- 🔴 **D** (60-69) — Needs attention
- 🔴 **F** (0-59) — Critical issues

### JSON (`--json-output`)

```json
{
  "path": ".",
  "score": 92,
  "grade": "A",
  "checks": [
    {"name": "Working Tree", "score": 100, "status": "pass", "detail": "Clean working tree"},
    {"name": "Stale Branches", "score": 100, "status": "pass", "detail": "No stale branches"},
    ...
  ],
  "summary": {
    "total_checks": 18,
    "passed": 17,
    "failed": 1,
    "warnings": 0
  }
}
```

## Grading

| Score | Grade | Status |
|-------|-------|--------|
| 90-100 | A | ✓ Passing |
| 80-89 | B | ✓ Passing |
| 70-79 | C | ✓ Passing |
| 60-69 | D | ✗ Failing |
| 0-59 | F | ✗ Failing |

Exit code is 0 for grades A-C, 1 for D-F (useful for CI gates).

## Configuration

repohealth works with zero configuration. Just run it in any Git repo.

Optional configuration via command-line flags:

```bash
# Custom large-file threshold (KB)
repohealth --threshold 512

# JSON output for CI
repohealth --json-output

# Check specific repo
repohealth /path/to/repo
```

## Check Details

### Working Tree
Checks for uncommitted changes, unstaged changes, and untracked files. A clean working tree scores 100.

### Stale Branches
Finds local branches that have been merged into the default branch (main/master) but not deleted.

### Essentials
Verifies presence of:
- README (md/rst/txt)
- LICENSE
- .gitignore
- CI configuration (.github/workflows/, .gitlab-ci.yml, .circleci/, Jenkinsfile, etc.)

### Dependencies
Runs `pip list --outdated --format=json` and cross-references with requirements.txt, pyproject.toml, or setup.cfg.

### Large Files
Finds files larger than the threshold (default 1024KB). Configure with `--threshold KB`.

### Activity
Scores based on days since last commit: 0d=100, 1-7d=90, 8-30d=70, 31-90d=40, 90d+=0.

### Code Churn
Analyzes git history for insertions+deletions per file. High churn files are instability indicators.

### Commit Conventions
Parses commit messages for Conventional Commits format (feat:, fix:, chore:, etc.).

### Dependency Graph
Parses pyproject.toml/requirements.txt to categorize runtime/dev/optional/build deps, checks version constraint quality, and compares declared vs imported packages.

### Doc Coverage
- Python: Public class/function docstring coverage (skips private/underscore)
- README: Checks for Installation, Usage, Contributing, License, Changelog, Examples, API, Configuration, FAQ, Credits
- Other: API docs directory, CHANGELOG, CONTRIBUTING, CODE_OF_CONDUCT

### History
Saves health reports to `.repohealth_history/` and computes trend: improving/stable/declining.

### PR Review (requires `gh` CLI)
- Total/open/merged/closed PRs
- Average reviews per PR
- Average days to merge
- Stale PRs (>30d open)
- Unreviewed PRs (0 reviews)
- Large PRs (>400 lines changed)

### Outdated Dependencies
Compares `pip list --outdated` against requirements files.

### Security
- Secret detection: passwords, API keys, tokens, AWS creds, private keys, DB URIs, GitHub/GitLab/OpenAI tokens
- Dangerous files: .env, .pem, id_rsa, .npmrc, .netrc, etc.
- Checks for .gitignore entries, pre-commit, Dependabot/Renovate, SECURITY.md
- Optional pip-audit integration

### Tech Debt
Counts TODO/FIXME/HACK/XXX/BUG/OPTIMIZE/REVIEW comments per file.

### Test Coverage
Detects coverage from:
- `pytest --cov` output
- `.coverage` / `coverage.xml`
- Coverage badge in README

## Development

```bash
# Clone and setup
git clone https://github.com/jlaportebot/repohealth.git
cd repohealth
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check src/ tests/

# Format
ruff format src/ tests/
```

## License

MIT

---

**repohealth** — Built with 🦞 by Mister Lobster