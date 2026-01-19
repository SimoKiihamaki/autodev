# Research: Fix race condition in process cancellation

**Date**: 2025-01-19
**Item**: 008-fix-race-condition-in-process-cancellation

## Research Question
No explicit cancellation context for errgroup, potential for race conditions between concurrent goroutines.

**Motivation:** Prevents race conditions that could cause deadlocks or inconsistent state during concurrent operations.

**Technical constraints:**
- Add explicit context.WithCancel
- Use errgroup.WithContext to tie context to errgroup
- Ensure ctx is used for all goroutines

**Signals:** priority: critical

## Summary

The codebase has a **critical race condition** in the process cancellation logic within `internal/runner/runner.go`. The current implementation uses an `errgroup.Group` without tying it to a cancellation context, which creates a gap where:

1. **Three concurrent goroutines** are spawned (two for streaming stdout/stderr, one for waiting on process completion)
2. **Only one goroutine** (the process wait) is context-aware via the outer `ctx.Done()` select
3. **The streaming goroutines** have no cancellation mechanism and will block indefinitely waiting on I/O
4. **When ctx is cancelled**, the main select block triggers process termination but cannot cancel the streaming goroutines, leading to potential deadlocks

The fix requires using `errgroup.WithContext(ctx)` to create a cancellation-aware errgroup, ensuring all goroutines (including the streaming ones) respect context cancellation and exit cleanly.

## Current State Analysis

### Existing Implementation

**Location:** `internal/runner/runner.go:1041-1135`

The `Options.Run()` method manages a subprocess execution with the following concurrent operations:

```go
// Line 1094: errgroup created WITHOUT context binding
g := new(errgroup.Group)

// Lines 1095-1102: Two streaming goroutines that NEVER check ctx.Done()
g.Go(func() error {
    stream(stdout, false, o.Logs)
    return nil
})
g.Go(func() error {
    stream(stderr, true, o.Logs)
    return nil
})

// Line 1105: Process wait goroutine in a separate channel
waitCh := make(chan error, 1)
go func() { waitCh <- cmd.Wait() }()
```

**The problem:** Lines 1095-1102 spawn goroutines via `g.Go()` that call `stream()`, which performs blocking I/O operations (`bufio.Scanner.Scan()`) without any context cancellation checks. These goroutines cannot be interrupted.

### Current Patterns and Conventions

1. **Context creation pattern** (from `internal/tui/run.go:132`):
   ```go
   ctx, cancel := context.WithCancel(context.Background())
   m.cancel = cancel
   ```
   The TUI creates a cancellation context and stores the cancel function for manual triggering.

2. **Context passing pattern** (from `internal/tui/run.go:144-168`):
   ```go
   go func(ctx context.Context, opts runner.Options, logCh chan runner.Line, resultCh chan error) {
       defer func() { /* panic recovery */ }()
       err = opts.Run(ctx)
       // ...
   }(ctx, options, ch, m.runResult)
   ```
   The context is passed through to `opts.Run()` but not propagated to the errgroup.

3. **errgroup usage comment** (line 1093):
   ```go
   // Use errgroup for better error propagation and cleaner goroutine management.
   // The errgroup context is not used here because we manage cancellation separately.
   ```
   This comment is **misleading** - cancellation is managed separately for the process wait goroutine but NOT for the streaming goroutines.

### Integration Points

1. **TUI caller**: `internal/tui/run.go:167` - Calls `opts.Run(ctx)` with a cancellable context
2. **Test callers**:
   - `internal/runner/runner_test.go:157` - Uses `context.Background()` (non-cancellable)
   - `internal/tui/run_integration_test.go:66` - Creates cancellable context with `defer cancel()`
3. **API mode**: `cmd/api/main.go:26` - Uses `signal.NotifyContext()` for graceful shutdown

## Key Files

### `internal/runner/runner.go`

**Lines 1092-1102: errgroup creation and goroutine spawning**
- Creates plain `errgroup.Group` without context binding
- Spawns two streaming goroutines that never check for cancellation
- **Critical issue**: These goroutines will block forever on I/O if the process hangs

**Lines 1104-1134: Cancellation handling**
```go
select {
case <-ctx.Done():
    // Signal the process to stop
    if sigErr := interruptProcess(cmd); sigErr != nil { /* ... */ }
    select {
    case <-waitCh:
        // Process exited
    case <-time.After(2 * time.Second):
        // Force kill if timeout
        if killErr := forceKillProcess(cmd); killErr != nil { /* ... */ }
        <-waitCh
    }
    _ = g.Wait() // BLOCKS HERE if stream goroutines don't finish
```

**The race condition**: After `ctx.Done()` fires and the process is killed, the code calls `g.Wait()` at line 1122 or 1127. If the stream goroutines are still blocking on I/O (e.g., waiting for more data from a now-dead pipe), this wait will **block indefinitely** or until the pipes are closed by the OS.

**Lines 1137-1175: stream() function**
```go
func stream(r io.Reader, isErr bool, logs chan Line) {
    // ...
    sc := bufio.NewScanner(r)
    for sc.Scan() {  // NO context checking here!
        line := Line{Time: time.Now(), Text: sc.Text(), Err: isErr}
        if trySend(logs, line) {
            dropping = false
            continue
        }
        // ...
    }
}
```

