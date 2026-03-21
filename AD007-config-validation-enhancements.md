# AD007: Configuration Validation Enhancements

## Severity
Low

## Location
`internal/config/config.go` and `internal/config/validation_test.go`

## Current State

### What's Well Covered
The `ValidateInterField()` function has **excellent test coverage** with 20+ test cases:
- Phase validation (at least one phase enabled)
- Executor policy validation
- Phase executor validation
- Log level validation
- Timing validation (poll interval, max iters, timeouts)
- Batch processing validation
- Disabled phase settings warnings

### Validation Tests (validation_test.go - 678 lines)
```
TestValidateInterFieldDefaultsValid
TestValidateInterFieldNoPhasesEnabled
TestValidateInterFieldInfiniteReviewsWarning
TestValidateInterFieldDryRunAllowUnsafeInfo
TestValidateInterFieldPollExceedsIdleGrace
TestValidateInterFieldShortPollInterval
TestValidateInterFieldMaxLocalItersZero
TestValidateInterFieldMaxLocalItersNegative
TestValidateInterFieldMaxLocalItersExtremelyHigh
TestValidateInterFieldInvalidExecutorPolicy
TestValidateInterFieldValidExecutorPolicies
TestValidateInterFieldInvalidPhaseExecutor
TestValidateInterFieldValidPhaseExecutors
TestValidateInterFieldInvalidLogLevel
TestValidateInterFieldValidLogLevels
TestValidateInterFieldNegativeBatchTimeout
TestValidateInterFieldDisabledPhaseSettingsInfo
TestValidateInterFieldLocalDisabledMaxItersInfo
TestValidationResultHelpers
TestValidateInterFieldMultipleErrors
TestErrorInjectionScenarios
TestValidateInterFieldNegativeCodexTimeout
TestValidateInterFieldNegativeClaudeTimeout
TestValidateInterFieldShortCodexTimeout
TestValidateInterFieldShortClaudeTimeout
TestValidateInterFieldZeroTimeoutIsValid
TestValidateInterFieldReasonableTimeout
```

### Minor Gaps

#### 1. Missing Path Validations
```go
// These paths are not validated:
RepoPath        string  // Should exist and be git root
PythonScript    string  // Should exist and be .py
PythonCommand   string  // Should be valid command
```

#### 2. Missing Ralph Boolean Field Validation
```go
// Boolean fields in Ralph have edge cases (noted in docs)
// When partial Ralph config is provided, booleans may not
// get proper defaults (addressed in ApplyDefaults but not tested)
type Ralph struct {
    Enabled             bool  // No validation
    AutoAddSigns        bool  // No validation
    ShowProgressLog     bool  // No validation
    ShowGuardrails      bool  // No validation
    EnableReviewRound   bool  // No validation
}
```

#### 3. Missing Slice Element Validation
```go
// AllowedPythonDirs and SafeScriptDirs
// - No validation for empty strings
// - No validation for non-existent paths
// - No validation for relative vs absolute paths
```

#### 4. Missing Cross-Field Validation
```go
// Example: If Ralph.EnableReviewRound is true but RunPhases.ReviewFix is false
// Should warn about configuration mismatch
```

### Proposed Enhancements

#### 1. Add Path Validation Helper
```go
func validatePath(path, fieldName string, mustExist, mustBeFile bool) *ValidationIssue {
    if path == "" {
        return nil // Empty is OK for optional fields
    }
    
    info, err := os.Stat(path)
    if err != nil {
        return &ValidationIssue{
            Field:    fieldName,
            Message:  fmt.Sprintf("path does not exist: %s", path),
            Severity: "error",
        }
    }
    
    if mustBeFile && info.IsDir() {
        return &ValidationIssue{
            Field:    fieldName,
            Message:  fmt.Sprintf("expected file, got directory: %s", path),
            Severity: "error",
        }
    }
    
    return nil
}
```

#### 2. Add Ralph Config Cross-Validation
```go
func (c Config) validateRalphPhases() []ValidationIssue {
    var issues []ValidationIssue
    
    if c.Ralph.EnableReviewRound && !c.RunPhases.ReviewFix {
        issues = append(issues, ValidationIssue{
            Field:    "ralph.enable_review_round",
            Message:  "review_round enabled but review_fix phase is disabled",
            Severity: "warning",
        })
    }
    
    return issues
}
```

#### 3. Add Slice Element Validation
```go
func validateDirSlice(slice []string, fieldName string) []ValidationIssue {
    var issues []ValidationIssue
    seen := make(map[string]bool)
    
    for i, dir := range slice {
        dir = strings.TrimSpace(dir)
        if dir == "" {
            continue
        }
        
        if seen[strings.ToLower(dir)] {
            issues = append(issues, ValidationIssue{
                Field:    fmt.Sprintf("%s[%d]", fieldName, i),
                Message:  "duplicate directory entry",
                Severity: "warning",
            })
        }
        seen[strings.ToLower(dir)] = true
    }
    
    return issues
}
```

### Test Cases to Add
```go
func TestValidateInterFieldRalphReviewPhaseMismatch(t *testing.T)
func TestValidateInterFieldDuplicateAllowedPythonDirs(t *testing.T)
func TestValidateInterFieldInvalidRepoPath(t *testing.T)
func TestValidateInterFieldInvalidPythonScript(t *testing.T)
func TestValidateInterFieldEmptySliceElements(t *testing.T)
```

## Priority
Low - Current validation is comprehensive for production use

## Related Files
- `internal/config/config.go` (1054 lines)
- `internal/config/validation_test.go` (678 lines)
- `internal/config/config_test.go`
