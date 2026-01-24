"""
Tests for command.py - shell command execution with safety checks.

Security is paramount here - we verify that:
1. Dangerous commands are rejected
2. Secrets are sanitized from error messages
3. Safe CWD restrictions are enforced
4. Command output is handled correctly
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from .test_helpers import safe_import

# Import functions under test
CommandResult = safe_import("auto_prd.command", "..command", "CommandResult")
run_cmd = safe_import("auto_prd.command", "..command", "run_cmd")
run_sh = safe_import("auto_prd.command", "..command", "run_sh")
safe_popen = safe_import("auto_prd.command", "..command", "safe_popen")
popen_streaming = safe_import("auto_prd.command", "..command", "popen_streaming")
register_safe_cwd = safe_import("auto_prd.command", "..command", "register_safe_cwd")
validate_command_args = safe_import(
    "auto_prd.command", "..command", "validate_command_args"
)
validate_cwd = safe_import("auto_prd.command", "..command", "validate_cwd")
validate_stdin = safe_import("auto_prd.command", "..command", "validate_stdin")
validate_extra_env = safe_import("auto_prd.command", "..command", "validate_extra_env")
sanitize_args = safe_import("auto_prd.command", "..command", "sanitize_args")
is_within = safe_import("auto_prd.command", "..command", "is_within")
find_repo_root = safe_import("auto_prd.command", "..command", "find_repo_root")
CalledProcessError = safe_import("auto_prd.command", "..command", "CalledProcessError")
TimeoutExpired = safe_import("auto_prd.command", "..command", "TimeoutExpired")
require_zsh = safe_import("auto_prd.constants", "..constants", "require_zsh")


class CommandResultTests(unittest.TestCase):
    """Test CommandResult dataclass behavior."""

    def test_tuple_unpacking(self) -> None:
        """Verify backward-compatible tuple unpacking works."""
        result = CommandResult(stdout="out", stderr="err", exit_code=1)
        stdout, stderr, exit_code = result
        self.assertEqual(stdout, "out")
        self.assertEqual(stderr, "err")
        self.assertEqual(exit_code, 1)

    def test_is_success(self) -> None:
        """Verify is_success() returns correct boolean."""
        success = CommandResult("out", "err", 0)
        self.assertTrue(success.is_success())

        failure = CommandResult("out", "err", 1)
        self.assertFalse(failure.is_success())

    def test_get_error_message_from_stderr(self) -> None:
        """Verify get_error_message() prefers stderr."""
        result = CommandResult(stdout="ignore this", stderr="actual error", exit_code=1)
        self.assertIn("actual error", result.get_error_message())
        self.assertNotIn("ignore this", result.get_error_message())

    def test_get_error_message_falls_back_to_stdout(self) -> None:
        """Verify get_error_message() falls back to stdout when stderr is empty."""
        result = CommandResult(stdout="stdout error", stderr="", exit_code=1)
        self.assertIn("stdout error", result.get_error_message())

    def test_get_error_message_falls_back_to_exit_code(self) -> None:
        """Verify get_error_message() falls back to exit code when both streams are empty."""
        result = CommandResult(stdout="", stderr="", exit_code=42)
        self.assertIn("42", result.get_error_message())


class RunCmdTests(unittest.TestCase):
    """Test run_cmd() function with various scenarios."""

    @patch("auto_prd.command.subprocess.run")
    @patch("auto_prd.command.shutil.which")
    def test_successful_command(self, mock_which: Mock, mock_run: Mock) -> None:
        """Verify run_cmd returns correct output for successful commands."""
        mock_which.return_value = "/usr/bin/git"
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = b"output"
        mock_process.stderr = b""
        mock_run.return_value = mock_process

        result = run_cmd(["git", "--version"], check=False)
        self.assertIsInstance(result, CommandResult)
        self.assertTrue(result.is_success())
        self.assertEqual(result.exit_code, 0)

    @patch("auto_prd.command.subprocess.run")
    @patch("auto_prd.command.shutil.which")
    def test_failed_command(self, mock_which: Mock, mock_run: Mock) -> None:
        """Verify run_cmd handles failed commands correctly."""
        mock_which.return_value = "/usr/bin/git"
        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.stdout = b""
        mock_process.stderr = b"error"
        mock_run.return_value = mock_process

        result = run_cmd(["git", "status"], check=False)
        self.assertFalse(result.is_success())
        self.assertEqual(result.exit_code, 1)

    @patch("auto_prd.command.subprocess.run")
    @patch("auto_prd.command.shutil.which")
    def test_command_with_stderr(self, mock_which: Mock, mock_run: Mock) -> None:
        """Verify stderr is captured correctly."""
        mock_which.return_value = "/usr/bin/git"
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = b""
        mock_process.stderr = b"error message"
        mock_run.return_value = mock_process

        result = run_cmd(["git", "status"], check=False)
        self.assertIn("error", result.stderr)

    @patch("auto_prd.command.subprocess.run")
    @patch("auto_prd.command.shutil.which")
    def test_command_timeout(self, mock_which: Mock, mock_run: Mock) -> None:
        """Verify commands timeout correctly."""
        mock_which.return_value = "/usr/bin/git"
        mock_run.side_effect = subprocess.TimeoutExpired(["git"], 1)

        with self.assertRaises(subprocess.TimeoutExpired):
            run_cmd(["git", "status"], timeout=1)

    @patch("auto_prd.command.subprocess.run")
    @patch("auto_prd.command.shutil.which")
    def test_environment_variables_passed(
        self, mock_which: Mock, mock_run: Mock
    ) -> None:
        """Verify environment variables are passed to subprocess."""
        mock_which.return_value = "/usr/bin/git"
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = b"test_value"
        mock_process.stderr = b""
        mock_run.return_value = mock_process

        _ = run_cmd(
            ["git", "status"], extra_env={"TEST_VAR": "test_value"}, check=False
        )
        # Verify env was passed
        self.assertTrue(mock_run.called)
        call_kwargs = mock_run.call_args[1]
        self.assertIn("env", call_kwargs)

    @patch("auto_prd.command.subprocess.run")
    @patch("auto_prd.command.shutil.which")
    def test_working_directory(self, mock_which: Mock, mock_run: Mock) -> None:
        """Verify working directory is respected."""
        mock_which.return_value = "/usr/bin/git"
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = b"/tmp/test"
        mock_process.stderr = b""
        mock_run.return_value = mock_process

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            register_safe_cwd(tmpdir_path)
            _ = run_cmd(["git", "status"], cwd=tmpdir_path, check=False)
            # Verify cwd was passed
            call_kwargs = mock_run.call_args[1]
            self.assertEqual(call_kwargs["cwd"], str(tmpdir_path))

    @patch("auto_prd.command.subprocess.run")
    @patch("auto_prd.command.shutil.which")
    def test_stdin_input(self, mock_which: Mock, mock_run: Mock) -> None:
        """Verify stdin is passed to subprocess."""
        mock_which.return_value = "/usr/bin/git"
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = b"test input"
        mock_process.stderr = b""
        mock_run.return_value = mock_process

        _ = run_cmd(["git", "status"], stdin="test input", check=False)
        # Verify stdin was passed
        call_kwargs = mock_run.call_args[1]
        self.assertIsNotNone(call_kwargs.get("input"))

    @patch("auto_prd.command.subprocess.run")
    @patch("auto_prd.command.shutil.which")
    def test_check_raises_on_failure(self, mock_which: Mock, mock_run: Mock) -> None:
        """Verify check=True raises CalledProcessError."""
        mock_which.return_value = "/usr/bin/git"
        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.stdout = b""
        mock_process.stderr = b"error"
        mock_run.return_value = mock_process

        with self.assertRaises(CalledProcessError):
            run_cmd(["git", "status"], check=True)

    @patch("auto_prd.command.subprocess.run")
    @patch("auto_prd.command.shutil.which")
    def test_check_false_returns_result(self, mock_which: Mock, mock_run: Mock) -> None:
        """Verify check=False returns result even on failure."""
        mock_which.return_value = "/usr/bin/git"
        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.stdout = b""
        mock_process.stderr = b"error"
        mock_run.return_value = mock_process

        result = run_cmd(["git", "status"], check=False)
        self.assertFalse(result.is_success())
        self.assertEqual(result.exit_code, 1)

    @patch("auto_prd.command.subprocess.run")
    @patch("auto_prd.command.shutil.which")
    def test_capture_false(self, mock_which: Mock, mock_run: Mock) -> None:
        """Verify capture=False doesn't capture output."""
        mock_which.return_value = "/usr/bin/git"
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = None  # type: ignore
        mock_process.stderr = None  # type: ignore
        mock_run.return_value = mock_process

        result = run_cmd(["git", "status"], capture=False, check=False)
        # Output is not captured, so stdout/stderr should be empty
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    @patch("auto_prd.command.validate_command_args")
    @patch("auto_prd.command.shutil.which")
    def test_sanitize_args_false(self, mock_which: Mock, mock_validate: Mock) -> None:
        """Verify sanitize_args=False preserves special characters."""
        mock_which.return_value = "/usr/bin/git"
        # This test verifies that the sanitize_args parameter is passed through
        # The actual sanitization logic is tested separately
        run_cmd(["git", "status"], sanitize_args=False, check=False)
        # validate_command_args should still be called
        mock_validate.assert_called_once()

    @patch("auto_prd.command.validate_command_args")
    @patch("auto_prd.command.shutil.which")
    def test_sanitize_args_true(self, mock_which: Mock, mock_validate: Mock) -> None:
        """Verify sanitize_args=True is the default behavior."""
        mock_which.return_value = "/usr/bin/git"
        run_cmd(["git", "status"], check=False)
        # validate_command_args should be called
        mock_validate.assert_called_once()


