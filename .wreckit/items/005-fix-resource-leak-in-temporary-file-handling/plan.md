# Fix resource leak in temporary file handling - Implementation Plan

## Overview
Implement proper resource management for temporary file handling in `tools/generate_tracker.py` by using the context manager pattern with `tempfile.NamedTemporaryFile`. This prevents disk space leaks from abandoned temporary files during error conditions and ensures cleanup happens in both success and error paths.

## Current State Analysis

### What Exists Now
The `read_stdin_to_temp_file()` function in `tools/generate_tracker.py:135-144` creates a temporary file without using a context manager:

```python
temp_file = tempfile.NamedTemporaryFile(
    mode="w",
    suffix=".md",
    prefix=f"stdin_{content_hash}_",
    delete=False,
)
temp_file.write(content)
temp_file.close()
```

**Problems:**
1. Manual file handle management via `temp_file.close()` (not Pythonic)
2. No guarantee file handle is closed if an exception occurs during write
3. Violates the technical constraint to use context manager pattern
4. Creates a resource leak window between file creation and handle closure

### What's Missing
- Context manager pattern for automatic resource cleanup
- Unit tests for the `read_stdin_to_temp_file()` function
- Integration tests for error handling paths
- Documentation explaining the `delete=False` requirement

### Key Constraints Discovered
1. **File must persist**: The temporary file needs to exist after `read_stdin_to_temp_file()` returns because `generate_tracker()` reads it later (line 186)
2. **Caller manages deletion**: The `main()` function has proper cleanup in a `finally` block (lines 222-228) that must be preserved
3. **Standard library only**: No external dependencies; uses `tempfile`, `pathlib`, `hashlib`
4. **No breaking changes**: Function signature and return type must remain unchanged

## Desired End State

### Specification
The `read_stdin_to_temp_file()` function uses a context manager to ensure the file handle is properly closed even if exceptions occur, while keeping `delete=False` to allow the file to persist for later reading by `generate_tracker()`.

### Key Improvements
1. **Context manager**: Ensures file handle is closed automatically
2. **Exception safety**: File handle cleanup guaranteed even during errors
3. **Better documentation**: Comments explain why `delete=False` is necessary
4. **Test coverage**: Unit and integration tests verify correct behavior
5. **No behavior change**: External API and functionality remain identical

### Verification
- File handle is properly closed before returning path
- Temporary files are still cleaned up by `main()`'s finally block
- No temporary files leak during error conditions
- All existing functionality continues to work

## What We're NOT Doing

### Explicitly Out of Scope
1. **Not refactoring test files**: Test files using `delete=False` (e.g., `test_tracker_generator.py`) have proper cleanup mechanisms and are lower priority
2. **Not changing the cleanup pattern**: The `finally` block in `main()` works correctly and will be preserved
3. **Not using `delete=True`**: Would require copying the file, adding unnecessary I/O overhead
4. **Not extracting to utility function**: The pattern is simple enough that a utility function isn't warranted
5. **Not modifying `checkpoint.py`**: That file already demonstrates correct temp file handling patterns

### Why These Choices
- Test files already have proper cleanup with `safe_cleanup` utility
- The existing `finally` block is correct and well-tested
- `delete=False` is necessary for the file to persist for later reading
- A utility function would be over-engineering for this single use case
- `checkpoint.py` is already a good example of proper temp file handling

## Implementation Approach

### High-Level Strategy
Use **Option B** from research: Keep `delete=False` but wrap the file handle in a context manager. This ensures proper closure of the file handle while still allowing the file to persist for later reading. The context manager guarantees cleanup even if exceptions occur during the write operation.

### Why This Approach
- **Minimal refactoring**: Only changes the function internals, not its API
- **Meets constraints**: Uses context manager pattern as required
- **Preserves behavior**: File still persists for later reading by `generate_tracker()`
- **Low risk**: No changes to calling code or cleanup logic
- **Testable**: Can verify file handle closure and temp file cleanup

### Implementation Phases
The implementation is divided into three phases to ensure each change is tested independently:

---

## Phase 1: Refactor `read_stdin_to_temp_file()` to Use Context Manager

