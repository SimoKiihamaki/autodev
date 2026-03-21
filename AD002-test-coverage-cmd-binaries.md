# AD002: Zero Test Coverage for cmd/api and cmd/aprd

## Severity
Medium

## Location
- `cmd/api/main.go` - 0.0% coverage
- `cmd/aprd/main.go` - 0.0% coverage

## Current Coverage
```
github.com/SimoKiihamaki/autodev/cmd/api      0.0%
github.com/SimoKiihamaki/autodev/cmd/aprd     0.0%
github.com/SimoKiihamaki/autodev/internal/api 95.7%
github.com/SimoKiihamaki/autodev/internal/config 77.2%
github.com/SimoKiihamaki/autodev/internal/runner 77.1%
github.com/SimoKiihamaki/autodev/internal/tui 50.6%
github.com/SimoKiihamaki/autodev/internal/utils 100.0%
```

## Issue
The main entry points have no test coverage despite being production binaries. These contain:
- Flag parsing logic
- Configuration loading
- Signal handling
- Error reporting
- Graceful shutdown

## Test Gaps

### cmd/api/main.go
- Health endpoint startup
- Graceful shutdown handling
- Environment variable configuration
- Error reporting on startup failure

### cmd/aprd/main.go
- TUI startup with various flag combinations
- Config loading failures
- CleanupFinalModel invocation
- Signal handling (Ctrl+C)

## Proposed Tests

### cmd/api/main_test.go (exists but needs expansion)
```go
func TestMainGracefulShutdown(t *testing.T) {
    // Test that SIGTERM causes graceful shutdown
}

func TestMainConfigFromEnv(t *testing.T) {
    // Test AUTO_PRD_* env vars are picked up
}

func TestMainStartupFailure(t *testing.T) {
    // Test error reporting when port is in use
}
```

### cmd/aprd/main_test.go (new file needed)
```go
func TestAprdStartupWithFlags(t *testing.T) {
    // Test --help, --version flags
}

func TestAprdCleanupOnExit(t *testing.T) {
    // Test CleanupFinalModel is called
}

func TestAprdSignalHandling(t *testing.T) {
    // Test SIGINT handling
}
```

## Priority
Medium - Entry points are critical but have minimal logic (delegate to internal packages)

## Related
- `internal/api/server_test.go` has good coverage (part of 95.7%)
- `internal/tui/*_test.go` files have good coverage of core logic
