# Fix get_prd_hash() unused repo_root parameter Implementation Plan

## Overview
**CRITICAL DISCOVERY**: The issue described in this task item has **ALREADY BEEN FIXED** in the current codebase. The `get_prd_hash()` function correctly uses the `repo_root` parameter to construct the PRD path as `repo_root / "PRD.md"`. All 5 call sites throughout the codebase properly pass the `repo_root` parameter.

This task appears to be based on an outdated analysis that does not reflect the current state of the code. The only actionable work remaining is to add comprehensive test coverage for the already-correct implementation.

## Current State Analysis

### Existing Implementation (CORRECT)
File: `tools/auto_prd/utils.py:268-284`

```python
def get_prd_hash(repo_root: Path) -> str:
    """Compute SHA256 hash of PRD file for change detection."""
    prd_path = repo_root / "PRD.md"
    if prd_path.exists():
        return compute_file_hash(prd_path)
    return ""


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA256 hash of a file for change detection."""
    import hashlib

    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()
```

**Key observations:**
- ✅ `repo_root` parameter is **required** (no default value)
- ✅ Parameter is **properly used** to construct PRD path: `repo_root / "PRD.md"`
- ✅ Includes proper existence checking before hashing
- ✅ Returns empty string for graceful degradation if PRD.md doesn't exist
- ✅ Helper function `compute_file_hash()` uses memory-efficient chunked reading

### Call Sites (ALL CORRECT)
All 5 call sites properly pass `repo_root` parameter:

1. **`tools/auto_prd/verification_persistence.py:247`**
   - Context: Checking if verification evidence is fresh in `is_run_fresh()`
   - Code: `current_prd_hash = get_prd_hash(self.repo_root)`

2. **`tools/auto_prd/verification_persistence.py:325`**
   - Context: Creating verification run in `create_verification_run()`
   - Code: `prd_hash = get_prd_hash(repo_root)`

3. **`tools/auto_prd/scope_reviewer.py:220`**
   - Context: Recording PRD hash in scope review results
   - Code: `prd_hash=get_prd_hash(self.repo_root)`

4. **`tools/auto_prd/scope_reviewer.py:225`**
   - Context: Comparing current PRD hash with last recorded hash
   - Code: `current_prd_hash = get_prd_hash(self.repo_root)`

5. **`tools/auto_prd/readiness_loop.py:146`**
   - Context: Checking if scope review should be triggered
   - Code: `current_prd_hash=get_prd_hash(self.repo_root)`

### Test Coverage Gap
File: `tools/auto_prd/tests/test_utils.py`

**Current state**: No tests exist for `get_prd_hash()` or `compute_file_hash()`

**Impact**: Medium - the function works correctly but lacks automated verification, which creates risk for future regressions.

## Desired End State

### Specification
1. **No code changes to `get_prd_hash()` or `compute_file_hash()`** - they are already correct
2. **Add comprehensive test coverage** to verify current behavior and prevent regressions
3. **Document verification** that the function is working as intended

### Verification Criteria
- [ ] All new tests pass for `get_prd_hash()` function
- [ ] All new tests pass for `compute_file_hash()` function
- [ ] Test coverage includes normal cases and edge cases
- [ ] Existing tests continue to pass (no regressions)
- [ ] Manual verification confirms function behavior matches expectations

### Key Discoveries
- **Finding 1**: Function signature is `def get_prd_hash(repo_root: Path) -> str:` (utils.py:268)
- **Finding 2**: Parameter is required (no default value) and properly used
- **Finding 3**: All 5 call sites pass the parameter correctly
- **Finding 4**: No CODEBASE_ANALYSIS_REPORT.md file exists in the repository
- **Finding 5**: No test coverage exists for these functions (test_utils.py has no tests for them)
- **Pattern to follow**: Existing test structure in test_utils.py uses unittest and safe_import pattern
- **Constraint**: Do NOT modify the function implementation - it's already correct

## What We're NOT Doing

- ❌ **NOT modifying** `get_prd_hash()` function - it's already correct
- ❌ **NOT modifying** `compute_file_hash()` function - it's already correct
- ❌ **NOT updating** any call sites - they all pass the parameter correctly
- ❌ **NOT removing** the parameter - it's essential and used everywhere
- ❌ **NOT searching for** CODEBASE_ANALYSIS_REPORT.md - it doesn't exist in the repo
- ❌ **NOT adding** default parameter values - the required parameter is correct design
- ❌ **NOT changing** the function signature - would break all 5 call sites

