# Improve overall test coverage to 80%+ Implementation Plan

## Overview
Increase test coverage for both Go (40.4% → 80%+) and Python (58% → 80%+) codebases to enable confident refactoring, prevent regressions, and improve code documentation. This initiative focuses on adding meaningful tests for critical paths, stabilizing the existing test suite, and establishing sustainable testing patterns.

## Current State Analysis

**Go Codebase (38 source files):**
- **Overall coverage: 40.4%** (as measured by `go test ./... -coverprofile=coverage.out`)
- **Test count: 108 tests** across 7 packages
- **3 failing tests** in TUI navigation (test expectations out of sync with code)
- **Well-tested packages:** `internal/utils` (100%), `internal/runner` (69.3%)
- **Critical gaps:**
  - `internal/api/server.go:30-72` - HTTP server lifecycle (0% coverage)
  - `internal/runner/proc_unix.go:15-58` - Process signal handling (0% coverage)
  - `internal/tui/update.go:15-206` - Core TUI update loop (7.4% coverage)
  - `internal/config/config.go:133-308,477-483` - Config loading/saving (0% coverage)
  - 28 TUI view/keyboard handler files at 0% coverage

**Python Codebase (41 source files, 19 test files):**
- **Overall coverage: 58%** (estimated from test count and coverage gaps)
- **Test count: 569 tests** with 523 passing, **46 failing**
- **23 modules lack dedicated test files**, including critical infrastructure:
  - `agents.py` (1467 lines) - Claude/codex execution, timeout handling
  - `command.py` - Process execution, command safety checks
  - `cli.py` - Command-line interface
  - `app.py`, `local_loop.py`, `support_loop.py` - Workflow orchestration
  - `git_ops.py`, `gh_ops.py` - Git/GitHub integration
  - `journal.py`, `startup.py` - State management and initialization

**Key Discoveries:**
- **TUI navigation test failure** (`internal/tui/navigation_test.go:115`): Test expects "safescriptdirs" as last settings input, but "allowedpythondirs" was added to the end. Test needs update, not code fix.
- **Python test collection errors**: Many test files have import errors due to `PurePosixPath('.')` issues in pytest discovery
- **Command safety test failures**: 27 tests fail with "Command not allowed" due to `AUTO_PRD_ALLOW_UNSAFE_EXECUTION` not being set in test environment
- **Testing infrastructure is mature**: Both codebases have proper test frameworks (Go testing, pytest), CI integration via Makefile, and established patterns

## Desired End State

**Quantitative Goals:**
- Go coverage: **≥80%** overall (currently 40.4%)
- Python coverage: **≥80%** overall (currently 58%)
- All existing tests passing: **0 failures**
- New tests follow established patterns

**Qualitative Goals:**
- Critical paths (TUI update loop, API server, process management, command execution) have comprehensive test coverage
- Error paths and edge cases are tested
- Tests serve as documentation for expected behavior
- Test suite is fast and reliable (no flaky tests)

**Verification:**
```bash
# Go coverage
go test ./... -coverprofile=coverage.out
go tool cover -func=coverage.out | grep total:  # Should show ≥80%

# Python coverage (once pytest-cov is working)
cd tools && uv run pytest --cov=auto_prd --cov-report=term-missing

# All tests pass
go test ./...  # Should exit 0 with no FAIL lines
cd tools && uv run pytest  # Should show 0 failed
```

## What We're NOT Doing

- **NOT achieving 100% coverage**: Some code (error handlers, log statements) doesn't warrant tests
- **NOT rewriting existing tests**: Only fixing broken tests, not refactoring working ones
- **NOT changing production code**: Tests must adapt to code, not vice versa (unless tests reveal actual bugs)
- **NOT adding integration tests**: Focus is on unit tests for now; integration tests are out of scope
- **NOT setting up coverage reporting tools**: Codecov, coverage badges, etc. are deferred
- **NOT implementing test parallelization**: pytest-xdist is out of scope (test execution time is acceptable)
- **NOT refactoring for testability**: If code is hard to test, we'll adapt the test approach, not the code

## Implementation Approach

**Strategy:** Incremental, phased approach focusing on highest-value targets first. Fix existing tests before adding new ones. Prioritize critical paths over edge cases. Use established patterns from existing tests.

**Key Decisions:**
1. **Fix failing tests first** (Week 1): Cannot build on unstable foundation
2. **TUI testing with headless Bubbletea**: Use `tea.NewProgram(model, tea.WithRenderer(nil))` for Update() function testing
3. **Mock subprocess calls in Python**: Use `unittest.mock.patch` for external commands (git, gh, claude)
4. **Fix Python test environment errors**: Update test collection to handle import errors properly
5. **Keep tests focused and fast**: Avoid slow tests; mock external dependencies

---

## Phase 1: Stabilize Existing Tests (Week 1)

### Overview
Fix all failing tests to establish a reliable baseline. This phase is critical - we cannot measure coverage improvements accurately if tests are failing.

### Changes Required:

#### 1. Fix Go TUI Navigation Tests
**File**: `internal/tui/navigation_test.go:115`

**Problem**: Three tests fail because they expect "safescriptdirs" to be the last settings input, but "allowedpythondirs" was added after the tests were written.

**Root Cause**: Test expectations are out of sync with the actual `settingsInputNames` array in `model.go:239-265`.

**Solution**: Update test expectations to match the actual last element:

```go
// Line 22-29: "settings wrap down" test case
{
    name: "settings wrap down",
    setup: func(m *model) {
        m.focusInput("allowedpythondirs") // Was: safescriptdirs
    },
    action: func(_ *testing.T, m *model) {
        m.navigateSettings("down")
    },
    wantFocus: "repo",
    focusKind: "input",
},

// Line 31-40: "settings wrap up" test case
{
    name: "settings wrap up",
    setup: func(m *model) {
        m.focusInput("repo")
    },
    action: func(_ *testing.T, m *model) {
        m.navigateSettings("up")
    },
    wantFocus: "allowedpythondirs", // Was: safescriptdirs
    focusKind: "input",
},

// Line 54-66: "settings confirm wraps to repo" test case
{
    name: "settings confirm wraps to repo",
    setup: func(m *model) {
        m.focusInput("allowedpythondirs") // Was: safescriptdirs
    },
    action: func(t *testing.T, m *model) {
        if handled, _ := m.handleSettingsTabActions([]Action{ActConfirm}, tea.KeyMsg{}); !handled {
            t.Fatal("expected confirm action to be handled when wrapping")
        }
    },
    wantFocus: "repo",
    focusKind: "input",
},
```

