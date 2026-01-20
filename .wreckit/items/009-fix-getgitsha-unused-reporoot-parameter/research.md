# Research: Fix get_git_sha() unused repo_root parameter

**Date**: 2026-01-19
**Item**: 009-fix-getgitsha-unused-reporoot-parameter

## Research Question
Function parameter is misleading as it's never used - function always runs in current directory.

**Motivation:** Fixes incorrect function behavior and makes the API honest.

**Technical constraints:**
- Either implement using repo_root with git command's cwd parameter, or remove the parameter

**Signals:** priority: high

## Summary
The item title is **misleading** - the `repo_root` parameter IS being used correctly in `get_git_sha()` (via `cwd=repo_root` passed to `run_cmd`). However, the function has **two critical bugs** that make it completely non-functional:

1. **Missing import**: `run_cmd` is used but never imported, causing a `NameError` at runtime
2. **Incorrect unpacking**: `run_cmd` returns 3 values `(stdout, stderr, returncode)`, but the code only unpacks 2 values `out, _`

Additionally, there's **duplicate functionality**: `git_head_sha()` in `git_ops.py` does the exact same thing correctly, and is already used throughout the codebase (5 usages vs 1 usage for `get_git_sha`).

## Current State Analysis

### Existing Implementation

**File**: `tools/auto_prd/utils.py:262-265`
```python
def get_git_sha(repo_root: Path) -> str:
    """Get current git commit SHA."""
    out, _ = run_cmd(["git", "rev-parse", "HEAD"], cwd=repo_root)
    return out.strip()
```

**Critical Issues**:
1. `run_cmd` is not imported in `utils.py` (line 264 uses it without import)
2. Incorrect unpacking: `run_cmd` returns `(stdout, stderr, returncode)` but code expects 2 values
3. This causes `NameError: name 'run_cmd' is not defined` at runtime

**Duplicate Functionality**:
- `git_head_sha(repo_root: Path)` in `tools/auto_prd/git_ops.py:113-115` does the exact same thing
- `git_head_sha` is correctly implemented and used in 5 places
- `get_git_sha` is only used in 1 place (verification_persistence.py)

### Current Patterns and Conventions

The codebase has a clear pattern for git operations with `repo_root`:

**File**: `tools/auto_prd/git_ops.py`
```python
from .command import run_cmd

def git_head_sha(repo_root: Path) -> str:
    out, _, _ = run_cmd(["git", "rev-parse", "HEAD"], cwd=repo_root)
    return out.strip()

def workspace_has_changes(repo_root: Path) -> bool:
    out, _, _ = run_cmd(["git", "status", "--porcelain"], cwd=repo_root)
    return bool(out.strip())
```

**Pattern**:
1. Import `run_cmd` from `.command` module
2. Use 3-value unpacking: `out, _, _ = run_cmd(...)`
3. Pass `cwd=repo_root` to specify working directory
4. Return stripped string result

### Integration Points

**Current Usage** (only 1 place):
- `tools/auto_prd/verification_persistence.py:245` - `current_git_sha = get_git_sha(self.repo_root)`
- `tools/auto_prd/verification_persistence.py:324` - `git_sha = get_git_sha(repo_root)`

**Alternative Implementation** (used in 5 places):
- `tools/auto_prd/local_loop.py:31`
- `tools/auto_prd/review_loop.py:35`
- `tools/auto_prd/startup.py:27`
- `tools/auto_prd/support_loop.py:13`
- `tools/auto_prd/worker.py:22`

All use `git_head_sha` from `git_ops.py` instead.

### Key Files

- `tools/auto_prd/utils.py:262-265` - **Broken** `get_git_sha()` function (missing import, wrong unpacking)
- `tools/auto_prd/git_ops.py:113-115` - **Working** `git_head_sha()` function (correct implementation)
- `tools/auto_prd/command.py:360-545` - `run_cmd()` function definition (returns 3 values)
- `tools/auto_prd/verification_persistence.py:17, 245, 324` - Only module using `get_git_sha()`

