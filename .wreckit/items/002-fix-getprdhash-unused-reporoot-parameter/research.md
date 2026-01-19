# Research: Fix get_prd_hash() unused repo_root parameter

**Date**: 2026-01-19
**Item**: 002-fix-getprdhash-unused-reporoot-parameter

## Research Question
Function was refactored but the parameter was not removed or implemented, causing incorrect behavior when repo_root is passed.

**Motivation:** Fixes incorrect function behavior and removes misleading API surface.

**Technical constraints:**
- Either use the parameter to construct PRD path or remove it entirely
- Update function to use repo_root / 'PRD.md' when provided

**Signals:** priority: critical

## Summary
**CRITICAL FINDING**: The issue described in this task item has **ALREADY BEEN FIXED** in the current codebase. The `get_prd_hash()` function correctly uses the `repo_root` parameter to construct the PRD path. However, there is a mismatch between the outdated `CODEBASE_ANALYSIS_REPORT.md` (which is untracked) and the actual implementation.

The function currently accepts a required `repo_root: Path` parameter and correctly uses it to construct the PRD file path as `repo_root / "PRD.md"`. All call sites in the codebase pass the `repo_root` parameter correctly. The task description appears to be based on an outdated analysis report that does not reflect the current state of the code.

**No implementation work is required** - the function is working as intended. The only action needed is to verify this conclusion and potentially update or remove the outdated `CODEBASE_ANALYSIS_REPORT.md` if it exists.

## Current State Analysis

### Existing Implementation
The `get_prd_hash()` function is located at `tools/auto_prd/utils.py:268-273`:

```python
def get_prd_hash(repo_root: Path) -> str:
    """Compute SHA256 hash of PRD file for change detection."""
    prd_path = repo_root / "PRD.md"
    if prd_path.exists():
        return compute_file_hash(prd_path)
    return ""
```

**Key observations:**
- The `repo_root` parameter is **required** (no default value)
- The parameter is **properly used** to construct the PRD path: `repo_root / "PRD.md"`
- The function includes proper existence checking before hashing
- Returns empty string if PRD.md doesn't exist (graceful degradation)

### Integration Points

The function is called in **4 locations** across the codebase:

1. **`tools/auto_prd/verification_persistence.py:247`**
   ```python
   current_prd_hash = get_prd_hash(self.repo_root)
   ```
   Context: Checking if verification evidence is fresh in `is_run_fresh()` method

2. **`tools/auto_prd/verification_persistence.py:325`**
   ```python
   prd_hash = get_prd_hash(repo_root)
   ```
   Context: Creating verification run in `create_verification_run()` function

3. **`tools/auto_prd/scope_reviewer.py:220`**
   ```python
   prd_hash=get_prd_hash(self.repo_root),
   ```
   Context: Recording PRD hash in scope review results

4. **`tools/auto_prd/scope_reviewer.py:225`**
   ```python
   current_prd_hash = get_prd_hash(self.repo_root)
   ```
   Context: Comparing current PRD hash with last recorded hash

5. **`tools/auto_prd/readiness_loop.py:146`**
   ```python
   current_prd_hash=get_prd_hash(self.repo_root),
   ```
   Context: Checking if scope review should be triggered

**All call sites consistently pass `self.repo_root` or `repo_root` as the argument**, confirming the parameter is essential and properly used.

## Key Files

### Core Implementation
- **`tools/auto_prd/utils.py:268-273`** - `get_prd_hash()` function implementation
  - Takes required `repo_root: Path` parameter
  - Constructs path as `repo_root / "PRD.md"`
  - Returns SHA256 hash or empty string if file doesn't exist

- **`tools/auto_prd/utils.py:276-284`** - `compute_file_hash()` helper function
  - Generic file hashing utility using SHA256
  - Reads file in chunks for memory efficiency
  - Used by `get_prd_hash()`

### Call Sites
- **`tools/auto_prd/verification_persistence.py:247`** - Freshness check in verification system
- **`tools/auto_prd/verification_persistence.py:325`** - Creating verification runs
- **`tools/auto_prd/scope_reviewer.py:220`** - Scope review result tracking
- **`tools/auto_prd/scope_reviewer.py:225`** - PRD change detection
- **`tools/auto_prd/readiness_loop.py:146`** - Ralph Wiggum Loop orchestration