**Success Criteria**:
- [ ] `go test ./internal/tui -run TestNavigationWrapping -v` passes
- [ ] All 3 navigation test cases pass
- [ ] No other tests regress

#### 2. Fix Python Test Collection Errors
**File**: `tools/auto_prd/tests/test_*.py` (multiple files)

**Problem**: Pytest collection fails with `ValueError: PurePosixPath('.') has an invalid value for 'drive'` errors.

**Root Cause**: Test discovery is trying to import test modules as packages, causing path resolution issues with the `safe_import` helper.

**Solution**: Create a `conftest.py` file to configure pytest properly:

```python
# tools/auto_prd/tests/conftest.py
import sys
from pathlib import Path

# Add tools directory to Python path for imports
tools_dir = Path(__file__).parent.parent.parent
if str(tools_dir) not in sys.path:
    sys.path.insert(0, str(tools_dir))

# Configure pytest to ignore import path issues
def pytest_configure(config):
    """Configure pytest to handle our custom test structure."""
    # Disable strict path validation
    import pytest
    pytest.PYTEST_PARAM_IGNORE_RAISE = True
```

Alternatively, update the `Makefile` to run tests from the correct directory:

```makefile
# In Makefile, line 64
test-py:
	@echo "🧪 Running Python tests..."
	cd $(TOOLS_DIR) && uv run pytest auto_prd/tests/ -v
```

**Success Criteria**:
- [ ] `uv run pytest auto_prd/tests/ --collect-only` succeeds without errors
- [ ] All 569 tests are collected
- [ ] No import-related errors

#### 3. Fix Python Command Safety Tests
**Files**: Multiple test files (27 failures with "Command not allowed")

**Problem**: Tests fail with `SystemExit: Command not allowed: echo` or similar errors.

**Root Cause**: `command.py` has safety checks that prevent execution unless `AUTO_PRD_ALLOW_UNSAFE_EXECUTION=1` is set, but tests don't set this environment variable.

**Solution**: Set the environment variable in test setup. Two approaches:

**Option A: Environment variable in conftest.py** (recommended):
```python
# tools/auto_prd/tests/conftest.py
import os
import pytest

@pytest.fixture(autouse=True)
def allow_unsafe_execution():
    """Allow command execution in tests by setting the safety flag."""
    original_value = os.environ.get("AUTO_PRD_ALLOW_UNSAFE_EXECUTION")
    os.environ["AUTO_PRD_ALLOW_UNSAFE_EXECUTION"] = "1"
    yield
    # Restore original value after test
    if original_value is None:
        os.environ.pop("AUTO_PRD_ALLOW_UNSAFE_EXECUTION", None)
    else:
        os.environ["AUTO_PRD_ALLOW_UNSAFE_EXECUTION"] = original_value
```

**Option B: Set in Makefile** (simpler but less targeted):
```makefile
test-py:
	@echo "🧪 Running Python tests..."
	cd $(TOOLS_DIR) && AUTO_PRD_ALLOW_UNSAFE_EXECUTION=1 uv run pytest auto_prd/tests/ -v
```

**Success Criteria**:
- [ ] `uv run pytest auto_prd/tests/test_command_safety.py -v` passes
- [ ] All 27 command safety tests pass
- [ ] No "Command not allowed" errors

#### 4. Fix Remaining Python Test Failures
**Files**:
- `test_agents.py` - 3 failures (TypeError: fileno())
- `test_guardrails.py` - 12 failures (AttributeError: parse_owner_repo_from_git)
- `test_versioned_criteria.py` - 3 failures (data structure mismatches)
- `test_verification.py` - 1 failure (tuple vs object attribute error)

**Approach**: For each test file:
1. Read the test code
2. Identify the specific assertion or call that fails
3. Check if the test expectation is wrong or the code changed
4. Update test to match current implementation (or file bug if code is wrong)

**Success Criteria**:
- [ ] `uv run pytest auto_prd/tests/ -v` shows 0 failed, 523+ passed
- [ ] All 569 tests pass (after fixing collection issues)
- [ ] No warnings or skipped tests (unless intentional)

### Success Criteria:

#### Automated Verification:
- [ ] `make test` passes completely (Go + Python)
- [ ] `go test ./... -v` shows 0 FAIL results
- [ ] `cd tools && uv run pytest auto_prd/tests/` shows 0 failed
- [ ] No test warnings or skipped tests (unless intentional)

#### Manual Verification:
- [ ] Run test suite 3 times to ensure no flaky tests
- [ ] Check test execution time is acceptable (<2 minutes for Go, <1 minute for Python)
- [ ] Review code coverage report to confirm baseline

**Note**: Complete all automated verification, then pause for manual confirmation before proceeding to Phase 2. **All tests must pass before adding new tests.**

---

## Phase 2: High-Value Go Components (Weeks 2-3)

### Overview
Add comprehensive tests for critical Go components with zero or near-zero coverage. Focus on the TUI update loop, API server, and process management - these are high-impact, high-risk areas.

### Changes Required:

#### 1. API Server Tests
**File**: `internal/api/server_test.go` (new file)

**Coverage Target**: 90%+ for `server.go` (currently 0%)

