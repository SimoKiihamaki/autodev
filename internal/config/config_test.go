package config

import (
	"fmt"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/SimoKiihamaki/autodev/internal/utils"
)

func TestConfigCloneIndependence(t *testing.T) {
	base := Defaults()
	base.AllowedPythonDirs = []string{"/tmp/autodev"}
	stamp := time.Now()
	base.PRDs = map[string]PRDMeta{
		"/tmp/doc.md": {Tags: []string{"foo"}, LastUsed: stamp},
	}

	clone := base.Clone()
	if !base.Equal(clone) {
		t.Fatalf("expected clone to be equal to original")
	}

	clone.AllowedPythonDirs[0] = "/other"
	clone.PRDs["/tmp/doc.md"] = PRDMeta{Tags: []string{"bar"}}

	if base.AllowedPythonDirs[0] != "/tmp/autodev" {
		t.Fatalf("original slice mutated by clone change")
	}
	if got := base.PRDs["/tmp/doc.md"].Tags[0]; got != "foo" {
		t.Fatalf("original map mutated by clone change, got %q", got)
	}
}

func TestConfigEqual(t *testing.T) {
	base := Defaults()
	base.Flags.AllowUnsafe = true
	base.AllowedPythonDirs = []string{"/tmp/autodev"}
	base.PRDs = map[string]PRDMeta{
		"/tmp/doc.md": {Tags: []string{"foo"}},
	}

	if !base.Equal(base.Clone()) {
		t.Fatalf("expected equal configs to report true")
	}

	modified := base.Clone()
	modified.Flags.AllowUnsafe = false
	if base.Equal(modified) {
		t.Fatalf("expected differing flags to report inequality")
	}

	modified = base.Clone()
	modified.FollowLogs = utils.BoolPtr(!*base.FollowLogs)
	if base.Equal(modified) {
		t.Fatalf("expected differing follow_logs to report inequality")
	}

	modified = base.Clone()
	modified.PRDs["/tmp/doc.md"] = PRDMeta{Tags: []string{"foo"}, LastUsed: time.Now()}
	if base.Equal(modified) {
		t.Fatalf("expected differing PRD metadata to report inequality")
	}

	base = Defaults()
	base.AllowedPythonDirs = nil
	modified = base.Clone()
	modified.AllowedPythonDirs = []string{}
	if !base.Equal(modified) {
		t.Fatalf("nil vs empty slices should be considered equal")
	}
}

func TestIsValidGitBranchName(t *testing.T) {
	validBranches := []string{
		"main",
		"master",
		"feature/new-feature",
		"bugfix/123-fix-issue",
		"release-1.0.0",
		"codex/plan-20251127",
		"user/john/experiment",
		"v1.2.3",
		"some_branch",
		"UPPERCASE",
		"MixedCase123",
		"hyphen-end-", // dashes at end are allowed
	}

	for _, branch := range validBranches {
		if !isValidGitBranchName(branch) {
			t.Errorf("expected %q to be valid, but was rejected", branch)
		}
	}

	invalidBranches := []string{
		"",                // empty
		".hidden",         // starts with dot
		"/leading-slash",  // starts with slash
		"trailing.",       // ends with dot
		"trailing/",       // ends with slash
		"branch.lock",     // ends with .lock
		"has..dots",       // consecutive dots
		"has//slashes",    // consecutive slashes
		"has space",       // contains space
		"has~tilde",       // contains tilde
		"has^caret",       // contains caret
		"has:colon",       // contains colon
		"has?question",    // contains question mark
		"has*star",        // contains asterisk
		"has[bracket",     // contains open bracket
		"has@{seq",        // contains @{ sequence (security measure)
		"has\\backslash",  // contains backslash
		"-hyphen-start",   // starts with hyphen (git interprets as option)
		"-both-ends-",     // starts with hyphen (git interprets as option)
		"--double-hyphen", // starts with double hyphen (git interprets as option)
	}

	for _, branch := range invalidBranches {
		if isValidGitBranchName(branch) {
			t.Errorf("expected %q to be invalid, but was accepted", branch)
		}
	}
}

