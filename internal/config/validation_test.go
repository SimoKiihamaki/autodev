package config

import (
	"strings"
	"testing"
)

func TestValidateInterFieldDefaultsValid(t *testing.T) {
	cfg := Defaults()
	result := cfg.ValidateInterField()

	if !result.Valid {
		t.Errorf("default config should be valid, got errors: %v", result.Errors())
	}

	// Defaults should have no errors
	if len(result.Errors()) != 0 {
		t.Errorf("expected no errors for defaults, got %d", len(result.Errors()))
	}
}

func TestValidateInterFieldNoPhasesEnabled(t *testing.T) {
	cfg := Defaults()
	cfg.RunPhases.Local = false
	cfg.RunPhases.PR = false
	cfg.RunPhases.ReviewFix = false

	result := cfg.ValidateInterField()

	if result.Valid {
		t.Error("config with no phases enabled should be invalid")
	}

	// Should have exactly one error about phases
	errors := result.Errors()
	if len(errors) != 1 {
		t.Errorf("expected 1 error, got %d", len(errors))
	}
	if errors[0].Field != "run_phases" {
		t.Errorf("expected error on run_phases, got %s", errors[0].Field)
	}
}

func TestValidateInterFieldInfiniteReviewsWarning(t *testing.T) {
	cfg := Defaults()
	cfg.Flags.InfiniteReviews = true
	cfg.RunPhases.ReviewFix = false

	result := cfg.ValidateInterField()

	warnings := result.Warnings()
	found := false
	for _, w := range warnings {
		if w.Field == "flags.infinite_reviews" {
			found = true
			break
		}
	}
	if !found {
		t.Error("expected warning about infinite_reviews when review_fix disabled")
	}
}

func TestValidateInterFieldDryRunAllowUnsafeInfo(t *testing.T) {
	cfg := Defaults()
	cfg.Flags.DryRun = true
	cfg.Flags.AllowUnsafe = true

	result := cfg.ValidateInterField()

	// Should still be valid (just informational)
	if !result.Valid {
		t.Error("dry_run + allow_unsafe should still be valid")
	}

	// Should have an info about redundant flags
	found := false
	for _, issue := range result.Issues {
		if issue.Field == "flags" && issue.Severity == "info" {
			found = true
			break
		}
	}
	if !found {
		t.Error("expected info about redundant flags")
	}
}

func TestValidateInterFieldPollExceedsIdleGrace(t *testing.T) {
	cfg := Defaults()
	cfg.Timings.ReviewPollSeconds = intPtr(700) // 700 seconds
	cfg.Timings.IdleGraceMinutes = intPtr(10)   // 600 seconds

	result := cfg.ValidateInterField()

	warnings := result.Warnings()
	found := false
	for _, w := range warnings {
		if w.Field == "timings" && strings.Contains(w.Message, "exceeds") {
			found = true
			break
		}
	}
	if !found {
		t.Error("expected warning when poll interval exceeds idle grace")
	}
}

func TestValidateInterFieldShortPollInterval(t *testing.T) {
	cfg := Defaults()
	cfg.Timings.ReviewPollSeconds = intPtr(15)

	result := cfg.ValidateInterField()

	warnings := result.Warnings()
	found := false
	for _, w := range warnings {
		if w.Field == "timings.review_poll_seconds" && strings.Contains(w.Message, "rate limit") {
			found = true
			break
		}
	}
	if !found {
		t.Error("expected warning for very short poll interval")
	}
}

func TestValidateInterFieldMaxLocalItersZero(t *testing.T) {
	cfg := Defaults()
	cfg.Timings.MaxLocalIters = intPtr(0)

	result := cfg.ValidateInterField()

	if result.Valid {
		t.Error("max_local_iters = 0 should be invalid")
	}

	errors := result.Errors()
	found := false
	for _, e := range errors {
		if e.Field == "timings.max_local_iters" {
			found = true
			break
		}
	}
	if !found {
		t.Error("expected error on max_local_iters")
	}
}

func TestValidateInterFieldMaxLocalItersNegative(t *testing.T) {
	cfg := Defaults()
	cfg.Timings.MaxLocalIters = intPtr(-5)

	result := cfg.ValidateInterField()

	if result.Valid {
		t.Error("negative max_local_iters should be invalid")
	}
}

