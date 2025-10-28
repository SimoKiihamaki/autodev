Below is a **decomposed, implementation‑ready task plan** for tightening up the UI/UX of the **autodev** TUI and guaranteeing that all selectable features are actually wired to the underlying script/runner. I reference concrete files already present in the repo (not exhaustive):

* `internal/tui/model.go`
* `internal/tui/update_tabs.go`
* `internal/tui/view.go`
* `internal/tui/run.go`
* `internal/runner/runner.go`
* `internal/config/config.go`
* (tests) `internal/tui/run_feed_test.go`, `internal/tui/log_reader_test.go`, `internal/runner/runner_test.go`
* (entry points) `cmd/api/main.go`, `cmd/aprd/main.go`

> Where I propose new helper files, I keep them in `internal/tui/` and clearly mark them **NEW**.

---

## Task Tracker

- [x] A1 — Centralize all keybindings into a single source of truth
- [x] A2 — Guard global shortcuts while the user is typing
- [ ] A3 — Make tab navigation predictable and non-conflicting
- [ ] A4 — Enforce “no overlapping single-letter keys across tabs” (except navigation)
- [ ] A5 — Smooth, consistent field navigation & wrap-around
- [ ] B1 — Standardize tab model and identifiers
- [ ] B2 — Unsaved indicator & quit confirmation
- [ ] C1 — Single function to build runner args/env from config
- [ ] C2 — Audit: TUI state → config.Config fields
- [ ] C3 — Save everywhere with **Ctrl+S**
- [ ] D1 — Follow/Unfollow logs toggle and persistence
- [ ] D2 — Error surfacing from runner
- [ ] E1 — Autogenerate help from KeyMap
- [ ] F1 — Keystroke guard tests
- [ ] F2 — No overlap test across tabs (non-nav single letters)
- [ ] F3 — End-to-end wiring: config → BuildArgs → runner
- [ ] G1 — Status line & transient toasts
- [ ] G2 — Reset keys and defaults

---

## Epic A — Keyboard model & navigation (no overlaps, smooth typing)

### A1 — Centralize all keybindings into a single source of truth

**Goal:** prevent drift and overlaps; auto‑render help from the same map.

* **Where**

  * **Add:** `internal/tui/keys.go` (**NEW**)
  * **Touch:** `internal/tui/model.go`, `internal/tui/view.go`, `internal/tui/update_tabs.go`

* **What to implement**

  * Define:

    ```go
    // internal/tui/keys.go
    package tui
    type Action string
    const (
      ActQuit Action = "quit"
      ActSave Action = "save"
      ActNextTab Action = "next_tab"
      ActPrevTab Action = "prev_tab"
      ActGotoTab1 Action = "goto_tab_1"
      // ... ActGotoTabN, etc.
      // Tab-local actions:
      ActRun Action = "run"
      ActToggleFollowLogs Action = "toggle_follow_logs"
      // add others as needed
    )
    type KeyCombo struct { Key string; Alt, Ctrl bool }
    type KeyMap struct {
      Global map[Action][]KeyCombo
      PerTab map[string]map[Action][]KeyCombo // tabID -> action -> keys
    }
    func DefaultKeyMap() KeyMap { /* fill in once */ }
    ```
  * Hold `m.keys KeyMap` in `model.go`; switch all scattered key checks to table lookups.
  * In `view.go` render a help panel from `m.keys` (so docs always match behavior).

* **Acceptance**

  * There is exactly **one** definition of each binding.
  * Removing/adding a binding affects both behavior and help automatically.

---

### A2 — Guard global shortcuts while the user is typing

**Goal:** pressing letters/digits inside inputs/lists should not trigger global actions.

* **Where**

  * `internal/tui/model.go` (Update loop, model state)
  * `internal/tui/update_tabs.go` (tab switching code)

* **What to implement**

  * Track a **typing state**:

    ```go
    // model.go
    type Model struct {
      // ...
      typing bool // true when any input/textarea is focused
    }
    func (m *Model) SetTyping(on bool) { m.typing = on }
    func (m Model) IsTyping() bool     { return m.typing }
    ```
  * Wherever your text inputs/textareas/list filters gain/lose focus, call `SetTyping(true/false)`.
  * In the central key handler, **ignore** global shortcuts (quit, tab digits, etc.) when `m.IsTyping()` is true.

* **Acceptance**

  * User can type `q`, digits `0‑9`, `?`, etc. in inputs without unintended quits/tab jumps.
  * Regression test (see **F1**) covers this.

---

### A3 — Make tab navigation predictable and non‑conflicting

**Goal:** no accidental tab switching when entering numbers; provide alternative combos.

