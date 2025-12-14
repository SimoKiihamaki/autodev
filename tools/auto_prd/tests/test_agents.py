import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from .test_helpers import safe_import

# Import the agents module and functions we need to test
agents = safe_import("tools.auto_prd.agents", "..agents")
_timeout_from_env = safe_import(
    "tools.auto_prd.agents", "..agents", "_timeout_from_env"
)
get_codex_exec_timeout = safe_import(
    "tools.auto_prd.agents", "..agents", "get_codex_exec_timeout"
)
get_claude_exec_timeout = safe_import(
    "tools.auto_prd.agents", "..agents", "get_claude_exec_timeout"
)
DEFAULT_CLAUDE_TIMEOUT_SECONDS = safe_import(
    "tools.auto_prd.agents", "..agents", "DEFAULT_CLAUDE_TIMEOUT_SECONDS"
)
claude_exec_streaming = safe_import(
    "tools.auto_prd.agents", "..agents", "claude_exec_streaming"
)
_process_buffer = safe_import("tools.auto_prd.agents", "..agents", "_process_buffer")
_drain_fds_best_effort = safe_import(
    "tools.auto_prd.agents", "..agents", "_drain_fds_best_effort"
)
_resolve_unsafe_flag = safe_import(
    "tools.auto_prd.agents", "..agents", "_resolve_unsafe_flag"
)
_build_claude_args = safe_import(
    "tools.auto_prd.agents", "..agents", "_build_claude_args"
)
ClaudeHeadlessResponse = safe_import(
    "tools.auto_prd.agents", "..agents", "ClaudeHeadlessResponse"
)
parse_claude_json_response = safe_import(
    "tools.auto_prd.agents", "..agents", "parse_claude_json_response"
)
register_safe_cwd = safe_import(
    "tools.auto_prd.command", "..command", "register_safe_cwd"
)


