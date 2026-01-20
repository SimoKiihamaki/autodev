# Research: Improve overall test coverage to 80%+

**Date**: 2026-01-19
**Item**: 019-improve-overall-test-coverage-to-80

## Research Question
Low test coverage leaves the codebase vulnerable to regressions and makes refactoring risky.

**Motivation:** High test coverage enables confident refactoring, prevents regressions, and serves as documentation.

**Success criteria:**
- Achieve 80%+ test coverage for Go packages
- Achieve 80%+ test coverage for Python modules
- Add tests for all critical untested files

**Signals:** priority: medium

## Summary
The autodev project currently has **40.4% overall Go test coverage** and **58% Python test coverage**, significantly below the 80% target. The codebase consists of approximately 38 Go source files and 40 Python source files (excluding tests and vendor code). Key findings reveal that:

1. **Go codebase** has substantial gaps in TUI components (many at 0% coverage), API server (0% coverage), and several runner functions (process management at 0%)
2. **Python codebase** has 23 modules with no dedicated test files, though some coverage exists through integration tests
3. **Testing infrastructure** is well-established with proper frameworks (Go testing, pytest) and CI integration via Makefile
4. **Test failures** exist in both codebases (46 failing Python tests, 3 failing Go tests) which should be addressed first

The path to 80% coverage requires prioritizing untested critical paths, focusing on high-value components like the TUI update loop, API server, process management, and key Python modules like agents, command execution, and verification logic.

## Current State Analysis

### Existing Implementation

**Go Testing:**
- **Current overall coverage: 40.4%** (as measured by `go test ./... -coverprofile=coverage.out`)
- **Test count: 108 tests** across 7 packages
- **Coverage breakdown by package:**
  - `internal/utils`: 100.0% ✅ (already exceeds target)
  - `internal/runner`: 69.3% (good foundation, needs targeted improvements)
  - `internal/config`: 50.4% (moderate coverage, validation logic needs work)
  - `internal/api`: 43.5% (router covered, server untested)
  - `internal/tui`: 32.6% (major gap - most view/keyboard handlers at 0%)
  - `cmd/api`: 0.0% (main entry point untested)
  - `cmd/aprd`: 0.0% (main entry point untested)

**Python Testing:**
- **Current overall coverage: 58%** (as measured by `pytest --cov=tools/auto_prd`)
- **Test count: 569 tests** with 523 passing, 46 failing
- **23 Python modules lack dedicated test files:**
  - Core infrastructure: `app.py`, `cli.py`, `command.py`, `command_checks.py`, `executor.py`
  - Git/GitHub integration: `git_ops.py`, `gh_ops.py`
  - Workflow: `local_loop.py`, `support_loop.py`, `scope_reviewer.py`, `pr_flow.py`, `review_loop.py`
  - Utilities: `errors.py`, `journal.py`, `logging_utils.py`, `policy.py`, `progress.py`, `rollback.py`, `startup.py`
  - Verification: `verification_mock.py`, `verification_persistence.py`, `tracker_validator.py`

**Current Patterns and Conventions:**

**Go test patterns (from internal/tui/model_test.go:14-293, internal/config/config_test.go:11-325):**
- Table-driven tests for multiple scenarios
- Parallel test execution with `t.Parallel()`
- Helper functions for test setup (e.g., `newModelForSettingsTest()`)
- Subtests using `t.Run()` for hierarchical test organization
- Use of temporary directories with `t.TempDir()`
- Environment variable isolation with `t.Setenv()`

**Python test patterns (from tools/auto_prd/tests/test_utils.py:29-100, tools/auto_prd/tests/test_agents.py:50-100):**
- `unittest.TestCase` base class with descriptive test names
- `safe_import` helper for importing modules under test
- `setUp()` methods for test environment setup
- Comprehensive docstrings explaining test purpose
- Security-focused tests (e.g., secret exclusion verification)
- Mock-based testing with `unittest.mock.patch`