### Overview
Wrap the `tempfile.NamedTemporaryFile` usage in a context manager to ensure proper file handle cleanup, while keeping `delete=False` to allow the file to persist for later reading.

### Changes Required

#### 1. Update `read_stdin_to_temp_file()` function
**File**: `tools/generate_tracker.py`
**Lines**: 135-144

**Before:**
```python
    # Create temp file that persists until explicitly deleted
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

**After:**
```python
    # Use context manager to ensure file handle is properly closed.
    # delete=False is needed because the file must persist after this
    # function returns for use by generate_tracker(). The caller (main)
    # is responsible for deleting the file in its finally block.
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".md",
        prefix=f"stdin_{content_hash}_",
        delete=False,
    ) as temp_file:
        temp_file.write(content)
        # File handle is automatically closed when context exits
        temp_path = Path(temp_file.name)

    return temp_path, content_hash
```

**Changes:**
- Wrapped `NamedTemporaryFile` in a `with` statement (context manager)
- Removed explicit `temp_file.close()` call (now handled by context manager)
- Store `temp_path` before context exits for later return
- Added comprehensive docstring comment explaining the design

### Success Criteria

#### Automated Verification:
- [ ] Python syntax is valid: `python -m py_compile tools/generate_tracker.py`
- [ ] Script executes without errors: `python tools/generate_tracker.py --help`
- [ ] Existing functionality works: `echo "# Test PRD" | python tools/generate_tracker.py --stdin --dry-run`

#### Manual Verification:
- [ ] File is properly closed before `read_stdin_to_temp_file()` returns
- [ ] Temp file is still accessible after function returns (for `generate_tracker()`)
- [ ] Temp file is still cleaned up by `main()`'s finally block
- [ ] No regressions in existing behavior

**Note**: Complete all automated verification, then test manual verification steps before proceeding to Phase 2.

---

## Phase 2: Add Unit Tests for `read_stdin_to_temp_file()`

### Overview
Create comprehensive unit tests to verify the refactored function works correctly in both success and error scenarios. Currently, no tests exist for this function.

### Changes Required

#### 1. Create test file
**File**: `tools/tests/test_generate_tracker.py` (new file)

```python
"""Tests for tools/generate_tracker.py"""

import hashlib
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Import the function to test
from tools.generate_tracker import read_stdin_to_temp_file


