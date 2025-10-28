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
	var c Config
	if err := yaml.Unmarshal(b, &c); err != nil {
		return Config{}, err
	}
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
	// Validate and set default MaxBatchSize
	if c.BatchProcessing.MaxBatchSize <= 0 {
		log.Printf("Warning: Invalid max_batch_size (%d), using default value %d", c.BatchProcessing.MaxBatchSize, DefaultMaxBatchSize)
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

// GetAllowedPythonDirs returns the list of allowed Python directories from the config.
// This can be extended by users to support non-standard Python installations
// (e.g., pyenv, conda, virtualenvs).
func (c Config) GetAllowedPythonDirs() []string {
	if c.AllowedPythonDirs == nil {
		return []string{}
	}
	return c.AllowedPythonDirs
}