func TestValidateInterFieldMaxLocalItersExtremelyHigh(t *testing.T) {
	cfg := Defaults()
	cfg.Timings.MaxLocalIters = intPtr(500)

	result := cfg.ValidateInterField()

	// Should still be valid but with warning (threshold is >200)
	if !result.Valid {
		t.Error("extremely high max_local_iters should still be valid")
	}

	warnings := result.Warnings()
	found := false
	for _, w := range warnings {
		if w.Field == "timings.max_local_iters" && strings.Contains(w.Message, "runaway") {
			found = true
			break
		}
	}
	if !found {
		t.Error("expected warning for extremely high iteration limit")
	}
}

func TestValidateInterFieldInvalidExecutorPolicy(t *testing.T) {
	cfg := Defaults()
	cfg.ExecutorPolicy = "invalid-policy"

	result := cfg.ValidateInterField()

	if result.Valid {
		t.Error("invalid executor_policy should be invalid")
	}

	errors := result.Errors()
	found := false
	for _, e := range errors {
		if e.Field == "executor_policy" {
			found = true
			break
		}
	}
	if !found {
		t.Error("expected error on executor_policy")
	}
}

func TestValidateInterFieldValidExecutorPolicies(t *testing.T) {
	validPolicies := []string{"codex-first", "codex-only", "claude-only", ""}

	for _, policy := range validPolicies {
		cfg := Defaults()
		cfg.ExecutorPolicy = policy

		result := cfg.ValidateInterField()

		if !result.Valid {
			t.Errorf("executor_policy=%q should be valid", policy)
		}
	}
}

func TestValidateInterFieldInvalidPhaseExecutor(t *testing.T) {
	testCases := []struct {
		name     string
		setup    func(*Config)
		expected string
	}{
		{
			name: "invalid implement executor",
			setup: func(c *Config) {
				c.PhaseExecutors.Implement = "invalid"
			},
			expected: "phase_executors.implement",
		},
		{
			name: "invalid fix executor",
			setup: func(c *Config) {
				c.PhaseExecutors.Fix = "invalid"
			},
			expected: "phase_executors.fix",
		},
		{
			name: "invalid pr executor",
			setup: func(c *Config) {
				c.PhaseExecutors.PR = "invalid"
			},
			expected: "phase_executors.pr",
		},
		{
			name: "invalid review_fix executor",
			setup: func(c *Config) {
				c.PhaseExecutors.ReviewFix = "invalid"
			},
			expected: "phase_executors.review_fix",
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			cfg := Defaults()
			tc.setup(&cfg)

			result := cfg.ValidateInterField()

			if result.Valid {
				t.Error("invalid executor should make config invalid")
			}

			errors := result.Errors()
			found := false
			for _, e := range errors {
				if e.Field == tc.expected {
					found = true
					break
				}
			}
			if !found {
				t.Errorf("expected error on %s", tc.expected)
			}
		})
	}
}

func TestValidateInterFieldValidPhaseExecutors(t *testing.T) {
	cfg := Defaults()
	cfg.PhaseExecutors.Implement = "codex"
	cfg.PhaseExecutors.Fix = "claude"
	cfg.PhaseExecutors.PR = ""
	cfg.PhaseExecutors.ReviewFix = "codex"

	result := cfg.ValidateInterField()

	if !result.Valid {
		t.Errorf("valid phase executors should be valid, got errors: %v", result.Errors())
	}
}

func TestValidateInterFieldInvalidLogLevel(t *testing.T) {
	cfg := Defaults()
	cfg.LogLevel = "VERBOSE"

	result := cfg.ValidateInterField()

	if result.Valid {
		t.Error("invalid log_level should be invalid")
	}

	errors := result.Errors()
	found := false
	for _, e := range errors {
		if e.Field == "log_level" {
			found = true
			break
		}
	}
	if !found {
		t.Error("expected error on log_level")
	}
}

func TestValidateInterFieldValidLogLevels(t *testing.T) {
	validLevels := []string{"DEBUG", "INFO", "WARNING", "ERROR", "WARN", "debug", "info"}

	for _, level := range validLevels {
		cfg := Defaults()
		cfg.LogLevel = level

		result := cfg.ValidateInterField()

		if !result.Valid {
			t.Errorf("log_level=%q should be valid", level)
		}
	}
}

func TestValidateInterFieldNegativeBatchTimeout(t *testing.T) {
	cfg := Defaults()
	cfg.BatchProcessing.BatchTimeoutMs = intPtr(-1)

	result := cfg.ValidateInterField()

	if result.Valid {
		t.Error("negative batch_timeout_ms should be invalid")
	}

	errors := result.Errors()
	found := false
	for _, e := range errors {
		if e.Field == "batch_processing.batch_timeout_ms" {
			found = true
			break
		}
	}
	if !found {
		t.Error("expected error on batch_timeout_ms")
	}
}