**Test Structure**:
```go
package api

import (
    "context"
    "net/http"
    "net/http/httptest"
    "testing"
    "time"
)

func TestNewServer(t *testing.T) {
    t.Parallel()

    tests := []struct {
        name       string
        cfg        Config
        wantAddr   string
        wantNotNil bool
    }{
        {
            name: "default address",
            cfg:  Config{},
            wantAddr: ":8080",
            wantNotNil: true,
        },
        {
            name: "custom address",
            cfg: Config{Addr: ":9090"},
            wantAddr: ":9090",
            wantNotNil: true,
        },
        {
            name: "with timeouts",
            cfg: Config{
                Addr: ":8080",
                ReadTimeout: 10 * time.Second,
                WriteTimeout: 5 * time.Second,
                IdleTimeout: 120 * time.Second,
            },
            wantAddr: ":8080",
            wantNotNil: true,
        },
    }

    for _, tc := range tests {
        t.Run(tc.name, func(t *testing.T) {
            t.Parallel()

            srv := NewServer(tc.cfg, Dependencies{})
            if srv == nil && tc.wantNotNil {
                t.Fatal("NewServer() returned nil")
            }
            if srv.Addr() != tc.wantAddr {
                t.Errorf("Addr() = %q, want %q", srv.Addr(), tc.wantAddr)
            }
            if srv.Handler() == nil {
                t.Error("Handler() returned nil")
            }
        })
    }
}

func TestServerLifecycle(t *testing.T) {
    t.Parallel() // Note: Can't use t.Parallel() with t.Setenv()

    t.Run("Start and Shutdown", func(t *testing.T) {
        srv := NewServer(Config{Addr: ":0"}, Dependencies{}) // :0 for random port

        // Start server in background
        errCh := make(chan error, 1)
        go func() {
            errCh <- srv.Start()
        }()

        // Wait for server to be ready
        time.Sleep(100 * time.Millisecond)

        // Test that server responds
        client := &http.Client{Timeout: 1 * time.Second}
        resp, err := client.Get("http://" + srv.Addr() + "/health")
        if err != nil {
            t.Fatalf("Failed to connect to server: %v", err)
        }
        if resp.StatusCode != http.StatusOK {
            t.Errorf("Health check returned status %d", resp.StatusCode)
        }
        resp.Body.Close()

        // Shutdown server
        ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
        defer cancel()
        if err := srv.Shutdown(ctx); err != nil {
            t.Errorf("Shutdown() failed: %v", err)
        }

        // Verify Start() returned
        if err := <-errCh; err != nil && err != http.ErrServerClosed {
            t.Errorf("Start() returned error: %v", err)
        }
    })

    t.Run("StartListener", func(t *testing.T) {
        srv := NewServer(Config{}, Dependencies{})

        listener, err := (&net.ListenConfig{}).Listen(context.Background(), "tcp", ":0")
        if err != nil {
            t.Fatalf("Failed to create listener: %v", err)
        }
        defer listener.Close()

        errCh := make(chan error, 1)
        go func() {
            errCh <- srv.StartListener(listener)
        }()

        time.Sleep(100 * time.Millisecond)

        ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
        defer cancel()
        if err := srv.Shutdown(ctx); err != nil {
            t.Errorf("Shutdown() failed: %v", err)
        }

        if err := <-errCh; err != nil && err != http.ErrServerClosed {
            t.Errorf("StartListener() returned error: %v", err)
        }
    })
}

func TestChooseDuration(t *testing.T) {
    t.Parallel()

    tests := []struct {
        name     string
        candidate time.Duration
        fallback time.Duration
        want     time.Duration
    }{
        {
            name: "positive candidate uses candidate",
            candidate: 10 * time.Second,
            fallback: 5 * time.Second,
            want: 10 * time.Second,
        },
        {
            name: "zero candidate uses fallback",
            candidate: 0,
            fallback: 5 * time.Second,
            want: 5 * time.Second,
        },
        {
            name: "negative candidate uses fallback",
            candidate: -5 * time.Second,
            fallback: 5 * time.Second,
            want: 5 * time.Second,
        },
    }

    for _, tc := range tests {
        t.Run(tc.name, func(t *testing.T) {
            t.Parallel()
            got := chooseDuration(tc.candidate, tc.fallback)
            if got != tc.want {
                t.Errorf("chooseDuration(%v, %v) = %v, want %v",
                    tc.candidate, tc.fallback, got, tc.want)
            }
        })
    }
}
```

**Success Criteria**:
- [ ] `go test ./internal/api -v -cover` shows ≥90% coverage for server.go
- [ ] All server lifecycle tests pass (including concurrent tests)
- [ ] Tests complete in <5 seconds

#### 2. Process Management Tests (Unix)
**File**: `internal/runner/proc_test.go` (new file, Unix-only)

**Coverage Target**: 85%+ for `proc_unix.go` (currently 0-43%)

**Test Structure**:
```go
//go:build !windows

package runner

import (
    "os/exec"
    "syscall"
    "testing"
    "time"
)

func TestInterruptProcess(t *testing.T) {
    t.Parallel()

    t.Run("nil process returns nil", func(t *testing.T) {
        t.Parallel()
        cmd := &exec.Cmd{}
        if err := interruptProcess(cmd); err != nil {
            t.Errorf("interruptProcess(nil) should return nil, got %v", err)
        }
    })

    t.Run("exited process returns nil", func(t *testing.T) {
        t.Parallel()
        cmd := exec.Command("echo", "done")
        if err := cmd.Start(); err != nil {
            t.Fatal(err)
        }
        if err := cmd.Wait(); err != nil {
            t.Fatal(err)
        }
        // Process has exited
        if err := interruptProcess(cmd); err != nil {
            t.Errorf("interruptProcess(exited) should return nil, got %v", err)
        }
    })

    t.Run("running process receives SIGINT", func(t *testing.T) {
        // This test is tricky because we need a long-running process
        // Use sleep with a long duration, then interrupt it
        cmd := exec.Command("sleep", "60")
        if err := cmd.Start(); err != nil {
            t.Fatal(err)
        }

        // Give process time to start
        time.Sleep(100 * time.Millisecond)

        // Interrupt the process
        if err := interruptProcess(cmd); err != nil {
            t.Errorf("interruptProcess() failed: %v", err)
        }

        // Wait should return quickly (process was killed)
        done := make(chan error, 1)
        go func() {
            done <- cmd.Wait()
        }()

        select {
        case err := <-done:
            // Process should have been interrupted
            if err == nil {
                t.Error("Expected process to be interrupted, but it exited normally")
            }
        case <-time.After(2 * time.Second):
            t.Error("Process did not exit within timeout after interrupt")
        }
    })
}

func TestForceKillProcess(t *testing.T) {
    t.Parallel()

    t.Run("nil process returns nil", func(t *testing.T) {
        t.Parallel()
        cmd := &exec.Cmd{}
        if err := forceKillProcess(cmd); err != nil {
            t.Errorf("forceKillProcess(nil) should return nil, got %v", err)
        }
    })

    t.Run("ignores ESRCH and EINVAL errors", func(t *testing.T) {
        t.Parallel()
        // Create a mock process that will return ESRCH
        cmd := exec.Command("echo", "test")
        if err := cmd.Start(); err != nil {
            t.Fatal(err)
        }
        cmd.Wait() // Let it exit

        // Trying to kill an exited process should succeed (ignores ESRCH)
        if err := forceKillProcess(cmd); err != nil {
            t.Errorf("forceKillProcess(exited) should return nil, got %v", err)
        }
    })
}

func TestInterruptProcessCmd(t *testing.T) {
    t.Parallel()

    t.Run("nil process returns nil", func(t *testing.T) {
        t.Parallel()
        var proc *os.Process = nil
        if err := interruptProcessCmd(proc); err != nil {
            t.Errorf("interruptProcessCmd(nil) should return nil, got %v", err)
        }
    })
}

func TestForceKillProcessCmd(t *testing.T) {
    t.Parallel()

    t.Run("nil process returns nil", func(t *testing.T) {
        t.Parallel()
        var proc *os.Process = nil
        if err := forceKillProcessCmd(proc); err != nil {
            t.Errorf("forceKillProcessCmd(nil) should return nil, got %v", err)
        }
    })
}
```