class ValidationTests(unittest.TestCase):
    """Test command validation functions."""

    def test_validate_command_args_empty_sequence(self) -> None:
        """Validate that empty command sequences raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            validate_command_args([])
        self.assertIn("non-empty", str(ctx.exception))

    def test_validate_command_args_string_raises(self) -> None:
        """Validate that passing a string (not a sequence) raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            validate_command_args("echo hello")
        self.assertIn("non-empty", str(ctx.exception))

    def test_validate_command_args_non_string_elements(self) -> None:
        """Validate that non-string elements raise TypeError."""
        with self.assertRaises(TypeError) as ctx:
            validate_command_args([123, "456"])
        self.assertIn("strings", str(ctx.exception))

    def test_validate_command_args_unsafe_chars(self) -> None:
        """Validate that unsafe shell metacharacters are rejected."""
        with self.assertRaises(ValueError) as ctx:
            validate_command_args(["echo", "hello|rm -rf /"])
        self.assertIn("unsafe shell metacharacters", str(ctx.exception))

    def test_validate_command_args_backtick_allowed(self) -> None:
        """Validate that backticks are allowed (subprocess uses shell=False)."""
        # Use git which is in the allowlist
        # Backticks should not raise an error
        try:
            validate_command_args(["git", "log", "--format=`hello`"])
        except ValueError as e:
            if "unsafe shell metacharacters" in str(e):
                self.fail("Backticks should be allowed but were rejected")

    def test_validate_command_args_pipe_rejected(self) -> None:
        """Validate that pipe character is rejected."""
        with self.assertRaises(ValueError):
            validate_command_args(["cat", "file|", "grep", "pattern"])

    def test_validate_command_args_semicolon_rejected(self) -> None:
        """Validate that semicolon is rejected."""
        with self.assertRaises(ValueError):
            validate_command_args(["echo", "hello;echo", "pwned"])

    def test_validate_command_args_redirect_rejected(self) -> None:
        """Validate that redirect characters are rejected."""
        with self.assertRaises(ValueError):
            validate_command_args(["echo", "hello>/tmp/pwned"])

    def test_validate_cwd_none(self) -> None:
        """Validate that None cwd is allowed."""
        # Should not raise
        validate_cwd(None)

    def test_validate_cwd_within_safe_roots(self) -> None:
        """Validate that cwd within safe roots is allowed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            register_safe_cwd(tmpdir_path)
            # Should not raise
            validate_cwd(tmpdir_path)

    def test_validate_cwd_outside_safe_roots(self) -> None:
        """Validate that cwd outside safe roots raises SystemExit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir) / "unsafe"
            tmpdir_path.mkdir()

            with self.assertRaises(SystemExit) as ctx:
                validate_cwd(tmpdir_path)
            self.assertIn("outside registered safe roots", str(ctx.exception))

    def test_validate_stdin_none(self) -> None:
        """Validate that None stdin is allowed."""
        # Should not raise
        validate_stdin(None)

    def test_validate_stdin_too_large(self) -> None:
        """Validate that oversized stdin raises SystemExit."""
        # Create a string larger than STDIN_MAX_BYTES (assuming it's reasonably small)
        large_input = "x" * 10_000_000  # 10 MB
        with self.assertRaises(SystemExit) as ctx:
            validate_stdin(large_input)
        self.assertIn("too large", str(ctx.exception))

    def test_validate_stdin_unsafe_control_chars(self) -> None:
        """Validate that unsafe control characters in stdin raise SystemExit."""
        # Control characters below 32 (excluding allowed ones) should raise
        unsafe_input = "hello\x00\x01world"
        with self.assertRaises(SystemExit) as ctx:
            validate_stdin(unsafe_input)
        self.assertIn("unsafe control characters", str(ctx.exception))

    def test_validate_extra_env_none(self) -> None:
        """Validate that None extra_env is allowed."""
        # Should not raise
        validate_extra_env(None)

    def test_validate_extra_env_empty_dict(self) -> None:
        """Validate that empty extra_env dict is allowed."""
        # Should not raise
        validate_extra_env({})

    def test_validate_extra_env_valid(self) -> None:
        """Validate that valid extra_env is allowed."""
        # Should not raise
        validate_extra_env({"KEY": "value"})

    def test_validate_extra_env_non_string_key(self) -> None:
        """Validate that non-string keys raise SystemExit."""
        with self.assertRaises(SystemExit) as ctx:
            validate_extra_env({123: "value"})
        self.assertIn("must be strings", str(ctx.exception))

    def test_validate_extra_env_non_string_value(self) -> None:
        """Validate that non-string values raise SystemExit."""
        with self.assertRaises(SystemExit) as ctx:
            validate_extra_env({"KEY": 123})
        self.assertIn("must be strings", str(ctx.exception))

    def test_validate_extra_env_newline_in_key(self) -> None:
        """Validate that newlines in keys raise SystemExit."""
        with self.assertRaises(SystemExit) as ctx:
            validate_extra_env({"KE\nY": "value"})
        self.assertIn("must not contain newlines", str(ctx.exception))

    def test_validate_extra_env_newline_in_value(self) -> None:
        """Validate that newlines in values raise SystemExit."""
        with self.assertRaises(SystemExit) as ctx:
            validate_extra_env({"KEY": "val\nue"})
        self.assertIn("must not contain newlines", str(ctx.exception))


