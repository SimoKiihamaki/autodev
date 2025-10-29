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

// allowedNamePattern validates python interpreter names (e.g., "python", "python2", "python2.7", "python3", "python3.9")
var allowedNamePattern = regexp.MustCompile(`^python(\d)?(\.\d+)?$`)

// uFlagPattern matches valid short option groups containing 'u', e.g. -uc, -Eu, -cEu, etc.
var uFlagPattern = regexp.MustCompile(`^-[a-zA-Z]*u[a-zA-Z]*$`)

// isPrefixOf checks if a prefix path is a prefix of another path, handling path separators correctly
func isPrefixOf(prefix, path string) bool {
	// Clean both paths to handle trailing separators consistently
	cleanPrefix := filepath.Clean(prefix)
	cleanPath := filepath.Clean(path)

	// Check for exact match before appending separator
	if cleanPath == cleanPrefix {
		return true
	}
	// Ensure prefix ends with a path separator
	if !strings.HasSuffix(cleanPrefix, string(os.PathSeparator)) {
		cleanPrefix = cleanPrefix + string(os.PathSeparator)
	}
	return strings.HasPrefix(cleanPath, cleanPrefix)
}

// hasUnbufferedFlag checks if the unbuffered flag is already present in the given flags
func hasUnbufferedFlag(flags []string) bool {
	for _, flag := range flags {
		// Check for literal -u flag
		if flag == "-u" {
			return true
		}
		// Check if -u is in a valid short option group (e.g. -uc, -Eu, -cEu)
		if uFlagPattern.MatchString(flag) {
			return true
		}
		// Check for long form --unbuffered
		if flag == "--unbuffered" {
			return true
		}
	}
	return false
}

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

// Args holds the fully constructed command invocation for the automation runner.
// Cmd is the executable, Args are the positional/flag arguments (excluding Cmd),
// and Env contains the complete environment slice to pass to exec.Command.
type Args struct {
	Cmd  string
	Args []string
	Env  []string
}

// BuildArgsInput captures the data required to translate a Config into process
// arguments. Fields that originate from transient UI state (PRD selection,
// log file destination, runtime log level override) are surfaced explicitly
// so tests can exercise the full mapping deterministically.
type BuildArgsInput struct {
	Config      config.Config
	PRDPath     string
	LogFilePath string
	LogLevel    string
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
		return "", nil, fmt.Errorf("reading PRD %s: %w", prdPath, err)
	}
	tmpDir := os.TempDir()
	tmpPath := filepath.Join(tmpDir, fmt.Sprintf("aprd_%d.md", time.Now().UnixNano()))
	header := fmt.Sprintf("<!-- OPERATOR_INSTRUCTION (added by autodev TUI)\n%s\n-->\n\n", prompt)
	if err := os.WriteFile(tmpPath, []byte(header+string(origBytes)), 0o600); err != nil {
		return "", nil, fmt.Errorf("writing temporary PRD %s: %w", tmpPath, err)
	}
	cleanup := func() { _ = os.Remove(tmpPath) }
	return tmpPath, cleanup, nil
}

// validatePythonScriptPath validates that the PythonScript path is safe and doesn't escape expected directories
func validatePythonScriptPath(scriptPath, repoPath string) error {
	// If script path is absolute, validate it directly
	if filepath.IsAbs(scriptPath) {
		// Use filepath.Clean to normalize the path
		cleaned := filepath.Clean(scriptPath)
		if repoPath != "" {
			relPath, err := filepath.Rel(repoPath, cleaned)
			if err != nil {
				return fmt.Errorf("PythonScript absolute path cannot be resolved relative to repo: %q", scriptPath)
			}
			if strings.HasPrefix(relPath, "..") {
				return fmt.Errorf("PythonScript absolute path would escape repository directory: %q", scriptPath)
			}
		}
		return nil
	}

	// For relative paths, check if they would escape the repo when resolved
	if repoPath != "" {
		absScript := filepath.Join(repoPath, scriptPath)
		relPath, err := filepath.Rel(repoPath, absScript)
		if err != nil {
			return fmt.Errorf("PythonScript path cannot be resolved relative to repo: %q", scriptPath)
		}
		// If the relative path starts with "..", it would escape the repo directory
		if strings.HasPrefix(relPath, "..") {
			return fmt.Errorf("PythonScript path would escape repository directory: %q", scriptPath)
		}
	}

	return nil
}

