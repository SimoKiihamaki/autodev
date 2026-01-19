# Implement or remove mouse event handler Implementation Plan

## Overview
Remove the unused mouse event handler case from the TUI's Update function. The handler is a no-op stub that serves no functional purpose, as mouse events are not enabled in the Bubble Tea program initialization. This cleanup eliminates dead code and removes potential confusion about mouse support.

## Current State Analysis

### What Exists Now
- **File**: `/Users/simo/Projects/autodev/internal/tui/update.go:29-30`
- **Code**: A `case tea.MouseMsg:` that immediately returns `m, nil` without any processing
- **Context**: The Update function uses a type switch pattern to handle different Bubble Tea message types
- **Mouse Status**: Mouse events are NOT enabled in the program (missing `tea.WithMouseCell()` option in `main.go`)

### What's Missing
- No mouse event handling functionality (by design - keyboard-first TUI)
- No mouse interaction design or requirements
- No user demand for mouse support (issue filed internally)

### Key Constraints Discovered
1. **Keyboard-First Architecture**: The application has 40+ keyboard actions defined in `/Users/simo/Projects/autodev/internal/tui/keys.go`
2. **Comprehensive Keybindings**: All 8 tabs are accessible via number keys (1-8), with extensive navigation shortcuts
3. **No Mouse Dependencies**: Zero code references to mouse events outside of the stub handler
4. **No Test Impact**: Only one test calls `Update()` and it tests `toastExpiredMsg`, not mouse messages

### Pattern Analysis
The Update function follows this pattern:
```go
func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch typed := msg.(type) {
	case tea.WindowSizeMsg:
		return m.handleResize(typed), nil
	case tea.KeyMsg:
		return m.handleKeyMsg(typed)
	case tea.MouseMsg:  // ← THIS IS THE PROBLEM
		return m, nil
	// ... other message types
	}
}
```

Each message type has a dedicated case with either:
- Inline handling (e.g., `toastExpiredMsg`)
- Handler function (e.g., `handleResize()`, `handleKeyMsg()`)

The mouse case does neither - it's just a no-op stub.

## Desired End State

### Specification
Remove the mouse event handler case from the Update function, eliminating dead code and clarifying that the application is keyboard-only.

### Verification
1. **Code Change**: Lines 29-30 removed from `update.go`
2. **Tests Pass**: All existing tests continue to pass (no test explicitly tests mouse handling)
3. **Build Succeeds**: Application builds and runs without issues
4. **No Behavioral Change**: Application functions identically (mouse was never enabled)

### Key Discoveries
- **File**: `/Users/simo/Projects/autodev/internal/tui/update.go:29-30`
  - The exact lines to remove: `case tea.MouseMsg:` and `return m, nil`
- **Pattern**: Other message types follow consistent pattern; this is the only no-op case
- **Constraint**: Mouse events not enabled in `/Users/simo/Projects/autodev/cmd/aprd/main.go:13`
  - Only `tea.WithAltScreen()` is present; no `tea.WithMouseCell()` or similar
- **Dependency**: None. This is isolated dead code with no callers or dependencies.

## What We're NOT Doing
- ❌ NOT implementing mouse support (would require feature design and user requirements)
- ❌ NOT enabling mouse events in the program (no `tea.WithMouseCell()` addition)
- ❌ NOT adding mouse-related help text or documentation (keyboard-only design maintained)
- ❌ NOT changing any other part of the Update function
- ❌ NOT modifying the keyboard-driven UI architecture

## Implementation Approach

### High-Level Strategy
**Single-line removal**: Delete the two lines comprising the mouse event handler case. This is the simplest possible implementation - pure code removal with no additions or modifications.

### Rationale
1. **Zero Functional Impact**: Mouse events aren't enabled, so removing the handler changes nothing
2. **Zero Risk**: The code does nothing; removing it cannot break anything
3. **Maintains Clarity**: Removing dead code signals that mouse support is not planned
4. **Follows YAGNI**: If mouse support is needed in the future, it should be properly designed as a feature, not added as a stub

