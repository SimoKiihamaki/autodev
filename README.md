# aprd-tui — Interactive TUI for the PRD→PR Automation

A Bubble Tea terminal UI that drives your Python **auto_prd_to_pr_v3.py** pipeline.
Launch with a single binary, tweak settings (including **per-phase executors**), pick/tag a PRD, add an initial prompt, and run.
Shows live logs from the underlying Python process.

## Features

- Single binary `aprd` to start the TUI.
- Configure flags & env (executor policy, repo/base/branch, CI toggles, timings).
- **Select & tag** a PRD file (quick scan for `*.md`, add/remove tags).
- **Initial prompt** field (optional); injected as a temp overlay above your PRD for the first pass.
- **Per-phase executors** (implement, fix, PR, review_fix) via env overrides or policy fallback.
- **Start from any step** by toggling phases: local, pr, review_fix.
- Finds the Python automation script relative to the binary when the default path is missing.
- Persists each run’s logs to `~/.config/aprd/logs/` for post-run debugging.

## Live Feed at a Glance

- Streams the Python automation output into both the Logs tab and the Live Feed as batches of freshly read lines.
- Relies on the runner’s non-blocking channel to keep the UI responsive while always persisting a full log file.
- Read the [Live Feed guide](docs/live-feed.md) for the detailed architecture and logging expectations.

## Requirements

- Go 1.21+
- Python 3.10+ (required for `zip(strict=True)` and modern type hints)
- CLIs: `codex` (for codex-first|codex-only), `claude` (for claude-only|codex-first), `coderabbit`, `git`, `gh`

> **Note:** The Python requirement is enforced in `tools/auto_prd/pyproject.toml` via `requires-python = ">=3.10"`.
> This prevents installation on unsupported Python versions.

## Quick start

```bash
make build
./bin/aprd
```

In Settings:
- Python Command: `python3`
- Python Script: `tools/auto_prd_to_pr_v3.py` (default)

Then pick a PRD, add optional Prompt, set phases, and **Enter** on Run.

## Advanced control

### Select phases to run
From the **Env** tab, toggle which phases to execute:
- **[L] Local:** run the local implementation loop
- **[P] PR:** push & open PR
- **[R] ReviewFix:** review/fix loop (requires an open PR; if PR phase is off we try to infer PR from current branch)

Under the hood this maps to the Python tool’s `--phases local,pr,review_fix`.

### Per-phase executors
In **Settings**, set the executor for each phase:
- Exec (implement): `codex|claude|<empty>`
- Exec (fix): `codex|claude|<empty>`
- Exec (pr): `codex|claude|<empty>`
- Exec (review_fix): `codex|claude|<empty>`

If left empty, the global **Executor policy** applies.
This is implemented via env vars: `AUTO_PRD_EXECUTOR_IMPLEMENT|FIX|PR|REVIEW_FIX`.

## Troubleshooting Live Feed

- **UI quiet but log file growing**: The reader loop likely stopped rescheduling. Reopen the TUI or restart the run to reset `readLogsBatch()`.
- **UI and log file both quiet**: The script is not emitting output—ensure it runs with `PYTHONUNBUFFERED=1` or `python -u`.
- **Still unsure?** Confirm the automation script is printing the expected markers described in the [Live Feed guide](docs/live-feed.md).

### Common delays

The live feed in the Logs tab may pause for minutes during long operations while the Python process works without emitting new lines. Typical long-running steps include Codex/Claude implementation passes (2-10 minutes), CodeRabbit reviews (1-5 minutes), and Git operations during PR creation (30 seconds to 2 minutes). Review the last log entry and the active phase in the status bar before assuming the feed is stuck.

### If the feed seems actually stuck

If the feed has not updated for more than 15 minutes, the process may have encountered an issue:

1. Check for lingering `python3` or `codex` processes.
2. Review the saved logs in `~/.config/aprd/logs/`.
3. Restart and resume by toggling phases (for example, run only the "PR" and "ReviewFix" phases).

### Performance tips

- Use a fast executor (`codex` is typically faster than `claude` for implementation).
- Enable CodeRabbit to catch issues early and shrink review cycles.
- Monitor system resources when processing large PRDs.