func buildScriptArgs(cfg config.Config, prdPath, logFilePath, logLevel string) ([]string, error) {
	script := cfg.PythonScript

	// Validate script path for security
	if err := validatePythonScriptPath(script, cfg.RepoPath); err != nil {
		return nil, err
	}

	if !filepath.IsAbs(script) && strings.TrimSpace(cfg.RepoPath) != "" {
		candidate := filepath.Join(cfg.RepoPath, script)
		if abs, err := filepath.Abs(candidate); err == nil {
			if _, statErr := os.Stat(abs); statErr == nil {
				script = abs
			}
		}
	}
	args := []string{script, "--prd", prdPath}
	if cfg.RepoPath != "" {
		args = append(args, "--repo", cfg.RepoPath)
	}
	if cfg.BaseBranch != "" {
		args = append(args, "--base", cfg.BaseBranch)
	}
	if cfg.Branch != "" {
		args = append(args, "--branch", cfg.Branch)
	}
	if cfg.CodexModel != "" {
		args = append(args, "--codex-model", cfg.CodexModel)
	}
	if cfg.Flags.DryRun {
		args = append(args, "--dry-run")
	}
	if cfg.Flags.SyncGit {
		args = append(args, "--sync-git")
	}
	if cfg.Flags.InfiniteReviews {
		args = append(args, "--infinite-reviews")
	}

	// Timings
	if cfg.Timings.WaitMinutes > 0 {
		args = append(args, "--wait-minutes", fmt.Sprint(cfg.Timings.WaitMinutes))
	}
	if cfg.Timings.ReviewPollSeconds > 0 {
		args = append(args, "--review-poll-seconds", fmt.Sprint(cfg.Timings.ReviewPollSeconds))
	}
	if cfg.Timings.IdleGraceMinutes > 0 {
		args = append(args, "--idle-grace-minutes", fmt.Sprint(cfg.Timings.IdleGraceMinutes))
	}
	if cfg.Timings.MaxLocalIters > 0 {
		args = append(args, "--max-local-iters", fmt.Sprint(cfg.Timings.MaxLocalIters))
	}

	// Phases selection
	phases := []string{}
	if cfg.RunPhases.Local {
		phases = append(phases, "local")
	}
	if cfg.RunPhases.PR {
		phases = append(phases, "pr")
	}
	if cfg.RunPhases.ReviewFix {
		phases = append(phases, "review_fix")
	}
	if len(phases) > 0 {
		args = append(args, "--phases", strings.Join(phases, ","))
	}

	// Executor policy
	if cfg.ExecutorPolicy != "" {
		args = append(args, "--executor-policy", cfg.ExecutorPolicy)
	}

	// Unsafe exec flag
	if cfg.Flags.AllowUnsafe {
		args = append(args, "--allow-unsafe-execution")
	}

	if logFilePath != "" {
		args = append(args, "--log-file", logFilePath)
	}

	level := strings.TrimSpace(logLevel)
	if level == "" {
		level = strings.TrimSpace(cfg.LogLevel)
	}
	if level == "" {
		level = "INFO"
	}
	level = strings.ToUpper(level)
	args = append(args, "--log-level", level)

	return args, nil
}

