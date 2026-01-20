# Standardize error handling in command execution Implementation Plan

## Overview
Replace the tuple-based return type `(stdout: str, stderr: str, returncode: int)` from `run_cmd()` with a structured `CommandResult` dataclass. This provides self-documenting, type-safe access to command execution results while maintaining backward compatibility with existing code.

## Current State Analysis

### Existing Implementation
The `run_cmd()` function in `tools/auto_prd/command.py:360-549` returns a raw tuple with three elements:
- `stdout: str` - Standard output from the command (decoded)
- `stderr: str` - Standard error output from the command (decoded)
- `returncode: int` - Exit code (0 for success, non-zero for failure)

**Problems with current design:**
1. **Position-dependent access**: Callers must remember tuple ordering, leading to errors like `out, err, exit_code = run_cmd(...)` where variable order matters
2. **No helper methods**: Common operations (checking success, extracting error messages) must be manually implemented at each call site
3. **Scattered error handling**: Error message construction is duplicated across 30+ call sites throughout the codebase
4. **Type safety issues**: Tuple unpacking with ignored values (`out, _, _ = run_cmd(...)`) obscures intent

### Call Site Analysis
From grep analysis, there are **30+ call sites** using these patterns:

1. **Full unpacking with error handling** (most common, 15+ sites):
   ```python
   out, err, exit_code = run_cmd(cmd, cwd=repo_root, check=False)
   if exit_code != 0:
       error_msg = err or out or "Unknown error"
   ```
   Examples: `verification.py:482`, `rollback.py:207`, `initializer.py:324`

2. **Ignoring stderr/exit code** (8+ sites):
   ```python
   out, _, _ = run_cmd(["git", "status", "--porcelain"])
   _, _, exit_code = run_cmd(["git", "diff", "--cached", "--quiet"], check=False)
   ```
   Examples: `git_ops.py:99`, `rollback.py:127`, `pr_flow.py:115`

3. **Exception-based** (when `check=True`, 5+ sites):
   ```python
   try:
       run_cmd(["git", "push", ...])
   except subprocess.CalledProcessError as exc:
       details = extract_called_process_error_details(exc)
   ```
   Examples: `pr_flow.py:110`, `app.py:318-350`

### Existing Patterns to Follow

**Dataclass conventions** (from `worker.py`, `initializer.py`):
- Use `@dataclass` decorator with `field(default_factory=list)` for mutable defaults
- Include type hints on all fields
- Add properties for computed values (e.g., `success` property in `InitResult`)
- Follow naming pattern: `TaskResult`, `InitResult`, `BaselineResult` → `CommandResult`

**Error utilities** (from `utils.py:133-159`):
- `extract_called_process_error_details()` extracts error message from `CalledProcessError`
- Uses stderr only (not stdout) for security to prevent sensitive model output in error messages
- Falls back to `"exit code N"` when stderr is empty

## Desired End State

### Specification

Create a `CommandResult` dataclass with:
1. **Fields**: `stdout: str`, `stderr: str`, `exit_code: int`
2. **Helper methods**:
   - `is_success() -> bool` - Returns `True` if exit_code == 0
   - `get_error_message() -> str` - Returns stderr if available, otherwise stdout, otherwise "exit code N"
3. **Backward compatibility**: `__iter__()` method enabling tuple unpacking
4. **Type annotation**: Update `run_cmd()` return type to `-> CommandResult`

### Verification

**Success criteria:**
- All existing code continues to work without modification (backward compatible)
- New code can use `result.stdout`, `result.stderr`, `result.exit_code` attributes
- Helper methods work correctly: `result.is_success()`, `result.get_error_message()`
- Type annotations are accurate (verified with mypy if available)
- All 30+ call sites work unchanged

**Key Discoveries:**
- ✅ Dataclass pattern is well-established in the codebase (`TaskResult`, `InitResult`, `BaselineResult`)
- ✅ `__iter__()` enables backward compatibility without breaking existing tuple unpacking
- ✅ The name should be `CommandResult` (not `CommandErrorDetails`) to match existing naming patterns
- ✅ `extract_called_process_error_details()` utility can remain for exception-based error handling
- ✅ `run_sh()` helper also needs updating to return `CommandResult`

## What We're NOT Doing

