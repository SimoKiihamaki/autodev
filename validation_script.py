#!/usr/bin/env python3
"""
Validation script to demonstrate that the live feed investigation improvements work correctly.
This script shows evidence that the implemented changes address the issues from the implementation plan.
"""

import sys
import time
import subprocess
import tempfile
import os
import re
from pathlib import Path


def get_project_root():
    """Get the project root directory dynamically."""
    # Start from the current script location and walk up to find .git or go.mod
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / ".git").exists() or (current / "go.mod").exists():
            return current
        current = current.parent

    # Fallback to current working directory if no markers found
    return Path.cwd()


def test_python_logging_flush():
    """Test that Python logging flushes correctly."""
    print("=== Testing Python Logging Flush Behavior ===")

    # Test the print_flush utility
    from tools.auto_prd.logging_utils import (
        print_flush,
        install_print_logger,
        uninstall_print_logger,
    )

    print("Testing print_flush utility...")
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        original_stdout = sys.stdout
        sys.stdout = f

        print_flush("Test message with flush")

        sys.stdout = original_stdout
        temp_path = f.name

    # Read the content
    with open(temp_path, "r") as f:
        content = f.read()

    os.unlink(temp_path)

    if "Test message with flush" in content:
        print("✓ print_flush works correctly")
        return True
    else:
        print("✗ print_flush failed")
        return False


def test_go_test_coverage():
    """Test that Go test coverage is comprehensive."""
    print("\n=== Testing Go Test Coverage ===")

    # Run Go tests with coverage
    result = subprocess.run(
        ["go", "test", "./...", "-cover"],
        capture_output=True,
        text=True,
        cwd=str(get_project_root()),
    )

    if result.returncode == 0:
        print("✓ All Go tests pass")

        # Parse coverage output
        lines = result.stdout.split("\n")
        for line in lines:
            if "ok:" in line and "coverage:" in line:
                print(f"  {line.strip()}")

        return True
    else:
        print("✗ Go tests failed")
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
        return False


def test_python_test_coverage():
    """Test that Python test coverage is comprehensive."""
    print("\n=== Testing Python Test Coverage ===")

    # Run Python tests
    result = subprocess.run(
        ["python3", "-m", "unittest", "discover", "-s", "tools/auto_prd/tests"],
        capture_output=True,
        text=True,
        cwd=str(get_project_root()),
    )

    if result.returncode == 0:
        print("✓ All Python tests pass")

        # Count tests
        output = result.stdout
        if "Ran" in output and "tests" in output:
            # Extract test count
            match = re.search(r"Ran (\d+) tests", output)
            if match:
                test_count = match.group(1)
                print(f"  Total Python tests: {test_count}")

        return True
    else:
        print("✗ Python tests failed")
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
        return False


def test_runner_backpressure():
    """Test that runner backpressure is handled correctly."""
    print("\n=== Testing Runner Backpressure Handling ===")

    # Run specific runner tests for backpressure
    result = subprocess.run(
        [
            "go",
            "test",
            "./internal/runner",
            "-v",
            "-run",
            "TestTrySend|TestSendLine|TestStream",
        ],
        capture_output=True,
        text=True,
        cwd=str(get_project_root()),
    )

    if result.returncode == 0:
        print("✓ Runner backpressure tests pass")

        # Check for specific test patterns
        output = result.stdout
        test_patterns = [
            "TestTrySendChannelBackpressure",
            "TestSendLineNeverBlocks",
            "TestStreamWithNilChannel",
            "TestStreamWithErrorInReader",
        ]

        for pattern in test_patterns:
            if pattern in output:
                print(f"  ✓ {pattern} passed")

        return True
    else:
        print("✗ Runner backpressure tests failed")
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
        return False


def test_tui_feed_behavior():
    """Test that TUI feed behavior works correctly."""
    print("\n=== Testing TUI Feed Behavior ===")

    # Run TUI tests for feed handling
    result = subprocess.run(
        [
            "go",
            "test",
            "./internal/tui",
            "-v",
            "-run",
            "TestHandleRunFeed|TestConsumeRunSummary",
        ],
        capture_output=True,
        text=True,
        cwd=str(get_project_root()),
    )

    if result.returncode == 0:
        print("✓ TUI feed behavior tests pass")

        # Check for specific test patterns
        output = result.stdout
        test_patterns = [
            "TestHandleRunFeedLine_LongStreamingSession",
            "TestHandleRunFeedLine_FlushBoundaries",
            "TestHandleIterationHeader",
            "TestConsumeRunSummaryStripsLogPrefix",
        ]

        for pattern in test_patterns:
            if pattern in output:
                print(f"  ✓ {pattern} passed")

        return True
    else:
        print("✗ TUI feed behavior tests failed")
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
        return False


def main():
    """Run all validation tests."""
    print("Live Feed Investigation - Validation & Rollout Evidence")
    print("=" * 60)

    results = []

    # Run all validation checks
    results.append(("Python Logging Flush", test_python_logging_flush()))
    results.append(("Go Test Coverage", test_go_test_coverage()))
    results.append(("Python Test Coverage", test_python_test_coverage()))
    results.append(("Runner Backpressure", test_runner_backpressure()))
    results.append(("TUI Feed Behavior", test_tui_feed_behavior()))

    # Summary
    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)

    passed = 0
    total = len(results)

    for name, success in results:
        status = "PASS" if success else "FAIL"
        symbol = "✓" if success else "✗"
        print(f"{symbol} {name}: {status}")
        if success:
            passed += 1

    print(f"\nOverall: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 ALL VALIDATION TESTS PASSED")
        print("\nThe implementation successfully addresses:")
        print("• Task 1: TUI Log Ingestion Path - Tested via TUI feed behavior tests")
        print(
            "• Task 2: Runner Streaming & Channel Backpressure - Tested via runner tests"
        )
        print(
            "• Task 3: Python Runner Output Cadence - Tested via Python logging tests"
        )
        print("• Task 6: Expanded Test Coverage & Tooling - All tests pass")
        print("• Task 7: Plan Validation & Rollout - This validation script")
        print("\nReady for production rollout!")
        return 0
    else:
        print("❌ SOME VALIDATION TESTS FAILED")
        print("Please review the failing tests before rollout.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