// BuildArgs converts the provided configuration into the final command, arguments,
// and environment required to invoke the automation runner. It centralizes all
// mappings so TUI and tests can validate behavior via a single entry point.
func BuildArgs(input BuildArgsInput) (Args, error) {
	// Validate PythonCommand early for security - reject invalid/malicious commands before any processing
	if err := validatePythonCommandWithConfig(input.Config.PythonCommand, input.Config); err != nil {
		return Args{}, err
	}

	scriptArgs, err := buildScriptArgs(input.Config, input.PRDPath, input.LogFilePath, input.LogLevel)
	if err != nil {
		return Args{}, err
	}

	// Build env
	// Remove CI environment variable to prevent unintended CI behavior in the automation script
	// CI will only be re-added when AllowUnsafe is explicitly enabled
	env := sanitizedEnviron(
		config.EnvExecutorPolicy,
		config.EnvExecutorImplement,
		config.EnvExecutorFix,
		config.EnvExecutorPR,
		config.EnvExecutorReviewFix,
		config.EnvAllowUnsafeExecution,
		"CI",
	)

	// Consolidated executor environment variable setting
	executorVars := map[string]string{}
	if input.Config.ExecutorPolicy != "" {
		executorVars[config.EnvExecutorPolicy] = input.Config.ExecutorPolicy
	}
	// Per-phase executor overrides
	if v := strings.ToLower(strings.TrimSpace(input.Config.PhaseExecutors.Implement)); v == "codex" || v == "claude" {
		executorVars[config.EnvExecutorImplement] = v
	}
	if v := strings.ToLower(strings.TrimSpace(input.Config.PhaseExecutors.Fix)); v == "codex" || v == "claude" {
		executorVars[config.EnvExecutorFix] = v
	}
	if v := strings.ToLower(strings.TrimSpace(input.Config.PhaseExecutors.PR)); v == "codex" || v == "claude" {
		executorVars[config.EnvExecutorPR] = v
	}
	if v := strings.ToLower(strings.TrimSpace(input.Config.PhaseExecutors.ReviewFix)); v == "codex" || v == "claude" {
		executorVars[config.EnvExecutorReviewFix] = v
	}

	if input.Config.Flags.AllowUnsafe {
		executorVars[config.EnvAllowUnsafeExecution] = "1"
		// CI=1 is removed during sanitization and re-added here when AllowUnsafe is true
		env = append(env, "CI=1")
	}

	env = setExecutorEnv(env, executorVars)

	// Ensure unbuffered Python output - belt-and-suspenders approach:
	// 1. PYTHONUNBUFFERED=1 environment variable (also set in tools/auto_prd/command.py)
	// 2. -u command-line flag forces unbuffered binary stdout/stderr
	// This redundancy is intentional defense-in-depth to guarantee unbuffered output
	// regardless of how the process is invoked. If you change/remove this, update both places.
	env = append(env, "PYTHONUNBUFFERED=1")

	// Support PythonCommand with interpreter flags, e.g. "python3 -X dev"

	pyParts, err := shlex.Split(input.Config.PythonCommand)
	if err != nil {
		return Args{}, fmt.Errorf("failed to parse PythonCommand %q: %w", input.Config.PythonCommand, err)
	}
	if len(pyParts) == 0 {
		return Args{}, fmt.Errorf("PythonCommand %q resulted in no command parts after splitting", input.Config.PythonCommand)
	}
	pyBin, pyFlags := pyParts[0], pyParts[1:]

	// Compute capacity dynamically: add 1 only if "-u" will be appended
	needUnbuffered := !hasUnbufferedFlag(pyFlags)
	capacity := len(pyFlags) + len(scriptArgs)
	if needUnbuffered {
		capacity++
	}
	pythonArgs := make([]string, 0, capacity)
	pythonArgs = append(pythonArgs, pyFlags...)
	if needUnbuffered {
		pythonArgs = append(pythonArgs, "-u")
	}

	pythonArgs = append(pythonArgs, scriptArgs...)

	return Args{
		Cmd:  pyBin,
		Args: pythonArgs,
		Env:  env,
	}, nil
}

// isRegexPattern checks if a string contains regex metacharacters that would require
// regex matching instead of simple string operations.
func isRegexPattern(pattern string) bool {
	return strings.ContainsAny(pattern, "[]+*()^$?{}\\|")
}

