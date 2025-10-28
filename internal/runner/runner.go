package runner

import (
	"bufio"
	"context"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"time"

	"github.com/SimoKiihamaki/autodev/internal/config"
	"github.com/google/shlex"
)

// bufferPool reuses byte buffers to reduce allocations
var bufferPool = sync.Pool{
	New: func() interface{} {
		return make([]byte, 0, 64*1024) // 64KB initial capacity
	},
}

// allowedNamePattern validates python interpreter names (e.g., "python3", "python3.9")
var allowedNamePattern = regexp.MustCompile(`^python3(\.\d+)?$`)

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
	LogFilePath   string
	LogLevel      string
}

func trySend(logs chan Line, line Line) bool {
	if logs == nil {
		return false
	}
	select {
	case logs <- line:
		return true
	default:
		return false
	}
}

func sendLine(logs chan Line, line Line) {
	_ = trySend(logs, line)
}

// makeTempPRD optionally prepends an initial prompt into a temp PRD file.
func makeTempPRD(prdPath, prompt string) (string, func(), error) {
	if strings.TrimSpace(prompt) == "" {
		return prdPath, func() {}, nil
	}
	origBytes, err := os.ReadFile(prdPath)
	if err != nil {
		return "", nil, err
	}
	tmpDir := os.TempDir()
	tmpPath := filepath.Join(tmpDir, fmt.Sprintf("aprd_%d.md", time.Now().UnixNano()))
	header := fmt.Sprintf("<!-- OPERATOR_INSTRUCTION (added by autodev TUI)\n%s\n-->\n\n", prompt)
	if err := os.WriteFile(tmpPath, []byte(header+string(origBytes)), 0o600); err != nil {
		return "", nil, err
	}
	cleanup := func() { _ = os.Remove(tmpPath) }
	return tmpPath, cleanup, nil
}

func buildArgs(c config.Config, prd string, logFile string, logLevel string) []string {
	script := c.PythonScript
	if !filepath.IsAbs(script) && strings.TrimSpace(c.RepoPath) != "" {
		candidate := filepath.Join(c.RepoPath, script)
		if abs, err := filepath.Abs(candidate); err == nil {
			if _, statErr := os.Stat(abs); statErr == nil {
				script = abs
			}
		}
	}
	args := []string{script, "--prd", prd}
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
	if c.RunPhases.Local {
		phases = append(phases, "local")
	}
	if c.RunPhases.PR {
		phases = append(phases, "pr")
	}
	if c.RunPhases.ReviewFix {
		phases = append(phases, "review_fix")
	}
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

	if logFile != "" {
		args = append(args, "--log-file", logFile)
	}

	level := strings.TrimSpace(logLevel)
	if level == "" {
		level = strings.TrimSpace(c.LogLevel)
	}
	if level == "" {
		level = "INFO"
	}
	level = strings.ToUpper(level)
	args = append(args, "--log-level", level)

	return args
}

// validatePythonCommand checks that the PythonCommand doesn't contain potentially dangerous
// shell metacharacters that could lead to command injection.
func validatePythonCommand(pythonCommand string) error {
	return validatePythonCommandWithConfig(pythonCommand, config.Config{})
}

