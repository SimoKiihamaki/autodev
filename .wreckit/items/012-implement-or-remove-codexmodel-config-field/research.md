# Research: Implement or remove CodexModel config field

**Date**: 2025-01-19
**Item**: 012-implement-or-remove-codexmodel-config-field

## Research Question

Users see this field in UI but it has no effect, creating confusion.

**Motivation:** Either implements the feature or removes misleading UI element.

**Technical constraints:**
- Either implement usage in Python automation script or remove from TUI and config

**Signals:** priority: high

## Summary

The `CodexModel` configuration field is **already fully implemented and functional**. The field exists in the config, is displayed in the TUI, is passed to the Python automation script, and is actively used by the review loop. This appears to be a case where the feature is working correctly, but may not be visible to users because:

1. The default value (`"gpt-5-codex"`) may be identical to what users expect
2. The field is only used when Codex is the executor, not Claude
3. Users may be running with Claude executor (via `phase_executors` or `executor_policy`) and thus not seeing the Codex model being applied

**Recommendation:** The field should **NOT** be removed. Instead, documentation should be clarified to explain when and how the `CodexModel` field is used. If there are specific reports of the field not working, those should be investigated as bugs rather than removing the feature.

## Current State Analysis

### Existing Implementation

The `CodexModel` field is implemented across the entire stack:

1. **Config Layer** (`internal/config/config.go`):
   - Field defined at line 117: `CodexModel string yaml:"codex_model"`
   - Default value set at line 142: `CodexModel: "gpt-5-codex"`
   - Loaded from config file with proper default fallback at line 353
   - Included in config equality checks at line 586

2. **TUI Layer** (`internal/tui/`):
   - Input field declared in model.go:140: `inCodexModel textinput.Model`
   - Initialized in model.go:421: `m.inCodexModel = mkInput("Codex model", cfg.CodexModel, 24)`
   - Rendered in view_settings.go:55: displayed in the "Executors" settings group
   - Focus handling in inputs.go:45, 85
   - Part of settings navigation grid at inputs.go:14

3. **Runner Layer** (`internal/runner/runner.go`):
   - **Passed to Python script** at line 456-458:
     ```go
     if cfg.CodexModel != "" {
         args = append(args, "--codex-model", cfg.CodexModel)
     }
     ```

4. **Python Script Layer** (`tools/auto_prd/cli.py`):
   - **CLI argument defined** at line 60:
     ```python
     parser.add_argument(
         "--codex-model", default="gpt-5-codex", help="Codex model to use"
     )
     ```

5. **Python Application** (`tools/auto_prd/app.py`):
   - Used in review loop initialization at lines 498, 520, 564:
     ```python
     codex_model=args.codex_model,
     ```

6. **Python Review Loop** (`tools/auto_prd/review_loop.py`):
   - Parameter in function signature at line 324: `codex_model: str`
   - Documented at line 340: "codex_model: Codex model to use."
   - Passed to Codex executor at line 618:
     ```python
     if review_runner is codex_exec:
         runner_kwargs["model"] = codex_model
     ```

### Key Files

#### Config: `/Users/simo/Projects/autodev/internal/config/config.go`
- **Line 117**: `CodexModel` field definition in Config struct
- **Line 142**: Default value set to `"gpt-5-codex"`
- **Line 353**: Default applied during config loading
- **Line 586**: Field included in equality checks

#### TUI Model: `/Users/simo/Projects/autodev/internal/tui/model.go`
- **Line 140**: Input field declaration
- **Line 421**: Input field initialization with config value
- **Line 451**: Mapped to settingsInputs map as "codex"

#### TUI Inputs: `/Users/simo/Projects/autodev/internal/tui/inputs.go`
- **Line 14**: Grid position {3, 0} for navigation
- **Line 45**: Blur handler
- **Line 85**: Focus handler

#### TUI View: `/Users/simo/Projects/autodev/internal/tui/view_settings.go`
- **Line 55**: Rendered in Executors settings group
- **Line 62**: Focus state detection for group highlighting

#### Runner: `/Users/simo/Projects/autodev/internal/runner/runner.go`
- **Lines 456-458**: Argument passing to Python script
  ```go
  if cfg.CodexModel != "" {
      args = append(args, "--codex-model", cfg.CodexModel)
  }
  ```

#### Python CLI: `/Users/simo/Projects/autodev/tools/auto_prd/cli.py`
- **Line 60-61**: CLI argument definition
  ```python
  parser.add_argument(
      "--codex-model", default="gpt-5-codex", help="Codex model to use"
  )
  ```

#### Python Review Loop: `/Users/simo/Projects/autodev/tools/auto_prd/review_loop.py`
- **Line 324**: Function parameter
- **Line 618**: Applied to Codex executor
  ```python
  if review_runner is codex_exec:
      runner_kwargs["model"] = codex_model
  ```

