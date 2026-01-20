# Make MaxBatchSize validation fail in strict mode Implementation Plan

## Overview
Implement a strict mode for configuration validation that causes invalid `MaxBatchSize` values to fail fast at startup instead of being auto-corrected with a warning. When `AUTO_PRD_STRICT=1` is set, the application will exit with a clear error message if `MaxBatchSize` is invalid (nil or <= 0), preventing silent misconfigurations that could lead to undefined behavior.

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

**Current behavior**: When MaxBatchSize is invalid:
1. Logs a warning message with the invalid value
2. Substitutes the default value (25)
3. Continues execution normally
4. Application never fails, regardless of configuration quality

**Call chain analysis**:
1. `cmd/aprd/main.go:12` → `tui.New()`
2. `internal/tui/model.go:270` → `config.Load()`
3. `internal/config/config.go:292-297` → `LoadWithWarnings()`
4. Warnings are logged via `log.Printf()` and execution continues

**Key constraint**: The `Load()` function never returns an error - it always returns a valid config. This is documented behavior that consumers rely on.

### Environment Variable Pattern

**Location**: `/Users/simo/Projects/autodev/internal/config/config.go:16-26`

All environment variables use `AUTO_PRD_` prefix:
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

**Decision**: Use `AUTO_PRD_STRICT` to match existing pattern, not `APRD_STRICT` as specified in task description.

## Desired End State

When `AUTO_PRD_STRICT=1` is set in the environment:
1. Invalid MaxBatchSize (nil or <= 0) causes application to exit with error
2. Error message clearly indicates the problem and mentions strict mode
3. Default behavior (no strict mode) remains unchanged - warning + auto-correction
4. Error is surfaced before TUI initialization to prevent partial startup

**Success criteria**:
- [ ] Setting `AUTO_PRD_STRICT=1` with invalid MaxBatchSize exits with status 1
- [ ] Error message includes: field name, invalid value, and strict mode indication
- [ ] Setting `AUTO_PRD_STRICT=1` with valid MaxBatchSize works normally
- [ ] Not setting `AUTO_PRD_STRICT` maintains current behavior (warning + default)
- [ ] All existing tests pass
- [ ] New tests cover strict mode scenarios

### Key Discoveries:

1. **LoadResult struct** (config.go:280-285) already has a `Warnings []string` field but no `Error` field. Adding an `Error` field is the cleanest approach to maintain backward compatibility.

2. **config.Load()** (config.go:292-298) logs warnings internally and never errors. This function is called by `tui.New()` which assumes it always succeeds. We need to add error handling to `Load()`.

3. **main.go** (lines 11-24) only handles TUI runtime errors. Config load errors need to be checked before TUI initialization.

4. **No existing tests** for MaxBatchSize validation. The config_test.go file only has tests for Clone(), Equal(), and git branch validation. We need to add comprehensive tests for strict mode.

5. **intPtr() helper function** (config.go:726-728) is available for creating integer pointers, used throughout the codebase.

## What We're NOT Doing

- **NOT changing existing default behavior**: Without `AUTO_PRD_STRICT`, the application continues to use warnings and defaults
- **NOT implementing strict mode for other config validations**: Only MaxBatchSize is in scope
- **NOT changing the config file format**: This is purely a runtime behavior change
- **NOT creating a migration**: No config schema changes
- **NOT implementing a general validation framework**: Strict mode is specific to MaxBatchSize
- **NOT exposing strict mode in the TUI**: This is a deployment/environment-level setting only

## Implementation Approach

### Design Decision: Error Handling Approach

**Approach**: Add `Error` field to `LoadResult` struct and check it in `main()` before TUI initialization.

**Rationale**:
1. **Backward compatibility**: Existing code that calls `Load()` or `LoadWithWarnings()` and doesn't check for errors continues to work
2. **Follows existing patterns**: `LoadResult` already has a `Warnings` field; `Error` is a natural extension
3. **Minimal changes**: Only need to modify `LoadWithWarnings()`, `Load()`, and `main()`
4. **Testable**: Error can be returned and checked in unit tests without requiring `os.Exit()`
5. **Future-proof**: Pattern can be extended to other validations if needed

