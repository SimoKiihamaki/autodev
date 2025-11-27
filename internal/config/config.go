package config

import (
	"errors"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/SimoKiihamaki/autodev/internal/utils"
	"gopkg.in/yaml.v3"
)

// Environment variable constants for executor configuration
const (
	EnvExecutorPolicy       = "AUTO_PRD_EXECUTOR_POLICY"
	EnvExecutorImplement    = "AUTO_PRD_EXECUTOR_IMPLEMENT"
	EnvExecutorFix          = "AUTO_PRD_EXECUTOR_FIX"
	EnvExecutorPR           = "AUTO_PRD_EXECUTOR_PR"
	EnvExecutorReviewFix    = "AUTO_PRD_EXECUTOR_REVIEW_FIX"
	EnvAllowUnsafeExecution = "AUTO_PRD_ALLOW_UNSAFE_EXECUTION"
)

// Default configuration values
const (
	DefaultMaxBatchSize     = 25
	DefaultLogChannelBuffer = 2048
	DefaultMaxLogLines      = 2000
	DefaultToastTTLMs       = 4000    // 4 seconds
	ConfigVersion           = "1.0.0" // Increment when schema changes require migration
)

type Flags struct {
	AllowUnsafe     bool `yaml:"allow_unsafe"`
	DryRun          bool `yaml:"dry_run"`
	SyncGit         bool `yaml:"sync_git"`
	InfiniteReviews bool `yaml:"infinite_reviews"`
}

type Timings struct {
	WaitMinutes       *int `yaml:"wait_minutes"`
	ReviewPollSeconds *int `yaml:"review_poll_seconds"`
	IdleGraceMinutes  *int `yaml:"idle_grace_minutes"`
	MaxLocalIters     *int `yaml:"max_local_iters"`
}

// BatchProcessing configures how log messages are batched for performance.
// BatchTimeoutMs: 5 provides responsive UI while minimizing CPU wake-ups for better power efficiency.
// MaxBatchSize: 25 balances throughput with memory overhead by limiting concurrent messages.
// LogChannelBuffer: 2048 bounds memory usage while allowing bursts without dropping lines.
type BatchProcessing struct {
	MaxBatchSize     *int `yaml:"max_batch_size"`
	BatchTimeoutMs   *int `yaml:"batch_timeout_ms"`
	LogChannelBuffer *int `yaml:"log_channel_buffer"`
}

// UI configures TUI display settings.
type UI struct {
	MaxLogLines *int `yaml:"max_log_lines"` // Maximum lines to keep in log buffer
	ToastTTLMs  *int `yaml:"toast_ttl_ms"`  // Toast notification duration in milliseconds
}

type PRDMeta struct {
	Tags     []string  `yaml:"tags"`
	LastUsed time.Time `yaml:"last_used,omitempty"`
}

type PhaseExec struct {
	Implement string `yaml:"implement"` // "", "codex", or "claude"
	Fix       string `yaml:"fix"`
	PR        string `yaml:"pr"`
	ReviewFix string `yaml:"review_fix"`
}

type Phases struct {
	Local     bool `yaml:"local"`
	PR        bool `yaml:"pr"`
	ReviewFix bool `yaml:"review_fix"`
}

type Config struct {
	Version           string             `yaml:"version,omitempty"` // Config schema version for migrations
	ExecutorPolicy    string             `yaml:"executor_policy"`
	LogLevel          string             `yaml:"log_level"`
	PythonCommand     string             `yaml:"python_command"`
	PythonScript      string             `yaml:"python_script"`
	RepoPath          string             `yaml:"repo_path"`
	BaseBranch        string             `yaml:"base_branch"`
	Branch            string             `yaml:"branch"`
	CodexModel        string             `yaml:"codex_model"`
	FollowLogs        *bool              `yaml:"follow_logs"`
	Flags             Flags              `yaml:"flags"`
	Timings           Timings            `yaml:"timings"`
	BatchProcessing   BatchProcessing    `yaml:"batch_processing"`
	UI                UI                 `yaml:"ui"`
	PhaseExecutors    PhaseExec          `yaml:"phase_executors"`
	RunPhases         Phases             `yaml:"run_phases"`
	AllowedPythonDirs []string           `yaml:"allowed_python_dirs"`
	PRDs              map[string]PRDMeta `yaml:"prds"` // abs path -> metadata
}