❌ **NOT changing exception behavior**: `run_cmd(check=True)` will still raise `CalledProcessError` on failure
❌ **NOT removing `extract_called_process_error_details()`**: This utility is still useful for exception handling
❌ **NOT deprecating tuple unpacking immediately**: Backward compatibility via `__iter__()` allows gradual migration
❌ **NOT integrating with `StructuredError` from errors.py**: Keep it simple; can be a future enhancement
❌ **NOT changing `popen_streaming()` return type**: That function returns `tuple[Popen, list[str]]` which is different
❌ **NOT modifying `safe_popen()`**: It returns `subprocess.Popen` directly, not a result tuple

## Implementation Approach

### Strategy: Incremental, Backward-Compatible Change

1. **Phase 1**: Create `CommandResult` dataclass with `__iter__()` for backward compatibility
2. **Phase 2**: Update `run_cmd()` to return `CommandResult` instead of tuple
3. **Phase 3**: Update `run_sh()` to return `CommandResult`
4. **Phase 4**: Run tests to verify backward compatibility
5. **Phase 5**: Optionally migrate high-value call sites to use named attributes

### Why This Approach?

- **Zero risk**: Backward compatibility ensures no breakage
- **Incremental value**: Immediate improvement for new code, gradual migration for existing code
- **No migration burden**: Existing code works unchanged; migration is optional
- **Type safety**: New code gets proper type checking, old code continues working

---

## Phase 1: Create CommandResult Dataclass

### Overview
Add the `CommandResult` dataclass to `tools/auto_prd/command.py` with helper methods and backward compatibility.

### Changes Required

#### 1. Add CommandResult to command.py

**File**: `tools/auto_prd/command.py`

**Location**: After line 28 (after imports, before `find_repo_root` function)

**Changes**: Add new dataclass definition

```python
@dataclass
class CommandResult:
    """Result of command execution with structured access to output and exit status.

    This dataclass encapsulates the results of running a subprocess command,
    providing both named attribute access and tuple unpacking for backward
    compatibility.

    Examples:
        # Named attribute access (preferred for new code)
        result = run_cmd(["git", "status"], check=False)
        if result.is_success():
            print(result.stdout)

        # Tuple unpacking (backward compatible)
        stdout, stderr, exit_code = run_cmd(["git", "status"], check=False)
        if exit_code == 0:
            print(stdout)
    """

    stdout: str
    stderr: str
    exit_code: int

    def is_success(self) -> bool:
        """Check if command succeeded (exit code 0).

        Returns:
            True if exit_code is 0, False otherwise.
        """
        return self.exit_code == 0

    def get_error_message(self) -> str:
        """Get error message from command failure.

        Returns stderr content if available; otherwise falls back to stdout;
        otherwise returns a generic exit code message. This matches the
        behavior of extract_called_process_error_details() for security
        (stderr only) with stdout fallback.

        Returns:
            A string containing the error message.
        """
        if self.stderr.strip():
            return self.stderr.strip()
        if self.stdout.strip():
            return self.stdout.strip()
        return f"exit code {self.exit_code}"

    def __iter__(self):
        """Enable backward-compatible tuple unpacking.

        Allows existing code to continue working:
            stdout, stderr, exit_code = result

        Yields:
            Values in order: stdout, stderr, exit_code
        """
        return iter((self.stdout, self.stderr, self.exit_code))
```

**Import addition needed**: Add `from dataclasses import dataclass` to imports at line 4 (if not already present)

### Success Criteria

#### Automated Verification:
- [ ] Python syntax is valid: `python -m py_compile tools/auto_prd/command.py`
- [ ] Type annotations are correct: No import errors

#### Manual Verification:
- [ ] Dataclass can be instantiated: `CommandResult("out", "err", 0)` works
- [ ] `is_success()` returns True for exit_code 0, False otherwise
- [ ] `get_error_message()` returns stderr when available
- [ ] `__iter__()` enables tuple unpacking: `out, err, code = CommandResult("a", "b", 0)` works

**Note**: Complete this phase before proceeding to Phase 2.

---

## Phase 2: Update run_cmd Return Type

### Overview
Modify `run_cmd()` to return `CommandResult` instead of `tuple[str, str, int]`, updating all return statements and the function signature.

### Changes Required

#### 1. Update run_cmd signature

**File**: `tools/auto_prd/command.py`
**Line**: 360 (function definition)

**Before**:
```python
def run_cmd(
    cmd: Sequence[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    capture: bool = True,
    timeout: int | None = None,
    extra_env: dict | None = None,
    stdin: str | None = None,
    sanitize_args: bool = True,
    # Retry parameters (backward compatible defaults)
    retries: int = 0,
    retry_on_codes: set[int] | None = None,
    retry_on_stderr: list[str] | None = None,
    backoff_base: float = 1.0,
    backoff_max: float = 60.0,
    backoff_jitter: float = 0.5,
) -> tuple[str, str, int]:
```