func TestValidateInterFieldDisabledPhaseSettingsInfo(t *testing.T) {
	cfg := Defaults()
	cfg.RunPhases.ReviewFix = false
	cfg.Timings.ReviewPollSeconds = intPtr(60) // Non-default
	cfg.Timings.IdleGraceMinutes = intPtr(5)   // Non-default
	cfg.Timings.WaitMinutes = intPtr(3)        // Non-default

	result := cfg.ValidateInterField()

	// Should be valid but with info messages
	if !result.Valid {
		t.Error("disabled phase with custom settings should still be valid")
	}

	// Count info messages about review_fix settings
	infoCount := 0
	for _, issue := range result.Issues {
		if issue.Severity == "info" && strings.Contains(issue.Message, "review_fix") {
			infoCount++
		}
	}

	if infoCount < 3 {
		t.Errorf("expected at least 3 info messages about unused review_fix settings, got %d", infoCount)
	}
}

func TestValidateInterFieldLocalDisabledMaxItersInfo(t *testing.T) {
	cfg := Defaults()
	cfg.RunPhases.Local = false
	cfg.Timings.MaxLocalIters = intPtr(100) // Non-default

	result := cfg.ValidateInterField()

	// Should be valid but with info
	if !result.Valid {
		t.Error("disabled local with custom max_local_iters should still be valid")
	}

	found := false
	for _, issue := range result.Issues {
		if issue.Field == "timings.max_local_iters" && issue.Severity == "info" {
			found = true
			break
		}
	}
	if !found {
		t.Error("expected info about unused max_local_iters")
	}
}

func TestValidationResultHelpers(t *testing.T) {
	result := ValidationResult{Valid: true}

	// Test AddError
	result.AddError("field1", "error message")
	if result.Valid {
		t.Error("Valid should be false after AddError")
	}
	if len(result.Errors()) != 1 {
		t.Errorf("expected 1 error, got %d", len(result.Errors()))
	}

	// Test AddWarning (doesn't change Valid)
	result = ValidationResult{Valid: true}
	result.AddWarning("field2", "warning message")
	if !result.Valid {
		t.Error("Valid should still be true after AddWarning")
	}
	if len(result.Warnings()) != 1 {
		t.Errorf("expected 1 warning, got %d", len(result.Warnings()))
	}

	// Test AddInfo (doesn't change Valid)
	result = ValidationResult{Valid: true}
	result.AddInfo("field3", "info message")
	if !result.Valid {
		t.Error("Valid should still be true after AddInfo")
	}
	if len(result.Issues) != 1 {
		t.Errorf("expected 1 issue, got %d", len(result.Issues))
	}
}

func TestValidateInterFieldMultipleErrors(t *testing.T) {
	cfg := Config{
		ExecutorPolicy: "invalid",
		LogLevel:       "VERBOSE",
		RunPhases: Phases{
			Local:     false,
			PR:        false,
			ReviewFix: false,
		},
		Timings: Timings{
			MaxLocalIters: intPtr(-1),
		},
		BatchProcessing: BatchProcessing{
			BatchTimeoutMs: intPtr(-5),
		},
		PhaseExecutors: PhaseExec{
			Implement: "bad",
		},
	}

	result := cfg.ValidateInterField()

	if result.Valid {
		t.Error("config with multiple errors should be invalid")
	}

	// Should have multiple errors
	if len(result.Errors()) < 4 {
		t.Errorf("expected at least 4 errors, got %d: %v", len(result.Errors()), result.Errors())
	}
}

// TestErrorInjectionScenarios tests various error injection scenarios
// that might occur during long-running automation sessions.
func TestErrorInjectionScenarios(t *testing.T) {
	testCases := []struct {
		name        string
		cfg         Config
		expectValid bool
		errorFields []string
	}{
		{
			name: "missing all phases",
			cfg: func() Config {
				c := Defaults()
				c.RunPhases = Phases{}
				return c
			}(),
			expectValid: false,
			errorFields: []string{"run_phases"},
		},
		{
			name: "zero iteration limit",
			cfg: func() Config {
				c := Defaults()
				c.Timings.MaxLocalIters = intPtr(0)
				return c
			}(),
			expectValid: false,
			errorFields: []string{"timings.max_local_iters"},
		},
		{
			name: "completely invalid config",
			cfg: Config{
				ExecutorPolicy: "garbage",
				LogLevel:       "SUPER_DEBUG",
				RunPhases:      Phases{},
				Timings: Timings{
					MaxLocalIters: intPtr(-100),
				},
			},
			expectValid: false,
			errorFields: []string{"run_phases", "timings.max_local_iters", "executor_policy", "log_level"},
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			result := tc.cfg.ValidateInterField()

			if result.Valid != tc.expectValid {
				t.Errorf("expected Valid=%v, got %v", tc.expectValid, result.Valid)
			}

			errors := result.Errors()
			for _, expectedField := range tc.errorFields {
				found := false
				for _, e := range errors {
					if e.Field == expectedField {
						found = true
						break
					}
				}
				if !found {
					t.Errorf("expected error on field %q, errors: %v", expectedField, errors)
				}
			}
		})
	}
}

