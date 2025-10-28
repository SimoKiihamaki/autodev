# Settings Tab Fix Implementation Guide

## Scope
- Restore basic arrow-key navigation inside the Settings tab without requiring modifier keys.
- Replace the four free-form executor text inputs with three binary toggles that flip between Codex and Claude for the Local loop, PR push, and PR review-fix phases.
- Keep configuration loading/saving and downstream runner behaviour aligned with the new toggles.

## Step-by-step Tasks

1. **Reshape the model to track executor toggles**
   - Files: `internal/tui/model.go`, `internal/tui/run.go`
   - Remove `inExecImpl`, `inExecFix`, `inExecPR`, `inExecRev` `textinput.Model` fields from the `model` struct.
   - Introduce a small enum (e.g. `type executorChoice string`) with constants for `codex` and `claude`, plus struct fields such as `execLocalChoice`, `execPRChoice`, and `execReviewChoice`.
   - During `New()`, derive the toggle defaults from `cfg.PhaseExecutors`, defaulting to Codex when the YAML fields are empty or unrecognised. Store both Implement and Fix under the Local toggle.
   - Update `settingsInputNames` to drop the executor entries so it only lists real `textinput` controls. Keep a separate slice (e.g. `executorToggleOrder`) if you need deterministic iteration for toggles.
   - Remove executor entries from `m.settingsInputs` and ensure `getInputField` returns `nil` for the toggle identifiers.

2. **Rebuild the settings navigation grid**
   - File: `internal/tui/inputs.go`
   - Replace the `settingsGrid` entries for `execimpl`, `execfix`, `execpr`, and `execrev` with three new keys (for example `toggleLocal`, `togglePR`, `toggleReview`). Keep them on the same visual row, using columns 0–2.
   - Update `blurAllInputs()` to stop trying to blur the removed executor inputs.
   - Extend `focusInput` with `case` branches for the three toggle keys so they simply set `m.focusedInput` without touching `textinput` state.
   - Add a helper like `cycleExecutorChoice(name string, direction int)` that flips between Codex and Claude and keep `navigateSettings` unchanged—its grid math works as long as the toggle names are present in `settingsGrid`.

3. **Handle arrow keys and toggle activation**
   - File: `internal/tui/update_tabs.go`
   - For `case "up"`, `case "down"`, `case "left"`, and `case "right"`, call `m.navigateSettings(...)` when `m.focusedInput` is non-empty so plain arrows move the focus; keep the existing Alt bindings as aliases.
   - Before delegating to the focused `textinput`, intercept `left`, `right`, `enter`, and optionally `space` when the focus is on one of the toggle IDs and call `cycleExecutorChoice` instead of `field.Update`.
   - Ensure `tab` navigation still works: when focused on a toggle, `tab` should fall through to `navigateSettings("down")`.

4. **Render the toggles and refresh help copy**
   - File: `internal/tui/view.go`
   - Replace the executor text-input row with a helper (e.g. `renderExecutorToggle(label, choice, focused bool)`) that prints something like `Local Loop: [Codex] Claude` and flips the highlight style based on the selection.
   - Highlight the focused toggle when `m.focusedInput` matches its key to preserve visual focus cues.
   - Update the instructional copy in both the Settings tab footer and the Help tab (`renderHelpView`) to mention plain arrow keys and the new toggle behaviour (e.g. “←/→ or Enter to toggle Codex/Claude”).

5. **Persist the toggle selections**
   - File: `internal/tui/run.go`
   - In `hydrateConfigFromInputs()`, set `cfg.PhaseExecutors.Implement` **and** `cfg.PhaseExecutors.Fix` from the Local toggle, and set `cfg.PhaseExecutors.PR` / `cfg.PhaseExecutors.ReviewFix` from their respective toggles before saving.
   - Remove any references to the removed executor text inputs and keep all other numeric parsing logic intact.

6. **Refresh tests and add coverage**
   - File: `internal/tui/model_test.go`
   - Update `TestSettingsInputNamesAreSynchronized` to use the reduced `settingsInputNames` slice.
   - Add a new test (e.g. `TestExecutorToggleDefaults`) that constructs a model with different `PhaseExecutors` values and asserts the `exec*Choice` fields resolve correctly (empty → codex, `CLAUDE` → claude).
   - Consider a focused test for `cycleExecutorChoice` to ensure arrow keys and wrapping logic stay predictable.

7. **Documentation and QA**
   - File: `NAVIGATION_GUIDE.md` (Settings section)
     - Revise the guidance so it mirrors the new arrow key behaviour and toggle description.
   - Manual verification:
     1. `go test ./...`
     2. `go run ./cmd/aprd` (or `make run`) and confirm arrow navigation works without Alt and that each toggle flips between Codex and Claude while updating the saved config.
   - Run `go fmt ./...` (or `make build`) before committing to satisfy formatting expectations.

