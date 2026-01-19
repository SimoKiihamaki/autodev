# Add test coverage for critical security validation functions Implementation Plan

## Overview
Create comprehensive test coverage for four security-critical validation functions in `tools/auto_prd/command.py` that prevent shell injection, path traversal, and subprocess vulnerabilities. Currently, only `validate_command_args()` has minimal tests (3 basic cases), while `validate_cwd()`, `validate_stdin()`, and `validate_extra_env()` have **zero** dedicated test coverage.

## Current State Analysis

### Existing Implementation
Four validation functions located at `/Users/simo/Projects/autodev/tools/auto_prd/command.py`:

1. **validate_command_args()** (lines 164-205):
   - Validates command is non-empty sequence of strings
   - Checks for shell metacharacters in UNSAFE_ARG_CHARS: `|`, `;`, `>`, `<`, `` ` ``
   - Special case: backticks allowed with debug log (shell=False prevents interpretation)
   - Validates binary is in COMMAND_ALLOWLIST or absolute path within SAFE_CWD_ROOTS
   - Raises: `ValueError`, `TypeError`, `SystemExit`

2. **validate_cwd()** (lines 208-215):
   - Ensures working directory is within SAFE_CWD_ROOTS
   - Uses `is_within()` helper to check path containment
   - Raises: `SystemExit`

3. **validate_stdin()** (lines 218-226):
   - Validates stdin size ≤ STDIN_MAX_BYTES (200,000 bytes)
   - Checks for unsafe control characters (bytes < 32 except tab=9, newline=10, carriage return=13)
   - Raises: `SystemExit`

4. **validate_extra_env()** (lines 229-240):
   - Validates env var keys and values are strings
   - Rejects newlines in keys or values
   - Raises: `SystemExit`

### Current Test Coverage
**File:** `/Users/simo/Projects/autodev/tools/auto_prd/tests/test_cli_safety.py`

Only `ValidateCommandArgsTests` class exists (lines 49-66) with 3 tests:
- `test_rejects_unsafe_arguments` - tests pipe character rejection
- `test_allows_backticks` - tests backtick allowance
- `test_accepts_scrubbed_arguments` - tests sanitized arguments pass

**Missing coverage:**
- NO tests for `validate_cwd()`
- NO tests for `validate_stdin()`
- NO tests for `validate_extra_env()`
- Incomplete tests for `validate_command_args()`:
  - No tests for empty/invalid command sequences
  - No tests for non-string arguments
  - No tests for semicolon, greater-than, less-than characters
  - No tests for command allowlist enforcement
  - No tests for absolute path validation

### Key Security Constants
**File:** `/Users/simo/Projects/autodev/tools/auto_prd/constants.py` (lines 35-55)

- `COMMAND_ALLOWLIST = {"codex", "coderabbit", "git", "gh", "zsh", "claude"}`
- `UNSAFE_ARG_CHARS = set("|;><`")` (backtick is special case - allowed)
- `STDIN_MAX_BYTES = 200_000`
- `SAFE_STDIN_ALLOWED_CTRL = {9, 10, 13}` (tab, newline, carriage return)
- `SAFE_CWD_ROOTS: set[Path]` - initialized to `tools/auto_prd` directory

### Existing Test Patterns to Follow

**Import pattern** (from `test_cli_safety.py:19-32`):
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

**Constants import pattern:**
```python
COMMAND_ALLOWLIST = safe_import("tools.auto_prd.constants", "..constants", "COMMAND_ALLOWLIST")
UNSAFE_ARG_CHARS = safe_import("tools.auto_prd.constants", "..constants", "UNSAFE_ARG_CHARS")
STDIN_MAX_BYTES = safe_import("tools.auto_prd.constants", "..constants", "STDIN_MAX_BYTES")
SAFE_STDIN_ALLOWED_CTRL = safe_import("tools.auto_prd.constants", "..constants", "SAFE_STDIN_ALLOWED_CTRL")
```

**Test class structure:**
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

## Desired End State

### Specification
Create `/Users/simo/Projects/autodev/tools/auto_prd/tests/test_command_safety.py` with:

1. **ValidateCommandArgsTests** - 17 comprehensive tests covering:
   - Input validation (empty sequences, non-sequences, non-string arguments)
   - Shell metacharacter rejection (individual tests for `|`, `;`, `>`, `<`)
   - Backtick allowance (single and multiple)
   - Command allowlist enforcement
   - Absolute path validation within/outside SAFE_CWD_ROOTS

2. **ValidateCwdTests** - 8 tests covering:
   - None acceptance
   - Safe path acceptance (within roots, equal to root, nested subdirectories)
   - Path traversal rejection (dot-dot escaping, absolute paths outside roots)
   - Symlink handling within roots

3. **ValidateStdinTests** - 20 tests covering:
   - None and empty string acceptance
   - Size limit validation (at boundary, over limit)
   - Control character validation (each allowed/disallowed char individually)
   - Mixed control character rejection

4. **ValidateExtraEnvTests** - 12 tests covering:
   - None and empty dict acceptance
   - Type validation (non-string keys/values)
   - Newline rejection in keys/values
   - Valid environment variable acceptance

### Verification Criteria
- All new tests pass when run with `pytest tools/auto_prd/tests/test_command_safety.py`
- Test coverage for the four validation functions increases from ~15% to >95%
- No regressions in existing test suite
- Tests are maintainable, well-documented, and follow existing patterns

### Key Discoveries:
- **Line 182 in command.py**: `validate_command_args()` checks `isinstance(cmd, str | bytes)` to reject strings/bytes - must test this explicitly
- **Lines 190-195 in command.py**: Backticks are special-cased - allowed but logged - must verify this behavior
- **Line 202 in command.py**: Absolute paths must `exist()` to pass validation - critical for testing
- **Line 211 in command.py**: `validate_cwd()` resolves paths before checking - tests should use resolved paths
- **Lines 224-226 in command.py**: Control character check is byte-by-byte - must test each byte value individually
- **Line 232 in command.py**: `validate_extra_env()` uses `isinstance(key, str)` - must test non-string types

## What We're NOT Doing

- **NOT modifying the validation functions themselves** - only adding tests
- **NOT testing the helper functions** (`register_safe_cwd()`, `is_within()`) except indirectly through the validation function tests
- **NOT adding integration tests** - the existing `test_cli_safety.py` already has integration tests for `run_cmd()` and `popen_streaming()`
- **NOT adding property-based tests** (e.g., using Hypothesis) - not used elsewhere in the test suite
- **NOT testing `verify_unsafe_execution_ready()` or `env_with_zsh()`** - these are separate concerns

## Implementation Approach

### High-Level Strategy
Create a single new test file `test_command_safety.py` with four test class groups, one per validation function. This approach:

- **Maintains clear separation of concerns** - each test class focuses on one function
- **Follows existing patterns** - similar structure to `test_cli_safety.py`
- **Makes tests maintainable** - easy to find and update tests for specific functions
- **Enables incremental development** - can implement and verify each test class independently

### Why This Approach?

1. **Single test file** is preferred over splitting into multiple files because:
   - The four validation functions are closely related (all security validators)
   - They share imports and test helpers
   - Easier to run all safety tests together: `pytest test_command_safety.py`

2. **Using setUp/tearDown** for temp directories (not pytest fixtures) because:
   - Existing test suite uses unittest.TestCase pattern
   - Consistent with `test_prd_validation.py` and `test_cli_safety.py`
   - No need to introduce pytest dependencies

3. **Testing each unsafe character individually** (not one big test) because:
   - Clearer failure messages when a specific character test fails
   - Easier to add coverage for new unsafe characters
   - Documents security boundaries explicitly

4. **Using real temp directories** (not mocks) for path tests because:
   - More authentic testing - catches real filesystem behavior
   - `is_within()` uses `Path.resolve(strict=True)` which has real filesystem behavior
   - Existing tests use this pattern (see `test_cli_safety.py:73-83`)

---

## Phase 1: Create Test File Structure and Imports

### Overview
Set up the basic test file structure with all necessary imports and helper functions. This creates the foundation for the four test classes.

### Changes Required:

#### 1. Create test file with imports and setup
**File**: `/Users/simo/Projects/autodev/tools/auto_prd/tests/test_command_safety.py`
**Changes**: Create new file with:

```python
"""Comprehensive tests for security-critical command validation functions.

This test module provides thorough coverage for the four validation functions
in command.py that prevent shell injection, path traversal, and subprocess
vulnerabilities:
- validate_command_args: Shell metacharacter and command allowlist validation
- validate_cwd: Path traversal prevention
- validate_stdin: Control character and size validation
- validate_extra_env: Environment variable validation
"""