### Implementation Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ main.go                                                      │
│  1. Check if config.Load() returned an error                │
│  2. If error: log fatal and exit(1)                         │
│  3. Otherwise: proceed with tui.New()                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ config.Load()                                                │
│  1. Call LoadWithWarnings()                                 │
│  2. If LoadResult.Error is set: log it and return error     │
│  3. Otherwise: log warnings and return Config               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ config.LoadWithWarnings()                                   │
│  1. Load config from file                                   │
│  2. Check for AUTO_PRD_STRICT env var                       │
│  3. If strict mode and MaxBatchSize invalid:                │
│     - Return LoadResult with Error field set                │
│  4. Otherwise:                                               │
│     - Add warning and substitute default (current behavior) │
│  5. Return LoadResult                                       │
└─────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Add Environment Variable Constant

### Overview
Add the `AUTO_PRD_STRICT` environment variable constant to match existing patterns.

### Changes Required:

#### 1. internal/config/config.go
**File**: `/Users/simo/Projects/autodev/internal/config/config.go`
**Lines**: 26 (after existing env constants)

**Add**:
```go
EnvStrict = "AUTO_PRD_STRICT"
```

**Before**:
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

**After**:
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
    EnvStrict               = "AUTO_PRD_STRICT"
)
```

### Success Criteria:

#### Automated Verification:
- [ ] Code compiles: `go build ./internal/config`
- [ ] No new warnings from `go vet`
- [ ] Constant is accessible via `config.EnvStrict`

**Note**: This phase is simple and safe - just adding a constant.

---

## Phase 2: Add Error Field to LoadResult

### Overview
Modify the `LoadResult` struct to include an `Error` field for validation failures.

### Changes Required:

#### 1. internal/config/config.go
**File**: `/Users/simo/Projects/autodev/internal/config/config.go`
**Lines**: 280-285

**Before**:
```go
// LoadResult holds the result of loading configuration, including any warnings
// that occurred during loading (e.g., partial parse failures).
type LoadResult struct {
    Config   Config
    Warnings []string
}
```

**After**:
```go
// LoadResult holds the result of loading configuration, including any warnings
// that occurred during loading (e.g., partial parse failures).
type LoadResult struct {
    Config   Config
    Warnings []string
    Error    error // Validation error when strict mode is enabled
}
```

### Success Criteria:

#### Automated Verification:
- [ ] Code compiles: `go build ./internal/config`
- [ ] All existing tests pass: `go test ./internal/config`
- [ ] No new warnings from `go vet`

**Note**: Adding a field to a struct is backward compatible in Go - existing code that doesn't use the field continues to work.

---

## Phase 3: Implement Strict Mode Validation Logic

### Overview
Modify `LoadWithWarnings()` to check for strict mode and return an error when MaxBatchSize is invalid in strict mode.

### Changes Required:

#### 1. internal/config/config.go
**File**: `/Users/simo/Projects/autodev/internal/config/config.go`
**Lines**: 443-451

**Before**:
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

**After**:
```go
// Validate and set default MaxBatchSize if still invalid
if c.BatchProcessing.MaxBatchSize == nil || *c.BatchProcessing.MaxBatchSize <= 0 {
    var currentValue int
    if c.BatchProcessing.MaxBatchSize != nil {
        currentValue = *c.BatchProcessing.MaxBatchSize
    }

    // Check if strict mode is enabled
    if os.Getenv(EnvStrict) == "1" {
        // Strict mode: return error instead of warning
        return LoadResult{
            Config: Defaults(),
            Error: fmt.Errorf("config validation failed (AUTO_PRD_STRICT enabled): max_batch_size must be > 0, got %d", currentValue),
        }
    }

    // Non-strict mode: warning + auto-correction (existing behavior)
    warnings = append(warnings, fmt.Sprintf("max_batch_size must be > 0, got %d; using default value %d", currentValue, DefaultMaxBatchSize))
    c.BatchProcessing.MaxBatchSize = intPtr(DefaultMaxBatchSize)
}
```

**Important note**: Keep the existing `return LoadResult{Config: c, Warnings: warnings}` at line 453 unchanged. The early return in strict mode bypasses the normal return.

### Success Criteria:

#### Automated Verification:
- [ ] Code compiles: `go build ./internal/config`
- [ ] All existing tests pass: `go test ./internal/config`
- [ ] Linting passes: `gofmt -w internal/config/config.go`

#### Manual Verification:
- [ ] Test strict mode with invalid MaxBatchSize in config file
- [ ] Test strict mode with valid MaxBatchSize (should work)
- [ ] Test non-strict mode (default) with invalid MaxBatchSize (should warn)

**Note**: Phase 3 doesn't wire up error handling yet, so errors will be ignored. This is intentional - we'll test the logic in Phase 5 before connecting it.

---

## Phase 4: Modify Load() to Handle Errors

### Overview
Update `Load()` to check if `LoadResult.Error` is set and handle it appropriately.

### Changes Required:

#### 1. internal/config/config.go
**File**: `/Users/simo/Projects/autodev/internal/config/config.go`
**Lines**: 292-298

**Before**:
```go
// Load reads the configuration from disk, falling back to defaults on error.
// For corrupt configs, it logs a warning and returns defaults. This function
// always returns a valid Config and never returns an error; warnings are
// logged internally. Use LoadWithWarnings() if you need access to warnings
// for UI display or other handling.
func Load() Config {
    result := LoadWithWarnings()
    for _, warning := range result.Warnings {
        log.Printf("Warning: %s", warning)
    }
    return result.Config
}
```

**After**:
```go
// Load reads the configuration from disk, falling back to defaults on error.
// For corrupt configs, it logs a warning and returns defaults. When strict
// mode is enabled (AUTO_PRD_STRICT=1), validation errors are fatal and this
// function will panic after logging the error. Use LoadWithWarnings() if you
// need to handle validation errors programmatically.
func Load() Config {
    result := LoadWithWarnings()
    for _, warning := range result.Warnings {
        log.Printf("Warning: %s", warning)
    }
    if result.Error != nil {
        log.Fatalf("Config validation failed: %v", result.Error)
    }
    return result.Config
}
```

**Rationale for using `log.Fatalf()`**:
- It calls `os.Exit(1)` after logging, which is appropriate for fatal config errors
- It's consistent with how Go's standard library handles fatal errors
- It prevents the need to change `Load()`'s signature (maintains backward compatibility)

### Success Criteria:

#### Automated Verification:
- [ ] Code compiles: `go build ./internal/config`
- [ ] All existing tests pass: `go test ./internal/config`
- [ ] Linting passes: `gofmt -w internal/config/config.go`

**Note**: This phase makes `Load()` terminate the program on strict mode errors. The next phase will test this end-to-end.

---

## Phase 5: Add Unit Tests

### Overview
Add comprehensive unit tests to verify strict mode behavior in all scenarios.

### Changes Required:

#### 1. internal/config/config_test.go
**File**: `/Users/simo/Projects/autodev/internal/config/config_test.go`

**Add test cases** at the end of the file:

```go
func TestLoadWithWarningsStrictMode(t *testing.T) {
    // Save and restore original env value
    originalEnv := os.Getenv(config.EnvStrict)
    defer func() {
        if originalEnv != "" {
            os.Setenv(config.EnvStrict, originalEnv)
        } else {
            os.Unsetenv(config.EnvStrict)
        }
    }()

    t.Run("strict mode with nil MaxBatchSize returns error", func(t *testing.T) {
        os.Setenv(config.EnvStrict, "1")

        // Create config with nil MaxBatchSize
        cfg := config.Defaults()
        cfg.BatchProcessing.MaxBatchSize = nil

        // Marshal and unmarshal to simulate file load
        data, err := yaml.Marshal(cfg)
        if err != nil {
            t.Fatalf("failed to marshal config: %v", err)
        }

        // Create temporary config file
        tmpDir := t.TempDir()
        configPath := filepath.Join(tmpDir, "config.yaml")
        if err := os.WriteFile(configPath, data, 0600); err != nil {
            t.Fatalf("failed to write config file: %v", err)
        }

        // Temporarily override config path
        // Note: This requires config.LoadWithWarnings() to accept a path parameter
        // OR we need to refactor to make this testable
        // For now, we'll test LoadWithWarnings() with a constructed Config
    })

    t.Run("strict mode with zero MaxBatchSize returns error", func(t *testing.T) {
        os.Setenv(config.EnvStrict, "1")

        // Create config with MaxBatchSize = 0
        cfg := config.Defaults()
        zero := 0
        cfg.BatchProcessing.MaxBatchSize = &zero

        // Test that validation fails
        // (Implementation depends on refactoring for testability)
    })

    t.Run("strict mode with negative MaxBatchSize returns error", func(t *testing.T) {
        os.Setenv(config.EnvStrict, "1")

        // Create config with MaxBatchSize = -1
        cfg := config.Defaults()
        neg := -1
        cfg.BatchProcessing.MaxBatchSize = &neg

        // Test that validation fails
    })

    t.Run("strict mode with valid MaxBatchSize succeeds", func(t *testing.T) {
        os.Setenv(config.EnvStrict, "1")

        // Create config with valid MaxBatchSize
        cfg := config.Defaults()
        valid := 50
        cfg.BatchProcessing.MaxBatchSize = &valid

        // Test that validation succeeds
    })

    t.Run("non-strict mode with invalid MaxBatchSize returns warning", func(t *testing.T) {
        os.Unsetenv(config.EnvStrict)

        // Create config with nil MaxBatchSize
        cfg := config.Defaults()
        cfg.BatchProcessing.MaxBatchSize = nil

        // Test that warning is returned and default is applied
    })

    t.Run("non-strict mode with valid MaxBatchSize succeeds", func(t *testing.T) {
        os.Unsetenv(config.EnvStrict)

        // Create config with valid MaxBatchSize
        cfg := config.Defaults()
        valid := 100
        cfg.BatchProcessing.MaxBatchSize = &valid

        // Test that no warning and no error
    })
}
```

**Note**: The above test structure shows intent but requires refactoring `LoadWithWarnings()` to accept a config path parameter for proper testing. Alternative: add a helper function `validateMaxBatchSize()` that can be tested directly.

**Recommended testable refactor**:

Add a new internal function in config.go:
```go
// validateMaxBatchSize checks if MaxBatchSize is valid and returns an error if in strict mode.
// Returns (warning string, error). If both are nil, the value is valid.
func validateMaxBatchSize(maxBatchSize *int, strictMode bool) (string, error) {
    if maxBatchSize == nil || *maxBatchSize <= 0 {
        var currentValue int
        if maxBatchSize != nil {
            currentValue = *maxBatchSize
        }

        if strictMode {
            return "", fmt.Errorf("max_batch_size must be > 0, got %d (strict mode enabled)", currentValue)
        }

        return fmt.Sprintf("max_batch_size must be > 0, got %d; using default value %d", currentValue, DefaultMaxBatchSize), nil
    }
    return "", nil
}
```

Then update `LoadWithWarnings()` to call this helper, and test the helper directly.

### Success Criteria:

#### Automated Verification:
- [ ] New tests compile: `go test ./internal/config -run TestLoadWithWarningsStrictMode`
- [ ] All tests pass: `go test ./internal/config`
- [ ] Code coverage includes new validation logic

**Note**: Tests should be added in Phase 5 to verify the implementation from Phases 1-4 works correctly.

---

## Phase 6: Integration Testing

### Overview
Test the full end-to-end flow with the environment variable set and unset.

### Manual Testing Steps:

1. **Test strict mode with invalid config**:
   ```bash
   # Create config with invalid MaxBatchSize
   cat > ~/.config/aprd/config.yaml <<EOF
   batch_processing:
     max_batch_size: 0
   EOF

   # Set strict mode
   export AUTO_PRD_STRICT=1

   # Run application - should exit with error
   aprd
   # Expected: Exit with status 1 and error message mentioning strict mode
   ```

2. **Test strict mode with valid config**:
   ```bash
   # Create config with valid MaxBatchSize
   cat > ~/.config/aprd/config.yaml <<EOF
   batch_processing:
     max_batch_size: 50
   EOF

   # Set strict mode
   export AUTO_PRD_STRICT=1

   # Run application - should start normally
   aprd
   # Expected: TUI starts successfully
   ```

3. **Test non-strict mode with invalid config**:
   ```bash
   # Create config with invalid MaxBatchSize
   cat > ~/.config/aprd/config.yaml <<EOF
   batch_processing:
     max_batch_size: -5
   EOF

   # Unset strict mode (or don't set it)
   unset AUTO_PRD_STRICT

   # Run application - should start with warning
   aprd
   # Expected: Warning logged, TUI starts with default value
   ```

4. **Test non-strict mode with valid config**:
   ```bash
   # Create config with valid MaxBatchSize
   cat > ~/.config/aprd/config.yaml <<EOF
   batch_processing:
     max_batch_size: 30
   EOF

   # Unset strict mode
   unset AUTO_PRD_STRICT

   # Run application - should start normally
   aprd
   # Expected: No warnings, TUI starts successfully
   ```

### Success Criteria:

#### Manual Verification:
- [ ] Strict mode with invalid MaxBatchSize exits before TUI starts
- [ ] Error message is clear and mentions AUTO_PRD_STRICT
- [ ] Exit code is 1 for strict mode errors
- [ ] Strict mode with valid MaxBatchSize works normally
- [ ] Non-strict mode shows warning but continues
- [ ] No regressions in normal operation

**Note**: Manual testing is crucial here because we're testing `log.Fatalf()` behavior which terminates the process.

---

## Testing Strategy

### Unit Tests:

**Test helper function** (if refactored):
- `validateMaxBatchSize(nil, true)` → returns error
- `validateMaxBatchSize(intPtr(0), true)` → returns error
- `validateMaxBatchSize(intPtr(-1), true)` → returns error
- `validateMaxBatchSize(intPtr(25), true)` → returns (nil, nil)
- `validateMaxBatchSize(nil, false)` → returns warning, nil error
- `validateMaxBatchSize(intPtr(0), false)` → returns warning, nil error
- `validateMaxBatchSize(intPtr(25), false)` → returns (nil, nil)

**Test LoadResult**:
- LoadResult with Error field is populated in strict mode
- LoadResult with Warnings is populated in non-strict mode
- LoadResult.Config contains defaults in strict mode on error

### Integration Tests:

**End-to-end scenarios**:
1. `AUTO_PRD_STRICT=1` + invalid config → exit 1
2. `AUTO_PRD_STRICT=1` + valid config → success
3. No env var + invalid config → warning + success
4. No env var + valid config → success

### Edge Cases to Test:

- MaxBatchSize = 0 (zero value)
- MaxBatchSize = -1 (negative value)
- MaxBatchSize = nil (not set)
- MaxBatchSize = 1 (minimum valid value)
- MaxBatchSize = 1000000 (large value)
- Env var set to "0" (should not enable strict mode)
- Env var set to "true" (should not enable strict mode - only "1" works)

## Migration Notes

No migration needed. This is a purely additive feature:
- Default behavior is unchanged
- Opt-in via environment variable
- No config file format changes
- No database migrations
- No API changes

## References

- Research: `/Users/simo/Projects/autodev/.wreckit/items/016-make-maxbatchsize-validation-fail-in-strict-mode/research.md`
- Config file: `/Users/simo/Projects/autodev/internal/config/config.go`
  - Lines 16-26: Environment variable constants
  - Lines 280-285: LoadResult struct
  - Lines 292-298: Load() function
  - Lines 300-454: LoadWithWarnings() function
  - Lines 443-451: MaxBatchSize validation logic
- TUI initialization: `/Users/simo/Projects/autodev/internal/tui/model.go:267-336`
- Main entry point: `/Users/simo/Projects/autodev/cmd/aprd/main.go:11-24`
- Test file: `/Users/simo/Projects/autodev/internal/config/config_test.go`