### Related Files
- **`tools/auto_prd/tests/test_utils.py`** - Existing tests for utils module
  - **IMPORTANT**: No tests currently exist for `get_prd_hash()` or `compute_file_hash()`
  - This is a gap in test coverage that should be addressed

### Outdated Analysis
- **`CODEBASE_ANALYSIS_REPORT.md:58-76`** - Untracked file containing outdated analysis
  - Claims `get_prd_hash()` has unused `repo_root` parameter
  - Shows incorrect signature: `def get_prd_hash(repo_root: Path | None = None) -> str:`
  - Shows incorrect implementation: `return hash_file(open("PRD.md"))`
  - **This does NOT match the current codebase**

## Technical Considerations

### Dependencies
- **External**: `hashlib` (standard library) - used by `compute_file_hash()`
- **Internal**:
  - `pathlib.Path` for path construction
  - No other internal dependencies

### Patterns to Follow
1. **Path construction pattern**: The current implementation follows the correct pattern used elsewhere:
   ```python
   prd_path = repo_root / "PRD.md"  # Proper use of pathlib /
   ```

2. **Existence checking**: Always check file existence before operations:
   ```python
   if prd_path.exists():
       return compute_file_hash(prd_path)
   return ""
   ```

3. **Graceful degradation**: Return empty string for missing files rather than raising exceptions

4. **Consistent API**: The function signature matches similar functions in the codebase:
   ```python
   def get_git_sha(repo_root: Path) -> str:  # Similar pattern at utils.py:262
   ```

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Outdated analysis report causes confusion** | Low | The report is untracked and should be updated or removed |
| **Missing test coverage** | Medium | Add comprehensive tests for `get_prd_hash()` and `compute_file_hash()` |
| **Breaking changes if signature is modified** | High | **DO NOT CHANGE** - current implementation is correct and all 5 call sites depend on it |
| **Edge cases not tested** | Low | Add tests for: missing PRD.md, empty PRD.md, large PRD files |

## Recommended Approach

### Conclusion: NO IMPLEMENTATION REQUIRED

The `get_prd_hash()` function is **already correctly implemented**:
- ✅ Parameter is properly used to construct PRD path
- ✅ All call sites pass the parameter correctly
- ✅ Function follows existing code patterns
- ✅ Includes proper error handling

### Recommended Actions

1. **DO NOT modify the function** - it's working correctly

2. **Update or remove** `CODEBASE_ANALYSIS_REPORT.md`:
   - Option A: Remove the file (it's untracked and contains outdated information)
   - Option B: Update the file to reflect current state
   - Option C: Add a disclaimer that the report may be outdated

3. **Add test coverage** (optional but recommended):
   - Create tests in `tools/auto_prd/tests/test_utils.py`
   - Test scenarios:
     - Normal case: PRD.md exists
     - Edge case: PRD.md doesn't exist (returns "")
     - Edge case: Empty PRD.md
     - Verify hash changes when file content changes
     - Verify hash is stable for same content

4. **Document the function** (optional):
   - The current docstring is adequate but could be enhanced with examples

## Open Questions

1. **Why does the task description claim the parameter is unused when it clearly is used?**
   - **Answer**: The task appears to be based on an outdated `CODEBASE_ANALYSIS_REPORT.md` that doesn't match the current codebase state.

2. **Should we add tests for this function?**
   - **Recommendation**: Yes, but this is outside the scope of the current task. The function works correctly; adding tests would improve robustness but is not critical.

3. **What should be done with the outdated CODEBASE_ANALYSIS_REPORT.md?**
   - **Recommendation**: Since it's untracked and contains misinformation, it should be removed or updated.

4. **Are there any edge cases not handled by the current implementation?**
   - **Analysis**: The function handles missing files gracefully. Potential edge cases include permission errors or corrupt files, but these would naturally raise exceptions which is appropriate behavior.
