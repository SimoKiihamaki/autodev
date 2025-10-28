# Live Feed Guide

## Overview

```
Python proc ─stdout/stderr─> runner(stream) ─chan runner.Line─> TUI(update loop)
                         └─────────────────> log file (always complete)
```

## Responsibilities

- **Runner**
  - Launches the Python automation process with `PYTHONUNBUFFERED=1`.
  - Scans stdout/stderr, packages each line as `runner.Line`, and sends it over the channel without blocking.
  - Persists every line to the log file so disk logs remain the source of truth.
  - Closes the channel after EOF; no other component should close it.
- **TUI**
  - Uses `readLogsBatch()` to block for the first line, then drain up to the configured batch size before yielding.
  - Streams lines into both the Logs viewport and the Live Feed, applying the existing formatting helpers.
  - Flushes any buffered state when the channel closes and stops scheduling further reads.

## Output Conventions for Automation Scripts

- Use `print("=== Phase: name ===")` when entering a new phase.
- Use `print("→ Doing task...")` to announce long-running work.
- Use `print("✓ Done task")` when a step completes.
- Flushing is enforced by environment variables, but it is fine to set `flush=True` when emitting critical status messages.

## Performance & Drops

- The runner’s channel is sized to 2,048 entries; this bounds memory growth while allowing short bursts to flow through.
- Live Feed updates favor recency—extreme bursts may skip some lines in the UI, but the on-disk log always contains every entry.
- If the UI appears quiet, check the footer counters or open the saved log file to confirm ongoing activity.
