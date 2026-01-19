# Research: Fix missing pipe cleanup in runner

**Date**: 2025-01-19
**Item**: 015-fix-missing-pipe-cleanup-in-runner

## Research Question
File descriptors may not be closed if errors occur during pipe setup.

**Motivation:** Prevents file descriptor leaks that could exhaust system resources over time.

**Technical constraints:**
- Add defer stdout.Close() and defer stderr.Close() after pipe creation

**Signals:** priority: high

## Summary
The research identified a resource leak vulnerability in the `runner.Run()` function at `/Users/simo/Projects/autodev/internal/runner/runner.go:1068-1075`. When `cmd.StdoutPipe()` or `cmd.StderrPipe()` are called successfully, they create pipe file descriptors. If subsequent operations fail (such as `cmd.Start()` at line 1077), these pipes are never closed, leading to file descriptor leaks. The fix requires adding deferred cleanup of these pipes immediately after their creation to ensure they're closed regardless of whether the function succeeds or fails.

This is a well-documented issue in the Go community, with [GitHub Issue #58369](https://github.com/golang/go/issues/58369) specifically addressing pipe leaks when `cmd.Start()` is never called or fails. The recommended pattern is to use `defer` to ensure pipes are closed in all execution paths.

## Current State Analysis

### Existing Implementation
The `Options.Run()` function in `/Users/simo/Projects/autodev/internal/runner/runner.go` (lines 1041-1168) manages the execution of Python automation scripts with the following flow:

1. **Lines 1068-1071**: Creates stdout pipe via `cmd.StdoutPipe()`
   - Returns an `io.ReadCloser` that wraps a file descriptor
   - **PROBLEM**: If this succeeds but later operations fail, the pipe is never closed

2. **Lines 1072-1075**: Creates stderr pipe via `cmd.StderrPipe()`
   - Returns another `io.ReadCloser` with a file descriptor
   - **PROBLEM**: Same leak issue as stdout pipe

3. **Lines 1077-1079**: Calls `cmd.Start()` to begin process execution
   - If this fails, the function returns immediately
   - **BUG**: Pipes created in steps 1-2 are not closed before returning

4. **Lines 1104-1111**: Pipes are passed to `stream()` goroutines
   - These goroutines read from the pipes but don't own their lifecycle
   - Pipes should be closed by the owner (the Run function)

5. **Lines 1159-1160**: Waits for streams to finish
   - Comment mentions "they will exit when pipes are closed"
   - However, pipes are only implicitly closed when the process exits
   - No explicit cleanup happens before this point

### Current Error Handling Paths

**Path 1: cmd.Start() failure (line 1077-1079)**
```go
stdout, err := cmd.StdoutPipe()
if err != nil {
    return fmt.Errorf("opening stdout pipe: %w", err)  // OK - no pipe to close
}
stderr, err := cmd.StderrPipe()
if err != nil {
    return fmt.Errorf("opening stderr pipe: %w", err)  // BUG - stdout pipe leaked!
}
if err := cmd.Start(); err != nil {
    return fmt.Errorf("starting runner process: %w", err)  // BUG - both pipes leaked!
}
```

**Path 2: Context cancellation (line 1137-1156)**
- When context is cancelled, process is interrupted/killed
- Pipes are eventually closed when process exits
- No explicit cleanup, but this is less critical since process completes

**Path 3: Normal completion (line 1157-1166)**
- Process exits, implicitly closing pipes
- Streams finish when pipes reach EOF
- No explicit cleanup, but also less critical

### Key Files

- **`/Users/simo/Projects/autodev/internal/runner/runner.go:1041-1168`**
  - Contains the `Options.Run()` function with the pipe leak
  - Lines 1068-1075: Pipe creation without deferred cleanup
  - Line 1077: `cmd.Start()` failure point that leaks pipes
  - Lines 1104-1111: Pipe usage in stream goroutines

- **`/Users/simo/Projects/autodev/internal/runner/runner.go:1173-1216`**
  - Contains the `stream()` helper function
  - Reads from pipes but does not own their lifecycle
  - Uses `bufio.Scanner` with buffer pooling for efficiency

- **`/Users/simo/Projects/autodev/internal/runner/runner_test.go`**
  - Contains integration tests including `TestOptionsRunPassesEnvAndArgs` (lines 106-218)
  - Tests normal execution flow but doesn't test error paths
  - No specific tests for pipe cleanup on early errors

- **`/Users/simo/Projects/autodev/internal/runner/runner.go:126-162`**
  - Contains `makeTempPRD()` function showing proper cleanup pattern
  - Uses deferred cleanup function: `defer cleanup()` at line 1047
  - This is the pattern to follow for pipe cleanup

## Technical Considerations

### Dependencies
- **Go 1.25.0**: Current Go version in use
- **Standard library**: `os/exec` package for process management
- **No external dependencies**: This is pure Go standard library code

### Patterns to Follow

1. **Deferred cleanup pattern** (from `makeTempPRD` at lines 155-160):
   ```go
   cleanup := func() {
       if err := os.Remove(tmpPath); err != nil && !os.IsNotExist(err) {
           log.Printf("debug: failed to remove temp PRD %s: %v", tmpPath, err)
       }
   }
   defer cleanup()
   ```
   This shows the codebase already uses deferred cleanup functions for resources.

2. **sync.Once for channel cleanup** (lines 1085-1094):
   ```go
   var closeOnce sync.Once
   closeLogs := func() {
       closeOnce.Do(func() {
           if o.Logs != nil {
               close(o.Logs)
           }
       })
   }
   ```
   This demonstrates careful resource management to prevent double-close panics.

3. **Error handling with immediate return on failure**:
   The function consistently uses `return fmt.Errorf(...)` pattern, which defer statements will handle correctly.

### Go Documentation Guidance

According to [GitHub Issue #58369](https://github.com/golang/go/issues/58369) ("os/exec: leaks os.pipes if cmd.Start() is never called"), pipes created by `StdoutPipe()` and `StderrPipe()` must be explicitly closed if `cmd.Start()` is never called or fails. The issue confirms this is a known problem and recommends always deferring pipe cleanup.

The `os/exec` documentation states that pipes are the caller's responsibility to close when using `StdoutPipe()` and `StderrPipe()` (unlike `StdoutPipe`'s counterpart methods like `Run()` which handle cleanup automatically).

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Double-close panic** | High | If both the defer and the stream goroutine try to close the pipe, it could panic. However, looking at the `stream()` function (lines 1173-1216), it only reads from the pipe and never closes it. The pipe writes are owned by the os/exec package, which closes them on process exit. Therefore, only our defer will close the read side, making double-close impossible. |
| **Closing pipes too early** | Medium | If we defer close immediately after pipe creation but before starting the process, the process might fail to write. However, defer only executes on function return, so this is safe. The pipes will remain open throughout the function's execution and only close when the function returns (after the process and streams complete). |
| **Breaking existing tests** | Low | Existing tests pass the pipes to `stream()` which just reads from them. Adding defer close won't change this behavior - the pipes will still be readable until the function returns. The test at `TestOptionsRunPassesEnvAndArgs` should continue to work. |
| **Performance overhead** | Low | Defer has minimal overhead (a few nanoseconds). The benefit of preventing file descriptor leaks far outweighs this cost. |

## Recommended Approach

Based on the research findings, the recommended fix is straightforward:

1. **Add deferred cleanup for stdout pipe** immediately after line 1068:
   ```go
   stdout, err := cmd.StdoutPipe()
   if err != nil {
       return fmt.Errorf("opening stdout pipe: %w", err)
   }
   defer stdout.Close()
   ```

2. **Add deferred cleanup for stderr pipe** immediately after line 1072:
   ```go
   stderr, err := cmd.StderrPipe()
   if err != nil {
       return fmt.Errorf("opening stderr pipe: %w", err)
   }
   defer stderr.Close()
   ```

This approach:
- ✅ Ensures pipes are closed on all error paths (including cmd.Start() failure)
- ✅ Ensures pipes are closed on successful completion (redundant but harmless)
- ✅ Follows the existing codebase pattern (see `makeTempPRD` cleanup)
- ✅ Has no double-close risk (stream() only reads, doesn't close)
- ✅ Minimal code change (2 lines added)
- ✅ No impact on existing functionality

### Why This Works

1. **Defer executes on function return**: Whether the function returns due to error or success, defer will run
2. **Pipes remain open until needed**: Defer doesn't close immediately, just schedules close for return time
3. **Safe for goroutines**: The stream goroutines will finish when pipes close (either by defer on return, or by EOF when process exits)
4. **No race conditions**: Only the Run function closes the read side of the pipes

### Testing Recommendations

After implementing the fix, add tests to verify:

1. **Test pipe cleanup on cmd.Start() failure**:
   ```go
   // Create a config that will cause cmd.Start() to fail
   // Verify no file descriptors are leaked
   ```

2. **Test pipe cleanup on StderrPipe() failure**:
   ```go
   // Mock a scenario where StderrPipe() succeeds but Start() fails
   // Verify stdout pipe is still closed
   ```

3. **Integration test with resource monitoring**:
   ```go
   // Check file descriptor count before/after Run() calls
   // Ensure no leaks in error paths
   ```

## Open Questions

1. **Should we add a test for file descriptor leaks?**
   - This would require integration tests that monitor `/proc/self/fd` (Linux) or similar
   - May be overkill for this fix, but could prevent regressions
   - Consider adding to CI if resources allow

2. **Should we add a comment explaining the defer?**
   - The codebase doesn't extensively comment obvious patterns
   - However, since this is fixing a subtle leak bug, a brief comment might be helpful
   - Consider: `// Ensure pipes are closed even if cmd.Start() fails`

3. **Are there other places in the codebase with similar issues?**
   - Searched for `StdoutPipe` and `StderrPipe` - only found in `runner.go`
   - No other uses of `os/exec` pipes in the codebase
   - This appears to be the only instance

## Sources
- [GitHub Issue #58369](https://github.com/golang/go/issues/58369) - os/exec: leaks os.pipes if cmd.Start() is never called
- [GitHub Issue #52580](https://github.com/golang/go/issues/52580) - Documentation clarification on Wait() and cleanup
- [Google Groups Discussion](https://groups.google.com/g/golang-nuts/c/dJkw05r_DNo) - How to correctly use exec.Command and properly clean up