**After**:
```python
def run_cmd(
    cmd: Sequence[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    capture: bool = True,
    timeout: int | None = None,
    extra_env: dict | None = None,
    stdin: str | None = None,
    sanitize_args: bool = True,
    # Retry parameters (backward compatible defaults)
    retries: int = 0,
    retry_on_codes: set[int] | None = None,
    retry_on_stderr: list[str] | None = None,
    backoff_base: float = 1.0,
    backoff_max: float = 60.0,
    backoff_jitter: float = 0.5,
) -> CommandResult:
```

#### 2. Update docstring return type

**File**: `tools/auto_prd/command.py`
**Line**: 397 (in docstring)

**Before**:
```python
    Returns:
        Tuple of (stdout, stderr, returncode).
```

**After**:
```python
    Returns:
        CommandResult containing stdout, stderr, and exit_code fields.
        Supports backward-compatible tuple unpacking: stdout, stderr, exit_code = result.
```

#### 3. Update success return statement

**File**: `tools/auto_prd/command.py`
**Line**: 499

**Before**:
```python
        if proc.returncode == 0:
            logger.info("Command succeeded in %.2fs: %s", duration, cmd_display)
            return stdout_text, stderr_text, proc.returncode
```

**After**:
```python
        if proc.returncode == 0:
            logger.info("Command succeeded in %.2fs: %s", duration, cmd_display)
            return CommandResult(stdout_text, stderr_text, proc.returncode)
```

#### 4. Update failure return statement

**File**: `tools/auto_prd/command.py`
**Line**: 549

**Before**:
```python
        # No more retries - either exhausted or not retryable
        if check:
            raise subprocess.CalledProcessError(
                proc.returncode, sanitized_cmd, output=stdout_bytes, stderr=stderr_bytes
            )

        return stdout_text, stderr_text, proc.returncode
```

**After**:
```python
        # No more retries - either exhausted or not retryable
        if check:
            raise subprocess.CalledProcessError(
                proc.returncode, sanitized_cmd, output=stdout_bytes, stderr=stderr_bytes
            )

        return CommandResult(stdout_text, stderr_text, proc.returncode)
```

### Success Criteria

#### Automated Verification:
- [ ] Module imports successfully: `python -c "from tools.auto_prd.command import run_cmd, CommandResult"`
- [ ] Function signature is correct: Check with `inspect.signature(run_cmd)` if available
- [ ] All existing tests pass (if any exist)

#### Manual Verification:
- [ ] Test with check=False: `result = run_cmd(["echo", "hello"], check=False); assert result.exit_code == 0`
- [ ] Test tuple unpacking still works: `out, err, code = run_cmd(["echo", "test"], check=False)`
- [ ] Test named attributes: `result = run_cmd(["echo", "test"], check=False); print(result.stdout)`
- [ ] Test failure case: `result = run_cmd(["false"], check=False); assert result.exit_code == 1`

**Note**: Complete all automated verification, then pause for manual confirmation before proceeding to Phase 3.

---

## Phase 3: Update run_sh Helper

### Overview
The `run_sh()` function calls `run_cmd()` internally and should also return `CommandResult` for consistency.

### Changes Required

#### 1. Update run_sh signature and return type

**File**: `tools/auto_prd/command.py`
**Line**: 598-606

**Before**:
```python
def run_sh(
    script: str,
    *,
    cwd: Path | None = None,
    check: bool = True,
    capture: bool = True,
    timeout: int | None = None,
    extra_env: dict | None = None,
) -> tuple[str, str, int]:
    verify_unsafe_execution_ready()
    return run_cmd(
        [require_zsh(), "-lc", script],
        cwd=cwd,
        check=check,
        capture=capture,
        timeout=timeout,
        extra_env=extra_env,
    )
```

**After**:
```python
def run_sh(
    script: str,
    *,
    cwd: Path | None = None,
    check: bool = True,
    capture: bool = True,
    timeout: int | None = None,
    extra_env: dict | None = None,
) -> CommandResult:
    verify_unsafe_execution_ready()
    return run_cmd(
        [require_zsh(), "-lc", script],
        cwd=cwd,
        check=check,
        capture=capture,
        timeout=timeout,
        extra_env=extra_env,
    )
```

### Success Criteria

