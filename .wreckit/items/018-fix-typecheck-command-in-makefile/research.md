# Research: Fix TypeCheck command in Makefile

**Date**: 2025-01-19
**Item**: 018-fix-typecheck-command-in-makefile

## Research Question
Typecheck doesn't respect Python configuration and hides import issues.

**Motivation:** Ensures type checking uses correct Python and catches all type errors.

**Technical constraints:**
- Use $(PYTHON) variable instead of hardcoded python3
- Consider removing --ignore-missing-imports flag

**Signals:** priority: medium

## Summary

The current `typecheck` target in the Makefile uses `$(PYTHON)` (which is set to `python3`) correctly, **so the first constraint is already satisfied**. However, the `--ignore-missing-imports` flag is indeed hiding import-related type errors. Research reveals:

1. **Python Version Mismatch**: The project requires Python 3.10+ per `pyproject.toml:6`, but the system has multiple Python installations (3.9.6, 3.13.2, 3.13.7) and the CI uses 3.11, while the `tools/.venv` uses Python 3.13.7. The Makefile's `PYTHON := python3` resolves to `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3`, which may not match the venv's Python 3.13.7.

2. **Missing Import Errors Hidden**: With `--ignore-missing-imports`, mypy currently reports 22 type errors. Without the flag, mypy reports 62 total errors, including 5 additional `import-untyped` errors that indicate missing type stubs for the `tools.auto_prd` module itself.

3. **Core Issue**: The `tools/auto_prd` package lacks proper type annotations (no `py.typed` marker), causing mypy to skip analysis of internal modules when type-checking test files that import from `auto_prd`.

The fix requires:
- **Keep** `$(PYTHON)` variable usage (already correct)
- **Remove** `--ignore-missing-imports` flag to expose all type errors
- **Add** `py.typed` marker file to enable proper typed package checking
- **Consider** adding mypy configuration to handle test files appropriately

## Current State Analysis

### Existing Implementation

**Makefile** (`/Users/simo/Projects/autodev/Makefile`):

- **Line 2**: `PYTHON := python3` - Variable definition (hardcoded to `python3` command)
- **Line 7**: `.PHONY` declaration includes `typecheck` and `typecheck-lenient`
- **Line 35**: `ci` target runs `typecheck-lenient` (non-blocking)
- **Lines 79-81**: `typecheck` target definition:
  ```makefile
  typecheck:
      @echo "🔎 Running type checks..."
      cd $(TOOLS_DIR) && $(PYTHON) -m mypy auto_prd/ --ignore-missing-imports
  ```
- **Lines 84-86**: `typecheck-lenient` target definition (ignores exit code):
  ```makefile
  typecheck-lenient:
      @echo "🔎 Running type checks (lenient mode)..."
      cd $(TOOLS_DIR) && $(PYTHON) -m mypy auto_prd/ --ignore-missing-imports || true
  ```

**Current behavior**:
- Both targets use `$(PYTHON)` variable ✓ (already following constraint)
- Both targets use `--ignore-missing-imports` flag ✗ (hides import errors)
- `typecheck-lenient` is used in CI and ignores failures via `|| true`

### Python Project Configuration

**`/Users/simo/Projects/autodev/tools/auto_prd/pyproject.toml`**:

- **Line 6**: `requires-python = ">=3.10"` - Project requires Python 3.10 or higher
- **Lines 17-20**: Supports Python 3.10, 3.11, 3.12, and 3.13
- **Lines 67-70**: Mypy override ignores test files completely:
  ```toml
  [[tool.mypy.overrides]]
  module = ["auto_prd.tests.*", "tests.*"]
  ignore_errors = true
  ```

**No mypy configuration file exists** (no `mypy.ini`, `.mypy.ini`, or `setup.cfg` with mypy section).

### Python Environment

**System Python installations**:
```
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 (3.13.2)
/usr/local/bin/python3 (3.13.2)
/usr/bin/python3 (3.9.6) - TOO OLD
```

**Project virtual environments**:
- `/Users/simo/Projects/autodev/tools/.venv/` - Python 3.13.7 (managed by uv 0.8.9)
- `/Users/simo/Projects/autodev/tools/auto_prd/.venv/` - Python 3.12.9 (managed by uv)

**Mypy installation**:
- Version 1.15.0 installed in system Python 3.13 at `/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/site-packages`
- **NOT installed** in `tools/.venv/`

### Type Check Error Analysis

**With `--ignore-missing-imports` flag (current)**:
- 22 type errors reported
- Categories: `var-annotated`, `attr-defined`, `operator`, `assignment`, `arg-type`, `misc`, `index`
- Example errors:
  - `auto_prd/task_completion_detector.py:57`: "object" has no attribute "append"
  - `auto_prd/ralph.py:46`: Incompatible types (float vs int)
  - `auto_prd/guardrails.py:464-466`: Sequence[str] vs str type mismatches

**Without `--ignore-missing-imports` flag**:
- 62 total type errors (40 additional errors)
- Additional errors include `import-untyped` for `tools.auto_prd` module:
  ```
  auto_prd/tests/test_task_completion_detector.py:3: error: Skipping analyzing "tools.auto_prd.task_completion_detector": module is installed, but missing library stubs or py.typed marker  [import-untyped]
  ```
- This indicates the package lacks the `py.typed` marker file