**Success Criteria**:
- [ ] `go test ./internal/runner -run "^Test.*Process" -v -cover` shows ≥85% coverage
- [ ] All process management tests pass
- [ ] Tests are reliable (no race conditions)

#### 3. TUI Update Loop Tests
**File**: `internal/tui/update_test.go` (new file)

**Coverage Target**: 70%+ for `update.go` (currently 7.4%)

**Challenge**: Bubbletea programs require specialized testing. We'll test the Update() function by sending controlled Msg sequences and verifying state changes.

**Test Structure**:
```go
package tui

import (
    "testing"
    "time"

    tea "github.com/charmbracelet/bubbletea"
)

func TestUpdateWindowSizeMsg(t *testing.T) {
    t.Parallel()

    m := model{}
    msg := tea.WindowSizeMsg{Width: 120, Height: 40}

    newModel, cmd := m.Update(msg)
    if cmd != nil {
        t.Error("WindowSizeMsg should not return a command")
    }

    newM, ok := newModel.(model)
    if !ok {
        t.Fatal("Update() should return a model")
    }

    // Verify viewport sizes were updated
    if newM.logs.Width != 120 {
        t.Errorf("logs width = %d, want %d", newM.logs.Width, 120)
    }
}

func TestUpdateToastExpiredMsg(t *testing.T) {
    t.Parallel()

    m := model{
        toast: &toastState{
            id:        1,
            message:   "test",
            expiresAt: time.Now(),
        },
    }

    msg := toastExpiredMsg{id: 1}
    newModel, cmd := m.Update(msg)
    if cmd != nil {
        t.Error("toastExpiredMsg should not return a command")
    }

    newM, ok := newModel.(model)
    if !ok {
        t.Fatal("Update() should return a model")
    }

    if newM.toast != nil {
        t.Error("toast should be cleared after expiry")
    }
}

func TestUpdateStatusMsg(t *testing.T) {
    t.Parallel()

    t.Run("update status text", func(t *testing.T) {
        t.Parallel()
        m := model{status: "old status"}

        msg := statusMsg{note: "new status"}
        newModel, cmd := m.Update(msg)
        if cmd != nil {
            t.Error("statusMsg should not return a command")
        }

        newM, ok := newModel.(model)
        if !ok {
            t.Fatal("Update() should return a model")
        }

        if newM.status != "new status" {
            t.Errorf("status = %q, want %q", newM.status, "new status")
        }
    })

    t.Run("quit after save success", func(t *testing.T) {
        t.Parallel()
        m := model{
            quitAfterSave: true,
            lastSaveErr:   nil,
        }

        msg := statusMsg{note: "Saved"}
        newModel, cmd := m.Update(msg)

        // Should return tea.Quit command
        if cmd == nil {
            t.Fatal("should return tea.Quit command")
        }
    })
}

func TestUpdateRunStartMsg(t *testing.T) {
    t.Parallel()

    m := model{}
    msg := runStartMsg{}

    newModel, cmd := m.Update(msg)
    if cmd == nil {
        t.Error("runStartMsg should return a flash command")
    }

    newM, ok := newModel.(model)
    if !ok {
        t.Fatal("Update() should return a model")
    }

    if !newM.running {
        t.Error("running should be true after runStartMsg")
    }
    if newM.errMsg != "" {
        t.Errorf("errMsg should be cleared, got %q", newM.errMsg)
    }
    if newM.status != "Running…" {
        t.Errorf("status = %q, want %q", newM.status, "Running…")
    }
}

func TestUpdateLogBatchMsg(t *testing.T) {
    t.Parallel()

    m := model{}
    msg := logBatchMsg{
        logs: []string{"line1", "line2"},
    }

    newModel, cmd := m.Update(msg)
    if cmd != nil {
        t.Error("logBatchMsg should not return a command")
    }

    newM, ok := newModel.(model)
    if !ok {
        t.Fatal("Update() should return a model")
    }

    // Verify logs were added
    // This requires understanding the internal log buffer structure
}
```

**Success Criteria**:
- [ ] `go test ./internal/tui -run "^TestUpdate" -v -cover` shows ≥70% coverage for update.go
- [ ] Update() function correctly handles all message types
- [ ] State transitions are verified
- [ ] Tests are fast and reliable

### Success Criteria:

#### Automated Verification:
- [ ] `go test ./internal/api ./internal/runner ./internal/tui -v` all pass
- [ ] `go test ./... -coverprofile=coverage.out && go tool cover -func=coverage.out | grep total:` shows ≥55% overall coverage
- [ ] No new test failures
- [ ] Test execution time <10 seconds

#### Manual Verification:
- [ ] Review test coverage report to verify untested branches are edge cases
- [ ] Manually test TUI to ensure Update() function changes don't break behavior
- [ ] Run API server and verify it still starts/stops correctly

**Note**: Each component (server, process, update) should be tested independently. Complete all automated verification before proceeding to Phase 3.

---

## Phase 3: High-Value Python Components (Weeks 4-5)

### Overview
Add comprehensive tests for critical Python infrastructure components. Focus on command execution, agent integration, and the CLI - these are the core interaction points with external systems.

### Changes Required:

#### 1. Command Execution Tests
**File**: `tools/auto_prd/tests/test_command.py` (new file)

**Coverage Target**: 75%+ for `command.py` (currently ~0%)

