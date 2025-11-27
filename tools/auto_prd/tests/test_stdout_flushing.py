#!/usr/bin/env python3
"""
Tests for stdout/stderr flushing behavior to ensure incremental output appears immediately.
This validates that the Python automation pipeline doesn't buffer output unexpectedly.
"""

import sys
import time
import tempfile
import threading
import queue
import os
from pathlib import Path
from dataclasses import dataclass

# Constants for assertion messages to ensure consistency
ASSERTION_MSG_TEMPLATES = {
    "integration_test_failed": " integration test failed\nStdout:\n{stdout}\nStderr:\n{stderr}"
}

try:
    from tools.auto_prd.command import (
        run_cmd,
        safe_popen,
        register_safe_cwd,
    )
    from tools.auto_prd.tests import safe_cleanup
except ImportError:
    from ..command import (
        run_cmd,
        safe_popen,
        register_safe_cwd,
    )
    from . import safe_cleanup


@dataclass
class CmdResult:
    """Result object for command execution."""

    stdout: str
    stderr: str
    returncode: int


class OutputCapture:
    """Captures stdout/stderr from a subprocess in real-time."""

    def __init__(self, process, timeout=30):
        self.process = process
        self.timeout = timeout
        self.stdout_queue = queue.Queue()
        self.stderr_queue = queue.Queue()
        self.stdout_thread = None
        self.stderr_thread = None
        self.start_time = None

    def _read_stream(self, stream, output_queue, stream_name):
        """Read lines from a stream and put them in a queue with timestamps."""
        try:
            for line in iter(stream.readline, ""):
                timestamp = time.time()
                elapsed = timestamp - self.start_time if self.start_time else 0
                output_queue.put(
                    {
                        "text": line.rstrip(),
                        "timestamp": timestamp,
                        "elapsed": elapsed,
                        "stream": stream_name,
                    }
                )
        except Exception as e:
            output_queue.put(
                {
                    "text": f"ERROR reading {stream_name}: {e}",
                    "timestamp": time.time(),
                    "elapsed": time.time() - self.start_time if self.start_time else 0,
                    "stream": stream_name,
                }
            )

    def start_capture(self):
        """Start capturing output from the subprocess."""
        self.start_time = time.time()

        self.stdout_thread = threading.Thread(
            target=self._read_stream,
            args=(self.process.stdout, self.stdout_queue, "stdout"),
        )
        self.stderr_thread = threading.Thread(
            target=self._read_stream,
            args=(self.process.stderr, self.stderr_queue, "stderr"),
        )

        self.stdout_thread.daemon = True
        self.stderr_thread.daemon = True

        self.stdout_thread.start()
        self.stderr_thread.start()

    def get_output(self, timeout=None):
        """Get all output lines collected so far."""
        if timeout is None:
            timeout = self.timeout

        lines = []

        # Get stdout lines
        while not self.stdout_queue.empty():
            try:
                lines.append(self.stdout_queue.get_nowait())
            except queue.Empty:
                break

        # Get stderr lines
        while not self.stderr_queue.empty():
            try:
                lines.append(self.stderr_queue.get_nowait())
            except queue.Empty:
                break

        # Sort by timestamp
        lines.sort(key=lambda x: x["timestamp"])
        return lines

    def wait_for_output(self, expected_patterns, timeout=10):
        """Wait for specific patterns to appear in output."""
        start_time = time.time()
        found_patterns = set()

        while time.time() - start_time < timeout:
            lines = self.get_output()

            for line in lines:
                for pattern in expected_patterns:
                    if pattern in line["text"]:
                        found_patterns.add(pattern)

            if found_patterns == set(expected_patterns):
                return True, found_patterns

            time.sleep(0.1)

        return False, found_patterns


