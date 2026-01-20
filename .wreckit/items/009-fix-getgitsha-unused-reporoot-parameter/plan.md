# Fix get_git_sha() unused repo_root parameter Implementation Plan

## Overview
This item addresses a misleading function title - the `repo_root` parameter in `get_git_sha()` IS being used correctly, but the function has critical bugs that make it non-functional. Additionally, it duplicates existing functionality from `git_head_sha()`. The solution is to remove the broken duplicate function and standardize on the working implementation.

## Current State Analysis

**Broken Function**: `tools/auto_prd/utils.py:262-265`
```python
def get_git_sha(repo_root: Path) -> str:
    """Get current git commit SHA."""
    out, _ = run_cmd(["git", "rev-parse", "HEAD"], cwd=repo_root)  # BUG: NameError + wrong unpacking
    return out.strip()
```

**Critical Issues**:
1. `run_cmd` is not imported in `utils.py` → causes `NameError` at runtime
2. Incorrect unpacking: `run_cmd` returns `(stdout, stderr, returncode)` but code expects 2 values
3. Cannot add import due to circular import: `command.py` imports from `utils.py`

**Working Alternative**: `tools/auto_prd/git_ops.py:113-115`
```python
def git_head_sha(repo_root: Path) -> str:
    out, _, _ = run_cmd(["git", "rev-parse", "HEAD"], cwd=repo_root)
    return out.strip()
```

**Usage Statistics**:
- `git_head_sha()`: Used in 8 files (23 times total), properly imported from `git_ops.py`
- `get_git_sha()`: Used in only 1 file (2 times), completely broken

## Desired End State

1. **Remove broken duplicate**: Delete `get_git_sha()` from `utils.py`
2. **Standardize API**: Use `git_head_sha()` consistently across codebase
3. **Update callers**: Replace the 2 calls in `verification_persistence.py` with `git_head_sha()`
4. **Maintain functionality**: No behavioral changes - same git SHA retrieval, just using working code

### Key Discoveries:
- `utils.py:262-265` - Broken `get_git_sha()` with NameError and wrong unpacking
- `git_ops.py:113-115` - Working `git_head_sha()` with correct implementation (8 files use this)
- `verification_persistence.py:17, 245, 324` - Only file using broken `get_git_sha()`
- `command.py:28` - Imports from `utils.py`, creating circular import constraint
- No tests exist for either function (verified: no `test_git*.py` files, no tests in `test_utils.py`)

## What We're NOT Doing

- **NOT fixing `get_git_sha()` in place** - would require circular import workaround
- **NOT moving `get_git_sha()` to `git_ops.py` - creates unnecessary duplication with `git_head_sha()`
- **NOT adding new tests** - existing working code is already tested via integration tests that mock `git_head_sha`
- **NOT changing the API** - `git_head_sha()` is already the standard across the codebase
- **NOT updating documentation** - no separate documentation files exist for these internal utilities

## Implementation Approach

**Strategy**: Remove and Replace (simplest, safest approach)

**Rationale**:
1. `git_head_sha()` is already the de facto standard (8 files vs 1 file)
2. `get_git_sha()` is completely broken (NameError at runtime)
3. Cannot fix in place due to circular import constraint
4. Removing duplication improves code maintainability
5. Zero behavioral risk - same functionality, just using working code

**Risk Level**: Low
- Only 1 file needs changes (`verification_persistence.py`)
- Change is localized and mechanical (function rename)
- No API changes for external consumers (private module)
- Can easily rollback if issues arise

---

## Phase 1: Remove Broken Function and Update Imports

### Overview
Remove the broken `get_git_sha()` function from `utils.py` and update the import in `verification_persistence.py` to use `git_head_sha()` instead.

### Changes Required:

#### 1. Remove get_git_sha() from utils.py
**File**: `tools/auto_prd/utils.py`
**Lines**: 262-265
**Changes**: Delete the entire `get_git_sha()` function

```python
# DELETE these 4 lines:
def get_git_sha(repo_root: Path) -> str:
    """Get current git commit SHA."""
    out, _ = run_cmd(["git", "rev-parse", "HEAD"], cwd=repo_root)
    return out.strip()
```

#### 2. Update imports in verification_persistence.py
**File**: `tools/auto_prd/verification_persistence.py`
**Line**: 17
**Changes**: Replace `get_git_sha` with `git_head_sha` and update import source

```python
# BEFORE:
from .utils import get_git_sha, get_prd_hash

# AFTER:
from .git_ops import git_head_sha
from .utils import get_prd_hash
```

#### 3. Update function calls in verification_persistence.py
**File**: `tools/auto_prd/verification_persistence.py`
**Lines**: 245, 324
**Changes**: Replace `get_git_sha()` calls with `git_head_sha()`

```python
# Line 245 - BEFORE:
current_git_sha = get_git_sha(self.repo_root)

# Line 245 - AFTER:
current_git_sha = git_head_sha(self.repo_root)

# Line 324 - BEFORE:
git_sha = get_git_sha(repo_root)

# Line 324 - AFTER:
git_sha = git_head_sha(repo_root)
```

### Success Criteria:

#### Automated Verification:
- [ ] Code search confirms `get_git_sha` no longer exists in codebase
- [ ] Code search confirms `git_head_sha` import added to verification_persistence.py
- [ ] Python syntax check passes: `python -m py_compile tools/auto_prd/verification_persistence.py`
- [ ] Python syntax check passes: `python -m py_compile tools/auto_prd/utils.py`
- [ ] Import check succeeds: `python -c "from tools.auto_prd.verification_persistence import VerificationRun; print('Import OK')"`
- [ ] No circular import errors when importing the module

#### Manual Verification:
- [ ] Visual inspection confirms function is removed from utils.py
- [ ] Visual inspection confirms imports are correct in verification_persistence.py
- [ ] Visual inspection confirms both call sites updated
- [ ] Git diff shows only expected changes (no unexpected modifications)

**Note**: Complete all automated verification, then pause for manual confirmation before proceeding to next phase.

---

## Phase 2: Verify Functionality

### Overview
Run existing tests to ensure the changes don't break anything, particularly verification-related tests.

### Changes Required:
No code changes in this phase - verification only.

### Test Execution:

#### 1. Run verification-related tests
**Command**: `python -m pytest tools/auto_prd/tests/test_verification.py -v`
**Purpose**: Ensure verification persistence still works correctly

#### 2. Run utils tests
**Command**: `python -m pytest tools/auto_prd/tests/test_utils.py -v`
**Purpose**: Ensure other utilities in utils.py still work

#### 3. Run integration tests that use git operations
**Command**: `python -m pytest tools/auto_prd/tests/test_review_loop.py::TestReviewLoop::test_verify_stale_check -v`
**Purpose**: Verify git_head_sha mocking still works (tests mock git_head_sha, not get_git_sha)

#### 4. Check for any other test failures
**Command**: `python -m pytest tools/auto_prd/tests/ -x -v 2>&1 | head -100`
**Purpose**: Catch any unexpected regressions early

### Success Criteria:

#### Automated Verification:
- [ ] test_verification.py passes all tests
- [ ] test_utils.py passes all tests
- [ ] test_review_loop.py git-related tests pass
- [ ] No new test failures introduced
- [ ] No import errors in test runs

#### Manual Verification:
- [ ] Review test output for any warnings or deprecations
- [ ] Confirm no tests reference `get_git_sha` (should all use `git_head_sha`)
- [ ] Spot-check 2-3 test files to ensure mocks still work

**Note**: If tests fail, investigate whether they were using the broken `get_git_sha` function (unlikely since it would have caused NameError).

---

## Testing Strategy

### Unit Tests:
No new unit tests needed - existing integration tests already cover this functionality:
- `test_verification.py` tests verification persistence (uses get_git_sha, will use git_head_sha after change)
- `test_review_loop.py` mocks `git_head_sha` (8 test methods mock this function)
- These tests verify the behavior at the integration level

### Integration Tests:
Existing integration tests provide coverage:
- Tests that mock `git_head_sha` prove it's the correct API to use
- Verification persistence tests ensure git_sha is used correctly for reproducibility
- No behavior change means existing tests remain valid

### Manual Testing Steps:
1. **Code Search Verification**:
   ```bash
   # Confirm get_git_sha is removed
   grep -r "get_git_sha" tools/auto_prd/ --include="*.py"
   # Expected: Only verification_persistence.py import line (to be removed)

   # Confirm git_head_sha is imported in verification_persistence.py
   grep "git_head_sha" tools/auto_prd/verification_persistence.py
   # Expected: Import line and 2 usage sites
   ```

2. **Import Verification**:
   ```bash
   # Test that imports work without circular import
   python -c "from tools.auto_prd.verification_persistence import VerificationRun; print('OK')"
   # Expected: "OK" output, no errors
   ```

3. **Runtime Verification** (if test suite exists):
   ```bash
   # Run a quick smoke test
   python -m pytest tools/auto_prd/tests/test_verification.py -v -k "test_create_run"
   # Expected: Test passes
   ```

## Migration Notes

### For Other Developers:
- If you were using `get_git_sha()` from `utils.py`, switch to `git_head_sha()` from `git_ops.py`
- The API is identical: `git_head_sha(repo_root: Path) -> str`
- No behavioral changes - same function, different name

### Rollback Strategy:
If issues arise after deployment:
1. Restore `get_git_sha()` in `utils.py` (but fix the bugs!)
2. Revert imports in `verification_persistence.py`
3. However, this is NOT recommended because `get_git_sha()` is broken (NameError)

Better rollback: Fix any issues with `git_head_sha()` usage rather than reverting to broken code.

## References

### Research:
- `/Users/simo/Projects/autodev/.wreckit/items/009-fix-getgitsha-unused-reporoot-parameter/research.md`

### Key Files:
- `tools/auto_prd/utils.py:262-265` - Broken function to remove
- `tools/auto_prd/git_ops.py:113-115` - Working function to use instead
- `tools/auto_prd/verification_persistence.py:17, 245, 324` - Update imports and calls
- `tools/auto_prd/command.py:28, 360-377` - Circular import constraint, run_cmd signature

### Related Usage Patterns:
- `tools/auto_prd/local_loop.py:31, 224, 450, 598, 603` - Examples of git_head_sha usage
- `tools/auto_prd/review_loop.py:35, 578, 720` - More examples
- `tools/auto_prd/startup.py:27, 243` - Startup usage pattern
