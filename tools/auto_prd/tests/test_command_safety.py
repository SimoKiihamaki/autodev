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
    "tools.auto_prd.command", "auto_prd.command", "validate_command_args"
)
validate_cwd = safe_import("tools.auto_prd.command", "auto_prd.command", "validate_cwd")
validate_stdin = safe_import(
    "tools.auto_prd.command", "auto_prd.command", "validate_stdin"
)
validate_extra_env = safe_import(
    "tools.auto_prd.command", "auto_prd.command", "validate_extra_env"
)
register_safe_cwd = safe_import(
    "tools.auto_prd.command", "auto_prd.command", "register_safe_cwd"
)

# Import security constants for testing
COMMAND_ALLOWLIST = safe_import(
    "tools.auto_prd.constants", "auto_prd.constants", "COMMAND_ALLOWLIST"
)
UNSAFE_ARG_CHARS = safe_import(
    "tools.auto_prd.constants", "auto_prd.constants", "UNSAFE_ARG_CHARS"
)
STDIN_MAX_BYTES = safe_import(
    "tools.auto_prd.constants", "auto_prd.constants", "STDIN_MAX_BYTES"
)
SAFE_STDIN_ALLOWED_CTRL = safe_import(
    "tools.auto_prd.constants", "auto_prd.constants", "SAFE_STDIN_ALLOWED_CTRL"
)


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
            validate_command_args(["git", "foo`bar"])
        except ValueError as exc:
            self.fail(f"validate_command_args unexpectedly rejected backticks: {exc}")

    def test_allows_multiple_backticks(self) -> None:
        """Test that multiple backticks are allowed."""
        try:
            validate_command_args(["gh", "`foo` `bar`"])
        except ValueError as exc:
            self.fail(
                f"validate_command_args unexpectedly rejected multiple backticks: {exc}"
            )

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
                self.fail(
                    f"validate_command_args rejected allowlisted command '{cmd}': {exc}"
                )

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
            self.fail(
                f"validate_command_args rejected absolute path within safe root: {exc}"
            )

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
            validate_extra_env(
                {
                    "VAR1": "value1",
                    "VAR2": "value2",
                    "VAR3": "value3",
                }
            )
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
            validate_extra_env({123: "value"})  # type: ignore
        self.assertIn("must be strings", str(context.exception.code))

    def test_rejects_integer_value(self) -> None:
        """Test that int value raises SystemExit."""
        with self.assertRaises(SystemExit) as context:
            validate_extra_env({"KEY": 123})  # type: ignore
        self.assertIn("must be strings", str(context.exception.code))

    def test_rejects_none_key(self) -> None:
        """Test that None key raises SystemExit."""
        with self.assertRaises(SystemExit) as context:
            validate_extra_env({None: "value"})  # type: ignore
        self.assertIn("must be strings", str(context.exception.code))

    def test_rejects_none_value(self) -> None:
        """Test that None value raises SystemExit."""
        with self.assertRaises(SystemExit) as context:
            validate_extra_env({"KEY": None})  # type: ignore
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


if __name__ == "__main__":
    main()