// validatePythonCommandWithConfig checks that the PythonCommand doesn't contain potentially dangerous
// shell metacharacters that could lead to command injection. It also validates the interpreter path
// against allowed directories, with support for user configuration overrides.
// This function uses an atomic approach: it splits the command first using shlex, then validates each part.
func validatePythonCommandWithConfig(pythonCommand string, cfg config.Config) error {
	// First, split the command using shlex to properly handle quotes and escapes
	parts, err := shlex.Split(pythonCommand)
	if err != nil {
		return fmt.Errorf("failed to parse PythonCommand %q: %w", pythonCommand, err)
	}

	if len(parts) == 0 {
		return fmt.Errorf("PythonCommand is empty")
	}

	// Note: exec.Command does not invoke a shell; argument characters are not interpreted.
	// We rely on allowlisted interpreter paths/names below instead of a blanket char filter.
	// Additional check: ensure the command starts with a safe interpreter name
	// Allow common Python interpreters like python, python3, /usr/bin/python3, etc.
	interpreter := parts[0]
	// Allow absolute paths or simple interpreter names without path separators
	if strings.ContainsAny(interpreter, "/\\") {
		// If it contains path separators, it should be an absolute path
		if !filepath.IsAbs(interpreter) {
			return fmt.Errorf("PythonCommand with path must be absolute: %q", interpreter)
		}
		absPath, err := filepath.EvalSymlinks(interpreter)
		if err != nil {
			return fmt.Errorf("failed to resolve interpreter path: %v", err)
		}
		// Validate against allowed directories
		// NOTE: This is a hardcoded list of common Python installation paths.
		// This limitation exists for security reasons to prevent execution of interpreters from arbitrary locations.
		// This will fail for valid Python installations in other locations (e.g., pyenv, conda, custom paths).
		// Allowlist can be extended via config for non-standard Python installations (e.g., pyenv, conda, virtualenvs)
		defaultAllowedDirs := []string{
			// Unix-like systems
			"/usr/bin/", "/usr/local/bin/", "/opt/homebrew/bin/", "/opt/homebrew/opt/python/libexec/bin/",
			// Windows systems
			"C:\\Python3\\", "C:\\Python313\\", "C:\\Python312\\", "C:\\Python311\\", "C:\\Python310\\", "C:\\Python39\\",
			"C:\\Program Files\\Python3\\", "C:\\Program Files\\Python313\\", "C:\\Program Files\\Python312\\", "C:\\Program Files\\Python311\\", "C:\\Program Files\\Python310\\", "C:\\Program Files\\Python39\\",
			"C:\\Program Files (x86)\\Python3\\", "C:\\Program Files (x86)\\Python313\\", "C:\\Program Files (x86)\\Python312\\", "C:\\Program Files (x86)\\Python311\\", "C:\\Program Files (x86)\\Python310\\", "C:\\Program Files (x86)\\Python39\\",
			// Windows AppData paths
			"C:\\Users\\[^\\]+\\AppData\\Local\\Programs\\Python\\", "C:\\Users\\[^\\]+\\AppData\\Local\\Programs\\Python\\Python3\\",
			"C:\\Users\\[^\\]+\\AppData\\Local\\Programs\\Python\\Python313\\", "C:\\Users\\[^\\]+\\AppData\\Local\\Programs\\Python\\Python312\\", "C:\\Users\\[^\\]+\\AppData\\Local\\Programs\\Python\\Python311\\", "C:\\Users\\[^\\]+\\AppData\\Local\\Programs\\Python\\Python310\\", "C:\\Users\\[^\\]+\\AppData\\Local\\Programs\\Python\\Python39\\",
		}
		userAllowedDirs := cfg.GetAllowedPythonDirs()
		allowedDirs := append(defaultAllowedDirs, userAllowedDirs...)
		allowed := false
		for _, dir := range allowedDirs {
			// Check if the pattern contains regex characters
			if strings.ContainsAny(dir, "[]+*()^$?{}\\.|") {
				// Treat as regex pattern
				if matched, _ := regexp.MatchString(dir, absPath); matched {
					allowed = true
					break
				}
			} else {
				// Simple prefix match
				if strings.HasPrefix(absPath, dir) {
					allowed = true
					break
				}
			}
		}
		if !allowed {
			return fmt.Errorf("interpreter path %q is not in allowed directories. Add the directory to allowed_python_dirs in the config file to permit this interpreter.", absPath)
		}
	} else {
		// No path separator: must be a bare allowed name
		// Allow "python3" or "python3.x" where x is any number
		if !allowedNamePattern.MatchString(interpreter) {
			return fmt.Errorf("interpreter name %q is not allowed (must be python3 or python3.x)", interpreter)
		}
	}

	return nil
}

