# Fix race condition in process cancellation Implementation Plan

## Overview
This plan addresses a **critical race condition** in the process cancellation logic within the subprocess runner. The current implementation uses an `errgroup.Group` without tying it to a cancellation context, which creates a deadlock scenario where streaming goroutines cannot be cancelled and block indefinitely on I/O operations.

**Impact**: High-priority fix that prevents deadlocks during process cancellation, particularly when the TUI user cancels a running operation or when the system is under load.

## Current State Analysis

### What Exists Now
**Location**: `internal/runner/runner.go:1041-1175`

The `Options.Run()` method manages subprocess execution with concurrent operations:
- **Line 1094**: Creates `new(errgroup.Group)` without context binding
- **Lines 1095-1102**: Spawns two streaming goroutines that NEVER check `ctx.Done()`
- **Line 1105**: Creates separate `waitCh` for process completion (manual goroutine, not in errgroup)
- **Lines 1107-1134**: Select block that handles cancellation via `ctx.Done()`

The `stream()` function (lines 1140-1175) performs blocking I/O with `bufio.Scanner.Scan()` but **never checks context cancellation**. When `ctx.Done()` fires:
1. Process is interrupted/killed (lines 1110-1120)
2. Code calls `g.Wait()` (line 1122 or 1127)
3. **RACE CONDITION**: If stream goroutines are blocked on `sc.Scan()`, `g.Wait()` blocks indefinitely

### What's Missing
1. **No errgroup context**: The errgroup is created without `errgroup.WithContext()`
2. **No context in stream()**: The stream function signature lacks a context parameter
3. **No cancellation checks**: The scanning loop never checks `ctx.Done()`
4. **Inconsistent goroutine management**: Process wait uses manual goroutine, streams use errgroup

### Key Constraints
- **No new dependencies**: Fix only uses existing `golang.org/x/sync/errgroup` and `context`
- **Backward compatible**: The `Options.Run(ctx)` signature must remain unchanged
- **Platform support**: Must work on both Unix (proc_unix.go) and Windows (proc_windows.go)
- **Test coverage**: Tests use `context.Background()` (non-cancellable) and must be updated
- **Grace period**: Current 2-second graceful shutdown timeout should be preserved

## Desired End State

### Specification
All goroutines spawned during process execution must respect context cancellation and exit cleanly:

1. **errgroup.WithContext**: The errgroup is bound to a cancellable context
2. **Context-aware stream()**: The stream function accepts a context and checks for cancellation
3. **Unified goroutine management**: All three goroutines (stdout, stderr, wait) are in the errgroup
4. **Clean shutdown**: When context is cancelled, all goroutines exit promptly without deadlocking

### Verification
- **Race detector**: `make test-go-race` passes without warnings
- **Manual test**: Cancel a running process in TUI (Ctrl+C or 'q' key) - process exits cleanly
- **Integration test**: Verify cancellation works while subprocess is actively streaming output
- **Code coverage**: All new code paths are covered by tests

## Key Discoveries

### Important Findings
1. **Line 1093 comment is misleading**: The code says "The errgroup context is not used here because we manage cancellation separately" - but cancellation is only managed for the process wait, NOT the streaming goroutines
2. **Two call sites for stream()**: Both at lines 1096 and 1100 in `runner.go`
3. **Three test files**: Tests at `internal/runner/runner_test.go`, `internal/tui/run_integration_test.go:66`, and `cmd/api/main.go:26`
4. **Platform-specific code**: Process group setup differs by platform (proc_unix.go vs proc_windows.go)
5. **Buffer pool**: Line 1149 uses `bufferPool.Get()` for memory efficiency - must be preserved
6. **Nil channel handling**: Lines 1141-1145 show `stream()` handles `nil` logs channel for test scenarios

### Pattern to Follow
From `cmd/api/main.go:26`:
```go
ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
defer stop()
```
This shows the project already uses context cancellation for graceful shutdown.

### Constraint to Work Within
The stream function has a specific pattern for handling slow consumers (lines 1157-1171). Any context checking must be integrated without disrupting this backpressure mechanism.

## What We're NOT Doing

- **Changing the public API**: `Options.Run(ctx context.Context)` signature remains unchanged
- **Adding configuration**: Not making the 2-second timeout configurable (deferred to future work)
- **Rewriting the stream logic**: Only adding context cancellation, not changing the backpressure/dropping behavior
- **Modifying other subsystems**: API server and TUI are callers, not part of this fix
- **Adding new dependencies**: Using only existing Go standard library and errgroup
- **Changing buffer pool behavior**: Memory optimization via bufferPool must be preserved

