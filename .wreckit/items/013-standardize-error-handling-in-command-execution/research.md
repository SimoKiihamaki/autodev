# Research: Standardize error handling in command execution

**Date**: 2025-01-19
**Item**: 013-standardize-error-handling-in-command-execution

## Research Question

Inconsistent error return types make error handling difficult and error-prone.

**Motivation:** Provides consistent, structured error information for better error handling and debugging.

**Technical constraints:**
- Create CommandErrorDetails dataclass with exit_code, stderr, stdout fields
- Update function to return structured object

**Signals:** priority: high

## Summary

The current command execution infrastructure in `tools/auto_prd/command.py` returns a raw tuple `(stdout: str, stderr: str, returncode: int)` from the main `run_cmd()` function. This creates several issues:

1. **Inconsistent access patterns**: Callers must remember tuple positions (stdout, stderr, returncode) leading to errors like `out, err, exit_code = run_cmd(...)` where variable ordering matters and can be confused.

2. **No structured error information**: When commands fail with `check=False`, callers manually inspect exit codes and construct error messages. The `extract_called_process_error_details()` utility in `utils.py` exists to extract details from `CalledProcessError` exceptions, but this only works when exceptions are raised, not when `check=False` is used.

3. **Scattered error handling**: Error message construction is duplicated across the codebase (e.g., in `rollback.py:209`, `verification.py:488`, `git_ops.py:204-240`), with each location manually combining stderr/stdout/exit code.

The proposed solution is to create a `CommandErrorDetails` dataclass that encapsulates exit_code, stderr, and stdout fields, and update `run_cmd()` to return this structured object instead of a tuple. This would:
- Provide self-documenting access to result fields
- Enable methods on the result object for common operations (e.g., `.is_success()`, `.get_error_message()`)
- Maintain backward compatibility through tuple unpacking if needed
- Align with existing dataclass patterns used throughout the codebase (e.g., `TaskResult`, `InitResult`, `BaselineResult`, `StructuredError`)

## Current State Analysis

### Existing Implementation

**Primary command execution function**: `tools/auto_prd/command.py:360-549`
- `run_cmd()` returns `tuple[str, str, int]` representing `(stdout, stderr, returncode)`
- Supports retry logic with exponential backoff for transient failures
- Raises `subprocess.CalledProcessError` when `check=True` and command fails
- When `check=False`, returns tuple with non-zero exit code

**Current return value usage patterns** across the codebase:

1. **Direct tuple unpacking** (most common):
   ```python
   out, err, exit_code = run_cmd(cmd, cwd=repo_root, check=False)
   if exit_code != 0:
       error_msg = err or out or "Unknown error"
   ```
   Examples: `verification.py:482`, `rollback.py:207`, `initializer.py:324`

2. **Ignoring some values**:
   ```python
   out, _, _ = run_cmd(["git", "status", "--porcelain"])
   _, _, exit_code = run_cmd(["git", "diff", "--cached", "--quiet"], check=False)
   ```
   Examples: `git_ops.py:99`, `git_ops.py:261`

3. **Exception-based error handling** (when `check=True`):
   ```python
   try:
       run_cmd(["git", "push", ...])
   except subprocess.CalledProcessError as exc:
       details = extract_called_process_error_details(exc)
   ```
   Examples: `pr_flow.py:110-111`, `app.py:318-350`

### Key Files

**Core command execution**:
- `tools/auto_prd/command.py:360-549` - Main `run_cmd()` function returning tuple[str, str, int]
- `tools/auto_prd/command.py:552-596` - `safe_popen()` wrapper for subprocess.Popen
- `tools/auto_prd/command.py:598-615` - `run_sh()` shell script execution helper
- `tools/auto_prd/command.py:618-769` - `popen_streaming()` for streaming output

**Error handling utilities**:
- `tools/auto_prd/utils.py:92-98` - `extract_http_status()` - extracts HTTP status from CalledProcessError
- `tools/auto_prd/utils.py:109-130` - `_extract_stdout_stderr()` - extracts stdout/stderr from CalledProcessError
- `tools/auto_prd/utils.py:133-159` - `extract_called_process_error_details()` - extracts error details from CalledProcessError (stderr only, for security)

