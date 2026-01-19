# Remove dead code in tabIndexFromAction function Implementation Plan

## Overview
Remove the unreachable `return 0, false` statement from the `tabIndexFromAction` function in `internal/tui/update_keys.go`. This function is guaranteed to always find a match because it's only called from a switch statement that filters to exactly the eight tab navigation actions present in the `tabActions` array.

## Current State Analysis

### Existing Implementation
The `tabIndexFromAction` function at `internal/tui/update_keys.go:191-199`:
```go
func tabIndexFromAction(act Action) (int, bool) {
	for i, tabAction := range tabActions {
		if tabAction == act {
			return i, true
		}
	}
	return 0, false  // Line 198 - NEVER REACHED
}
```

### Why the Return is Unreachable
1. **Switch statement guard** (`update_keys.go:119`): The function is only called when `act` is one of `ActGotoTab1` through `ActGotoTab8`
2. **Complete action array** (`keys.go:68-77`): The `tabActions` array contains exactly these 8 actions, no more, no less
3. **Guaranteed match**: Since the switch only passes these 8 actions and the array contains exactly these 8 actions, the loop will always find a match and return early
4. **Unreachable code**: Line 198 (`return 0, false`) can never be executed

### Usage Context
The function is called **exactly once** in the entire codebase at `update_keys.go:120`:
```go
case ActGotoTab1, ActGotoTab2, ActGotoTab3, ActGotoTab4, ActGotoTab5, ActGotoTab6, ActGotoTab7, ActGotoTab8:
	if idx, ok := tabIndexFromAction(act); ok && m.setActiveTabIndex(idx) {
		m.blurAllInputs()
		// Trigger async tracker load when switching to Progress tab
		if m.currentTabID() == tabIDProgress && !m.trackerLoaded {
			return true, loadTrackerCmd(m.cfg.RepoPath)
		}
		return true, nil
	}
```

### Safety Validation
The `setActiveTabIndex` function (`model.go:622-628`) provides an additional safety net by validating bounds:
```go
func (m *model) setActiveTabIndex(idx int) bool {
	if idx < 0 || idx >= len(m.tabs) {
		return false
	}
	m.tabIndex = idx
	return true
}
```

## Desired End State

The function will have:
1. The dead `return 0, false` statement removed from line 198
2. An explanatory comment documenting why the final return is unreachable
3. Cleaner, more honest code that accurately reflects its actual behavior

### Key Discoveries
- **Single call site**: The function is internal (not exported) and only called from one location
- **No tests exist**: There are currently no tests for this function (verified via grep)
- **Defensive programming already in place**: `setActiveTabIndex` validates the returned index, providing defense in depth
- **Pattern consistency**: This is pure code cleanup with no API changes or functional impact

## What We're NOT Doing
- ❌ Changing the function signature (keeping `(int, bool)` return type for minimal changes)
- ❌ Adding a panic or error handling (unnecessary for a case that cannot occur)
- ❌ Refactoring to use a map for O(1) lookup (current O(n) is fine for 8 elements)
- ❌ Adding tests (out of scope for this dead code removal)
- ❌ Modifying any other files or functions

## Implementation Approach

**Strategy**: Minimal, surgical change to remove dead code while adding documentation

We'll take the simplest approach (Option 2 from research):
- Remove the unreachable `return 0, false` statement
- Keep the function signature unchanged to minimize diff noise
- Add a clear comment explaining why the function is guaranteed to succeed

