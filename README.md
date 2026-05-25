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

  Check           Score  Status  Detail
 ─────────────── ────── ─────── ──────────────────────
  Working Tree      100    ✓     Clean working tree
  Stale Branches    100    ✓     No stale branches
  Essentials        100    ✓     All essentials present
  Dependencies      100    ✓     All deps up-to-date
  Large Files       100    ✓     No files ≥1024KB
  Activity          100    ✓     Last commit 0d ago
```

## What it checks

| Check | Weight | What it detects |
|-------|--------|-----------------|
| **Working Tree** | 15 | Uncommitted, unstaged, or untracked changes |
| **Stale Branches** | 10 | Local branches already merged into default |
| **Essentials** | 20 | Missing README, LICENSE, .gitignore, or CI config |
| **Dependencies** | 15 | Outdated pip packages in requirements/pyproject |
| **Large Files** | 10 | Files exceeding a size threshold (default 1MB) |
| **Activity** | 15 | How recently the last commit was made |

## Installation

```bash
pip install repohealth
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

- **0** — Grade A, B, or C
- **1** — Grade D or F (useful for CI gates)

### CI integration

```yaml
# GitHub Actions example
- name: Check repo health
  run: |
    pip install repohealth
    repohealth --json-output
```

## License

MIT