class TimeoutConfigurationTests(unittest.TestCase):
    """Test suite for timeout configuration functions."""

    def setUp(self):
        """Set up test environment by clearing relevant environment variables."""
        # Clear any existing timeout environment variables
        env_vars_to_clear = [
            "AUTO_PRD_CODEX_TIMEOUT_SECONDS",
            "AUTO_PRD_CLAUDE_TIMEOUT_SECONDS",
        ]
        for env_var in env_vars_to_clear:
            if env_var in os.environ:
                del os.environ[env_var]

    def test_timeout_from_env_unset_returns_default(self):
        """Test that unset environment variable returns the default value."""
        result = _timeout_from_env("AUTO_PRD_TEST_TIMEOUT", 300)
        self.assertEqual(result, 300)

    def test_timeout_from_env_none_default(self):
        """Test that unset environment variable returns None when default is None."""
        result = _timeout_from_env("AUTO_PRD_TEST_TIMEOUT", None)
        self.assertIsNone(result)

    def test_timeout_from_env_empty_string_returns_none(self):
        """Test that empty string returns None."""
        with patch.dict(os.environ, {"AUTO_PRD_TEST_TIMEOUT": ""}):
            result = _timeout_from_env("AUTO_PRD_TEST_TIMEOUT", 300)
            self.assertIsNone(result)

    def test_timeout_from_env_whitespace_only_returns_none(self):
        """Test that whitespace-only string returns None."""
        with patch.dict(os.environ, {"AUTO_PRD_TEST_TIMEOUT": "   "}):
            result = _timeout_from_env("AUTO_PRD_TEST_TIMEOUT", 300)
            self.assertIsNone(result)

    def test_timeout_from_env_disabled_keywords_return_none(self):
        """Test that various disabled keywords return None."""
        disabled_keywords = ["none", "no", "off", "disable", "disabled"]

        for keyword in disabled_keywords:
            with self.subTest(keyword=keyword):
                with patch.dict(os.environ, {"AUTO_PRD_TEST_TIMEOUT": keyword}):
                    result = _timeout_from_env("AUTO_PRD_TEST_TIMEOUT", 300)
                    self.assertIsNone(result)

    def test_timeout_from_env_disabled_keywords_case_insensitive(self):
        """Test that disabled keywords are case insensitive."""
        disabled_variations = ["NONE", "No", "OFF", "Disable", "DISABLED"]

        for variation in disabled_variations:
            with self.subTest(variation=variation):
                with patch.dict(os.environ, {"AUTO_PRD_TEST_TIMEOUT": variation}):
                    result = _timeout_from_env("AUTO_PRD_TEST_TIMEOUT", 300)
                    self.assertIsNone(result)

    def test_timeout_from_env_disabled_keywords_with_whitespace(self):
        """Test that disabled keywords with whitespace return None."""
        with patch.dict(os.environ, {"AUTO_PRD_TEST_TIMEOUT": "  none  "}):
            result = _timeout_from_env("AUTO_PRD_TEST_TIMEOUT", 300)
            self.assertIsNone(result)

    def test_timeout_from_env_valid_integer_returns_parsed_value(self):
        """Test that valid integer string returns the parsed value."""
        with patch.dict(os.environ, {"AUTO_PRD_TEST_TIMEOUT": "500"}):
            result = _timeout_from_env("AUTO_PRD_TEST_TIMEOUT", 300)
            self.assertEqual(result, 500)

    def test_timeout_from_env_valid_integer_with_whitespace_returns_parsed_value(self):
        """Test that valid integer with whitespace returns the parsed value."""
        with patch.dict(os.environ, {"AUTO_PRD_TEST_TIMEOUT": "  500  "}):
            result = _timeout_from_env("AUTO_PRD_TEST_TIMEOUT", 300)
            self.assertEqual(result, 500)

    def test_timeout_from_env_invalid_format_returns_default(self):
        """Test that invalid format returns the default value."""
        with patch.dict(os.environ, {"AUTO_PRD_TEST_TIMEOUT": "invalid"}):
            result = _timeout_from_env("AUTO_PRD_TEST_TIMEOUT", 300)
            self.assertEqual(result, 300)

    def test_timeout_from_env_non_numeric_string_returns_default(self):
        """Test that non-numeric string returns the default value."""
        invalid_values = ["abc", "12.5", "1e3", "inf", "-inf", "nan"]

        for invalid_value in invalid_values:
            with self.subTest(invalid_value=invalid_value):
                with patch.dict(os.environ, {"AUTO_PRD_TEST_TIMEOUT": invalid_value}):
                    result = _timeout_from_env("AUTO_PRD_TEST_TIMEOUT", 300)
                    self.assertEqual(result, 300)

    def test_timeout_from_env_zero_returns_none(self):
        """Test that zero value returns None."""
        with patch.dict(os.environ, {"AUTO_PRD_TEST_TIMEOUT": "0"}):
            result = _timeout_from_env("AUTO_PRD_TEST_TIMEOUT", 300)
            self.assertIsNone(result)

    def test_timeout_from_env_negative_returns_none(self):
        """Test that negative value returns None."""
        with patch.dict(os.environ, {"AUTO_PRD_TEST_TIMEOUT": "-10"}):
            result = _timeout_from_env("AUTO_PRD_TEST_TIMEOUT", 300)
            self.assertIsNone(result)

    def test_get_codex_exec_timeout_default(self):
        """Test get_codex_exec_timeout with no environment variable set."""
        result = get_codex_exec_timeout()
        self.assertIsNone(result)  # Default is None for codex

    def test_get_claude_exec_timeout_default(self):
        """Test get_claude_exec_timeout with no environment variable set."""
        result = get_claude_exec_timeout()
        # Default is 60 minutes (3600 seconds) to prevent infinite hangs
        self.assertEqual(result, DEFAULT_CLAUDE_TIMEOUT_SECONDS)
        self.assertEqual(result, 3600)

    def test_get_codex_exec_timeout_from_env(self):
        """Test get_codex_exec_timeout reads from environment variable."""
        with patch.dict(os.environ, {"AUTO_PRD_CODEX_TIMEOUT_SECONDS": "600"}):
            result = get_codex_exec_timeout()
            self.assertEqual(result, 600)

    def test_get_claude_exec_timeout_from_env(self):
        """Test get_claude_exec_timeout reads from environment variable."""
        with patch.dict(os.environ, {"AUTO_PRD_CLAUDE_TIMEOUT_SECONDS": "400"}):
            result = get_claude_exec_timeout()
            self.assertEqual(result, 400)

    def test_get_codex_exec_timeout_disabled(self):
        """Test get_codex_exec_timeout with disabled value."""
        with patch.dict(os.environ, {"AUTO_PRD_CODEX_TIMEOUT_SECONDS": "disabled"}):
            result = get_codex_exec_timeout()
            self.assertIsNone(result)

    def test_get_claude_exec_timeout_disabled(self):
        """Test get_claude_exec_timeout with disabled value."""
        with patch.dict(os.environ, {"AUTO_PRD_CLAUDE_TIMEOUT_SECONDS": "off"}):
            result = get_claude_exec_timeout()
            self.assertIsNone(result)

    def test_get_codex_exec_timeout_invalid(self):
        """Test get_codex_exec_timeout with invalid value falls back to default."""
        with patch.dict(os.environ, {"AUTO_PRD_CODEX_TIMEOUT_SECONDS": "invalid"}):
            result = get_codex_exec_timeout()
            self.assertIsNone(result)  # Falls back to default (None)

    def test_get_claude_exec_timeout_invalid(self):
        """Test get_claude_exec_timeout with invalid value falls back to default."""
        with patch.dict(os.environ, {"AUTO_PRD_CLAUDE_TIMEOUT_SECONDS": "invalid"}):
            result = get_claude_exec_timeout()
            # Falls back to default (3600 seconds)
            self.assertEqual(result, DEFAULT_CLAUDE_TIMEOUT_SECONDS)

    def test_timeout_functions_isolated(self):
        """Test that codex and claude timeout functions are independent."""
        with patch.dict(
            os.environ,
            {
                "AUTO_PRD_CODEX_TIMEOUT_SECONDS": "500",
                "AUTO_PRD_CLAUDE_TIMEOUT_SECONDS": "300",
            },
        ):
            codex_result = get_codex_exec_timeout()
            claude_result = get_claude_exec_timeout()

            self.assertEqual(codex_result, 500)
            self.assertEqual(claude_result, 300)

    def test_timeout_functions_runtime_evaluation(self):
        """Test that timeout functions evaluate at runtime, not import time."""
        # Initially no environment variables - codex returns None, claude returns default
        self.assertIsNone(get_codex_exec_timeout())
        self.assertEqual(get_claude_exec_timeout(), DEFAULT_CLAUDE_TIMEOUT_SECONDS)

        # Set environment variables after import
        with patch.dict(
            os.environ,
            {
                "AUTO_PRD_CODEX_TIMEOUT_SECONDS": "700",
                "AUTO_PRD_CLAUDE_TIMEOUT_SECONDS": "900",
            },
        ):
            # Functions should pick up the new values
            self.assertEqual(get_codex_exec_timeout(), 700)
            self.assertEqual(get_claude_exec_timeout(), 900)


