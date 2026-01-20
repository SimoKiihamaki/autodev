# Research: Add test coverage for critical security validation functions

**Date**: 2025-01-19
**Item**: 003-add-test-coverage-for-critical-security-validation

## Research Question
Security-critical code paths for shell injection prevention, path traversal prevention, and subprocess spawning are completely untested.

**Motivation:** Untested security code increases vulnerability risk. Comprehensive tests are needed to validate shell metacharacter rejection, path traversal attempts, and control character handling.

**Success criteria:**
- Test shell metacharacter rejection
- Test path traversal attempts
- Test control character handling
- Test safe command allowlist

**Technical constraints:**
- Create tools/auto_prd/tests/test_command_safety.py
- Test all four validation functions thoroughly

**Signals:** priority: critical

## Summary
The codebase has four critical security validation functions in `tools/auto_prd/command.py` that are currently undertested. While `test_cli_safety.py` exists and contains some tests for `validate_command_args`, there are NO dedicated tests for:
1. `validate_cwd()` - path traversal prevention (lines 208-215)
2. `validate_stdin()` - control character and size validation (lines 218-226)
3. `validate_extra_env()` - environment variable validation (lines 229-240)

The existing `ValidateCommandArgsTests` class in `test_cli_safety.py` has only 3 basic tests and doesn't comprehensively cover edge cases like:
- Empty command sequences
- Non-string arguments
- All shell metacharacters in UNSAFE_ARG_CHARS (`|`, `;`, `>`, `<`, `` ` ``)
- Command allowlist validation
- Absolute path validation for commands outside allowlist

A new test file `test_command_safety.py` should be created to provide comprehensive coverage of all four validation functions with thorough edge case testing, following the existing test patterns in the codebase.

## Current State Analysis

### Existing Implementation

The four validation functions are located in `/Users/simo/Projects/autodev/tools/auto_prd/command.py`:

1. **validate_command_args()** (lines 164-205):
   - Validates command is a non-empty sequence of strings
   - Checks for shell metacharacters: `|`, `;`, `>`, `<`, `` ` `` (from UNSAFE_ARG_CHARS)
   - Special case: backticks are allowed with a debug log (because shell=False prevents interpretation)
   - Validates binary is in COMMAND_ALLOWLIST or is an absolute path within SAFE_CWD_ROOTS
   - Raises: `ValueError`, `TypeError`, `SystemExit`

2. **validate_cwd()** (lines 208-215):
   - Ensures working directory is within SAFE_CWD_ROOTS
   - Uses `is_within()` helper to check path containment
   - Raises: `SystemExit`

3. **validate_stdin()** (lines 218-226):
   - Validates stdin size <= STDIN_MAX_BYTES (200,000 bytes)
   - Checks for unsafe control characters (bytes < 32 except tab, newline, carriage return)
   - Raises: `SystemExit`

4. **validate_extra_env()** (lines 229-240):
   - Validates env var keys and values are strings
   - Rejects newlines in keys or values
   - Raises: `SystemExit`

### Current Test Coverage

**Existing tests in `/Users/simo/Projects/autodev/tools/auto_prd/tests/test_cli_safety.py`:**
- `ValidateCommandArgsTests` class (lines 49-66):
  - `test_rejects_unsafe_arguments` - tests pipe character rejection
  - `test_allows_backticks` - tests backtick allowance
  - `test_accepts_scrubbed_arguments` - tests sanitized arguments pass

**Missing test coverage:**
- NO tests for `validate_cwd()`
- NO tests for `validate_stdin()`
- NO tests for `validate_extra_env()`
- Incomplete tests for `validate_command_args()`:
  - No tests for empty/invalid command sequences
  - No tests for non-string arguments
  - No tests for semicolon, greater-than, less-than characters
  - No tests for command allowlist enforcement
  - No tests for absolute path validation

### Key Files

- `/Users/simo/Projects/autodev/tools/auto_prd/command.py:164-240` - Four validation functions to test
- `/Users/simo/Projects/autodev/tools/auto_prd/constants.py:35-55` - Security constants:
  - `COMMAND_ALLOWLIST = {"codex", "coderabbit", "git", "gh", "zsh", "claude"}`
  - `UNSAFE_ARG_CHARS = set("|;><`")`
  - `STDIN_MAX_BYTES = 200_000`
  - `SAFE_STDIN_ALLOWED_CTRL = {9, 10, 13}` (tab, newline, carriage return)
  - `SAFE_CWD_ROOTS: set[Path]` - initialized to `tools/auto_prd` directory
- `/Users/simo/Projects/autodev/tools/auto_prd/tests/test_cli_safety.py:49-66` - Existing validation tests (incomplete)
- `/Users/simo/Projects/autodev/tools/auto_prd/tests/test_helpers.py:7-63` - `safe_import()` helper for imports
- `/Users/simo/Projects/autodev/tools/auto_prd/tests/test_prd_validation.py` - Example of path validation tests

## Technical Considerations

### Dependencies
- **pytest** (>=7.0) - test framework
- **unittest.mock** - for mocking Path objects and system calls
- **tempfile** - for creating temporary test directories
- **pathlib.Path** - for path manipulation in tests

### Internal modules to integrate with
- `tools.auto_prd.command` - the four validation functions
- `tools.auto_prd.constants` - security constants (COMMAND_ALLOWLIST, UNSAFE_ARG_CHARS, etc.)
- `tools.auto_prd.tests.test_helpers` - safe_import helper

### Patterns to Follow

**Import pattern** (from `test_cli_safety.py:19-28`):
```python
from .test_helpers import safe_import

validate_command_args = safe_import(
    "tools.auto_prd.command", "..command", "validate_command_args"
)
validate_cwd = safe_import("tools.auto_prd.command", "..command", "validate_cwd")
validate_stdin = safe_import("tools.auto_prd.command", "..command", "validate_stdin")
validate_extra_env = safe_import(
    "tools.auto_prd.command", "..command", "validate_extra_env"
)
register_safe_cwd = safe_import(
    "tools.auto_prd.command", "..command", "register_safe_cwd"
)
```

**Test class structure** (from `test_cli_safety.py:49`):
```python
class ValidateCommandArgsTests(TestCase):
    def test_rejects_unsafe_arguments(self) -> None:
        with self.assertRaises(ValueError):
            validate_command_args(["gh", "pr", "create", "--body", "contains | pipe"])
```

**Path validation pattern** (from `test_prd_validation.py:20-30`):
```python
def setUp(self) -> None:
    """Set up test environment with temporary directories."""
    self.temp_dir = tempfile.mkdtemp()
    self.parent_dir = Path(self.temp_dir)

def tearDown(self) -> None:
    """Clean up test environment."""
    import shutil
    shutil.rmtree(self.temp_dir, ignore_errors=True)
```

**Security constants import pattern** (from `test_cli_safety.py:19-21`):
```python
CLAUDE_DEBUG_LOG_NAME = safe_import(
    "tools.auto_prd.command", "..command", "CLAUDE_DEBUG_LOG_NAME"
)
```

### Test Naming Conventions
- Test classes: `<FunctionName>Tests` (e.g., `ValidateCommandArgsTests`)
- Test methods: `test_<scenario>_<expected_outcome>` (e.g., `test_rejects_unsafe_arguments`)
- Docstrings: Use triple quotes with descriptive text (seen in `test_prd_validation.py`)

### Error Assertion Patterns
- For exceptions: `with self.assertRaises(ExceptionType) as context:`
- Then check: `self.assertIn("expected message", str(context.exception))`
- For SystemExit: access `context.exception.code` for the exit message

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Tests may be too brittle if they depend on specific SAFE_CWD_ROOTS initialization | Medium | Use `register_safe_cwd()` in setUp to create predictable test environments |
| Path resolution behavior differs across operating systems (symlinks, case sensitivity) | Low | Focus on cross-platform path patterns; use `resolve()` consistently |
| Tests may mock incorrectly and not catch real security issues | High | Use integration-style tests where possible; validate actual behavior not just mocks |
| Coverage may give false sense of security if edge cases missed | High | Be exhaustive: test each unsafe char individually, boundary conditions, and error paths |
| Test file may become too large and hard to maintain | Medium | Organize into separate test class per validation function; use descriptive names |

## Recommended Approach

### High-Level Strategy
Create `tools/auto_prd/tests/test_command_safety.py` with four test class groups, one per validation function:

1. **ValidateCommandArgsTests** - Comprehensive shell metacharacter and allowlist testing
2. **ValidateCwdTests** - Path traversal prevention testing
3. **ValidateStdinTests** - Control character and size limit testing
4. **ValidateExtraEnvTests** - Environment variable validation testing

### Test Organization

```python
"""Comprehensive tests for security-critical command validation functions."""

import tempfile
from pathlib import Path
from unittest import TestCase, main

from .test_helpers import safe_import

# Import all validation functions and constants
validate_command_args = safe_import(...)
validate_cwd = safe_import(...)
validate_stdin = safe_import(...)
validate_extra_env = safe_import(...)
register_safe_cwd = safe_import(...)
COMMAND_ALLOWLIST = safe_import("tools.auto_prd.constants", "..constants", "COMMAND_ALLOWLIST")
UNSAFE_ARG_CHARS = safe_import("tools.auto_prd.constants", "..constants", "UNSAFE_ARG_CHARS")
STDIN_MAX_BYTES = safe_import("tools.auto_prd.constants", "..constants", "STDIN_MAX_BYTES")
SAFE_STDIN_ALLOWED_CTRL = safe_import("tools.auto_prd.constants", "..constants", "SAFE_STDIN_ALLOWED_CTRL")

class ValidateCommandArgsTests(TestCase):
    """Test suite for validate_command_args function."""

    # Group 1: Input validation tests
    # Group 2: Shell metacharacter rejection tests (one test per character)
    # Group 3: Command allowlist tests
    # Group 4: Absolute path validation tests

class ValidateCwdTests(TestCase):
    """Test suite for validate_cwd function."""

    # Group 1: None acceptance tests
    # Group 2: Safe path acceptance tests
    # Group 3: Path traversal rejection tests
    # Group 4: Edge cases (symlinks, non-existent paths)

class ValidateStdinTests(TestCase):
    """Test suite for validate_stdin function."""

    # Group 1: None acceptance tests
    # Group 2: Size limit tests (boundary, over limit)
    # Group 3: Control character tests (each disallowed char, each allowed char)

class ValidateExtraEnvTests(TestCase):
    """Test suite for validate_extra_env function."""

    # Group 1: None/empty dict acceptance tests
    # Group 2: Type validation tests
    # Group 3: Newline rejection tests
    # Group 4: Valid environment variable tests
```

### Specific Test Cases to Implement

**ValidateCommandArgsTests:**
1. `test_rejects_empty_sequence` - empty list raises ValueError
2. `test_rejects_string_instead_of_list` - string raises ValueError (not a sequence)
3. `test_rejects_bytes_argument` - bytes element raises TypeError
4. `test_rejects_integer_argument` - int element raises TypeError
5. `test_rejects_pipe_character` - `|` raises ValueError
6. `test_rejects_semicolon_character` - `;` raises ValueError
7. `test_rejects_greater_than_character` - `>` raises ValueError
8. `test_rejects_less_than_character` - `<` raises ValueError
9. `test_allows_backtick_character` - `` ` `` passes (special case)
10. `test_allows_multiple_backticks` - multiple `` ` `` pass
11. `test_rejects_mixed_unsafe_characters` - combination of unsafe chars raises ValueError
12. `test_allows_allowlisted_command` - commands in COMMAND_ALLOWLIST pass
13. `test_allows_allowlisted_command_with_args` - allowlisted with safe args pass
14. `test_rejects_non_allowlisted_command` - commands not in allowlist raise SystemExit
15. `test_allows_absolute_path_within_safe_root` - absolute paths in SAFE_CWD_ROOTS pass
16. `test_rejects_absolute_path_outside_safe_root` - absolute paths outside raise SystemExit
17. `test_rejects_nonexistent_absolute_path_outside_root` - non-existent paths outside raise SystemExit

**ValidateCwdTests:**
1. `test_accepts_none` - None passes (no cwd specified)
2. `test_accepts_cwd_within_safe_roots` - path within registered roots passes
3. `test_accepts_cwd_equal_to_safe_root` - path equal to safe root passes
4. `test_accepts_nested_subdirectory` - deeply nested path within root passes
5. `test_rejects_cwd_outside_safe_roots` - path outside roots raises SystemExit
6. `test_rejects_path_traversal_with_dot_dot` - `../` escaping attempt raises SystemExit
7. `test_rejects_absolute_path_outside_roots` - absolute path outside raises SystemExit
8. `test_resolves_symlinks_within_root` - symlinks within root are handled correctly

**ValidateStdinTests:**
1. `test_accepts_none` - None passes (no stdin)
2. `test_accepts_empty_string` - empty string passes
3. `test_accepts_safe_ascii_text` - normal text passes
4. `test_accepts_safe_size_at_limit` - exactly STDIN_MAX_BYTES passes
5. `test_rejects_payload_over_limit` - STDIN_MAX_BYTES + 1 raises SystemExit
6. `test_accepts_tab_character` - `\t` (byte 9) passes
7. `test_accepts_newline_character` - `\n` (byte 10) passes
8. `test_accepts_carriage_return_character` - `\r` (byte 13) passes
9. `test_rejects_null_byte` - `\0` (byte 0) raises SystemExit
10. `test_rejects_control_char_1` - byte 1 raises SystemExit
11. `test_rejects_control_char_2` - byte 2 raises SystemExit
12. `test_rejects_control_char_3` - byte 3 raises SystemExit
13. `test_rejects_control_char_4` - byte 4 raises SystemExit
14. `test_rejects_control_char_5` - byte 5 raises SystemExit
15. `test_rejects_control_char_6` - byte 6 raises SystemExit
16. `test_rejects_control_char_7` - byte 7 raises SystemExit
17. `test_rejects_control_char_8` - byte 8 raises SystemExit
18. `test_rejects_control_chars_11_12` - bytes 11-12 raise SystemExit
19. `test_rejects_control_chars_14_31` - bytes 14-31 raise SystemExit
20. `test_rejects_mixed_control_characters` - mix of disallowed ctrl chars raises SystemExit

**ValidateExtraEnvTests:**
1. `test_accepts_none` - None passes (no extra env)
2. `test_accepts_empty_dict` - empty dict passes
3. `test_accepts_valid_string_key_value` - string key and value pass
4. `test_accepts_multiple_valid_env_vars` - multiple valid vars pass
5. `test_rejects_integer_key` - int key raises SystemExit
6. `test_rejects_integer_value` - int value raises SystemExit
7. `test_rejects_none_key` - None key raises SystemExit
8. `test_rejects_none_value` - None value raises SystemExit
9. `test_rejects_newline_in_key` - key with `\n` raises SystemExit
10. `test_rejects_newline_in_value` - value with `\n` raises SystemExit
11. `test_rejects_newline_in_both` - `\n` in both raises SystemExit
12. `test_accepts_special_characters_in_value` - special chars (except `\n`) in value pass

### Implementation Notes

1. **Use setUp/tearDown** for temp directory management (follow `test_prd_validation.py:20-30` pattern)
2. **Register safe CWDs** using `register_safe_cwd()` in setUp for predictable test environments
3. **Mock Path operations** carefully - prefer real temp directories over mocks for path tests
4. **Test boundary conditions** explicitly (e.g., exactly at byte limit, just over limit)
5. **Test each unsafe character individually** for clarity and easier debugging
6. **Use descriptive assertion messages** when the default isn't clear enough
7. **Import constants** using safe_import to avoid hardcoding values in tests
8. **Follow existing naming conventions** for consistency with the rest of the test suite

## Open Questions

1. **Should tests import COMMAND_ALLOWLIST and other constants directly?**
   - Yes, use safe_import to import constants from constants.py
   - This avoids hardcoding values and keeps tests in sync with implementation

2. **Should we test the interaction between validation functions?**
   - No, focus on unit tests for each function independently
   - Integration tests for run_cmd/popen_streaming already exist in test_cli_safety.py

3. **How to handle OS-specific path behavior in tests?**
   - Use pathlib.Path.resolve() consistently
   - Focus on cross-platform patterns
   - Skip tests for OS-specific features (like symlinks) if not supported

4. **Should we test the is_within() helper function separately?**
   - It's already tested indirectly through validate_cwd() tests
   - No need for separate tests unless behavior becomes more complex

5. **What about testing the register_safe_cwd() function?**
   - It's a test helper function, not security-critical
   - No need for dedicated tests; it's used within other tests

6. **Should we add property-based tests (hypothesis)?**
   - Not in scope for this task
   - The existing test suite doesn't use property-based testing
   - Manual edge case coverage is sufficient for these validators
