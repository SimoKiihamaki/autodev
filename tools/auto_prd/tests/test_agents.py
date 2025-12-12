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
claude_exec_streaming = safe_import(
    "tools.auto_prd.agents", "..agents", "claude_exec_streaming"
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
        self.assertIsNone(result)  # Default is None for claude

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
            self.assertIsNone(result)  # Falls back to default (None)

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
        # Initially no environment variables
        self.assertIsNone(get_codex_exec_timeout())
        self.assertIsNone(get_claude_exec_timeout())

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
    def test_dry_run_returns_dry_run_output(self, mock_verify, mock_popen):
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

    @unittest.skipIf(sys.platform == "win32", "fcntl not available on Windows")
    def test_os_error_on_windows_platform(self):
        """Test that OSError is raised when fcntl is not available."""
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


if __name__ == "__main__":
    unittest.main()