import tempfile
from pathlib import Path
from unittest import TestCase, main

from .test_helpers import safe_import

# Import validation functions
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

# Import security constants for testing
COMMAND_ALLOWLIST = safe_import(
    "tools.auto_prd.constants", "..constants", "COMMAND_ALLOWLIST"
)
UNSAFE_ARG_CHARS = safe_import(
    "tools.auto_prd.constants", "..constants", "UNSAFE_ARG_CHARS"
)
STDIN_MAX_BYTES = safe_import(
    "tools.auto_prd.constants", "..constants", "STDIN_MAX_BYTES"
)
SAFE_STDIN_ALLOWED_CTRL = safe_import(
    "tools.auto_prd.constants", "..constants", "SAFE_STDIN_ALLOWED_CTRL"
)


class ValidateCommandArgsTests(TestCase):
    """Test suite for validate_command_args function."""

    # Tests will be added in Phase 2


class ValidateCwdTests(TestCase):
    """Test suite for validate_cwd function."""

    # Tests will be added in Phase 3


class ValidateStdinTests(TestCase):
    """Test suite for validate_stdin function."""

    # Tests will be added in Phase 4


class ValidateExtraEnvTests(TestCase):
    """Test suite for validate_extra_env function."""

    # Tests will be added in Phase 5


