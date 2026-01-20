# Research: Fix resource leak in temporary file handling

**Date**: 2025-01-19
**Item**: 005-fix-resource-leak-in-temporary-file-handling

## Research Question
If an exception occurs between file creation and the os.unlink() call, temporary files are leaked.

**Motivation:** Prevents disk space leaks from abandoned temporary files during error conditions.

**Technical constraints:**
- Use context manager pattern with tempfile.NamedTemporaryFile
- Ensure cleanup happens in both success and error paths

**Signals:** priority: critical

## Summary

The research identified **one critical resource leak** in the main codebase at `tools/generate_tracker.py:135-144`. The `read_stdin_to_temp_file()` function creates a temporary file with `delete=False` but relies on manual cleanup in a `finally` block in the calling `main()` function. This creates a window for resource leaks if exceptions occur between file creation and the finally block execution.

The good news is that the cleanup code in `main()` (lines 222-228) already exists and appears correct. However, the implementation violates the context manager pattern specified in the technical constraints and is less robust than using `tempfile.NamedTemporaryFile` as a context manager.

The test files generally follow proper patterns with try/finally blocks and use of the `safe_cleanup` utility function from `tools/auto_prd/tests/__init__.py`. However, several test files also use `delete=False` without proper context manager patterns.

## Current State Analysis

### Existing Implementation

#### Primary Issue: tools/generate_tracker.py

**File**: `tools/generate_tracker.py:121-144`

The `read_stdin_to_temp_file()` function creates a temporary file without proper resource management:

```python
def read_stdin_to_temp_file() -> tuple[Path, str]:
    """Read PRD content from stdin and write to a temporary file.

    Returns:
        Tuple of (temp_file_path, content_hash)
    """
    content = sys.stdin.read()
    if not content.strip():
        raise ValueError("Empty input received from stdin")

    # Generate a hash for the source identifier
    content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

    # Create temp file that persists until explicitly deleted
    temp_file = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".md",
        prefix=f"stdin_{content_hash}_",
        delete=False,  # <-- VULNERABILITY: Manual cleanup required
    )
    temp_file.write(content)
    temp_file.close()

    return Path(temp_file.name), content_hash
```

**Cleanup code** exists in `main()` function at lines 222-228:

```python
finally:
    # Clean up temp file if created
    if temp_file is not None and temp_file.exists():
        try:
            temp_file.unlink()
        except OSError:
            pass
```

**Problems with this implementation:**
1. **Not using context manager**: Violates the technical constraint to use context manager pattern
2. **Relies on caller for cleanup**: The function returns a Path and expects the caller to clean up
3. **Exception window**: If an exception occurs after line 161 (`temp_file = prd_path`) but before the finally block, the file may not be cleaned up
4. **Less Pythonic**: Modern Python best practices prefer context managers for resource management

#### Good Example: tools/auto_prd/checkpoint.py

**File**: `tools/auto_prd/checkpoint.py:307-343`

This file demonstrates the CORRECT pattern for temporary file handling with `mkstemp`:

```python
# Set restrictive umask for temp file creation (0077 = owner only).
# This ensures the temp file is created with 0600 permissions by default.
old_umask = os.umask(0o077)
try:
    # Write to temp file then rename for atomicity.
    # fd is wrapped in try-finally immediately to prevent fd leak if an exception
    # occurs before os.fdopen takes ownership of the file descriptor.
    fd, temp_path = tempfile.mkstemp(
        suffix=".json.tmp",
        prefix=f"{session_id}-",
        dir=target_path.parent,
    )
    fd_closed = False
    try:
        # os.fdopen takes ownership; fd will be closed by context manager.
        # We only mark fd_closed = True AFTER os.fdopen succeeds to ensure
        # we close the fd manually if os.fdopen itself raises an exception.
        with os.fdopen(fd, "w") as f:
            fd_closed = True
            json.dump(checkpoint, f, indent=2, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.rename(temp_path, target_path)
        # Ensure final file has restrictive permissions (0600)
        os.chmod(target_path, 0o600)
        logger.debug("Saved checkpoint to %s", target_path)
    except Exception:
        # Close fd if os.fdopen was never called (prevents fd leak)
        if not fd_closed:
            try:
                os.close(fd)
            except OSError:
                # Ignore errors closing fd; it may already be closed or invalid during cleanup.
                pass
        # Clean up temp file on failure
        try:
            os.unlink(temp_path)
        except OSError:
            # Ignore errors deleting temp file; it may not exist or may have already been removed.
            pass
        raise
finally:
    # Restore original umask
    os.umask(old_umask)
```

