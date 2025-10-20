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