// Defaults returns a sensible default config.
func Defaults() Config {
	return Config{
		Version:        ConfigVersion,
		ExecutorPolicy: "codex-first",
		LogLevel:       "INFO",
		PythonCommand:  "python3",
		PythonScript:   "tools/auto_prd_to_pr_v3.py",
		RepoPath:       "",
		BaseBranch:     "main",
		Branch:         "",
		CodexModel:     "gpt-5-codex",
		FollowLogs:     utils.BoolPtr(true),
		Flags: Flags{
			AllowUnsafe:     false,
			DryRun:          false,
			SyncGit:         false,
			InfiniteReviews: false,
		},
		Timings: Timings{
			WaitMinutes:       intPtr(0),
			ReviewPollSeconds: intPtr(120),
			IdleGraceMinutes:  intPtr(10),
			MaxLocalIters:     intPtr(50),
		},
		BatchProcessing: BatchProcessing{
			MaxBatchSize:     intPtr(DefaultMaxBatchSize),
			BatchTimeoutMs:   intPtr(5),
			LogChannelBuffer: intPtr(DefaultLogChannelBuffer),
		},
		UI: UI{
			MaxLogLines: intPtr(DefaultMaxLogLines),
			ToastTTLMs:  intPtr(DefaultToastTTLMs),
		},
		PhaseExecutors:    PhaseExec{},
		RunPhases:         Phases{Local: true, PR: true, ReviewFix: true},
		AllowedPythonDirs: []string{},
		PRDs:              map[string]PRDMeta{},
	}
}

func configDir() (string, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(home, ".config", "aprd"), nil
}

func path() (string, error) {
	dir, err := configDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(dir, "config.yaml"), nil
}

func EnsureDir() (string, error) {
	dir, err := configDir()
	if err != nil {
		return "", err
	}
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return "", err
	}
	if err := os.Chmod(dir, 0o700); err != nil {
		return "", err
	}
	return dir, nil
}

// migrateConfig applies any necessary migrations to bring the config up to the current version.
// Returns the migrated config and a list of warnings about migrations applied.
func migrateConfig(c Config) (Config, []string) {
	var warnings []string

	// If version is empty, this is a pre-versioning config (treat as 0.0.0)
	if c.Version == "" {
		// Migrate from pre-versioning to 1.0.0
		// No structural changes needed, just set the version
		c.Version = ConfigVersion
		warnings = append(warnings, "config upgraded to version "+ConfigVersion)
	} else if compareVersions(c.Version, ConfigVersion) < 0 {
		// Future migrations would go here, e.g.:
		// if compareVersions(c.Version, "1.1.0") < 0 {
		//     // Apply migration from 1.0.x to 1.1.0
		// }
		warnings = append(warnings, fmt.Sprintf("config upgraded from %s to %s", c.Version, ConfigVersion))
		c.Version = ConfigVersion
	}

	return c, warnings
}

// compareVersions compares two semantic version strings.
// Returns -1 if v1 < v2, 0 if v1 == v2, 1 if v1 > v2.
// Handles missing or malformed versions gracefully (treats them as 0.0.0).
func compareVersions(v1, v2 string) int {
	parse := func(v string) (int, int, int) {
		var major, minor, patch int
		parts := strings.Split(v, ".")
		if len(parts) >= 1 {
			_, _ = fmt.Sscanf(parts[0], "%d", &major)
		}
		if len(parts) >= 2 {
			_, _ = fmt.Sscanf(parts[1], "%d", &minor)
		}
		if len(parts) >= 3 {
			_, _ = fmt.Sscanf(parts[2], "%d", &patch)
		}
		return major, minor, patch
	}

	maj1, min1, pat1 := parse(v1)
	maj2, min2, pat2 := parse(v2)

	if maj1 != maj2 {
		if maj1 < maj2 {
			return -1
		}
		return 1
	}
	if min1 != min2 {
		if min1 < min2 {
			return -1
		}
		return 1
	}
	if pat1 != pat2 {
		if pat1 < pat2 {
			return -1
		}
		return 1
	}
	return 0
}

