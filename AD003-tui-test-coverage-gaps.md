# AD003: TUI Test Coverage Gaps (50.6%)

## Severity
Medium

## Location
`internal/tui/` - 50.6% coverage

## Current State
The TUI package has moderate coverage but significant gaps remain. Key untested areas:

### Files with Test Coverage
- `view_test.go` (1104 LOC) - Good coverage
- `update_test.go` (811 LOC) - Good coverage
- `keys_test.go` (496 LOC) - Good coverage
- `run_feed_test.go` (447 LOC) - Good coverage
- Various smaller test files

### Large Files Needing Tests
| File | Lines | Notes |
|------|-------|-------|
| `model.go` | 676 | Model struct, initialization, cleanup |
| `run.go` | 458 | Run execution, channel management |
| `inputs.go` | 423 | Input handling, validation |
| `view_run.go` | 337 | Run tab rendering |
| `keys_settings.go` | 335 | Settings key handling |
| `components.go` | 334 | UI component rendering |
| `run_feed.go` | 316 | Live feed rendering |
| `view_progress.go` | 303 | Progress tab rendering |

### Untested Areas

#### 1. Channel Lifecycle (run.go)
```go
// Channel creation - lines 124, 129
m.logCh = make(chan runner.Line, bufferSize)
m.runResult = make(chan error, 1)

// Goroutine spawn - line 144
go func(ctx context.Context, opts runner.Options, ...) {
    // Needs integration test coverage
}
```

#### 2. Cleanup Logic (model.go:33-40)
```go
func (m model) cleanup() {
    if m.cancel != nil {
        m.cancel()
    }
    m.closeLogFile("cleanup")
}
```

#### 3. Preflight Checks (run.go:173-212)
- Python executable validation
- Script path validation
- PRD file validation

#### 4. Error Recovery (run.go:147-166)
- Panic recovery in goroutine
- safeSendCritical usage

### Proposed Tests

```go
// run_integration_test.go - Expand existing
func TestRunCancellationCleansUpProperly(t *testing.T)
func TestRunPanicRecovery(t *testing.T)
func TestRunChannelClosureOnError(t *testing.T)

// model_test.go - New file
func TestCleanupCancelsContext(t *testing.T)
func TestCleanupClosesLogFile(t *testing.T)

// inputs_test.go - New file
func TestNumericInputValidation(t *testing.T)
func TestEmptyInputHandling(t *testing.T)

// preflight_test.go - New file
func TestPreflightMissingPython(t *testing.T)
func TestPreflightMissingScript(t *testing.T)
func TestPreflightInvalidPRD(t *testing.T)
```

## Related Files
- `internal/tui/run_integration_test.go` (exists, needs expansion)
- `internal/tui/model_test.go` (exists)
- `internal/runner/runner_test.go` (77.1% coverage, good reference)