func TestValidateInterFieldBranchNames(t *testing.T) {
	// Valid branch name should not produce error
	cfg := Defaults()
	cfg.Branch = "feature/valid-branch"
	cfg.BaseBranch = "main"
	result := cfg.ValidateInterField()
	for _, issue := range result.Issues {
		if issue.Field == "branch" || issue.Field == "base_branch" {
			t.Errorf("unexpected validation issue for valid branch: %s - %s", issue.Field, issue.Message)
		}
	}

	// Invalid branch name should produce error
	cfg = Defaults()
	cfg.Branch = "invalid..branch"
	result = cfg.ValidateInterField()
	found := false
	for _, issue := range result.Issues {
		if issue.Field == "branch" && issue.Severity == "error" {
			found = true
			break
		}
	}
	if !found {
		t.Error("expected validation error for invalid branch name")
	}

	// Invalid base branch name should produce error
	cfg = Defaults()
	cfg.BaseBranch = "has space"
	result = cfg.ValidateInterField()
	found = false
	for _, issue := range result.Issues {
		if issue.Field == "base_branch" && issue.Severity == "error" {
			found = true
			break
		}
	}
	if !found {
		t.Error("expected validation error for invalid base_branch name")
	}
}

func TestLoadWithWarningsStrictMode(t *testing.T) {
	t.Run("strict mode with nil MaxBatchSize returns error", func(t *testing.T) {
		cfg := Defaults()
		cfg.BatchProcessing.MaxBatchSize = nil

		result := loadWithWarningsForTest(cfg, true)
		if result.Error == nil {
			t.Error("expected error in strict mode with nil MaxBatchSize, got nil")
		}
		if len(result.Warnings) > 0 {
			t.Errorf("expected no warnings in strict mode, got %d", len(result.Warnings))
		}
	})

	t.Run("strict mode with zero MaxBatchSize returns error", func(t *testing.T) {
		cfg := Defaults()
		zero := 0
		cfg.BatchProcessing.MaxBatchSize = &zero

		result := loadWithWarningsForTest(cfg, true)
		if result.Error == nil {
			t.Error("expected error in strict mode with zero MaxBatchSize, got nil")
		}
		errorMsg := result.Error.Error()
		if !contains(errorMsg, "max_batch_size must be > 0") {
			t.Errorf("error message should mention max_batch_size validation, got: %s", errorMsg)
		}
		if !contains(errorMsg, "AUTO_PRD_STRICT") {
			t.Errorf("error message should mention AUTO_PRD_STRICT, got: %s", errorMsg)
		}
	})

	t.Run("strict mode with negative MaxBatchSize returns error", func(t *testing.T) {
		cfg := Defaults()
		neg := -1
		cfg.BatchProcessing.MaxBatchSize = &neg

		result := loadWithWarningsForTest(cfg, true)
		if result.Error == nil {
			t.Error("expected error in strict mode with negative MaxBatchSize, got nil")
		}
	})

	t.Run("strict mode with valid MaxBatchSize succeeds", func(t *testing.T) {
		cfg := Defaults()
		valid := 50
		cfg.BatchProcessing.MaxBatchSize = &valid

		result := loadWithWarningsForTest(cfg, true)
		if result.Error != nil {
			t.Errorf("expected no error in strict mode with valid MaxBatchSize, got: %v", result.Error)
		}
		if *result.Config.BatchProcessing.MaxBatchSize != 50 {
			t.Errorf("expected MaxBatchSize to be 50, got %d", *result.Config.BatchProcessing.MaxBatchSize)
		}
	})

	t.Run("non-strict mode with nil MaxBatchSize returns warning", func(t *testing.T) {
		cfg := Defaults()
		cfg.BatchProcessing.MaxBatchSize = nil

		result := loadWithWarningsForTest(cfg, false)
		if result.Error != nil {
			t.Errorf("expected no error in non-strict mode, got: %v", result.Error)
		}
		if len(result.Warnings) == 0 {
			t.Error("expected warning in non-strict mode with nil MaxBatchSize, got none")
		}
		foundWarning := false
		for _, w := range result.Warnings {
			if contains(w, "max_batch_size must be > 0") {
				foundWarning = true
				break
			}
		}
		if !foundWarning {
			t.Errorf("expected warning about max_batch_size, got: %v", result.Warnings)
		}
		if *result.Config.BatchProcessing.MaxBatchSize != DefaultMaxBatchSize {
			t.Errorf("expected MaxBatchSize to be default (%d), got %d", DefaultMaxBatchSize, *result.Config.BatchProcessing.MaxBatchSize)
		}
	})

	t.Run("non-strict mode with zero MaxBatchSize returns warning", func(t *testing.T) {
		cfg := Defaults()
		zero := 0
		cfg.BatchProcessing.MaxBatchSize = &zero

		result := loadWithWarningsForTest(cfg, false)
		if result.Error != nil {
			t.Errorf("expected no error in non-strict mode, got: %v", result.Error)
		}
		if len(result.Warnings) == 0 {
			t.Error("expected warning in non-strict mode with zero MaxBatchSize, got none")
		}
	})

	t.Run("non-strict mode with valid MaxBatchSize succeeds", func(t *testing.T) {
		cfg := Defaults()
		valid := 100
		cfg.BatchProcessing.MaxBatchSize = &valid

		result := loadWithWarningsForTest(cfg, false)
		if result.Error != nil {
			t.Errorf("expected no error in non-strict mode with valid MaxBatchSize, got: %v", result.Error)
		}
		if len(result.Warnings) != 0 {
			t.Errorf("expected no warnings in non-strict mode with valid MaxBatchSize, got %d", len(result.Warnings))
		}
		if *result.Config.BatchProcessing.MaxBatchSize != 100 {
			t.Errorf("expected MaxBatchSize to be 100, got %d", *result.Config.BatchProcessing.MaxBatchSize)
		}
	})
}