---

## Phase 1: Remove Mouse Event Handler

### Overview
Delete the unused mouse event handler case from the Update function.

### Changes Required

#### 1. Update Function
**File**: `/Users/simo/Projects/autodev/internal/tui/update.go`
**Changes**: Remove lines 29-30 (the mouse event case)

**Current code:**
```go
func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch typed := msg.(type) {
	case tea.WindowSizeMsg:
		return m.handleResize(typed), nil

	case toastExpiredMsg:
		if m.toast != nil && m.toast.id == typed.id {
			m.toast = nil
		}
		return m, nil

	case tea.KeyMsg:
		return m.handleKeyMsg(typed)

	case tea.MouseMsg:
		return m, nil

	case prdScanMsg:
		m.prdList.SetItems(typed.items)
		// ... rest of function
```

**After change:**
```go
func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch typed := msg.(type) {
	case tea.WindowSizeMsg:
		return m.handleResize(typed), nil

	case toastExpiredMsg:
		if m.toast != nil && m.toast.id == typed.id {
			m.toast = nil
		}
		return m, nil

	case tea.KeyMsg:
		return m.handleKeyMsg(typed)

	case prdScanMsg:
		m.prdList.SetItems(typed.items)
		// ... rest of function
```

**Specific removal:**
- Line 29: `case tea.MouseMsg:`
- Line 30: `return m, nil`

### Success Criteria

#### Automated Verification:
- [ ] Tests pass: `go test ./internal/tui/...`
- [ ] Type checking passes: `go build ./cmd/aprd`
- [ ] Linting passes: `golangci-lint run` (if configured)
- [ ] Build succeeds: `go build -o bin/aprd ./cmd/aprd`

#### Manual Verification:
- [ ] Application starts without errors
- [ ] All keyboard shortcuts work normally
- [ ] Tab switching functions correctly (1-8 keys)
- [ ] Navigation in all tabs works as expected
- [ ] No warnings or errors related to mouse events

**Note**: Complete all automated verification, then verify manually. Since this is pure code removal with no functional changes, manual testing is minimal but confirms no regressions.

---

## Testing Strategy

### Unit Tests
- **No new tests required**: The change is pure code removal
- **Existing tests pass**: One test calls `Update()` with `toastExpiredMsg` (not mouse), so unaffected
- **Test file**: `/Users/simo/Projects/autodev/internal/tui/model_test.go:205`

### Integration Tests
- **No changes needed**: Application behavior is identical
- **Existing tests**: Run full test suite to ensure no regressions

### Manual Testing Steps
1. **Build the application**: `go build ./cmd/aprd`
2. **Start the TUI**: `./aprd`
3. **Verify keyboard navigation**:
   - Press keys 1-8 to switch tabs
   - Use arrow keys to navigate lists
   - Use Tab/Shift+Tab to cycle through fields
   - Test all keyboard shortcuts in Help tab
4. **Verify no errors**: Check for any warnings or error messages
5. **Exit normally**: Press `q` to quit

**Expected Result**: Application works exactly as before, with no mouse-related changes or issues.

## Migration Notes
**Not applicable** - This is pure code removal with no data or system changes.

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Breaking existing functionality | Very Low | Low | Code is dead; removing it cannot break anything |
| Test failures | Very Low | Low | No tests reference mouse messages |
| User confusion | None | None | Mouse was never documented or enabled |
| Future mouse support blocked | None | None | Can be re-added later if properly designed |

**Overall Risk**: **Minimal** - This is dead code removal with no functional changes.

## References
- Research: `/Users/simo/Projects/autodev/.wreckit/items/014-implement-or-remove-mouse-event-handler/research.md`
- Main file: `/Users/simo/Projects/autodev/internal/tui/update.go:29-30`
- Program init: `/Users/simo/Projects/autodev/cmd/aprd/main.go:13`
- Keymap system: `/Users/simo/Projects/autodev/internal/tui/keys.go:1-483`
- Tests: `/Users/simo/Projects/autodev/internal/tui/model_test.go:205`