**Test Structure**:
```python
"""
Tests for command.py - shell command execution with safety checks.

Security is paramount here - we verify that:
1. Dangerous commands are rejected
2. Secrets are sanitized from error messages
3. Safe CWD restrictions are enforced
4. Command output is handled correctly
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, Mock

from .test_helpers import safe_import

# Import functions under test
run_cmd = safe_import("tools.auto_prd.command", "..command", "run_cmd")
popen_streaming = safe_import("tools.auto_prd.command", "..command", "popen_streaming")
CommandResult = safe_import("tools.auto_prd.command", "..command", "CommandResult")
register_safe_cwd = safe_import("tools.auto_prd.command", "..command", "register_safe_cwd")


class RunCmdTests(unittest.TestCase):
    """Test run_cmd() function with various scenarios."""

    def test_successful_command(self) -> None:
        """Verify run_cmd returns correct output for successful commands."""
        result = run_cmd(["echo", "hello"], check=False)
        self.assertIsInstance(result, CommandResult)
        self.assertTrue(result.is_success())
        self.assertIn("hello", result.stdout)
        self.assertEqual(result.exit_code, 0)

    def test_failed_command(self) -> None:
        """Verify run_cmd handles failed commands correctly."""
        result = run_cmd(["false"], check=False)
        self.assertFalse(result.is_success())
        self.assertEqual(result.exit_code, 1)

    def test_command_with_stderr(self) -> None:
        """Verify stderr is captured correctly."""
        result = run_cmd(
            ["sh", "-c", "echo error >&2"],
            check=False
        )
        self.assertIn("error", result.stderr)

    @patch.dict(os.environ, {"AUTO_PRD_ALLOW_UNSAFE_EXECUTION": "1"})
    def test_command_timeout(self) -> None:
        """Verify commands timeout correctly."""
        with self.assertRaises(subprocess.TimeoutExpired):
            run_cmd(["sleep", "10"], timeout=0.1)

    def test_environment_variables_passed(self) -> None:
        """Verify environment variables are passed to subprocess."""
        result = run_cmd(
            ["sh", "-c", "echo $TEST_VAR"],
            env={"TEST_VAR": "test_value"},
            check=False
        )
        self.assertIn("test_value", result.stdout)

    def test_working_directory(self) -> None:
        """Verify working directory is respected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_cmd(
                ["pwd"],
                cwd=Path(tmpdir),
                check=False
            )
            self.assertIn(tmpdir, result.stdout)


class CommandResultTests(unittest.TestCase):
    """Test CommandResult dataclass behavior."""

    def test_tuple_unpacking(self) -> None:
        """Verify backward-compatible tuple unpacking works."""
        result = CommandResult(
            stdout="out",
            stderr="err",
            exit_code=1
        )
        stdout, stderr, exit_code = result
        self.assertEqual(stdout, "out")
        self.assertEqual(stderr, "err")
        self.assertEqual(exit_code, 1)

    def test_is_success(self) -> None:
        """Verify is_success() returns correct boolean."""
        success = CommandResult("out", "err", 0)
        self.assertTrue(success.is_success())

        failure = CommandResult("out", "err", 1)
        self.assertFalse(failure.is_success())

    def test_get_error_message_from_stderr(self) -> None:
        """Verify get_error_message() prefers stderr."""
        result = CommandResult(
            stdout="ignore this",
            stderr="actual error",
            exit_code=1
        )
        self.assertIn("actual error", result.get_error_message())
        self.assertNotIn("ignore this", result.get_error_message())

    def test_get_error_message_falls_back_to_stdout(self) -> None:
        """Verify get_error_message() falls back to stdout when stderr is empty."""
        result = CommandResult(
            stdout="stdout error",
            stderr="",
            exit_code=1
        )
        self.assertIn("stdout error", result.get_error_message())

    def test_get_error_message_falls_back_to_exit_code(self) -> None:
        """Verify get_error_message() falls back to exit code when both streams are empty."""
        result = CommandResult(
            stdout="",
            stderr="",
            exit_code=42
        )
        self.assertIn("42", result.get_error_message())


class SafeCWDTests(unittest.TestCase):
    """Test safe CWD restrictions."""

    def test_register_safe_cwd_adds_to_roots(self) -> None:
        """Verify register_safe_cwd adds directory to allowed roots."""
        with tempfile.TemporaryDirectory() as tmpdir:
            register_safe_cwd(Path(tmpdir))
            # Verify the directory is now in SAFE_CWD_ROOTS
            # (This requires importing the constant)

    def test_unsafe_cwd_rejected(self) -> None:
        """Verify commands outside safe CWD are rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            unsafe_path = Path(tmpdir) / "unsafe"
            unsafe_path.mkdir()

            with self.assertRaises(SystemExit):
                run_cmd(["pwd"], cwd=unsafe_path, check=False)


class SecurityTests(unittest.TestCase):
    """Test security-related functionality."""

    def test_secrets_not_in_errors(self) -> None:
        """Verify secrets are excluded from error messages."""
        # This tests the interaction between command.py and utils.py
        # which does the actual sanitization
        pass

    @patch.dict(os.environ, {"AUTO_PRD_ALLOW_UNSAFE_EXECUTION": "1"})
    def test_stdin_validation(self) -> None:
        """Verify stdin content is validated for safety."""
        # Test with mock stdin
        pass


if __name__ == "__main__":
    unittest.main()
```

**Success Criteria**:
- [ ] `uv run pytest tests/test_command.py -v --cov=auto_prd.command` shows ≥75% coverage
- [ ] All command execution tests pass
- [ ] Security tests verify secret sanitization
- [ ] Tests mock subprocess calls appropriately (no real external commands)

#### 2. Agent Integration Tests (Enhanced)
**File**: `tools/auto_prd/tests/test_agents.py` (enhance existing)

**Coverage Target**: 65%+ for `agents.py` (currently ~20%)

**Additional Tests**:
```python
class ClaudeStreamingTests(unittest.TestCase):
    """Test claude_exec_streaming() function."""

    @patch.dict(os.environ, {"AUTO_PRD_ALLOW_UNSAFE_EXECUTION": "1"})
    @patch("subprocess.Popen")
    def test_streaming_timeout(self, mock_popen: Mock) -> None:
        """Verify streaming respects timeout configuration."""
        # Mock a subprocess that times out
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout = MagicMock()
        mock_process.stderr = MagicMock()
        mock_popen.return_value = mock_process

        # This should timeout and raise an error
        # (Implementation depends on actual timeout logic)
        pass

    @patch.dict(os.environ, {"AUTO_PRD_ALLOW_UNSAFE_EXECUTION": "1"})
    @patch("subprocess.Popen")
    def test_buffer_processing(self, mock_popen: Mock) -> None:
        """Verify streaming buffer processes JSON chunks correctly."""
        # Mock subprocess returning JSON data
        pass

    def test_rate_limit_handling(self) -> None:
        """Verify rate limits are respected with jitter."""
        # Test rate limit backoff logic
        pass


class TimeoutConfigurationTests(unittest.TestCase):
    """Test timeout configuration from environment variables."""

    @patch.dict(os.environ, {"CLAUDE_TIMEOUT_SECONDS": "120"})
    def test_claude_timeout_from_env(self) -> None:
        """Verify Claude timeout is read from environment."""
        timeout = get_claude_exec_timeout()
        self.assertEqual(timeout, 120)

    @patch.dict(os.environ, {}, clear=True)
    def test_default_claude_timeout(self) -> None:
        """Verify default timeout is used when env var is not set."""
        timeout = get_claude_exec_timeout()
        self.assertEqual(timeout, DEFAULT_CLAUDE_TIMEOUT_SECONDS)

    @patch.dict(os.environ, {"CODEX_TIMEOUT_SECONDS": "60"})
    def test_codex_timeout_from_env(self) -> None:
        """Verify Codex timeout is read from environment."""
        timeout = get_codex_exec_timeout()
        self.assertEqual(timeout, 60)
```