class SanitizeArgsTests(unittest.TestCase):
    """Test argument sanitization for logging."""

    def test_sanitize_args_preserves_safe_args(self) -> None:
        """Verify that safe arguments are not modified."""
        args = ["echo", "hello", "world"]
        sanitized = sanitize_args(args)
        self.assertEqual(sanitized, args)

    def test_sanitize_args_redacts_shell_script(self) -> None:
        """Verify that -c shell scripts are redacted."""
        args = ["sh", "-c", "echo secret"]
        sanitized = sanitize_args(args)
        self.assertEqual(sanitized, ["sh", "-c", "<REDACTED_SCRIPT>"])

    def test_sanitize_args_redacts_sensitive_keys(self) -> None:
        """Verify that sensitive key=value pairs are redacted."""
        args = ["--token=secret123", "--password=pwd"]
        sanitized = sanitize_args(args)
        self.assertIn("--token=<REDACTED>", sanitized)
        self.assertIn("--password=<REDACTED>", sanitized)

    def test_sanitize_args_redacts_api_key(self) -> None:
        """Verify that api_key=value is redacted."""
        args = ["--api_key=mykey"]
        sanitized = sanitize_args(args)
        self.assertIn("--api_key=<REDACTED>", sanitized)

    def test_sanitize_args_redacts_next_arg(self) -> None:
        """Verify that sensitive keys redact the next argument."""
        args = ["--token", "secret123"]
        sanitized = sanitize_args(args)
        self.assertEqual(sanitized, ["--token", "<REDACTED>"])

    def test_sanitize_args_case_insensitive_keys(self) -> None:
        """Verify that key matching is case-insensitive."""
        args = ["--TOKEN=secret", "--Password=pwd"]
        sanitized = sanitize_args(args)
        self.assertIn("--TOKEN=<REDACTED>", sanitized)
        self.assertIn("--Password=<REDACTED>", sanitized)