## Implementation Approach

### High-Level Strategy
The fix uses `errgroup.WithContext()` to create a cancellable errgroup, then:
1. Add context parameter to `stream()` function
2. Check `ctx.Done()` in the scanning loop before blocking operations
3. Move process wait goroutine into the errgroup for unified error handling
4. Update tests to use cancellable contexts where appropriate

**Reasoning**: This approach ensures all goroutines receive the cancellation signal simultaneously and can exit cleanly, preventing deadlocks.

---

## Phase 1: Update stream() Function Signature

### Overview
Add a context parameter to the `stream()` function and check for cancellation in the scanning loop.

### Changes Required

#### 1. Update stream() function
**File**: `internal/runner/runner.go`
**Lines**: 1140-1175

**Current signature:**
```go
func stream(r io.Reader, isErr bool, logs chan Line) {
```

**New signature:**
```go
func stream(ctx context.Context, r io.Reader, isErr bool, logs chan Line) {
```

**Implementation change at line 1158:**
```go
for sc.Scan() {
    // Check for context cancellation before processing each line
    select {
    case <-ctx.Done():
        return
    default:
        // Continue processing
    }

    line := Line{Time: time.Now(), Text: sc.Text(), Err: isErr}
    // ... rest of loop unchanged
}
```

**Rationale**: The `select` statement with `ctx.Done()` allows the goroutine to exit immediately when the context is cancelled, preventing blocking on the next `sc.Scan()` call. The `default` case ensures normal processing continues when not cancelled.

#### 2. Update stream() call sites
**File**: `internal/runner/runner.go`
**Lines**: 1096 and 1100

**Current calls:**
```go
g.Go(func() error {
    stream(stdout, false, o.Logs)
    return nil
})
g.Go(func() error {
    stream(stderr, true, o.Logs)
    return nil
})
```

**Updated calls** (after errgroup.WithContext is added in Phase 2):
```go
g.Go(func() error {
    stream(ctx, stdout, false, o.Logs)
    return nil
})
g.Go(func() error {
    stream(ctx, stderr, true, o.Logs)
    return nil
})
```

**Note**: These calls will be updated in Phase 2 when `errgroup.WithContext()` is introduced, but they're listed here for completeness.

### Success Criteria

#### Automated Verification:
- [ ] Tests pass: `make test-go`
- [ ] Type checking passes: `go build ./...`
- [ ] No new compiler warnings

#### Manual Verification:
- [ ] Review diff to ensure context parameter is properly propagated
- [ ] Verify all stream() call sites are updated (2 locations)
- [ ] Confirm context check doesn't interfere with backpressure logic

**Note**: Complete all automated verification, then pause for manual confirmation before proceeding to next phase.

---

## Phase 2: Use errgroup.WithContext

### Overview
Replace the plain `errgroup.Group` with `errgroup.WithContext()` to create a cancellable errgroup.

### Changes Required

#### 1. Replace errgroup creation
**File**: `internal/runner/runner.go`
**Line**: 1094

**Current code:**
```go
// Use errgroup for better error propagation and cleaner goroutine management.
// The errgroup context is not used here because we manage cancellation separately.
g := new(errgroup.Group)
```

**New code:**
```go
// Use errgroup with context for proper cancellation propagation.
// All goroutines in the group will receive the cancellation signal.
g, ctx := errgroup.WithContext(ctx)
```

**Important**: The `ctx` returned by `errgroup.WithContext()` shadows the parameter `ctx`, which is intentional - all goroutines should use the errgroup's context which is cancelled when any goroutine errors.

#### 2. Update comment about cancellation
**File**: `internal/runner/runner.go`
**Line**: 1092-1093 (above the errgroup creation)

**Current comment:**
```go
// Use errgroup for better error propagation and cleaner goroutine management.
// The errgroup context is not used here because we manage cancellation separately.
```

**New comment:**
```go
// Use errgroup with context for unified cancellation handling.
// The errgroup context is tied to the parent context and is cancelled when
// any goroutine returns an error, ensuring all goroutines exit cleanly.
```

#### 3. Update stream() goroutines to pass ctx
**File**: `internal/runner/runner.go`
**Lines**: 1095-1102

**Current code:**
```go
g.Go(func() error {
    stream(stdout, false, o.Logs)
    return nil
})
g.Go(func() error {
    stream(stderr, true, o.Logs)
    return nil
})
```

**New code:**
```go
g.Go(func() error {
    stream(ctx, stdout, false, o.Logs)
    return nil
})
g.Go(func() error {
    stream(ctx, stderr, true, o.Logs)
    return nil
})
```