**Error classification infrastructure**:
- `tools/auto_prd/errors.py:21-43` - `ErrorCategory` and `ErrorSeverity` enums
- `tools/auto_prd/errors.py:46-84` - `StructuredError` dataclass with message, category, severity, context, recovery hints
- `tools/auto_prd/errors.py:86-166` - Error patterns and recovery hints dictionaries
- `tools/auto_prd/errors.py:168-239` - `classify_error()` function for automatic error categorization

**Existing dataclass patterns** (to follow for consistency):
- `tools/auto_prd/worker.py:43-50` - `TaskResult` dataclass with task_id, success, output, errors
- `tools/auto_prd/initializer.py:32-46` - `InitResult` dataclass with tracker, baseline_passed, next_feature, errors
- `tools/auto_prd/initializer.py:49-56` - `BaselineResult` dataclass with success, output, exit_code, errors
- `tools/auto_prd/verification.py` (referenced) - `QualityGateResult` and `TestResult` dataclasses

**Files that would be affected by the change** (partial list from grep):
- `tools/auto_prd/verification.py:482,532,945,1014` - Quality gate execution
- `tools/auto_prd/rollback.py:207,232` - Git revert operations
- `tools/auto_prd/initializer.py:324` - Baseline test execution
- `tools/auto_prd/git_ops.py:37,43,99,220,261` - Git operations
- `tools/auto_prd/agents.py:662,760,1041` - Agent command execution
- `tools/auto_prd/pr_flow.py:115,146` - PR workflow commands
- `tools/auto_prd/app.py:283,290,293,308,316` - Application git operations
- Test files: `tests/test_stdout_flushing.py`, `tests/test_cli_safety.py`, `tests/fixtures/flush_test_script.py`

## Technical Considerations

### Dependencies

**External dependencies**:
- None (dataclass is built-in Python 3.7+)

**Internal modules to integrate with**:
- `tools/auto_prd/command.py` - Primary location for CommandErrorDetails and run_cmd modification
- `tools/auto_prd/utils.py` - `extract_called_process_error_details()` may need updating or can be deprecated
- `tools/auto_prd/errors.py` - Optionally integrate with StructuredError for advanced error classification

### Patterns to Follow

**Dataclass conventions** (from existing codebase):
1. Use `from dataclasses import dataclass, field` for imports
2. Use `field(default_factory=list)` for mutable defaults
3. Include type hints on all fields
4. Add properties for computed values (e.g., `success` property in `InitResult`)
5. Keep dataclasses immutable where possible (no `@dataclass(frozen=False)` explicitly, but default is mutable)

**Naming conventions**:
- Use descriptive names: `exit_code` (not `returncode`), `stdout`, `stderr`
- For result objects, consider naming like `CommandResult` (following `TaskResult`, `InitResult`, `BaselineResult` pattern)
- The spec suggests `CommandErrorDetails` but this might be misleading since it contains both success and failure cases

**Type hints**:
- Use `from __future__ import annotations` at top of file (already present in command.py:3)
- Use `str` for stdout/stderr (already decoded, as seen in command.py:485-486)
- Use `int` for exit_code/returncode

**Backward compatibility**:
- Python's dataclasses are not tuples by default, but can be made to work with tuple unpacking
- Consider using `__iter__()` method to enable `stdout, stderr, exit_code = result` unpacking
- Alternative: Provide transition period with both tuple and dataclass support

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Breaking existing code** - Many call sites use tuple unpacking | High | Implement `__iter__()` on dataclass to enable backward-compatible unpacking; or provide migration period with deprecation warnings |
| **Type annotation mismatch** - Function signature changes from `-> tuple[str, str, int]` to `-> CommandResult` | Medium | Update all call sites systematically; use type checker (mypy/pyright) to find issues |
| **Performance overhead** - Dataclass creation vs tuple return | Low | Dataclass overhead is negligible; can benchmark if needed |
| **Naming confusion** - Spec says "CommandErrorDetails" but it's used for both success and failure | Low | Use more accurate name like `CommandResult` or `CommandExecutionResult`; clarify in documentation |
| **Test updates** - Test assertions need updating for new return type | Medium | Systematically update test files; leverage test helpers to reduce duplication |
| **Compatibility with CalledProcessError** - Need to maintain exception flow | Low | Keep CalledProcessError unchanged; only change return value when check=False |