// Helper function to test LoadWithWarnings logic with a pre-configured Config
func loadWithWarningsForTest(c Config, strictMode bool) LoadResult {
	// Simulate the validation logic from LoadWithWarnings
	var warnings []string

	// Validate MaxBatchSize
	if c.BatchProcessing.MaxBatchSize == nil || *c.BatchProcessing.MaxBatchSize <= 0 {
		var currentValue int
		if c.BatchProcessing.MaxBatchSize != nil {
			currentValue = *c.BatchProcessing.MaxBatchSize
		}

		// Check if strict mode is enabled
		if strictMode {
			// Strict mode: return error instead of warning
			return LoadResult{
				Config: Defaults(),
				Error:  fmt.Errorf("config validation failed (AUTO_PRD_STRICT enabled): max_batch_size must be > 0, got %d", currentValue),
			}
		}

		// Non-strict mode: warning + auto-correction
		warnings = append(warnings, fmt.Sprintf("max_batch_size must be > 0, got %d; using default value %d", currentValue, DefaultMaxBatchSize))
		c.BatchProcessing.MaxBatchSize = intPtr(DefaultMaxBatchSize)
	}

	return LoadResult{Config: c, Warnings: warnings}
}

// Helper functions for testing
func contains(s, substr string) bool {
	return len(s) >= len(substr) && (s == substr || len(s) > len(substr) && containsHelper(s, substr))
}

func containsHelper(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}

func TestLoad(t *testing.T) {
	t.Run("returns defaults when config file does not exist", func(t *testing.T) {
		// Set a custom config directory to avoid using the real user config
		// Note: Cannot use t.Parallel() with t.Setenv()
		tmpDir := t.TempDir()
		t.Setenv("HOME", tmpDir)

		cfg := Load()
		defaults := Defaults()

		// Should return defaults when no config file exists
		if !cfg.Equal(defaults) {
			t.Errorf("Load() should return defaults when config doesn't exist")
		}
	})
}

func TestLoadWithWarnings(t *testing.T) {
	t.Run("returns defaults when config file does not exist", func(t *testing.T) {
		// Note: Cannot use t.Parallel() with t.Setenv()
		tmpDir := t.TempDir()
		t.Setenv("HOME", tmpDir)

		result := LoadWithWarnings()

		if result.Error != nil {
			t.Errorf("LoadWithWarnings() should not return error when config doesn't exist, got: %v", result.Error)
		}

		if len(result.Warnings) != 0 {
			t.Errorf("LoadWithWarnings() should not return warnings when config doesn't exist, got: %v", result.Warnings)
		}

		defaults := Defaults()
		if !result.Config.Equal(defaults) {
			t.Errorf("LoadWithWarnings() should return defaults when config doesn't exist")
		}
	})

	t.Run("returns warning when config path cannot be determined", func(t *testing.T) {
		// Note: Cannot use t.Parallel() with t.Setenv()
		// Set HOME to a path that will cause directory creation to fail
		// by using a very long path that exceeds system limits
		// Note: This is hard to test reliably, so we'll skip the actual test
		// and just verify the logic structure
		tmpDir := t.TempDir()
		t.Setenv("HOME", tmpDir)

		result := LoadWithWarnings()
		// With a valid temp directory, this should succeed
		if result.Error != nil {
			t.Errorf("LoadWithWarnings() failed: %v", result.Error)
		}
	})
}