### Success Criteria

#### Automated Verification:
- [ ] Tests pass: `make test-go`
- [ ] Race detector passes: `make test-go-race`
- [ ] Build succeeds: `make build`
- [ ] No lint errors: `make lint-go`

#### Manual Verification:
- [ ] Verify errgroup context shadows the parent context (correct Go pattern)
- [ ] Confirm all goroutines now use the cancellable context
- [ ] Test cancellation in TUI by starting a run and pressing 'q' to cancel

**Note**: Complete all automated verification, then pause for manual confirmation before proceeding to next phase.

---

## Phase 3: Move Process Wait Goroutine to errgroup

### Overview
Replace the manual `waitCh` pattern with an errgroup goroutine for unified error handling.

### Changes Required

#### 1. Replace waitCh pattern
**File**: `internal/runner/runner.go`
**Lines**: 1104-1105 and 1107-1134

**Current code:**
```go
waitCh := make(chan error, 1)
go func() { waitCh <- cmd.Wait() }()

select {
case <-ctx.Done():
    // Graceful stop logic
    if sigErr := interruptProcess(cmd); sigErr != nil { /* ... */ }
    select {
    case <-waitCh:
        // Process exited
    case <-time.After(2 * time.Second):
        if killErr := forceKillProcess(cmd); killErr != nil { /* ... */ }
        <-waitCh
    }
    _ = g.Wait() // Wait for stream goroutines to complete
    sendLine(o.Logs, Line{Time: time.Now(), Text: "process finished", Err: false})
    closeLogs()
    return fmt.Errorf("run canceled: %w", ctx.Err())
case err := <-waitCh:
    _ = g.Wait() // Wait for stream goroutines to complete
    sendLine(o.Logs, Line{Time: time.Now(), Text: "process finished", Err: false})
    closeLogs()
    if err != nil {
        return fmt.Errorf("runner exited with error: %w", err)
    }
    return nil
}
```

**New code:**
```go
// Add the wait goroutine to the errgroup
g.Go(func() error {
    return cmd.Wait()
})

// Start a goroutine to wait for errgroup completion or context cancellation
errCh := make(chan error, 1)
go func() {
    errCh <- g.Wait()
}()

select {
case <-ctx.Done():
    // Graceful stop: send Interrupt, then wait; kill on timeout to ensure pipes close and streams finish.
    if sigErr := interruptProcess(cmd); sigErr != nil {
        sendLine(o.Logs, Line{Time: time.Now(), Text: "failed to send interrupt: " + sigErr.Error(), Err: true})
    }
    // Wait for errgroup to finish (all goroutines including cmd.Wait will exit)
    select {
    case <-errCh:
        // All goroutines finished
    case <-time.After(2 * time.Second):
        if killErr := forceKillProcess(cmd); killErr != nil {
            sendLine(o.Logs, Line{Time: time.Now(), Text: "failed to kill process: " + killErr.Error(), Err: true})
        }
        <-errCh
    }
    sendLine(o.Logs, Line{Time: time.Now(), Text: "process finished", Err: false})
    closeLogs()
    return fmt.Errorf("run canceled: %w", ctx.Err())
case err := <-errCh:
    sendLine(o.Logs, Line{Time: time.Now(), Text: "process finished", Err: false})
    closeLogs()
    if err != nil {
        return fmt.Errorf("runner exited with error: %w", err)
    }
    return nil
}
```

**Rationale**: This unifies all three goroutines (stdout, stderr, wait) under the errgroup. The `errCh` pattern allows us to wait for the entire group to finish while still respecting the parent context's cancellation signal.

### Success Criteria

#### Automated Verification:
- [ ] Tests pass: `make test-go`
- [ ] Race detector passes: `make test-go-race`
- [ ] Build succeeds: `make build`

#### Manual Verification:
- [ ] Verify process completes normally (no cancellation)
- [ ] Verify process cancels cleanly when context is cancelled
- [ ] Verify error handling works when process exits with error
- [ ] Confirm no goroutine leaks (all goroutines exit in both success and error cases)

**Note**: Complete all automated verification, then pause for manual confirmation before proceeding to next phase.

---

## Phase 4: Update Tests

### Overview
Update tests that call `stream()` or test `Options.Run()` to use cancellable contexts where appropriate.

### Changes Required

#### 1. Update stream() tests
**File**: `internal/runner/runner_test.go`