**Success Criteria**:
- [ ] `uv run pytest tests/test_agents.py -v --cov=auto_prd.agents` shows ≥65% coverage
- [ ] All streaming and timeout tests pass
- [ ] Mock subprocess calls are realistic and reliable

#### 3. CLI Tests
**File**: `tools/auto_prd/tests/test_cli.py` (new file)

**Coverage Target**: 60%+ for `cli.py` (currently ~0%)

**Test Structure**:
```python
"""
Tests for cli.py - command-line interface argument parsing and main entry point.
"""

import argparse
import unittest
from unittest.mock import patch, MagicMock

from .test_helpers import safe_import

# Import CLI functions
parse_args = safe_import("tools.auto_prd.cli", "..cli", "parse_args")
main = safe_import("tools.auto_prd.cli", "..cli", "main")


class ParseArgsTests(unittest.TestCase):
    """Test command-line argument parsing."""

    def test_default_arguments(self) -> None:
        """Verify default values for all arguments."""
        # Test with no arguments
        args = parse_args([])
        # Verify defaults match expected values

    def test_prd_argument(self) -> None:
        """Verify --prd argument sets PRD path."""
        args = parse_args(["--prd", "/path/to/prd.md"])
        self.assertEqual(args.prd, Path("/path/to/prd.md"))

    def test_phases_argument(self) -> None:
        """Verify --phases argument is parsed correctly."""
        args = parse_args(["--phases", "local,pr,review_fix"])
        # Verify phases are set correctly

    def test_executor_arguments(self) -> None:
        """Verify executor selection arguments work."""
        args = parse_args([
            "--local-executor", "claude",
            "--pr-executor", "codex",
            "--review-executor", "claude"
        ])
        # Verify executors are set

    def test_flag_arguments(self) -> None:
        """Verify boolean flags are parsed correctly."""
        args = parse_args([
            "--unsafe",
            "--dry-run",
            "--sync-git"
        ])
        self.assertTrue(args.unsafe)
        self.assertTrue(args.dry_run)
        self.assertTrue(args.sync_git)


class MainTests(unittest.TestCase):
    """Test main entry point."""

    @patch("tools.auto_prd.cli.run_loop")
    def test_successful_execution(self, mock_run_loop: Mock) -> None:
        """Verify main() calls run_loop with correct arguments."""
        mock_run_loop.return_value = 0

        with patch("sys.argv", ["auto_prd", "--prd", "test.md"]):
            exit_code = main()
            self.assertEqual(exit_code, 0)
            mock_run_loop.assert_called_once()

    @patch("tools.auto_prd.cli.run_loop")
    def test_keyboard_interrupt(self, mock_run_loop: Mock) -> None:
        """Verify main() handles KeyboardInterrupt gracefully."""
        mock_run_loop.side_effect = KeyboardInterrupt()

        with patch("sys.argv", ["auto_prd", "--prd", "test.md"]):
            exit_code = main()
            self.assertEqual(exit_code, 130)  # Standard exit code for SIGINT

    @patch("tools.auto_prd.cli.run_loop")
    def test_generic_exception(self, mock_run_loop: Mock) -> None:
        """Verify main() handles unexpected exceptions."""
        mock_run_loop.side_effect = Exception("Unexpected error")

        with patch("sys.argv", ["auto_prd", "--prd", "test.md"]):
            exit_code = main()
            self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
```

**Success Criteria**:
- [ ] `uv run pytest tests/test_cli.py -v --cov=auto_prd.cli` shows ≥60% coverage
- [ ] All argument parsing tests pass
- [ ] Main entry point error handling is tested

### Success Criteria:

#### Automated Verification:
- [ ] `cd tools && uv run pytest tests/test_command.py tests/test_agents.py tests/test_cli.py -v` all pass
- [ ] `uv run pytest --cov=auto_prd --cov-report=term-missing` shows ≥65% overall coverage
- [ ] No new test failures
- [ ] Test execution time <30 seconds for these three files

#### Manual Verification:
- [ ] Run actual command execution to ensure mocks don't hide real bugs
- [ ] Test CLI with various argument combinations
- [ ] Verify agent execution still works with real Claude CLI

**Note**: Each module (command, agents, cli) should be tested independently. Use mocking extensively to avoid dependencies on external tools (git, gh, claude).

---

## Phase 4: Moderate-Value Components (Weeks 6-7)

### Overview
Add tests for medium-priority components. These are important but less critical than the components tested in Phases 2-3. Focus on TUI views, config management, and workflow orchestration.

### Changes Required:

#### 1. TUI View Tests
**Files**: Multiple `internal/tui/view_*.go` test files (new)

**Coverage Target**: 60%+ for all view files combined

**Approach**: Since views are primarily rendering functions (they return strings), tests verify that:
- Correct view is selected based on model state
- Key strings are present in the output
- Edge cases (empty lists, errors) are handled

**Example for view_settings.go**:
```go
package tui

import (
    "strings"
    "testing"

    tea "github.com/charmbracelet/bubbletea"
)

func TestViewSettingsRendering(t *testing.T) {
    t.Parallel()

    m := newModelForSettingsTest()
    m.tabIndex = 1 // Settings tab

    view := m.View()

    // Verify key sections are present
    if !strings.Contains(view, "Repository") {
        t.Error("Settings view should contain 'Repository' section")
    }
    if !strings.Contains(view, "Python") {
        t.Error("Settings view should contain 'Python' section")
    }
    if !strings.Contains(view, "Ralph") {
        t.Error("Settings view should contain 'Ralph' section")
    }
}

func TestViewSettingsHelpText(t *testing.T) {
    t.Parallel()

    m := newModelForSettingsTest()
    m.tabIndex = 1

    view := m.View()

    // Verify help text is present
    if !strings.Contains(view, "ctrl+q") {
        t.Error("Settings view should contain keyboard shortcuts")
    }
}
```

**Success Criteria**:
- [ ] All view files have basic rendering tests
- [ ] Coverage for `internal/tui` package increases from 32.6% to ≥55%
- [ ] Tests verify presence of key UI elements