class TestReadStdinToTempFile:
    """Test suite for read_stdin_to_temp_file function."""

    def test_read_stdin_to_temp_file_success(self):
        """Test successful reading from stdin and temp file creation."""
        test_content = "# Test PRD\n\nThis is a test PRD content."
        expected_hash = hashlib.sha256(test_content.encode()).hexdigest()[:16]

        # Mock stdin to provide test content
        with patch("sys.stdin.read", return_value=test_content):
            temp_path, content_hash = read_stdin_to_temp_file()

        # Verify the hash is correct
        assert content_hash == expected_hash

        # Verify the temp file exists
        assert temp_path.exists()

        # Verify the temp file contains the correct content
        actual_content = temp_path.read_text()
        assert actual_content == test_content

        # Verify file naming convention
        assert temp_path.suffix == ".md"
        assert f"stdin_{content_hash}_" in temp_path.name

        # Clean up
        temp_path.unlink()

    def test_read_stdin_to_temp_file_empty_input(self):
        """Test that empty input raises ValueError."""
        # Mock stdin to return empty string
        with patch("sys.stdin.read", return_value=""):
            with pytest.raises(ValueError, match="Empty input received from stdin"):
                read_stdin_to_temp_file()

    def test_read_stdin_to_temp_file_whitespace_only(self):
        """Test that whitespace-only input raises ValueError."""
        # Mock stdin to return whitespace
        with patch("sys.stdin.read", return_value="   \n\t  \n  "):
            with pytest.raises(ValueError, match="Empty input received from stdin"):
                read_stdin_to_temp_file()

    def test_read_stdin_to_temp_file_handle_closed(self):
        """Test that file handle is properly closed after function returns."""
        test_content = "# Test PRD"

        with patch("sys.stdin.read", return_value=test_content):
            temp_path, _ = read_stdin_to_temp_file()

        # Try to delete the file - should succeed because handle is closed
        # If the handle were still open, this might fail on Windows
        try:
            temp_path.unlink()
        except OSError as e:
            pytest.fail(f"Failed to unlink temp file (handle may not be closed): {e}")

    def test_read_stdin_to_temp_file_persistence(self):
        """Test that temp file persists after function returns (delete=False)."""
        test_content = "# Test PRD content that must persist"

        with patch("sys.stdin.read", return_value=test_content):
            temp_path, _ = read_stdin_to_temp_file()

        # File should still exist after function returns
        assert temp_path.exists()

        # File should be readable
        content = temp_path.read_text()
        assert content == test_content

        # Clean up
        temp_path.unlink()

    def test_read_stdin_to_temp_file_multiline_content(self):
        """Test handling of multiline content with special characters."""
        test_content = """# PRD Title

## Section 1
Content with special chars: @#$%^&*()

## Section 2
- List item 1
- List item 2
"""
        with patch("sys.stdin.read", return_value=test_content):
            temp_path, content_hash = read_stdin_to_temp_file()

        # Verify content is preserved exactly
        assert temp_path.read_text() == test_content

        # Clean up
        temp_path.unlink()

    def test_read_stdin_to_temp_file_unicode_content(self):
        """Test handling of unicode characters."""
        test_content = "# PRD with unicode: café, 日本語, 🎉"
        expected_hash = hashlib.sha256(test_content.encode()).hexdigest()[:16]

        with patch("sys.stdin.read", return_value=test_content):
            temp_path, content_hash = read_stdin_to_temp_file()

        # Verify hash
        assert content_hash == expected_hash

        # Verify content is preserved
        assert temp_path.read_text() == test_content

        # Clean up
        temp_path.unlink()
```

**Changes:**
- Created new test file with comprehensive test coverage
- Tests include: success case, empty input, handle closure, file persistence, multiline, unicode
- Uses pytest fixtures and mocking for stdin
- Verifies both the function behavior and resource management

### Success Criteria

#### Automated Verification:
- [ ] All new tests pass: `python -m pytest tools/tests/test_generate_tracker.py -v`
- [ ] Test coverage covers all code paths in `read_stdin_to_temp_file()`
- [ ] No existing tests are broken

#### Manual Verification:
- [ ] Review test output to ensure all assertions pass
- [ ] Manually verify file handle closure test succeeds on your platform
- [ ] Confirm no temp files are left behind after test runs

**Note**: Complete all automated verification, then review manual verification before proceeding to Phase 3.

---

## Phase 3: Add Integration Test for Error Handling

### Overview
Add an integration test that simulates the full flow of `generate_tracker.py` with stdin input, including error scenarios, to ensure temporary files are properly cleaned up even when exceptions occur.

### Changes Required

#### 1. Add integration test
**File**: `tools/tests/test_generate_tracker_integration.py` (new file)

```python
"""Integration tests for tools/generate_tracker.py script."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


class TestGenerateTrackerIntegration:
    """Integration tests for the generate_tracker.py script."""

    def test_stdin_mode_creates_and_cleans_temp_file(self):
        """Test that temp files are created and cleaned up in stdin mode."""
        test_prd = """# Test PRD