if __name__ == "__main__":
    main()
```

### Success Criteria:

#### Automated Verification:
- [ ] File created at correct path: `/Users/simo/Projects/autodev/tools/auto_prd/tests/test_command_safety.py`
- [ ] File imports successfully: `python -m tools.auto_prd.tests.test_command_safety`
- [ ] All four test class definitions exist (can be inspected with dir())
- [ ] All validation functions imported successfully (no ImportError)

#### Manual Verification:
- [ ] File structure matches existing test files (similar imports pattern to test_cli_safety.py)
- [ ] Docstring clearly explains the purpose of the test module
- [ ] Test class names follow convention: `<FunctionName>Tests`

**Note**: Complete all automated verification, then pause for manual confirmation before proceeding to next phase.

---

## Phase 2: Implement ValidateCommandArgsTests

### Overview
Add comprehensive tests for `validate_command_args()` covering input validation, shell metacharacter rejection, backtick allowance, command allowlist enforcement, and absolute path validation.

### Changes Required:

#### 1. Add test methods to ValidateCommandArgsTests class
**File**: `/Users/simo/Projects/autodev/tools/auto_prd/tests/test_command_safety.py`
**Changes**: Add test methods to the empty class:

```python
class ValidateCommandArgsTests(TestCase):
    """Test suite for validate_command_args function."""

    def setUp(self) -> None:
        """Set up test environment with temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        register_safe_cwd(self.temp_path)

    def tearDown(self) -> None:
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # Input validation tests
    def test_rejects_empty_sequence(self) -> None:
        """Test that empty command list raises ValueError."""
        with self.assertRaises(ValueError) as context:
            validate_command_args([])
        self.assertIn("non-empty sequence", str(context.exception))

    def test_rejects_string_instead_of_list(self) -> None:
        """Test that string command raises ValueError (not a sequence)."""
        with self.assertRaises(ValueError) as context:
            validate_command_args("git status")  # type: ignore
        self.assertIn("non-empty sequence", str(context.exception))

    def test_rejects_bytes_argument(self) -> None:
        """Test that bytes element raises TypeError."""
        with self.assertRaises(TypeError) as context:
            validate_command_args(["git", b"status"])
        self.assertIn("must be strings", str(context.exception))

    def test_rejects_integer_argument(self) -> None:
        """Test that integer element raises TypeError."""
        with self.assertRaises(TypeError) as context:
            validate_command_args(["git", 123])
        self.assertIn("must be strings", str(context.exception))

    # Shell metacharacter rejection tests (one per character)
    def test_rejects_pipe_character(self) -> None:
        """Test that pipe character | raises ValueError."""
        with self.assertRaises(ValueError) as context:
            validate_command_args(["echo", "foo|bar"])
        self.assertIn("unsafe shell metacharacters", str(context.exception))
        self.assertIn("|", str(context.exception))

    def test_rejects_semicolon_character(self) -> None:
        """Test that semicolon character ; raises ValueError."""
        with self.assertRaises(ValueError) as context:
            validate_command_args(["echo", "foo;bar"])
        self.assertIn("unsafe shell metacharacters", str(context.exception))
        self.assertIn(";", str(context.exception))

    def test_rejects_greater_than_character(self) -> None:
        """Test that greater-than character > raises ValueError."""
        with self.assertRaises(ValueError) as context:
            validate_command_args(["echo", "foo>bar"])
        self.assertIn("unsafe shell metacharacters", str(context.exception))
        self.assertIn(">", str(context.exception))

    def test_rejects_less_than_character(self) -> None:
        """Test that less-than character < raises ValueError."""
        with self.assertRaises(ValueError) as context:
            validate_command_args(["echo", "foo<bar"])
        self.assertIn("unsafe shell metacharacters", str(context.exception))
        self.assertIn("<", str(context.exception))

    # Backtick allowance tests (special case)
    def test_allows_backtick_character(self) -> None:
        """Test that backtick character ` is allowed (special case)."""
        try:
            validate_command_args(["echo", "foo`bar"])
        except ValueError as exc:
            self.fail(f"validate_command_args unexpectedly rejected backticks: {exc}")

    def test_allows_multiple_backticks(self) -> None:
        """Test that multiple backticks are allowed."""
        try:
            validate_command_args(["echo", "`foo` `bar`"])
        except ValueError as exc:
            self.fail(f"validate_command_args unexpectedly rejected multiple backticks: {exc}")

    def test_rejects_mixed_unsafe_characters(self) -> None:
        """Test that combination of unsafe characters raises ValueError."""
        with self.assertRaises(ValueError) as context:
            validate_command_args(["echo", "foo|bar;baz"])
        self.assertIn("unsafe shell metacharacters", str(context.exception))

    # Command allowlist tests
    def test_allows_allowlisted_command(self) -> None:
        """Test that commands in COMMAND_ALLOWLIST pass."""
        for cmd in COMMAND_ALLOWLIST:
            try:
                validate_command_args([cmd])
            except (ValueError, SystemExit) as exc:
                self.fail(f"validate_command_args rejected allowlisted command '{cmd}': {exc}")

    def test_allows_allowlisted_command_with_args(self) -> None:
        """Test that allowlisted commands with safe arguments pass."""
        try:
            validate_command_args(["git", "status"])
            validate_command_args(["gh", "pr", "list"])
        except (ValueError, SystemExit) as exc:
            self.fail(f"validate_command_args rejected safe allowlisted command: {exc}")

    def test_rejects_non_allowlisted_command(self) -> None:
        """Test that commands not in allowlist raise SystemExit."""
        with self.assertRaises(SystemExit) as context:
            validate_command_args(["rm", "-rf", "/"])
        self.assertIn("Command not allowed", str(context.exception.code))
        self.assertIn("rm", str(context.exception.code))

    # Absolute path validation tests
    def test_allows_absolute_path_within_safe_root(self) -> None:
        """Test that absolute paths within SAFE_CWD_ROOTS pass."""
        # Create a test executable within the safe root
        test_script = self.temp_path / "test_script.sh"
        test_script.write_text("#!/bin/sh\necho test", encoding="utf-8")
        test_script.chmod(0o755)

        try:
            validate_command_args([str(test_script)])
        except (ValueError, SystemExit) as exc:
            self.fail(f"validate_command_args rejected absolute path within safe root: {exc}")

    def test_rejects_absolute_path_outside_safe_root(self) -> None:
        """Test that absolute paths outside SAFE_CWD_ROOTS raise SystemExit."""
        # Use /usr/bin/ls which exists but is outside our temp safe root
        with self.assertRaises(SystemExit) as context:
            validate_command_args(["/usr/bin/ls"])
        self.assertIn("Command not allowed", str(context.exception.code))

    def test_rejects_nonexistent_absolute_path_outside_root(self) -> None:
        """Test that non-existent absolute paths outside roots raise SystemExit."""
        with self.assertRaises(SystemExit) as context:
            validate_command_args(["/nonexistent/path/to/command"])
        self.assertIn("Command not allowed", str(context.exception.code))
