# Research: Make MaxBatchSize validation fail in strict mode

**Date**: 2026-01-19
**Item**: 016-make-maxbatchsize-validation-fail-in-strict-mode

## Research Question
Invalid configuration values are allowed with only a warning, potentially causing undefined behavior.

**Motivation:** Provides better configuration validation and catches errors early in strict environments.

**Technical constraints:**
- Check for APRD_STRICT environment variable
- Return error instead of warning when strict mode is enabled

**Signals:** priority: high

## Summary

The task requires implementing a strict mode validation for the MaxBatchSize configuration parameter. Currently, when MaxBatchSize is invalid (nil or <= 0), the system logs a warning and substitutes the default value (25). This allows the application to continue running, which may lead to undefined behavior or silent misconfigurations.

The implementation needs to:
1. Add a new environment variable constant `APRD_STRICT`
2. Modify the `LoadWithWarnings()` function to check for this environment variable
3. When `APRD_STRICT=1` is set, treat invalid MaxBatchSize as a fatal error instead of a warning
4. Ensure the error is properly surfaced to the user at startup

The current architecture uses a warning-based system where `LoadWithWarnings()` returns a `LoadResult` struct containing both the config and a list of warnings. The TUI initialization in `model.New()` calls `config.Load()` which internally calls `LoadWithWarnings()` and logs warnings but continues execution. To support strict mode, we need to either:
- Add an `Error` field to `LoadResult` and handle it in the TUI initialization, OR
- Return an error from `LoadWithWarnings()` and propagate it through the call chain

## Current State Analysis

### Existing Implementation

**Location**: `/Users/simo/Projects/autodev/internal/config/config.go:443-451`

Current MaxBatchSize validation code:
```go
// Validate and set default MaxBatchSize if still invalid
if c.BatchProcessing.MaxBatchSize == nil || *c.BatchProcessing.MaxBatchSize <= 0 {
    var currentValue int
    if c.BatchProcessing.MaxBatchSize != nil {
        currentValue = *c.BatchProcessing.MaxBatchSize
    }
    warnings = append(warnings, fmt.Sprintf("max_batch_size must be > 0, got %d; using default value %d", currentValue, DefaultMaxBatchSize))
    c.BatchProcessing.MaxBatchSize = intPtr(DefaultMaxBatchSize)
}
```

**Behavior**: When MaxBatchSize is invalid:
- Logs a warning message with the invalid value
- Substitutes the default value (25)
- Continues execution normally

**Call chain**:
1. `cmd/aprd/main.go:12` → `tui.New()`
2. `internal/tui/model.go:270` → `config.Load()`
3. `internal/config/config.go:292-297` → `LoadWithWarnings()`
4. Warnings are logged via `log.Printf()` and execution continues

### Environment Variable Pattern

**Location**: `/Users/simo/Projects/autodev/internal/config/config.go:16-26`

The codebase already has a pattern for environment variable constants:
```go
const (
    EnvExecutorPolicy       = "AUTO_PRD_EXECUTOR_POLICY"
    EnvExecutorImplement    = "AUTO_PRD_EXECUTOR_IMPLEMENT"
    EnvExecutorFix          = "AUTO_PRD_EXECUTOR_FIX"
    EnvExecutorPR           = "AUTO_PRD_EXECUTOR_PR"
    EnvExecutorReviewFix    = "AUTO_PRD_EXECUTOR_REVIEW_FIX"
    EnvAllowUnsafeExecution = "AUTO_PRD_ALLOW_UNSAFE_EXECUTION"
    EnvCodexTimeoutSeconds  = "AUTO_PRD_CODEX_TIMEOUT_SECONDS"
    EnvClaudeTimeoutSeconds = "AUTO_PRD_CLAUDE_TIMEOUT_SECONDS"
)
```

Note: The existing constants use `AUTO_PRD_` prefix, not `APRD_`. The task specification mentions `APRD_STRICT`, but we should follow the existing pattern with `AUTO_PRD_STRICT`.

