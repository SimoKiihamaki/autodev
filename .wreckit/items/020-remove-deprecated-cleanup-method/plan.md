# Remove deprecated Cleanup() method Implementation Plan

## Overview
Remove the deprecated `Cleanup()` method from the TUI model and update all call sites to use the correct Bubble Tea lifecycle pattern. The deprecated method is being called during the Bubble Tea update loop, which is premature - cleanup should happen after `p.Run()` completes via `CleanupFinalModel()`.

## Current State Analysis

### Existing Implementation
The codebase has two cleanup mechanisms:

1. **`CleanupFinalModel()` function** (model.go:25-29) - The recommended approach
   - Exported function that takes `any` type
   - Performs type assertion to access the model's private `cleanup()` method
   - Called after `p.Run()` completes in `cmd/aprd/main.go:23`
   - Handles nil models gracefully

2. **`Cleanup()` method** (model.go:674-691) - Deprecated but still in use
   - Method on `*model` type (pointer receiver)
   - Marked as deprecated with comment (line 672)
   - Currently called from 4 locations in TUI update logic
   - Performs: cancels context, clears buffers, closes log file

3. **`cleanup()` method** (model.go:33-40) - Private implementation
   - Private method on `model` type (value receiver)
   - Called by `CleanupFinalModel()` via type assertion
   - Performs the actual cleanup: cancels context, closes log file

### Current Pattern (Correct)
The established pattern for cleanup in `cmd/aprd/main.go:19-23`:
```go
finalModel, err := p.Run()
if err != nil {
    log.Printf("TUI error: %v", err)
    os.Exit(1)
}
tui.CleanupFinalModel(finalModel)
```

This pattern ensures cleanup happens after Bubble Tea has fully exited, which is the correct lifecycle approach.

### Problem: In-Flight Cleanup Calls
The deprecated `Cleanup()` is incorrectly called in 4 locations within the TUI update logic:

1. **`internal/tui/update.go:51`** - In `statusMsg` handler when `quitAfterSave` flag is set and save succeeds
2. **`internal/tui/update_keys.go:97`** - In `handleGlobalAction()` for `ActInterrupt` when not running and not dirty
3. **`internal/tui/update_keys.go:107`** - In `handleGlobalAction()` for `ActQuit` when not running and not dirty
4. **`internal/tui/update_keys.go:182`** - In `executeQuitSelection()` for "Discard" option (index 1)

These calls are problematic because:
- They're made during the Bubble Tea update loop, before the program has exited
- They modify model state during transition (sets `m.cancel = nil`)
- They're unnecessary since `CleanupFinalModel()` will be called anyway after exit
- They create API confusion about which method to use

## Desired End State

### Specification
1. **No premature cleanup**: The TUI update logic should not call any cleanup methods
2. **Single cleanup API**: Only `CleanupFinalModel()` should be used for cleanup
3. **Clean Bubble Tea lifecycle**: Use `tea.Quit` to exit, then cleanup after `p.Run()` returns
4. **No API confusion**: Remove the deprecated `Cleanup()` method entirely

### Verification Criteria
- [ ] The `Cleanup()` method is completely removed from `internal/tui/model.go`
- [ ] All 4 call sites in TUI update logic only return `tea.Quit` without cleanup calls
- [ ] `CleanupFinalModel()` in `cmd/aprd/main.go` remains unchanged and continues to work
- [ ] All existing tests pass (especially `cmd/aprd/main_test.go`)
- [ ] Manual testing confirms cleanup still works (context cancelled, log file closed)

### Key Discoveries:
- **Lines 666-691 in model.go**: The deprecated `Cleanup()` method to be removed
- **Lines 22-29 in model.go**: `CleanupFinalModel()` is the correct public API
- **Lines 33-40 in model.go**: The private `cleanup()` method will still be used via type assertion
- **Lines 19-23 in cmd/aprd/main.go**: Shows the correct pattern - cleanup after `p.Run()`, not before `tea.Quit`
- **Pattern identified**: All 4 problematic calls follow the same pattern: `m.Cleanup()` immediately followed by `tea.Quit`
- **Zero external dependencies**: No code outside the TUI package uses `Cleanup()` (compiler will verify this)

