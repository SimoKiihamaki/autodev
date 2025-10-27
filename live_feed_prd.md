# PRD – Live Feed Investigation & Recovery

## Overview
Document the live log ingestion path, runner streaming behavior, and follow-up work needed to restore the real-time feed inside the Bubble Tea TUI.

## Tasks

- [x] Task 1 – Trace the TUI log ingestion path and viewport updates.
- [x] Task 2 – Examine runner streaming and channel backpressure handling.
- [ ] Task 3 – Validate Python runner output cadence.
- [ ] Task 4 – Reproduce the stalled feed.
- [ ] Task 5 – Propose code adjustments.
- [ ] Task 6 – Expand test coverage & tooling.
- [ ] Task 7 – Plan validation & rollout.

## Findings

### Task 1 – TUI log ingestion and viewport flow
- `startRunCmd` (`internal/tui/run.go:55-137`) creates a buffered `logCh` (`cap=2048`), clears the log + feed buffers, and schedules `readLogs()` and `waitRunResult()` so the Bubble Tea program starts consuming runner output immediately.
- `readLogs` (`internal/tui/messages.go:16-27`) performs a single receive from `logCh`; each `logLineMsg` schedules another call so the consumer keeps draining until the channel closes.
- `logLineMsg` handling (`internal/tui/update.go:52-67`) formats the line, writes it to disk via `persistLogLine`, trims the in-memory log buffer to `maxLogLines=2000`, and refreshes the logs viewport when either fewer than `logFlushStep=8` lines have been gathered or the dirty counter reaches eight.
- `handleRunFeedLine` (`internal/tui/run_feed.go:47-90`) mirrors each display line into `runFeedBuf`, trimming to the most recent `feedBufCap=800` entries. It flushes the run feed viewport immediately when the buffer grows for the first time or after trimming, otherwise it batches redraws using `feedFollowFlushStep=4` when auto-following or `feedFlushStep=16` when the viewport is scrolled away from the bottom.
- `runFeedAutoFollow` defaults to `true` on run start (`internal/tui/update.go:40-47`); scrolling keys call `updateRunFeedFollowFromViewport` (`internal/tui/update_keys.go:70-111`) so the viewport only re-scrolls when the user stays at the bottom. Toggling `f` re-enables auto-follow and jumps back to the latest line.
- `consumeRunSummary` (`internal/tui/run_feed.go:108-196`) strips Python logging prefixes with `trimAutomationLogPrefix`, updates iteration/section metadata through `handleIterationHeader` and `handleSectionHeader`, and tracks status phrases so the run dashboard reflects phase progress even when viewport refreshes are throttled.

### Task 2 – Runner streaming/backpressure
- The runner launches the Python process with `Options.Run` (`internal/runner/runner.go:165-255`), wiring both stdout and stderr through `stream`. A `sync.WaitGroup` waits for both readers before emitting a synthetic `"process finished"` line and closing the shared channel.
- `stream` (`internal/runner/runner.go:258-289`) uses a pooled 64 KB buffer and raises the scanner limit to 1 MiB to avoid truncating long log lines. Each line is tagged with `time.Now()` and `Err=true` when sourced from stderr.
- `trySend`/`sendLine` (`internal/runner/runner.go:41-55`) perform non-blocking writes. When the 2048-slot channel fills, the first dropped record triggers a best-effort `"log channel backlog full (capacity 2048)"` diagnostic before subsequent lines are skipped until the consumer drains the queue.
- Cancelation flows (`internal/runner/runner.go:227-247`) send `SIGINT`, wait up to two seconds, then escalate to `Kill`, ensuring that both stream goroutines exit and the channel closes so the TUI stops polling.
- The goroutine launched by `startRunCmd` wraps `Options.Run` with a panic guard (`internal/tui/run.go:105-134`). Any panic—including closing an already-closed channel—gets surfaced back into the TUI via `logCh` and propagated as the run result, preventing silent stalls.