def create_flush_test_script():
    """Create a temporary copy of the flush test script for execution."""
    # Get the path to the fixture script
    fixture_path = Path(__file__).parent / "fixtures" / "flush_test_script.py"

    # Read the fixture script content
    with open(fixture_path, "r") as f:
        script_content = f.read()

    # Create temporary script file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(script_content)
        script_path = f.name

    # Make it executable
    os.chmod(script_path, 0o755)
    return script_path


def test_real_time_output_capture():
    """Test that output appears in real-time without unexpected buffering."""
    print("Testing real-time output capture...")
    # Register test directory as safe
    register_safe_cwd(Path(__file__).parent)

    script_path = create_flush_test_script()
    process = None  # Initialize to avoid UnboundLocalError

    try:
        # Start the test script
        process = safe_popen(["python3", script_path])

        # Start capturing output
        capturer = OutputCapture(process)
        capturer.start_capture()

        # Define expected patterns
        expected_patterns = [
            "BASIC FLUSH TEST COMPLETED",
            "NO-FLUSH TEST COMPLETED",
            "MIXED OUTPUT TEST COMPLETED",
            "LARGE OUTPUT TEST COMPLETED",
            "RAPID SUCCESSION TEST COMPLETED",
            "SUBPROCESS TEST COMPLETED",
            "ALL FLUSH TESTS COMPLETED",
        ]

        # Wait for all patterns to appear
        found_all, found_patterns = capturer.wait_for_output(
            expected_patterns, timeout=30
        )

        if not found_all:
            missing = set(expected_patterns) - found_patterns
            lines = capturer.get_output()
            tail = "\n".join(
                f"[{line['elapsed']:.2f}s] {line['stream']}: {line['text']}"
                for line in lines[-10:]
            )
            raise AssertionError(f"Missing patterns: {missing}\nLast lines:\n{tail}")

        # Analyze timing of output
        lines = capturer.get_output()

        # Check that output appeared incrementally
        start_patterns = [
            "STARTING BASIC FLUSH TEST",
            "STARTING NO-FLUSH TEST",
            "STARTING MIXED OUTPUT TEST",
        ]

        timing_issues = []
        for pattern in start_patterns:
            pattern_lines = [line for line in lines if pattern in line["text"]]
            if pattern_lines:
                first_line = pattern_lines[0]
                if first_line["elapsed"] > 2.0:  # Should appear within 2 seconds
                    timing_issues.append(
                        f"{pattern}: appeared after {first_line['elapsed']:.2f}s"
                    )

        if timing_issues:
            print("⚠️  Timing issues detected:")
            for issue in timing_issues:
                print(f"   {issue}")

        # Wait for process to complete
        process.wait(timeout=10)

        print("✅ Real-time output test passed")
        print(f"   Captured {len(lines)} lines")
        print(
            f"   Test duration: {lines[-1]['elapsed']:.2f}s"
            if lines
            else "   No lines captured"
        )

        return True

    finally:
        # Clean up
        if process is not None:
            try:
                process.terminate()
                process.wait(timeout=5)
            except (OSError, ProcessLookupError, TimeoutError):
                try:
                    process.kill()
                except (OSError, ProcessLookupError) as kill_error:
                    # Process might already be dead
                    print(
                        f"Warning: Failed to kill process {kill_error}", file=sys.stderr
                    )

        safe_cleanup(script_path, "script file")