## What We're NOT Doing

- **NOT modifying `CleanupFinalModel()`**: It's already correct and well-tested
- **NOT modifying `cmd/aprd/main.go`**: The cleanup pattern there is already correct
- **NOT adding new cleanup mechanisms**: The existing `CleanupFinalModel()` is sufficient
- **NOT changing cleanup behavior**: The same operations will still happen, just at the correct time
- **NOT handling crashes/panics differently**: Same risk exists with current approach (defer could be future enhancement)
- **NOT modifying the private `cleanup()` method**: It will continue to work via type assertion

## Implementation Approach

### Strategy
This is a straightforward refactoring with a single phase. The approach is:

1. **Remove all calls to `Cleanup()`** - Replace with just `tea.Quit`
2. **Remove the deprecated method** - Delete lines 666-691 from `model.go`
3. **Verify compilation** - Compiler will catch any missed calls
4. **Run tests** - Existing tests verify `CleanupFinalModel()` works
5. **Manual testing** - Confirm cleanup still works correctly

### Why This Is Safe
- **Single cleanup point**: `CleanupFinalModel()` is already called unconditionally in `main.go`
- **Same operations**: The private `cleanup()` method still does the same work
- **Correct timing**: Cleanup happens after Bubble Tea exits, not during the update loop
- **Compiler verification**: Removing the method ensures no missed calls

### Bubble Tea Lifecycle Pattern
The correct Bubble Tea pattern is:
```
p.Run() → returns final model → cleanup → program exits
```

NOT:
```
cleanup → tea.Quit → p.Run() returns → cleanup again (problematic!)
```

---

## Phase 1: Remove Deprecated Cleanup() Method

### Overview
Remove all calls to the deprecated `Cleanup()` method from TUI update logic, then delete the method itself. This ensures cleanup happens at the correct lifecycle point (after Bubble Tea exits) rather than during the update loop.

### Changes Required:

#### 1. Remove Cleanup() calls in update_keys.go (3 locations)
**File**: `internal/tui/update_keys.go`

**Location 1** (Line 97):
```go
// BEFORE:
if m.dirty {
    m.beginQuitConfirm()
    return true, nil
}
m.Cleanup()
return true, tea.Quit

// AFTER:
if m.dirty {
    m.beginQuitConfirm()
    return true, nil
}
return true, tea.Quit
```

**Location 2** (Line 107):
```go
// BEFORE:
if m.dirty {
    m.beginQuitConfirm()
    return true, nil
}
m.Cleanup()
return true, tea.Quit

// AFTER:
if m.dirty {
    m.beginQuitConfirm()
    return true, nil
}
return true, tea.Quit
```

**Location 3** (Line 182):
```go
// BEFORE:
case 1: // Discard
    m.cancelQuitConfirm()
    m.Cleanup()
    return true, tea.Quit

// AFTER:
case 1: // Discard
    m.cancelQuitConfirm()
    return true, tea.Quit
```

#### 2. Remove Cleanup() call in update.go (1 location)
**File**: `internal/tui/update.go`

**Location** (Line 51):
```go
// BEFORE:
if m.lastSaveErr == nil {
    // Only clear the flag when save succeeds
    m.quitAfterSave = false
    m.cancelQuitConfirm()
    m.Cleanup()
    return m, tea.Quit
}

// AFTER:
if m.lastSaveErr == nil {
    // Only clear the flag when save succeeds
    m.quitAfterSave = false
    m.cancelQuitConfirm()
    return m, tea.Quit
}
```

#### 3. Delete the deprecated Cleanup() method
**File**: `internal/tui/model.go`