### CI Configuration

**`/.github/workflows/ci.yml`**:
- **Line 25**: CI uses Python 3.11 (`python-version: '3.11'`)
- **Line 37**: CI runs `make ci` which includes `typecheck-lenient`
- **Line 34**: Installs `uv` for Python dependency management

## Technical Considerations

### Dependencies

**External dependencies**:
- `mypy` 1.15.0 (type checker)
- Python 3.10+ (project requirement)

**Internal modules**:
- All type checking targets the `tools/auto_prd/` directory
- 39 Python source files in `tools/auto_prd/`
- Test files in `tools/auto_prd/tests/` and `tools/tests/`

### Patterns to Follow

**Existing Makefile patterns**:
- All Python-related targets `cd $(TOOLS_DIR)` before running commands
- Use `$(PYTHON)` variable for Python interpreter (already followed)
- Linting uses `ruff check auto_prd/` directly, not via python module
- Formatting uses `ruff format auto_prd/` directly

**Mypy best practices** (not currently followed):
- Typed packages should include a `py.typed` marker file
- Mypy configuration should be in `mypy.ini` or `pyproject.toml` [tool.mypy] section
- Test files can use separate mypy configuration

**Project conventions**:
- Uses `uv` for Python package management
- Has separate venvs: `tools/.venv/` (tools level) and `tools/auto_prd/.venv/` (package level)
- Tests configured to ignore type errors via `pyproject.toml:67-70`

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Removing `--ignore-missing-imports` exposes 40+ new type errors | **High** - CI will break if switched to strict mode | Keep `typecheck-lenient` for CI, use strict `typecheck` for local development; fix errors incrementally |
| System Python (3.13.2) differs from venv Python (3.13.7) | **Medium** - May type-check against wrong Python version | Install mypy in `tools/.venv/` and use venv's Python explicitly |
| Missing `py.typed` marker causes `import-untyped` errors | **Medium** - Package not recognized as typed | Add `py.typed` marker file to `tools/auto_prd/` package |
| CI uses Python 3.11 but dev uses 3.13 | **Low** - Type hints are compatible across 3.10+ | Python version differences unlikely to affect type checking |
| Test files already set to `ignore_errors = true` | **Low** - Test file type errors already suppressed | This configuration is appropriate and should remain |

## Recommended Approach

Based on research findings, the implementation should proceed in phases:

### Phase 1: Immediate Fixes (Required for this item)

1. **Verify $(PYTHON) variable is correct** - The Makefile already uses `$(PYTHON)`, so no change needed for this constraint. However, document that this resolves to the system `python3` which may differ from venv Python.

2. **Remove `--ignore-missing-imports` flag** from the `typecheck` target to expose all type errors. This will increase reported errors from 22 to 62, catching legitimate type issues.

3. **Add `py.typed` marker** to `tools/auto_prd/` directory to mark the package as typed, allowing mypy to properly analyze internal imports. Create empty file at `tools/auto_prd/py.typed`.

4. **Update `typecheck-lenient`** to keep `--ignore-missing-imports` for CI compatibility, ensuring CI continues to pass during the transition period.

**Resulting Makefile targets**:
```makefile
typecheck:
	@echo "🔎 Running type checks..."
	cd $(TOOLS_DIR) && $(PYTHON) -m mypy auto_prd/

typecheck-lenient:
	@echo "🔎 Running type checks (lenient mode)..."
	cd $(TOOLS_DIR) && $(PYTHON) -m mypy auto_prd/ --ignore-missing-imports || true
```

### Phase 2: Future Improvements (Out of scope for this item)

1. **Install mypy in project venv** - Add mypy to `tools/auto_prd/pyproject.toml` dev dependencies so it's installed via `uv`, ensuring version consistency.

2. **Create mypy.ini configuration** - Centralize mypy settings including:
   - `python_version = 3.10` (match project requirement)
   - `warn_return_any = True`
   - `warn_unused_configs = True`
   - Proper test file handling

3. **Fix type errors incrementally** - Address the 62 type errors revealed by strict checking, starting with high-impact issues like `attr-defined` and `operator` errors.

4. **Update CI to use strict typecheck** - Once type errors are resolved, switch CI from `typecheck-lenient` to `typecheck`.

### Implementation Order

For this item (018), implement only **Phase 1** steps:
1. Create `tools/auto_prd/py.typed` marker file
2. Remove `--ignore-missing-imports` from `typecheck` target in Makefile
3. Verify `typecheck` now reports all 62 errors
4. Ensure `typecheck-lenient` remains unchanged for CI
5. Run `make typecheck` and `make typecheck-lenient` to verify both targets work

## Open Questions

1. **Should mypy be installed in the project venv?** Currently it's installed in system Python. Installing via `uv` would ensure consistency but is out of scope for this item.

2. **Should we create a mypy.ini configuration file?** This would improve maintainability but is not required to fix the immediate issue.

3. **What is the timeline for fixing the 62 type errors?** This item only exposes them; a separate effort should track fixing them.

4. **Should CI eventually use strict typecheck?** Yes, but should wait until type errors are resolved to avoid blocking deployments.

5. **Why does `tools/.venv` use Python 3.13.7 while `tools/auto_prd/.venv` uses 3.12.9?** This may cause environment inconsistencies but is out of scope for this item.
