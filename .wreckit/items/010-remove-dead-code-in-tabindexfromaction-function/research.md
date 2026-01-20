# Research: Remove dead code in tabIndexFromAction function

**Date**: 2025-01-19
**Item**: 010-remove-dead-code-in-tabindexfromaction-function

## Research Question
Dead return statement that is never reached since the loop always matches.

**Motivation:** Removes confusing dead code and improves code clarity.

**Technical constraints:**
- Remove the dead return statement or add proper handling for no-match case

**Signals:** priority: high

## Summary

The `tabIndexFromAction` function in `internal/tui/update_keys.go:191-199` contains unreachable dead code. The function is only called from within a `switch` statement that explicitly handles the eight tab navigation actions (`ActGotoTab1` through `ActGotoTab8`). The `tabActions` array in `internal/tui/keys.go:68-77` contains exactly these eight actions in order. Since the switch statement filters to only these eight actions before calling the function, the loop in `tabIndexFromAction` will **always** find a match, making the `return 0, false` statement at line 198 unreachable.

The fix is straightforward: remove the dead return statement at line 198. The function will now always return the matched index, which aligns with its guaranteed usage pattern. This improves code clarity by removing confusing unreachable code.

## Current State Analysis

### Existing Implementation

The function is implemented in `internal/tui/update_keys.go:191-199`:

```go
// tabIndexFromAction maps a goto tab action to its index.
func tabIndexFromAction(act Action) (int, bool) {
	for i, tabAction := range tabActions {
		if tabAction == act {
			return i, true
		}
	}
	return 0, false  // NEVER REACHED
}
```

The `tabActions` array is defined in `internal/tui/keys.go:68-77`:

```go
var tabActions = []Action{
	ActGotoTab1,
	ActGotoTab2,
	ActGotoTab3,
	ActGotoTab4,
	ActGotoTab5,
	ActGotoTab6,
	ActGotoTab7,
	ActGotoTab8,
}
```

### Usage Context

The function is called **exactly once** in the entire codebase at `internal/tui/update_keys.go:120`:

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

### Why the Return is Dead Code

1. The `switch` statement at line 119 only matches the eight `ActGotoTab*` actions
2. The `tabActions` array contains exactly these eight actions (no more, no less)
3. Therefore, when `tabIndexFromAction` is called, the `act` parameter is **guaranteed** to be in `tabActions`
4. The loop will always find a match and return early
5. The `return 0, false` at line 198 is unreachable

### Tab Structure

The application has exactly 8 tabs defined in `internal/tui/tabs.go:18-27`:
- Run (index 0)
- PRD (index 1)
- Settings (index 2)
- Env (index 3)
- Prompt (index 4)
- Logs (index 5)
- Progress (index 6)
- Help (index 7)

These map 1-to-1 with the actions in `tabActions`.

## Key Files

- **`internal/tui/update_keys.go:191-199`** - The `tabIndexFromAction` function with dead return statement
- **`internal/tui/keys.go:68-77`** - The `tabActions` array containing all 8 tab navigation actions
- **`internal/tui/keys.go:17-24`** - Action constants for `ActGotoTab1` through `ActGotoTab8`
- **`internal/tui/update_keys.go:119-127`** - The single call site for `tabIndexFromAction`
- **`internal/tui/tabs.go:18-27`** - Tab specifications showing 8 tabs total
- **`internal/tui/model.go:622-628`** - `setActiveTabIndex` function that validates the returned index

## Technical Considerations

### Dependencies
- **No external dependencies** - Pure Go function
- **Internal integration**: Called from `handleGlobalAction` in the same file
- **Related function**: `setActiveTabIndex` in `model.go` validates the returned index

### Patterns to Follow

1. **Go idiomatic error handling**: When a function cannot fail, don't return error values
2. **Code clarity**: Remove unreachable code rather than keeping "just in case"
3. **Simplicity**: The function becomes clearer as a pure mapping function

### Alternative Approaches Considered

1. **Keep the dead return**: Not recommended - confusing and misleading
2. **Add panic/log for no match**: Unnecessary - this case cannot happen
3. **Refactor to direct mapping**: Could use a map instead of loop, but current approach is clear and efficient

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Future code changes could call function with invalid action | Low | The function is only called from one location with a switch that guards it. Any new code would need to explicitly bypass the switch, which is unlikely. |
| Removing boolean return could break API | Low | The function is internal (not exported), only called once, and the caller already checks `ok` before using `idx`. |
| Index validation might be needed | Low | `setActiveTabIndex` already validates bounds (line 623: `if idx < 0 || idx >= len(m.tabs)`) |

## Recommended Approach

**Option 1: Remove dead return and simplify (RECOMMENDED)**

Change the function to:
```go
// tabIndexFromAction maps a goto tab action to its index.
// Preconditions: act must be one of ActGotoTab1-8
func tabIndexFromAction(act Action) int {
	for i, tabAction := range tabActions {
		if tabAction == act {
			return i
		}
	}
	// unreachable - switch statement guarantees act is in tabActions
	panic("tabIndexFromAction called with invalid action")
}
```

And update the call site to:
```go
case ActGotoTab1, ActGotoTab2, ActGotoTab3, ActGotoTab4, ActGotoTab5, ActGotoTab6, ActGotoTab7, ActGotoTab8:
	idx := tabIndexFromAction(act)
	if m.setActiveTabIndex(idx) {
		m.blurAllInputs()
		// Trigger async tracker load when switching to Progress tab
		if m.currentTabID() == tabIDProgress && !m.trackerLoaded {
			return true, loadTrackerCmd(m.cfg.RepoPath)
		}
		return true, nil
	}
```

**Option 2: Keep signature but remove dead code (SIMPLER)**

Just remove line 198:
```go
// tabIndexFromAction maps a goto tab action to its index.
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

**Recommendation**: Option 2 is simpler and less invasive. The panic in Option 1 is defensive but adds unnecessary complexity for a case that cannot occur.

## Open Questions

1. **Should we add a comment explaining why the return is unreachable?**
   - Yes, add a brief comment: "// unreachable - switch statement guarantees act is in tabActions"

2. **Should we consider refactoring to use a map for O(1) lookup?**
   - Current O(n) loop is fine for 8 elements. Not worth the complexity.

3. **Are there any tests that need to be updated?**
   - No tests exist for this function currently. Tests would be good but are out of scope for this fix.

## Implementation Notes

- **Files to modify**: `internal/tui/update_keys.go` only
- **Lines to change**: Remove line 198, add explanatory comment
- **Testing**: Manual testing of tab navigation (keys 1-8) should verify no regression
- **Backward compatibility**: Not an issue - function is internal, not exported
