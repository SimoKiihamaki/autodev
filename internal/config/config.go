package config

import (
	"errors"
	"log"
	"os"
	"path/filepath"
	"strings"
	"time"

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
	DefaultMaxBatchSize = 25
)

type Flags struct {
	AllowUnsafe     bool `yaml:"allow_unsafe"`
	DryRun          bool `yaml:"dry_run"`
	SyncGit         bool `yaml:"sync_git"`
	InfiniteReviews bool `yaml:"infinite_reviews"`
}

type Timings struct {
	WaitMinutes       int `yaml:"wait_minutes"`
	ReviewPollSeconds int `yaml:"review_poll_seconds"`
	IdleGraceMinutes  int `yaml:"idle_grace_minutes"`
	MaxLocalIters     int `yaml:"max_local_iters"`
}

// BatchProcessing configures how log messages are batched for performance.
// BatchTimeoutMs: 5 provides responsive UI while minimizing CPU wake-ups for better power efficiency.
// MaxBatchSize: 25 balances throughput with memory overhead by limiting concurrent messages.
type BatchProcessing struct {
	MaxBatchSize   int `yaml:"max_batch_size"`
	BatchTimeoutMs int `yaml:"batch_timeout_ms"`
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
	PhaseExecutors    PhaseExec          `yaml:"phase_executors"`
	RunPhases         Phases             `yaml:"run_phases"`
	AllowedPythonDirs []string           `yaml:"allowed_python_dirs"`
	PRDs              map[string]PRDMeta `yaml:"prds"` // abs path -> metadata
}

// Defaults returns a sensible default config.
func Defaults() Config {
	return Config{
		ExecutorPolicy: "codex-first",
		LogLevel:       "INFO",
		PythonCommand:  "python3",
		PythonScript:   "tools/auto_prd_to_pr_v3.py",
		RepoPath:       "",
		BaseBranch:     "main",
		Branch:         "",
		CodexModel:     "gpt-5-codex",
		FollowLogs:     boolPtr(true),
		Flags: Flags{
			AllowUnsafe:     false,
			DryRun:          false,
			SyncGit:         false,
			InfiniteReviews: false,
		},
		Timings: Timings{
			WaitMinutes:       0,
			ReviewPollSeconds: 120,
			IdleGraceMinutes:  10,
			MaxLocalIters:     50,
		},
		BatchProcessing: BatchProcessing{
			MaxBatchSize:   DefaultMaxBatchSize,
			BatchTimeoutMs: 5,
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

func Load() (Config, error) {
	p, err := path()
	if err != nil {
		return Config{}, err
	}
	b, err := os.ReadFile(p)
	if errors.Is(err, os.ErrNotExist) {
		return Defaults(), nil
	}
	if err != nil {
		return Config{}, err
	}

	// Start with empty config instead of defaults to preserve explicit zero values
	var c Config
	if err := yaml.Unmarshal(b, &c); err != nil {
		return Config{}, err
	}

	// Apply defaults only for fields that weren't explicitly set
	defaults := Defaults()

	// Helper function to set default only if field is zero value
	setStringDefault := func(field *string, defaultValue string) {
		if strings.TrimSpace(*field) == "" {
			*field = defaultValue
		}
	}

	setIntDefault := func(field *int, defaultValue int) {
		if *field == 0 {
			*field = defaultValue
		}
	}

	// Apply defaults for string fields
	setStringDefault(&c.ExecutorPolicy, defaults.ExecutorPolicy)
	setStringDefault(&c.LogLevel, defaults.LogLevel)
	setStringDefault(&c.PythonCommand, defaults.PythonCommand)
	setStringDefault(&c.PythonScript, defaults.PythonScript)
	setStringDefault(&c.BaseBranch, defaults.BaseBranch)
	setStringDefault(&c.CodexModel, defaults.CodexModel)

	// For FollowLogs pointer, if not set, use default
	if c.FollowLogs == nil {
		c.FollowLogs = defaults.FollowLogs
	}

	// Apply defaults for int fields
	setIntDefault(&c.Timings.WaitMinutes, defaults.Timings.WaitMinutes)
	setIntDefault(&c.Timings.ReviewPollSeconds, defaults.Timings.ReviewPollSeconds)
	setIntDefault(&c.Timings.IdleGraceMinutes, defaults.Timings.IdleGraceMinutes)
	setIntDefault(&c.Timings.MaxLocalIters, defaults.Timings.MaxLocalIters)
	setIntDefault(&c.BatchProcessing.MaxBatchSize, defaults.BatchProcessing.MaxBatchSize)
	setIntDefault(&c.BatchProcessing.BatchTimeoutMs, defaults.BatchProcessing.BatchTimeoutMs)

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
	if c.BatchProcessing.MaxBatchSize <= 0 {
		log.Printf("Warning: max_batch_size must be > 0, got %d; using default value %d. Note: Invalid values are corrected in memory but not persisted to the config file.", c.BatchProcessing.MaxBatchSize, DefaultMaxBatchSize)
		c.BatchProcessing.MaxBatchSize = DefaultMaxBatchSize
	}

	return c, nil
}

func Save(c Config) error {
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
	return os.WriteFile(p, b, 0o600)
}

// Clone returns a deep copy of the configuration so callers can mutate the
// returned value without affecting the receiver's internal maps or slices.
func (c Config) Clone() Config {
	copyCfg := c
	if c.AllowedPythonDirs != nil {
		copyCfg.AllowedPythonDirs = append([]string(nil), c.AllowedPythonDirs...)
	}
	if c.FollowLogs != nil {
		copyCfg.FollowLogs = boolPtr(*c.FollowLogs)
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
	if c.Timings != other.Timings {
		return false
	}
	if c.BatchProcessing != other.BatchProcessing {
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
	if len(a) == 0 {
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

// boolPtr returns a pointer to a bool value.
func boolPtr(b bool) *bool {
	return &b
}