// sanitizedEnviron returns a copy of the current environment with the specified keys removed.
// removeKeys is a variadic list of environment variable names to exclude from the returned slice.
// The returned slice can be used as the environment for subprocesses.
//
// Example:
//
//	env := sanitizedEnviron("SECRET_KEY", "TEMP_VAR")
//
// For each environment entry, the key name is determined as the substring before the first '='.
// If an entry does not contain '=', the entire string is treated as the key name.
// Any entry whose key name matches an entry in removeKeys will be removed.
//
// Example:
//
//	env := sanitizedEnviron("SECRET_KEY", "MALFORMED_ENTRY")
//	// If environ contains: "PATH=/usr/bin", "MALFORMED_ENTRY", "SECRET_KEY=foo", "HOME=/home/user"
//	// Then "MALFORMED_ENTRY" and "SECRET_KEY=foo" will be removed since their key names match removeKeys.
func sanitizedEnviron(removeKeys ...string) []string {
	if len(removeKeys) == 0 {
		return os.Environ()
	}
	skip := make(map[string]struct{}, len(removeKeys))
	for _, key := range removeKeys {
		skip[key] = struct{}{}
	}
	env := os.Environ()
	out := make([]string, 0, len(env))
	for _, kv := range env {
		name := kv
		if idx := strings.IndexByte(kv, '='); idx >= 0 {
			name = kv[:idx]
		}
		if _, drop := skip[name]; drop {
			continue
		}
		out = append(out, kv)
	}
	return out
}

// setExecutorEnv appends executor-related environment variables to the provided environment slice.
//
// Parameters:
//
//	env - the base environment as a slice of strings in "KEY=VALUE" format.
//	executorVars - a map of environment variable names to values to be added.
//
// Returns:
//
//	A new environment slice with the executorVars added (if their value is not empty).
func setExecutorEnv(env []string, executorVars map[string]string) []string {
	for key, value := range executorVars {
		if value != "" {
			env = append(env, key+"="+value)
		}
	}
	return env
}

func (o Options) Run(ctx context.Context) error {
	prd := o.PRDPath
	tmpPath, cleanup, err := makeTempPRD(prd, o.InitialPrompt)
	if err != nil {
		return err
	}
	defer cleanup()

	args := buildArgs(o.Config, tmpPath, o.LogFilePath, o.LogLevel)

	// Build env
	env := sanitizedEnviron(
		config.EnvExecutorPolicy,
		config.EnvExecutorImplement,
		config.EnvExecutorFix,
		config.EnvExecutorPR,
		config.EnvExecutorReviewFix,
		config.EnvAllowUnsafeExecution,
		"CI",
		"PYTHONUNBUFFERED",
	)

	// Consolidated executor environment variable setting
	executorVars := map[string]string{}
	if o.Config.ExecutorPolicy != "" {
		executorVars[config.EnvExecutorPolicy] = o.Config.ExecutorPolicy
	}
	// Per-phase executor overrides
	if v := strings.ToLower(strings.TrimSpace(o.Config.PhaseExecutors.Implement)); v == "codex" || v == "claude" {
		executorVars[config.EnvExecutorImplement] = v
	}
	if v := strings.ToLower(strings.TrimSpace(o.Config.PhaseExecutors.Fix)); v == "codex" || v == "claude" {
		executorVars[config.EnvExecutorFix] = v
	}
	if v := strings.ToLower(strings.TrimSpace(o.Config.PhaseExecutors.PR)); v == "codex" || v == "claude" {
		executorVars[config.EnvExecutorPR] = v
	}
	if v := strings.ToLower(strings.TrimSpace(o.Config.PhaseExecutors.ReviewFix)); v == "codex" || v == "claude" {
		executorVars[config.EnvExecutorReviewFix] = v
	}

	if o.Config.Flags.AllowUnsafe {
		executorVars[config.EnvAllowUnsafeExecution] = "1"
		// CI=1 is removed during sanitization and re-added here when AllowUnsafe is true
		env = append(env, "CI=1")
	}

	env = setExecutorEnv(env, executorVars)
	if len(o.ExtraEnv) > 0 {
		env = append(env, o.ExtraEnv...)
	}

	// Ensure unbuffered Python output - belt-and-suspenders approach:
	// 1. PYTHONUNBUFFERED=1 environment variable (also set in tools/auto_prd/command.py)
	// 2. -u command-line flag forces unbuffered binary stdout/stderr
	// This redundancy is intentional defense-in-depth to guarantee unbuffered output
	// regardless of how the process is invoked. If you change/remove this, update both places.
	env = append(env, "PYTHONUNBUFFERED=1")

	// Support PythonCommand with interpreter flags, e.g. "python3 -X dev"
	// Validate PythonCommand to prevent command injection
	if err := validatePythonCommandWithConfig(o.Config.PythonCommand, o.Config); err != nil {
		return err
	}

	pyParts, err := shlex.Split(o.Config.PythonCommand)
	if err != nil {
		return fmt.Errorf("failed to parse PythonCommand %q: %w", o.Config.PythonCommand, err)
	}
	if len(pyParts) == 0 {
		return fmt.Errorf("PythonCommand %q resulted in no command parts after splitting", o.Config.PythonCommand)
	}
	pyBin, pyFlags := pyParts[0], pyParts[1:]

	// Use exec.Command to allow graceful Interrupt before a forced Kill on ctx cancel
	pythonArgs := make([]string, 0, len(pyFlags)+len(args)+1)
	pythonArgs = append(pythonArgs, pyFlags...)

	// Only append "-u" if not already present in pyFlags
	hasU := false
	for _, flag := range pyFlags {
		if flag == "-u" {
			hasU = true
			break
		}
	}
	if !hasU {
		pythonArgs = append(pythonArgs, "-u")
	}

	pythonArgs = append(pythonArgs, args...)
	cmd := exec.Command(pyBin, pythonArgs...)
	cmd.Env = env
	setupProcessGroup(cmd)

	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return err
	}
	stderr, err := cmd.StderrPipe()
	if err != nil {
		return err
	}

	if err := cmd.Start(); err != nil {
		return err
	}

	var wg sync.WaitGroup
	wg.Add(2)
	go func() { defer wg.Done(); stream(stdout, false, o.Logs) }()
	go func() { defer wg.Done(); stream(stderr, true, o.Logs) }()

	waitCh := make(chan error, 1)
	go func() { waitCh <- cmd.Wait() }()

	select {
	case <-ctx.Done():
		// Graceful stop: send Interrupt, then wait; kill on timeout to ensure pipes close and streams finish.
		if sigErr := interruptProcess(cmd); sigErr != nil {
			sendLine(o.Logs, Line{Time: time.Now(), Text: "failed to send interrupt: " + sigErr.Error(), Err: true})
		}
		select {
		case <-waitCh:
			// Process exited; streams will drain/finish.
		case <-time.After(2 * time.Second):
			if killErr := forceKillProcess(cmd); killErr != nil {
				sendLine(o.Logs, Line{Time: time.Now(), Text: "failed to kill process: " + killErr.Error(), Err: true})
			}
			<-waitCh
		}
		wg.Wait()
		sendLine(o.Logs, Line{Time: time.Now(), Text: "process finished", Err: false})
		if o.Logs != nil {
			close(o.Logs)
		}
		return ctx.Err()
	case err := <-waitCh:
		wg.Wait()
		sendLine(o.Logs, Line{Time: time.Now(), Text: "process finished", Err: false})
		if o.Logs != nil {
			close(o.Logs)
		}
		return err
	}
}

