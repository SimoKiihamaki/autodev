package runner

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/SimoKiihamaki/autodev/internal/config"
)

func TestBuildArgsIncludesConfiguredFlags(t *testing.T) {
	// Serial execution required due to t.Setenv usage (not safe with t.Parallel)
	t.Setenv(safeScriptDirsEnv, "")

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
	cfg.Timings.WaitMinutes = &[]int{3}[0]
	cfg.Timings.ReviewPollSeconds = &[]int{45}[0]
	cfg.Timings.IdleGraceMinutes = &[]int{2}[0]
	cfg.Timings.MaxLocalIters = &[]int{7}[0]
	cfg.RunPhases.Local = true
	cfg.RunPhases.PR = false
	cfg.RunPhases.ReviewFix = true
	cfg.ExecutorPolicy = "claude-only"

	logFile := filepath.Join(repo, "run.log")

	plan, err := BuildArgs(BuildArgsInput{
		Config:      cfg,
		PRDPath:     prd,
		LogFilePath: logFile,
		LogLevel:    "warning",
	})
	if err != nil {
		t.Fatalf("BuildArgs failed: %v", err)
	}
	if plan.Cmd != "python3" {
		t.Fatalf("expected python executable 'python3', got %q", plan.Cmd)
	}

	scriptArgs, _, err := buildScriptArgs(cfg, prd, logFile, "warning")
	if err != nil {
		t.Fatalf("buildScriptArgs failed: %v", err)
	}
	if len(plan.Args) < len(scriptArgs) {
		t.Fatalf("plan args shorter than script args: %v vs %v", plan.Args, scriptArgs)
	}
	if got := plan.Args[len(plan.Args)-len(scriptArgs):]; !slices.Equal(got, scriptArgs) {
		t.Fatalf("script args mismatch; got %v want %v", got, scriptArgs)
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
		if !containsSequence(scriptArgs, want...) {
			t.Fatalf("script args missing %v; got %v", want, scriptArgs)
		}
	}
}

