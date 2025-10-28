Below is a **focused, implementation-ready task list** to get the Live Feed working, simplify the logging pipeline, and upgrade the docs. Each task includes *what to change*, *where to change it*, concrete code snippets, and *acceptance criteria*. Adjust file paths if your repo layout differs, but these reference the current `autodev/aprd` structure.

---

## A) HOTFIX: Make the Live Feed actually stream

### **Task A1 — Make `readLogsBatch()` block for the first line, then drain quickly**

**Problem:** The batch reader returns `nil` when the channel is briefly empty at startup, so the Bubble Tea loop never “latches” onto logs.

**Files**

* `internal/tui/update.go` (or `internal/tui/commands.go` if you split commands)
* `internal/tui/messages.go` (for message types)

**Steps**

1. **Define a single batch message type** (if not already present):

   ```go
   // internal/tui/messages.go
   type logBatchMsg struct {
       lines  []runner.Line
       closed bool // true when channel closed while reading
   }
   ```

2. **Implement a robust reader that:**

   * Blocks until *one* line or the channel closes,
   * Then drains up to `N` more lines without blocking,
   * Returns a `logBatchMsg` every time (never `nil` unless the channel is already closed before the first read).

   ```go
   // internal/tui/update.go (or commands.go)
   func (m model) readLogsBatch() tea.Cmd {
       if m.logCh == nil {
           return nil
       }
       ch := m.logCh
       const maxBatch = 25 // or from config
       return func() tea.Msg {
           // BLOCK for the first line (don’t time out here)
           line, ok := <-ch
           if !ok {
               return logBatchMsg{lines: nil, closed: true}
           }
           lines := make([]runner.Line, 0, maxBatch)
           lines = append(lines, line)

           // Non-blocking drain up to maxBatch
           for len(lines) < maxBatch {
               select {
               case l, ok := <-ch:
                   if !ok {
                       return logBatchMsg{lines: lines, closed: true}
                   }
                   lines = append(lines, l)
               default:
                   return logBatchMsg{lines: lines, closed: false}
               }
           }
           return logBatchMsg{lines: lines, closed: false}
       }
   }
   ```

3. **Handle the batch in the update loop** (append to both Logs & Live Feed; then immediately schedule the next batch read unless closed):

   ```go
   // internal/tui/update.go
   case logBatchMsg:
       for _, ln := range msg.lines {
           m.persistLogLine(ln)                 // write to file
           disp, plain := m.formatLogLine(ln)   // same formatter you already have
           // Logs panel (append + flush)
           m.logBuf = append(m.logBuf, disp)
           m.logs.SetContent(strings.Join(m.logBuf, "\n"))

           // Live feed (append + flush)
           m.handleRunFeedLine(disp, plain)
       }

       if msg.closed {
           // Channel closed: stop reading and do any final UI flush
           m.logCh = nil
           // (optional) ensure final flush of run feed if you buffer
           return m, nil
       }
       // Continue reading
       return m, m.readLogsBatch()
   ```

**Acceptance criteria**

* Starting a run shows the first log line in **≤1s**.
* Subsequent lines appear in the **Logs** viewport and the **Live Feed** as they arrive.
* No more “Awaiting updates…” stuck state while the process is active.

---

### **Task A2 — Remove the double close on `logCh`**

**Problem:** The channel is closed by both the runner and the TUI launcher goroutine → race/panic.

**Files**

* `internal/tui/run.go` (or wherever you spawn the run and create `m.logCh`)
* `internal/runner/runner.go`

**Steps**

1. **In TUI launcher**: **remove** any `defer close(logCh)` after creating the channel. The **producer (runner)** owns closing the channel.
2. **In runner**: keep the single responsibility to close `o.Logs` **once** after all stdout/stderr streaming goroutines exit.

**Acceptance criteria**

* No runtime panic `close of closed channel`.
* On process exit, `logBatchMsg{closed:true}` is received and the TUI stops reading gracefully.