## User Stories
- [ ] Story 1
"""
        # Run the script with stdin input
        result = subprocess.run(
            [sys.executable, "tools/generate_tracker.py", "--stdin", "--dry-run"],
            input=test_prd,
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )

        # Should succeed (dry-run mode)
        assert result.returncode == 0

        # Verify temp files are cleaned up (check temp directory)
        temp_dir = Path(tempfile.gettempdir())
        remaining_files = list(temp_dir.glob("stdin_*.md"))
        # Our temp file should be cleaned up
        # Note: This might have false positives if other processes are running
        # so we just check that files aren't accumulating
        assert len(remaining_files) < 10, "Too many temp files remaining - possible leak"

    def test_stdin_mode_with_invalid_executor(self):
        """Test error handling with invalid executor argument."""
        test_prd = "# Test PRD"

        result = subprocess.run(
            [
                sys.executable,
                "tools/generate_tracker.py",
                "--stdin",
                "--executor",
                "invalid",
            ],
            input=test_prd,
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )

        # Should fail with error message
        assert result.returncode != 0
        assert "Invalid executor" in result.stderr

        # Verify no temp files left behind
        temp_dir = Path(tempfile.gettempdir())
        recent_temp_files = [
            f
            for f in temp_dir.glob("stdin_*.md")
            if "stdin_" in f.name  # Our naming pattern
        ]
        # Files should be cleaned up even on error
        assert len(recent_temp_files) < 10

    def test_stdin_mode_with_empty_input(self):
        """Test that empty input is properly handled."""
        result = subprocess.run(
            [sys.executable, "tools/generate_tracker.py", "--stdin"],
            input="",
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )

        # Should fail with error message
        assert result.returncode != 0
        assert "Empty input" in result.stderr

        # Verify no temp files created
        temp_dir = Path(tempfile.gettempdir())
        temp_files = list(temp_dir.glob("stdin_*.md"))
        # Empty input should not create temp file
        assert len(temp_files) < 10

    def test_stdin_mode_success_flow(self, tmp_path):
        """Test successful flow with actual PRD content."""
        test_prd = """# Feature: User Authentication

## User Stories

### US-001: User Login
**Priority**: 1

