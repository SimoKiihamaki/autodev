# Live Feed Investigation – Remaining Tasks

## Task 4 – Capture Stall Reproduction Evidence
- Run `make run` (or an equivalent scripted invocation) against a representative PRD with DEBUG logging enabled so both the Go runner and Python automation emit detailed timestamps.
- Record the per-line `runner.Line.Time` values alongside the corresponding Python log timestamps (e.g., by teeing stdout/stderr to a structured log). Include notes on the scenario exercised (buffers hit, phases executed, duration).
- Commit the correlated timeline under `logs/` (for example, `logs/stall_repro_<date>.md`) so future investigations can reference concrete evidence rather than hypotheses.

## Task 7 – Final Validation & Rollout Evidence
- Execute `go test ./...` and `python3 -m unittest discover -s tools/auto_prd/tests` on the implementation branch and capture the summarized outputs. If any suites are skipped, document why.
- Perform an end-to-end sanity check with `make run`, taking screenshots or trimmed terminal captures that show the live feed progressing without stalls during a realistic automation pass.
- Collect the artifacts above (test command outputs, screenshots/log excerpts) and store them in the repository or link them from documentation so the rollout package contains explicit before/after proof.
