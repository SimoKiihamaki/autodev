# Research: Remove deprecated Cleanup() method

**Date**: 2025-01-20
**Item**: 020-remove-deprecated-cleanup-method

## Research Question
Deprecated code creates confusion about which cleanup method to use.

**Motivation:** Reduces API confusion and removes dead code.

**Technical constraints:**
- Remove deprecated Cleanup() method from model.go
- Ensure all callers use CleanupFinalModel() or other appropriate method

**Signals:** priority: medium

## Summary
The codebase currently has two cleanup methods for the TUI model: a deprecated `Cleanup()` method and a recommended `CleanupFinalModel()` function. The deprecated `Cleanup()` method is still being called in multiple places within the TUI update logic, creating confusion about which method should be used. The `CleanupFinalModel()` function was introduced as the recommended approach for post-Run() cleanup and is already being used correctly in `cmd/aprd/main.go`.

The research reveals that the deprecated `Cleanup()` method is called in four locations within the TUI package's update logic (`update.go` and `update_keys.go`), all in scenarios where the application is quitting. However, these calls are problematic because they're being made during the Bubble Tea update loop, before the program has actually exited. The correct pattern, already established in `cmd/aprd/main.go`, is to let Bubble Tea exit normally and then call `CleanupFinalModel()` on the final model returned by `p.Run()`.

The implementation requires removing the deprecated `Cleanup()` method and replacing its in-flight calls with the appropriate quit commands (`tea.Quit`) without any cleanup calls, since `CleanupFinalModel()` will handle cleanup after the program exits.

## Current State Analysis

### Existing Implementation
The codebase has two cleanup mechanisms:

1. **`CleanupFinalModel()` function** (model.go:25-29) - The recommended approach
   - Exported function that takes `any` type
   - Performs type assertion to access the model's private `cleanup()` method
   - Called after `p.Run()` completes in `cmd/aprd/main.go:23`
   - Handles nil models gracefully

2. **`Cleanup()` method** (model.go:674-691) - Deprecated but still in use
   - Method on `*model` type (receiver is pointer)
   - Marked as deprecated with comment (line 672)
   - Currently called from 4 locations in TUI update logic
   - Performs: cancels context, clears buffers, closes log file

3. **`cleanup()` method** (model.go:33-40) - Private implementation
   - Private method on `model` type (value receiver)
   - Called by `CleanupFinalModel()` via type assertion
   - Performs the actual cleanup: cancels context, closes log file

### Current patterns and conventions
The established pattern for cleanup, as shown in `cmd/aprd/main.go:19-23`:
```go
finalModel, err := p.Run()
if err != nil {
    log.Printf("TUI error: %v", err)
    os.Exit(1)
}
tui.CleanupFinalModel(finalModel)
```

This pattern ensures cleanup happens after Bubble Tea has fully exited, which is the correct lifecycle approach.

### Integration points
- **`cmd/aprd/main.go`**: Correctly uses `CleanupFinalModel()` after program exit
- **`internal/tui/update.go`**: Incorrectly calls `Cleanup()` before quit (line 51)
- **`internal/tui/update_keys.go`**: Incorrectly calls `Cleanup()` before quit (lines 97, 107, 182)
- **`internal/tui/model.go`**: Contains both the deprecated `Cleanup()` method and the cleanup implementation

## Key Files

### `internal/tui/model.go`
- **Lines 22-29**: `CleanupFinalModel()` - The recommended public API for cleanup
- **Lines 31-40**: `cleanup()` - Private method that performs actual cleanup
- **Lines 666-691**: `Cleanup()` - Deprecated method to be removed
  - Line 672: Deprecation notice
  - Lines 675-678: Cancels running process and sets `m.cancel = nil`
  - Lines 685-687: Clears log and run feed buffers
  - Line 690: Closes log file

### `cmd/aprd/main.go`
- **Lines 19-23**: Correct usage of `CleanupFinalModel()` after program exit
  - Shows the proper pattern: let Bubble Tea exit first, then cleanup

### `internal/tui/update.go`
- **Line 51**: Incorrect call to `m.Cleanup()` before `tea.Quit`
  - Context: In `statusMsg` handler when `quitAfterSave` flag is set and save succeeds
  - Should be: Just return `tea.Quit` without cleanup call

### `internal/tui/update_keys.go`
- **Line 97**: Incorrect call to `m.Cleanup()` before `tea.Quit`
  - Context: In `handleGlobalAction()` for `ActInterrupt` when not running and not dirty
  - Should be: Just return `tea.Quit` without cleanup call

- **Line 107**: Incorrect call to `m.Cleanup()` before `tea.Quit`
  - Context: In `handleGlobalAction()` for `ActQuit` when not running and not dirty
  - Should be: Just return `tea.Quit` without cleanup call

