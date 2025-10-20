package runner

import (
	"bufio"
	"context"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/example/aprd-tui/internal/config"
)

type Line struct {
	Time time.Time
	Text string
	Err  bool
}

type Options struct {
	Config        config.Config
	PRDPath       string
	InitialPrompt string
	ExtraEnv      []string
	Logs          chan Line
}

// makeTempPRD optionally prepends an initial prompt into a temp PRD file.
func makeTempPRD(prdPath, prompt string) (string, func(), error) {
	if strings.TrimSpace(prompt) == "" {
		return prdPath, func(){}, nil
	}
	origBytes, err := os.ReadFile(prdPath)
	if err != nil {
		return "", nil, err
	}
	tmpDir := os.TempDir()
	tmpPath := filepath.Join(tmpDir, fmt.Sprintf("aprd_%d.md", time.Now().UnixNano()))
	header := fmt.Sprintf("<!-- OPERATOR_INSTRUCTION (added by aprd-tui)\n%s\n-->\n\n", prompt)
	if err := os.WriteFile(tmpPath, []byte(header+string(origBytes)), 0o644); err != nil {
		return "", nil, err
	}
	cleanup := func() { _ = os.Remove(tmpPath) }
	return tmpPath, cleanup, nil
}

func buildArgs(c config.Config, prd string) []string {
	args := []string{c.PythonScript, "--prd", prd}
	if c.RepoPath != "" {
		args = append(args, "--repo", c.RepoPath)
	}
	if c.BaseBranch != "" {
		args = append(args, "--base", c.BaseBranch)
	}
	if c.Branch != "" {
		args = append(args, "--branch", c.Branch)
	}
	if c.CodexModel != "" {
		args = append(args, "--codex-model", c.CodexModel)
	}
	if c.Flags.DryRun {
		args = append(args, "--dry-run")
	}
	if c.Flags.SyncGit {
		args = append(args, "--sync-git")
	}
	if c.Flags.InfiniteReviews {
		args = append(args, "--infinite-reviews")
	}

	// Timings
	if c.Timings.WaitMinutes > 0 {
		args = append(args, "--wait-minutes", fmt.Sprint(c.Timings.WaitMinutes))
	}
	if c.Timings.ReviewPollSeconds > 0 {
		args = append(args, "--review-poll-seconds", fmt.Sprint(c.Timings.ReviewPollSeconds))
	}
	if c.Timings.IdleGraceMinutes > 0 {
		args = append(args, "--idle-grace-minutes", fmt.Sprint(c.Timings.IdleGraceMinutes))
	}
	if c.Timings.MaxLocalIters > 0 {
		args = append(args, "--max-local-iters", fmt.Sprint(c.Timings.MaxLocalIters))
	}

	// Phases selection
	phases := []string{}
	if c.RunPhases.Local { phases = append(phases, "local") }
	if c.RunPhases.PR    { phases = append(phases, "pr") }
	if c.RunPhases.ReviewFix { phases = append(phases, "review_fix") }
	if len(phases) > 0 {
		args = append(args, "--phases", strings.Join(phases, ","))
	}

	// Executor policy
	if c.ExecutorPolicy != "" {
		args = append(args, "--executor-policy", c.ExecutorPolicy)
	}

	// Unsafe exec flag
	if c.Flags.AllowUnsafe {
		args = append(args, "--allow-unsafe-execution")
	}

	return args
}

func (o Options) Run(ctx context.Context) error {
	prd := o.PRDPath
	tmpPath, cleanup, err := makeTempPRD(prd, o.InitialPrompt)
	if err != nil {
		return err
	}
	defer cleanup()

	args := buildArgs(o.Config, tmpPath)

	// Build env
	env := os.Environ()
	if o.Config.ExecutorPolicy != "" {
		env = append(env, "AUTO_PRD_EXECUTOR_POLICY="+o.Config.ExecutorPolicy)
	}
	// Per-phase executor overrides
	if v := strings.ToLower(strings.TrimSpace(o.Config.PhaseExecutors.Implement)); v == "codex" || v == "claude" {
		env = append(env, "AUTO_PRD_EXECUTOR_IMPLEMENT="+v)
	}
	if v := strings.ToLower(strings.TrimSpace(o.Config.PhaseExecutors.Fix)); v == "codex" || v == "claude" {
		env = append(env, "AUTO_PRD_EXECUTOR_FIX="+v)
	}
	if v := strings.ToLower(strings.TrimSpace(o.Config.PhaseExecutors.PR)); v == "codex" || v == "claude" {
		env = append(env, "AUTO_PRD_EXECUTOR_PR="+v)
	}
	if v := strings.ToLower(strings.TrimSpace(o.Config.PhaseExecutors.ReviewFix)); v == "codex" || v == "claude" {
		env = append(env, "AUTO_PRD_EXECUTOR_REVIEW_FIX="+v)
	}

	if o.Config.Flags.AllowUnsafe {
		env = append(env, "AUTO_PRD_ALLOW_UNSAFE_EXECUTION=1", "CI=1")
	}
	if len(o.ExtraEnv) > 0 {
		env = append(env, o.ExtraEnv...)
	}

	cmd := exec.CommandContext(ctx, o.Config.PythonCommand, args...)
	cmd.Env = env

	stdout, err := cmd.StdoutPipe(); if err != nil { return err }
	stderr, err := cmd.StderrPipe(); if err != nil { return err }

	if err := cmd.Start(); err != nil {
		return err
	}

	go stream(stdout, false, o.Logs)
	go stream(stderr, true, o.Logs)

	waitCh := make(chan error, 1)
	go func() { waitCh <- cmd.Wait() }()

	select {
	case <-ctx.Done():
		_ = cmd.Process.Kill()
		return ctx.Err()
	case err := <-waitCh:
		return err
	}
}

func stream(r io.Reader, isErr bool, logs chan Line) {
	sc := bufio.NewScanner(r)
	for sc.Scan() {
		logs <- Line{Time: time.Now(), Text: sc.Text(), Err: isErr}
	}
	if err := sc.Err(); err != nil {
		logs <- Line{Time: time.Now(), Text: "stream error: " + err.Error(), Err: true}
	}
}