**Rationale**:
- The function is internal and only called once
- The current call site already checks the `ok` boolean
- Keeping the signature maintains API compatibility (even though it's internal)
- The change is self-contained and low-risk

---

## Phase 1: Remove Dead Return Statement and Add Documentation

### Overview
Remove the unreachable return statement and document why the function is guaranteed to always find a match.

### Changes Required

#### 1. tabIndexFromAction function
**File**: `internal/tui/update_keys.go`
**Lines**: 191-199
**Changes**:
- Remove line 198 (`return 0, false`)
- Add explanatory comment before the function

**Current code**:
```go
// tabIndexFromAction maps a goto tab action to its index.
func tabIndexFromAction(act Action) (int, bool) {
	for i, tabAction := range tabActions {
		if tabAction == act {
			return i, true
		}
	}
	return 0, false
}
```

**New code**:
```go
// tabIndexFromAction maps a goto tab action to its index.
// This function is only called from a switch statement that handles exactly the eight
// ActGotoTab* actions contained in tabActions, so the loop will always find a match.
func tabIndexFromAction(act Action) (int, bool) {
	for i, tabAction := range tabActions {
		if tabAction == act {
			return i, true
		}
	}
	// unreachable - switch statement guarantees act is in tabActions
	return 0, false
}
```

**Wait** - I need to reconsider this. The research recommends keeping the unreachable return with a comment. Let me re-read the research...

Actually, looking at the research again, it says:

> **Option 2: Keep signature but remove dead code (SIMPLER)**
> Just remove line 198

But then it shows keeping the return statement with a comment. Let me clarify - the research is saying to keep the unreachable return but add a comment. However, that's still dead code.

Let me reconsider: The research actually says Option 2 is to keep the signature but the title says "remove dead code". The example shows keeping the return with a comment, which is contradictory.

Looking at the acceptance criteria in the research:
> - Remove the dead return statement or add proper handling for no-match case

The "or" suggests either approach is acceptable. However, the title clearly says "Remove dead code" and the recommendation says "Remove the dead return statement at line 198".

I think the cleanest approach is to actually REMOVE the dead return statement entirely, not keep it with a comment. Dead code should be removed, not kept with comments.

Let me revise the plan:

**Revised approach**: Remove the unreachable return statement entirely

**New code**:
```go
// tabIndexFromAction maps a goto tab action to its index.
// This function is only called from a switch statement that handles exactly the eight
// ActGotoTab* actions contained in tabActions, so the loop will always find a match.
func tabIndexFromAction(act Action) (int, bool) {
	for i, tabAction := range tabActions {
		if tabAction == act {
			return i, true
		}
	}
	// unreachable - switch statement guarantees act is in tabActions
	panic("unreachable")
}
```

Actually wait - in Go, if a function has a return value, all code paths must return a value. So we can't just remove the return. We either:
1. Keep the return with a comment (but it's still dead code)
2. Add a panic (defensive but changes behavior)
3. Change the function signature to not return a bool (larger refactor)

Given the research says "Option 2 is simpler and less invasive" and shows keeping the return with a comment, I think the intent is:
- Keep the function signature
- Keep the return statement
- Add a comment explaining it's unreachable

This satisfies the requirement of "adding proper handling" (the comment explains why it's not needed) while being simpler than changing the signature.

Let me finalize with Option 2 from the research:

**Final approach**: Keep the return statement but add documentation

**New code**:
```go
// tabIndexFromAction maps a goto tab action to its index.
// This function is only called from a switch statement that handles exactly the eight
// ActGotoTab* actions contained in tabActions, so the loop will always find a match.
func tabIndexFromAction(act Action) (int, bool) {
	for i, tabAction := range tabActions {
		if tabAction == act {
			return i, true
		}
	}
	// unreachable - switch statement guarantees act is in tabActions
	return 0, false
}
```

This aligns with the research recommendation and Go's requirement that all code paths return values.

### Success Criteria

#### Automated Verification:
- [ ] Build succeeds: `go build ./...`
- [ ] Code compiles without errors
- [ ] No linter warnings about missing return statements

#### Manual Verification:
- [ ] Test tab navigation using keys 1-8
- [ ] Verify each tab (1-8) switches correctly
- [ ] Confirm no regressions in tab switching behavior
- [ ] Test the Progress tab specifically (triggers async tracker load)

**Note**: Complete automated verification, then manually test tab navigation before considering the task complete.

---

## Testing Strategy

### Unit Tests
- **No unit tests to add** - Out of scope for this dead code removal
- Current behavior is preserved; no logic changes

### Integration Tests
- **No integration tests to modify** - This is purely internal code cleanup

### Manual Testing Steps

1. **Start the application**: Run the TUI application
2. **Test each tab navigation key**: Press keys 1-8 individually
3. **Verify correct tab switches**: Each key should switch to its corresponding tab
4. **Test Progress tab specifically**: Press 8 to switch to Progress tab and verify tracker loads if not already loaded
5. **Test other tabs**: Navigate through tabs multiple times to ensure no regressions
6. **Test other global shortcuts**: Ensure other keys (q, ?, Ctrl+S, etc.) still work

**Expected behavior**: All tab navigation works exactly as before, with no observable changes.

## Migration Notes
- **No migration needed** - This is pure code cleanup with no API or data changes
- **No breaking changes** - Function is internal, not exported
- **No configuration changes** - No user-facing impact

## References
- Research: `/Users/simo/Projects/autodev/.wreckit/items/010-remove-dead-code-in-tabindexfromaction-function/research.md`
- Target function: `internal/tui/update_keys.go:191-199`
- Call site: `internal/tui/update_keys.go:119-127`
- tabActions array: `internal/tui/keys.go:68-77`
- Index validation: `internal/tui/model.go:622-628`