### Key Files

- **`/Users/simo/Projects/autodev/internal/config/config.go`**
  - Lines 16-26: Environment variable constants
  - Lines 30-35: Default values including `DefaultMaxBatchSize = 25`
  - Lines 58-62: `BatchProcessing` struct with `MaxBatchSize` field
  - Lines 280-285: `LoadResult` struct definition (currently only has Config and Warnings)
  - Lines 300-454: `LoadWithWarnings()` function
  - Lines 443-451: MaxBatchSize validation logic

- **`/Users/simo/Projects/autodev/internal/tui/model.go`**
  - Lines 267-336: `New()` function that loads config
  - Line 270: `cfg := config.Load()` - loads config and logs warnings internally

- **`/Users/simo/Projects/autodev/cmd/aprd/main.go`**
  - Lines 11-24: Main function that initializes TUI
  - Lines 14-18: Error handling only for TUI runtime errors, not config errors

- **`/Users/simo/Projects/autodev/internal/config/config_test.go`**
  - Contains tests for config validation patterns
  - No existing tests for MaxBatchSize validation

- **`/Users/simo/Projects/autodev/internal/config/validation_test.go`**
  - Contains comprehensive validation tests
  - Tests for `ValidateInterField()` which validates runtime config constraints
  - No tests for load-time MaxBatchSize validation

## Technical Considerations

### Dependencies

**External Dependencies**: None - uses only Go standard library

**Internal Modules**:
- `internal/config` - Configuration loading and validation
- `internal/tui` - TUI model initialization
- `cmd/aprd` - Application entry point

### Patterns to Follow

**Environment Variable Naming**:
- Existing pattern: `AUTO_PRD_*` prefix for all environment variables
- Task specifies: `APRD_STRICT`
- **Recommendation**: Use `AUTO_PRD_STRICT` to match existing pattern

**Error Handling Pattern**:
- Current: `Load()` always returns a valid config, warnings are logged
- Current: `LoadWithWarnings()` returns `LoadResult{Config, Warnings}`
- Current: TUI's `New()` assumes config loading never fails
- **Consideration**: Need to decide between two approaches:
  1. Add `Error` field to `LoadResult` and handle in TUI
  2. Make `Load()` return `(Config, error)` and update all callers

**Validation Pattern**:
- The codebase has two types of validation:
  1. Load-time validation (in `LoadWithWarnings()`) - validates structural issues
  2. Runtime validation (in `ValidateInterField()`) - validates logical consistency
- MaxBatchSize validation is currently load-time
- Strict mode error should be load-time (fail fast)

**Constant Definition Pattern**:
- Environment variable constants are defined at package level
- Follow the pattern in lines 16-26 of config.go

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Breaking change for existing users** | High | Strict mode should be opt-in via environment variable. Default behavior (no strict mode) remains unchanged |
| **LoadResult struct change affects callers** | Medium | If adding Error field, ensure all callers handle it. If using separate error return, update all call sites |
| **TUI initialization assumes success** | Medium | Need to handle config load errors in `tui.New()` and propagate to `main()` for proper exit |
| **Inconsistent env var naming** | Low | Use `AUTO_PRD_STRICT` to match existing pattern, not `APRD_STRICT` as specified |
| **No existing tests for MaxBatchSize validation** | Medium | Add comprehensive tests for both strict and non-strict modes |
| **Other config validations might need similar strict mode** | Low | Focus on MaxBatchSize for this task, but design for future extensibility |

## Recommended Approach

Based on the research, here's the recommended implementation strategy:

### Design Decision: Error Handling Approach

**Recommended**: Add `Error` field to `LoadResult` rather than changing function signature.

**Rationale**:
1. Maintains backward compatibility - existing code that doesn't check for errors continues to work
2. Follows the existing `LoadResult` pattern (already has warnings)
3. Allows gradual migration - can check error in `main()` without changing `tui.New()`
4. Simpler than updating all call sites of `config.Load()`

### Implementation Steps