**Critical gap**: The `stream()` function never checks `ctx.Done()`. It will block on `sc.Scan()` indefinitely if the subprocess doesn't close its stdout/stderr pipes.

### `internal/tui/run.go`

**Lines 132-133: Context creation**
```go
ctx, cancel := context.WithCancel(context.Background())
m.cancel = cancel
```
Creates a cancellable context for the run operation.

**Lines 144-168: Goroutine that calls opts.Run()**
```go
go func(ctx context.Context, opts runner.Options, logCh chan runner.Line, resultCh chan error) {
    defer func() {
        // Panic recovery and error handling
        select {
        case resultCh <- err:
        case <-ctx.Done():  // Checks context before send
        }
        close(resultCh)
    }()
    err = opts.Run(ctx)  // Context passed but not fully used
}(ctx, options, ch, m.runResult)
```

The context is passed through but the errgroup goroutines don't respect it.

## Technical Considerations

### Dependencies

**External dependencies:**
- `golang.org/x/sync/errgroup` - Already imported (line 19)
- Standard library `context` package - Already imported (line 5)

**No new dependencies required** - The fix only requires changing how existing packages are used.

### Patterns to Follow

**Existing errgroupWithContext pattern:**
The codebase does NOT currently use `errgroup.WithContext()`, but this is the standard Go pattern for cancellable goroutine groups:

```go
g, ctx := errgroup.WithContext(ctx)
g.Go(func() error {
    return doSomething(ctx)
})
```

**Existing context cancellation pattern:**
From `cmd/api/main.go:26`:
```go
ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
defer stop()
```

This shows the project already uses context cancellation for graceful shutdown.

### How errgroup.WithContext Works

When using `errgroup.WithContext(ctx)`:
1. The returned context is cancelled when **any** goroutine in the group returns a non-nil error
2. All goroutines in the group should check `ctx.Done()` to exit early
3. Calling `g.Wait()` will return the first non-nil error from any goroutine

**Key benefit:** If one goroutine fails or needs to cancel, all other goroutines in the group are notified via the shared context.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Breaking change to stream() signature** | High - stream() is called from multiple locations | Add context parameter with default value, update all call sites |
| **Deadlock during cancellation** | Critical - process could hang indefinitely | Ensure all goroutines check ctx.Done() before blocking operations |
| **Test failures** | Medium - tests may need context updates | Update tests to use cancellable contexts where appropriate |
| **Backward compatibility** | Low - internal API change only | No public API changes, all callers are internal |

## Recommended Approach

Based on the research findings, here's the high-level strategy:

### Phase 1: Update stream() Function

**Change signature to accept context:**
```go
func stream(ctx context.Context, r io.Reader, isErr bool, logs chan Line) {
    // ...
    sc := bufio.NewScanner(r)
    for sc.Scan() {
        select {
        case <-ctx.Done():
            return // Exit early on cancellation
        default:
            // Continue processing
        }
        // ... rest of loop
    }
}
```

### Phase 2: Use errgroup.WithContext

**In Options.Run() around line 1094:**
```go
// Create cancellable errgroup
g, ctx := errgroup.WithContext(ctx)

// Streaming goroutines now have access to cancellable context
g.Go(func() error {
    stream(ctx, stdout, false, o.Logs)
    return nil
})
g.Go(func() error {
    stream(ctx, stderr, true, o.Logs)
    return nil
})
```

### Phase 3: Update Process Wait Goroutine

**Replace the manual waitCh pattern:**
```go
// Instead of: waitCh := make(chan error, 1)
//            go func() { waitCh <- cmd.Wait() }()

// Use errgroup for the wait goroutine too:
g.Go(func() error {
    return cmd.Wait()
})

// Then select on both ctx.Done() and g.Wait() in a goroutine
```

### Implementation Considerations

1. **Context propagation**: The `ctx` parameter from `WithOptions.Run()` should be the parent context for the errgroup
2. **Graceful degradation**: If `ctx` is already cancelled when entering Run(), return early
3. **Backwards compatibility**: Keep the `Options.Run(ctx context.Context)` signature unchanged
4. **Testing**: Update tests to verify cancellation behavior under load

## Open Questions

1. **Should the process wait goroutine also be in the errgroup?**
   - Current: Separate `waitCh` pattern with manual goroutine
   - Alternative: Add to errgroup for unified error handling
   - **Recommendation**: Yes, move to errgroup for consistency

2. **What timeout should be used for graceful shutdown?**
   - Current: 2-second hardcoded timeout in select (line 1116)
   - Consider: Make this configurable via Options
   - **Recommendation**: Keep 2-second default for now, can be configurable later

3. **Should we cancel the errgroup context explicitly after process termination?**
   - The errgroup context is auto-cancelled when any goroutine returns an error
   - We may want to explicitly cancel it after cmd.Wait() completes
   - **Recommendation**: Let errgroup handle it naturally via goroutine completion

4. **How to test the race condition fix?**
   - Need a test that triggers cancellation while streams are active
   - Could use a slow subprocess that blocks on I/O
   - **Recommendation**: Add integration test with hanging subprocess

## Conclusion

The race condition is **real and critical** - the current implementation can deadlock when cancellation occurs because streaming goroutines have no cancellation mechanism. The fix is straightforward using `errgroup.WithContext()` and requires no external dependencies. The main challenge is ensuring the `stream()` function checks for context cancellation during blocking I/O operations.