This is an excellent example of careful resource management with:
- Proper file descriptor management
- Cleanup in both success and exception paths
- Detailed comments explaining the logic
- Atomic file operations

### Key Files

- **`tools/generate_tracker.py:121-144`** - **[NEEDS FIX]** Function that creates temp file without context manager
- **`tools/generate_tracker.py:222-228`** - Existing cleanup code in finally block (works but not ideal)
- **`tools/auto_prd/checkpoint.py:307-343`** - **[GOOD EXAMPLE]** Proper temp file handling with mkstemp
- **`tools/auto_prd/tests/__init__.py:7-32`** - **[REFERENCE]** `safe_cleanup` utility function
- **`validation_script.py:55-68`** - **[MINOR ISSUE]** Uses delete=False but has cleanup at line 68

### Test Files with delete=False Pattern

Multiple test files use `tempfile.NamedTemporaryFile` with `delete=False`, but they generally have proper cleanup with try/finally blocks:

1. **`tools/auto_prd/tests/test_integration_feed.py:68-74, 103-105, 264-267`** - Uses `safe_cleanup` utility
2. **`tools/auto_prd/tests/test_tracker_generator.py:30-33, 47-50, 52-55, 67-70, 72-75`** - Uses try/finally with manual cleanup
3. **`tools/auto_prd/tests/test_stdout_flushing.py:157-159`** - Uses `safe_cleanup` utility
4. **`tools/auto_prd/tests/fixtures/flush_test_script.py:95-120`** - Has try/finally with os.unlink

These test files are **lower priority** since:
- They already have cleanup mechanisms
- Tests run in controlled environments
- The `safe_cleanup` utility handles errors gracefully

## Technical Considerations

### Dependencies

- **Standard library only**: `tempfile`, `os`, `pathlib`
- **No external dependencies** required for the fix
- **Internal utilities**: `tools/auto_prd/tests/__init__.py` has `safe_cleanup` but it's test-only

### Patterns to Follow

1. **Context Manager Pattern** (required by constraints):
   ```python
   # GOOD - Context manager ensures cleanup
   with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=True) as f:
       f.write(content)
       temp_path = Path(f.name)
       # Use the file while inside context
   # File automatically deleted here
   ```

2. **When delete=False is necessary** (e.g., file needs to persist after context):
   ```python
   # ACCEPTABLE - If file must persist, use explicit cleanup
   temp_file = tempfile.NamedTemporaryFile(mode="w", delete=False)
   try:
       temp_file.write(content)
       temp_path = Path(temp_file.name)
       # Do work with the file
   finally:
       temp_file.close()
       if temp_path.exists():
           temp_path.unlink()
   ```

3. **Pattern from checkpoint.py** (for mkstemp):
   ```python
   fd, temp_path = tempfile.mkstemp(suffix=".tmp")
   try:
       with os.fdopen(fd, "w") as f:
           # Write to file
       # Use the file
   except Exception:
       try:
           os.close(fd)
       except OSError:
           pass
       try:
           os.unlink(temp_path)
       except OSError:
           pass
       raise
   ```

### Constraints Analysis

The technical constraint states: "Use context manager pattern with tempfile.NamedTemporaryFile"

**Challenge**: The current implementation uses `delete=False` because the file needs to persist after the `read_stdin_to_temp_file()` function returns. The file path is passed to `generate_tracker()` which needs to read it later.

**Solution Options**:

1. **Option A**: Refactor to use the file within the context manager
   - Move the `generate_tracker()` call inside the context manager
   - More significant refactoring but cleanest pattern