// validatePythonCommandWithConfig performs critical security validation of the PythonCommand string.
//
// SECURITY RATIONALE:
// Threat model: Prevent command injection via shell metacharacters in user-supplied PythonCommand.
// This function does NOT invoke a shell (exec.Command is used), but we must still ensure that only
// known-safe interpreter names/paths and flags are allowed, to prevent bypasses or abuse.
// The allowlist approach is chosen to strictly permit only recognized Python interpreter names/paths
// (e.g., "python3", "/usr/bin/python3") and safe flags, rejecting anything unexpected.
// The command is split using shlex to handle quoting/escaping safely, and each part is validated.
// This ensures that even if a user attempts to inject shell metacharacters or unexpected arguments,
// they will be rejected unless explicitly allowed.
//
// Future maintainers: Do not relax these checks without a thorough security review.
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
		// At this point, absPath holds the resolved symlink target. All validation below is performed on this resolved path.
		// Validate resolved path against allowed directories (after symlink resolution)
		// NOTE: This is a hardcoded list of common Python installation paths.
		// This limitation exists for security reasons to prevent execution of interpreters from arbitrary locations.
		// This will fail for valid Python installations in other locations (e.g., pyenv, conda, custom paths).
		// Allowlist can be extended via the allowed_python_dirs config field for non-standard Python installations.
		// See the error message returned below (at line 342) for instructions on configuring allowed_python_dirs.
		// Symlink validation ensures the resolved path itself is in an allowed directory.

		// Simple prefix matches for Unix-like systems
		defaultAllowedPrefixes := []string{
			"/usr/bin/", "/usr/local/bin/", "/opt/homebrew/bin/", "/opt/homebrew/opt/python/libexec/bin/",
			"/opt/python/bin/", "/usr/lib/",
		}
		// Add user-local bin directory (e.g., ~/.local/bin/) if available
		if home, err := os.UserHomeDir(); err == nil {
			userLocalBin := filepath.Join(home, ".local", "bin")
			defaultAllowedPrefixes = append(defaultAllowedPrefixes, userLocalBin)
		}

		// Regex patterns for Windows systems (to match all Python 3.x versions)
		defaultAllowedPatterns := []string{
			`(?i)^[A-Z]:\\Python3(\d{1,3})\\`,                        // Matches any drive:\Python310\, etc.
			`(?i)^[A-Z]:\\Program Files\\Python3(\d{1,3})\\`,         // Matches any drive:\Program Files\Python310\, etc.
			`(?i)^[A-Z]:\\Program Files \(x86\)\\Python3(\d{1,3})\\`, // Matches any drive:\Program Files (x86)\Python310\, etc.
			// Windows AppData paths (regex for all user Python installs)
			`(?i)^[A-Z]:\\Users\\[^\\]+\\AppData\\Local\\Programs\\Python\\`,                   // Base user Python dir
			`(?i)^[A-Z]:\\Users\\[^\\]+\\AppData\\Local\\Programs\\Python\\Python3(\d{1,3})\\`, // Matches all Python3 user installs
		}

		userAllowedDirs := cfg.GetAllowedPythonDirs()

		allowed := false

		// Check default prefixes first
		for _, prefix := range defaultAllowedPrefixes {
			if isPrefixOf(prefix, absPath) {
				allowed = true
				break
			}
		}

		// Check default patterns if not already allowed
		if !allowed {
			for _, pattern := range defaultAllowedPatterns {
				matched, err := regexp.MatchString(pattern, absPath)
				if err != nil {
					return fmt.Errorf("invalid regex pattern in default allowed patterns: %q: %v", pattern, err)
				}
				if matched {
					allowed = true
					break
				}
			}
		}

		// Check user-configured directories if still not allowed
		if !allowed {
			for _, dir := range userAllowedDirs {
				if isRegexPattern(dir) {
					// Treat as regex pattern
					matched, err := regexp.MatchString(dir, absPath)
					if err != nil {
						return fmt.Errorf("invalid regex pattern in allowed_python_dirs: %q: %v", dir, err)
					}
					if matched {
						allowed = true
						break
					}
				} else {
					// Simple prefix match
					if isPrefixOf(dir, absPath) {
						allowed = true
						break
					}
				}
			}
		}
		if !allowed {
			const errMsg = `interpreter path %q is not in allowed directories.
To permit this interpreter, add its directory as a prefix or a regex pattern to allowed_python_dirs in your config file (e.g., ~/.config/aprd/config.yaml):

  # Prefix match example (for simple cases):
  allowed_python_dirs:
    - %s
  # Or as a regex pattern (for complex version-specific paths or multiple installation patterns):
  # - '^%s([/\\]|$)'
`
			return fmt.Errorf(errMsg, absPath, filepath.Dir(absPath), regexp.QuoteMeta(filepath.Dir(absPath)))
		}
	} else {
		// No path separator: must be a bare allowed name
		// Allow "python3" or "python3.x" where x is any number
		if !allowedNamePattern.MatchString(interpreter) {
			return fmt.Errorf("interpreter name %q is not allowed (must be python, python2, python2.x, python3, or python3.x)", interpreter)
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
	// Defensive copy: ensure we never mutate the input slice
	newEnv := make([]string, len(env))
	copy(newEnv, env)
	for key, value := range executorVars {
		if value != "" {
			newEnv = append(newEnv, key+"="+value)
		}
	}
	return newEnv
}

func (o Options) Run(ctx context.Context) error {
	prd := o.PRDPath
	tmpPath, cleanup, err := makeTempPRD(prd, o.InitialPrompt)
	if err != nil {
		return fmt.Errorf("preparing PRD for run: %w", err)
	}
	defer cleanup()

	plan, err := BuildArgs(BuildArgsInput{
		Config:      o.Config,
		PRDPath:     tmpPath,
		LogFilePath: o.LogFilePath,
		LogLevel:    o.LogLevel,
	})
	if err != nil {
		return fmt.Errorf("building runner arguments: %w", err)
	}

	env := append([]string(nil), plan.Env...)
	if len(o.ExtraEnv) > 0 {
		env = append(env, o.ExtraEnv...)
	}

	cmd := exec.Command(plan.Cmd, plan.Args...)
	cmd.Env = env
	setupProcessGroup(cmd)

	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return fmt.Errorf("opening stdout pipe: %w", err)
	}
	stderr, err := cmd.StderrPipe()
	if err != nil {
		return fmt.Errorf("opening stderr pipe: %w", err)
	}

	if err := cmd.Start(); err != nil {
		return fmt.Errorf("starting runner process: %w", err)
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
		return fmt.Errorf("run canceled: %w", ctx.Err())
	case err := <-waitCh:
		wg.Wait()
		sendLine(o.Logs, Line{Time: time.Now(), Text: "process finished", Err: false})
		if o.Logs != nil {
			close(o.Logs)
		}
		if err != nil {
			return fmt.Errorf("runner exited with error: %w", err)
		}
		return nil
	}
}

// stream attempts to forward subprocess output to the log channel without blocking for normal log lines.
// When the channel backlog fills (UI too slow), it emits a warning (which may block) and drops live-feed lines.
// The Python process (invoked with --log-file) is responsible for writing the complete log file synchronously; the Go runner and TUI do not persist log lines to disk.
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
			// Warning: Log lines may be dropped here if the channel is full. Any dropped lines are not delivered to the TUI or its display.
			// The Python process (invoked with --log-file) is responsible for writing the complete log file synchronously; the Go runner and TUI do not persist log lines to disk.
			msg := fmt.Sprintf("log channel backlog full (capacity %d); downstream consumer may be too slow", cap(logs))
			sendLine(logs, Line{Time: time.Now(), Text: msg, Err: true})
		}
	}
	if err := sc.Err(); err != nil {
		sendLine(logs, Line{Time: time.Now(), Text: "stream error: " + err.Error(), Err: true})
	}
}