* **Where**

  * `internal/tui/update_tabs.go`
  * `internal/tui/view.go` (help text sourced from KeyMap)

* **What to implement**

  * Option 1 (recommended): switch tab‑by‑number to **Alt+1..Alt+N** (or **Ctrl+1..Ctrl+N**); keep bare digits for data entry.
  * Option 2: keep bare digits but only when `!m.IsTyping()` (A2).
  * Ensure all visible tabs have corresponding mappings; if you show N tabs, include `ActGotoTab1..N`.

* **Acceptance**

  * Numeric typing in fields never switches tabs.
  * All tabs are reachable with a documented combo (and shown in help).

---

### A4 — Enforce “no overlapping single‑letter keys across tabs” (except navigation)

**Goal:** “r” should not mean different things in different tabs (unless it’s Up/Down/Enter/Tab).

* **Where**

  * **Add tests:** `internal/tui/keymap_test.go` (**NEW**)
  * `internal/tui/keys.go` (source of truth)

* **What to implement**

  * In the test: build a map for each tab `{keyCombo -> action}` and **fail** if a single letter (no modifiers) is bound to different actions across two tabs.
    Allowlist: arrows, PageUp/Down, Enter, Esc, Tab/Shift+Tab.
  * Fix conflicts by converting secondary uses to **Ctrl+X** or **Alt+X**.

* **Acceptance**

  * Test fails when an overlap is introduced; currently passes after fixes.

---

### A5 — Smooth, consistent field navigation & wrap‑around

**Goal:** consistent Up/Down/Tab behavior across forms; wrap around at ends.

* **Where**

  * `internal/tui/model.go` (shared helpers)
  * Form‑specific code in `internal/tui/...` (wherever you maintain field indices)

* **What to implement**

  * Add utility:

    ```go
    func wrapIndex(idx, n int) int { 
      if n == 0 { return 0 }
      if idx < 0 { return n-1 }
      if idx >= n { return 0 }
      return idx
    }
    ```
  * Apply in Up/Down handlers on settings/env forms.
  * Make **Tab** = next field, **Shift+Tab** = previous; **Enter** inside a field either submits or advances (choose one policy; be consistent).

* **Acceptance**

  * Down on last field goes to first, Up on first goes to last.
  * Tab/Shift+Tab consistently move focus; Enter behavior is consistent across forms.

---

## Epic B — Tabs, layout, and state feedback

### B1 — Standardize tab model and identifiers

**Goal:** clear, stable IDs used in keymaps and routing.

* **Where**

  * `internal/tui/update_tabs.go`
  * `internal/tui/model.go`

* **What to implement**

  * Create a `const` block for tab IDs (e.g., `TabRun`, `TabSettings`, `TabLogs`, `TabHelp`, …).
  * Keep an ordered slice `m.tabs []string` to compute 1‑based shortcuts reliably.

* **Acceptance**

  * Adding/removing a tab updates `m.tabs` and helps autogenerate the right help content and number shortcuts.

---

### B2 — Unsaved indicator & quit confirmation

**Goal:** users don’t lose changes; simple feedback loop.

* **Where**

  * `internal/tui/model.go` (add `dirty bool`)
  * `internal/tui/view.go` (status line / title)
  * `internal/tui/keys.go` (quit action)
  * `internal/config/config.go` (compare/save helpers)

* **What to implement**

  * Mark `m.dirty = true` on any change to configuration‑backed fields.
  * Show `*` (or `[unsaved]`) in the title/status when `dirty`.
  * On Quit: if `dirty` ask **confirm** (`Save / Discard / Cancel`).
  * Implement `func (c Config) Equal(other Config) bool` (or a checksum) to detect changes robustly.

* **Acceptance**

  * Attempting to quit with unsaved changes asks for confirmation.
  * Saving clears the dirty flag and indicator.

---

## Epic C — Wiring TUI selections to the runner/script

### C1 — Single function to build runner args/env from config

**Goal:** guarantee every selectable option influences the script; easy to test.

* **Where**

  * `internal/runner/runner.go` (introduce `BuildArgs`)
  * `internal/config/config.go` (ensure all fields are present)
  * `internal/tui/run.go` (call site)

* **What to implement**

  * In `internal/runner/runner.go`:

    ```go
    type Args struct {
      Cmd  string
      Args []string
      Env  []string
    }
    func BuildArgs(cfg config.Config) (Args, error) {
      // map flags & env deterministically from cfg
    }
    func Run(cfg config.Config) error {
      a, err := BuildArgs(cfg); if err != nil { return err }
      // exec command with a.Args, a.Env
    }
    ```
  * Replace ad‑hoc arg construction in `internal/tui/run.go` with `BuildArgs`.

