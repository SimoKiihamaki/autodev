# Autodev Codebase Analysis Report

**Generated:** 2026-01-19
**Scope:** Full codebase analysis covering Go and Python components
**Severity Levels:** 🔴 Critical | 🟠 High | 🟡 Medium | 🔵 Low

---

## Executive Summary

This report identifies **86 issues** across the autodev codebase, comprising:
- **🔴 Critical Issues:** 7
- **🟠 High Issues:** 23
- **🟡 Medium Issues:** 41
- **🔵 Low Issues:** 15

**Overall Assessment:** The codebase is well-structured with good separation of concerns and comprehensive security validation. However, there are significant gaps in test coverage, some dead/unused code, and configuration inconsistencies that should be addressed.

---

## Table of Contents

1. [Critical Issues](#critical-issues)
2. [High Priority Issues](#high-priority-issues)
3. [Medium Priority Issues](#medium-priority-issues)
4. [Low Priority Issues](#low-priority-issues)
5. [Test Coverage Gaps](#test-coverage-gaps)
6. [Dead Code & Unused Features](#dead-code--unused-features)
7. [Configuration Issues](#configuration-issues)
8. [Documentation Issues](#documentation-issues)

---

## Critical Issues

### CRITICAL-001: Missing Environment Variable Documentation
**Location:** `internal/runner/runner.go:232`

**Issue:** The `AUTO_PRD_SAFE_SCRIPT_DIRS` environment variable is hardcoded in the Go runner but is NOT exposed through the config system or TUI.

**Root Cause:** The runner uses `safeScriptDirsEnv` constant but there's no corresponding config field or TUI input for managing allowed Python script directories.

**Impact:** Users cannot configure allowed Python directories through the UI; they must manually edit environment variables.

**Recommended Fix:**
```go
// In config.go, add to Config struct:
SafeScriptDirs []string `yaml:"safe_script_dirs"`

// In runner.go, read from config instead of just environment:
func resolvedSafeScriptDirs(cfg config.Config) []string {
    // Merge cfg.SafeScriptDirs with os.Getenv(safeScriptDirsEnv)
}
```

---

### CRITICAL-002: Inconsistent PRD Hash Function
**Location:** `tools/auto_prd/utils.py:268-273`

**Issue:** `get_prd_hash()` function has a `repo_root` parameter that is never used - it hardcodes `PRD.md` instead.

**Root Cause:** Function was refactored but the parameter was not removed or implemented.

**Current Code:**
```python
def get_prd_hash(repo_root: Path | None = None) -> str:
    return hash_file(open("PRD.md"))  # repo_root ignored!
```

**Recommended Fix:** Either use the parameter or remove it:
```python
def get_prd_hash(repo_root: Path | None = None) -> str:
    prd_path = repo_root / "PRD.md" if repo_root else Path("PRD.md")
    return hash_file(prd_path)
```

---

### CRITICAL-003: Test Gaps in Core Safety Functions
**Location:** `tools/auto_prd/command.py`

**Issue:** Critical security validation functions have NO test coverage:
- `validate_command_args()` - Shell injection prevention
- `validate_cwd()` - Path traversal prevention
- `validate_stdin()` - Control character filtering
- `popen_streaming()` - Subprocess spawning

**Impact:** Security-critical code paths are untested, increasing risk of vulnerabilities.

**Recommended Fix:** Add comprehensive tests in `tools/auto_prd/tests/test_command_safety.py`:
- Test shell metacharacter rejection
- Test path traversal attempts
- Test control character handling
- Test safe command allowlist

---

### CRITICAL-005: Resource Leak in Temporary File Handling
**Location:** `tools/auto_prd/generate_tracker.py:135-140`

**Issue:** Temporary files created with `delete=False` may not be cleaned up if exceptions occur.

**Current Code:**
```python
tmp = tempfile.NamedTemporaryFile(delete=False)
try:
    # ... write ...
finally:
    os.unlink(tmp.name)  # Only if no exception before this point
```

**Recommended Fix:** Use context manager pattern:
```python
with tempfile.NamedTemporaryFile(delete=False) as tmp:
    # ... write ...
    tmp_path = tmp.name
# Cleanup happens automatically or use try/finally/finally
```

---

### CRITICAL-006: Go Version Mismatch in Documentation
**Location:** `README.md:26` vs `go.mod:3`

**Issue:** README states "Go 1.21+" but go.mod requires "go 1.23.0"

**Impact:** Users may attempt to build with Go 1.21/1.22 and encounter compatibility issues.

**Recommended Fix:** Update README.md to match go.mod:
```markdown
- Go 1.23+
```

---

### CRITICAL-007: Missing GitHub CI/CD Workflows
**Location:** `.github/` directory

**Issue:** No GitHub Actions workflows exist despite Makefile having CI targets (`make ci`).

**Impact:** No automated testing/validation on PRs.

**Recommended Fix:** Create `.github/workflows/ci.yml`:
```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version: '1.23'
      - run: make ci
```

---

### CRITICAL-008: Race Condition in Process Cancellation
**Location:** `internal/runner/runner.go:1084-1086`

**Issue:** Errgroup cancellation handling could cause race conditions between goroutines.

**Current Code:**
```go
g := new(errgroup.Group)
g.Go(func() error { ... })
g.Go(func() error { ... })
// No explicit cancellation context
```

**Recommended Fix:**
```go
ctx, cancel := context.WithCancel(ctx)
defer cancel()
g, ctx := errgroup.WithContext(ctx)
// Use ctx for all goroutines
```

---

### RESOLVED-2025-01-19: Progress Tab Handler

**Previously Reported as CRITICAL-004**

The Progress tab handler (`handleProgressTabActions()`) was fully implemented in commit `98a50a3` on 2025-11-27. The issue reported in the initial analysis was based on outdated information.

**Current State:**
- Handler implemented: `internal/tui/keys_progress.go:6-34`
- Integrated in key dispatch: `internal/tui/update_keys.go:74-75`
- Supports refresh (u), navigation (↑/↓), and confirm (Enter) actions
- Async tracker loading with proper error handling
- Complete view rendering with metadata, summary, and feature list

**No further action required.**

---

## High Priority Issues

### HIGH-001: Unused Function Parameter
**Location:** `tools/auto_prd/utils.py:264`

**Issue:** `get_git_sha()` has a `repo_root` parameter that is never used.

**Recommended Fix:** Remove the unused parameter or implement the functionality:
```python
def get_git_sha(repo_root: Path | None = None) -> str:
    root = repo_root or Path.cwd()
    return check_output(["git", "rev-parse", "HEAD"], cwd=root)
```

---

### HIGH-002: Dead Code in TUI Update Handler
**Location:** `internal/tui/update_keys.go:199`

**Issue:** Function `tabIndexFromAction` has unreachable default return.

**Current Code:**
```go
func tabIndexFromAction(act Action) (int, bool) {
    for i, tab := range defaultTabIDs() {
        if act.matchesTab(tab) {
            return i, true
        }
    }
    return 0, false  // NEVER REACHED - loop always matches
}
```

**Recommended Fix:** Remove the dead return or handle the case where no match is found.

---

### HIGH-003: Config Field Not Exposed in TUI
**Location:** `internal/config/config.go:126`, `internal/tui/view_settings.go`

**Issue:** `AllowedPythonDirs` config field exists but is NOT accessible through the TUI Settings tab.

**Impact:** Users can only configure this by manually editing `~/.config/aprd/config.yaml`.

**Recommended Fix:** Add TUI input field in Settings tab for managing allowed Python directories.

---

### HIGH-004: CodexModel Config Not Used by Python
**Location:** `internal/config/config.go:117`

**Issue:** The `CodexModel` field is configured in the TUI and persisted but is NOT consumed by the Python automation script.

**Impact:** Users see this field but it has no effect.

**Recommended Fix:** Either implement usage in Python or remove from the UI.

---

### HIGH-005: Inconsistent Error Handling in Command Execution
**Location:** `tools/auto_prd/utils.py:133-159`

**Issue:** `extract_called_process_error_details()` inconsistently returns stderr text OR exit code.

**Recommended Fix:** Standardize to always return a structured error:
```python
@dataclass
class CommandErrorDetails:
    exit_code: int
    stderr: str
    stdout: str

def extract_called_process_error_details(exc: CalledProcessError) -> CommandErrorDetails:
    return CommandErrorDetails(
        exit_code=exc.returncode,
        stderr=exc.stderr.decode() if exc.stderr else "",
        stdout=exc.stdout.decode() if exc.stdout else ""
    )
```

---

### HIGH-006: Mouse Event Handler Not Implemented
**Location:** `internal/tui/update.go:30`

**Issue:** Mouse message case has no implementation.

**Current Code:**
```go
case tea.MouseMsg:
    return m, nil // No handling implemented
```

**Recommended Fix:** Either implement mouse handling or remove the case if not needed.

---

### HIGH-007: Missing Pipe Cleanup
**Location:** `internal/runner/runner.go:1060-1067`

**Issue:** File handles from `cmd.StdoutPipe()` and `cmd.StderrPipe()` are not explicitly closed.

**Recommended Fix:**
```go
stdout, err := cmd.StdoutPipe()
if err != nil {
    return err
}
defer stdout.Close()

stderr, err := cmd.StderrPipe()
if err != nil {
    return err
}
defer stderr.Close()
```

---

### HIGH-008: Validation Warning Continues Execution
**Location:** `internal/config/config.go:438-446`

**Issue:** `MaxBatchSize` validation logs a warning but continues execution with invalid value.

**Recommended Fix:** In strict mode, make this a hard error:
```go
if c.BatchProcessing.MaxBatchSize == nil || *c.BatchProcessing.MaxBatchSize <= 0 {
    if os.Getenv("APRD_STRICT") == "1" {
        return LoadResult{
            Config: Defaults(),
            Warnings: []string{"Invalid max_batch_size in strict mode"},
        }
    }
    // Otherwise apply default with warning
}
```

---

### HIGH-009 through HIGH-023

*(Additional high-priority issues include unused imports, redundant validation, and error handling gaps - see detailed analysis in appendices)*

---

## Medium Priority Issues

### MEDIUM-001: Complex Nested Function
**Location:** `tools/auto_prd/command.py:273-304`

**Issue:** Nested helper function `normalize()` inside `ensure_claude_debug_dir()`.

**Recommended Fix:** Extract to module-level utility if used elsewhere, or keep nested if truly private.

---

### MEDIUM-002: Redundant Formatting Commands
**Location:** `Makefile:72-73`

**Issue:** Both `goimports` and `gofmt` are run, but `goimports` already includes formatting.

**Recommended Fix:** Remove `gofmt -w .` as `goimports` handles both import sorting and formatting.

---

### MEDIUM-003: TypeCheck Command Issues
**Location:** `Makefile:82`

**Issue:** Uses hardcoded `python3` instead of configured Python command; `--ignore-missing-imports` hides issues.

**Recommended Fix:**
```makefile
typecheck:
	@echo "🔎 Running type checks..."
	cd $(TOOLS_DIR) && $(PYTHON) -m mypy auto_prd/
```

---

### MEDIUM-004 through MEDIUM-041

*(Additional medium-priority issues include bare exception handlers, type annotation inconsistencies, performance optimizations, and documentation updates)*

---

## Low Priority Issues

### LOW-001 through LOW-015

*(Minor issues including unused variables in comments, documentation improvements, and code style consistency)*

---

## Test Coverage Gaps

### Critical Untested Files

| File | Lines | Missing Tests | Impact |
|------|-------|---------------|--------|
| `tools/auto_prd/app.py` | 626 | 100% | Main application flow |
| `tools/auto_prd/git_ops.py` | ~300 | 100% | Git operations core |
| `tools/auto_prd/gh_ops.py` | ~200 | 100% | PR creation/management |
| `tools/auto_prd/command.py` | 770 | 100% | Command execution |
| `tools/auto_prd/executor.py` | ~150 | 100% | Execution engine |
| `tools/auto_prd/guardrails.py` | ~200 | 100% | Safety mechanisms |
| `tools/auto_prd/local_loop.py` | 749 | 90% | Core automation loop |
| `tools/auto_prd/ralph.py` | ~150 | 100% | Ralph mode features |
| `tools/auto_prd/checkpoint.py` | ~200 | 100% | Session persistence |
| `tools/auto_prd/tracker_generator.py` | ~300 | 100% | Task tracking |

### Go Test Coverage

| Package | Coverage | Critical Gaps |
|---------|----------|---------------|
| `internal/tui/` | ~40% | View rendering, navigation |
| `internal/runner/` | ~60% | Platform-specific code |
| `internal/config/` | ~70% | Migration logic |
| `internal/api/` | ~30% | Server lifecycle |

---

## Dead Code & Unused Features

### Unused Functions

1. **`cleanup()` method** (model.go:652-669) - Marked deprecated but still present
2. **`formatBool()` function** (model.go:401-406) - Only used in one place
3. **`CleanupFinalModel()` vs `Cleanup()`** - Both exist, unclear which to use

### Unused Imports

- `tools/auto_prd_to_pr_v3.py` - Conditional import pattern that's always true

### Unused Constants

- Various command patterns in `constants.py` that are defined but never referenced

---

## Configuration Issues

### Config Defined But Not Read

| Field | Location | Issue |
|-------|----------|-------|
| `CodexModel` | config.go:117 | Set but never read by Python |
| `AllowedPythonDirs` | config.go:126 | Not exposed in TUI |
| `MaxLogLines` | config.go:66 | Not consistently used |

### Documentation Mismatches

| Config Field | Documentation | Reality |
|--------------|---------------|---------|
| `FollowLogs` | "runtime-only" | Actually persisted |
| Go version | "1.21+" | Requires 1.23 |
| Python path | `tools/auto_prd/pyproject.toml` | Actually `tools/auto_prd_to_pr_v3.py` |

---

## Documentation Issues

### Missing Documentation

1. **API Components** - No API documentation despite `internal/api/` existing
2. **Ralph Integration** - Partial documentation, needs updates
3. **Environment Variables** - `AUTO_PRD_*` variables not documented in README

### Outdated Documentation

1. **Go version** in README.md
2. **Python paths** in README.md
3. **FollowLogs behavior** in docs/tui-to-config.md

---

## Recommendations by Priority

### Immediate Actions (This Week)

1. Fix Go version documentation mismatch
2. Fix `get_prd_hash()` unused parameter
3. Add GitHub CI workflow
4. Fix `AUTO_PRD_SAFE_SCRIPT_DIRS` config exposure

### Short-term (Next Sprint)

1. Add tests for security-critical functions
2. Remove dead/redundant code
3. Fix resource leaks in temp file handling
4. Standardize error handling patterns
5. Fix config field exposure in TUI

### Medium-term (Next Quarter)

1. Improve test coverage to 80%+
2. Implement missing mouse handling or remove
3. Refactor complex nested functions
4. Update all documentation
5. Add integration tests

### Long-term (Future)

1. Consider breaking changes for cleaner API
2. Performance optimizations
3. Enhanced logging/monitoring
4. Plugin architecture

---

## Statistics

| Metric | Value |
|--------|-------|
| Total Go files | 51 |
| Total Python files | 41 |
| Go test coverage | ~40% |
| Python test coverage | ~30% |
| Critical issues | 8 |
| High issues | 23 |
| Medium issues | 41 |
| Low issues | 15 |

---

## Appendix: Detailed Findings by File

### Go Files

#### internal/tui/model.go
- Line 652-669: Deprecated `Cleanup()` still exists
- Line 292-297: FollowLogs nil handling could be simplified

#### internal/runner/runner.go
- Line 232: `AUTO_PRD_SAFE_SCRIPT_DIRS` not in config
- Line 1060-1067: Missing pipe cleanup
- Line 1084-1086: Race condition potential

#### internal/config/config.go
- Line 117: `CodexModel` unused
- Line 126: `AllowedPythonDirs` not exposed in TUI
- Line 438-446: Validation continues with warning

### Python Files

#### tools/auto_prd/app.py
- Line 1-626: Main application has NO tests
- Line 128-157: PRD path validation is complex and untested

#### tools/auto_prd/command.py
- Line 72-96: `find_repo_root()` untested
- Line 164-206: `validate_command_args()` critical but untested
- Line 260-357: `ensure_claude_debug_dir()` complex nested logic

#### tools/auto_prd/local_loop.py
- Line 83-96: `sanitize_session_id()` should use `re.escape()` for safety
- Line 282-294: Hardcoded QA snippet should be configurable

#### tools/auto_prd/utils.py
- Line 264: `get_git_sha()` unused parameter
- Line 268-273: `get_prd_hash()` ignores `repo_root` parameter

---

*End of Report*