class IsWithinTests(unittest.TestCase):
    """Test is_within() path checking function."""

    def test_is_within_same_path(self) -> None:
        """Verify that a path is within itself."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            self.assertTrue(is_within(tmpdir_path, tmpdir_path))

    def test_is_within_child_path(self) -> None:
        """Verify that a child path is within parent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            child_path = tmpdir_path / "child"
            child_path.mkdir()
            self.assertTrue(is_within(child_path, tmpdir_path))

    def test_is_within_parent_path(self) -> None:
        """Verify that parent is not within child."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            child_path = tmpdir_path / "child"
            child_path.mkdir()
            self.assertFalse(is_within(tmpdir_path, child_path))

    def test_is_within_sibling_path(self) -> None:
        """Verify that sibling paths are not within each other."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            child1 = tmpdir_path / "child1"
            child2 = tmpdir_path / "child2"
            child1.mkdir()
            child2.mkdir()
            self.assertFalse(is_within(child1, child2))

    def test_is_within_nonexistent_path(self) -> None:
        """Verify that nonexistent paths are handled correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            nonexistent = tmpdir_path / "does_not_exist"
            # is_within catches FileNotFoundError and falls back to resolve()
            # For a nonexistent child path, it will still return True if the resolved
            # path would be within the parent's parents
            result = is_within(nonexistent, tmpdir_path)
            # The nonexistent path should resolve to a path within tmpdir_path
            self.assertTrue(result)


class FindRepoRootTests(unittest.TestCase):
    """Test find_repo_root() function."""

    def test_find_repo_root_finds_git_dir(self) -> None:
        """Verify that .git directory is found."""
        # Start from the current directory (which should have .git somewhere in ancestors)
        repo_root = find_repo_root()
        self.assertIsInstance(repo_root, Path)
        # The repo root should exist
        self.assertTrue(repo_root.exists())

    def test_find_repo_root_falls_back_to_cwd(self) -> None:
        """Verify fallback to cwd when .git not found."""
        # Create a temp directory without .git
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir).resolve()  # Resolve to handle symlinks
            # Change to temp directory
            original_cwd = Path.cwd()
            try:
                os.chdir(tmpdir_path)
                repo_root = find_repo_root(tmpdir_path)
                # Should fall back to Path.cwd() which is now tmpdir_path
                # Use resolve() to handle macOS /var -> /private/var symlinks
                self.assertEqual(repo_root.resolve(), tmpdir_path.resolve())
            finally:
                os.chdir(original_cwd)


class SafePopenTests(unittest.TestCase):
    """Test safe_popen() function."""

    @patch("auto_prd.command.subprocess.Popen")
    @patch("auto_prd.command.shutil.which")
    def test_safe_popen_creates_process(
        self, mock_which: Mock, mock_popen: Mock
    ) -> None:
        """Verify that safe_popen creates a subprocess.Popen object."""
        mock_which.return_value = "/usr/bin/git"
        mock_process = MagicMock()
        mock_process.stdout = MagicMock()
        mock_process.stderr = MagicMock()
        mock_popen.return_value = mock_process

        proc = safe_popen(["git", "status"])

        self.assertIsNotNone(proc)
        mock_popen.assert_called_once()

    @patch("auto_prd.command.shutil.which")
    def test_safe_popen_command_not_found(self, mock_which: Mock) -> None:
        """Verify that safe_popen raises FileNotFoundError for missing commands."""
        mock_which.return_value = None
        with self.assertRaises(FileNotFoundError):
            safe_popen(["git", "status"])


class PopenStreamingTests(unittest.TestCase):
    """Test popen_streaming() function."""

    @patch("auto_prd.command.subprocess.Popen")
    @patch("auto_prd.command.shutil.which")
    @patch("auto_prd.command.find_repo_root")
    def test_popen_streaming_creates_process(
        self, mock_repo_root: Mock, mock_which: Mock, mock_popen: Mock
    ) -> None:
        """Verify that popen_streaming creates a Popen object with sanitized args."""
        # Setup mocks
        mock_which.return_value = "/usr/bin/git"
        mock_process = MagicMock()
        mock_process.stdout = MagicMock()
        mock_process.stderr = MagicMock()
        mock_popen.return_value = mock_process

        # Mock repo root
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            tmpdir_path.mkdir(exist_ok=True)
            (tmpdir_path / ".git").mkdir()
            mock_repo_root.return_value = tmpdir_path

            proc, sanitized_cmd = popen_streaming(["git", "status"])

            self.assertIsNotNone(proc)
            self.assertEqual(sanitized_cmd, ["git", "status"])
            mock_popen.assert_called_once()

    @patch("auto_prd.command.shutil.which")
    def test_popen_streaming_command_not_found(self, mock_which: Mock) -> None:
        """Verify that popen_streaming raises FileNotFoundError for missing commands."""
        mock_which.return_value = None
        with self.assertRaises(FileNotFoundError):
            popen_streaming(["git", "status"])

    def test_popen_streaming_validates_before_sanitization(self) -> None:
        """Verify that validation happens BEFORE sanitization (security)."""
        # This is a security-critical test - we want to ensure that
        # malicious input is rejected before sanitization hides it
        with self.assertRaises(ValueError):
            popen_streaming(["git", "status|rm", "-rf", "/"])

    @patch("auto_prd.command.subprocess.Popen")
    @patch("auto_prd.command.shutil.which")
    @patch("auto_prd.command.find_repo_root")
    @patch("auto_prd.command.scrub_cli_text")
    def test_popen_streaming_sanitizes_when_enabled(
        self, mock_scrub: Mock, mock_repo_root: Mock, mock_which: Mock, mock_popen: Mock
    ) -> None:
        """Verify that popen_streaming sanitizes args when sanitize=True."""
        # Setup mocks
        mock_which.return_value = "/usr/bin/git"
        mock_scrub.side_effect = lambda x: x.replace("`", "'")  # Simple sanitization
        mock_process = MagicMock()
        mock_process.stdout = MagicMock()
        mock_process.stderr = MagicMock()
        mock_popen.return_value = mock_process

        # Mock repo root
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            tmpdir_path.mkdir(exist_ok=True)
            (tmpdir_path / ".git").mkdir()
            mock_repo_root.return_value = tmpdir_path

            proc, sanitized_cmd = popen_streaming(["git", "log", "--format=`hello`"])

            # scrub_cli_text should have been called
            mock_scrub.assert_called()


class RetryLogicTests(unittest.TestCase):
    """Test retry logic in run_cmd()."""

    @patch("auto_prd.command.subprocess.run")
    @patch("auto_prd.command.shutil.which")
    @patch("auto_prd.command.time.sleep")
    def test_retry_on_exit_code(
        self, mock_sleep: Mock, mock_which: Mock, mock_run: Mock
    ) -> None:
        """Verify that retry works for specific exit codes."""
        mock_which.return_value = "/usr/bin/git"
        # Fail twice, then succeed
        mock_process_fail = MagicMock()
        mock_process_fail.returncode = 1
        mock_process_fail.stdout = b""
        mock_process_fail.stderr = b"error"
        mock_process_success = MagicMock()
        mock_process_success.returncode = 0
        mock_process_success.stdout = b"success"
        mock_process_success.stderr = b""
        mock_run.side_effect = [
            mock_process_fail,
            mock_process_fail,
            mock_process_success,
        ]

        result = run_cmd(["git", "status"], retries=2, retry_on_codes={1}, check=False)

        # Should have succeeded after retries
        self.assertTrue(result.is_success())
        self.assertEqual(mock_run.call_count, 3)  # Initial + 2 retries
        self.assertEqual(mock_sleep.call_count, 2)  # Slept between retries

    @patch("auto_prd.command.subprocess.run")
    @patch("auto_prd.command.shutil.which")
    @patch("auto_prd.command.time.sleep")
    def test_retry_on_stderr_pattern(
        self, mock_sleep: Mock, mock_which: Mock, mock_run: Mock
    ) -> None:
        """Verify that retry works for stderr patterns."""
        mock_which.return_value = "/usr/bin/git"
        # Fail twice with transient error, then succeed
        mock_process_fail = MagicMock()
        mock_process_fail.returncode = 1
        mock_process_fail.stdout = b""
        mock_process_fail.stderr = b"transient error"
        mock_process_success = MagicMock()
        mock_process_success.returncode = 0
        mock_process_success.stdout = b"success"
        mock_process_success.stderr = b""
        mock_run.side_effect = [
            mock_process_fail,
            mock_process_fail,
            mock_process_success,
        ]

        result = run_cmd(
            ["git", "status"], retries=2, retry_on_stderr=["transient"], check=False
        )

        # Should have succeeded after retries
        self.assertTrue(result.is_success())
        self.assertEqual(mock_run.call_count, 3)

    @patch("auto_prd.command.subprocess.run")
    @patch("auto_prd.command.shutil.which")
    def test_no_retry_when_not_match(self, mock_which: Mock, mock_run: Mock) -> None:
        """Verify that retry is skipped when conditions don't match."""
        mock_which.return_value = "/usr/bin/git"
        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.stdout = b""
        mock_process.stderr = b"permanent error"
        mock_run.return_value = mock_process

        result = run_cmd(
            ["git", "status"],
            retries=2,
            retry_on_codes={2},  # Doesn't match exit code 1
            retry_on_stderr=["transient"],  # Doesn't match stderr
            check=False,
        )

        # Should have failed without retries
        self.assertFalse(result.is_success())
        self.assertEqual(mock_run.call_count, 1)  # Only initial call


class RunShTests(unittest.TestCase):
    """Test run_sh() function."""

    @patch("auto_prd.command.run_cmd")
    @patch("auto_prd.command.require_zsh")
    def test_run_sh_calls_run_cmd(self, mock_zsh: Mock, mock_run_cmd: Mock) -> None:
        """Verify that run_sh delegates to run_cmd with zsh."""
        mock_zsh.return_value = "/bin/zsh"
        mock_result = CommandResult("out", "err", 0)
        mock_run_cmd.return_value = mock_result

        result = run_sh("echo hello", check=False)

        self.assertEqual(result, mock_result)
        mock_run_cmd.assert_called_once()
        call_args = mock_run_cmd.call_args[0]
        self.assertEqual(call_args[0][0], "/bin/zsh")
        self.assertEqual(call_args[0][1], "-lc")
        self.assertEqual(call_args[0][2], "echo hello")


if __name__ == "__main__":
    unittest.main()
