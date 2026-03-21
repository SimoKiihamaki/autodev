# AD009: Resource Leak Analysis

## Severity
Low-Medium

## Location
Multiple files

## Summary
Comprehensive analysis of potential resource leaks in the codebase.

## Goroutine Leak Sources

### 1. Config Save Timeout (AD001)
**Location:** `internal/config/config.go:516-529`
**Severity:** Medium
**Status:** Documented in AD001

The goroutine spawned for file write can leak if timeout occurs.

### 2. Wait Channel Pattern (Safe)
**Location:** `internal/runner/runner.go:1143-1144`
```go
waitCh := make(chan error, 1)
go func() { waitCh <- cmd.Wait() }()
```
**Status:** Safe - Channel is buffered (size 1) and always read from in select.

### 3. Log Channel Closure (Safe)
**Location:** `internal/runner/runner.go:1113-1120`
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
**Status:** Safe - Uses sync.Once to prevent double-close panics.

### 4. Result Channel Closure (Safe)
**Location:** `internal/tui/run.go:165`
```go
close(resultCh)
```
**Status:** Safe - Closed in deferred cleanup, only by owning goroutine.

## File Handle Analysis

### 1. Stdout/Stderr Pipes (Safe)
**Location:** `internal/runner/runner.go:1092-1101`
```go
stdout, err := cmd.StdoutPipe()
defer func() { _ = stdout.Close() }()
stderr, err := cmd.StderrPipe()
defer func() { _ = stderr.Close() }()
```
**Status:** Safe - Deferred close with error ignored (acceptable for pipes).

### 2. Log File (Delegated to Python)
**Location:** `internal/tui/logging.go`
```go
// Note: The log file is not opened here; only the path is prepared.
// File writing is handled by the Python process (via --log-file argument)
```
**Status:** Safe - No Go file handle, Python owns the file.

### 3. Buffer Pool (Safe)
**Location:** `internal/runner/runner.go:24-29`
```go
var bufferPool = sync.Pool{
    New: func() interface{} {
        b := make([]byte, 0, 64*1024)
        return &b
    },
}
```
**Status:** Safe - Properly returned in deferred cleanup (line 1213).

## Channel Lifecycle

### Channels Created in TUI
| Channel | Created | Closed | Safe? |
|---------|---------|--------|-------|
| `logCh` | run.go:124 | runner.go:1117 | Yes |
| `runResult` | run.go:129 | run.go:165 | Yes |

### Channel Buffer Sizes
| Channel | Buffer | Rationale |
|---------|--------|-----------|
| `logCh` | 2048 (configurable) | Bound memory, handle bursts |
| `runResult` | 1 | Single error result |
| `waitCh` | 1 | Single wait result |
| `done` (config) | 1 | Single write result |

## Memory Leak Patterns Checked

### 1. Unbounded Slices
**Status:** All slices are bounded
- `logBuf` - Limited by UI.MaxLogLines (default 2000)
- `runFeedBuf` - Limited similarly
- Toast messages expire after TTL

### 2. Timer/Ticker Leaks
**Status:** No ticker leaks found
- Uses `time.After()` in select (auto-cleanup)
- No long-running tickers without Stop()

### 3. Context Cancellation
**Status:** Properly handled
```go
ctx, cancel := context.WithCancel(context.Background())
m.cancel = cancel  // Stored for cleanup
```

## Test Coverage for Leaks

### Existing Tests
- `TestLogBufferMemoryLeakFix` in `log_buffer_test.go`
- Integration tests in `run_integration_test.go`

### Missing Tests
```go
func TestGoroutineLeakOnConfigTimeout(t *testing.T)
func TestNoLeakOnRunnerCancellation(t *testing.T)
func TestChannelCleanupOnError(t *testing.T)
```

## Recommendations

### High Priority
1. Fix AD001 (config save goroutine leak)

### Medium Priority
2. Add goroutine leak tests using `runtime.NumGoroutine()`
3. Add integration test that runs 100+ iterations and checks for leaks

### Low Priority
4. Consider using `goleak` package for CI leak detection
```go
func TestMain(m *testing.M) {
    goleak.VerifyTestMain(m)
}
```

## Conclusion
The codebase is **generally well-managed** for resources. The only confirmed leak is AD001 (config save timeout). All other patterns follow best practices for:
- Channel closure with sync.Once
- Context cancellation
- File handle cleanup
- Buffer pool management

## Related Issues
- AD001 - Config save goroutine leak (primary issue)