2. **Option B**: Keep delete=False but add context manager for file handle
   ```python
   def read_stdin_to_temp_file() -> tuple[Path, str]:
       content = sys.stdin.read()
       content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

       # Use context manager for the file handle
       with tempfile.NamedTemporaryFile(
           mode="w",
           suffix=".md",
           prefix=f"stdin_{content_hash}_",
           delete=False,  # File persists after close
       ) as temp_file:
           temp_file.write(content)
           # File is closed here by context manager
           temp_path = Path(temp_file.name)

       return temp_path, content_hash
   ```
   - Better than current (context manager ensures file is closed)
   - Still relies on caller for deletion (but that's explicit in design)

3. **Option C**: Use context manager in main() directly
   - Inline the temp file creation in main() within a context manager
   - Pass the file path to generate_tracker() within the context

**Recommended**: Option B is the best balance of meeting constraints while minimizing refactoring. It uses a context manager for the file handle (ensuring proper closure) while still allowing the file to persist for later use.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Breaking change to function signature** | High | Keep the same return type; only change internal implementation |
| **File deleted before use** | High | Keep `delete=False` but ensure proper cleanup in caller's finally block |
| **Exceptions during write** | Medium | Context manager ensures file handle is closed even on exception |
| **Temp file not cleaned up on error** | High | Verify the finally block in main() is preserved and tested |
| **Test failures** | Low | Tests should continue to work; the cleanup pattern remains the same |

## Recommended Approach

### High-Level Strategy

1. **Primary Fix**: Refactor `read_stdin_to_temp_file()` in `tools/generate_tracker.py`
   - Add context manager for file handle (Option B above)
   - Keep `delete=False` since file must persist
   - Ensure file is properly closed before returning path

2. **Verify Cleanup**: Ensure the finally block in `main()` remains intact
   - The existing cleanup at lines 222-228 is correct
   - Test that it works with the refactored code

3. **Add Documentation**: Add comments explaining:
   - Why delete=False is necessary (file must persist for later reading)
   - How the context manager ensures file handle cleanup
   - Responsibility of caller to delete the file

4. **Testing**: Verify the fix works correctly
   - Test normal operation (file created, used, deleted)
   - Test error paths (exceptions during write, during processing)
   - Verify no temp files left behind

### Implementation Steps

1. Modify `read_stdin_to_temp_file()` to use context manager
2. Add unit tests for the function (if not already present)
3. Add integration test for error handling
4. Update documentation/comments
5. Verify existing tests still pass

### Code Change Preview

**Before** (lines 135-144):
```python
    temp_file = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".md",
        prefix=f"stdin_{content_hash}_",
        delete=False,
    )
    temp_file.write(content)
    temp_file.close()

    return Path(temp_file.name), content_hash
```

**After**:
```python
    # Use context manager to ensure file handle is properly closed
    # delete=False is needed because the file must persist after this
    # function returns for use by generate_tracker()
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".md",
        prefix=f"stdin_{content_hash}_",
        delete=False,
    ) as temp_file:
        temp_file.write(content)
        # File is automatically closed when context exits
        temp_path = Path(temp_file.name)

    return temp_path, content_hash
```

## Open Questions

1. **Scope of fixes**: Should we also update the test files that use `delete=False`?
   - **Recommendation**: No, treat those as lower priority. They have proper cleanup mechanisms and are less critical than production code.

2. **Should we extract temp file management to a utility function?**
   - **Recommendation**: Not necessary for this fix. The pattern is simple enough. However, consider creating a utility if more temp file handling is added in the future.

3. **Should we use `delete=True` and copy the file instead?**
   - **Recommendation**: No, that would add unnecessary I/O overhead. The `delete=False` pattern is acceptable when documented and properly cleaned up.

4. **Are there any other files with similar issues?**
   - **Answer**: Based on the research, `tools/generate_tracker.py` is the only production file (non-test) with this issue. Other uses of temp files in production code (`checkpoint.py`, `command.py`) are implemented correctly.

## Additional Findings

### Files That Are Correctly Implemented

- **`tools/auto_prd/checkpoint.py`**: Excellent resource management with detailed comments (lines 307-343)
- **`tools/auto_prd/command.py`**: Only uses `tempfile.gettempdir()` to get temp directory path, not creating temp files

### Test Infrastructure

The project has a good testing infrastructure:
- **`tools/auto_prd/tests/__init__.py`**: Provides `safe_cleanup()` utility for graceful cleanup
- Tests use try/finally consistently
- Test files are generally well-structured

### Priority Assessment

**Critical**: `tools/generate_tracker.py` - Production code with resource leak
**Low**: Test files - Have cleanup mechanisms, run in controlled environments

## Conclusion

The research identified **one critical issue** in `tools/generate_tracker.py` where temporary file handling violates the context manager pattern specified in the technical constraints. The fix is straightforward: wrap the `NamedTemporaryFile` usage in a context manager while keeping `delete=False` for file persistence. The existing cleanup code in `main()` is correct and should be preserved.

The codebase generally demonstrates good practices with proper resource management in `checkpoint.py` and comprehensive cleanup utilities in the test infrastructure.