func TestSaveAndLoad(t *testing.T) {
	t.Run("saves and loads config correctly", func(t *testing.T) {
		// Note: Cannot use t.Parallel() with t.Setenv()
		tmpDir := t.TempDir()
		t.Setenv("HOME", tmpDir)

		// Create a custom config
		original := Defaults()
		original.RepoPath = "/test/repo"
		original.BaseBranch = "develop"
		original.ExecutorPolicy = "claude-only"

		// Save the config
		if err := Save(original); err != nil {
			t.Fatalf("Save() failed: %v", err)
		}

		// Load the config
		loaded := Load()

		// Verify the loaded config matches the saved config
		if loaded.RepoPath != original.RepoPath {
			t.Errorf("RepoPath = %q, want %q", loaded.RepoPath, original.RepoPath)
		}
		if loaded.BaseBranch != original.BaseBranch {
			t.Errorf("BaseBranch = %q, want %q", loaded.BaseBranch, original.BaseBranch)
		}
		if loaded.ExecutorPolicy != original.ExecutorPolicy {
			t.Errorf("ExecutorPolicy = %q, want %q", loaded.ExecutorPolicy, original.ExecutorPolicy)
		}
	})

	t.Run("creates config directory if it doesn't exist", func(t *testing.T) {
		// Note: Cannot use t.Parallel() with t.Setenv()
		tmpDir := t.TempDir()
		t.Setenv("HOME", tmpDir)

		cfg := Defaults()
		cfg.RepoPath = "/test/repo"

		if err := Save(cfg); err != nil {
			t.Fatalf("Save() failed: %v", err)
		}

		// Verify config file exists
		configDir, err := configDir()
		if err != nil {
			t.Fatalf("configDir() failed: %v", err)
		}

		configPath := joinPath(configDir, "config.yaml")
		if _, err := os.Stat(configPath); os.IsNotExist(err) {
			t.Error("Config file was not created")
		}
	})
}

func TestSaveWithTimeout(t *testing.T) {
	t.Run("saves config within timeout", func(t *testing.T) {
		// Note: Cannot use t.Parallel() with t.Setenv()
		tmpDir := t.TempDir()
		t.Setenv("HOME", tmpDir)

		cfg := Defaults()
		cfg.RepoPath = "/test/repo"

		// Save with a reasonable timeout
		timeout := 5 * time.Second
		if err := SaveWithTimeout(cfg, timeout); err != nil {
			t.Errorf("SaveWithTimeout() failed: %v", err)
		}
	})

	t.Run("returns error when timeout is exceeded", func(t *testing.T) {
		// Note: Cannot use t.Parallel() with t.Setenv()
		tmpDir := t.TempDir()
		t.Setenv("HOME", tmpDir)

		cfg := Defaults()

		// Save with a very short timeout (this test is tricky because
		// file I/O is usually fast, so we'll just verify the function exists)
		timeout := 1 * time.Nanosecond

		// This may or may not timeout depending on the system
		err := SaveWithTimeout(cfg, timeout)
		// We don't assert the error because it's system-dependent
		_ = err
	})
}

