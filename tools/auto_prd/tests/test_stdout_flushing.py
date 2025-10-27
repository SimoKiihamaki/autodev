#!/usr/bin/env python3
"""
Tests for stdout/stderr flushing behavior to ensure incremental output appears immediately.
This validates that the Python automation pipeline doesn't buffer output unexpectedly.
"""

import subprocess
import sys
import time
import tempfile
import threading
import queue
import os
from pathlib import Path

from tools.auto_prd.command import (
    run_cmd,
    validate_command_args,
    validate_cwd,
    env_with_zsh,
)


def safe_popen(cmd, *, text=True, bufsize=1):
    """Safe wrapper for subprocess.Popen using validation from command.py."""
    validate_command_args(cmd)
    validate_cwd(None)

    env = env_with_zsh()
    return subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=text,
        bufsize=bufsize,
        env=env,
    )


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
    """Create a Python script that tests various flushing scenarios."""
    script_content = '''#!/usr/bin/env python3
import sys
import time

def test_basic_flushing():
    """Test basic print with flush=True."""
    print("=== STARTING BASIC FLUSH TEST ===", flush=True)

    for i in range(10):
        print(f"Basic line {i+1}/10", flush=True)
        time.sleep(0.1)

    print("=== BASIC FLUSH TEST COMPLETED ===", flush=True)

def test_no_flush():
    """Test print without explicit flush (should still work due to logging_utils)."""
    print("=== STARTING NO-FLUSH TEST ===")

    for i in range(5):
        print(f"No-flush line {i+1}/5")  # No explicit flush
        time.sleep(0.1)

    print("=== NO-FLUSH TEST COMPLETED ===")

def test_mixed_output():
    """Test mixing stdout and stderr."""
    print("=== STARTING MIXED OUTPUT TEST ===", flush=True)

    for i in range(5):
        print(f"STDOUT line {i+1}/5", flush=True)
        print(f"STDERR line {i+1}/5", file=sys.stderr, flush=True)
        time.sleep(0.1)

    print("=== MIXED OUTPUT TEST COMPLETED ===", flush=True)

def test_large_output():
    """Test large output blocks that might trigger buffering."""
    print("=== STARTING LARGE OUTPUT TEST ===", flush=True)

    large_text = "x" * 1000  # 1KB of text

    for i in range(5):
        print(f"Large block {i+1}/5: {large_text[:100]}...", flush=True)
        time.sleep(0.05)

    print("=== LARGE OUTPUT TEST COMPLETED ===", flush=True)

def test_rapid_succession():
    """Test rapid output without delays."""
    print("=== STARTING RAPID SUCCESSION TEST ===", flush=True)

    for i in range(50):
        print(f"Rapid line {i+1}/50", flush=True)
        # No delay - should still appear immediately

    print("=== RAPID SUCCESSION TEST COMPLETED ===", flush=True)

def test_subprocess_output():
    """Test output from subprocess calls."""
    print("=== STARTING SUBPROCESS TEST ===", flush=True)

    # Test a simple subprocess
    stdout, stderr, returncode = run_cmd([sys.executable, "-c",
                                         "for i in range(3): print(f'Subprocess line {i+1}')"])

    # Create a result object for compatibility
    class Result:
        def __init__(self, stdout, stderr, returncode):
            self.stdout = stdout
            self.stderr = stderr
            self.returncode = returncode

    result = Result(stdout, stderr, returncode)

    print("Subprocess stdout:", flush=True)
    for line in result.stdout.strip().split('\\n'):
        print(f"  {line}", flush=True)

    if result.stderr:
        print("Subprocess stderr:", flush=True)
        for line in result.stderr.strip().split('\\n'):
            print(f"  {line}", flush=True)

    print("=== SUBPROCESS TEST COMPLETED ===", flush=True)

if __name__ == "__main__":
    import subprocess

    print("=== COMPREHENSIVE FLUSH TESTING STARTED ===", flush=True)

    test_basic_flushing()
    time.sleep(0.5)

    test_no_flush()
    time.sleep(0.5)

    test_mixed_output()
    time.sleep(0.5)

    test_large_output()
    time.sleep(0.5)

    test_rapid_succession()
    time.sleep(0.5)

    test_subprocess_output()

    print("=== ALL FLUSH TESTS COMPLETED ===", flush=True)
'''

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

    script_path = create_flush_test_script()

    try:
        # Start the test script
        process = safe_popen([sys.executable, script_path])

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
            print(f"❌ Missing patterns: {missing}")

            # Show what we got
            lines = capturer.get_output()
            print(f"Captured {len(lines)} lines total")
            for line in lines[-10:]:  # Show last 10 lines
                print(f"  [{line['elapsed']:.2f}s] {line['stream']}: {line['text']}")

            return False

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
            print(f"⚠️  Timing issues detected:")
            for issue in timing_issues:
                print(f"   {issue}")

        # Wait for process to complete
        process.wait(timeout=10)

        print(f"✅ Real-time output test passed")
        print(f"   Captured {len(lines)} lines")
        print(
            f"   Test duration: {lines[-1]['elapsed']:.2f}s"
            if lines
            else "   No lines captured"
        )

        return True

    finally:
        # Clean up
        try:
            process.terminate()
            process.wait(timeout=5)
        except (OSError, ProcessLookupError, TimeoutError) as e:
            try:
                process.kill()
            except (OSError, ProcessLookupError) as kill_error:
                # Process might already be dead
                pass

        try:
            os.unlink(script_path)
        except (OSError, FileNotFoundError) as e:
            # File might already be deleted
            pass


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
        [sys.executable, "-c", rapid_script], timeout=10
    )

    # Create a result object for compatibility
    class Result:
        def __init__(self, stdout, stderr, returncode):
            self.stdout = stdout
            self.stderr = stderr
            self.returncode = returncode

    result = Result(stdout, stderr, returncode)

    if "RAPID_TEST_DONE" not in result.stdout:
        print("❌ Rapid output test failed")
        return False

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

    process = safe_popen([sys.executable, "-c", mixed_script])

    capturer = OutputCapture(process)
    capturer.start_capture()

    found, _ = capturer.wait_for_output(["MIXED_TEST_DONE"], timeout=10)

    if not found:
        print("❌ Mixed flush test failed")
        process.terminate()
        return False

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
        [sys.executable, "-c", large_script], timeout=10
    )

    # Create a result object for compatibility
    class Result:
        def __init__(self, stdout, stderr, returncode):
            self.stdout = stdout
            self.stderr = stderr
            self.returncode = returncode

    result = Result(stdout, stderr, returncode)

    if "LARGE_TEST_DONE" not in result.stdout:
        print("❌ Large output test failed")
        return False

    print("✅ All buffering edge case tests passed")
    return True


def test_logging_utils_integration():
    """Test integration with logging_utils if available."""
    print("Testing logging_utils integration...")

    # Try to import and use logging_utils
    test_script = """
try:
    import sys
    sys.path.insert(0, ".")

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
        [sys.executable, "-c", test_script],
        cwd=Path(__file__).parent.parent,
        timeout=10,
    )

    # Create a result object for compatibility
    class Result:
        def __init__(self, stdout, stderr, returncode):
            self.stdout = stdout
            self.stderr = stderr
            self.returncode = returncode

    result = Result(stdout, stderr, returncode)

    if "LOGGING_UTILS_TEST_DONE" in result.stdout:
        print("✅ Logging utils integration test passed")
        return True
    elif "LOGGING_UTILS_TEST_SKIPPED" in result.stdout:
        print("ℹ️  Logging utils not available, test skipped")
        return True
    else:
        print("❌ Logging utils integration test failed")
        print(f"Stdout: {result.stdout}")
        print(f"Stderr: {result.stderr}")
        return False


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