## Recommended Approach

Based on research findings, here's the recommended implementation strategy:

### Phase 1: Create the dataclass
1. Add `CommandResult` dataclass to `tools/auto_prd/command.py` with:
   - `stdout: str`
   - `stderr: str`
   - `exit_code: int`
   - Helper methods: `is_success() -> bool`, `get_error_message() -> str`
   - `__iter__()` method for backward-compatible tuple unpacking

### Phase 2: Update run_cmd function
1. Change `run_cmd()` return type from `tuple[str, str, int]` to `CommandResult`
2. Update all return statements to return `CommandResult(stdout_text, stderr_text, proc.returncode)`
3. Keep exception raising logic unchanged (check=True still raises CalledProcessError)

### Phase 3: Maintain backward compatibility
1. Implement `__iter__()` on CommandResult to allow unpacking:
   ```python
   def __iter__(self):
       return iter((self.stdout, self.stderr, self.exit_code))
   ```
2. This allows existing code `out, err, code = run_cmd(...)` to work unchanged
3. Gradually migrate call sites to use named attributes: `result.stdout`, `result.stderr`, `result.exit_code`

### Phase 4: Update error handling utilities
1. Update `extract_called_process_error_details()` or create new helper on CommandResult
2. Consider deprecating `extract_called_process_error_details()` in favor of `result.get_error_message()`
3. Optionally integrate with `StructuredError` from errors.py for advanced categorization

### Phase 5: Migration path
1. Update call sites incrementally to use named attributes
2. Keep tuple unpacking working via `__iter__()`
3. Add deprecation warning for tuple unpacking if desired (future enhancement)
4. Update tests to use both patterns initially, then migrate to named attributes

### Implementation details

**CommandResult dataclass structure** (following existing patterns):
```python
@dataclass
class CommandResult:
    """Result of command execution with structured access to output and exit status."""

    stdout: str
    stderr: str
    exit_code: int

    def is_success(self) -> bool:
        """Check if command succeeded (exit code 0)."""
        return self.exit_code == 0

    def get_error_message(self) -> str:
        """Get error message from stderr, with fallback to stdout and exit code."""
        if self.stderr.strip():
            return self.stderr.strip()
        if self.stdout.strip():
            return self.stdout.strip()
        return f"exit code {self.exit_code}"

    def __iter__(self):
        """Enable backward-compatible tuple unpacking: stdout, stderr, exit_code = result."""
        return iter((self.stdout, self.stderr, self.exit_code))
```

**Alternative naming**: If following the spec exactly, name it `CommandErrorDetails`, but note this is misleading since it's used for both success and failure cases. `CommandResult` is more accurate and follows existing naming patterns (`TaskResult`, `InitResult`, `BaselineResult`).

## Open Questions

1. **Naming**: Should the dataclass be named `CommandResult` (following existing patterns) or `CommandErrorDetails` (as specified in the item)? The latter is misleading since it contains success information too.

2. **Backward compatibility strategy**: Should we:
   - Implement `__iter__()` for seamless backward compatibility?
   - Or provide a migration period with deprecation warnings?
   - Or do a hard break and update all call sites at once?

3. **Helper methods**: What helper methods should be included?
   - `is_success()` - Check exit code == 0
   - `get_error_message()` - Construct error message (like `extract_called_process_error_details`)
   - `raise_for_status()` - Raise CalledProcessError if non-zero exit
   - Others?

4. **Integration with errors.py**: Should `CommandResult` integrate with `StructuredError` from errors.py for advanced error classification, or keep it simple?

5. **Type checking**: Should we run mypy/pyright to identify all type mismatches before implementing?

6. **Test strategy**: Should we add tests specifically for the dataclass behavior (e.g., `__iter__()`, helper methods), or rely on existing tests?
