#!/usr/bin/env python3
"""
Unittest-compatible tests for stdout/stderr flushing behavior.
"""

import unittest
import sys
from pathlib import Path
from dataclasses import dataclass

try:
    from tools.auto_prd.command import safe_popen, run_cmd, register_safe_cwd
except ImportError:
    from ..command import safe_popen, run_cmd, register_safe_cwd


@dataclass
class CmdResult:
    """Result object for command execution."""

    stdout: str
    stderr: str
    returncode: int


class TestStdoutFlushing(unittest.TestCase):
    """Test stdout/stderr flushing behavior."""

    def setUp(self):
        """Register the test directory as safe for command execution."""
        register_safe_cwd(Path(__file__).parent)
        # Also register Python executable directory as safe
        python_path = Path(sys.executable).parent
        register_safe_cwd(python_path)

    def test_basic_flushing(self):
        """Test that basic print with flush=True works immediately."""
        script = """
import sys
import time

print("START_TEST", flush=True)
time.sleep(0.1)
print("END_TEST", flush=True)
"""

        process = safe_popen(
            ["python3", "-c", script],
            text=True,
            bufsize=1,
        )

        stdout, stderr = process.communicate(timeout=5)

        self.assertIn("START_TEST", stdout)
        self.assertIn("END_TEST", stdout)
        self.assertEqual(process.returncode, 0)

    def test_rapid_output(self):
        """Test rapid succession of prints."""
        script = """
import sys

for i in range(20):
    print(f"LINE_{i}", flush=True)

print("RAPID_DONE", flush=True)
"""

        stdout, stderr, returncode = run_cmd(
            ["python3", "-c", script],
            timeout=10,
            sanitize_args=False,
        )
        result = CmdResult(stdout, stderr, returncode)

        self.assertIn("RAPID_DONE", result.stdout)
        self.assertEqual(
            len(result.stdout.strip().splitlines()), 21
        )  # 20 lines + 1 done line
        self.assertEqual(result.returncode, 0)

    def test_mixed_stdout_stderr(self):
        """Test mixing stdout and stderr output."""
        script = """
import sys

print("STDOUT_1", flush=True)
print("STDERR_1", file=sys.stderr, flush=True)
print("STDOUT_2", flush=True)
print("STDERR_2", file=sys.stderr, flush=True)
print("MIXED_DONE", flush=True)
"""

        process = safe_popen(
            ["python3", "-c", script],
            text=True,
            bufsize=1,
        )

        stdout, stderr = process.communicate(timeout=5)

        self.assertIn("STDOUT_1", stdout)
        self.assertIn("STDOUT_2", stdout)
        self.assertIn("MIXED_DONE", stdout)

        self.assertIn("STDERR_1", stderr)
        self.assertIn("STDERR_2", stderr)

        self.assertEqual(process.returncode, 0)

    def test_large_output_blocks(self):
        """Test large output blocks don't cause buffering issues."""
        script = """
import sys

large_content = "x" * 5000  # 5KB
print("LARGE_START", flush=True)
print(large_content, flush=True)
print("LARGE_END", flush=True)
"""

        stdout, stderr, returncode = run_cmd(
            ["python3", "-c", script],
            timeout=10,
            sanitize_args=False,
        )
        result = CmdResult(stdout, stderr, returncode)

        self.assertIn("LARGE_START", result.stdout)
        self.assertIn("LARGE_END", result.stdout)
        self.assertEqual(result.returncode, 0)

    def test_no_explicit_flush_still_works(self):
        """Test that output appears even without explicit flush (due to line buffering)."""
        script = """
import sys
import time

print("NO_FLUSH_START")
time.sleep(0.1)
print("NO_FLUSH_END")
"""

        process = safe_popen(
            ["python3", "-c", script],
            text=True,
            bufsize=1,  # Line buffered
        )

        stdout, stderr = process.communicate(timeout=5)

        # With line buffering, output should appear even without explicit flush
        self.assertIn("NO_FLUSH_START", stdout)
        self.assertIn("NO_FLUSH_END", stdout)
        self.assertEqual(process.returncode, 0)

    def test_subprocess_output_handling(self):
        """Test that subprocess calls don't block output."""
        script = """
import subprocess
import sys

print("SUBPROCESS_TEST_START", flush=True)

# Run a subprocess that produces output
result = subprocess.run(
    [sys.executable, "-c", "for i in range(3): print(f'SUB_OUT_{i}')"],
    capture_output=True,
    text=True
)

print("SUBPROCESS_OUTPUT:", flush=True)
for line in result.stdout.strip().splitlines():
    print(f"  {line}", flush=True)

print("SUBPROCESS_TEST_DONE", flush=True)
"""

        stdout, stderr, returncode = run_cmd(
            ["python3", "-c", script],
            timeout=10,
            sanitize_args=False,
        )
        result = CmdResult(stdout, stderr, returncode)

        self.assertIn("SUBPROCESS_TEST_START", result.stdout)
        self.assertIn("SUBPROCESS_TEST_DONE", result.stdout)
        self.assertIn("SUB_OUT_0", result.stdout)
        self.assertEqual(result.returncode, 0)

    def test_python_logging_integration(self):
        """Test Python logging module integration."""
        script = """
import logging
import sys

# Configure logging to output to stdout
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    stream=sys.stdout,
    force=True
)

print("LOGGING_TEST_START", flush=True)

logging.info("Log message 1")
logging.info("Log message 2")

print("LOGGING_TEST_END", flush=True)
"""

        stdout, stderr, returncode = run_cmd(
            ["python3", "-c", script],
            timeout=10,
            sanitize_args=False,
        )
        result = CmdResult(stdout, stderr, returncode)

        self.assertIn("LOGGING_TEST_START", result.stdout)
        self.assertIn("LOGGING_TEST_END", result.stdout)
        self.assertIn("Log message 1", result.stdout)
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