#### Automated Verification:
- [ ] Module imports successfully: `python -c "from tools.auto_prd.command import run_sh"`
- [ ] Return type is correct: Check with `inspect.signature(run_sh)` if available

#### Manual Verification:
- [ ] Test basic call: `result = run_sh("echo hello", check=False); assert result.exit_code == 0`
- [ ] Test tuple unpacking: `out, err, code = run_sh("echo test", check=False)`

**Note**: Complete all automated verification, then pause for manual confirmation before proceeding to Phase 4.

---

## Phase 4: Verification and Testing

### Overview
Run comprehensive tests to verify the changes work correctly across all call sites in the codebase.

### Changes Required

#### 1. Import and syntax tests

**File**: None (verification commands)

**Commands**:
```bash
# Verify imports work
python -c "from tools.auto_prd.command import run_cmd, run_sh, CommandResult"

# Verify module loads without errors
python -c "import tools.auto_prd.command"

# Verify dataclass creates instances correctly
python -c "
from tools.auto_prd.command import CommandResult
result = CommandResult('out', 'err', 0)
assert result.stdout == 'out'
assert result.stderr == 'err'
assert result.exit_code == 0
assert result.is_success() == True
print('CommandResult works correctly')
"
```

#### 2. Backward compatibility tests

**File**: Create temporary test script `/tmp/test_command_result.py`

```python
#!/usr/bin/env python3
"""Test CommandResult backward compatibility."""
import sys
sys.path.insert(0, '/Users/simo/Projects/autodev')

from tools.auto_prd.command import run_cmd, CommandResult

# Test 1: Named attribute access (new pattern)
result = run_cmd(["echo", "hello"], check=False)
assert result.stdout.strip() == "hello", f"Expected 'hello', got {result.stdout}"
assert result.is_success(), "Command should succeed"
print("✓ Test 1: Named attribute access works")

# Test 2: Tuple unpacking (backward compatible)
stdout, stderr, exit_code = run_cmd(["echo", "test"], check=False)
assert stdout.strip() == "test", f"Expected 'test', got {stdout}"
assert exit_code == 0, f"Expected exit code 0, got {exit_code}"
print("✓ Test 2: Tuple unpacking works")

# Test 3: Failure case
result = run_cmd(["false"], check=False)
assert not result.is_success(), "Command should fail"
assert result.exit_code == 1, f"Expected exit code 1, got {result.exit_code}"
msg = result.get_error_message()
assert "exit code 1" in msg or "1" in msg, f"Expected exit code in message, got {msg}"
print("✓ Test 3: Failure handling works")

# Test 4: Error message from stderr
result = run_cmd(["sh", "-c", "echo error >&2; exit 1"], check=False)
assert not result.is_success(), "Command should fail"
error_msg = result.get_error_message()
assert "error" in error_msg, f"Expected 'error' in message, got {error_msg}"
print("✓ Test 4: Error message from stderr works")

# Test 5: run_sh returns CommandResult
from tools.auto_prd.command import run_sh
result = run_sh("echo hello from zsh", check=False)
assert result.is_success(), "run_sh should succeed"
assert "hello" in result.stdout, f"Expected 'hello' in output, got {result.stdout}"
print("✓ Test 5: run_sh returns CommandResult")

print("\n✅ All tests passed!")
```

**Run command**:
```bash
python /tmp/test_command_result.py
```

#### 3. Integration test with real call sites

**File**: None (verification commands)

**Commands**: Run a sample of actual code that uses run_cmd to ensure nothing breaks

```bash
# Test git operations (from git_ops.py)
python -c "
import sys
sys.path.insert(0, '/Users/simo/Projects/autodev')
from pathlib import Path
from tools.auto_prd.command import run_cmd

# Test from git_ops.py:99
out, _, _ = run_cmd(['git', 'status', '--porcelain'], cwd=Path.cwd())
print('✓ git status unpacking works')

# Test from rollback.py:207
out, err, exit_code = run_cmd(['git', 'rev-parse', '--git-dir'], check=False, cwd=Path.cwd())
if exit_code != 0:
    error_msg = err or out or 'Unknown error'
    print(f'Got error (expected): {error_msg}')
else:
    print('✓ git rev-parse works')
"
```

### Success Criteria

#### Automated Verification:
- [ ] All import tests pass
- [ ] CommandResult instantiation tests pass
- [ ] Backward compatibility tests pass (all 5 test cases)
- [ ] Integration tests with real git operations pass