// LoadResult holds the result of loading configuration, including any warnings
// that occurred during loading (e.g., partial parse failures).
type LoadResult struct {
	Config   Config
	Warnings []string
}

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

// LoadWithWarnings reads the configuration from disk and returns any warnings
// encountered during loading. Unlike Load(), it doesn't log warnings directly,
// allowing callers to handle them as appropriate.
func LoadWithWarnings() LoadResult {
	p, err := path()
	if err != nil {
		return LoadResult{
			Config:   Defaults(),
			Warnings: []string{"could not determine config path: " + err.Error()},
		}
	}
	b, err := os.ReadFile(p)
	if errors.Is(err, os.ErrNotExist) {
		return LoadResult{Config: Defaults()}
	}
	if err != nil {
		return LoadResult{
			Config:   Defaults(),
			Warnings: []string{"could not read config file: " + err.Error()},
		}
	}

	// Start with empty config instead of defaults to preserve explicit zero values
	var c Config
	var warnings []string
	if err := yaml.Unmarshal(b, &c); err != nil {
		// Config file is corrupt; log warning and fall back to defaults
		return LoadResult{
			Config:   Defaults(),
			Warnings: []string{fmt.Sprintf("config file corrupt (using defaults): %v", err)},
		}
	}

	// Apply migrations if config version is older than current
	c, migrationWarnings := migrateConfig(c)
	warnings = append(warnings, migrationWarnings...)

	// Apply defaults only for fields that weren't explicitly set
	defaults := Defaults()

	// Helper function to set default if field is nil, empty, or contains only whitespace
	setStringDefaultIfEmptyOrWhitespace := func(field *string, defaultValue string) {
		if field == nil || strings.TrimSpace(*field) == "" {
			*field = defaultValue
		}
	}

	// Apply defaults for string fields
	setStringDefaultIfEmptyOrWhitespace(&c.ExecutorPolicy, defaults.ExecutorPolicy)
	setStringDefaultIfEmptyOrWhitespace(&c.LogLevel, defaults.LogLevel)
	setStringDefaultIfEmptyOrWhitespace(&c.PythonCommand, defaults.PythonCommand)
	setStringDefaultIfEmptyOrWhitespace(&c.PythonScript, defaults.PythonScript)
	setStringDefaultIfEmptyOrWhitespace(&c.BaseBranch, defaults.BaseBranch)
	setStringDefaultIfEmptyOrWhitespace(&c.CodexModel, defaults.CodexModel)

	// For FollowLogs pointer, if not set, use default (avoid pointer aliasing)
	if c.FollowLogs == nil {
		c.FollowLogs = utils.BoolPtr(*defaults.FollowLogs)
	}

	// Apply defaults for int pointer fields only when nil (preserves explicit zeros)
	if c.Timings.WaitMinutes == nil {
		c.Timings.WaitMinutes = intPtr(*defaults.Timings.WaitMinutes)
	}
	if c.Timings.ReviewPollSeconds == nil {
		c.Timings.ReviewPollSeconds = intPtr(*defaults.Timings.ReviewPollSeconds)
	}
	if c.Timings.IdleGraceMinutes == nil {
		c.Timings.IdleGraceMinutes = intPtr(*defaults.Timings.IdleGraceMinutes)
	}
	if c.Timings.MaxLocalIters == nil {
		c.Timings.MaxLocalIters = intPtr(*defaults.Timings.MaxLocalIters)
	}
	if c.BatchProcessing.MaxBatchSize == nil {
		c.BatchProcessing.MaxBatchSize = intPtr(*defaults.BatchProcessing.MaxBatchSize)
	}
	if c.BatchProcessing.BatchTimeoutMs == nil {
		c.BatchProcessing.BatchTimeoutMs = intPtr(*defaults.BatchProcessing.BatchTimeoutMs)
	}
	if c.BatchProcessing.LogChannelBuffer == nil {
		c.BatchProcessing.LogChannelBuffer = intPtr(*defaults.BatchProcessing.LogChannelBuffer)
	}
	if c.UI.MaxLogLines == nil {
		c.UI.MaxLogLines = intPtr(*defaults.UI.MaxLogLines)
	}
	if c.UI.ToastTTLMs == nil {
		c.UI.ToastTTLMs = intPtr(*defaults.UI.ToastTTLMs)
	}

	// Initialize slices/maps if nil
	if c.AllowedPythonDirs == nil {
		c.AllowedPythonDirs = defaults.AllowedPythonDirs
	}
	if c.PRDs == nil {
		c.PRDs = defaults.PRDs
	}

	// Process LogLevel
	trim := strings.TrimSpace(c.LogLevel)
	if trim == "" {
		c.LogLevel = "INFO"
	} else {
		upper := strings.ToUpper(trim)
		if upper == "WARN" {
			c.LogLevel = "WARNING"
		} else {
			c.LogLevel = upper
		}
	}

	// Validate and set default MaxBatchSize if still invalid
	if c.BatchProcessing.MaxBatchSize == nil || *c.BatchProcessing.MaxBatchSize <= 0 {
		var currentValue int
		if c.BatchProcessing.MaxBatchSize != nil {
			currentValue = *c.BatchProcessing.MaxBatchSize
		}
		warnings = append(warnings, fmt.Sprintf("max_batch_size must be > 0, got %d; using default value %d", currentValue, DefaultMaxBatchSize))
		c.BatchProcessing.MaxBatchSize = intPtr(DefaultMaxBatchSize)
	}

	return LoadResult{Config: c, Warnings: warnings}
}