## Technical Considerations

### Dependencies
- **External**: None (uses only standard library subprocess)
- **Internal**:
  - `tools.auto_prd.command.run_cmd` - Command execution helper (must be imported)
  - `tools.auto_prd.logging_utils` - For logging (already imported in utils.py)

### Patterns to Follow
1. **Import pattern**: `from .command import run_cmd` (see git_ops.py:10)
2. **Unpacking pattern**: Use 3-value unpacking `out, _, _ = run_cmd(...)` (see git_ops.py pattern)
3. **CWD usage**: Pass `cwd=repo_root` to `run_cmd` (already correct in get_git_sha)
4. **Code organization**: Git operations belong in `git_ops.py`, not `utils.py`

### Circular Import Considerations
- `command.py` imports from `utils.py` (scrub_cli_text on line 28)
- `utils.py` cannot import from `command.py` without causing circular import
- This is likely why `run_cmd` is not imported in `utils.py`
- **Solution**: Move `get_git_sha` to `git_ops.py` or use it from there

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Circular import** if adding import to utils.py | High | Don't add import - either move function or use git_head_sha |
| **Breaking change** if removing function | Medium | Verify no external callers; update verification_persistence.py |
| **Inconsistent API** with duplicate functions | Low | Standardize on git_head_sha (more widely used) |
| **Test coverage gaps** for git operations | Low | git_head_sha works; get_git_sha is currently broken anyway |

## Recommended Approach

**Option 1: Remove duplicate, use existing (RECOMMENDED)**
1. Remove `get_git_sha()` from `utils.py` (it's broken and redundant)
2. Update `verification_persistence.py` to import and use `git_head_sha` from `git_ops.py`
3. Add tests for `git_head_sha` if none exist
4. **Pros**: Eliminates duplication, uses working code, no circular import issues
5. **Cons**: Changes import in one file

**Option 2: Fix and move function**
1. Move `get_git_sha()` from `utils.py` to `git_ops.py`
2. Fix import (add `from .command import run_cmd`)
3. Fix unpacking (`out, _, _ = run_cmd(...)`)
4. Keep using `get_git_sha` in `verification_persistence.py`
5. **Pros**: Preserves current API, fixes bugs
6. **Cons**: Adds duplication with git_head_sha

**Option 3: Fix in place with late import**
1. Keep `get_git_sha()` in `utils.py`
2. Use late import inside function: `from .command import run_cmd`
3. Fix unpacking (`out, _, _ = run_cmd(...)`)
4. **Pros**: Minimal changes, preserves API
5. **Cons**: Performance overhead, unusual pattern, still duplicates git_head_sha

**Recommended**: **Option 1** - Use `git_head_sha` consistently. It's already working, widely used (5x more), and properly located in `git_ops.py` alongside other git operations.

## Open Questions

1. **Why does get_git_sha exist separately?** Was it intentional duplication or an oversight?
2. **Are there any external callers?** Need to verify nothing outside the codebase imports get_git_sha
3. **Why wasn't this caught?** The NameError suggests the code path is never tested
4. **API preference?** Should we use `get_git_sha` or `git_head_sha` naming convention?

## Implementation Notes

### Current Call Sites
```python
# verification_persistence.py:245
current_git_sha = get_git_sha(self.repo_root)

# verification_persistence.py:324
git_sha = get_git_sha(repo_root)
```

### Proposed Change (Option 1)
```python
# verification_persistence.py - update imports
from .git_ops import git_head_sha, git_status_snapshot  # add git_head_sha

# verification_persistence.py:245 - update call
current_git_sha = git_head_sha(self.repo_root)

# verification_persistence.py:324 - update call
git_sha = git_head_sha(repo_root)
```

### Testing Strategy
1. Verify `git_head_sha` works correctly in repository context
2. Test verification_persistence.py after change
3. Check for any other callers in the codebase
4. Run existing tests to ensure no regressions