```

### Success Criteria:

#### Automated Verification:
- [ ] All 17 tests in ValidateCommandArgsTests pass
- [ ] Test run: `pytest tools/auto_prd/tests/test_command_safety.py::ValidateCommandArgsTests -v`
- [ ] Coverage for `validate_command_args()` increases significantly

#### Manual Verification:
- [ ] Each shell metacharacter (`|`, `;`, `>`, `<`) is tested individually
- [ ] Backtick special case is tested (single and multiple)
- [ ] Input validation edge cases are covered (empty, non-sequence, non-string)
- [ ] Command allowlist enforcement is tested
- [ ] Absolute path validation is tested with real temp directory
- [ ] Error messages are specific and helpful

**Note**: Complete all automated verification, then pause for manual confirmation before proceeding to next phase.

---

## Phase 3: Implement ValidateCwdTests

### Overview
Add comprehensive tests for `validate_cwd()` covering None acceptance, safe path acceptance, path traversal rejection, and symlink handling.

### Changes Required:

#### 1. Add test methods to ValidateCwdTests class
**File**: `/Users/simo/Projects/autodev/tools/auto_prd/tests/test_command_safety.py`
**Changes**: Add test methods to the empty class:

```python
class ValidateCwdTests(TestCase):
    """Test suite for validate_cwd function."""

    def setUp(self) -> None:
        """Set up test environment with temporary directories."""
        self.temp_dir = tempfile.mkdtemp()
        self.safe_root = Path(self.temp_dir) / "safe_root"
        self.safe_root.mkdir()
        self.unsafe_dir = Path(self.temp_dir) / "unsafe_dir"
        self.unsafe_dir.mkdir()
        register_safe_cwd(self.safe_root)

    def tearDown(self) -> None:
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # None acceptance tests
    def test_accepts_none(self) -> None:
        """Test that None passes (no cwd specified)."""
        try:
            validate_cwd(None)
        except SystemExit as exc:
            self.fail(f"validate_cwd rejected None: {exc}")

    # Safe path acceptance tests
    def test_accepts_cwd_within_safe_roots(self) -> None:
        """Test that path within registered safe roots passes."""
        subdir = self.safe_root / "subdir"
        subdir.mkdir()
        try:
            validate_cwd(subdir)
        except SystemExit as exc:
            self.fail(f"validate_cwd rejected path within safe roots: {exc}")

    def test_accepts_cwd_equal_to_safe_root(self) -> None:
        """Test that path equal to safe root passes."""
        try:
            validate_cwd(self.safe_root)
        except SystemExit as exc:
            self.fail(f"validate_cwd rejected path equal to safe root: {exc}")

    def test_accepts_nested_subdirectory(self) -> None:
        """Test that deeply nested path within root passes."""
        nested = self.safe_root / "a" / "b" / "c" / "d"
        nested.mkdir(parents=True)
        try:
            validate_cwd(nested)
        except SystemExit as exc:
            self.fail(f"validate_cwd rejected nested subdirectory: {exc}")

    # Path traversal rejection tests
    def test_rejects_cwd_outside_safe_roots(self) -> None:
        """Test that path outside safe roots raises SystemExit."""
        with self.assertRaises(SystemExit) as context:
            validate_cwd(self.unsafe_dir)
        self.assertIn("outside registered safe roots", str(context.exception.code))

    def test_rejects_path_traversal_with_dot_dot(self) -> None:
        """Test that ../ escaping attempt raises SystemExit."""
        # Create a path that tries to escape using .. (even if resolved)
        escape_path = self.safe_root / ".." / "unsafe_dir"
        with self.assertRaises(SystemExit) as context:
            validate_cwd(escape_path)
        self.assertIn("outside registered safe roots", str(context.exception.code))

    def test_rejects_absolute_path_outside_roots(self) -> None:
        """Test that absolute path outside roots raises SystemExit."""
        with self.assertRaises(SystemExit) as context:
            validate_cwd(Path("/tmp"))
        self.assertIn("outside registered safe roots", str(context.exception.code))

    # Symlink handling tests
    def test_resolves_symlinks_within_root(self) -> None:
        """Test that symlinks within root are handled correctly."""
        # Create a symlink within the safe root
        link_target = self.safe_root / "target"
        link_target.mkdir()
        symlink = self.safe_root / "link"
        try:
            symlink.symlink_to(link_target)
        except OSError:
            # Symlinks not supported on this platform, skip test
            self.skipTest("Symlinks not supported on this platform")

        try:
            validate_cwd(symlink)
        except SystemExit as exc:
            self.fail(f"validate_cwd rejected symlink within safe root: {exc}")
