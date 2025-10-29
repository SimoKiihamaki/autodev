package runner

import (
	"errors"
	"os"
	"path/filepath"
	"testing"

	"github.com/SimoKiihamaki/autodev/internal/config"
)

// envSliceToMap flattens the env slice returned by BuildArgs for assertions.
func envSliceToMap(env []string) map[string]string {
	out := make(map[string]string, len(env))
	for _, kv := range env {
		if kv == "" {
			continue
		}
		key := kv
		val := ""
		if idx := indexOfEqual(kv); idx >= 0 {
			key = kv[:idx]
			val = kv[idx+1:]
		}
		out[key] = val
	}
	return out
}

// indexOfEqual is a tiny helper so tests remain self-contained without strings imports.
func indexOfEqual(s string) int {
	for i := 0; i < len(s); i++ {
		if s[i] == '=' {
			return i
		}
	}
	return -1
}

func firstToken(input string) string {
	for i := 0; i < len(input); i++ {
		if input[i] == ' ' || input[i] == '\t' {
			return input[:i]
		}
	}
	return input
}

func countOccurrences(items []string, target string) int {
	count := 0
	for _, item := range items {
		if item == target {
			count++
		}
	}
	return count
}

func containsSequence(haystack []string, needle ...string) bool {
	if len(needle) == 0 {
		return true
	}
outer:
	for i := 0; i <= len(haystack)-len(needle); i++ {
		for j := range needle {
			if haystack[i+j] != needle[j] {
				continue outer
			}
		}
		return true
	}
	return false
}

func TestBuildArgsArgumentMapping(t *testing.T) {
	t.Parallel()

	repo := t.TempDir()
	toolsDir := filepath.Join(repo, "tools")
	if err := os.MkdirAll(toolsDir, 0o755); err != nil {
		t.Fatalf("mkdir tools: %v", err)
	}
	scriptRel := filepath.Join("tools", "auto_prd_to_pr_v3.py")
	scriptAbs := filepath.Join(repo, scriptRel)
	if err := os.WriteFile(scriptAbs, []byte("print('stub')\n"), 0o644); err != nil {
		t.Fatalf("write script: %v", err)
	}

	// Resolve symlinks in script path since security code does symlink resolution
	resolvedScript, err := filepath.EvalSymlinks(scriptAbs)
	if err != nil {
		// If symlink resolution fails, use the original path
		resolvedScript = scriptAbs
	}
	prd := filepath.Join(repo, "spec.md")
	if err := os.WriteFile(prd, []byte("# spec"), 0o644); err != nil {
		t.Fatalf("write prd: %v", err)
	}

	logFile := filepath.Join(repo, "run.log")

	baseCfg := config.Defaults()
	baseCfg.RepoPath = repo
	baseCfg.PythonScript = scriptRel
	baseCfg.BaseBranch = "develop"
	baseCfg.Branch = "feature/flags"
	baseCfg.CodexModel = "gpt-5.1-codex"
	baseCfg.LogLevel = "debug"
	baseCfg.Timings = config.Timings{
		WaitMinutes:       &[]int{7}[0],
		ReviewPollSeconds: &[]int{33}[0],
		IdleGraceMinutes:  &[]int{5}[0],
		MaxLocalIters:     &[]int{11}[0],
	}
	baseCfg.RunPhases = config.Phases{Local: true, PR: false, ReviewFix: false}

	baseInput := BuildArgsInput{
		Config:      baseCfg,
		PRDPath:     prd,
		LogFilePath: logFile,
		LogLevel:    "",
	}

	tests := []struct {
		name        string
		mutate      func(cfg *config.Config, input *BuildArgsInput)
		expectArgs  [][]string
		expectEnv   map[string]string
		expectUnset []string
		extraCheck  func(t *testing.T, plan Args, cfg config.Config)
	}{
		{
			name: "defaults_map_core_fields",
			expectArgs: [][]string{
				{resolvedScript},
				{"--prd", prd},
				{"--repo", repo},
				{"--base", "develop"},
				{"--branch", "feature/flags"},
				{"--codex-model", "gpt-5.1-codex"},
				{"--wait-minutes", "7"},
				{"--review-poll-seconds", "33"},
				{"--idle-grace-minutes", "5"},
				{"--max-local-iters", "11"},
				{"--phases", "local"},
				{"--log-file", logFile},
				{"--log-level", "DEBUG"},
			},
			expectEnv: map[string]string{
				config.EnvExecutorPolicy: baseCfg.ExecutorPolicy,
				"PYTHONUNBUFFERED":       "1",
			},
			expectUnset: []string{"CI", config.EnvAllowUnsafeExecution},
		},
		{
			name: "flags_enable_all",
			mutate: func(cfg *config.Config, input *BuildArgsInput) {
				cfg.Flags.AllowUnsafe = true
				cfg.Flags.DryRun = true
				cfg.Flags.SyncGit = true
				cfg.Flags.InfiniteReviews = true
			},
			expectArgs: [][]string{
				{"--allow-unsafe-execution"},
				{"--dry-run"},
				{"--sync-git"},
				{"--infinite-reviews"},
			},
			expectEnv: map[string]string{
				config.EnvAllowUnsafeExecution: "1",
				"CI":                           "1",
			},
		},
		{
			name: "phases_combinations",
			mutate: func(cfg *config.Config, input *BuildArgsInput) {
				cfg.RunPhases = config.Phases{Local: false, PR: true, ReviewFix: true}
			},
			expectArgs: [][]string{
				{"--phases", "pr,review_fix"},
			},
		},
		{
			name: "log_level_override_respected",
			mutate: func(cfg *config.Config, input *BuildArgsInput) {
				input.LogLevel = "warning"
			},
			expectArgs: [][]string{
				{"--log-level", "WARNING"},
			},
		},
		{
			name: "python_command_preserves_u_flag",
			mutate: func(cfg *config.Config, input *BuildArgsInput) {
				cfg.PythonCommand = "python3 -O -u"
			},
			expectArgs: [][]string{
				{resolvedScript},
			},
			extraCheck: func(t *testing.T, plan Args, cfg config.Config) {
				t.Helper()
				if plan.Cmd != firstToken(cfg.PythonCommand) {
					t.Fatalf("expected command %q, got %q", firstToken(cfg.PythonCommand), plan.Cmd)
				}
				if countOccurrences(plan.Args, "-u") != 1 {
					t.Fatalf("expected exactly one -u flag, args=%v", plan.Args)
				}
				if !containsSequence(plan.Args, "-O") {
					t.Fatalf("expected optimiser flag to persist, args=%v", plan.Args)
				}
			},
		},
	}

	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			cfg := baseCfg.Clone()
			input := baseInput
			input.Config = cfg
			if tc.mutate != nil {
				tc.mutate(&cfg, &input)
			}
			input.Config = cfg

			plan, err := BuildArgs(input)
			if err != nil {
				t.Fatalf("BuildArgs failed: %v", err)
			}

			wantCmd := firstToken(cfg.PythonCommand)
			if plan.Cmd != wantCmd {
				t.Fatalf("plan.Cmd=%q want %q", plan.Cmd, wantCmd)
			}

			for _, seq := range tc.expectArgs {
				if !containsSequence(plan.Args, seq...) {
					t.Fatalf("args %v missing sequence %v", plan.Args, seq)
				}
			}

			env := envSliceToMap(plan.Env)
			for key, want := range tc.expectEnv {
				if got := env[key]; got != want {
					t.Fatalf("env[%s]=%q want %q", key, got, want)
				}
			}
			for _, absent := range tc.expectUnset {
				if _, ok := env[absent]; ok {
					t.Fatalf("env[%s] unexpectedly present: %q", absent, env[absent])
				}
			}
			if tc.extraCheck != nil {
				tc.extraCheck(t, plan, cfg)
			}
		})
	}
}

