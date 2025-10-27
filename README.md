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

## Requirements

- Go 1.21+
- Python 3.9+
- CLIs: `codex` (for codex-first|codex-only), `claude` (for claude-only|codex-first), `coderabbit`, `git`, `gh`

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

## Troubleshooting

### Live feed appears to "stall" during long operations

**Symptom**: The live feed in the Logs tab stops updating for minutes, even though work is continuing.

**Cause**: This is normal behavior during long-running operations (like Codex execution). The Python process may be working on a task that takes several minutes, during which no new log lines are generated.

**What's happening**: The feed is not actually stalled - it's just waiting for the next status update. Common long operations include:
- Codex/Claude implementation passes (2-10 minutes)
- CodeRabbit reviews (1-5 minutes)
- Git operations during PR creation (30 seconds to 2 minutes)

**Solutions**:
1. **Wait patiently** - Most operations complete within 10 minutes
2. **Check the current phase** - The status bar shows what phase is active
3. **Review the last log entry** - It usually indicates what operation is in progress
4. **Enable DEBUG mode** - Set `AUTO_PRD_DEBUG=1` in environment for more verbose output

### If the feed seems actually stuck (rare)

If the feed hasn't updated for more than 15 minutes, the process may have encountered an issue:

1. **Check the process**: Look for running `python3` or `codex` processes
2. **Review the logs**: Full logs are saved to `~/.config/aprd/logs/`
3. **Restart and resume**: You can often restart and use the "PR" and "ReviewFix" phases only

### Performance tips

- **Use a fast executor**: `codex` is typically faster than `claude` for implementation
- **Enable CodeRabbit**: It can catch issues early, reducing review cycles
- **Monitor resource usage**: Large PRDs may require more memory and time