```

### Success Criteria:

#### Automated Verification:
- [ ] All 8 tests in ValidateCwdTests pass
- [ ] Test run: `pytest tools/auto_prd/tests/test_command_safety.py::ValidateCwdTests -v`
- [ ] Coverage for `validate_cwd()` reaches >95%

#### Manual Verification:
- [ ] None acceptance is tested
- [ ] Safe paths (within roots, equal to root, nested) are tested
- [ ] Path traversal attempts (.., outside roots) are rejected
- [ ] Symlink handling is tested with platform-aware skip
- [ ] Real temp directories are used (not mocks)
- [ ] Error messages mention "outside registered safe roots"

**Note**: Complete all automated verification, then pause for manual confirmation before proceeding to next phase.

---

## Phase 4: Implement ValidateStdinTests

### Overview
Add comprehensive tests for `validate_stdin()` covering None acceptance, size limit validation, and control character validation (testing each allowed/disallowed character individually).

### Changes Required:

#### 1. Add test methods to ValidateStdinTests class
**File**: `/Users/simo/Projects/autodev/tools/auto_prd/tests/test_command_safety.py`
**Changes**: Add test methods to the empty class:

```python
class ValidateStdinTests(TestCase):
    """Test suite for validate_stdin function."""

    # None and empty string acceptance tests
    def test_accepts_none(self) -> None:
        """Test that None passes (no stdin)."""
        try:
            validate_stdin(None)
        except SystemExit as exc:
            self.fail(f"validate_stdin rejected None: {exc}")

    def test_accepts_empty_string(self) -> None:
        """Test that empty string passes."""
        try:
            validate_stdin("")
        except SystemExit as exc:
            self.fail(f"validate_stdin rejected empty string: {exc}")

    def test_accepts_safe_ascii_text(self) -> None:
        """Test that normal ASCII text passes."""
        try:
            validate_stdin("Hello, World!")
        except SystemExit as exc:
            self.fail(f"validate_stdin rejected safe ASCII text: {exc}")

    # Size limit tests
    def test_accepts_safe_size_at_limit(self) -> None:
        """Test that stdin at exactly STDIN_MAX_BYTES passes."""
        # Create a string that's exactly STDIN_MAX_BYTES when encoded
        safe_input = "a" * STDIN_MAX_BYTES
        try:
            validate_stdin(safe_input)
        except SystemExit as exc:
            self.fail(f"validate_stdin rejected input at byte limit: {exc}")

    def test_rejects_payload_over_limit(self) -> None:
        """Test that STDIN_MAX_BYTES + 1 raises SystemExit."""
        # Create a string that's one byte over the limit
        oversized_input = "a" * (STDIN_MAX_BYTES + 1)
        with self.assertRaises(SystemExit) as context:
            validate_stdin(oversized_input)
        self.assertIn("too large", str(context.exception.code))

    # Control character tests - allowed chars
    def test_accepts_tab_character(self) -> None:
        """Test that tab character \\t (byte 9) passes."""
        try:
            validate_stdin("hello\tworld")
        except SystemExit as exc:
            self.fail(f"validate_stdin rejected tab character: {exc}")

    def test_accepts_newline_character(self) -> None:
        """Test that newline character \\n (byte 10) passes."""
        try:
            validate_stdin("hello\nworld")
        except SystemExit as exc:
            self.fail(f"validate_stdin rejected newline character: {exc}")

    def test_accepts_carriage_return_character(self) -> None:
        """Test that carriage return character \\r (byte 13) passes."""
        try:
            validate_stdin("hello\rworld")
        except SystemExit as exc:
            self.fail(f"validate_stdin rejected carriage return character: {exc}")

    # Control character tests - disallowed chars (individual tests for clarity)
    def test_rejects_null_byte(self) -> None:
        """Test that null byte \\0 (byte 0) raises SystemExit."""
        with self.assertRaises(SystemExit) as context:
            validate_stdin("hello\x00world")
        self.assertIn("unsafe control characters", str(context.exception.code))

    def test_rejects_control_char_1(self) -> None:
        """Test that byte 1 raises SystemExit."""
        with self.assertRaises(SystemExit) as context:
            validate_stdin("hello\x01world")
        self.assertIn("unsafe control characters", str(context.exception.code))

    def test_rejects_control_char_2(self) -> None:
        """Test that byte 2 raises SystemExit."""
        with self.assertRaises(SystemExit) as context:
            validate_stdin("hello\x02world")
        self.assertIn("unsafe control characters", str(context.exception.code))

    def test_rejects_control_char_3(self) -> None:
        """Test that byte 3 raises SystemExit."""
        with self.assertRaises(SystemExit) as context:
            validate_stdin("hello\x03world")
        self.assertIn("unsafe control characters", str(context.exception.code))

    def test_rejects_control_char_4(self) -> None:
        """Test that byte 4 raises SystemExit."""
        with self.assertRaises(SystemExit) as context:
            validate_stdin("hello\x04world")
        self.assertIn("unsafe control characters", str(context.exception.code))

    def test_rejects_control_char_5(self) -> None:
        """Test that byte 5 raises SystemExit."""
        with self.assertRaises(SystemExit) as context:
            validate_stdin("hello\x05world")
        self.assertIn("unsafe control characters", str(context.exception.code))

    def test_rejects_control_char_6(self) -> None:
        """Test that byte 6 raises SystemExit."""
        with self.assertRaises(SystemExit) as context:
            validate_stdin("hello\x06world")
        self.assertIn("unsafe control characters", str(context.exception.code))

    def test_rejects_control_char_7(self) -> None:
        """Test that byte 7 raises SystemExit."""
        with self.assertRaises(SystemExit) as context:
            validate_stdin("hello\x07world")
        self.assertIn("unsafe control characters", str(context.exception.code))

    def test_rejects_control_char_8(self) -> None:
        """Test that byte 8 raises SystemExit."""
        with self.assertRaises(SystemExit) as context:
            validate_stdin("hello\x08world")
        self.assertIn("unsafe control characters", str(context.exception.code))

    def test_rejects_control_chars_11_12(self) -> None:
        """Test that bytes 11-12 raise SystemExit."""
        with self.assertRaises(SystemExit) as context:
            validate_stdin("hello\x0b\x0cworld")
        self.assertIn("unsafe control characters", str(context.exception.code))

    def test_rejects_control_chars_14_31(self) -> None:
        """Test that bytes 14-31 raise SystemExit."""
        with self.assertRaises(SystemExit) as context:
            validate_stdin("hello\x0e\x0f\x10\x1fworld")
        self.assertIn("unsafe control characters", str(context.exception.code))

    def test_rejects_mixed_control_characters(self) -> None:
        """Test that mix of disallowed ctrl chars raises SystemExit."""
        with self.assertRaises(SystemExit) as context:
            validate_stdin("hello\x00\x01\x02world")
        self.assertIn("unsafe control characters", str(context.exception.code))
