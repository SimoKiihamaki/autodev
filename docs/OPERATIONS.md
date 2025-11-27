# AutoDev Operations Guide

This guide covers day-to-day operations with the AutoDev system.

## Quick Start

```bash
# Build and run
make build
./bin/aprd

# Or build, install to PATH, then run
make install
aprd
```

## TUI Navigation

### Tab Overview

| Tab | Key | Purpose |
|-----|-----|---------|
| Run | `1` | Execute automation, view status |
| PRD | `2` | Select and preview PRD files |
| Settings | `3` | Configure paths, models, executors |
| Env | `4` | Toggle phases and flags |
| Prompt | `5` | Add initial instructions |
| Logs | `6` | View live execution output |
| Help | `?` | Usage instructions |

### Key Bindings

| Key | Action |
|-----|--------|
| `1-6` | Switch to tab |
| `?` | Toggle help |
| `Tab` | Navigate forward |
| `Shift+Tab` | Navigate backward |
| `Enter` | Confirm/Execute |
| `Esc` | Cancel/Back |
| `Ctrl+S` | Save configuration |
| `Ctrl+R` | Reset to defaults |
| `Ctrl+C` | Cancel run / Quit |

## Configuration

### Config File Location

```
~/.config/aprd/config.yaml
```

### Key Settings

```yaml
# Executor selection
executor_policy: "codex-first"  # codex-first, codex-only, claude-only

# Per-phase executor overrides
phase_executors:
  implement: ""      # "", "codex", or "claude"
  fix: ""
  pr: ""
  review_fix: ""

# Phases to run
run_phases:
  local: true        # Local implementation phase
  pr: true           # PR creation phase
  review_fix: true   # Review and fix phase

# Flags
flags:
  allow_unsafe: false
  dry_run: false
  sync_git: false
  infinite_reviews: false

# Timing
timings:
  wait_minutes: 0
  review_poll_seconds: 120
  idle_grace_minutes: 10
  max_local_iters: 50
```

## Running Automation

### Basic Run

1. Navigate to PRD tab (`2`)
2. Select a PRD file from the list
3. (Optional) Configure settings in Settings tab (`3`)
4. (Optional) Add initial instructions in Prompt tab (`5`)
5. Go to Run tab (`1`) and press `Enter`

### Monitoring Progress

- **Logs tab** (`6`): Live stdout/stderr from Python process
- **Run tab** (`1`): Phase progress stepper
- **Status line**: Current operation summary

### Cancelling a Run

- Press `Ctrl+C` to cancel the current run
- Wait for graceful shutdown
- Check Logs tab for cleanup status

## Session Management

### Session Files

Sessions are stored in:
```
~/.config/aprd/sessions/{session_id}.json
```

Each session contains:
- PRD hash for change detection
- Feature progress
- Checkpoint data for resume

### Tracker Files

Project-local tracker:
```
{repo}/.aprd/tracker.json
```

Contains:
- Feature list with status
- Task breakdowns
- Verification evidence
- Commit associations for rollback

## Troubleshooting

### Common Issues

#### "No PRD selected"
- Navigate to PRD tab and select a file
- PRD files are scanned from current directory (*.md)

#### "Config file corrupt"
- Delete `~/.config/aprd/config.yaml`
- Restart aprd to regenerate defaults

#### Agent execution fails
- Check that `codex` or `claude` CLI is installed
- Verify API credentials in environment
- Check Logs tab for detailed error

#### Tests fail during verification
- Check that project tests pass locally
- Verify test command in project Makefile
- Check for flaky tests

### Viewing Logs

```bash
# TUI persists logs to:
~/.config/aprd/logs/{session_id}.log

# View most recent log:
ls -lt ~/.config/aprd/logs/ | head -2
```

### Resetting State

```bash
# Reset config to defaults
rm ~/.config/aprd/config.yaml

# Clear all sessions
rm -rf ~/.config/aprd/sessions/

# Clear project tracker
rm -rf .aprd/
```

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `AUTO_PRD_EXECUTOR_POLICY` | Override executor policy |
| `AUTO_PRD_EXECUTOR_IMPLEMENT` | Override implement phase executor |
| `AUTO_PRD_EXECUTOR_FIX` | Override fix phase executor |
| `AUTO_PRD_EXECUTOR_PR` | Override PR phase executor |
| `AUTO_PRD_EXECUTOR_REVIEW_FIX` | Override review_fix phase executor |
| `AUTO_PRD_ALLOW_UNSAFE_EXECUTION` | Allow unsafe operations |
| `AUTO_PRD_CODEX_TIMEOUT_SECONDS` | Codex execution timeout |
| `AUTO_PRD_CLAUDE_TIMEOUT_SECONDS` | Claude execution timeout |

## Rollback Operations

### Rolling Back a Feature

If a feature implementation fails or needs to be undone:

```python
# Using Python directly
from tools.auto_prd.rollback import run_rollback
from pathlib import Path

result = run_rollback(
    repo_root=Path("."),
    feature_id="F001",
    dry_run=False,
)
print(f"Rolled back: {result.commits_reverted}")
```

### Rolling Back to Checkpoint

For more drastic rollback to a known good state:

```python
from tools.auto_prd.rollback import rollback_to_checkpoint
from pathlib import Path

result = rollback_to_checkpoint(
    repo_root=Path("."),
    checkpoint_sha="abc123",
    dry_run=True,  # Preview first
)
```

## Best Practices

### PRD Writing

1. Use clear, actionable requirements
2. Include acceptance criteria
3. Specify testing requirements
4. Define measurable outcomes

### Configuration

1. Start with defaults
2. Enable `dry_run` for testing
3. Use per-phase executor overrides for fine control
4. Set reasonable timeouts

### Monitoring

1. Watch Logs tab for real-time progress
2. Check tracker.json for feature status
3. Review git log for commits per feature
4. Verify tests pass before marking complete

### Recovery

1. Keep `sync_git: true` for safer operation
2. Use checkpoints for long-running sessions
3. Know how to rollback features individually
4. Maintain backup branches

## CLI Reference

```bash
# Build
make build          # Build binary to ./bin/aprd
make install        # Build and install to system PATH
make clean          # Remove build artifacts

# Testing
make test           # Run all tests
make ci             # Run full CI suite (lint + test + race)
make lint           # Run linters only
make lint-fix       # Auto-fix lint issues

# Development
make run            # Build and run
make tidy           # Update Go modules
```