**Integration Points:**
- **Makefile** (`/Users/simo/Projects/autodev/Makefile:34-64`) provides standardized test commands
- Go tests use standard `go test ./...` with optional race detector
- Python tests use `pytest` via `uv run` in the tools directory
- Coverage reporting via `go test -coverprofile` and `pytest --cov`

### Key Files

#### Go Files Requiring Coverage

**Zero Coverage Files (Critical):**
- `internal/api/server.go:30-72` - HTTP server lifecycle methods (NewServer, Start, Shutdown, Addr, Handler)
- `internal/runner/proc_unix.go:15-58` - Unix process signal handling (interruptProcess, forceKillProcess)
- `internal/runner/proc_windows.go` - Windows process management (entire file)
- 28 TUI files with 0% coverage including:
  - `internal/tui/update.go:15-206` - Core update loop (Update function at 7.4%)
  - `internal/tui/view.go:30-256` - Main view rendering
  - `internal/tui/view_settings.go:24-177` - Settings view rendering
  - `internal/tui/view_progress.go:64-297` - Progress/tracker view
  - `internal/tui/keys_*.go` files - All keyboard handlers

**Low Coverage Files (20-50%, high impact):**
- `internal/runner/runner.go:685-765` - Python flag validation (0-29%)
- `internal/runner/runner.go:955-1003` - Safe script directory merging (44%)
- `internal/config/config.go:133-308` - Config loading and migration (0%)
- `internal/config/config.go:477-483` - Config saving (0%)

**Well-Tested Files (Reference Examples):**
- `internal/utils/utils.go:4-9` - Utility functions (100% coverage)
- `internal/runner/build_args_test.go` - Argument building (comprehensive table tests)
- `internal/tui/model_test.go:14-293` - Model initialization and state management

#### Python Files Requiring Coverage

**No Test Files (23 modules):**
- `tools/auto_prd/agents.py` (1467 lines) - Claude/codex execution, timeout handling
- `tools/auto_prd/app.py` - Main application orchestration
- `tools/auto_prd/cli.py` - Command-line interface
- `tools/auto_prd/command.py` - Process execution, command safety checks
- `tools/auto_prd/command_checks.py` - Command validation (59 lines)
- `tools/auto_prd/executor.py` - Execution policies
- `tools/auto_prd/git_ops.py` (12084 bytes) - Git operations
- `tools/auto_prd/gh_ops.py` (16785 bytes) - GitHub API operations
- `tools/auto_prd/journal.py` (13976 bytes) - Journaling/state persistence
- `tools/auto_prd/local_loop.py` (31710 bytes) - Local execution loop
- `tools/auto_prd/logging_utils.py` - Logging configuration
- `tools/auto_prd/policy.py` - Policy management
- `tools/auto_prd/pr_flow.py` - PR workflow orchestration
- `tools/auto_prd/progress.py` (298 lines) - Progress tracking
- `tools/auto_prd/rollback.py` (551 lines) - Rollback mechanisms
- `tools/auto_prd/scope_reviewer.py` (18690 bytes) - Scope review logic
- `tools/auto_prd/startup.py` (20045 bytes) - Initialization
- `tools/auto_prd/support_loop.py` (19712 bytes) - Support loop
- `tools/auto_prd/task_completion_detector.py` - Task completion detection
- `tools/auto_prd/tracker_validator.py` - Tracker schema validation
- `tools/auto_prd/verification_mock.py` - Verification mocking
- `tools/auto_prd/verification_persistence.py` (341 lines) - Verification state persistence

**Tested Files (Reference Examples):**
- `tools/auto_prd/tests/test_utils.py` - Utility function tests with security focus
- `tools/auto_prd/tests/test_agents.py` - Agent execution tests
- `tools/auto_prd/tests/test_context.py` - Context management tests
- `tools/auto_prd/tests/test_verification.py` - Verification protocol tests

## Technical Considerations

### Dependencies