```

### Success Criteria:

#### Automated Verification:
- [ ] All 20 tests in ValidateStdinTests pass
- [ ] Test run: `pytest tools/auto_prd/tests/test_command_safety.py::ValidateStdinTests -v`
- [ ] Coverage for `validate_stdin()` reaches >95%

#### Manual Verification:
- [ ] None and empty string are tested
- [ ] Size limit boundary is tested (at limit, over limit)
- [ ] Each allowed control character is tested individually (tab, newline, carriage return)
- [ ] Each disallowed control character range is tested (0-8, 11-12, 14-31)
- [ ] Mixed control characters are tested
- [ ] Large input test at STDIN_MAX_BYTES boundary completes quickly

**Note**: Complete all automated verification, then pause for manual confirmation before proceeding to next phase.

---

## Phase 5: Implement ValidateExtraEnvTests

### Overview
Add comprehensive tests for `validate_extra_env()` covering None/empty dict acceptance, type validation, newline rejection, and valid environment variable acceptance.

### Changes Required:

#### 1. Add test methods to ValidateExtraEnvTests class
**File**: `/Users/simo/Projects/autodev/tools/auto_prd/tests/test_command_safety.py`
**Changes**: Add test methods to the empty class:

```python
class ValidateExtraEnvTests(TestCase):
    """Test suite for validate_extra_env function."""

    # None/empty dict acceptance tests
    def test_accepts_none(self) -> None:
        """Test that None passes (no extra env)."""
        try:
            validate_extra_env(None)
        except SystemExit as exc:
            self.fail(f"validate_extra_env rejected None: {exc}")

    def test_accepts_empty_dict(self) -> None:
        """Test that empty dict passes."""
        try:
            validate_extra_env({})
        except SystemExit as exc:
            self.fail(f"validate_extra_env rejected empty dict: {exc}")

    # Valid environment variable tests
    def test_accepts_valid_string_key_value(self) -> None:
        """Test that string key and value pass."""
        try:
            validate_extra_env({"TEST_VAR": "test_value"})
        except SystemExit as exc:
            self.fail(f"validate_extra_env rejected valid string key/value: {exc}")

    def test_accepts_multiple_valid_env_vars(self) -> None:
        """Test that multiple valid vars pass."""
        try:
            validate_extra_env({
                "VAR1": "value1",
                "VAR2": "value2",
                "VAR3": "value3",
            })
        except SystemExit as exc:
            self.fail(f"validate_extra_env rejected multiple valid vars: {exc}")

    def test_accepts_special_characters_in_value(self) -> None:
        """Test that special chars (except \\n) in value pass."""
        try:
            validate_extra_env({"TEST_VAR": "value with spaces, symbols!@#$%^&*()"})
        except SystemExit as exc:
            self.fail(f"validate_extra_env rejected special characters in value: {exc}")

    # Type validation tests
    def test_rejects_integer_key(self) -> None:
        """Test that int key raises SystemExit."""
        with self.assertRaises(SystemExit) as context:
            validate_extra_env({123: "value"})
        self.assertIn("must be strings", str(context.exception.code))

    def test_rejects_integer_value(self) -> None:
        """Test that int value raises SystemExit."""
        with self.assertRaises(SystemExit) as context:
            validate_extra_env({"KEY": 123})
        self.assertIn("must be strings", str(context.exception.code))

    def test_rejects_none_key(self) -> None:
        """Test that None key raises SystemExit."""
        with self.assertRaises(SystemExit) as context:
            validate_extra_env({None: "value"})  # type: ignore
        self.assertIn("must be strings", str(context.exception.code))

    def test_rejects_none_value(self) -> None:
        """Test that None value raises SystemExit."""
        with self.assertRaises(SystemExit) as context:
            validate_extra_env({"KEY": None})
        self.assertIn("must be strings", str(context.exception.code))

    # Newline rejection tests
    def test_rejects_newline_in_key(self) -> None:
        """Test that key with \\n raises SystemExit."""
        with self.assertRaises(SystemExit) as context:
            validate_extra_env({"KEY\nWITH_NEWLINE": "value"})
        self.assertIn("must not contain newlines", str(context.exception.code))

    def test_rejects_newline_in_value(self) -> None:
        """Test that value with \\n raises SystemExit."""
        with self.assertRaises(SystemExit) as context:
            validate_extra_env({"KEY": "value\nwith_newline"})
        self.assertIn("must not contain newlines", str(context.exception.code))

    def test_rejects_newline_in_both(self) -> None:
        """Test that \\n in both key and value raises SystemExit."""
        with self.assertRaises(SystemExit) as context:
            validate_extra_env({"KEY\n": "value\n"})
        self.assertIn("must not contain newlines", str(context.exception.code))