#### 2. Config Loading and Saving Tests
**File**: `internal/config/config_test.go` (enhance existing)

**Coverage Target**: 80%+ for `config.go` (currently 50.4%)

**Additional Tests**:
```go
func TestLoad(t *testing.T) {
    t.Parallel()

    t.Run("load non-existent config returns defaults", func(t *testing.T) {
        t.Parallel()
        tmpDir := t.TempDir()
        os.Setenv("AUTODEV_CONFIG_DIR", tmpDir)
        defer os.Unsetenv("AUTODEV_CONFIG_DIR")

        cfg := Load()
        if cfg == nil {
            t.Fatal("Load() should never return nil")
        }

        // Verify defaults are applied
        expected := Defaults()
        if !cfg.Equal(&expected) {
            t.Error("Non-existent config should return defaults")
        }
    })

    t.Run("load valid config from file", func(t *testing.T) {
        t.Parallel()
        tmpDir := t.TempDir()
        configPath := filepath.Join(tmpDir, "config.json")

        // Write a valid config
        validCfg := Defaults()
        validCfg.Repo = "test/repo"
        data, _ := json.Marshal(validCfg)
        os.WriteFile(configPath, data, 0644)

        os.Setenv("AUTODEV_CONFIG_DIR", tmpDir)
        defer os.Unsetenv("AUTODEV_CONFIG_DIR")

        cfg := Load()
        if cfg.Repo != "test/repo" {
            t.Errorf("Repo = %q, want %q", cfg.Repo, "test/repo")
        }
    })

    t.Run("migrate old config version", func(t *testing.T) {
        // Test config migration logic
    })
}

func TestSave(t *testing.T) {
    t.Parallel()

    t.Run("save config to file", func(t *testing.T) {
        t.Parallel()
        tmpDir := t.TempDir()
        os.Setenv("AUTODEV_CONFIG_DIR", tmpDir)
        defer os.Unsetenv("AUTODEV_CONFIG_DIR")

        cfg := Defaults()
        cfg.Repo = "test/repo"

        err := cfg.Save()
        if err != nil {
            t.Fatalf("Save() failed: %v", err)
        }

        // Verify file exists
        configPath := filepath.Join(tmpDir, "config.json")
        if _, err := os.Stat(configPath); os.IsNotExist(err) {
            t.Error("Config file was not created")
        }

        // Verify content
        data, _ := os.ReadFile(configPath)
        var savedCfg Config
        if err := json.Unmarshal(data, &savedCfg); err != nil {
            t.Fatalf("Failed to parse saved config: %v", err)
        }

        if savedCfg.Repo != "test/repo" {
            t.Errorf("Saved Repo = %q, want %q", savedCfg.Repo, "test/repo")
        }
    })
}
```

**Success Criteria**:
- [ ] `go test ./internal/config -v -cover` shows ≥80% coverage
- [ ] Config loading/saving/migration all tested
- [ ] Error paths (invalid JSON, permission errors) are tested

#### 3. Python Workflow Modules
**Files**: `tools/auto_prd/tests/test_local_loop.py`, `test_git_ops.py`, `test_gh_ops.py` (new files)

**Coverage Target**: 50%+ for each module (currently ~0%)

**Approach**: Focus on control flow and decision logic. Mock all external subprocess calls.

**Example for local_loop.py**:
```python
class LocalLoopTests(unittest.TestCase):
    """Test local execution loop logic."""

    @patch("tools.auto_prd.local_loop.run_cmd")
    @patch("tools.auto_prd.local_loop.execute_phase")
    def test_successful_iteration(
        self,
        mock_execute_phase: Mock,
        mock_run_cmd: Mock
    ) -> None:
        """Verify a single iteration executes successfully."""
        # Setup mocks
        mock_execute_phase.return_value = 0
        mock_run_cmd.return_value = CommandResult("", "", 0)

        # Run loop iteration
        # (Implementation depends on actual loop structure)

        mock_execute_phase.assert_called()

    @patch("tools.auto_prd.local_loop.run_cmd")
    def test_command_failure_handling(self, mock_run_cmd: Mock) -> None:
        """Verify loop handles command failures gracefully."""
        mock_run_cmd.return_value = CommandResult(
            stdout="",
            stderr="command failed",
            exit_code=1
        )

        # Verify loop continues or exits appropriately
        pass
```

**Success Criteria**:
- [ ] `uv run pytest tests/test_local_loop.py tests/test_git_ops.py tests/test_gh_ops.py -v` all pass
- [ ] All external subprocess calls are mocked
- [ ] Error handling paths are tested

### Success Criteria:

#### Automated Verification:
- [ ] `go test ./... -coverprofile=coverage.out && go tool cover -func=coverage.out | grep total:` shows ≥70% overall coverage
- [ ] `cd tools && uv run pytest --cov=auto_prd` shows ≥75% overall coverage
- [ ] No new test failures
- [ ] Test execution time <1 minute total

#### Manual Verification:
- [ ] Run full TUI to verify views render correctly
- [ ] Test config loading/saving with real files
- [ ] Execute a local loop to ensure mocks don't hide bugs

**Note**: These components are less critical, so focus on happy paths and obvious error cases. Don't test every edge case.

---

## Phase 5: Edge Cases and Error Paths (Week 8)

### Overview
Improve coverage of partially-tested files by adding tests for edge cases, error paths, and boundary conditions. This phase pushes us from ~75% coverage to the 80%+ target.

### Changes Required:

#### 1. Go Runner Package Error Paths
**File**: `internal/runner/runner_test.go` (enhance existing)

**Coverage Target**: 80%+ for `runner.go` (currently 69.3%)

**Additional Tests**:
```go
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
            name:    "disallow -m flag",
            flags:   []string{"-m", "module"},
            wantErr: true,
            errMsg:  "disallowed Python flag",
        },
        {
            name:    "allow safe flags",
            flags:   []string{"-u", "-E", "-I"},
            wantErr: false,
        },
        {
            name:    "disallow dangerous flag in group",
            flags:   []string{"-ucm"},
            wantErr: true,
            errMsg:  "disallowed Python flag in group",
        },
        {
            name:    "disallow long flags",
            flags:   []string{"--verbose"},
            wantErr: true,
            errMsg:  "disallowed long flag",
        },
        {
            name:    "allow -X dev",
            flags:   []string{"-X", "dev"},
            wantErr: false,
        },
        {
            name:    "disallow -X with invalid argument",
            flags:   []string{"-X", "unsafe"},
            wantErr: true,
            errMsg:  "disallowed argument to -X",
        },
    }

    for _, tc := range tests {
        t.Run(tc.name, func(t *testing.T) {
            t.Parallel()
            err := ValidatePythonFlagsForTest(tc.flags)
            if tc.wantErr {
                if err == nil {
                    t.Errorf("Expected error containing %q, got nil", tc.errMsg)
                } else if !strings.Contains(err.Error(), tc.errMsg) {
                    t.Errorf("Error = %q, want to contain %q", err.Error(), tc.errMsg)
                }
            } else {
                if err != nil {
                    t.Errorf("Unexpected error: %v", err)
                }
            }
        })
    }
}
```

