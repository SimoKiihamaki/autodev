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
	// Clean both paths to handle trailing separators consistently and normalize path separators
	cleanPrefix := filepath.Clean(prefix)
	cleanPath := filepath.Clean(path)

	// Check for exact match before appending separator
	if cleanPath == cleanPrefix {
		return true
	}
	// Ensure prefix ends with a path separator using filepath.Separator for cross-platform consistency
	sep := string(filepath.Separator)
	if !strings.HasSuffix(cleanPrefix, sep) {
		cleanPrefix += sep
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

// validatePythonScriptPath validates that the PythonScript path is safe and doesn't escape expected directories.
// validatePythonScriptPath requires absolute paths for both scriptPath and repoPath.
// All paths passed to this function should be absolute.
// Note: repoPath should be resolved from symlinks before calling this function to prevent TOCTOU issues
func validatePythonScriptPath(scriptPath, repoPath string) error {
	sep := string(filepath.Separator)

	// scriptPath is assumed to be symlink-resolved as per function contract
	if !filepath.IsAbs(scriptPath) {
		return fmt.Errorf("internal error: validatePythonScriptPath received non-absolute path: %q", scriptPath)
	}

	// If repoPath is configured, ensure the script is within the repo
	if repoPath != "" {
		// Validate that repoPath is absolute as per function contract
		if !filepath.IsAbs(repoPath) {
			return fmt.Errorf("internal error: validatePythonScriptPath received non-absolute repoPath: %q", repoPath)
		}

		// repoPath should already be resolved from symlinks before calling this function
		// to prevent TOCTOU (Time-of-Check-Time-of-Use) vulnerabilities
		relPath, err := filepath.Rel(repoPath, scriptPath)
		if err != nil {
			return fmt.Errorf("PythonScript path cannot be resolved relative to repo: %q", scriptPath)
		}
		if filepath.IsAbs(relPath) {
			return fmt.Errorf("PythonScript path cannot be made relative to repository root (possible different drives/volumes on Windows): %q (repo: %q)", scriptPath, repoPath)
		}
		for _, part := range strings.Split(relPath, sep) {
			if part == ".." {
				return fmt.Errorf("PythonScript path would escape repository directory: %q", scriptPath)
			}
		}
		return nil
	}

	// When repoPath is not configured, restrict to safe directories only
	tmpDir := os.TempDir()
	// Restrict to a specific subdirectory within the temp directory for safety
	autodevTmpDir := filepath.Join(tmpDir, "autodev")
	if stat, err := os.Stat(autodevTmpDir); err == nil && stat.IsDir() {
		resolvedAutodevTmpDir, err := filepath.EvalSymlinks(autodevTmpDir)
		if err == nil && isPrefixOf(resolvedAutodevTmpDir, scriptPath) {
			// Allow paths within autodev subdirectory of temp directory (important for testing)
			return nil
		}
	}

	homeDir, err := os.UserHomeDir()
	if err == nil {
		// Restrict to a specific safe subdirectory within the home directory
		autodevDir := filepath.Join(homeDir, ".local", "share", "autodev")
		if info, statErr := os.Stat(autodevDir); statErr == nil && info.IsDir() {
			resolvedAutodevDir, err := filepath.EvalSymlinks(autodevDir)
			if err == nil && isPrefixOf(resolvedAutodevDir, scriptPath) {
				// Allow paths only within ~/.local/share/autodev
				return nil
			}
		}
	}

	// Reject absolute paths in other locations when repoPath is not configured
	return fmt.Errorf("PythonScript path requires repoPath configuration or must be within safe directories: %q", scriptPath)
}

// resolveScriptPath resolves the script path to the absolute path that will be executed
func resolveScriptPath(scriptPath, repoPath string) (string, error) {
	// If path is already absolute, use it directly
	if filepath.IsAbs(scriptPath) {
		resolved, err := filepath.EvalSymlinks(scriptPath)
		if err != nil {
			return "", fmt.Errorf("failed to resolve absolute script path symlinks: %q: %w", scriptPath, err)
		}
		return resolved, nil
	}

	// For relative paths, repoPath must be configured
	if repoPath == "" {
		return "", fmt.Errorf("relative script path requires repoPath configuration: %q", scriptPath)
	}

	// Join with repoPath and resolve to absolute path
	candidate := filepath.Join(repoPath, scriptPath)
	absPath, err := filepath.Abs(candidate)
	if err != nil {
		return "", fmt.Errorf("cannot make script path absolute: %q: %w", scriptPath, err)
	}

	resolved, err := filepath.EvalSymlinks(absPath)
	if err != nil {
		return "", fmt.Errorf("failed to resolve script path symlinks: %q: %w", scriptPath, err)
	}
	return resolved, nil
}

// buildScriptArgs constructs the argument list for invoking the configured Python script.
//
// Parameters:
//   - cfg:        The configuration object containing the Python script path and repository path.
//   - prdPath:    The path to the PRD file to be passed to the script.
//   - logFilePath:The path to the log file to be passed to the script.
//   - logLevel:   The log level to be passed to the script.
//
// Returns:
//   - []string:   The argument list to be used for invoking the Python script.
//   - error:      An error if argument construction or validation fails.
//
// Security considerations:
//   - This function performs extensive validation and resolution of the script path to prevent
//     security vulnerabilities, such as TOCTOU (Time-of-check to time-of-use) attacks.
//   - It resolves symlinks in both the repository path and the script path to ensure that the
//     script to be executed is within the intended repository and not replaced by a malicious file.
//   - The function uses validatePythonScriptPath to enforce that the resolved script path is safe.
//   - Any failure in path resolution or validation results in an error, preventing execution.
func buildScriptArgs(cfg config.Config, prdPath, logFilePath, logLevel string) ([]string, error) {
	script := cfg.PythonScript

	// Resolve repoPath symlinks first to prevent TOCTOU issues
	var resolvedRepoPath string
	if cfg.RepoPath != "" {
		var err error
		resolvedRepoPath, err = filepath.EvalSymlinks(cfg.RepoPath)
		if err != nil {
			return nil, fmt.Errorf("cannot resolve symlinks in repoPath: %q: %v", cfg.RepoPath, err)
		}
	}

	// Resolve the final script path that will be executed
	resolvedScript, err := resolveScriptPath(script, cfg.RepoPath)
	if err != nil {
		return nil, err
	}

	// Validate the resolved script path for security (prevents TOCTOU)
	if err := validatePythonScriptPath(resolvedScript, resolvedRepoPath); err != nil {
		return nil, err
	}

	script = resolvedScript
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
	if cfg.Timings.WaitMinutes != nil && *cfg.Timings.WaitMinutes > 0 {
		args = append(args, "--wait-minutes", fmt.Sprint(*cfg.Timings.WaitMinutes))
	}
	if cfg.Timings.ReviewPollSeconds != nil && *cfg.Timings.ReviewPollSeconds > 0 {
		args = append(args, "--review-poll-seconds", fmt.Sprint(*cfg.Timings.ReviewPollSeconds))
	}
	if cfg.Timings.IdleGraceMinutes != nil && *cfg.Timings.IdleGraceMinutes > 0 {
		args = append(args, "--idle-grace-minutes", fmt.Sprint(*cfg.Timings.IdleGraceMinutes))
	}
	if cfg.Timings.MaxLocalIters != nil && *cfg.Timings.MaxLocalIters > 0 {
		args = append(args, "--max-local-iters", fmt.Sprint(*cfg.Timings.MaxLocalIters))
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

	// Validate Python flags for security
	if err := validatePythonFlags(pyFlags); err != nil {
		return Args{}, err
	}

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

// validatePythonFlags enforces a safe allowlist and rejects flags like -c/-m that change execution target.
func validatePythonFlags(flags []string) error {
	allowedGrouped := map[rune]bool{'u': true, 'E': true, 'I': true, 's': true, 'B': true}
	for i := 0; i < len(flags); i++ {
		f := flags[i]

		// Handle grouped short options like -uE, -IEu, etc. Forbid c/m anywhere.
		if strings.HasPrefix(f, "-") && len(f) > 2 {
			for _, ch := range f[1:] {
				if ch == 'c' || ch == 'm' {
					return fmt.Errorf("disallowed Python flag in group %q: -%c", f, ch)
				}
				if !allowedGrouped[ch] {
					return fmt.Errorf("unexpected short flag in group %q: -%c", f, ch)
				}
			}
			continue
		}

		switch f {
		case "-c", "--command", "-m", "--module":
			return fmt.Errorf("disallowed Python flag in PythonCommand: %q (would bypass the runner script)", f)
		}
		if strings.HasPrefix(f, "--") {
			// No long flags are needed for the interpreter in this tool; be conservative.
			return fmt.Errorf("disallowed long flag in PythonCommand: %q", f)
		}
		// Allow common safe short flags: -u (we also enforce), -E, -I, -s, -B, -X <opt>
		// Also allow common optimization flags: -O, -OO
		if f == "-u" || f == "-E" || f == "-I" || f == "-s" || f == "-B" || f == "-O" || f == "-OO" {
			continue
		}
		if f == "-X" {
			// -X must be followed by an option and is only allowed for a safe allowlist (e.g., only "dev")
			if i+1 >= len(flags) {
				return fmt.Errorf("Python flag -X requires an option argument")
			}
			xArg := flags[i+1]
			allowedX := map[string]bool{"dev": true}
			if !allowedX[xArg] {
				return fmt.Errorf("disallowed argument to -X: %q (only -X dev is allowed)", xArg)
			}
			i++ // Skip the argument to -X
			continue
		}
		// Allow -W flag (may have argument, will be validated below)
		if f == "-W" {
			// -W may have an argument; if next element doesn't start with -, skip it
			if i+1 < len(flags) && !strings.HasPrefix(flags[i+1], "-") {
				i++ // Skip the argument to -W
			}
			continue
		}
		return fmt.Errorf("unexpected flag in PythonCommand: %q", f)
	}
	return nil
}

// ValidatePythonFlagsForTest is a test helper that exports validatePythonFlags for testing
func ValidatePythonFlagsForTest(flags []string) error {
	return validatePythonFlags(flags)
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