---

### **Task A3 — Guarantee unbuffered Python output (belt-and-suspenders)**

**Problem:** If a different interpreter or env path runs, buffering can return.

**Files**

* `internal/runner/runner.go` (before `cmd.Start()`), wherever you build env/args.

**Steps**

1. Ensure **both**:

   * `PYTHONUNBUFFERED=1` is in `cmd.Env`.
   * The `PythonCommand` includes `-u` or the script adds `flush=True` on critical prints.

   ```go
   env := os.Environ()
   env = append(env, "PYTHONUNBUFFERED=1")
   cmd.Env = env
   // If you accept a python command string, ensure it defaults to "python3 -u"
   ```

**Acceptance criteria**

* If you run the script *without* your TUI (plain `exec`), each `print()` with newline appears immediately on the pipe.

---

## B) CLEANUP: Reduce redundancy / over‑engineering

### **Task B1 — Remove legacy single-line reader**

**Problem:** Two parallel pipelines (single-line `logLineMsg` and batch `logBatchMsg`) fragment logic.

**Files**

* `internal/tui/update.go`
* `internal/tui/messages.go`
* `internal/tui/run.go` (or commands file)

**Steps**

1. Delete `logLineMsg` and `readLogs()` code paths.
2. Ensure **only** `readLogsBatch()` is used at run start and for rescheduling.
3. Consolidate handling into the `logBatchMsg` case.

**Acceptance criteria**

* Grep for `logLineMsg` returns **0** results.
* All log updates flow through the single `logBatchMsg` path.

---

### **Task B2 — Simplify viewport flush strategy**

**Problem:** Complex “dirty line” counters/adaptive flush introduces state & bugs.

**Files**

* `internal/tui/run_feed.go`
* `internal/tui/update.go`

**Steps**

1. **Logs panel**: remove “dirty line counter” and refresh **every batch** (you already batch 25 lines → a single `SetContent()` per message is fine).
2. **Run feed**: flush **every batch** too. Optionally cap to 1–3 lines if you want faster “tick” feel:

   * Easiest: flush every time `logBatchMsg` arrives.
   * Remove adaptive `follow` timers unless you’ve measured a real benefit.

**Acceptance criteria**

* Consistent timely updates; no noticeable UI stutter; code is easier to read.

---

### **Task B3 — Collapse duplicate run-feed handlers**

**Problem:** Parallel implementations (e.g., `batchEnabledModel.handleRunFeedLineBatch` **and** `model.handleRunFeedLine`) cause drift.

**Files**

* `internal/tui/run_feed.go`

**Steps**

1. Keep **one** `handleRunFeedLine(disp, plain string)` and call it from the `logBatchMsg` loop.
2. Delete / inline any `*Batch` variants if they only differ by minor accounting.

**Acceptance criteria**

* Only one feed handler; no duplicated parsing/state transitions.

---

### **Task B4 — Make channel size explicit & documented**

**Problem:** Silent drops when the UI doesn’t consume; sometimes fine, but document.

**Files**

* `internal/runner/runner.go`
* `internal/tui/run.go` (where channel created)

**Steps**

1. Set capacity (e.g., `make(chan runner.Line, 2048)`) in **one** place (TUI where it’s created).
2. **Document**: runner uses non-blocking send; if buffer full, it logs a warning and drops lines, but **all lines still go to the file sink**.

**Acceptance criteria**

* One definition of buffer size; code comment describing drop policy present.

---

## C) VALIDATION: Add tests / quick tooling

### **Task C1 — Unit-test the batch reader**

**Files**

* `internal/tui/log_reader_test.go`

**Steps**

1. Simulate `logCh := make(chan runner.Line, 8)`.
2. Push lines with small sleeps; assert:

   * First `readLogsBatch()` blocks till first line then returns.
   * Subsequent calls drain up to `maxBatch`.
   * When channel closes, you get `{closed:true}`.