func TestBuildArgsPhaseExecutorEnvs(t *testing.T) {
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
	prd := filepath.Join(repo, "spec.md")
	if err := os.WriteFile(prd, []byte("# spec"), 0o644); err != nil {
		t.Fatalf("write prd: %v", err)
	}

	baseCfg := config.Defaults()
	baseCfg.RepoPath = repo
	baseCfg.PythonScript = script

	input := BuildArgsInput{
		Config:      baseCfg,
		PRDPath:     prd,
		LogFilePath: filepath.Join(repo, "run.log"),
	}

	tests := []struct {
		name       string
		configure  func(cfg *config.Config)
		wantEnv    map[string]string
		unexpected []string
	}{
		{
			name: "no_overrides_only_policy",
			wantEnv: map[string]string{
				config.EnvExecutorPolicy: baseCfg.ExecutorPolicy,
			},
			unexpected: []string{
				config.EnvExecutorImplement,
				config.EnvExecutorFix,
				config.EnvExecutorPR,
				config.EnvExecutorReviewFix,
			},
		},
		{
			name: "per_phase_overrides_set",
			configure: func(cfg *config.Config) {
				cfg.PhaseExecutors.Implement = "codex"
				cfg.PhaseExecutors.Fix = "claude"
				cfg.PhaseExecutors.PR = "invalid"
				cfg.PhaseExecutors.ReviewFix = "claude"
			},
			wantEnv: map[string]string{
				config.EnvExecutorPolicy:    baseCfg.ExecutorPolicy,
				config.EnvExecutorImplement: "codex",
				config.EnvExecutorFix:       "claude",
				config.EnvExecutorReviewFix: "claude",
			},
			unexpected: []string{
				config.EnvExecutorPR,
			},
		},
	}

	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			cfg := baseCfg.Clone()
			if tc.configure != nil {
				tc.configure(&cfg)
			}
			input.Config = cfg

			plan, err := BuildArgs(input)
			if err != nil {
				t.Fatalf("BuildArgs failed: %v", err)
			}

			env := envSliceToMap(plan.Env)
			for key, want := range tc.wantEnv {
				if got := env[key]; got != want {
					t.Fatalf("env[%s]=%q want %q", key, got, want)
				}
			}
			for _, unexpected := range tc.unexpected {
				if val, ok := env[unexpected]; ok {
					t.Fatalf("env[%s] unexpectedly present: %q", unexpected, val)
				}
			}
		})
	}
}