## Implementation Approach

**Strategy**: Verification and Test Coverage Only

Since the function is already correctly implemented, this task focuses on:
1. Adding comprehensive automated tests to verify the correct behavior
2. Documenting the verification that no changes are needed
3. Ensuring future changes don't introduce regressions

**Reasoning**:
- The function works correctly and all call sites use it properly
- The task description appears based on outdated information
- Adding tests provides value by preventing regressions
- No code changes reduces risk and avoids breaking working functionality

---

## Phase 1: Add Comprehensive Test Coverage

### Overview
Add thorough test coverage for `get_prd_hash()` and `compute_file_hash()` functions to verify the existing correct implementation and prevent future regressions.

### Changes Required:

#### 1. Test Functions for get_prd_hash()
**File**: `tools/auto_prd/tests/test_utils.py`
**Changes**: Add new test class `GetPrdHashTests` with comprehensive test cases

```python
import tempfile
from pathlib import Path

get_prd_hash = safe_import("tools.auto_prd.utils", "..utils", "get_prd_hash")
compute_file_hash = safe_import("tools.auto_prd.utils", "..utils", "compute_file_hash")


class GetPrdHashTests(unittest.TestCase):
    """Tests for get_prd_hash helper function."""

    def test_returns_hash_when_prd_exists(self) -> None:
        """Verify function returns SHA256 hash when PRD.md exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            prd_path = repo_root / "PRD.md"
            prd_path.write_text("# Test PRD\n\nContent here")

            result = get_prd_hash(repo_root)

            self.assertIsInstance(result, str)
            self.assertEqual(len(result), 64)  # SHA256 hex digest length
            self.assertNotEqual(result, "")

    def test_returns_empty_string_when_prd_missing(self) -> None:
        """Verify function returns empty string when PRD.md doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            # Don't create PRD.md

            result = get_prd_hash(repo_root)

            self.assertEqual(result, "")

    def test_returns_hash_for_empty_prd(self) -> None:
        """Verify function returns valid hash even for empty PRD.md."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            prd_path = repo_root / "PRD.md"
            prd_path.write_text("")

            result = get_prd_hash(repo_root)

            # Empty file still has a hash (SHA256 of empty string)
            self.assertEqual(result, "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")

    def test_hash_changes_when_content_changes(self) -> None:
        """Verify hash value changes when PRD content changes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            prd_path = repo_root / "PRD.md"

            prd_path.write_text("Version 1")
            hash1 = get_prd_hash(repo_root)

            prd_path.write_text("Version 2")
            hash2 = get_prd_hash(repo_root)

            self.assertNotEqual(hash1, hash2)

    def test_hash_is_stable_for_same_content(self) -> None:
        """Verify hash is stable across multiple calls with same content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            prd_path = repo_root / "PRD.md"
            prd_path.write_text("Stable content")

            hash1 = get_prd_hash(repo_root)
            hash2 = get_prd_hash(repo_root)

            self.assertEqual(hash1, hash2)


class ComputeFileHashTests(unittest.TestCase):
    """Tests for compute_file_hash helper function."""

    def test_returns_sha256_hash(self) -> None:
        """Verify function returns SHA256 hash of file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.txt"
            file_path.write_text("Test content")

            result = compute_file_hash(file_path)

            self.assertIsInstance(result, str)
            self.assertEqual(len(result), 64)  # SHA256 hex digest length

    def test_hash_matches_known_value(self) -> None:
        """Verify hash matches known SHA256 value for test content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.txt"
            content = "Hello, World!"
            file_path.write_text(content)

            result = compute_file_hash(file_path)

            # Known SHA256 hash of "Hello, World!" (UTF-8)
            expected = "dffd6021bb2bd5b0af676290809ec3a53191dd81c7f70a4b28688a362182986f"
            self.assertEqual(result, expected)

    def test_handles_large_files_efficiently(self) -> None:
        """Verify function can handle large files without memory issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "large.txt"
            # Create 10MB file
            large_content = "x" * (10 * 1024 * 1024)
            file_path.write_text(large_content)

            result = compute_file_hash(file_path)

            self.assertEqual(len(result), 64)
            self.assertNotEqual(result, "")

    def test_handles_binary_files(self) -> None:
        """Verify function handles binary files correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "binary.bin"
            binary_content = bytes([0, 1, 2, 3, 255, 254, 253])
            file_path.write_bytes(binary_content)

            result = compute_file_hash(file_path)

            self.assertEqual(len(result), 64)
            # Known SHA256 of these bytes
            expected = "9f1a6af8704a87a617640fce68a4c7db0b61a0e24f8db5bda6aaaefc6f365bb6"
            self.assertEqual(result, expected)
```