* **Acceptance**

  * Unit tests (see **F3**) cover every config field that is user-selectable in the TUI and assert the constructed CLI/env.

---

### C2 — Audit: TUI state → config.Config fields

**Goal:** nothing in the UI is “display‑only”.

* **Where**

  * `internal/tui/model.go` (state definitions)
  * Any per‑tab update code
  * `internal/config/config.go`

* **What to implement**

  * List all TUI controls (toggles, selects, text inputs). For each, ensure:

    1. There is a field in `config.Config` (or nested structs).
    2. The Update handler writes that field.
    3. On **Save** (Ctrl+S), `config.Save(cfg)` persists it.
  * If a control currently **has no config sink**, either:

    * add a `Config` field and wire it into `BuildArgs`, **or**
    * make it visual‑only and remove it from the TUI (to keep promises honest).

* **Acceptance**

  * A checklist of controls ↔ fields is maintained (commit as `docs/tui-to-config.md`).
  * No selectable control lacks a config mapping or explicit rationale.

---

### C3 — Save everywhere with **Ctrl+S**

**Goal:** one mental model; prevent inconsistent `s`/`ctrl+s` behavior.

* **Where**

  * `internal/tui/keys.go` (bind `ActSave` → `Ctrl+S`)
  * `internal/tui/model.go` (handle `ActSave` once)
  * `internal/config/config.go` (expose `Save(cfg)` and error surfacing)

* **What to implement**

  * Remove any plain “s” save handlers in tab‑local code; map all to `ActSave`.
  * On save: write to disk and flash a transient “[saved]” status message.

* **Acceptance**

  * Pressing **Ctrl+S** on any tab saves without changing tabs; help shows this.

---

## Epic D — Run & Logs UX

### D1 — Follow/Unfollow logs toggle and persistence

**Goal:** “follow logs” is predictable; same key everywhere.

* **Where**

  * `internal/tui/run.go` (log reader/follower)
  * `internal/tui/keys.go` (e.g., bind `ActToggleFollowLogs` → `f`)
  * tests: extend `internal/tui/run_feed_test.go`

* **What to implement**

  * Ensure there is a model bool `m.followLogs`.
  * Toggle with a single key; reflect in view (badge).
  * Persist preference to config if desirable (optional).

* **Acceptance**

  * Toggling works during a run and when idle; tested by feeding synthetic log lines in `run_feed_test.go`.

---

### D2 — Error surfacing from runner

**Goal:** runner failures are visible and actionable.

* **Where**

  * `internal/runner/runner.go` (return rich errors)
  * `internal/tui/run.go` (display errors)
  * `internal/tui/view.go` (inline error banner or modal)

* **What to implement**

  * Wrap errors with context (`fmt.Errorf("running step X: %w", err)`).
  * In TUI, display the last error with a “copy error” action and a retry key.

* **Acceptance**

  * Simulated failing command shows banner and provides retry.

---

## Epic E — Contextual help (always accurate)

### E1 — Autogenerate help from KeyMap

**Goal:** no stale help docs; focus on discoverability.

* **Where**

  * `internal/tui/view.go` (help renderer)
  * `internal/tui/keys.go` (labels)

* **What to implement**

  * Add friendly labels to each `Action` (e.g., `Label(ActSave) → "Save config"`).
  * Render a help box with **global** bindings and the **current tab** bindings.
  * Bind `?` to toggle help; also add `F1` as an alternative.

* **Acceptance**

  * Changing a key in `DefaultKeyMap()` changes the Help view automatically.

---

## Epic F — Tests & quality gates

### F1 — Keystroke guard tests

**Goal:** typing mode blocks globals; non‑typing mode allows them.

* **Where**

  * **Add:** `internal/tui/typing_guard_test.go` (**NEW**)

* **What to implement**

  * Spin up the Bubble Tea model, set `m.SetTyping(true)`, simulate `q` (quit), digit `1`, `?`, and assert they are **not** handled as globals.
  * Set `m.SetTyping(false)` and assert they **are** handled.

* **Acceptance**

  * Test fails if future changes reintroduce unwanted interception while typing.

---

### F2 — No overlap test across tabs (non‑nav single letters)

**Goal:** programmatically catch conflicting semantics.

* **Where**

  * `internal/tui/keymap_test.go` (from A4)

* **What to implement**

  * Build a per‑tab map; for single‑letter, no‑modifier keys, assert uniqueness of `Action`.

* **Acceptance**

  * Red test when overlap is introduced; green after resolution.

---

### F3 — End‑to‑end wiring: config → BuildArgs → runner

