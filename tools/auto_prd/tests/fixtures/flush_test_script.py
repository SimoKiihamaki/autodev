#!/usr/bin/env python3
"""
Test fixture script for comprehensive stdout/stderr flushing behavior validation.
This script tests various flushing scenarios to ensure incremental output appears immediately.
"""

import sys
import tempfile
import time
from dataclasses import dataclass


@dataclass
class CmdResult:
    """Result object for command execution."""

    stdout: str
    stderr: str
    returncode: int


# Mock run_cmd for the subprocess test - use subprocess directly
def run_cmd(cmd, timeout=None, sanitize_args=True):
    """Mock run_cmd for the subprocess test."""
    import subprocess

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return result.stdout, result.stderr, result.returncode


def test_basic_flushing():
    """Test basic print with flush=True."""
    print("=== STARTING BASIC FLUSH TEST ===", flush=True)

    for i in range(10):
        print(f"Basic line {i + 1}/10", flush=True)
        time.sleep(0.1)

    print("=== BASIC FLUSH TEST COMPLETED ===", flush=True)


def test_no_flush():
    """Test print without explicit flush (should still work due to logging_utils)."""
    print("=== STARTING NO-FLUSH TEST ===")

    for i in range(5):
        print(f"No-flush line {i + 1}/5")  # No explicit flush
        time.sleep(0.1)

    print("=== NO-FLUSH TEST COMPLETED ===")


def test_mixed_output():
    """Test mixing stdout and stderr."""
    print("=== STARTING MIXED OUTPUT TEST ===", flush=True)

    for i in range(5):
        print(f"STDOUT line {i + 1}/5", flush=True)
        print(f"STDERR line {i + 1}/5", file=sys.stderr, flush=True)
        time.sleep(0.1)

    print("=== MIXED OUTPUT TEST COMPLETED ===", flush=True)


def test_large_output():
    """Test large output blocks that might trigger buffering."""
    print("=== STARTING LARGE OUTPUT TEST ===", flush=True)

    large_text = "x" * 1000  # 1KB of text

    for i in range(5):
        print(f"Large block {i + 1}/5: {large_text[:100]}...", flush=True)
        time.sleep(0.05)

    print("=== LARGE OUTPUT TEST COMPLETED ===", flush=True)


def test_rapid_succession():
    """Test rapid output without delays."""
    print("=== STARTING RAPID SUCCESSION TEST ===", flush=True)

    for i in range(50):
        print(f"Rapid line {i + 1}/50", flush=True)
        # No delay - should still appear immediately

    print("=== RAPID SUCCESSION TEST COMPLETED ===", flush=True)


def test_subprocess_output():
    """Test output from subprocess calls."""
    print("=== STARTING SUBPROCESS TEST ===", flush=True)

    # Test a simple subprocess using a temporary script file to avoid sanitize_args=False
    script_code = "for i in range(3): print(f'Subprocess line {i+1}')"
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as tmp_script:
        tmp_script.write(script_code)
        tmp_script_path = tmp_script.name
    try:
        stdout, stderr, returncode = run_cmd(
            ["python3", tmp_script_path],
        )
        result = CmdResult(stdout, stderr, returncode)

        print("Subprocess stdout:", flush=True)
        for line in result.stdout.strip().split("\n"):
            print(f"  {line}", flush=True)

        if result.stderr:
            print("Subprocess stderr:", flush=True)
            for line in result.stderr.strip().split("\n"):
                print(f"  {line}", flush=True)

        print("=== SUBPROCESS TEST COMPLETED ===", flush=True)
    finally:
        try:
            import os

            os.unlink(tmp_script_path)
        except FileNotFoundError:
            pass
        except OSError as e:
            print(
                f"Warning: Failed to clean up temporary script {tmp_script_path}: {e}",
                file=sys.stderr,
            )


if __name__ == "__main__":
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