**External Dependencies:**
- **Go:**
  - `github.com/charmbracelet/bubbletea` - TUI framework (requires special testing patterns for Msg types)
  - `github.com/charmbracelet/bubbles` - UI components (textarea, textinput, viewport)
  - `golang.org/x/sync/errgroup` - Concurrency primitives
  - `github.com/google/shlex` - Shell lexer for argument parsing

- **Python:**
  - `pytest` - Test framework with fixture support
  - `pytest-cov` - Coverage reporting
  - `unittest.mock` - Mocking framework
  - Standard library: subprocess, tempfile, pathlib

**Internal Modules to Integrate:**
- Go TUI tests need to integrate with `internal/config` and `internal/runner`
- Python tests need to mock external command execution (Claude CLI, git, gh)
- Both codebases share similar patterns for process management and configuration

### Patterns to Follow

**Go Testing Patterns:**
1. **Table-driven tests** (from `internal/runner/runner_test.go:20-100`):
   ```go
   tests := []struct {
       name string
       input InputType
       want ExpectedType
   }{
       // test cases
   }
   for _, tc := range tests {
       t.Run(tc.name, func(t *testing.T) {
           // test logic
       })
   }
   ```

2. **Helper functions** (from `internal/tui/model_test.go:45-55`):
   - Create reusable setup functions like `newModelForSettingsTest()`
   - Use `t.TempDir()` for filesystem operations
   - Use `t.Setenv()` for environment variable isolation

3. **Parallel test execution**:
   - Use `t.Parallel()` for independent tests
   - Avoid `t.Parallel()` when using `t.Setenv()` or shared resources

4. **Subtest organization**:
   - Use descriptive names in `t.Run()`
   - Group related test cases hierarchically

**Python Testing Patterns:**
1. **Safe import pattern** (from `tools/auto_prd/tests/test_helpers.py`):
   ```python
   from .test_helpers import safe_import
   module = safe_import("tools.auto_prd.module", "..module", "function_name")
   ```

2. **Mock-based testing** (from `tools/auto_prd/tests/test_utils.py:43-67`):
   ```python
   from unittest.mock import patch
   with patch.dict(os.environ, {"VAR": "value"}):
       result = function_under_test()
   ```

3. **Security-focused testing**:
   - Test for secret/PII exclusion from error messages
   - Verify command sanitization
   - Test path traversal prevention

4. **Comprehensive docstrings**:
   - Explain what is being tested and why
   - Document security implications
   - Note migration considerations

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Test failures masking real issues** | High | Fix existing 46 failing Python tests and 3 failing Go tests before adding new tests |
| **TUI testing complexity** | High | Bubbletea programs require specialized testing patterns - focus on Update() function with controlled Msg sequences, use tea.NewProgram() with tea.WithRenderer(nil) for headless testing |
| **Mock maintenance overhead** | Medium | Keep mocks minimal and focused; prefer integration-style tests where possible; document mock behavior clearly |
| **Test execution time** | Medium | Use parallel test execution (t.Parallel in Go, pytest-xdist in Python); keep unit tests fast; move slow tests to integration suite |
| ** brittleness in subprocess tests** | Medium | The existing tests show many failures related to subprocess execution - use reliable mocking for external commands (claude, git, gh); only test real subprocess behavior in integration tests |
| **Coverage inflation** | Low | Focus on meaningful tests, not just coverage numbers; test error paths and edge cases; review coverage reports to identify untested branches |
| **Environment-specific test failures** | Low | Use `t.Setenv()` (Go) and `patch.dict(os.environ, ...)` (Python) for environment isolation; avoid reliance on specific system state |

## Recommended Approach

### Phase 1: Stabilize Existing Tests (Week 1)
**Goal:** Fix failing tests to establish reliable baseline

**Go (3 failures):**
1. Fix `internal/tui/navigation_test.go:115` - Navigation wrapping tests failing with unexpected focus
   - Issue: Expected "repo" but got "allowedpythondirs"
   - Root cause: Likely changes to settings input structure or navigation logic
   - Action: Update test expectations to match current implementation or fix navigation bug