**Success Criteria**:
- [ ] `go test ./internal/runner -v -cover` shows ≥80% coverage
- [ ] All validation error cases are tested
- [ ] Edge cases (empty arrays, nil values) are handled

#### 2. TUI Keyboard Handler Edge Cases
**Files**: `internal/tui/keys_*.go` test enhancements

**Coverage Target**: 70%+ for all keyboard handlers combined

**Approach**: Add tests for:
- Unknown keys (should be ignored)
- Keys pressed when input is focused vs not focused
- Boundary cases (first/last item in list)
- Modifier key combinations

**Success Criteria**:
- [ ] `go test ./internal/tui -v -cover` shows ≥60% coverage (up from 32.6%)
- [ ] All keyboard handlers have basic tests
- [ ] Edge cases are covered

#### 3. Python Utility Function Edge Cases
**File**: `tools/auto_prd/tests/test_utils.py` (enhance existing)

**Coverage Target**: 90%+ for `utils.py`

**Additional Tests**:
```python
class UtilityFunctionEdgeCases(unittest.TestCase):
    """Test edge cases in utility functions."""

    def test_scrub_cli_text_empty_string(self) -> None:
        """Verify scrubbing empty string returns empty string."""
        result = scrub_cli_text("")
        self.assertEqual(result, "")

    def test_scrub_cli_text_binary_data(self) -> None:
        """Verify scrubbing binary data doesn't crash."""
        binary_data = b"\x00\x01\x02\xff"
        result = scrub_cli_text(binary_data)
        self.assertIsNotNone(result)

    def test_parse_tasks_left_edge_cases(self) -> None:
        """Verify parsing handles edge cases."""
        # Empty string
        self.assertIsNone(parse_tasks_left(""))

        # No tasks left pattern
        self.assertIsNone(parse_tasks_left("No tasks mentioned"))

        # Invalid number
        self.assertIsNone(parse_tasks_left("Tasks left: NaN"))

    def test_compute_file_hash_nonexistent_file(self) -> None:
        """Verify hash computation handles missing files."""
        with self.assertRaises(FileNotFoundError):
            compute_file_hash(Path("/nonexistent/file.txt"))
```

**Success Criteria**:
- [ ] `uv run pytest tests/test_utils.py -v --cov=auto_prd.utils` shows ≥90% coverage
- [ ] All error paths are tested
- [ ] Edge cases don't cause crashes

### Success Criteria:

#### Automated Verification:
- [ ] `go test ./... -coverprofile=coverage.out && go tool cover -func=coverage.out | grep total:` shows ≥80% overall coverage
- [ ] `cd tools && uv run pytest --cov=auto_prd` shows ≥80% overall coverage
- [ ] All tests pass
- [ ] Coverage report shows no untested critical paths

#### Manual Verification:
- [ ] Review coverage report for remaining gaps
- [ ] Verify remaining untested code is truly edge cases
- [ ] Run full test suite 3 times to ensure no flakiness

**Note**: This is the final phase. After this, we should achieve the 80%+ target for both Go and Python.

---

## Testing Strategy

### Unit Tests:
- **Focus**: Test individual functions and methods in isolation
- **Scope**: Happy paths, error paths, edge cases
- **Dependencies**: Mock external dependencies (filesystem, network, subprocess)
- **Speed**: Each test should complete in <100ms

### Integration Tests (Out of Scope):
- End-to-end workflows are NOT covered in this plan
- Integration tests will be addressed in a future initiative

### Manual Testing Steps:
1. After each phase, manually verify the feature still works
2. For TUI: Run the application and verify UI renders correctly
3. For CLI: Test actual command execution with various arguments
4. For API: Start the server and make real HTTP requests

### Coverage Goals:
- **Go**: ≥80% overall (currently 40.4%)
- **Python**: ≥80% overall (currently 58%)
- **Per-package minimums**:
  - Go: No package below 60% (except cmd/ entry points)
  - Python: No module below 50%

## Migration Notes

### Test Environment:
- All tests must run in CI/CD without manual intervention
- No test should depend on specific system state
- Use `t.TempDir()` (Go) and `tempfile.TemporaryDirectory()` (Python) for filesystem operations
- Use `t.Setenv()` (Go) and `patch.dict(os.environ, ...)` (Python) for environment isolation

### Mocking Strategy:
- **Go**: Prefer interfaces over concrete mocks. Extract interfaces where needed.
- **Python**: Use `unittest.mock.patch` extensively. Mock all subprocess calls to external tools.
- **Avoid**: Mocking time (use fixed timestamps instead), mocking randomness (use fixed seeds)

### Test Data:
- Keep test data minimal but realistic
- Avoid copying large production files into test data
- Generate test data programmatically where possible

## References

### Research:
- `/Users/simo/Projects/autodev/.wreckit/items/019-improve-overall-test-coverage-to-80/research.md`

### Existing Test Patterns:
- Go: `internal/tui/model_test.go:14-293` (table-driven tests, helper functions)
- Go: `internal/runner/build_args_test.go` (comprehensive argument testing)
- Python: `tools/auto_prd/tests/test_utils.py:29-100` (security-focused tests)
- Python: `tools/auto_prd/tests/test_helpers.py:7-63` (safe import pattern)

### Key Files:
- `Makefile:34-64` (test commands)
- `internal/tui/navigation_test.go:115` (failing test to fix)
- `internal/api/server.go:30-72` (zero coverage, needs tests)
- `internal/runner/proc_unix.go:15-58` (zero coverage, needs tests)
- `internal/tui/update.go:15-206` (low coverage, needs tests)
- `tools/auto_prd/command.py` (zero coverage, critical module)
- `tools/auto_prd/agents.py` (low coverage, critical module)

### Success Verification:
```bash
# After completion, verify:
go test ./... -coverprofile=coverage.out
go tool cover -func=coverage.out | grep total:  # Should show ≥80%

cd tools && uv run pytest --cov=auto_prd --cov-report=term-missing
# Should show ≥80% coverage
```