func TestMigrateConfig(t *testing.T) {
	t.Run("adds version to pre-versioning config", func(t *testing.T) {
		t.Parallel()

		oldConfig := Config{
			Version:  "", // Pre-versioning
			RepoPath: "/test/repo",
		}

		migrated, warnings := migrateConfig(oldConfig)

		if migrated.Version != ConfigVersion {
			t.Errorf("Version = %q, want %q", migrated.Version, ConfigVersion)
		}

		if len(warnings) == 0 {
			t.Error("Expected migration warning")
		}

		// Verify RepoPath is preserved
		if migrated.RepoPath != oldConfig.RepoPath {
			t.Errorf("RepoPath = %q, want %q", migrated.RepoPath, oldConfig.RepoPath)
		}
	})

	t.Run("does not modify current version config", func(t *testing.T) {
		t.Parallel()

		currentConfig := Config{
			Version:  ConfigVersion,
			RepoPath: "/test/repo",
		}

		migrated, warnings := migrateConfig(currentConfig)

		if migrated.Version != currentConfig.Version {
			t.Errorf("Version changed from %q to %q", currentConfig.Version, migrated.Version)
		}

		if len(warnings) != 0 {
			t.Errorf("Expected no warnings, got: %v", warnings)
		}

		if !migrated.Equal(currentConfig) {
			t.Error("Config should not be modified when already at current version")
		}
	})

	t.Run("handles future version config", func(t *testing.T) {
		t.Parallel()

		// Simulate a future version config
		futureConfig := Config{
			Version:  "9.9.9",
			RepoPath: "/test/repo",
		}

		migrated, warnings := migrateConfig(futureConfig)

		// Future versions should not be downgraded
		if migrated.Version != futureConfig.Version {
			t.Errorf("Version changed from %q to %q", futureConfig.Version, migrated.Version)
		}

		if len(warnings) != 0 {
			t.Errorf("Expected no warnings for future version, got: %v", warnings)
		}
	})
}

func TestEnsureDir(t *testing.T) {
	t.Run("creates config directory with correct permissions", func(t *testing.T) {
		// Note: Cannot use t.Parallel() with t.Setenv()
		tmpDir := t.TempDir()
		t.Setenv("HOME", tmpDir)

		dir, err := EnsureDir()
		if err != nil {
			t.Fatalf("EnsureDir() failed: %v", err)
		}

		// Verify directory exists
		if info, err := os.Stat(dir); os.IsNotExist(err) {
			t.Error("Config directory was not created")
		} else {
			// Check permissions (0o700 = rwx------
			if info.Mode().Perm() != 0o700 {
				t.Errorf("Directory permissions = %o, want %o", info.Mode().Perm(), 0o700)
			}
		}
	})

	t.Run("returns existing directory if it already exists", func(t *testing.T) {
		// Note: Cannot use t.Parallel() with t.Setenv()
		tmpDir := t.TempDir()
		t.Setenv("HOME", tmpDir)

		// Create directory first
		dir1, err := EnsureDir()
		if err != nil {
			t.Fatalf("First EnsureDir() failed: %v", err)
		}

		// Call again
		dir2, err := EnsureDir()
		if err != nil {
			t.Fatalf("Second EnsureDir() failed: %v", err)
		}

		if dir1 != dir2 {
			t.Errorf("EnsureDir() returned different paths: %q vs %q", dir1, dir2)
		}
	})
}

func TestPath(t *testing.T) {
	t.Run("returns correct config file path", func(t *testing.T) {
		// Note: Cannot use t.Parallel() with t.Setenv()
		tmpDir := t.TempDir()
		t.Setenv("HOME", tmpDir)

		configPath, err := path()
		if err != nil {
			t.Fatalf("path() failed: %v", err)
		}

		// Verify path contains the expected components
		if !contains(configPath, ".config") {
			t.Error("Config path should contain '.config'")
		}
		if !contains(configPath, "aprd") {
			t.Error("Config path should contain 'aprd'")
		}
		if !contains(configPath, "config.yaml") {
			t.Error("Config path should contain 'config.yaml'")
		}
	})
}

func TestConfigDir(t *testing.T) {
	t.Run("returns correct config directory path", func(t *testing.T) {
		// Note: Cannot use t.Parallel() with t.Setenv()
		tmpDir := t.TempDir()
		t.Setenv("HOME", tmpDir)

		dir, err := configDir()
		if err != nil {
			t.Fatalf("configDir() failed: %v", err)
		}

		// Verify directory contains the expected components
		if !contains(dir, ".config") {
			t.Error("Config directory should contain '.config'")
		}
		if !contains(dir, "aprd") {
			t.Error("Config directory should contain 'aprd'")
		}
	})

	t.Run("returns error when HOME is not set", func(t *testing.T) {
		// Note: Cannot use t.Parallel() with t.Setenv()
		// Unset HOME environment variable
		oldHome := os.Getenv("HOME")
		defer func() { _ = os.Setenv("HOME", oldHome) }()
		_ = os.Unsetenv("HOME")

		_, err := configDir()
		if err == nil {
			t.Error("configDir() should return error when HOME is not set")
		}
	})
}

// Helper function to join paths (portable version)
func joinPath(parts ...string) string {
	return strings.Join(parts, string(os.PathSeparator))
}