// DefaultSaveTimeout is the maximum time allowed for a config save operation.
const DefaultSaveTimeout = 5 * time.Second

// Save writes the configuration to disk.
// It applies a timeout to prevent indefinite hangs on slow or failing filesystems.
func Save(c Config) error {
	return SaveWithTimeout(c, DefaultSaveTimeout)
}

// SaveWithTimeout writes the configuration to disk with a specified timeout.
// If the save takes longer than the timeout, it returns a timeout error.
func SaveWithTimeout(c Config, timeout time.Duration) error {
	if _, err := EnsureDir(); err != nil {
		return err
	}
	p, err := path()
	if err != nil {
		return err
	}
	b, err := yaml.Marshal(c)
	if err != nil {
		return err
	}

	// Channel to receive the write result
	done := make(chan error, 1)
	go func() {
		done <- os.WriteFile(p, b, 0o600)
	}()

	// Wait for completion or timeout
	select {
	case err := <-done:
		return err
	case <-time.After(timeout):
		return errors.New("config save timed out after " + timeout.String())
	}
}

// Clone returns a deep copy of the configuration so callers can mutate the
// returned value without affecting the receiver's internal maps or slices.
func (c Config) Clone() Config {
	copyCfg := c
	if c.AllowedPythonDirs != nil {
		copyCfg.AllowedPythonDirs = append([]string(nil), c.AllowedPythonDirs...)
	}
	if c.FollowLogs != nil {
		copyCfg.FollowLogs = utils.BoolPtr(*c.FollowLogs)
	}

	// Clone pointer fields
	if c.Timings.WaitMinutes != nil {
		copyCfg.Timings.WaitMinutes = intPtr(*c.Timings.WaitMinutes)
	}
	if c.Timings.ReviewPollSeconds != nil {
		copyCfg.Timings.ReviewPollSeconds = intPtr(*c.Timings.ReviewPollSeconds)
	}
	if c.Timings.IdleGraceMinutes != nil {
		copyCfg.Timings.IdleGraceMinutes = intPtr(*c.Timings.IdleGraceMinutes)
	}
	if c.Timings.MaxLocalIters != nil {
		copyCfg.Timings.MaxLocalIters = intPtr(*c.Timings.MaxLocalIters)
	}
	if c.BatchProcessing.MaxBatchSize != nil {
		copyCfg.BatchProcessing.MaxBatchSize = intPtr(*c.BatchProcessing.MaxBatchSize)
	}
	if c.BatchProcessing.BatchTimeoutMs != nil {
		copyCfg.BatchProcessing.BatchTimeoutMs = intPtr(*c.BatchProcessing.BatchTimeoutMs)
	}
	if c.BatchProcessing.LogChannelBuffer != nil {
		copyCfg.BatchProcessing.LogChannelBuffer = intPtr(*c.BatchProcessing.LogChannelBuffer)
	}
	if c.UI.MaxLogLines != nil {
		copyCfg.UI.MaxLogLines = intPtr(*c.UI.MaxLogLines)
	}
	if c.UI.ToastTTLMs != nil {
		copyCfg.UI.ToastTTLMs = intPtr(*c.UI.ToastTTLMs)
	}

	if c.PRDs != nil {
		clone := make(map[string]PRDMeta, len(c.PRDs))
		for k, meta := range c.PRDs {
			metaCopy := meta
			if meta.Tags != nil {
				metaCopy.Tags = append([]string(nil), meta.Tags...)
			}
			clone[k] = metaCopy
		}
		copyCfg.PRDs = clone
	}
	return copyCfg
}