@unittest.skipIf(sys.platform == "win32", "claude_exec_streaming requires Unix fcntl")
class ClaudeExecStreamingTests(unittest.TestCase):
    """Test suite for claude_exec_streaming function."""

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.repo_root = Path(self.temp_dir)
        register_safe_cwd(self.repo_root)

    def tearDown(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("tools.auto_prd.agents.popen_streaming")
    @patch("tools.auto_prd.agents.verify_unsafe_execution_ready")
    def test_dry_run_returns_dry_run_output(self, _mock_verify, mock_popen):
        """Test that dry_run=True returns ('DRY_RUN', '') without execution."""
        stdout, stderr = claude_exec_streaming(
            prompt="Test prompt",
            repo_root=self.repo_root,
            allow_unsafe_execution=True,
            dry_run=True,
        )
        self.assertEqual(stdout, "DRY_RUN")
        self.assertEqual(stderr, "")
        # Verify no subprocess was spawned (the key behavior for dry_run)
        mock_popen.assert_not_called()
        # Note: verify_unsafe_execution_ready IS called even in dry_run mode when
        # allow_unsafe_execution=True, to provide consistent error messaging about
        # environment configuration. This is intentional behavior.

    def test_permission_error_without_allow_unsafe_execution(self):
        """Test that PermissionError is raised when allow_unsafe_execution=False."""
        with self.assertRaises(PermissionError) as context:
            claude_exec_streaming(
                prompt="Test prompt",
                repo_root=self.repo_root,
                allow_unsafe_execution=False,
                dry_run=False,
            )
        self.assertIn("requires allow_unsafe_execution=True", str(context.exception))

    def test_os_error_when_fcntl_unavailable(self):
        """Test that OSError is raised when fcntl is not available.

        This test simulates the missing-fcntl code path on Unix-like platforms
        by patching fcntl to None. Since this test class is skipped on Windows,
        we're testing that Unix systems correctly raise OSError when fcntl is
        unavailable (a scenario that would require explicit patching to trigger).
        """
        with patch("tools.auto_prd.agents.fcntl", None):
            with self.assertRaises(OSError) as context:
                claude_exec_streaming(
                    prompt="Test prompt",
                    repo_root=self.repo_root,
                    allow_unsafe_execution=True,
                    dry_run=False,
                )
            self.assertIn("fcntl", str(context.exception))

    @patch("tools.auto_prd.agents.popen_streaming")
    @patch("tools.auto_prd.agents.verify_unsafe_execution_ready")
    def test_broken_pipe_error_handling(self, _mock_verify, mock_popen):
        """Test that BrokenPipeError during stdin write raises CalledProcessError."""
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdin.write.side_effect = BrokenPipeError("Broken pipe")
        mock_proc.wait.return_value = None
        mock_proc.returncode = 1
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.close = MagicMock()
        mock_proc.stderr = MagicMock()
        mock_proc.stderr.read.return_value = "Process died early"
        mock_proc.stderr.close = MagicMock()
        mock_popen.return_value = (mock_proc, ["claude", "--print"])

        with self.assertRaises(subprocess.CalledProcessError) as context:
            claude_exec_streaming(
                prompt="Test prompt",
                repo_root=self.repo_root,
                allow_unsafe_execution=True,
                dry_run=False,
            )
        self.assertEqual(context.exception.returncode, 1)
        self.assertIn(b"terminated unexpectedly", context.exception.stderr)

    @patch("tools.auto_prd.agents.popen_streaming")
    @patch("tools.auto_prd.agents.verify_unsafe_execution_ready")
    @patch("tools.auto_prd.agents._set_nonblocking")
    @patch("tools.auto_prd.agents.select.select")
    def test_timeout_handling(
        self, mock_select, _mock_nonblock, _mock_verify, mock_popen
    ):
        """Test that timeout raises TimeoutExpired with partial output."""
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdin.write = MagicMock()
        mock_proc.stdin.close = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.fileno.return_value = 3
        mock_proc.stdout.read.return_value = "partial output"
        mock_proc.stdout.close = MagicMock()
        mock_proc.stderr = MagicMock()
        mock_proc.stderr.fileno.return_value = 4
        mock_proc.stderr.read.return_value = ""
        mock_proc.stderr.close = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.kill = MagicMock()
        mock_proc.wait = MagicMock()
        mock_popen.return_value = (mock_proc, ["claude", "--print"])

        # Simulate timeout by returning readable fds but no actual data
        mock_select.return_value = ([mock_proc.stdout], [], [])

        with patch("tools.auto_prd.agents.time.monotonic") as mock_time:
            # First call for start_time, subsequent calls show elapsed time > timeout
            mock_time.side_effect = [
                0,
                0,
                2,
            ]  # start=0, check=0, check=2 (> 1s timeout)
            with self.assertRaises(subprocess.TimeoutExpired) as context:
                claude_exec_streaming(
                    prompt="Test prompt",
                    repo_root=self.repo_root,
                    allow_unsafe_execution=True,
                    dry_run=False,
                    timeout=1,
                )
            self.assertEqual(context.exception.timeout, 1)

    @patch("tools.auto_prd.agents.popen_streaming")
    @patch("tools.auto_prd.agents.verify_unsafe_execution_ready")
    @patch("tools.auto_prd.agents._set_nonblocking")
    @patch("tools.auto_prd.agents.select.select")
    def test_successful_streaming_execution(
        self, mock_select, _mock_nonblock, _mock_verify, mock_popen
    ):
        """Test successful streaming execution with output callback."""
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdin.write = MagicMock()
        mock_proc.stdin.close = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.fileno.return_value = 3
        mock_proc.stderr = MagicMock()
        mock_proc.stderr.fileno.return_value = 4
        mock_proc.stdout.close = MagicMock()
        mock_proc.stderr.close = MagicMock()
        mock_proc.returncode = 0
        mock_proc.wait = MagicMock()
        mock_popen.return_value = (mock_proc, ["claude", "--print"])

        # First poll returns None (process running), second returns 0 (process done)
        mock_proc.poll.side_effect = [None, 0]
        # First select returns stdout readable, second select with empty readable fds
        mock_select.side_effect = [([mock_proc.stdout], [], []), ([], [], [])]
        # First read returns output, second read returns empty (EOF)
        mock_proc.stdout.read.side_effect = ["Hello, World!\n", ""]
        mock_proc.stderr.read.return_value = ""

        output_lines = []

        def output_handler(line):
            output_lines.append(line)

        stdout, _stderr = claude_exec_streaming(
            prompt="Test prompt",
            repo_root=self.repo_root,
            allow_unsafe_execution=True,
            dry_run=False,
            on_output=output_handler,
        )

        self.assertEqual(stdout, "Hello, World!")
        self.assertEqual(output_lines, ["Hello, World!"])

    @patch("tools.auto_prd.agents.popen_streaming")
    @patch("tools.auto_prd.agents.verify_unsafe_execution_ready")
    @patch("tools.auto_prd.agents._set_nonblocking")
    def test_io_error_handling_during_nonblocking_setup(
        self, mock_nonblock, _mock_verify, mock_popen
    ):
        """Test that OSError during non-blocking setup is properly propagated."""
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdin.write = MagicMock()
        mock_proc.stdin.close = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.fileno.return_value = 3
        mock_proc.stdout.close = MagicMock()
        mock_proc.stderr = MagicMock()
        mock_proc.stderr.fileno.return_value = 4
        mock_proc.stderr.close = MagicMock()
        mock_proc.kill = MagicMock()
        mock_proc.wait = MagicMock()
        mock_popen.return_value = (mock_proc, ["claude", "--print"])

        mock_nonblock.side_effect = OSError("Failed to set non-blocking")

        with self.assertRaises(OSError) as context:
            claude_exec_streaming(
                prompt="Test prompt",
                repo_root=self.repo_root,
                allow_unsafe_execution=True,
                dry_run=False,
            )
        self.assertIn("non-blocking", str(context.exception))
        mock_proc.kill.assert_called_once()
        mock_proc.wait.assert_called_once()

    @patch("tools.auto_prd.agents.popen_streaming")
    @patch("tools.auto_prd.agents.verify_unsafe_execution_ready")
    @patch("tools.auto_prd.agents._set_nonblocking")
    @patch("tools.auto_prd.agents.select.select")
    def test_nonzero_exit_code_raises_called_process_error(
        self, mock_select, _mock_nonblock, _mock_verify, mock_popen
    ):
        """Test that non-zero exit code raises CalledProcessError."""
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdin.write = MagicMock()
        mock_proc.stdin.close = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.fileno.return_value = 3
        mock_proc.stderr = MagicMock()
        mock_proc.stderr.fileno.return_value = 4
        mock_proc.stdout.close = MagicMock()
        mock_proc.stderr.close = MagicMock()
        mock_proc.returncode = 1
        mock_proc.wait = MagicMock()
        mock_popen.return_value = (mock_proc, ["claude", "--print"])

        mock_proc.poll.return_value = 1
        mock_select.return_value = ([], [], [])
        mock_proc.stdout.read.return_value = ""
        mock_proc.stderr.read.return_value = "Error occurred"

        with self.assertRaises(subprocess.CalledProcessError) as context:
            claude_exec_streaming(
                prompt="Test prompt",
                repo_root=self.repo_root,
                allow_unsafe_execution=True,
                dry_run=False,
            )
        self.assertEqual(context.exception.returncode, 1)


class ProcessBufferTests(unittest.TestCase):
    """Test suite for _process_buffer helper function."""

    def test_empty_buffer_returns_empty(self):
        """Test _process_buffer with empty buffer returns empty string."""
        lines: list[str] = []
        result = _process_buffer("", lines)
        self.assertEqual(result, "")
        self.assertEqual(lines, [])

    def test_no_newlines_returns_input_unchanged(self):
        """Test _process_buffer with no newlines returns input unchanged."""
        lines: list[str] = []
        result = _process_buffer("incomplete", lines)
        self.assertEqual(result, "incomplete")
        self.assertEqual(lines, [])

    def test_single_complete_line(self):
        """Test _process_buffer extracts single complete line."""
        lines: list[str] = []
        result = _process_buffer("complete\n", lines)
        self.assertEqual(result, "")
        self.assertEqual(lines, ["complete"])

    def test_multiple_complete_lines(self):
        """Test _process_buffer extracts all complete lines."""
        lines: list[str] = []
        result = _process_buffer("line1\nline2\nline3\n", lines)
        self.assertEqual(result, "")
        self.assertEqual(lines, ["line1", "line2", "line3"])

    def test_with_trailing_incomplete_line(self):
        """Test _process_buffer returns incomplete trailing line."""
        lines: list[str] = []
        result = _process_buffer("complete\nincomplete", lines)
        self.assertEqual(result, "incomplete")
        self.assertEqual(lines, ["complete"])

    def test_with_output_handler(self):
        """Test _process_buffer calls output handler for each line."""
        lines: list[str] = []
        handler_calls: list[str] = []

        def handler(line: str) -> None:
            handler_calls.append(line)

        result = _process_buffer("line1\nline2\n", lines, handler)
        self.assertEqual(result, "")
        self.assertEqual(lines, ["line1", "line2"])
        self.assertEqual(handler_calls, ["line1", "line2"])

    def test_empty_lines_preserved(self):
        """Test _process_buffer preserves empty lines (consecutive newlines)."""
        lines: list[str] = []
        result = _process_buffer("line1\n\nline3\n", lines)
        self.assertEqual(result, "")
        self.assertEqual(lines, ["line1", "", "line3"])


class DrainFdsBestEffortTests(unittest.TestCase):
    """Test suite for _drain_fds_best_effort helper function."""

    def test_drains_remaining_data_from_stdout(self):
        """Test _drain_fds_best_effort captures remaining stdout data."""
        mock_stdout = MagicMock()
        mock_stdout.closed = False
        mock_stdout.read.return_value = "remaining"

        stdout_buf, stderr_buf = _drain_fds_best_effort(
            [mock_stdout], mock_stdout, None, "existing", ""
        )
        self.assertEqual(stdout_buf, "existingremaining")
        self.assertEqual(stderr_buf, "")

    def test_drains_remaining_data_from_stderr(self):
        """Test _drain_fds_best_effort captures remaining stderr data."""
        mock_stderr = MagicMock()
        mock_stderr.closed = False
        mock_stderr.read.return_value = "error_remaining"

        stdout_buf, stderr_buf = _drain_fds_best_effort(
            [mock_stderr], None, mock_stderr, "", "existing_error"
        )
        self.assertEqual(stdout_buf, "")
        self.assertEqual(stderr_buf, "existing_errorerror_remaining")

    def test_skips_closed_file_descriptors(self):
        """Test _drain_fds_best_effort skips closed file descriptors."""
        mock_fd = MagicMock()
        mock_fd.closed = True

        stdout_buf, _stderr_buf = _drain_fds_best_effort(
            [mock_fd], None, None, "original", ""
        )
        self.assertEqual(stdout_buf, "original")
        mock_fd.read.assert_not_called()

    def test_handles_empty_fd_list(self):
        """Test _drain_fds_best_effort with empty fd list."""
        stdout_buf, stderr_buf = _drain_fds_best_effort([], None, None, "buf1", "buf2")
        self.assertEqual(stdout_buf, "buf1")
        self.assertEqual(stderr_buf, "buf2")

    def test_handles_read_exception_gracefully(self):
        """Test _drain_fds_best_effort catches read exceptions."""
        mock_fd = MagicMock()
        mock_fd.closed = False
        mock_fd.read.side_effect = OSError("Read failed")

        # Should not raise - errors are logged and ignored
        stdout_buf, stderr_buf = _drain_fds_best_effort(
            [mock_fd], mock_fd, None, "", ""
        )
        self.assertEqual(stdout_buf, "")
        self.assertEqual(stderr_buf, "")


class ResolveUnsafeFlagTests(unittest.TestCase):
    """Test suite for _resolve_unsafe_flag helper function."""

    def test_allow_unsafe_execution_true(self):
        """Test _resolve_unsafe_flag with allow_unsafe_execution=True."""
        result = _resolve_unsafe_flag(True, None, "test_caller")
        self.assertTrue(result)

    def test_allow_unsafe_execution_false(self):
        """Test _resolve_unsafe_flag with allow_unsafe_execution=False."""
        result = _resolve_unsafe_flag(False, None, "test_caller")
        self.assertFalse(result)

    def test_both_none_returns_false(self):
        """Test _resolve_unsafe_flag with both None returns False."""
        result = _resolve_unsafe_flag(None, None, "test_caller")
        self.assertFalse(result)

    def test_yolo_alone_returns_true(self):
        """Test _resolve_unsafe_flag with yolo=True alone."""
        with patch("tools.auto_prd.agents.logger") as mock_logger:
            result = _resolve_unsafe_flag(None, True, "test_caller")
            self.assertTrue(result)
            mock_logger.warning.assert_called()

    def test_yolo_false_returns_false(self):
        """Test _resolve_unsafe_flag with yolo=False returns False."""
        with patch("tools.auto_prd.agents.logger"):
            result = _resolve_unsafe_flag(None, False, "test_caller")
            self.assertFalse(result)

    def test_both_set_uses_or_logic(self):
        """Test _resolve_unsafe_flag ORs both values when both set."""
        with patch("tools.auto_prd.agents.logger"):
            # False OR True = True
            result = _resolve_unsafe_flag(False, True, "test_caller")
            self.assertTrue(result)

            # True OR False = True
            result = _resolve_unsafe_flag(True, False, "test_caller")
            self.assertTrue(result)


class BuildClaudeArgsTests(unittest.TestCase):
    """Test suite for _build_claude_args helper function."""

    def test_basic_args_without_flags(self):
        """Test _build_claude_args generates basic args."""
        args = _build_claude_args(
            allow_flag=False, model=None, enable_search=True, extra=None
        )
        self.assertEqual(args, ["claude", "-p", "-"])

    def test_with_allow_flag(self):
        """Test _build_claude_args adds --dangerously-skip-permissions."""
        args = _build_claude_args(
            allow_flag=True, model=None, enable_search=True, extra=None
        )
        self.assertIn("--dangerously-skip-permissions", args)
        self.assertEqual(args[0], "claude")
        self.assertEqual(args[-2:], ["-p", "-"])

    def test_with_model(self):
        """Test _build_claude_args adds model flag."""
        args = _build_claude_args(
            allow_flag=False, model="claude-3-opus", enable_search=True, extra=None
        )
        self.assertIn("--model", args)
        model_idx = args.index("--model")
        self.assertEqual(args[model_idx + 1], "claude-3-opus")

    def test_with_extra_args(self):
        """Test _build_claude_args appends extra args."""
        args = _build_claude_args(
            allow_flag=False, model=None, enable_search=True, extra=["--verbose", "-v"]
        )
        self.assertIn("--verbose", args)
        self.assertIn("-v", args)
        # Extra args should be before the final -p -
        self.assertEqual(args[-2:], ["-p", "-"])

    def test_p_stdin_always_at_end(self):
        """Test _build_claude_args always ends with -p -."""
        args = _build_claude_args(
            allow_flag=True,
            model="claude-3-sonnet",
            enable_search=True,
            extra=["--debug"],
        )
        self.assertEqual(args[-2:], ["-p", "-"])

    # Tests for allowed_tools parameter
    def test_with_allowed_tools_list(self):
        """Test _build_claude_args adds --allowedTools for each tool."""
        tools = ["Read", "Edit", "Write"]
        args = _build_claude_args(
            allow_flag=False,
            model=None,
            enable_search=True,
            extra=None,
            allowed_tools=tools,
        )
        # Each tool should have its own --allowedTools argument
        self.assertEqual(args.count("--allowedTools"), 3)
        self.assertIn("Read", args)
        self.assertIn("Edit", args)
        self.assertIn("Write", args)
        # Verify structure: --allowedTools followed by tool name
        for tool in tools:
            tool_idx = args.index(tool)
            self.assertEqual(args[tool_idx - 1], "--allowedTools")

    def test_with_allowed_tools_empty_list(self):
        """Test _build_claude_args with empty allowed_tools list adds no args."""
        args = _build_claude_args(
            allow_flag=False,
            model=None,
            enable_search=True,
            extra=None,
            allowed_tools=[],
        )
        self.assertNotIn("--allowedTools", args)
        self.assertEqual(args, ["claude", "-p", "-"])

    def test_with_allowed_tools_none(self):
        """Test _build_claude_args with None allowed_tools adds no args."""
        args = _build_claude_args(
            allow_flag=False,
            model=None,
            enable_search=True,
            extra=None,
            allowed_tools=None,
        )
        self.assertNotIn("--allowedTools", args)

    def test_allowed_tools_non_list_raises_type_error(self):
        """Test _build_claude_args raises TypeError for non-list allowed_tools."""
        with self.assertRaises(TypeError) as ctx:
            _build_claude_args(
                allow_flag=False,
                model=None,
                enable_search=True,
                extra=None,
                allowed_tools="Read",  # String, not list
            )
        self.assertIn("allowed_tools", str(ctx.exception))
        self.assertIn("list or tuple", str(ctx.exception))

    def test_allowed_tools_non_string_elements_raises_type_error(self):
        """Test _build_claude_args raises TypeError when allowed_tools contains non-strings."""
        with self.assertRaises(TypeError) as ctx:
            _build_claude_args(
                allow_flag=False,
                model=None,
                enable_search=True,
                extra=None,
                allowed_tools=["Read", 123, "Write"],  # 123 is not a string
            )
        self.assertIn("allowed_tools", str(ctx.exception))
        self.assertIn("strings", str(ctx.exception))

    def test_allowed_tools_tuple_accepted(self):
        """Test _build_claude_args accepts tuple for allowed_tools."""
        tools = ("Read", "Edit")
        args = _build_claude_args(
            allow_flag=False,
            model=None,
            enable_search=True,
            extra=None,
            allowed_tools=tools,
        )
        self.assertEqual(args.count("--allowedTools"), 2)

    # Tests for system_prompt_suffix parameter
    def test_with_system_prompt_suffix(self):
        """Test _build_claude_args adds --append-system-prompt for suffix."""
        suffix = "Previous context: Task completed successfully."
        args = _build_claude_args(
            allow_flag=False,
            model=None,
            enable_search=True,
            extra=None,
            system_prompt_suffix=suffix,
        )
        self.assertIn("--append-system-prompt", args)
        prompt_idx = args.index("--append-system-prompt")
        self.assertEqual(args[prompt_idx + 1], suffix)

    def test_with_system_prompt_suffix_none(self):
        """Test _build_claude_args with None suffix adds no args."""
        args = _build_claude_args(
            allow_flag=False,
            model=None,
            enable_search=True,
            extra=None,
            system_prompt_suffix=None,
        )
        self.assertNotIn("--append-system-prompt", args)

    def test_with_system_prompt_suffix_empty_string(self):
        """Test _build_claude_args with empty suffix adds no args."""
        args = _build_claude_args(
            allow_flag=False,
            model=None,
            enable_search=True,
            extra=None,
            system_prompt_suffix="",
        )
        self.assertNotIn("--append-system-prompt", args)

    def test_with_system_prompt_suffix_multiline(self):
        """Test _build_claude_args handles multiline suffix correctly."""
        suffix = "Line 1\nLine 2\nLine 3"
        args = _build_claude_args(
            allow_flag=False,
            model=None,
            enable_search=True,
            extra=None,
            system_prompt_suffix=suffix,
        )
        prompt_idx = args.index("--append-system-prompt")
        self.assertEqual(args[prompt_idx + 1], suffix)
        self.assertIn("\n", args[prompt_idx + 1])

    def test_with_system_prompt_suffix_special_characters(self):
        """Test _build_claude_args handles special characters in suffix."""
        suffix = "Context: $var, 'quotes', \"double\", <tags>"
        args = _build_claude_args(
            allow_flag=False,
            model=None,
            enable_search=True,
            extra=None,
            system_prompt_suffix=suffix,
        )
        prompt_idx = args.index("--append-system-prompt")
        self.assertEqual(args[prompt_idx + 1], suffix)

    # Tests for output_format parameter
    def test_with_output_format_json(self):
        """Test _build_claude_args adds --output-format for json."""
        args = _build_claude_args(
            allow_flag=False,
            model=None,
            enable_search=True,
            extra=None,
            output_format="json",
        )
        self.assertIn("--output-format", args)
        format_idx = args.index("--output-format")
        self.assertEqual(args[format_idx + 1], "json")

    def test_with_output_format_stream_json(self):
        """Test _build_claude_args adds --output-format for stream-json."""
        args = _build_claude_args(
            allow_flag=False,
            model=None,
            enable_search=True,
            extra=None,
            output_format="stream-json",
        )
        self.assertIn("--output-format", args)
        format_idx = args.index("--output-format")
        self.assertEqual(args[format_idx + 1], "stream-json")

    def test_with_output_format_none(self):
        """Test _build_claude_args with None output_format adds no args."""
        args = _build_claude_args(
            allow_flag=False,
            model=None,
            enable_search=True,
            extra=None,
            output_format=None,
        )
        self.assertNotIn("--output-format", args)

    def test_output_format_invalid_raises_value_error(self):
        """Test _build_claude_args raises ValueError for invalid output_format."""
        with self.assertRaises(ValueError) as ctx:
            _build_claude_args(
                allow_flag=False,
                model=None,
                enable_search=True,
                extra=None,
                output_format="invalid-format",
            )
        self.assertIn("output_format", str(ctx.exception))
        self.assertIn("json", str(ctx.exception))
        self.assertIn("stream-json", str(ctx.exception))

    def test_output_format_empty_string_raises_value_error(self):
        """Test _build_claude_args raises ValueError for empty output_format."""
        with self.assertRaises(ValueError) as ctx:
            _build_claude_args(
                allow_flag=False,
                model=None,
                enable_search=True,
                extra=None,
                output_format="",
            )
        self.assertIn("output_format", str(ctx.exception))

    # Test all parameters combined
    def test_all_new_parameters_combined(self):
        """Test _build_claude_args with all new parameters together."""
        args = _build_claude_args(
            allow_flag=True,
            model="claude-3-sonnet",
            enable_search=True,
            extra=["--verbose"],
            output_format="json",
            allowed_tools=["Read", "Edit"],
            system_prompt_suffix="Previous context here",
        )
        # Verify all components are present
        self.assertIn("--dangerously-skip-permissions", args)
        self.assertIn("--model", args)
        self.assertIn("--output-format", args)
        self.assertIn("--allowedTools", args)
        self.assertIn("--append-system-prompt", args)
        self.assertIn("--verbose", args)
        # And ends with -p -
        self.assertEqual(args[-2:], ["-p", "-"])


class ClaudeHeadlessResponseTests(unittest.TestCase):
    """Test suite for ClaudeHeadlessResponse dataclass."""

    def test_from_json_valid(self):
        """Test ClaudeHeadlessResponse.from_json() with valid JSON."""
        valid_json = json.dumps(
            {
                "result": "Task completed successfully",
                "session_id": "test-session-123",
                "is_error": False,
                "total_cost_usd": 0.05,
                "duration_ms": 1500,
                "duration_api_ms": 1200,
                "num_turns": 3,
            }
        )
        response = ClaudeHeadlessResponse.from_json(valid_json)
        self.assertEqual(response.result, "Task completed successfully")
        self.assertEqual(response.session_id, "test-session-123")
        self.assertFalse(response.is_error)
        self.assertEqual(response.total_cost_usd, 0.05)
        self.assertEqual(response.duration_ms, 1500)
        self.assertEqual(response.duration_api_ms, 1200)
        self.assertEqual(response.num_turns, 3)

    def test_from_json_invalid_json(self):
        """Test ClaudeHeadlessResponse.from_json() with malformed JSON."""
        with self.assertRaises(ValueError) as ctx:
            ClaudeHeadlessResponse.from_json("not valid json {{{")
        self.assertIn("Failed to parse", str(ctx.exception))

    def test_from_json_missing_required_fields(self):
        """Test ClaudeHeadlessResponse.from_json() with missing required fields."""
        incomplete_json = json.dumps({"total_cost_usd": 0.01})
        with self.assertRaises(ValueError) as ctx:
            ClaudeHeadlessResponse.from_json(incomplete_json)
        self.assertIn("missing required fields", str(ctx.exception))

    def test_from_json_non_dict_response(self):
        """Test ClaudeHeadlessResponse.from_json() with non-dict JSON."""
        array_json = json.dumps(["item1", "item2"])
        with self.assertRaises(ValueError) as ctx:
            ClaudeHeadlessResponse.from_json(array_json)
        self.assertIn("must be an object", str(ctx.exception))

    def test_from_json_null_values(self):
        """Test ClaudeHeadlessResponse.from_json() handles null values gracefully."""
        json_with_nulls = json.dumps(
            {
                "result": None,
                "session_id": None,
                "is_error": False,
                "total_cost_usd": None,
                "duration_ms": None,
                "duration_api_ms": None,
                "num_turns": None,
            }
        )
        response = ClaudeHeadlessResponse.from_json(json_with_nulls)
        self.assertEqual(response.result, "")
        self.assertEqual(response.session_id, "")
        self.assertEqual(response.total_cost_usd, 0.0)
        self.assertEqual(response.duration_ms, 0)
        self.assertEqual(response.duration_api_ms, 0)
        self.assertEqual(response.num_turns, 0)

    def test_negative_duration_raises(self):
        """Test ClaudeHeadlessResponse raises ValueError for negative duration."""
        with self.assertRaises(ValueError) as ctx:
            ClaudeHeadlessResponse(
                result="test",
                session_id="test",
                is_error=False,
                total_cost_usd=0.0,
                duration_ms=-100,
                duration_api_ms=0,
                num_turns=0,
                raw_json={},
            )
        self.assertIn("duration_ms must be non-negative", str(ctx.exception))

    def test_negative_cost_raises(self):
        """Test ClaudeHeadlessResponse raises ValueError for negative cost."""
        with self.assertRaises(ValueError) as ctx:
            ClaudeHeadlessResponse(
                result="test",
                session_id="test",
                is_error=False,
                total_cost_usd=-0.01,
                duration_ms=0,
                duration_api_ms=0,
                num_turns=0,
                raw_json={},
            )
        self.assertIn("total_cost_usd must be non-negative", str(ctx.exception))


class ParseClaudeJsonResponseTests(unittest.TestCase):
    """Test suite for parse_claude_json_response function."""

    def test_parse_valid_json(self):
        """Test parse_claude_json_response with valid JSON."""
        valid_json = json.dumps(
            {
                "result": "Done",
                "session_id": "sess-123",
                "is_error": False,
                "total_cost_usd": 0.02,
                "duration_ms": 500,
                "duration_api_ms": 400,
                "num_turns": 1,
            }
        )
        response = parse_claude_json_response(valid_json)
        self.assertIsNotNone(response)
        self.assertEqual(response.result, "Done")
        self.assertEqual(response.session_id, "sess-123")

    def test_parse_empty_stdout_lenient(self):
        """Test parse_claude_json_response with empty stdout in lenient mode."""
        response = parse_claude_json_response("", strict=False)
        self.assertIsNone(response)

        response = parse_claude_json_response("   ", strict=False)
        self.assertIsNone(response)

    def test_parse_empty_stdout_strict(self):
        """Test parse_claude_json_response with empty stdout in strict mode."""
        with self.assertRaises(ValueError) as ctx:
            parse_claude_json_response("", strict=True)
        self.assertIn("empty", str(ctx.exception))

    def test_parse_invalid_json_lenient(self):
        """Test parse_claude_json_response returns None for invalid JSON in lenient mode."""
        response = parse_claude_json_response("not json at all", strict=False)
        self.assertIsNone(response)

    def test_parse_invalid_json_strict(self):
        """Test parse_claude_json_response raises for invalid JSON in strict mode."""
        with self.assertRaises(ValueError) as ctx:
            parse_claude_json_response("not json at all", strict=True)
        self.assertIn("Failed to parse", str(ctx.exception))

    def test_parse_sanitizes_output_preview(self):
        """Test that parse_claude_json_response sanitizes output preview in error messages."""
        # JSON with potential secrets that should be sanitized
        bad_json = '{"result": "sk-1234567890abcdefghij secret token"'  # Invalid JSON
        with self.assertRaises(ValueError) as ctx:
            parse_claude_json_response(bad_json, strict=True)
        # The error message should have the preview sanitized
        error_msg = str(ctx.exception)
        self.assertNotIn("sk-1234567890abcdefghij", error_msg)
        self.assertIn("REDACTED", error_msg)


if __name__ == "__main__":
    unittest.main()