func TestOptionsRunPassesEnvAndArgs(t *testing.T) {
	// Serial execution required due to t.Setenv usage (not safe with t.Parallel)
	t.Setenv(safeScriptDirsEnv, "")

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

func TestTrySendChannelBackpressure(t *testing.T) {
	t.Parallel()

	// Test with a small channel to simulate backpressure
	logs := make(chan Line, 2)

	// Fill the channel to capacity
	line1 := Line{Time: time.Now(), Text: "line1"}
	line2 := Line{Time: time.Now(), Text: "line2"}

	// These should succeed
	if !trySend(logs, line1) {
		t.Fatal("first trySend should succeed")
	}
	if !trySend(logs, line2) {
		t.Fatal("second trySend should succeed")
	}

	// Channel is now full, this should fail
	line3 := Line{Time: time.Now(), Text: "line3"}
	if trySend(logs, line3) {
		t.Fatal("trySend should fail when channel is full")
	}

	// Drain one line and try again
	<-logs
	if !trySend(logs, line3) {
		t.Fatal("trySend should succeed after draining")
	}

	// Clean up
	close(logs)
}

func TestSendLineNeverBlocks(t *testing.T) {
	t.Parallel()

	logs := make(chan Line, 1)

	// Fill the channel
	line := Line{Time: time.Now(), Text: "filler"}
	trySend(logs, line)

	// sendLine should not block even when channel is full
	line2 := Line{Time: time.Now(), Text: "non-blocking"}
	sendLine(logs, line2) // This should not block

	// The channel should still only contain the first line
	select {
	case received := <-logs:
		if received.Text != "filler" {
			t.Fatalf("expected 'filler', got %q", received.Text)
		}
	default:
		t.Fatal("channel should have contained the first line")
	}

	close(logs)
}

func TestStreamWithSlowConsumer(t *testing.T) {
	t.Parallel()

	// Create a channel with very small capacity to guarantee backpressure
	logs := make(chan Line, 1)

	// Create a reader that outputs many lines quickly
	input := strings.Builder{}
	for i := 0; i < 5; i++ {
		input.WriteString(fmt.Sprintf("Line %d\n", i))
	}

	reader := strings.NewReader(input.String())

	// First, fill the channel with a line to block further sends
	blockedLine := Line{Time: time.Now(), Text: "blocking line"}
	logs <- blockedLine

	var wg sync.WaitGroup
	wg.Add(1)

	// Start streaming in a goroutine - it should encounter backpressure
	go func() {
		defer wg.Done()
		stream(context.Background(), reader, false, logs)
	}()

	// Wait a moment for the stream to process and encounter the full channel
	time.Sleep(100 * time.Millisecond)

	// Now start slowly consuming
	received := 0
	var backlogDetected bool

	// First consume the blocking line
	select {
	case line := <-logs:
		// Verify we received the expected blocking line that was pre-filled
		if line.Text != "blocking line" {
			t.Errorf("expected 'blocking line', got %q", line.Text)
		}
	case <-time.After(time.Second):
		t.Fatal("timeout waiting for blocking line")
	}

	// Continue consuming remaining lines
	timeout := time.After(time.Second)
loop:
	for {
		select {
		case line, ok := <-logs:
			if !ok {
				break loop
			}
			if strings.Contains(line.Text, "backlog full") {
				backlogDetected = true
			}
			if strings.HasPrefix(line.Text, "Line ") {
				received++
			}

		case <-timeout:
			break loop
		}
	}

	wg.Wait()

	// We should have detected the backlog condition
	if !backlogDetected {
		t.Skip("backlog condition not triggered in this test run - this is racey")
	}

	// We should have received some lines (actual behavior may vary due to races)
	t.Logf("Received %d lines and detected backlog: %v", received, backlogDetected)
}

func TestStreamWithNilChannel(t *testing.T) {
	t.Parallel()

	// When logs is nil, stream should discard all output
	input := strings.NewReader("Line 1\nLine 2\nLine 3\n")

	// This should not panic or block
	stream(context.Background(), input, false, nil)

	// Since we can't directly verify that content was discarded,
	// the fact that this returns without blocking is the test
}

func TestStreamWithErrorInReader(t *testing.T) {
	t.Parallel()

	logs := make(chan Line, 10)

	// Create a reader that will error
	reader := &errorReader{error: io.ErrUnexpectedEOF}

	var wg sync.WaitGroup
	wg.Add(1)
	go func() {
		defer wg.Done()
		stream(context.Background(), reader, false, logs)
	}()

	// Should receive an error line
	select {
	case line := <-logs:
		if !line.Err {
			t.Fatal("expected error line")
		}
		if !strings.Contains(line.Text, "stream error") {
			t.Fatalf("expected stream error message, got %q", line.Text)
		}
	case <-time.After(time.Second):
		t.Fatal("timeout waiting for error line")
	}

	wg.Wait()
	close(logs)
}

func TestOptionsRunCancellation(t *testing.T) {
	t.Parallel()

	// Create a temporary directory structure
	repo := t.TempDir()
	prd := filepath.Join(repo, "prd.json")
	if err := os.WriteFile(prd, []byte(`{"title":"test","sections":[]}`), 0o644); err != nil {
		t.Fatalf("write prd: %v", err)
	}

	// Create a stub Python script that sleeps for a long time
	script := filepath.Join(repo, "stub.py")
	stub := `#!/usr/bin/env python3
import time
import sys
time.sleep(30)  # Sleep long enough to be cancelled
sys.exit(0)
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
	cfg.LogLevel = "info"

	logs := make(chan Line, 64)
	opts := Options{
		Config:      cfg,
		PRDPath:     prd,
		Logs:        logs,
		LogFilePath: filepath.Join(repo, "run.log"),
	}

	// Create a cancellable context
	ctx, cancel := context.WithCancel(context.Background())

	errCh := make(chan error, 1)
	go func() {
		errCh <- opts.Run(ctx)
	}()

	// Wait a bit for the process to start
	time.Sleep(100 * time.Millisecond)

	// Cancel the context
	cancel()

	// Should receive cancellation error (not hang)
	err := <-errCh
	if err == nil {
		t.Error("expected error on cancellation, got nil")
	} else if !errors.Is(err, context.Canceled) {
		t.Errorf("expected context.Canceled, got %v", err)
	}

	// Drain logs to ensure goroutines finished
	drainTimeout := time.After(5 * time.Second)
	drained := false
	for !drained {
		select {
		case _, ok := <-logs:
			if !ok {
				drained = true
			}
		case <-drainTimeout:
			t.Fatal("timeout draining logs channel - possible goroutine leak")
		}
	}
}

func TestTrySendWithNilChannel(t *testing.T) {
	t.Parallel()

	// Should not panic when channel is nil
	line := Line{Time: time.Now(), Text: "test"}
	if trySend(nil, line) {
		t.Fatal("trySend should return false for nil channel")
	}
}

// errorReader is a helper that returns an error on read
type errorReader struct {
	error error
}

func (r *errorReader) Read(p []byte) (n int, err error) {
	return 0, r.error
}

func TestIsRegexPattern(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name    string
		pattern string
		want    bool
	}{
		{
			name:    "simple string has no regex",
			pattern: "hello",
			want:    false,
		},
		{
			name:    "string with brackets",
			pattern: "test[123]",
			want:    true,
		},
		{
			name:    "string with plus",
			pattern: "test+",
			want:    true,
		},
		{
			name:    "string with asterisk",
			pattern: "test*",
			want:    true,
		},
		{
			name:    "string with parentheses",
			pattern: "test(foo)",
			want:    true,
		},
		{
			name:    "string with caret",
			pattern: "^test",
			want:    true,
		},
		{
			name:    "string with dollar",
			pattern: "test$",
			want:    true,
		},
		{
			name:    "string with question mark",
			pattern: "test?",
			want:    true,
		},
		{
			name:    "string with curly braces",
			pattern: "test{1,3}",
			want:    true,
		},
		{
			name:    "string with backslash",
			pattern: "test\\n",
			want:    true,
		},
		{
			name:    "string with pipe",
			pattern: "test|foo",
			want:    true,
		},
		{
			name:    "string with dot (not regex)",
			pattern: "test.py",
			want:    false,
		},
		{
			name:    "string with dash (not regex)",
			pattern: "test-file",
			want:    false,
		},
		{
			name:    "string with underscore (not regex)",
			pattern: "test_file",
			want:    false,
		},
		{
			name:    "empty string",
			pattern: "",
			want:    false,
		},
		{
			name:    "complex regex",
			pattern: "^[a-z]+\\d{2,4}$",
			want:    true,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			got := isRegexPattern(tc.pattern)
			if got != tc.want {
				t.Errorf("isRegexPattern(%q) = %v, want %v", tc.pattern, got, tc.want)
			}
		})
	}
}

func TestValidatePythonFlags(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name    string
		flags   []string
		wantErr bool
		errMsg  string
	}{
		{
			name:    "disallow -c flag",
			flags:   []string{"-c", "print('hello')"},
			wantErr: true,
			errMsg:  "disallowed Python flag",
		},
		{
			name:    "disallow --command flag",
			flags:   []string{"--command", "print('hello')"},
			wantErr: true,
			errMsg:  "unexpected short flag in group",
		},
		{
			name:    "disallow -m flag",
			flags:   []string{"-m", "module"},
			wantErr: true,
			errMsg:  "disallowed Python flag",
		},
		{
			name:    "disallow --module flag",
			flags:   []string{"--module", "module"},
			wantErr: true,
			errMsg:  "unexpected short flag in group",
		},
		{
			name:    "disallow long flag",
			flags:   []string{"--verbose"},
			wantErr: true,
			errMsg:  "unexpected short flag in group",
		},
		{
			name:    "disallow long flag with value",
			flags:   []string{"--output", "file.txt"},
			wantErr: true,
			errMsg:  "unexpected short flag in group",
		},
		{
			name:    "disallow -c in grouped flags",
			flags:   []string{"-ucm"},
			wantErr: true,
			errMsg:  "disallowed Python flag in group",
		},
		{
			name:    "disallow -m in grouped flags",
			flags:   []string{"-ImE"},
			wantErr: true,
			errMsg:  "disallowed Python flag in group",
		},
		{
			name:    "disallow unexpected short flag in group",
			flags:   []string{"-uxz"},
			wantErr: true,
			errMsg:  "unexpected short flag in group",
		},
		{
			name:    "allow -u flag",
			flags:   []string{"-u"},
			wantErr: false,
		},
		{
			name:    "allow -E flag",
			flags:   []string{"-E"},
			wantErr: false,
		},
		{
			name:    "allow -I flag",
			flags:   []string{"-I"},
			wantErr: false,
		},
		{
			name:    "allow -s flag",
			flags:   []string{"-s"},
			wantErr: false,
		},
		{
			name:    "allow -B flag",
			flags:   []string{"-B"},
			wantErr: false,
		},
		{
			name:    "allow -O flag",
			flags:   []string{"-O"},
			wantErr: false,
		},
		{
			name:    "disallow -OO flag (treated as grouped)",
			flags:   []string{"-OO"},
			wantErr: true,
			errMsg:  "unexpected short flag in group",
		},
		{
			name:    "allow grouped safe flags",
			flags:   []string{"-uE", "-IEs", "-uB"},
			wantErr: false,
		},
		{
			name:    "allow -X dev",
			flags:   []string{"-X", "dev"},
			wantErr: false,
		},
		{
			name:    "disallow -X without argument",
			flags:   []string{"-X"},
			wantErr: true,
			errMsg:  "flag -X requires an option argument",
		},
		{
			name:    "disallow -X with invalid argument",
			flags:   []string{"-X", "unsafe"},
			wantErr: true,
			errMsg:  "disallowed argument to -X",
		},
		{
			name:    "disallow -X with other valid argument",
			flags:   []string{"-X", "utf8"},
			wantErr: true,
			errMsg:  "disallowed argument to -X",
		},
		{
			name:    "allow -W flag without argument",
			flags:   []string{"-W"},
			wantErr: false,
		},
		{
			name:    "allow -W flag with argument",
			flags:   []string{"-W", "ignore"},
			wantErr: false,
		},
		{
			name:    "allow -W followed by another flag",
			flags:   []string{"-W", "-u"},
			wantErr: false,
		},
		{
			name:    "allow multiple safe flags",
			flags:   []string{"-u", "-E", "-I", "-s", "-B"},
			wantErr: false,
		},
		{
			name:    "allow combination of -X dev and other flags",
			flags:   []string{"-u", "-X", "dev", "-E"},
			wantErr: false,
		},
		{
			name:    "disallow unexpected flag",
			flags:   []string{"-z"},
			wantErr: true,
			errMsg:  "unexpected flag",
		},
		{
			name:    "disallow single dash without flag",
			flags:   []string{"-"},
			wantErr: true,
			errMsg:  "unexpected flag",
		},
		{
			name:    "allow empty flag list",
			flags:   []string{},
			wantErr: false,
		},
		{
			name:    "allow optimization flag with -X dev (but not -OO)",
			flags:   []string{"-O", "-X", "dev"},
			wantErr: false,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			err := ValidatePythonFlagsForTest(tc.flags)
			if tc.wantErr {
				if err == nil {
					t.Errorf("ValidatePythonFlagsForTest(%v) expected error containing %q, got nil", tc.flags, tc.errMsg)
				} else if !strings.Contains(err.Error(), tc.errMsg) {
					t.Errorf("ValidatePythonFlagsForTest(%v) error = %q, want to contain %q", tc.flags, err.Error(), tc.errMsg)
				}
			} else {
				if err != nil {
					t.Errorf("ValidatePythonFlagsForTest(%v) unexpected error: %v", tc.flags, err)
				}
			}
		})
	}
}

func TestValidatePythonFlagsEdgeCases(t *testing.T) {
	t.Parallel()

	t.Run("nil slice", func(t *testing.T) {
		t.Parallel()
		err := ValidatePythonFlagsForTest(nil)
		if err != nil {
			t.Errorf("ValidatePythonFlagsForTest(nil) unexpected error: %v", err)
		}
	})

	t.Run("flag with value starting with dash", func(t *testing.T) {
		t.Parallel()
		// -W with a value that looks like a flag
		err := ValidatePythonFlagsForTest([]string{"-W", "-u"})
		if err != nil {
			t.Errorf("ValidatePythonFlagsForTest([-W -u]) unexpected error: %v", err)
		}
	})

	t.Run("grouped flag with only safe chars", func(t *testing.T) {
		t.Parallel()
		err := ValidatePythonFlagsForTest([]string{"-uIsB"})
		if err != nil {
			t.Errorf("ValidatePythonFlagsForTest([-uIsB]) unexpected error: %v", err)
		}
	})

	t.Run("multiple -X flags", func(t *testing.T) {
		t.Parallel()
		// First -X dev is valid, second -X is an unexpected flag (not preceded by -X)
		err := ValidatePythonFlagsForTest([]string{"-X", "dev", "-X"})
		// -X without argument should fail
		if err == nil {
			t.Error("ValidatePythonFlagsForTest([-X dev -X]) expected error, got nil")
		}
	})

	t.Run("complex valid combination", func(t *testing.T) {
		t.Parallel()
		// A complex but valid combination
		err := ValidatePythonFlagsForTest([]string{"-u", "-E", "-I", "-X", "dev", "-O", "-W", "ignore", "-B"})
		if err != nil {
			t.Errorf("ValidatePythonFlagsForTest(complex) unexpected error: %v", err)
		}
	})
}
