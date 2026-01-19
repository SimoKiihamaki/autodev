# Implement or remove CodexModel config field Implementation Plan

## Overview

This task addresses a reported issue where the `CodexModel` configuration field appears in the UI but "has no effect," creating user confusion. After thorough investigation, **the field is already fully implemented and functional** across the entire stack (config → TUI → Python CLI → Python application → review loop).

The root cause is not a missing implementation, but rather a **documentation and user experience gap**:
- Users may not understand that the field only applies when Codex is the active executor
- The field has no visual indication of when it's active vs. inactive
- No inline help explains its relationship to executor policy
- The default value (`"gpt-5-codex"`) may mask its effect if users don't change it meaningfully

**Decision**: Keep the field (it's functional) and improve its discoverability/UX through documentation and visual enhancements.

## Current State Analysis

### Existing Implementation (Fully Functional)

The `CodexModel` field is implemented end-to-end:

1. **Config Layer** (`internal/config/config.go:117`):
   - Field defined: `CodexModel string yaml:"codex_model"`
   - Default value: `"gpt-5-codex"` (line 142)
   - Loaded with proper default fallback (line 353)
   - Included in config equality checks (line 586)

2. **TUI Layer** (`internal/tui/`):
   - Input field declared in `model.go:140`: `inCodexModel textinput.Model`
   - Initialized in `model.go:421`: `m.inCodexModel = mkInput("Codex model", cfg.CodexModel, 24)`
   - Rendered in `view_settings.go:55`: displayed in "Executors" settings group
   - Focus handling in `inputs.go:45, 85`
   - Mapped to settingsInputs map at `inputs.go:14` as "codex"

3. **Runner Layer** (`internal/runner/runner.go:456-458`):
   ```go
   if cfg.CodexModel != "" {
       args = append(args, "--codex-model", cfg.CodexModel)
   }
   ```

4. **Python CLI Layer** (`tools/auto_prd/cli.py:60-61`):
   ```python
   parser.add_argument(
       "--codex-model", default="gpt-5-codex", help="Codex model to use"
   )
   ```

5. **Python Application** (`tools/auto_prd/app.py:498, 520, 564`):
   - Passed to review loop: `codex_model=args.codex_model`

6. **Python Review Loop** (`tools/auto_prd/review_loop.py`):
   - Parameter in function signature (line 324): `codex_model: str`
   - Documented (line 340): "codex_model: Codex model to use."
   - **Applied to Codex executor** (lines 617-618):
     ```python
     if review_runner is codex_exec:
         runner_kwargs["model"] = codex_model
     ```

### When CodexModel IS Used

The field is actively used when:
1. Executor policy allows Codex (`executor_policy: "codex-first"` or `"codex-only"`)
2. Specific phase uses Codex (`phase_executors.review_fix: "codex"`)
3. The value differs from default (or user wants to explicitly set it)

### When CodexModel is NOT Used

The field is correctly ignored when:
1. Executor policy is `"claude-only"` (Codex never runs)
2. Specific phase uses Claude executor
3. No execution occurs (support mode, dry-run)

### Why Users Think It Has No Effect

1. **Default Value Confusion**: Default is `"gpt-5-codex"` - changing it to the same value shows no effect
2. **Executor Policy Confusion**: If `executor_policy: "claude-only"`, the field never applies
3. **No Visual Context**: Field appears active even when it will be ignored
4. **Documentation Gap**: No explanation of when/why it applies

## Desired End State

Users should understand:
1. **When** the `CodexModel` field applies (only when Codex is the executor)
2. **How** to verify it's being used (check executor policy/phase executors)
3. **What** values are valid (model names supported by Codex CLI)
4. **Why** it might appear to have no effect (executor policy)

### Key Discoveries:
- **Finding**: Field is fully functional - removing it would break existing workflows
- **Pattern**: Follows same pattern as other config fields (ExecutorPolicy, PythonCommand, etc.)
- **Constraint**: Must not break backward compatibility for existing configs
- **File**: `internal/config/config.go:117` - config field definition
- **File**: `internal/tui/model.go:421` - TUI input initialization
- **File**: `internal/runner/runner.go:456-458` - argument passing to Python
- **File**: `tools/auto_prd/review_loop.py:617-618` - actual usage in review loop

## What We're NOT Doing

- **NOT removing the field** - it's functional and used by existing workflows
- **NOT changing the config schema** - backward compatibility is critical
- **NOT modifying the Python automation script** - it correctly uses the parameter
- **NOT adding validation for model names** - Codex CLI handles this
- **NOT implementing a symmetrical `ClaudeModel` field** - out of scope (can be separate task)

## Implementation Approach

**High-level strategy**: Keep the functional implementation and improve UX/documentation to make its usage clear.

**Approach Rationale**:
1. **Minimal risk**: No breaking changes to config or Python script
2. **Incremental improvements**: Each change can be tested independently
3. **Follows existing patterns**: Documentation, TUI styling, validation
4. **Addresses root cause**: User confusion, not technical implementation

**Alternatives Considered**:
- **Remove the field**: Rejected - would break workflows, feature works correctly
- **Add ClaudeModel field**: Rejected - out of scope, separate concern
- **Complex conditional logic**: Rejected - adds maintenance burden, current behavior is correct

---

## Phase 1: Update README Documentation

### Overview
Add clear documentation explaining when and how the `CodexModel` field is used, including its relationship to executor policy and phase executors.

### Changes Required:

#### 1. README.md
**File**: `/Users/simo/Projects/autodev/README.md`
**Changes**: Add new section explaining executor model configuration

Add after "Per-phase executors" section (around line 64):

```markdown
### Executor Models

In **Settings**, configure the model used for each executor type:

- **Codex model**: Model used when Codex is the executor (e.g., `gpt-5-codex`, `gpt-4-codex`)
  - Only applies when `Executor policy` is set to `codex-first` or `codex-only`
  - Can be overridden per-phase using phase executors (e.g., `Exec (review_fix): claude`)
  - If using `claude-only` policy, this field is ignored

**Note**: Model configuration is executor-specific. If you're using Claude as the executor, the Codex model setting will not apply.
```

### Success Criteria:

#### Automated Verification:
- [ ] Documentation is clear and accurate
- [ ] No breaking changes to existing content

#### Manual Verification:
- [ ] Documentation accurately describes the field's behavior
- [ ] Examples are clear and actionable
- [ ] Relationship to executor policy is explained
- [ ] Users understand when the field applies

**Note**: Complete documentation update, then proceed to Phase 2.

---

## Phase 2: Improve TUI Field Label

### Overview
Update the TUI input field label to be more descriptive and provide context about when it applies.

### Changes Required:

#### 1. internal/tui/model.go
**File**: `/Users/simo/Projects/autodev/internal/tui/model.go`
**Changes**: Update the label for CodexModel input

```go
// Line 421 - Update the label
m.inCodexModel = mkInput("Codex model (when Codex executor)", cfg.CodexModel, 24)
```

### Success Criteria:

#### Automated Verification:
- [ ] Build succeeds: `make build`
- [ ] No TypeScript/Go compilation errors

#### Manual Verification:
- [ ] TUI displays with new label
- [ ] Label is clear and provides context
- [ ] Label fits within the TUI layout (no overflow)
- [ ] Field is still editable and functional

**Note**: Complete label update, test TUI rendering, then proceed to Phase 3.

---

## Phase 3: Add Visual Context (Optional Enhancement)

### Overview
Add visual indication when the CodexModel field is inactive due to executor policy setting. This helps users understand why their setting might not have an effect.

### Changes Required:

#### 1. internal/tui/model.go
**File**: `/Users/simo/Projects/autodev/internal/tui/model.go`
**Changes**: Add helper to determine if CodexModel should be visually disabled

Add new helper function after `initSettingsInputs()`:

```go
// isCodexModelDisabled returns true if CodexModel field is effectively disabled
// based on executor policy settings.
func (m *model) isCodexModelDisabled() bool {
    policy := m.inPolicy.Value()
    return policy == "claude-only"
}
```

#### 2. internal/tui/view_settings.go
**File**: `/Users/simo/Projects/autodev/internal/tui/view_settings.go`
**Changes**: Apply dimmed styling when CodexModel is disabled

Update the rendering (around line 54-60):

```go
// Dim the CodexModel field if it's disabled by policy
codexModelView := m.inCodexModel.View()
if m.isCodexModelDisabled() {
    codexModelView = lipgloss.NewStyle().
        Foreground(lipgloss.Color("241")). // Dimmed gray
        Render(codexModelView)
}

execContent := lipgloss.JoinVertical(lipgloss.Left,
    codexModelView,
    m.inPyCmd.View(),
    m.inPyScript.View(),
    m.inPolicy.View(),
    togglesLine,
)
```

### Success Criteria:

#### Automated Verification:
- [ ] Build succeeds: `make build`
- [ ] No Go compilation errors

#### Manual Verification:
- [ ] When `executor_policy: "claude-only"`, CodexModel field appears dimmed
- [ ] When `executor_policy: "codex-first"` or `"codex-only"`, field appears normal
- [ ] Field remains visible and readable in all states
- [ ] Visual change helps users understand when field applies

**Note**: This is an optional enhancement. Test thoroughly to ensure visual clarity.

---

## Phase 4: Add Validation/Warning (Optional Enhancement)

### Overview
Add a subtle warning when users set a custom CodexModel but the executor policy is "claude-only", helping them understand the setting won't have an effect.

### Changes Required:

#### 1. internal/tui/model.go
**File**: `/Users/simo/Projects/autodev/internal/tui/model.go`
**Changes**: Add status message helper for CodexModel warning

Add helper function:

```go
// getCodexModelWarning returns a warning message if CodexModel is set but won't be used
func (m *model) getCodexModelWarning() string {
    if m.isCodexModelDisabled() && m.inCodexModel.Value() != "gpt-5-codex" {
        return "⚠ Codex model set but executor policy is claude-only"
    }
    return ""
}
```

#### 2. internal/tui/model.go (Update method that generates status messages)
**File**: `/Users/simo/Projects/autodev/internal/tui/model.go`
**Changes**: Include warning in status bar or settings view

This would integrate with existing status message display logic.

### Success Criteria:

#### Automated Verification:
- [ ] Build succeeds: `make build`
- [ ] No Go compilation errors

#### Manual Verification:
- [ ] Warning appears when CodexModel is non-default and policy is "claude-only"
- [ ] Warning is clear and non-intrusive
- [ ] Warning disappears when policy changes to allow Codex
- [ ] No false positives (warning only when appropriate)

**Note**: This is an optional enhancement. Carefully consider if it adds value or clutter.

---

## Testing Strategy

### Unit Tests:
No unit tests required - changes are primarily documentation and cosmetic.

### Integration Tests:
No integration tests required - no logic changes to core functionality.

### Manual Testing Steps:

#### Test 1: Verify Field Functionality
1. Start TUI: `./bin/aprd`
2. Go to Settings
3. Change "Codex model" to a different value (e.g., "gpt-4-codex")
4. Set executor policy to "codex-only"
5. Run a PRD with review_fix phase
6. Verify in logs that the model is passed to Python: `--codex-model gpt-4-codex`

#### Test 2: Verify Documentation
1. Read README.md "Executor Models" section
2. Confirm it clearly explains when CodexModel applies
3. Confirm relationship to executor policy is clear

#### Test 3: Verify TUI Label (Phase 2)
1. Start TUI: `./bin/aprd`
2. Go to Settings
3. Confirm the label reads "Codex model (when Codex executor)"
4. Confirm label fits without overflow

#### Test 4: Verify Visual Context (Phase 3 - Optional)
1. Start TUI: `./bin/aprd`
2. Go to Settings
3. Set executor policy to "claude-only"
4. Confirm CodexModel field appears dimmed
5. Change executor policy to "codex-first"
6. Confirm CodexModel field appears normal

#### Test 5: Verify Validation Warning (Phase 4 - Optional)
1. Start TUI: `./bin/aprd`
2. Go to Settings
3. Set CodexModel to non-default value
4. Set executor policy to "claude-only"
5. Confirm warning appears
6. Change executor policy to "codex-first"
7. Confirm warning disappears

## Migration Notes

**No migration required** - all changes are backward compatible:
- Documentation changes are additive
- TUI label changes are cosmetic
- Visual enhancements are non-breaking
- Existing configs continue to work unchanged

## Rollback Strategy

Each phase can be independently rolled back:
- **Phase 1**: Revert README.md changes
- **Phase 2**: Revert label change in `model.go:421`
- **Phase 3**: Remove `isCodexModelDisabled()` helper and styling in `view_settings.go`
- **Phase 4**: Remove `getCodexModelWarning()` helper and integration

## References

- Research: `/Users/simo/Projects/autodev/.wreckit/items/012-implement-or-remove-codexmodel-config-field/research.md`
- Config: `/Users/simo/Projects/autodev/internal/config/config.go` (lines 117, 142, 353, 586)
- TUI Model: `/Users/simo/Projects/autodev/internal/tui/model.go` (lines 140, 421)
- TUI Inputs: `/Users/simo/Projects/autodev/internal/tui/inputs.go` (line 14)
- TUI View: `/Users/simo/Projects/autodev/internal/tui/view_settings.go` (line 55)
- Runner: `/Users/simo/Projects/autodev/internal/runner/runner.go` (lines 456-458)
- Python CLI: `/Users/simo/Projects/autodev/tools/auto_prd/cli.py` (lines 60-61)
- Python Review Loop: `/Users/simo/Projects/autodev/tools/auto_prd/review_loop.py` (lines 324, 340, 617-618)
- README: `/Users/simo/Projects/autodev/README.md`