**Remove lines 666-691** (the entire method including deprecation comment):
```go
// DELETE THESE LINES:
// Cleanup performs graceful shutdown of the model's resources.
// It should be called before exiting the application to ensure:
// - Any running process is cancelled
// - Log channels are properly closed
// - File handles are released
//
// Deprecated: Use CleanupFinalModel() instead for post-Run() cleanup.
// This method is retained for internal use and backwards compatibility.
func (m *model) Cleanup() {
    // Cancel any running process
    if m.cancel != nil {
        m.cancel()
        m.cancel = nil
    }

    // Close the log channel if still open
    // Note: only the sender should close channels, and we're not the sender
    // The logCh is closed by the runner goroutine when it completes

    // Clear large buffers to help GC
    m.logBuf = nil
    m.runFeedBuf = nil

    // Close any open log file (though this is now handled by Python)
    m.closeLogFile("cleanup")
}
```

### Success Criteria:

#### Automated Verification:
- [ ] Tests pass: `go test ./cmd/aprd/...`
- [ ] Tests pass: `go test ./internal/tui/...`
- [ ] Build succeeds: `go build ./cmd/aprd`
- [ ] No compilation errors related to missing `Cleanup()` method

#### Manual Verification:
- [ ] Run the application and press `Ctrl+C` to quit - should exit cleanly
- [ ] Run the application, make changes, then quit with "Save" - should save and exit cleanly
- [ ] Run the application, make changes, then quit with "Discard" - should discard and exit cleanly
- [ ] Run the application, start a run, then interrupt it - should cancel and exit cleanly
- [ ] Verify that after each exit, the context is properly cancelled (no goroutine leaks)
- [ ] Verify that log files are properly closed (check with `lsof` if needed)

**Note**: Complete all automated verification, then pause for manual confirmation before considering the task complete.

---

## Testing Strategy

### Unit Tests:
- **Existing tests in `cmd/aprd/main_test.go`** verify `CleanupFinalModel()` works correctly
- **No new tests needed** - we're removing code, not adding functionality
- The compiler will act as a test: any missed calls to `Cleanup()` will cause compilation errors

### Integration Tests:
- **Existing TUI tests** verify update logic works correctly
- Removing cleanup calls should not affect these tests since they don't actually quit the program

### Manual Testing Steps:
1. **Test normal quit (Ctrl+C)**:
   - Start the application: `go run ./cmd/aprd`
   - Press `Ctrl+C` without making any changes
   - Verify: Application exits immediately without errors
   - Verify: No "cleanup already done" errors in logs

2. **Test quit with save**:
   - Start the application
   - Make a configuration change (e.g., toggle a flag)
   - Press `Ctrl+C` to trigger quit confirmation
   - Press `s` or select "Save" and press Enter
   - Verify: Changes are saved and application exits cleanly

3. **Test quit with discard**:
   - Start the application
   - Make a configuration change
   - Press `Ctrl+C` to trigger quit confirmation
   - Press `d` or select "Discard" and press Enter
   - Verify: Changes are discarded and application exits cleanly

4. **Test quit during run**:
   - Start the application
   - Start a run (if possible)
   - Press `Ctrl+C` to interrupt the run
   - Verify: Run is cancelled cleanly
   - Press `Ctrl+C` again to quit
   - Verify: Application exits cleanly

5. **Test context cancellation**:
   - Add temporary debug logging to `cleanup()` method in `model.go`
   - Run the application and quit
   - Verify: `cleanup()` is called after `p.Run()` returns (not before)
   - Remove debug logging

## Migration Notes
No migration needed - this is a pure refactoring that removes deprecated code. The cleanup behavior remains the same, just at the correct lifecycle point.

## References
- Research: `/Users/simo/Projects/autodev/.wreckit/items/020-remove-deprecated-cleanup-method/research.md`
- `internal/tui/model.go` lines 22-40: `CleanupFinalModel()` and `cleanup()` implementation
- `internal/tui/model.go` lines 666-691: Deprecated `Cleanup()` method to be removed
- `cmd/aprd/main.go` lines 19-23: Correct cleanup pattern
- `internal/tui/update.go` line 51: Incorrect cleanup call to remove
- `internal/tui/update_keys.go` lines 97, 107, 182: Incorrect cleanup calls to remove
- `cmd/aprd/main_test.go` lines 22-48: Tests verifying `CleanupFinalModel()` behavior
