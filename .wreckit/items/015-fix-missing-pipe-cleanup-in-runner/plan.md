# Fix missing pipe cleanup in runner Implementation Plan

## Overview
Fix a resource leak vulnerability in the `runner.Run()` function where file descriptors for stdout and stderr pipes are not closed if errors occur during pipe setup or process startup. This fix prevents file descriptor leaks that could exhaust system resources over time.

## Current State Analysis

The `Options.Run()` function in `/Users/simo/Projects/autodev/internal/runner/runner.go` (lines 1041-1168) creates pipes for subprocess output but fails to clean them up on error paths.

**Current implementation flow:**
1. **Lines 1068-1071**: Creates stdout pipe via `cmd.StdoutPipe()`
   - Returns an `io.ReadCloser` that wraps a file descriptor
   - **BUG**: If this succeeds but later operations fail, the pipe is never closed

2. **Lines 1072-1075**: Creates stderr pipe via `cmd.StderrPipe()`
   - Returns another `io.ReadCloser` with a file descriptor
   - **BUG**: Same leak issue as stdout pipe

3. **Lines 1077-1079**: Calls `cmd.Start()` to begin process execution
   - If this fails, the function returns immediately
   - **BUG**: Both pipes created in steps 1-2 are not closed before returning

**Error paths that leak pipes:**
- `cmd.StdoutPipe()` succeeds, `cmd.StderrPipe()` fails → **stdout pipe leaked**
- Both pipes succeed, `cmd.Start()` fails → **both pipes leaked**

**Why this matters:**
- Each leaked pipe consumes a file descriptor
- Repeated failures (e.g., in automation scripts) could exhaust system file descriptors
- This is a well-documented issue in Go ([GitHub Issue #58369](https://github.com/golang/go/issues/58369))

## Desired End State

Pipes created by `cmd.StdoutPipe()` and `cmd.StderrPipe()` are guaranteed to be closed on all execution paths (success and failure) using deferred cleanup.

### Key Discoveries:

1. **Only one location uses these pipes**: The entire codebase was searched; only `/Users/simo/Projects/autodev/internal/runner/runner.go` uses `StdoutPipe()` or `StderrPipe()`

2. **The `stream()` function does not close pipes**: Lines 1173-1216 show that `stream()` only reads from pipes and never calls `Close()` on them. This means deferring close in `Run()` is safe and won't cause double-close panics.

3. **Existing cleanup pattern in codebase**: The `makeTempPRD()` function (lines 155-160) demonstrates the proper deferred cleanup pattern already used in this codebase:
   ```go
   cleanup := func() {
       if err := os.Remove(tmpPath); err != nil && !os.IsNotExist(err) {
           log.Printf("debug: failed to remove temp PRD %s: %v", tmpPath, err)
       }
   }
   defer cleanup()
   ```

4. **No impact on normal execution**: The defer statement only executes when the function returns. During normal execution, pipes remain open and functional. The stream goroutines will finish when pipes close (either by defer on return, or by EOF when process exits).

## What We're NOT Doing

- ❌ Not modifying the `stream()` function (it correctly doesn't close pipes)
- ❌ Not changing the goroutine structure or error handling
- ❌ Not adding file descriptor monitoring tests (too complex for this fix)
- ❌ Not modifying any other files in the codebase
- ❌ Not adding extensive comments (the fix is self-documenting defer pattern)

## Implementation Approach

This is a minimal, surgical fix that adds **exactly two lines** of code to ensure pipes are cleaned up on all execution paths.

**Strategy:**
1. Add `defer stdout.Close()` immediately after creating stdout pipe (line 1071)
2. Add `defer stderr.Close()` immediately after creating stderr pipe (line 1075)

**Why this works:**
- Defer executes on function return, whether due to error or success
- Pipes remain open throughout the function's lifecycle
- No risk of double-close (stream() only reads, doesn't close)
- Follows the existing codebase pattern (see makeTempPRD cleanup)

---

## Phase 1: Add Deferred Pipe Cleanup

### Overview
Add deferred cleanup calls for both stdout and stderr pipes to ensure they are closed on all execution paths.

### Changes Required:

#### 1. runner.go - Options.Run() function
**File**: `/Users/simo/Projects/autodev/internal/runner/runner.go`
**Changes**: Add `defer` statements after pipe creation

**Line 1068-1071 (stdout pipe):**
```go
stdout, err := cmd.StdoutPipe()
if err != nil {
    return fmt.Errorf("opening stdout pipe: %w", err)
}
defer stdout.Close()
```

**Line 1072-1075 (stderr pipe):**
```go
stderr, err := cmd.StderrPipe()
if err != nil {
    return fmt.Errorf("opening stderr pipe: %w", err)
}
defer stderr.Close()
```

### Success Criteria:

#### Automated Verification:
- [ ] All existing tests pass: `go test ./internal/runner/...`
- [ ] Build succeeds: `go build ./...`
- [ ] No race conditions detected: `go test -race ./internal/runner/...`
- [ ] Linting passes: `golangci-lint run` (if configured)

#### Manual Verification:
- [ ] Verify the fix by examining the code: defer statements are present after both pipe creations
- [ ] Verify existing tests still pass (no behavioral changes)
- [ ] Verify no compiler warnings or errors

**Note**: Complete all automated verification, then confirm the fix is correct before marking complete.

---

## Testing Strategy

### Why No New Tests Are Required

This fix is defensive programming - it ensures cleanup on error paths that are not currently tested. Adding tests for these error paths would require:
1. Mocking `exec.Command` behavior in a way that's difficult to do cleanly
2. Integration tests that monitor file descriptors (platform-specific)
3. Tests that are fragile and add little value

The existing tests provide sufficient coverage:
- `TestOptionsRunPassesEnvAndArgs` (lines 106-218) tests the normal execution path
- The defer statements don't change behavior in the success case
- The fix is a well-known pattern recommended by Go documentation

### Existing Test Coverage

The current test suite validates:
- Normal execution flow (process starts, streams output, completes successfully)
- Environment variable passing
- Argument building
- PRD file preparation

These tests will continue to pass, confirming that the defer statements don't break normal operation.

### Verification Approach

Instead of new tests, verify the fix by:
1. **Code review**: Confirm defer statements are present and correctly placed
2. **Existing tests**: Run full test suite to ensure no regressions
3. **Static analysis**: The compiler and linter will catch any obvious issues

---

## Migration Notes

No migration required. This is a backward-compatible bug fix with no API changes.

---

## References

- Research: `/Users/simo/Projects/autodev/.wreckit/items/015-fix-missing-pipe-cleanup-in-runner/research.md`
- Source file: `/Users/simo/Projects/autodev/internal/runner/runner.go` (lines 1041-1168)
- Go Issue: [GitHub Issue #58369](https://github.com/golang/go/issues/58369) - os/exec: leaks os.pipes if cmd.Start() is never called
- Related pattern: `makeTempPRD()` function in same file (lines 155-160) showing deferred cleanup