**Tests to update:**
- `TestStreamWithSlowConsumer` (line 279)
- `TestStreamWithNilChannel` (line 356) - uses `context.Background()`, can keep nil
- `TestStreamWithErrorInReader` (line 369)

**Example update for TestStreamWithSlowConsumer:**
```go
// Add context parameter
ctx := context.Background()

// Update the goroutine
go func() {
    defer wg.Done()
    stream(ctx, reader, false, logs)  // Add ctx parameter
}()
```

#### 2. Add cancellation test
**File**: `internal/runner/runner_test.go` (new test)

**New test:**
```go
func TestOptionsRunCancellation(t *testing.T) {
    t.Parallel()

    cfg := &config.Config{...} // Minimal config

    logs := make(chan Line, 64)
    opts := Options{
        Config:      cfg,
        PRDPath:     prd,
        Logs:        logs,
        LogFilePath: logFile,
    }

    // Create a cancellable context
    ctx, cancel := context.WithCancel(context.Background())

    errCh := make(chan error, 1)
    go func() {
        errCh <- opts.Run(ctx)
    }()

    // Wait a bit for the process to start
    time.Sleep(100 * time.Millisecond)

    // Cancel the context
    cancel()

    // Should receive cancellation error (not hang)
    err := <-errCh
    if err == nil {
        t.Error("expected error on cancellation")
    }
    if !errors.Is(err, context.Canceled) {
        t.Errorf("expected context.Canceled, got %v", err)
    }

    // Drain logs
    for range logs {
    }
}
```

#### 3. Update integration test if needed
**File**: `internal/tui/run_integration_test.go:66`

**Current code:**
```go
ctx, cancel := context.WithCancel(context.Background())
defer cancel()
```

This test is already using a cancellable context - no change needed.

### Success Criteria

#### Automated Verification:
- [ ] All tests pass: `make test-go`
- [ ] Race detector passes: `make test-go-race`
- [ ] New cancellation test covers the race condition fix

#### Manual Verification:
- [ ] Run cancellation test multiple times to ensure it's reliable
- [ ] Verify test actually triggers the cancellation path
- [ ] Confirm no flakiness in the test

**Note**: Complete all automated verification, then pause for manual confirmation before proceeding.

---

## Testing Strategy

### Unit Tests
- **TestStreamWithContext**: Verify stream function exits when context is cancelled mid-scan
- **TestOptionsRunCancellation**: Verify Options.Run handles cancellation cleanly (new test)
- **Existing tests**: Update TestStreamWithSlowConsumer, TestStreamWithNilChannel, TestStreamWithErrorInReader

### Integration Tests
- **TUI cancellation test**: Start a run in TUI, cancel with 'q' key, verify clean exit
- **API server shutdown test**: Send SIGINT to API server while subprocess is running

### Manual Testing Steps

#### 1. Normal Completion
```bash
# Build the project
make build

# Run a simple PRD that completes successfully
./bin/aprd run --prd examples/simple.prd
# Should complete without errors
```

#### 2. Cancellation During Active Streaming
```bash
# Start a long-running process
./bin/aprd run --prd examples/long-running.prd

# While it's running, press Ctrl+C or 'q' to cancel
# Expected: Process exits cleanly, no hang, no panic
```

#### 3. Race Detector
```bash
# Run tests with race detector
make test-go-race

# Expected: No race condition warnings
```

#### 4. Goroutine Leak Check
```bash
# Run with goroutine leak detection (requires test modification)
go test -run TestOptionsRunCancellation -timeout 30s
# Expected: All goroutines exit after test completes
```

## Migration Notes

### Backward Compatibility
- **Public API unchanged**: `Options.Run(ctx)` signature remains the same
- **Callers unaffected**: TUI and API server continue to work without modifications
- **Test compatibility**: Tests using `context.Background()` still work (non-cancellable)

### Rollback Strategy
If issues arise:
1. Revert changes to `stream()` function signature
2. Revert errgroup usage to original pattern
3. Keep tests as they don't affect production code

### Performance Impact
- **Minimal overhead**: Context checking adds negligible CPU cost
- **Memory**: No additional allocations (context already exists)
- **Cancellation speed**: Faster goroutine shutdown due to explicit cancellation

## References
- Research: `/Users/simo/Projects/autodev/.wreckit/items/008-fix-race-condition-in-process-cancellation/research.md`
- Code location: `internal/runner/runner.go:1041-1175`
- Stream function: `internal/runner/runner.go:1140-1175`
- TUI integration: `internal/tui/run.go:132-168`
- Tests: `internal/runner/runner_test.go`
- Build system: `/Users/simo/Projects/autodev/Makefile`