// Equal reports whether two configurations contain the same values. It treats
// nil and empty slices/maps as equivalent so callers can rely on it for "dirty"
// state detection without spurious diffs.
func (c Config) Equal(other Config) bool {
	// Note: Version is intentionally excluded from equality check
	// as it's managed automatically during load/save and shouldn't
	// trigger "dirty" state when configs are otherwise identical
	if c.ExecutorPolicy != other.ExecutorPolicy ||
		c.LogLevel != other.LogLevel ||
		c.PythonCommand != other.PythonCommand ||
		c.PythonScript != other.PythonScript ||
		c.RepoPath != other.RepoPath ||
		c.BaseBranch != other.BaseBranch ||
		c.Branch != other.Branch ||
		c.CodexModel != other.CodexModel {
		return false
	}

	// Handle FollowLogs pointer comparison
	if (c.FollowLogs == nil) != (other.FollowLogs == nil) {
		return false
	}
	if c.FollowLogs != nil && other.FollowLogs != nil && *c.FollowLogs != *other.FollowLogs {
		return false
	}

	if c.Flags != other.Flags {
		return false
	}

	// Compare Timings pointer fields
	if !equalIntPointers(c.Timings.WaitMinutes, other.Timings.WaitMinutes) ||
		!equalIntPointers(c.Timings.ReviewPollSeconds, other.Timings.ReviewPollSeconds) ||
		!equalIntPointers(c.Timings.IdleGraceMinutes, other.Timings.IdleGraceMinutes) ||
		!equalIntPointers(c.Timings.MaxLocalIters, other.Timings.MaxLocalIters) {
		return false
	}

	// Compare BatchProcessing pointer fields
	if !equalIntPointers(c.BatchProcessing.MaxBatchSize, other.BatchProcessing.MaxBatchSize) ||
		!equalIntPointers(c.BatchProcessing.BatchTimeoutMs, other.BatchProcessing.BatchTimeoutMs) ||
		!equalIntPointers(c.BatchProcessing.LogChannelBuffer, other.BatchProcessing.LogChannelBuffer) {
		return false
	}
	// Compare UI pointer fields
	if !equalIntPointers(c.UI.MaxLogLines, other.UI.MaxLogLines) ||
		!equalIntPointers(c.UI.ToastTTLMs, other.UI.ToastTTLMs) {
		return false
	}
	if c.PhaseExecutors != other.PhaseExecutors {
		return false
	}
	if c.RunPhases != other.RunPhases {
		return false
	}

	if !equalStringSlices(c.AllowedPythonDirs, other.AllowedPythonDirs) {
		return false
	}

	if !equalPRDMetaMaps(c.PRDs, other.PRDs) {
		return false
	}

	return true
}