func TestValidateInterFieldNegativeCodexTimeout(t *testing.T) {
	cfg := Defaults()
	cfg.Timings.CodexTimeoutSeconds = intPtr(-1)

	result := cfg.ValidateInterField()

	if result.Valid {
		t.Error("negative codex_timeout_seconds should be invalid")
	}

	errors := result.Errors()
	found := false
	for _, e := range errors {
		if e.Field == "timings.codex_timeout_seconds" {
			found = true
			break
		}
	}
	if !found {
		t.Error("expected error on codex_timeout_seconds")
	}
}

func TestValidateInterFieldNegativeClaudeTimeout(t *testing.T) {
	cfg := Defaults()
	cfg.Timings.ClaudeTimeoutSeconds = intPtr(-1)

	result := cfg.ValidateInterField()

	if result.Valid {
		t.Error("negative claude_timeout_seconds should be invalid")
	}

	errors := result.Errors()
	found := false
	for _, e := range errors {
		if e.Field == "timings.claude_timeout_seconds" {
			found = true
			break
		}
	}
	if !found {
		t.Error("expected error on claude_timeout_seconds")
	}
}

func TestValidateInterFieldShortCodexTimeout(t *testing.T) {
	cfg := Defaults()
	cfg.Timings.CodexTimeoutSeconds = intPtr(30) // Less than 60

	result := cfg.ValidateInterField()

	// Should still be valid but with warning
	if !result.Valid {
		t.Error("short codex_timeout_seconds should still be valid")
	}

	warnings := result.Warnings()
	found := false
	for _, w := range warnings {
		if w.Field == "timings.codex_timeout_seconds" && strings.Contains(w.Message, "short timeout") {
			found = true
			break
		}
	}
	if !found {
		t.Error("expected warning for very short codex timeout")
	}
}

func TestValidateInterFieldShortClaudeTimeout(t *testing.T) {
	cfg := Defaults()
	cfg.Timings.ClaudeTimeoutSeconds = intPtr(45) // Less than 60

	result := cfg.ValidateInterField()

	// Should still be valid but with warning
	if !result.Valid {
		t.Error("short claude_timeout_seconds should still be valid")
	}

	warnings := result.Warnings()
	found := false
	for _, w := range warnings {
		if w.Field == "timings.claude_timeout_seconds" && strings.Contains(w.Message, "short timeout") {
			found = true
			break
		}
	}
	if !found {
		t.Error("expected warning for very short claude timeout")
	}
}

func TestValidateInterFieldZeroTimeoutIsValid(t *testing.T) {
	cfg := Defaults()
	cfg.Timings.CodexTimeoutSeconds = intPtr(0)
	cfg.Timings.ClaudeTimeoutSeconds = intPtr(0)

	result := cfg.ValidateInterField()

	// Zero timeout (meaning no timeout) should be valid without warnings
	if !result.Valid {
		t.Errorf("zero timeouts should be valid, got errors: %v", result.Errors())
	}

	// Should not have warnings about short timeout since 0 means "no timeout"
	for _, w := range result.Warnings() {
		if strings.Contains(w.Field, "timeout") {
			t.Errorf("zero timeout should not trigger warnings, got: %v", w)
		}
	}
}

func TestValidateInterFieldReasonableTimeout(t *testing.T) {
	cfg := Defaults()
	cfg.Timings.CodexTimeoutSeconds = intPtr(300)  // 5 minutes
	cfg.Timings.ClaudeTimeoutSeconds = intPtr(600) // 10 minutes

	result := cfg.ValidateInterField()

	// Reasonable timeouts should be valid with no warnings
	if !result.Valid {
		t.Errorf("reasonable timeouts should be valid, got errors: %v", result.Errors())
	}

	// Should not have timeout-related warnings
	for _, w := range result.Warnings() {
		if strings.Contains(w.Field, "timeout") {
			t.Errorf("reasonable timeout should not trigger warnings, got: %v", w)
		}
	}
}
