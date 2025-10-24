package runner

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"slices"
	"testing"

	"github.com/SimoKiihamaki/autodev/internal/config"
)

func TestBuildArgsIncludesConfiguredFlags(t *testing.T) {
	t.Parallel()

	repo := t.TempDir()
	toolsDir := filepath.Join(repo, "tools")
	if err := os.MkdirAll(toolsDir, 0o755); err != nil {
		t.Fatalf("mkdir tools: %v", err)
	}
	script := filepath.Join(toolsDir, "auto_prd_to_pr_v3.py")
	if err := os.WriteFile(script, []byte("print('stub')\n"), 0o644); err != nil {
		t.Fatalf("write script: %v", err)
	}
	prd := filepath.Join(repo, "sample.md")
	if err := os.WriteFile(prd, []byte("# test"), 0o644); err != nil {
		t.Fatalf("write prd: %v", err)
	}

	cfg := config.Defaults()
	cfg.RepoPath = repo
	cfg.PythonScript = "tools/auto_prd_to_pr_v3.py"
	cfg.BaseBranch = "develop"
	cfg.Branch = "feature"
	cfg.CodexModel = "gpt-5-codex"
	cfg.Flags.DryRun = true
	cfg.Flags.SyncGit = true
	cfg.Timings.WaitMinutes = 3
	cfg.Timings.ReviewPollSeconds = 45
	cfg.Timings.IdleGraceMinutes = 2
	cfg.Timings.MaxLocalIters = 7
	cfg.RunPhases.Local = true
	cfg.RunPhases.PR = false
	cfg.RunPhases.ReviewFix = true
	cfg.ExecutorPolicy = "claude-only"

	logFile := filepath.Join(repo, "run.log")

	args := buildArgs(cfg, prd, logFile, "warning")

	if len(args) == 0 {
		t.Fatalf("buildArgs returned no arguments")
	}
	if got := args[0]; got != script {
		t.Fatalf("expected script %q, got %q", script, got)
	}

	wantContains := [][]string{
		{"--prd", prd},
		{"--repo", repo},
		{"--base", "develop"},
		{"--branch", "feature"},
		{"--codex-model", "gpt-5-codex"},
		{"--wait-minutes", "3"},
		{"--review-poll-seconds", "45"},
		{"--idle-grace-minutes", "2"},
		{"--max-local-iters", "7"},
		{"--sync-git"},
		{"--dry-run"},
		{"--phases", "local,review_fix"},
		{"--executor-policy", "claude-only"},
		{"--log-file", logFile},
		{"--log-level", "WARNING"},
	}

	for _, want := range wantContains {
		if !containsSequence(args, want...) {
			t.Fatalf("args missing %v; got %v", want, args)
		}
	}
}

func TestOptionsRunPassesEnvAndArgs(t *testing.T) {
	t.Parallel()

	repo := t.TempDir()
	script := filepath.Join(repo, "wrapper.py")
	capture := filepath.Join(repo, "capture.json")
	prd := filepath.Join(repo, "spec.md")

	if err := os.WriteFile(prd, []byte("spec"), 0o644); err != nil {
		t.Fatalf("write prd: %v", err)
	}

	stub := `import json, os, sys
target = os.environ['APRD_TEST_CAPTURE']
payload = {
    "argv": sys.argv[1:],
    "env": {k: os.environ[k] for k in os.environ if k.startswith('AUTO_PRD_') or k in {'CI', 'APRD_TEST_CAPTURE'}}
}
with open(target, 'w', encoding='utf-8') as fh:
    json.dump(payload, fh)
`
	if err := os.WriteFile(script, []byte(stub), 0o644); err != nil {
		t.Fatalf("write script: %v", err)
	}

	cfg := config.Defaults()
	cfg.RepoPath = repo
	cfg.PythonScript = script
	cfg.BaseBranch = "main"
	cfg.Branch = "branch"
	cfg.CodexModel = "gpt-5-codex"
	cfg.ExecutorPolicy = "codex-only"
	cfg.LogLevel = "debug"
	cfg.Flags.DryRun = true
	cfg.Flags.AllowUnsafe = true
	cfg.RunPhases.Local = true
	cfg.RunPhases.PR = true
	cfg.RunPhases.ReviewFix = false
	cfg.PhaseExecutors.Implement = "codex"
	cfg.PhaseExecutors.Fix = "claude"
	cfg.PhaseExecutors.ReviewFix = "claude"

	logs := make(chan Line, 64)
	opts := Options{
		Config:      cfg,
		PRDPath:     prd,
		Logs:        logs,
		LogFilePath: filepath.Join(repo, "run.log"),
		ExtraEnv:    []string{"APRD_TEST_CAPTURE=" + capture},
	}

	if err := opts.Run(context.Background()); err != nil {
		t.Fatalf("run failed: %v", err)
	}

	// Drain logs to ensure the goroutines finished.
	for range logs {
	}

	data, err := os.ReadFile(capture)
	if err != nil {
		t.Fatalf("read capture: %v", err)
	}

	var snapshot struct {
		Argv []string          `json:"argv"`
		Env  map[string]string `json:"env"`
	}
	if err := json.Unmarshal(data, &snapshot); err != nil {
		t.Fatalf("unmarshal capture: %v", err)
	}

	wantArgs := [][]string{
		{"--prd", prd},
		{"--repo", repo},
		{"--base", "main"},
		{"--branch", "branch"},
		{"--codex-model", "gpt-5-codex"},
		{"--dry-run"},
		{"--allow-unsafe-execution"},
		{"--phases", "local,pr"},
		{"--executor-policy", "codex-only"},
		{"--log-level", "DEBUG"},
	}
	for _, want := range wantArgs {
		if !containsSequence(snapshot.Argv, want...) {
			t.Fatalf("argv missing %v; got %v", want, snapshot.Argv)
		}
	}

	env := snapshot.Env
	checks := map[string]string{
		"AUTO_PRD_EXECUTOR_POLICY":        "codex-only",
		"AUTO_PRD_EXECUTOR_IMPLEMENT":     "codex",
		"AUTO_PRD_EXECUTOR_FIX":           "claude",
		"AUTO_PRD_EXECUTOR_REVIEW_FIX":    "claude",
		"AUTO_PRD_ALLOW_UNSAFE_EXECUTION": "1",
		"CI":                              "1",
	}
	for key, want := range checks {
		if got := env[key]; got != want {
			t.Fatalf("env[%s]=%q, want %q", key, got, want)
		}
	}

	if _, ok := env["AUTO_PRD_EXECUTOR_PR"]; ok {
		t.Fatalf("AUTO_PRD_EXECUTOR_PR should be unset when no override")
	}
	if got := env["APRD_TEST_CAPTURE"]; got != capture {
		t.Fatalf("capture env mismatch: %q", got)
	}
}

func containsSequence(haystack []string, needle ...string) bool {
	if len(needle) == 0 {
		return true
	}
	for i := 0; i <= len(haystack)-len(needle); i++ {
		if slices.Equal(haystack[i:i+len(needle)], needle) {
			return true
		}
	}
	return false
}