### Success Criteria:

#### Automated Verification:
- [ ] New test class `GetPrdHashTests` added to test_utils.py
- [ ] New test class `ComputeFileHashTests` added to test_utils.py
- [ ] All new tests pass: `python -m pytest tools/auto_prd/tests/test_utils.py::GetPrdHashTests -v`
- [ ] All new tests pass: `python -m pytest tools/auto_prd/tests/test_utils.py::ComputeFileHashTests -v`
- [ ] All existing tests continue to pass: `python -m pytest tools/auto_prd/tests/test_utils.py -v`
- [ ] Test coverage includes 5 test cases for get_prd_hash()
- [ ] Test coverage includes 4 test cases for compute_file_hash()

#### Manual Verification:
- [ ] Review test code to ensure it follows existing test patterns in test_utils.py
- [ ] Verify tests use safe_import pattern consistent with existing tests
- [ ] Confirm tests cover both normal and edge cases
- [ ] Validate that no code changes were made to get_prd_hash() or compute_file_hash()

**Note**: Complete all automated verification, then pause for manual confirmation before marking task complete.

---

## Testing Strategy

### Unit Tests:

**For `get_prd_hash()`:**
1. ✅ Returns SHA256 hash when PRD.md exists (normal case)
2. ✅ Returns empty string when PRD.md doesn't exist (graceful degradation)
3. ✅ Returns valid hash for empty PRD.md (edge case)
4. ✅ Hash changes when content changes (change detection)
5. ✅ Hash is stable for same content (consistency)

**For `compute_file_hash()`:**
1. ✅ Returns SHA256 hash with correct length (format validation)
2. ✅ Hash matches known SHA256 value (correctness validation)
3. ✅ Handles large files efficiently (10MB test for memory efficiency)
4. ✅ Handles binary files correctly (binary data support)

### Integration Testing:
No integration tests required - this is a pure utility function with no external dependencies beyond the filesystem.

### Manual Testing Steps:
1. Run all tests: `python -m pytest tools/auto_prd/tests/test_utils.py -v`
2. Verify new test output shows all tests passing
3. Run the actual auto_prd workflow to ensure no runtime issues
4. Check that PRD change detection still works in scope_reviewer.py

## Migration Notes
**Not applicable** - no code changes required, only adding test coverage.

## Risk Assessment

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Tests might have bugs | Low | Low | Review test code carefully, run multiple times |
| Test environment differences | Low | Low | Use tempfile for isolation, avoid path dependencies |
| Breaking existing tests | Low | Very Low | Only adding new tests, not modifying existing ones |

## References
- Research: `/Users/simo/Projects/autodev/.wreckit/items/002-fix-getprdhash-unused-reporoot-parameter/research.md`
- Implementation: `tools/auto_prd/utils.py:268-284`
- Test file: `tools/auto_prd/tests/test_utils.py`
- Call sites:
  - `tools/auto_prd/verification_persistence.py:247`
  - `tools/auto_prd/verification_persistence.py:325`
  - `tools/auto_prd/scope_reviewer.py:220`
  - `tools/auto_prd/scope_reviewer.py:225`
  - `tools/auto_prd/readiness_loop.py:146`

## Conclusion

This implementation plan focuses on **verification and test coverage only**. The `get_prd_hash()` function is **already correctly implemented** and requires no code changes. The task description appears to be based on outdated analysis that doesn't match the current codebase state.

By adding comprehensive test coverage, we:
1. ✅ Verify the existing correct implementation
2. ✅ Prevent future regressions
3. ✅ Document expected behavior through tests
4. ✅ Provide confidence in the codebase

**No code changes to production code are required.**
