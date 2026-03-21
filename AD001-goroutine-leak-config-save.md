# AD001: Goroutine Leak in Config Save with Timeout

## Severity
Medium

## Location
`internal/config/config.go` lines 516-529

## Issue
The `saveWithTimeout` function spawns a goroutine to write the config file, but if the timeout is triggered, the goroutine continues running indefinitely. The channel `done` has buffer size 1, so when timeout occurs:
1. The select statement returns early with a timeout error
2. The goroutine is still blocked waiting to write to `done` channel
3. Since no one is reading from `done`, the goroutine leaks

## Code Snippet
```go
func saveWithTimeout(c *Config, p string, timeout time.Duration) error {
    // ...
    done := make(chan error, 1)
    go func() {
        done <- os.WriteFile(p, b, 0o600)  // BLOCKS if timeout triggers first
    }()

    select {
    case err := <-done:
        return err
    case <-time.After(timeout):
        return errors.New("config save timed out after " + timeout.String())
    }
}
```

## Impact
- Memory leak in long-running TUI sessions
- Goroutine count grows if config saves timeout repeatedly
- Potential file descriptor leak if write is slow

## Proposed Fix
```go
func saveWithTimeout(c *Config, p string, timeout time.Duration) error {
    // ...
    done := make(chan error, 1)
    go func() {
        done <- os.WriteFile(p, b, 0o600)
    }()

    select {
    case err := <-done:
        return err
    case <-time.After(timeout):
        // Drain the channel in a separate goroutine to prevent leak
        go func() { <-done }()
        return errors.New("config save timed out after " + timeout.String())
    }
}
```

Alternative: Use context with cancellation for cleaner shutdown.

## Test Case Needed
```go
func TestSaveWithTimeoutGoroutineLeak(t *testing.T) {
    // Create a config that will take longer than timeout to write
    // Verify goroutine count before and after
    // Ensure no goroutine leak
}
```

## Related Files
- `internal/config/config.go`
- `internal/config/config_test.go`