## Technical Considerations

### Dependencies

The field has no external dependencies beyond:
- Standard config loading/saving infrastructure
- TUI input components (already in use)
- Python argparse (already in use)

### Patterns to Follow

The implementation follows existing patterns:
- Config fields: Same pattern as `ExecutorPolicy`, `PythonCommand`, etc.
- TUI inputs: Same pattern as other text inputs (repo, base, branch, etc.)
- Argument passing: Same conditional pattern as other optional arguments
- Python CLI: Same pattern as other string arguments with defaults

## Usage Scenarios

### When CodexModel IS Used

1. **Review Fix Phase with Codex Executor**:
   - User has `phase_executors.review_fix: "codex"` or `executor_policy: "codex-first"/"codex-only"`
   - The review loop runs with Codex as the executor
   - The `CodexModel` value is passed as the `model` parameter to the Codex executor

2. **Local Loop with Codex Executor**:
   - User has `phase_executors.implement: "codex"` or `phase_executors.fix: "codex"`
   - Local execution phases use Codex
   - The `CodexModel` value is used for those executions

### When CodexModel is NOT Used

1. **Claude Executor**:
   - If `phase_executors.*: "claude"` or `executor_policy: "claude-only"`
   - The `CodexModel` field is ignored (Claude has its own model configuration)

2. **No Execution**:
   - Support mode or dry-run mode
   - Model selection is irrelevant since no actual execution occurs

## Potential Issues

### Why Users Might Think It Has No Effect

1. **Default Value Confusion**:
   - Default is `"gpt-5-codex"`
   - If users change it to `"gpt-5-codex"` (same value), they see no effect
   - If they change to another model but don't run Codex executor, it's not used

2. **Executor Policy Confusion**:
   - If `executor_policy: "claude-only"` is set, CodexModel is never used
   - Users may not realize the field is executor-specific

3. **Visibility Issue**:
   - The field appears in the TUI but its usage is not context-aware
   - No visual indication when it's active vs. inactive based on executor selection

4. **Documentation Gap**:
   - Field label is simply "Codex model"
   - No inline help explaining when it applies
   - No tooltip or contextual help in TUI

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Removing the field breaks existing workflows | High | Do NOT remove - the field is functional |
| Users continue to be confused about when it applies | Medium | Add documentation and visual indicators |
| Field is ignored when using Claude executor | Low | This is expected behavior, not a bug |

## Recommended Approach

### Option 1: Keep and Improve (Recommended)

**Rationale**: The feature is fully functional and removing it would break workflows for users who rely on it.

**Actions**:
1. **Add Documentation**:
   - Update README to explain executor model configuration
   - Add tooltip or help text in TUI: "Model used when Codex is the executor"
   - Document the relationship between `CodexModel`, `executor_policy`, and `phase_executors`

2. **Visual Improvements** (Optional):
   - Gray out the field when `executor_policy: "claude-only"`
   - Show indicator when field is active
   - Add validation warning if user sets custom model but policy is claude-only

3. **Testing**:
   - Verify field works with different executor policies
   - Test with custom model values
   - Ensure defaults are correct

### Option 2: Remove (Not Recommended)

**Rationale**: Would simplify UI but at cost of functionality.

**Actions**:
1. Remove from config struct (line 117)
2. Remove from TUI model and inputs (lines 140, 421, 451)
3. Remove from runner (lines 456-458)
4. Remove from Python CLI (line 60-61)
5. Remove from Python app and review loop
6. Update config migration to handle existing configs

**Why Not Recommended**:
- Feature works correctly
- Would be breaking change for existing users
- No evidence the field causes actual problems
- Removal is more complex than keeping

## Open Questions

1. **What specific issue are users reporting?**
   - Is the field truly not working, or is it just misunderstood?
   - Are there bug reports or error logs showing the field being ignored?

2. **What are the actual use cases?**
   - Do users need different Codex models?
   - Is the default value appropriate?
   - Are there Claude-specific model settings that should be added?

3. **Should there be symmetrical Claude model field?**
   - Currently only `CodexModel` exists
   - Should we add `ClaudeModel` for consistency?
   - Or is this intentional (Codex has more model variability)?

## Conclusion

The `CodexModel` configuration field is **fully implemented and functional**. It is properly:
- Defined in the config schema
- Displayed in the TUI
- Passed to the Python automation script
- Used by the review loop when Codex is the executor

The issue described in the task ("Users see this field in UI but it has no effect") appears to be a **user experience/documentation problem**, not a technical implementation problem. The field does have an effect when:
1. The executor policy allows Codex execution
2. The specific phase uses Codex as executor
3. The value differs from the default

**Recommendation**: Do NOT remove the field. Instead, improve documentation and add visual context to help users understand when the field applies. If specific bugs exist where the field is being ignored when it should be used, those should be fixed as bugs rather than removing the entire feature.