```

### Success Criteria:

#### Automated Verification:
- [ ] All 12 tests in ValidateExtraEnvTests pass
- [ ] Test run: `pytest tools/auto_prd/tests/test_command_safety.py::ValidateExtraEnvTests -v`
- [ ] Coverage for `validate_extra_env()` reaches >95%

#### Manual Verification:
- [ ] None and empty dict are tested
- [ ] Single and multiple valid env vars are tested
- [ ] Special characters (except newline) in values are tested
- [ ] Each non-string type is tested (int key, int value, None key, None value)
- [ ] Newline rejection is tested in key, value, and both
- [ ] Error messages are specific about the failure reason

**Note**: Complete all automated verification, then pause for manual confirmation before proceeding to final verification.

---

## Phase 6: Final Verification and Documentation

### Overview
Run complete test suite, verify coverage, and ensure no regressions in existing tests.

### Changes Required:

#### 1. Run full test suite
**Command**: `pytest tools/auto_prd/tests/test_command_safety.py -v --cov=tools.auto_prd.command --cov-report=term-missing`

**Expected output**:
- All 57 tests pass (17 + 8 + 20 + 12)
- Coverage for the four validation functions is >95%
- No warnings or errors

#### 2. Run existing test suite to check for regressions
**Command**: `pytest tools/auto_prd/tests/test_cli_safety.py -v`

**Expected output**:
- All existing tests still pass
- No new failures or errors

#### 3. Verify test file can be run standalone
**Command**: `python tools/auto_prd/tests/test_command_safety.py`

**Expected output**:
- All tests run and pass
- No import errors or missing dependencies

### Success Criteria:

#### Automated Verification:
- [ ] All 57 new tests pass: `pytest tools/auto_prd/tests/test_command_safety.py -v`
- [ ] Coverage for `validate_command_args()` >95%
- [ ] Coverage for `validate_cwd()` >95%
- [ ] Coverage for `validate_stdin()` >95%
- [ ] Coverage for `validate_extra_env()` >95%
- [ ] Existing tests still pass: `pytest tools/auto_prd/tests/test_cli_safety.py -v`
- [ ] Test file runs standalone: `python tools/auto_prd/tests/test_command_safety.py`

#### Manual Verification:
- [ ] Test file is well-organized with clear section comments
- [ ] Docstrings explain what each test validates
- [ ] Test names follow descriptive convention (test_<scenario>_<expected_outcome>)
- [ ] Error assertions check for specific error messages
- [ ] setUp/tearDown properly manage temp directories
- [ ] All imports use safe_import pattern
- [ ] No hardcoded constants (all imported via safe_import)

---

## Testing Strategy

### Unit Tests:
The implementation creates 57 comprehensive unit tests:

1. **ValidateCommandArgsTests (17 tests)**:
   - Input validation edge cases
   - Individual shell metacharacter rejection
   - Backtick special case handling
   - Command allowlist enforcement
   - Absolute path validation

2. **ValidateCwdTests (8 tests)**:
   - None and safe path acceptance
   - Path traversal rejection
   - Symlink handling

3. **ValidateStdinTests (20 tests)**:
   - Size limit boundary testing
   - Individual control character testing
   - Mixed control character rejection

4. **ValidateExtraEnvTests (12 tests)**:
   - Type validation for keys/values
   - Newline rejection in keys/values
   - Valid environment variable acceptance

### Integration Tests:
No integration tests needed - existing tests in `test_cli_safety.py` already cover integration with `run_cmd()` and `popen_streaming()`.

### Manual Testing Steps:
1. Run tests with verbose output to see individual test results
2. Check coverage report to verify all code paths are tested
3. Review test output for any warnings or skipped tests
4. Verify tests fail when validation logic is intentionally broken (to ensure tests actually catch bugs)

## Migration Notes
No migration needed - this is pure test addition with no changes to existing code.

## References
- Research: `/Users/simo/Projects/autodev/.wreckit/items/003-add-test-coverage-for-critical-security-validation/research.md`
- Implementation: `/Users/simo/Projects/autodev/tools/auto_prd/command.py` (lines 164-240)
- Constants: `/Users/simo/Projects/autodev/tools/auto_prd/constants.py` (lines 35-55)
- Existing tests: `/Users/simo/Projects/autodev/tools/auto_prd/tests/test_cli_safety.py`
- Test helpers: `/Users/simo/Projects/autodev/tools/auto_prd/tests/test_helpers.py`