**Python (46 failures):**
1. **Fix test compatibility issues:**
   - `test_agents.py` - `TypeError: fileno() returned a non-integer` (3 tests)
   - `test_guardrails.py` - `AttributeError: 'parse_owner_repo_from_git'` (12 tests)
   - `test_versioned_criteria.py` - Data structure mismatches (3 tests)
   - `test_verification.py` - Tuple vs object attribute error (1 test)

2. **Fix command execution tests (27 failures):**
   - Many tests fail with `SystemExit: Command not allowed` or `Command not allowed: echo`
   - Root cause: Safety checks in `command.py` preventing test execution
   - Action: Either use `AUTO_PRD_ALLOW_UNSAFE_EXECUTION=1` in tests or refactor safety checks to be test-aware

### Phase 2: High-Value Untested Components (Weeks 2-4)
**Goal:** Add tests for critical paths with zero coverage

**Go - Priority 1: Core TUI Logic (~500 additional lines of coverage)**
1. **`internal/tui/update.go:15-206`** (currently 7.4%):
   - Test `Update()` function with various message types
   - Cover tea.KeyMsg, tea.WindowSizeMsg, custom msgs
   - Test state transitions and error handling
   - Use `tea.NewProgram(model, tea.WithRenderer(nil))` for headless testing

2. **`internal/api/server.go:30-72`** (currently 0%):
   - Test `NewServer()` configuration
   - Test `Start()` and `Shutdown()` lifecycle
   - Test `Addr()` and `Handler()` accessors
   - Use `httptest` for HTTP server testing

3. **`internal/runner/proc_unix.go:15-58`** (currently 0%):
   - Test `interruptProcess()` signal handling
   - Test `forceKillProcess()` termination
   - Mock `os.Process` for reliable testing

**Go - Priority 2: Key Views and Handlers (~300 additional lines)**
1. **`internal/tui/view_settings.go:24-177`** (0%):
   - Test rendering of settings groups
   - Test help text generation
   - Test input field rendering

2. **`internal/tui/keys_settings.go:163-330`** (23%):
   - Test keyboard navigation in settings
   - Test boolean input toggling
   - Test executor choice cycling

3. **`internal/runner/runner.go:685-765`** (14-29%):
   - Test Python flag validation logic
   - Test regex pattern matching
   - Test error cases

**Python - Priority 1: Core Infrastructure (~800 additional lines)**
1. **`tools/auto_prd/command.py`** (critical - command execution):
   - Create `tools/auto_prd/tests/test_command.py`
   - Test `run_cmd()` with various scenarios
   - Test `popen_streaming()` with mocked subprocesses
   - Test command sanitization and safety checks
   - Test environment variable handling
   - Mock subprocess.Popen extensively

2. **`tools/auto_prd/agents.py`** (critical - Claude/codex execution):
   - Enhance existing `tools/auto_prd/tests/test_agents.py`
   - Test timeout configuration and handling
   - Test response parsing and error handling
   - Test buffer processing for streaming responses
   - Mock claude CLI calls

3. **`tools/auto_prd/cli.py`** (user-facing):
   - Create `tools/auto_prd/tests/test_cli.py`
   - Test argument parsing
   - Test main entry point
   - Test error handling and exit codes

**Python - Priority 2: Workflow Modules (~600 additional lines)**
1. **`tools/auto_prd/local_loop.py`** (execution orchestration):
   - Create `tools/auto_prd/tests/test_local_loop.py`
   - Test loop iteration logic
   - Test phase transitions
   - Test error recovery

2. **`tools/auto_prd/git_ops.py`** (git integration):
   - Create `tools/auto_prd/tests/test_git_ops.py`
   - Test git command execution
   - Test branch operations
   - Test status parsing
   - Mock subprocess calls to git