#### Manual Verification:
- [ ] No exceptions raised during import or execution
- [ ] Output shows "✅ All tests passed!"
- [ ] All verification commands complete successfully

**Note**: Complete all automated verification, then confirm manually before considering the implementation complete.

---

## Phase 5: Optional Call Site Migration (Low Priority)

### Overview
Migrate high-value call sites to use named attributes instead of tuple unpacking. This is **optional** and can be done incrementally over time.

### Changes Required

#### Example: Migrating a typical call site

**File**: `tools/auto_prd/verification.py:482`

**Before**:
```python
out, err, exit_code = run_cmd(
    cmd,
    cwd=self.repo_root,
    check=False,
    timeout=self.timeout_seconds,
)
output = out + ("\n" + err if err else "")
return QualityGateResult(
    gate=gate_name,
    requirement=requirement,
    passed=(exit_code == 0),
    output=output[:1000],
)
```

**After**:
```python
result = run_cmd(
    cmd,
    cwd=self.repo_root,
    check=False,
    timeout=self.timeout_seconds,
)
output = result.stdout + ("\n" + result.stderr if result.stderr else "")
return QualityGateResult(
    gate=gate_name,
    requirement=requirement,
    passed=result.is_success(),
    output=output[:1000],
)
```

**Benefits**:
- More readable: `result.is_success()` vs `exit_code == 0`
- Self-documenting: `result.stdout` vs `out`
- Consistent: All result access uses the same object

#### Priority call sites for migration

If doing migration, prioritize these files (most frequently used):
1. `tools/auto_prd/verification.py` - Quality gate execution
2. `tools/auto_prd/rollback.py` - Git revert operations
3. `tools/auto_prd/git_ops.py` - Core git operations
4. `tools/auto_prd/agents.py` - Agent command execution

### Success Criteria

#### Automated Verification:
- [ ] Migrated code still works correctly
- [ ] Tests still pass
- [ ] No behavioral changes

#### Manual Verification:
- [ ] Code is more readable
- [ ] Helper methods (`is_success()`, `get_error_message()`) are used where appropriate

**Note**: This phase is **optional**. The implementation is complete after Phase 4.

---

## Testing Strategy

### Unit Tests
- [x] CommandResult instantiation
- [x] `is_success()` method (True for 0, False otherwise)
- [x] `get_error_message()` method (stderr → stdout → fallback)
- [x] `__iter__()` method (tuple unpacking)
- [x] Type annotations (dataclass fields)

### Integration Tests
- [x] run_cmd() returns CommandResult
- [x] run_sh() returns CommandResult
- [x] Backward compatibility with tuple unpacking
- [x] Named attribute access
- [x] Exception handling (check=True still raises CalledProcessError)

### Manual Testing Steps
1. [ ] Run import verification: `python -c "from tools.auto_prd.command import run_cmd, CommandResult"`
2. [ ] Run test script: `python /tmp/test_command_result.py`
3. [ ] Test real call sites: Run verification.py or rollback.py commands
4. [ ] Verify no regressions in existing functionality

## Migration Notes

### Backward Compatibility Strategy
The `__iter__()` method on `CommandResult` ensures existing code works unchanged:

```python
# Old code still works
out, err, exit_code = run_cmd(cmd, check=False)

# New code gets better API
result = run_cmd(cmd, check=False)
if result.is_success():
    print(result.stdout)
```

### Type Annotation Migration
- Old type: `tuple[str, str, int]`
- New type: `CommandResult`
- Both support unpacking, but new type is more descriptive

### Gradual Migration Path
1. **Phase 1-4**: Complete implementation with backward compatibility (REQUIRED)
2. **Phase 5**: Incrementally migrate high-value call sites (OPTIONAL)
3. **Future**: Eventually deprecate tuple unpacking with warnings (FUTURE ENHANCEMENT)

## References
- Research: `/Users/simo/Projects/autodev/.wreckit/items/013-standardize-error-handling-in-command-execution/research.md`
- Core implementation: `tools/auto_prd/command.py:360-549` (run_cmd function)
- Similar patterns: `tools/auto_prd/worker.py:43-50` (TaskResult), `tools/auto_prd/initializer.py:32-56` (InitResult, BaselineResult)
- Error utilities: `tools/auto_prd/utils.py:133-159` (extract_called_process_error_details)
- Call sites (partial): `tools/auto_prd/verification.py`, `tools/auto_prd/rollback.py`, `tools/auto_prd/git_ops.py`, `tools/auto_prd/agents.py`
