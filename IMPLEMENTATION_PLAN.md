# Live Feed Investigation & Recovery Plan

## 1. Trace TUI Log Ingestion Path
- Review `internal/tui/run.go:startRunCmd` to document how the Bubble Tea program wires `runner.Options.Run` to the viewport state. Capture how `m.logCh` and `m.readLogs()` are scheduled so we know when refresh commands stop firing.
- Walk the `logLineMsg` handling in `internal/tui/update.go` (lines ~60-115) to verify when `handleRunFeedLine`, `persistLogLine`, and viewport flush thresholds run. Note any conditions (e.g., `runFeedDirtyLines`, `runFeedAutoFollow`, `viewport.AtBottom`) that could prevent refreshes once the buffer grows.
- Inspect `internal/tui/run_feed.go` helper methods (`handleRunFeedLine`, `handleIterationHeader`, `trimAutomationLogPrefix`) to ensure raw lines from Python are still parsed once prefixes change. Determine if the live feed stalls when the buffer hits `feedBufCap` or when `trimAutomationLogPrefix` returns an empty string.

## 2. Examine Runner Streaming & Channel Backpressure
- Audit `internal/runner/runner.go` focusing on `Options.Run`, `stream`, and the `trySend`/`sendLine` helpers. Confirm scanner buffering (`bufio.Scanner` with 1MB cap) and channel capacity (`make(chan runner.Line, 2048)`) align with the TUI consumer pace.
- Simulate slow consumer scenarios to see if the "log channel backlog full" diagnostic is triggered; if so, evaluate whether the TUI drops into a state where it never re-reads from `logCh` (inspect `m.readLogs()` in `internal/tui/messages.go`).
- Check whether `stream` closes the channel promptly on process exit to avoid the TUI waiting for new messages.

## 3. Validate Python Runner Output Cadence
- Inspect `tools/auto_prd/logging_utils.py` (`install_print_logger`, `PRINT_LOGGER_NAME`) to confirm log lines are emitted immediately and not buffered unexpectedly.
- Trace the automation flow in `tools/auto_prd/app.py` and `tools/auto_prd/review_loop.py` to see which prints/logs signal phase progress. Verify subprocess calls in `tools/auto_prd/command.py` and friends don’t consume stdout without re-streaming (e.g., `subprocess.run(..., capture_output=True)` might buffer output until completion).
- Identify any Python `print()` or logging invocations lacking `flush=True` (especially long-running loops) and decide whether to add explicit flushing or switch to `sys.stdout.write`.

## 4. Reproduce the Stalled Feed
- Use `make run` with a known PRD and instrumentation (e.g., enable DEBUG in `tools/auto_prd/logging_utils.logger`) to capture when the TUI stops updating.
- Capture timestamps from both the Go runner (`runner.Line.Time`) and Python logs to correlate when updates cease. Store findings in `logs/` for reference.

## 5. Propose Code Adjustments
- Based on findings from Tasks 1–4, draft concrete code changes: e.g., adjusting the TUI flush cadence, increasing/decreasing buffer caps, altering the runner channel mechanism, or ensuring Python writes line-buffered output.
- Document the proposed modifications per file (Go vs. Python) so implementation work can start immediately once approved.

## 6. Expand Test Coverage & Tooling
- Add targeted Go tests in `internal/tui/run_feed_test.go` (or new files) that simulate long streaming sessions and assert the viewport content advances past flush boundaries.
- Introduce Python-side tests under `tools/auto_prd/tests/` that mock long-running automation and verify stdout/stderr is flushed incrementally (potentially using `io.StringIO`).
- Consider a lightweight integration smoke test script (e.g., `tools/auto_prd/tests/test_integration_feed.py`) that spawns a fake subprocess emitting incremental logs to ensure the Go runner captures them in order.

## 7. Plan Validation & Rollout
- Once code changes are made, run `go test ./...`, `python3 -m unittest discover -s tools/auto_prd/tests`, and `make run` to verify live feed behavior.
- Prepare before/after evidence (screenshots of the TUI, trimmed log excerpts) and outline final documentation updates (README troubleshooting section or in-app status hints).