**Goal:** every selectable control influences the actual command.

* **Where**

  * `internal/runner/runner_test.go` (extend)
  * **Add:** `internal/runner/build_args_test.go` (**NEW**)

* **What to implement**

  * Table‑driven tests that:

    * Compose `config.Config` with permutations of toggles/fields.
    * Call `BuildArgs(cfg)` and assert `Args.Args` and `Args.Env` contain expected flags/env vars.
  * Add at least one test for a “dry‑run” or “phases”‑like flag if present in your config.

* **Acceptance**

  * Coverage for all user‑selectable config fields exposed in the TUI.

---

## Epic G — Small polish items that improve flow

### G1 — Status line & transient toasts

**Goal:** real‑time feedback for actions (saved, error, run started).

* **Where**

  * `internal/tui/model.go` (message queue or timer)
  * `internal/tui/view.go` (status line rendering)

* **What to implement**

  * Simple `m.flash(msg string, ttl time.Duration)` to show messages.
  * Use for Save/Run started/Completed.

* **Acceptance**

  * Users see immediate confirmation after actions; disappears automatically.

---

### G2 — Reset keys and defaults

**Goal:** easy to restore sane defaults.

* **Where**

  * `internal/tui/keys.go` (bind e.g., `ActResetDefaults` → `Ctrl+Backspace`)
  * `internal/tui/model.go` (apply default config)

* **What to implement**

  * Keep a copy of default `config.Config`. The action replaces current values and marks `dirty = true`.

* **Acceptance**

  * Pressing the reset key returns the form to defaults and marks unsaved changes.

---

## Concrete change notes per file

* **`internal/tui/model.go`**

  * Add: `keys KeyMap`, `typing bool`, `dirty bool`, optionally a `status Toast`.
  * Provide helpers: `IsTyping()`, `SetTyping(bool)`, `MarkDirty()`.
  * Centralize `Update` dispatch to use `keys` lookups.

* **`internal/tui/update_tabs.go`**

  * Route `ActNextTab`, `ActPrevTab`, `ActGotoTabX`; guard with `!m.IsTyping()`.
  * Keep ordered `m.tabs` and constants for tab IDs.

* **`internal/tui/view.go`**

  * Render status/unsaved indicator.
  * Add help box that reads from `m.keys` (global + current tab).

* **`internal/tui/run.go`**

  * Replace bespoke arg building with `runner.BuildArgs(cfg)`.
  * Keep `m.followLogs` state and `ActToggleFollowLogs` handling.
  * Surface runner errors with context to the view.

* **`internal/runner/runner.go`**

  * Add `Args` struct, `BuildArgs(cfg)`, refactor `Run(cfg)` to use it.
  * Make missing‑config cases explicit errors (caught by TUI).

* **`internal/config/config.go`**

  * Ensure a `Save(cfg)` and (optionally) `Load()` exist and bubble up errors.
  * Implement `Equal` or checksum for quit‑with‑unsaved detection.

* **Tests**

  * `internal/tui/run_feed_test.go`: extend with follow/unfollow toggle and visual states.
  * `internal/tui/log_reader_test.go`: keep as is; add a failure case if helpful.
  * **NEW:** `internal/tui/typing_guard_test.go`, `internal/tui/keymap_test.go`.
  * `internal/runner/runner_test.go` & **NEW** `internal/runner/build_args_test.go`: cover arg/env mapping exhaustively.

---

## Rollout checklist (sequenced)

1. **A1/A2**: Introduce `KeyMap`, add typing guard, move existing bindings into `keys`.
2. **A3/A4/A5**: Fix tab navigation, add overlap test, unify form navigation.
3. **B1/B2**: Tab IDs, unsaved indicator & quit confirmation.
4. **C1/C2/C3**: Central `BuildArgs`, full TUI→config audit, **Ctrl+S** everywhere.
5. **D1/D2**: Follow logs & error surfacing polish.
6. **E1**: Autogenerated help from `KeyMap`.
7. **F‑series tests**: land guard, overlap, build‑args coverage.
8. **G‑series polish**: status toasts, reset defaults.

---

## Definition of Done (practical)

* Pressing **Ctrl+S** on any tab saves; pressing `q` with unsaved changes prompts.
* Digits, `q`, `?` typed in inputs **don’t** trigger global actions.
* Each visible control in the TUI changes a value in `config.Config`; tests prove that value **changes CLI args/env** via `BuildArgs`.
* A unit test fails if a **single‑letter** key is mapped to **different actions** across tabs (ignoring navigation keys).
* Help screen shows **exact** bindings, pulled from `KeyMap`.