3. **`tools/auto_prd/verification_persistence.py`** (state management):
   - Create `tools/auto_prd/tests/test_verification_persistence.py`
   - Test state loading/saving
   - Test JSON serialization
   - Test error handling

### Phase 3: Moderate-Value Components (Weeks 5-6)
**Goal:** Address medium-priority untested files

**Go:**
1. TUI view files: `view_progress.go`, `view_prd.go`, `view_env.go`
2. TUI key handlers: `keys_run.go`, `keys_prd.go`, `keys_logs.go`
3. Config loading: `config.go:133-308` (Load, migration)
4. Config saving: `config.go:477-483` (Save functions)

**Python:**
1. `tools/auto_prd/gh_ops.py` - GitHub API operations
2. `tools/auto_prd/scope_reviewer.py` - Scope review logic
3. `tools/auto_prd/rollback.py` - Rollback mechanisms
4. `tools/auto_prd/startup.py` - Initialization logic

### Phase 4: Edge Cases and Error Paths (Week 7)
**Goal:** Improve coverage of partially-tested files

**Go files at 40-70% coverage:**
- Enhance `internal/runner/runner.go` tests for error paths
- Improve `internal/config` validation tests
- Add edge case tests for `internal/tui` helpers

**Python modules with partial coverage:**
- Add error path tests to existing test files
- Test edge cases in utils and helpers
- Improve timeout and error handling tests

### Testing Strategy Guidelines

**For Go:**
1. **Unit tests first:** Test individual functions in isolation
2. **Table-driven tests:** Use for multiple scenarios (see `runner_test.go`)
3. **Helper functions:** Create reusable test setup helpers
4. **Mock interfaces:** Extract interfaces for external dependencies
5. **Parallel execution:** Use `t.Parallel()` where safe
6. **Coverage targets:** Aim for 80-90% per package (100% not always necessary)

**For Python:**
1. **Fix existing tests:** Don't add new tests while old ones fail
2. **Mock subprocess calls:** Use `unittest.mock.patch` for external commands
3. **Use pytest fixtures:** Create reusable test components
4. **Environment isolation:** Use `patch.dict` for env vars
5. **Security tests:** Verify secret exclusion, command sanitization
6. **Integration tests:** Keep some real subprocess tests for confidence

### Success Metrics

**Weekly targets:**
- Week 1: 0 failing tests, Go coverage 45%, Python coverage 60%
- Week 2: Go coverage 55%, Python coverage 65%
- Week 3: Go coverage 65%, Python coverage 70%
- Week 4: Go coverage 75%, Python coverage 75%
- Week 5: Go coverage 80%, Python coverage 78%
- Week 6: Go coverage 82%, Python coverage 80%
- Week 7: Both at 80%+, focused on edge cases

**Quality gates:**
- All tests must pass before merging
- Coverage must not decrease
- New code must include tests
- Complex logic must have unit tests

## Open Questions

1. **TUI Testing Approach:** Bubbletea TUI testing is complex - should we invest in specialized Bubbletea testing utilities or stick with headless program testing?

2. **Mock Granularity:** Python tests have many subprocess-related failures - should we:
   - Fix existing tests by allowing unsafe execution in test environment?
   - Refactor to more comprehensive mocking?
   - Combination approach?

3. **Test Execution Time:** With 569 Python tests and growing, execution time is a concern. Should we:
   - Implement pytest-xdist for parallel test execution?
   - Separate unit and integration test suites?
   - Add test markers for slow tests?

4. **Coverage Tools:** Currently using `go test -coverprofile` and `pytest --cov`. Should we:
   - Set up continuous coverage reporting (e.g., Codecov)?
   - Add coverage badges to README?
   - Configure coverage thresholds in CI?

5. **Legacy Code:** Some modules (like `tools/auto_prd/agents.py` at 1467 lines) are large and complex. Should we:
   - Test incrementally as we modify code?
   - Dedicate time to comprehensive test coverage before changes?
   - Focus on critical paths only?