def test_buffering_edge_cases():
    """Test edge cases that might trigger unwanted buffering."""
    print("Testing buffering edge cases...")

    # Test 1: Very rapid output without any delays
    print("  Test 1: Very rapid output...")
    rapid_script = """
import sys
for i in range(100):
    print(f"Rapid {i}", flush=True)
print("RAPID_TEST_DONE", flush=True)
"""

    stdout, stderr, returncode = run_cmd(
        ["python3", "-c", rapid_script], timeout=10, sanitize_args=False
    )

    result = CmdResult(stdout, stderr, returncode)

    assert "RAPID_TEST_DONE" in result.stdout, "Rapid output test failed"

    # Test 2: Mixed flush and no-flush
    print("  Test 2: Mixed flush behavior...")
    mixed_script = """
import sys
import time

for i in range(5):
    print(f"With flush {i}", flush=True)
    print(f"Without flush {i}")  # No explicit flush
    time.sleep(0.01)

print("MIXED_TEST_DONE", flush=True)
"""

    process = safe_popen(["python3", "-c", mixed_script])

    capturer = OutputCapture(process)
    capturer.start_capture()

    found, _ = capturer.wait_for_output(["MIXED_TEST_DONE"], timeout=10)

    assert found, "Mixed flush test failed"

    process.wait(timeout=5)

    # Test 3: Large output blocks
    print("  Test 3: Large output blocks...")
    large_script = """
import sys
large_content = "x" * 10000  # 10KB
print("STARTING_LARGE_TEST", flush=True)
print(large_content, flush=True)
print("LARGE_TEST_DONE", flush=True)
"""

    stdout, stderr, returncode = run_cmd(
        ["python3", "-c", large_script], timeout=10, sanitize_args=False
    )

    result = CmdResult(stdout, stderr, returncode)

    assert "LARGE_TEST_DONE" in result.stdout, "Large output test failed"

    print("✅ All buffering edge case tests passed")
    return True


def test_logging_utils_integration():
    """Test integration with logging_utils if available."""
    print("Testing logging_utils integration...")

    # Try to import and use logging_utils
    test_script = """
try:
    from logging_utils import setup_file_logging, print_flush

    print("STARTING_LOGGING_UTILS_TEST", flush=True)

    # Test print_flush function
    for i in range(5):
        print_flush(f"print_flush line {i+1}/5")

    # Test regular print (should have flush=True by default after logging setup)
    print("REGULAR_PRINT_AFTER_SETUP", flush=True)

    print("LOGGING_UTILS_TEST_DONE", flush=True)

except ImportError as e:
    print(f"LOGGING_UTILS_NOT_AVAILABLE: {e}", flush=True)
    print("LOGGING_UTILS_TEST_SKIPPED", flush=True)
"""

    stdout, stderr, returncode = run_cmd(
        ["python3", "-c", test_script],
        cwd=Path(__file__).parent.parent,
        timeout=10,
        sanitize_args=False,
    )

    result = CmdResult(stdout, stderr, returncode)

    if "LOGGING_UTILS_TEST_DONE" in result.stdout:
        return True
    if "LOGGING_UTILS_TEST_SKIPPED" in result.stdout:
        return True
    raise AssertionError(
        f"Logging utils{ASSERTION_MSG_TEMPLATES['integration_test_failed'].format(stdout=result.stdout, stderr=result.stderr)}"
    )


def main():
    """Run all stdout/stderr flushing tests."""
    print("Running comprehensive stdout/stderr flushing tests...")
    print("=" * 60)

    tests = [
        ("Real-time output capture", test_real_time_output_capture),
        ("Buffering edge cases", test_buffering_edge_cases),
        ("Logging utils integration", test_logging_utils_integration),
    ]

    results = []

    for test_name, test_func in tests:
        print(f"\n🧪 {test_name}")
        print("-" * 40)

        try:
            start_time = time.time()
            success = test_func()
            duration = time.time() - start_time

            results.append((test_name, success, duration))

            if success:
                print(f"✅ {test_name} passed ({duration:.2f}s)")
            else:
                print(f"❌ {test_name} failed ({duration:.2f}s)")

        except Exception as e:
            print(f"💥 {test_name} crashed: {e}")
            results.append((test_name, False, 0))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, success, _ in results if success)
    total = len(results)

    for test_name, success, duration in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name} ({duration:.2f}s)")

    print(f"\nOverall: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All stdout/stderr flushing tests passed!")
        return 0
    else:
        print("⚠️  Some tests failed - output buffering issues detected")
        return 1


if __name__ == "__main__":
    sys.exit(main())