- **Line 182**: Incorrect call to `m.Cleanup()` before `tea.Quit`
  - Context: In `executeQuitSelection()` for "Discard" option (index 1)
  - Should be: Just return `tea.Quit` without cleanup call

### `cmd/aprd/main_test.go`
- **Lines 22-36**: `TestMain_CleanupFinalModel` - Tests cleanup behavior
- **Lines 38-48**: `TestMain_CleanupFinalModel_NilModel` - Tests nil model handling
- These tests verify `CleanupFinalModel()` works correctly and doesn't panic

### `internal/tui/logging.go`
- **Lines 48-59**: `closeLogFile()` method
  - Only updates status display, doesn't actually close file (handled by Python)
  - Called by both `cleanup()` and deprecated `Cleanup()`

## Technical Considerations

### Dependencies
- **External**: None (only uses Go standard library and Bubble Tea)
- **Internal**: None - this is purely a refactoring within the TUI package

### Patterns to Follow
1. **Bubble Tea lifecycle**: Let `tea.Quit` exit the program normally, then cleanup
2. **Post-exit cleanup**: Use `CleanupFinalModel()` after `p.Run()` returns
3. **Type assertion pattern**: `CleanupFinalModel()` shows how to safely access private methods from exported functions
4. **Nil safety**: `CleanupFinalModel()` handles nil models gracefully (check if model type matches before calling cleanup)

### Key Differences Between Methods

| Aspect | Cleanup() | CleanupFinalModel() |
|--------|-----------|---------------------|
| Type | Method on `*model` | Function taking `any` |
| When called | During Bubble Tea update loop | After Bubble Tea exits |
| Called from | TUI internal update logic | main.go after p.Run() |
| Context | Before quit | After final model returned |
| Status | Deprecated | Recommended |

### Why Cleanup() is problematic
1. **Called too early**: It's called during the Bubble Tea update loop, before the program has exited
2. **Modifies model during transition**: Sets `m.cancel = nil` which could affect concurrent operations
3. **Unnecessary work**: `CleanupFinalModel()` will be called anyway after exit
4. **API confusion**: Having two methods creates uncertainty about which to use

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Breaking existing behavior if cleanup timing is critical | Medium | Verify that `CleanupFinalModel()` in main.go is always called (already the case) |
| Missing cleanup if program crashes/panics | Low | Same risk exists with current approach; consider defer in main() as enhancement |
| Accidentally introducing calls to removed method | Low | Remove the method entirely; compiler will catch any missed calls |
| Tests may fail if they reference Cleanup() | Low | Search shows no tests call Cleanup() directly; only CleanupFinalModel() is tested |

## Recommended Approach

Based on research findings, the implementation strategy is:

1. **Remove all calls to `Cleanup()` from update logic** (4 locations):
   - `internal/tui/update.go:51` - Replace with just `tea.Quit`
   - `internal/tui/update_keys.go:97` - Replace with just `tea.Quit`
   - `internal/tui/update_keys.go:107` - Replace with just `tea.Quit`
   - `internal/tui/update_keys.go:182` - Replace with just `tea.Quit`

2. **Remove the deprecated `Cleanup()` method**:
   - Delete lines 666-691 from `internal/tui/model.go`
   - This includes the deprecation comment and entire method body

3. **Verify cleanup still happens**:
   - Confirm `cmd/aprd/main.go` calls `CleanupFinalModel()` after `p.Run()` (already does)
   - This ensures cleanup happens at the correct lifecycle point

4. **Run tests**:
   - Existing tests in `cmd/aprd/main_test.go` verify `CleanupFinalModel()` works
   - All TUI update tests should still pass since they don't rely on cleanup

### Why This Works
- Bubble Tea's `tea.Quit` command causes `p.Run()` to return the final model
- The `main.go` function already calls `CleanupFinalModel(finalModel)` unconditionally
- The private `cleanup()` method (lines 33-40) is still called via type assertion
- No cleanup functionality is lost, just moved to the correct lifecycle point

### Implementation Steps
1. Update `internal/tui/update_keys.go` (3 locations)
2. Update `internal/tui/update.go` (1 location)
3. Remove deprecated method from `internal/tui/model.go`
4. Run tests to verify no regressions
5. Build and run the application to verify cleanup still works correctly

## Open Questions
None - The research has confirmed:
- All current callers of `Cleanup()` are in the TUI update logic
- `CleanupFinalModel()` is already called after program exit
- No external code depends on `Cleanup()`
- The private `cleanup()` method will still be used via `CleanupFinalModel()`
- Tests already verify `CleanupFinalModel()` behavior