**Acceptance criteria**

* Tests pass; regression guard exists for read loop behavior.

---

### **Task C2 — Integration smoke test with a dummy process**

**Files**

* `internal/runner/runner_integration_test.go` or `tests/smoke_live_feed.sh` + `go test` wrapper

**Steps**

1. Spawn `bash -lc 'for i in $(seq 1 10); do echo "line $i"; sleep 0.05; done'`.
2. Wire into the runner; assert at least 10 lines made it to the TUI model buffers.

**Acceptance criteria**

* Live updates are observed (programmatically via model state).

---

## D) DOCS: Explain how the system works & how to use it

### **Task D1 — Add `docs/live-feed.md` (HOW IT WORKS + BEST PRACTICES)**

**Files**

* `docs/live-feed.md` (new)

**Content outline**

* **Overview diagram (ASCII)**

  ```
  Python proc ─stdout/stderr─> runner(stream) ─chan runner.Line─> TUI(update loop)
                           └───────────────> log file (always complete)
  ```
* **Responsibilities**

  * Runner: launch, set `PYTHONUNBUFFERED=1`, scan lines, non-blocking send, close channel.
  * TUI: batch-read channel until closed, update Logs & Live Feed viewports, final flush.
* **Output conventions for scripts**

  * Use `print("=== Phase: X ===")` for phases.
  * Use `print("→ Doing Y...")` when starting a long step.
  * Use `print("✓ Done Y")` on completion.
  * Flush is ensured by env, but ok to use `flush=True` for emphasis.
* **Performance & drops**

  * Channel size 2048, non-blocking send: very large bursts may skip some Live Feed lines; **file log is always complete**.

---

### **Task D2 — Update `README.md`**

**Files**

* `README.md`

**Add sections**

* **“Live Feed at a Glance”** linking to `docs/live-feed.md`.
* **“Troubleshooting Live Feed”**

  * If UI silent but log file has content → reader loop issue.
  * If UI & log file silent → script buffering or not printing.
  * Check `PYTHONUNBUFFERED` and `-u`.

---

### **Task D3 — Add `CONTRIBUTING.md` snippet**

**Files**

* `CONTRIBUTING.md`

**Add**

* “When touching logging: keep one reader (`readLogsBatch`) that blocks for the first line and drains; don’t add timeouts that return `nil`.”
* “Don’t close `logCh` in two places; producer closes, consumer reads to EOF.”

---

## E) OPTIONAL QUALITY-OF-LIFE

### **Task E1 — Configurable batch size**

* Add `aprd.yaml` or CLI flag `--log-batch N` (default 25).
* Wire into `readLogsBatch()`.

### **Task E2 — Minimal debug overlay (toggle)**

* Provide a small counter in the footer: “sent: X | recv: Y | dropped: Z”.
* Helps diagnose field issues quickly without opening the log file.

---

## Suggested commit plan

1. **feat(tui): robust batch reader; remove single-line path**
   A1, B1, B2 (basic flush simplification for both viewports)

2. **fix(tui/runner): single channel owner; remove double-close**
   A2, B4 (doc comments)

3. **chore(runner): enforce unbuffered python; doc policy**
   A3

4. **test(tui,runner): batch reader & smoke process tests**
   C1, C2

5. **docs: live feed guide + readme + contributing**
   D1, D2, D3

---

## Quick checklist (engineering acceptance)

* [ ] Starting a run shows first line in < 1s and keeps updating.
* [ ] No panic on exit; channel is closed once by runner.
* [ ] Logs panel always shows every line seen; Live Feed shows key lines (per parser).
* [ ] File log is complete even if channel overflows.
* [ ] Unit/integration tests pass.
* [ ] `docs/live-feed.md`, `README.md`, `CONTRIBUTING.md` updated and accurate.

---

If you want, I can also provide “drop‑in” patches (diffs) for the reader + update loop based on your current files—the above code is designed to paste directly with minimal adaptation.