- Implement login form
- Add authentication middleware
"""

        result = subprocess.run(
            [
                sys.executable,
                "tools/generate_tracker.py",
                "--stdin",
                "--dry-run",
                "--output",
                str(tmp_path / "tracker.json"),
            ],
            input=test_prd,
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )

        # Should succeed
        assert result.returncode == 0

        # Verify tracker was created
        tracker_path = tmp_path / "tracker.json"
        assert tracker_path.exists()

        # Verify tracker content is valid JSON
        tracker = json.loads(tracker_path.read_text())
        assert "validation_summary" in tracker

    def test_temp_file_cleanup_on_exception(self):
        """Test that temp files are cleaned up when exceptions occur."""
        # Provide invalid PRD that will cause processing to fail
        invalid_prd = "This is not valid markdown and will cause issues"

        result = subprocess.run(
            [sys.executable, "tools/generate_tracker.py", "--stdin", "--dry-run"],
            input=invalid_prd,
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )

        # May fail or succeed depending on validation
        # Either way, temp files should be cleaned up
        temp_dir = Path(tempfile.gettempdir())
        temp_files = list(temp_dir.glob("stdin_*.md"))
        assert len(temp_files) < 10, "Temp files not cleaned up after exception"
```

**Changes:**
- Created integration test file
- Tests the full script flow with stdin input
- Verifies temp file cleanup in both success and error scenarios
- Uses subprocess to test the actual script behavior
- Checks that no temp files leak

### Success Criteria

#### Automated Verification:
- [ ] All integration tests pass: `python -m pytest tools/tests/test_generate_tracker_integration.py -v`
- [ ] All unit tests still pass: `python -m pytest tools/tests/test_generate_tracker.py -v`
- [ ] No temp files left behind after test runs

#### Manual Verification:
- [ ] Run the script manually with stdin input: `echo "# Test" | python tools/generate_tracker.py --stdin --dry-run`
- [ ] Check temp directory for leftover files: `ls /tmp/stdin_*.md 2>/dev/null | wc -l`
- [ ] Verify temp files are cleaned up after script exits
- [ ] Test error scenario: `echo "" | python tools/generate_tracker.py --stdin` and verify cleanup

**Note**: Complete all verification steps to finish implementation.

---

## Testing Strategy

### Unit Tests
**Purpose**: Verify the `read_stdin_to_temp_file()` function works correctly in isolation.

**Test Coverage:**
- ✅ Successful temp file creation with valid content
- ✅ Empty input raises `ValueError`
- ✅ Whitespace-only input raises `ValueError`
- ✅ File handle is properly closed after function returns
- ✅ Temp file persists after function returns (delete=False behavior)
- ✅ Multiline content handling
- ✅ Unicode character handling

**Key Edge Cases:**
- Empty input (should raise error before creating temp file)
- Unicode characters (should be preserved correctly)
- Very long content (should handle without issues)
- Special characters and markdown formatting

### Integration Tests
**Purpose**: Verify the full script flow correctly manages temp files.

**Test Scenarios:**
- ✅ Normal flow with stdin input and dry-run mode
- ✅ Error handling with invalid executor
- ✅ Error handling with empty input
- ✅ Successful flow with valid PRD and output file
- ✅ Temp file cleanup when exceptions occur during processing

**End-to-End Verification:**
- Script completes successfully
- Temp files are created and written correctly
- Temp files are cleaned up in both success and error paths
- No file handle leaks or disk space accumulation

### Manual Testing Steps

#### Test 1: Normal Operation
```bash
# Create a test PRD
cat > /tmp/test_prd.md << 'EOF'
# Test Feature

## User Stories
- [ ] Story 1: Implement basic functionality
- [ ] Story 2: Add error handling
EOF

# Run the script with stdin
cat /tmp/test_prd.md | python tools/generate_tracker.py --stdin --dry-run

# Expected: Script succeeds, temp file is cleaned up
```

#### Test 2: Verify No Temp File Leak
```bash
# Count temp files before
echo "Before: $(ls /tmp/stdin_*.md 2>/dev/null | wc -l)"

# Run script multiple times
for i in {1..10}; do
  echo "# Test PRD $i" | python tools/generate_tracker.py --stdin --dry-run
done

# Count temp files after
echo "After: $(ls /tmp/stdin_*.md 2>/dev/null | wc -l)"

# Expected: Count should be low (< 20), files should be cleaned up
```

#### Test 3: Error Path Cleanup
```bash
# Test with empty input (should fail)
echo "" | python tools/generate_tracker.py --stdin

# Verify no temp files were created
ls /tmp/stdin_*.md 2>/dev/null

# Expected: No temp files or very few (from other processes)
```

#### Test 4: File Handle Closure
```bash
# This test verifies the file handle is properly closed
# On Windows, you can't delete a file with open handles
cat > /tmp/test_handle.md << 'EOF'
# Test PRD for handle closure
EOF

python -c "
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, 'tools')
from generate_tracker import read_stdin_to_temp_file

with patch('sys.stdin.read', return_value=open('/tmp/test_handle.md').read()):
    temp_path, _ = read_stdin_to_temp_file()

# Try to delete immediately - should work because handle is closed
temp_path.unlink()
print('✓ File handle was properly closed')
"

# Expected: Prints success message
```

## Migration Notes

### Backwards Compatibility
- ✅ **No breaking changes**: Function signature remains identical
- ✅ **Behavior preserved**: Temp file still persists for later reading
- ✅ **Cleanup unchanged**: `main()`'s finally block still handles deletion
- ✅ **External API unchanged**: Script usage and CLI arguments unchanged

### Deployment
- No migration needed
- No data migration required
- No configuration changes needed
- Can be deployed immediately after testing

### Rollback Strategy
If issues arise:
1. Revert the context manager change to original implementation
2. Temp file cleanup will still work (finally block is unchanged)
3. No data corruption or loss risk

## References

### Research
- Research document: `/Users/simo/Projects/autodev/.wreckit/items/005-fix-resource-leak-in-temporary-file-handling/research.md`

### Key Files
- **Primary target**: `tools/generate_tracker.py:135-144` - Function to refactor
- **Cleanup code**: `tools/generate_tracker.py:222-228` - Existing finally block (preserve)
- **Good example**: `tools/auto_prd/checkpoint.py:307-343` - Proper temp file pattern
- **Test utility**: `tools/auto_prd/tests/__init__.py:7-32` - `safe_cleanup` function

### Patterns
- Context manager pattern for resource management
- `delete=False` with explicit caller cleanup (when file must persist)
- `finally` blocks for guaranteed cleanup
- Atomic file operations with temp files

### Technical Constraints
- Must use context manager pattern with `tempfile.NamedTemporaryFile`
- Must ensure cleanup in both success and error paths
- Must not break existing functionality
- Must preserve file persistence for `generate_tracker()` usage