func equalStringSlices(a, b []string) bool {
	// Treat nil and empty slices as equivalent
	if len(a) == 0 && len(b) == 0 {
		return true
	}
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

func equalPRDMetaMaps(a, b map[string]PRDMeta) bool {
	if len(a) != len(b) {
		return false
	}
	if len(a) == 0 && len(b) == 0 {
		return true
	}
	for key, metaA := range a {
		metaB, ok := b[key]
		if !ok {
			return false
		}
		if !equalStringSlices(metaA.Tags, metaB.Tags) {
			return false
		}
		if !equalTimes(metaA.LastUsed, metaB.LastUsed) {
			return false
		}
	}
	return true
}

func equalTimes(a, b time.Time) bool {
	if a.IsZero() && b.IsZero() {
		return true
	}
	if a.IsZero() != b.IsZero() {
		return false
	}
	return a.Equal(b)
}

// GetAllowedPythonDirs returns the list of allowed Python directories from the config.
// This can be extended by users to support non-standard Python installations
// (e.g., pyenv, conda, virtualenvs).
func (c Config) GetAllowedPythonDirs() []string {
	if c.AllowedPythonDirs == nil {
		return []string{}
	}
	return append([]string(nil), c.AllowedPythonDirs...)
}

// intPtr returns a pointer to an int value.
func intPtr(i int) *int {
	return &i
}

// equalIntPointers safely compares two int pointers.
// Two nil pointers are considered equal, a nil pointer is different from any non-nil pointer,
// and two non-nil pointers are equal if they point to the same int value.
func equalIntPointers(a, b *int) bool {
	if a == nil && b == nil {
		return true
	}
	if a == nil || b == nil {
		return false
	}
	return *a == *b
}

// ValidationIssue represents a configuration validation issue.
type ValidationIssue struct {
	Field    string
	Message  string
	Severity string // "error", "warning", "info"
}

// ValidationResult holds the results of inter-field validation.
type ValidationResult struct {
	Valid  bool
	Issues []ValidationIssue
}

// AddError adds an error-level issue.
func (v *ValidationResult) AddError(field, message string) {
	v.Issues = append(v.Issues, ValidationIssue{
		Field:    field,
		Message:  message,
		Severity: "error",
	})
	v.Valid = false
}

// AddWarning adds a warning-level issue.
func (v *ValidationResult) AddWarning(field, message string) {
	v.Issues = append(v.Issues, ValidationIssue{
		Field:    field,
		Message:  message,
		Severity: "warning",
	})
}

// AddInfo adds an informational issue.
func (v *ValidationResult) AddInfo(field, message string) {
	v.Issues = append(v.Issues, ValidationIssue{
		Field:    field,
		Message:  message,
		Severity: "info",
	})
}

// Errors returns only error-level issues.
func (v *ValidationResult) Errors() []ValidationIssue {
	var errs []ValidationIssue
	for _, issue := range v.Issues {
		if issue.Severity == "error" {
			errs = append(errs, issue)
		}
	}
	return errs
}

// Warnings returns only warning-level issues.
func (v *ValidationResult) Warnings() []ValidationIssue {
	var warns []ValidationIssue
	for _, issue := range v.Issues {
		if issue.Severity == "warning" {
			warns = append(warns, issue)
		}
	}
	return warns
}

// ValidateInterField performs cross-field validation on the configuration.
// It checks for logical inconsistencies and potentially problematic combinations.
func (c Config) ValidateInterField() ValidationResult {
	result := ValidationResult{Valid: true}

	// Check that at least one phase is enabled
	if !c.RunPhases.Local && !c.RunPhases.PR && !c.RunPhases.ReviewFix {
		result.AddError("run_phases", "at least one phase must be enabled (local, pr, or review_fix)")
	}

	// Warn if infinite_reviews is true but review_fix phase is disabled
	if c.Flags.InfiniteReviews && !c.RunPhases.ReviewFix {
		result.AddWarning("flags.infinite_reviews", "infinite_reviews has no effect when review_fix phase is disabled")
	}

	// Warn if dry_run and allow_unsafe are both true (redundant)
	if c.Flags.DryRun && c.Flags.AllowUnsafe {
		result.AddInfo("flags", "allow_unsafe has no effect when dry_run is enabled")
	}

	// Validate timing constraints
	if c.Timings.ReviewPollSeconds != nil && c.Timings.IdleGraceMinutes != nil {
		pollSeconds := *c.Timings.ReviewPollSeconds
		idleGraceSeconds := *c.Timings.IdleGraceMinutes * 60

		// Warn if poll interval is longer than idle grace (would never poll)
		if pollSeconds > idleGraceSeconds && idleGraceSeconds > 0 {
			result.AddWarning("timings", "review_poll_seconds exceeds idle_grace_minutes; reviews may timeout before first poll")
		}
	}

	// Warn if poll interval is very short (< 30s can cause rate limits)
	if c.Timings.ReviewPollSeconds != nil && *c.Timings.ReviewPollSeconds < 30 {
		result.AddWarning("timings.review_poll_seconds", "very short poll interval may cause API rate limits; consider >= 30 seconds")
	}

	// Validate max_local_iters
	if c.Timings.MaxLocalIters != nil {
		if *c.Timings.MaxLocalIters <= 0 {
			result.AddError("timings.max_local_iters", "must be > 0")
		} else if *c.Timings.MaxLocalIters > 200 {
			result.AddWarning("timings.max_local_iters", "very high iteration limit (>200) may indicate runaway execution")
		}
	}

	// Warn if local phase is disabled but max_local_iters is set
	if !c.RunPhases.Local && c.Timings.MaxLocalIters != nil && *c.Timings.MaxLocalIters != 50 {
		result.AddInfo("timings.max_local_iters", "has no effect when local phase is disabled")
	}

	// Warn if review_fix phase is disabled but review timing settings are customized
	if !c.RunPhases.ReviewFix {
		defaultTimings := Defaults().Timings
		if c.Timings.ReviewPollSeconds != nil && defaultTimings.ReviewPollSeconds != nil &&
			*c.Timings.ReviewPollSeconds != *defaultTimings.ReviewPollSeconds {
			result.AddInfo("timings.review_poll_seconds", "has no effect when review_fix phase is disabled")
		}
		if c.Timings.IdleGraceMinutes != nil && defaultTimings.IdleGraceMinutes != nil &&
			*c.Timings.IdleGraceMinutes != *defaultTimings.IdleGraceMinutes {
			result.AddInfo("timings.idle_grace_minutes", "has no effect when review_fix phase is disabled")
		}
		if c.Timings.WaitMinutes != nil && defaultTimings.WaitMinutes != nil &&
			*c.Timings.WaitMinutes != *defaultTimings.WaitMinutes {
			result.AddInfo("timings.wait_minutes", "has no effect when review_fix phase is disabled")
		}
	}

	// Validate executor policy
	validPolicies := map[string]bool{
		"codex-first": true,
		"codex-only":  true,
		"claude-only": true,
		"":            true, // Empty defaults to codex-first
	}
	if !validPolicies[c.ExecutorPolicy] {
		result.AddError("executor_policy", "must be one of: codex-first, codex-only, claude-only")
	}

	// Validate phase executors
	validExecutors := map[string]bool{
		"codex":  true,
		"claude": true,
		"":       true, // Empty means use policy default
	}
	if !validExecutors[c.PhaseExecutors.Implement] {
		result.AddError("phase_executors.implement", "must be 'codex', 'claude', or empty")
	}
	if !validExecutors[c.PhaseExecutors.Fix] {
		result.AddError("phase_executors.fix", "must be 'codex', 'claude', or empty")
	}
	if !validExecutors[c.PhaseExecutors.PR] {
		result.AddError("phase_executors.pr", "must be 'codex', 'claude', or empty")
	}
	if !validExecutors[c.PhaseExecutors.ReviewFix] {
		result.AddError("phase_executors.review_fix", "must be 'codex', 'claude', or empty")
	}

	// Validate log level
	validLogLevels := map[string]bool{
		"DEBUG":   true,
		"INFO":    true,
		"WARNING": true,
		"ERROR":   true,
		"WARN":    true, // Alias
	}
	if !validLogLevels[strings.ToUpper(c.LogLevel)] {
		result.AddError("log_level", "must be one of: DEBUG, INFO, WARNING, ERROR")
	}

	// Validate batch processing
	if c.BatchProcessing.BatchTimeoutMs != nil && *c.BatchProcessing.BatchTimeoutMs < 0 {
		result.AddError("batch_processing.batch_timeout_ms", "must be >= 0")
	}
	if c.BatchProcessing.LogChannelBuffer != nil && *c.BatchProcessing.LogChannelBuffer <= 0 {
		result.AddError("batch_processing.log_channel_buffer", "must be > 0")
	}

	// Validate branch names using git's refname rules
	if c.Branch != "" && !isValidGitBranchName(c.Branch) {
		result.AddError("branch", "invalid git branch name (contains invalid characters or sequences)")
	}
	if c.BaseBranch != "" && !isValidGitBranchName(c.BaseBranch) {
		result.AddError("base_branch", "invalid git branch name (contains invalid characters or sequences)")
	}

	return result
}

// isValidGitBranchName checks if a string is a valid git branch name.
// Based on git-check-ref-format rules. Git branch names cannot:
// - Start with a dot or slash
// - End with a dot, slash, or .lock
// - Contain consecutive dots (..) or slashes (//)
// - Contain @{ (git shorthand that could cause confusion/security issues)
// - Contain backslash
// - Contain control characters, space, tilde, caret, colon, question mark, asterisk, or open bracket
// - Be empty
// Note: Leading hyphens are disallowed to prevent git option injection (e.g., "-branch"
// being interpreted as a command-line flag). Trailing hyphens are allowed per git spec.
func isValidGitBranchName(name string) bool {
	if name == "" {
		return false
	}

	// Cannot start with dot, slash, or hyphen (git interprets leading hyphen as option)
	if strings.HasPrefix(name, ".") || strings.HasPrefix(name, "/") || strings.HasPrefix(name, "-") {
		return false
	}
	// Cannot end with dot, slash, or .lock (git spec)
	if strings.HasSuffix(name, ".") || strings.HasSuffix(name, "/") || strings.HasSuffix(name, ".lock") {
		return false
	}

	// Cannot contain these patterns:
	// - ".." consecutive dots (git spec)
	// - "//" consecutive slashes (git spec)
	// - "@{" intentionally rejected to prevent git shorthand like @{upstream},
	//   @{push}, @{-1} etc. which could cause confusion or security issues
	//   when branch names are used in git commands
	// - "\\" backslash (git spec)
	invalidPatterns := []string{"..", "//", "@{", "\\"}
	for _, pattern := range invalidPatterns {
		if strings.Contains(name, pattern) {
			return false
		}
	}

	// Cannot contain these characters
	invalidChars := []rune{' ', '~', '^', ':', '?', '*', '['}
	for _, r := range name {
		for _, invalid := range invalidChars {
			if r == invalid {
				return false
			}
		}
		// Control characters (ASCII 0-31 and 127)
		if r < 32 || r == 127 {
			return false
		}
	}

	// Maximum length check (git doesn't have a hard limit, but filesystem does)
	if len(name) > 255 {
		return false
	}

	return true
}