// stream forwards subprocess output to the log channel without blocking. When the channel
// backlog fills (UI too slow), it emits a warning and drops live-feed lines; the log file
// remains complete because writes happen synchronously on disk.
func stream(r io.Reader, isErr bool, logs chan Line) {
	if logs == nil {
		// No consumer is interested in stream output (e.g. during tests); discard to
		// keep the subprocess draining without emitting spurious log noise.
		_, _ = io.Copy(io.Discard, r)
		return
	}
	sc := bufio.NewScanner(r)
	// Get buffer from pool and allow large log lines (up to 1MB)
	buf := bufferPool.Get().([]byte)
	sc.Buffer(buf, 1<<20)
	defer func() {
		// Return buffer to pool for reuse; scanner is out of scope when this runs
		bufferPool.Put(buf[:0])
	}()

	var dropping bool
	for sc.Scan() {
		line := Line{Time: time.Now(), Text: sc.Text(), Err: isErr}
		if trySend(logs, line) {
			dropping = false
			continue
		}
		if !dropping {
			dropping = true
			msg := fmt.Sprintf("log channel backlog full (capacity %d); downstream consumer may be too slow", cap(logs))
			sendLine(logs, Line{Time: time.Now(), Text: msg, Err: true})
		}
	}
	if err := sc.Err(); err != nil {
		sendLine(logs, Line{Time: time.Now(), Text: "stream error: " + err.Error(), Err: true})
	}
}