1. **Add environment variable constant** (config.go:26)
   ```go
   EnvStrict = "AUTO_PRD_STRICT"
   ```

2. **Add Error field to LoadResult** (config.go:280-285)
   ```go
   type LoadResult struct {
       Config   Config
       Warnings []string
       Error    error  // New field
   }
   ```

3. **Modify LoadWithWarnings()** (config.go:443-451)
   - Check for `AUTO_PRD_STRICT` environment variable
   - If set to "1" and MaxBatchSize is invalid:
     - Return LoadResult with Error field populated
     - Don't substitute default value
   - Otherwise, maintain current behavior (warning + default)

4. **Modify Load()** function (config.go:292-298)
   - Check if LoadResult has Error
   - If error exists, log it and exit (or return error)
   - Currently logs warnings, should also log fatal errors

5. **Handle error in main.go**
   - Check for config load errors before starting TUI
   - Log error message and exit with status 1

6. **Add comprehensive tests**
   - Test strict mode with invalid MaxBatchSize (should error)
   - Test strict mode with valid MaxBatchSize (should succeed)
   - Test non-strict mode with invalid MaxBatchSize (should warn + default)
   - Test non-strict mode with valid MaxBatchSize (should succeed)

### Code Structure

```go
// In LoadWithWarnings(), around line 443
strictMode := os.Getenv(EnvStrict) == "1"
if c.BatchProcessing.MaxBatchSize == nil || *c.BatchProcessing.MaxBatchSize <= 0 {
    if strictMode {
        var currentValue int
        if c.BatchProcessing.MaxBatchSize != nil {
            currentValue = *c.BatchProcessing.MaxBatchSize
        }
        return LoadResult{
            Config: Defaults(),
            Error: fmt.Errorf("max_batch_size must be > 0, got %d (strict mode enabled)", currentValue),
        }
    }
    // Non-strict mode: existing behavior
    var currentValue int
    if c.BatchProcessing.MaxBatchSize != nil {
        currentValue = *c.BatchProcessing.MaxBatchSize
    }
    warnings = append(warnings, fmt.Sprintf("max_batch_size must be > 0, got %d; using default value %d", currentValue, DefaultMaxBatchSize))
    c.BatchProcessing.MaxBatchSize = intPtr(DefaultMaxBatchSize)
}
```

### Testing Strategy

1. **Unit tests in config_test.go**:
   - `TestLoadWithWarningsStrictModeInvalid` - errors in strict mode
   - `TestLoadWithWarningsStrictModeValid` - succeeds in strict mode
   - `TestLoadWithWarningsNonStrictMode` - warns in non-strict mode

2. **Integration test**:
   - Test that TUI initialization fails with proper error message when strict mode is enabled and config is invalid

## Open Questions

1. **Environment variable name**: Should we use `APRD_STRICT` (as specified) or `AUTO_PRD_STRICT` (to match existing pattern)?
   - **Recommendation**: Use `AUTO_PRD_STRICT` for consistency

2. **Error handling approach**: Should we add an `Error` field to `LoadResult` or change `Load()` to return `(Config, error)`?
   - **Recommendation**: Add `Error` field to `LoadResult` for backward compatibility

3. **Exit behavior**: When strict mode triggers an error, should the application:
   - Log the error and call `os.Exit(1)` from within `Load()`?
   - Return an error and let `main()` handle the exit?
   - **Recommendation**: Return error and handle in `main()` for better testability

4. **Scope**: Should strict mode apply to all config validation issues or just MaxBatchSize?
   - **Recommendation**: Start with just MaxBatchSize as specified, but design for future extensibility (e.g., helper function `isStrictMode()`)

5. **Error message format**: What should the error message contain?
   - Current warning: "max_batch_size must be > 0, got %d; using default value %d"
   - Error should indicate: the problem, the invalid value, and that strict mode prevented auto-correction
   - **Recommendation**: "config validation failed (AUTO_PRD_STRICT enabled): max_batch_size must be > 0, got %d"