func TestBuildArgsAllowsInstalledScriptWithoutRepoPath(t *testing.T) {
	exePath, err := os.Executable()
	if err != nil {
		t.Fatalf("os.Executable: %v", err)
	}

	exeDir := filepath.Dir(exePath)
	toolsDir := filepath.Join(exeDir, "tools")
	if err := os.MkdirAll(toolsDir, 0o755); err != nil {
		t.Fatalf("mkdir tools next to executable: %v", err)
	}

	script := filepath.Join(toolsDir, "auto_prd_to_pr_v3.py")
	created := false
	if _, err := os.Stat(script); errors.Is(err, os.ErrNotExist) {
		if writeErr := os.WriteFile(script, []byte("print('ok')\n"), 0o755); writeErr != nil {
			t.Fatalf("write script: %v", writeErr)
		}
		created = true
	}
	if created {
		t.Cleanup(func() {
			_ = os.Remove(script)
		})
	}

	prdDir := t.TempDir()
	prd := filepath.Join(prdDir, "spec.md")
	if err := os.WriteFile(prd, []byte("# spec"), 0o600); err != nil {
		t.Fatalf("write prd: %v", err)
	}

	cfg := config.Defaults()
	cfg.RepoPath = ""
	cfg.PythonScript = script
	cfg.RunPhases = config.Phases{Local: true, PR: false, ReviewFix: false}

	input := BuildArgsInput{
		Config:      cfg,
		PRDPath:     prd,
		LogFilePath: filepath.Join(prdDir, "run.log"),
	}

	if _, err := BuildArgs(input); err != nil {
		t.Fatalf("BuildArgs rejected installed script without repo path: %v", err)
	}
}

func TestBuildArgsInfersRepoPathWhenUnset(t *testing.T) {
	repo := t.TempDir()
	if err := os.Mkdir(filepath.Join(repo, ".git"), 0o755); err != nil {
		t.Fatalf("mkdir .git: %v", err)
	}
	toolsDir := filepath.Join(repo, "tools")
	if err := os.MkdirAll(toolsDir, 0o755); err != nil {
		t.Fatalf("mkdir tools: %v", err)
	}
	script := filepath.Join(toolsDir, "auto_prd_to_pr_v3.py")
	if err := os.WriteFile(script, []byte("print('ok')\n"), 0o755); err != nil {
		t.Fatalf("write script: %v", err)
	}

	prd := filepath.Join(repo, "docs", "spec.md")
	if err := os.MkdirAll(filepath.Dir(prd), 0o755); err != nil {
		t.Fatalf("mkdir docs: %v", err)
	}
	if err := os.WriteFile(prd, []byte("# spec"), 0o600); err != nil {
		t.Fatalf("write prd: %v", err)
	}

	cfg := config.Defaults()
	cfg.RepoPath = ""
	cfg.PythonScript = script
	cfg.RunPhases = config.Phases{Local: true, PR: false, ReviewFix: false}

	input := BuildArgsInput{
		Config:      cfg,
		PRDPath:     prd,
		LogFilePath: filepath.Join(repo, "run.log"),
	}

	plan, err := BuildArgs(input)
	if err != nil {
		t.Fatalf("BuildArgs failed: %v", err)
	}

	repoArg := ""
	for i := 0; i < len(plan.Args)-1; i++ {
		if plan.Args[i] == "--repo" {
			repoArg = plan.Args[i+1]
			break
		}
	}
	if repoArg == "" {
		t.Fatalf("expected --repo argument in args %v", plan.Args)
	}
	gotResolved, err := filepath.EvalSymlinks(repoArg)
	if err != nil {
		t.Fatalf("eval symlinks for repo arg: %v", err)
	}
	wantResolved, err := filepath.EvalSymlinks(repo)
	if err != nil {
		t.Fatalf("eval symlinks for repo: %v", err)
	}
	if gotResolved != wantResolved {
		t.Fatalf("expected inferred repo %q (resolved %q), got %q (resolved %q)", repo, wantResolved, repoArg, gotResolved)
	}
}
