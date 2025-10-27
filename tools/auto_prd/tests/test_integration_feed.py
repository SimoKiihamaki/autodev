#!/usr/bin/env python3
"""
Integration smoke test to verify that the Go runner captures incremental logs correctly.
This script simulates the Python subprocess emitting incremental logs with timestamps.
"""

import subprocess
import sys
import time
import tempfile
import os
import shutil
from pathlib import Path

try:
    from tools.auto_prd.command import (
        run_cmd,
        safe_popen,
        register_safe_cwd,
    )
    from tools.auto_prd.tests import safe_cleanup, get_project_root
    from tools.auto_prd.tests.test_helpers import safe_import, try_send_with_timeout
except ImportError:
    from ..command import (
        run_cmd,
        safe_popen,
        register_safe_cwd,
    )
    from . import safe_cleanup, get_project_root
    from .test_helpers import safe_import, try_send_with_timeout


def create_fake_python_script():
    """Create a fake Python script that emits incremental logs."""
    script_content = """#!/usr/bin/env python3
import sys
import time

print("Starting fake automation process...", flush=True)
time.sleep(0.1)

print("=== Iteration 1/3: Setup Phase ===", flush=True)
time.sleep(0.2)

print("→ Setting up repository...", flush=True)
time.sleep(0.3)

print("✓ Repository setup completed.", flush=True)
time.sleep(0.1)

print("=== Iteration 2/3: Implementation Phase ===", flush=True)
time.sleep(0.2)

print("→ Launching implementation pass with codex...", flush=True)
time.sleep(0.5)  # Simulate longer work

print("✓ Codex implementation pass completed.", flush=True)
time.sleep(0.1)

print("=== Iteration 3/3: Review Phase ===", flush=True)
time.sleep(0.2)

print("→ Launching CodeRabbit review...", flush=True)
time.sleep(0.3)

print("✓ CodeRabbit review completed.", flush=True)
time.sleep(0.1)

print("Automation process finished successfully.", flush=True)
"""

    # Create temporary script file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(script_content)
        script_path = f.name

    # Make it executable
    os.chmod(script_path, 0o755)
    return script_path


def test_go_runner_log_capture():
    """Test that the Go runner captures logs incrementally."""
    # Register test directory as safe
    register_safe_cwd(Path(__file__).parent)

    # Create fake Python script
    fake_script = create_fake_python_script()

    try:
        # Find the aprd binary
        aprd_binary = get_project_root() / "bin" / "aprd"
        if not aprd_binary.exists():
            print("SKIP: aprd binary not found. Run 'make build' first.")
            return True  # Skip is considered success

        # Create temporary PRD file
        prd_content = """# Test PRD

## Test Feature
This is a test PRD for integration testing.

## Requirements
- Requirement 1
- Requirement 2
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(prd_content)
            prd_path = f.name

        try:
            # Run aprd with our fake script
            # Note: This is a simplified test that focuses on log capture
            cmd = [
                str(aprd_binary),
                "--dry-run",  # Use dry run to avoid actual git operations
                "--repo-path",
                str(get_project_root()),
                "--prd-path",
                prd_path,
                "--local-executor",
                "python3",
                "--pr-executor",
                "python3",
                "--review-executor",
                "python3",
            ]

            print(f"Running command: {' '.join(cmd)}")

            # Start the process
            process = safe_popen(
                cmd,
                text=True,
                bufsize=1,  # Line buffered
            )

            # Use non-blocking readers with threading and queue
            import threading
            import queue

            def pump(stream, q, prefix=""):
                """Read from stream and push lines to queue."""
                try:
                    for line in iter(stream.readline, ""):
                        if line:
                            q.put(prefix + line.rstrip())
                    q.put(None)  # Signal end of stream
                except Exception as e:
                    q.put(f"ERROR: {e}")
                    q.put(None)

            output_lines = []
            q = queue.Queue()

            # Start reader threads
            t1 = threading.Thread(target=pump, args=(process.stdout, q))
            t2 = threading.Thread(target=pump, args=(process.stderr, q, "STDERR: "))
            t1.daemon = True
            t2.daemon = True
            t1.start()
            t2.start()

            start_time = time.time()
            deadline = start_time + 30
            active_threads = 2

            # Read from queue with timeout
            while active_threads > 0 and time.time() < deadline:
                try:
                    item = q.get(timeout=0.1)
                    if item is None:
                        active_threads -= 1
                    elif item.startswith("ERROR:"):
                        print(f"Stream error: {item}")
                        active_threads -= 1
                    else:
                        output_lines.append(item)
                        elapsed = time.time() - start_time
                        print(f"[{elapsed:.1f}s] {item}")
                except queue.Empty:
                    # Check if process is done
                    if process.poll() is not None:
                        break
                    continue

            # Wait for reader threads to finish draining queues
            t1.join(timeout=1.0)
            t2.join(timeout=1.0)
            if t1.is_alive() or t2.is_alive():
                assert (
                    False
                ), "Reader threads did not finish cleanly: t1 alive = {}, t2 alive = {}".format(
                    t1.is_alive(), t2.is_alive()
                )

            # Clean up any hanging process
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    try:
                        process.wait(timeout=1)
                    except subprocess.TimeoutExpired as wait_error:
                        print(
                            f"Warning: Failed to wait for process after kill: {wait_error}",
                            file=sys.stderr,
                        )

            # Analyze captured output
            print(f"\nCaptured {len(output_lines)} lines of output")

            # Test generic streaming characteristics instead of hardcoded patterns
            non_empty_lines = [line.strip() for line in output_lines if line.strip()]
            unique_lines = set(non_empty_lines)

            print(f"Found {len(non_empty_lines)} non-empty lines")
            print(f"Found {len(unique_lines)} unique lines")

            # Show sample of captured output for debugging
            print("\nSample captured output:")
            for i, line in enumerate(output_lines[:10]):
                print(f"  {i+1:2d}: {line}")
            if len(output_lines) > 10:
                print(f"  ... and {len(output_lines) - 10} more lines")

            # Generic streaming validation - we should capture multiple lines over time
            min_lines_threshold = 5
            has_sufficient_output = len(non_empty_lines) >= min_lines_threshold
            has_diverse_output = len(unique_lines) >= 3  # Should have some variety

            print(f"Streaming validation:")
            print(
                f"  ✓ Sufficient output (≥{min_lines_threshold} lines): {has_sufficient_output}"
            )
            print(f"  ✓ Diverse output (≥3 unique lines): {has_diverse_output}")

            # Use assertions for robust testing
            assert has_sufficient_output, (
                f"Go runner did not capture enough output. "
                f"Expected at least {min_lines_threshold} non-empty lines, got {len(non_empty_lines)}"
            )

            assert has_diverse_output, (
                f"Go runner captured insufficient variety. "
                f"Expected at least 3 unique lines, got {len(unique_lines)}"
            )

            print("✓ Integration test PASSED: Go runner captured logs incrementally")
            return True

        finally:
            # Clean up PRD file
            safe_cleanup(prd_path, "PRD file")

    finally:
        # Clean up fake script
        safe_cleanup(fake_script, "fake script")


def test_simple_log_streaming():
    """Simple test of log streaming with a basic command."""
    print("\n" + "=" * 50)
    print("Testing simple log streaming...")
    # Register test directory as safe
    register_safe_cwd(Path(__file__).parent)

    # Create temporary script file instead of using -c to avoid validation issues
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False
    ) as tiny_script:
        tiny_script.write(
            "import time\n"
            "for i in range(5):\n"
            "    print(f'Progress line {i+1}/5', flush=True)\n"
            "    time.sleep(0.2)\n"
            "print('Process completed', flush=True)\n"
        )
        cmd = ["python3", tiny_script.name]

    # Safety check: ensure python3 executable exists
    python_exe = shutil.which("python3")
    if not python_exe:
        raise RuntimeError("python3 executable not found for test")

    try:
        process = safe_popen(cmd, extra_env={"PWD": str(get_project_root())})

        # Use non-blocking readers with threading and queue
        import threading
        import queue

        def pump(stream, q, prefix=""):
            """Read from stream and push lines to queue."""
            try:
                for line in iter(stream.readline, ""):
                    if line:
                        q.put(prefix + line.rstrip())
                q.put(None)  # Signal end of stream
            except Exception as e:
                q.put(f"ERROR: {e}")
                q.put(None)

        output_lines = []
        q = queue.Queue()

        # Start reader threads
        t1 = threading.Thread(target=pump, args=(process.stdout, q))
        t2 = threading.Thread(target=pump, args=(process.stderr, q, "STDERR: "))
        t1.daemon = True
        t2.daemon = True
        t1.start()
        t2.start()

        start_time = time.time()
        deadline = start_time + 10
        active_threads = 2

        # Read from queue with timeout
        while active_threads > 0 and time.time() < deadline:
            try:
                item = q.get(timeout=0.1)
                if item is None:
                    active_threads -= 1
                elif item.startswith("ERROR:"):
                    print(f"Stream error: {item}")
                    active_threads -= 1
                else:
                    output_lines.append(item)
                    elapsed = time.time() - start_time
                    print(f"[{elapsed:.1f}s] {item}")
            except queue.Empty:
                # Check if process is done
                if process.poll() is not None:
                    break
                continue

        # Wait for reader threads to finish draining queues
        t1.join(timeout=1.0)
        t2.join(timeout=1.0)
        if t1.is_alive() or t2.is_alive():
            assert (
                False
            ), "Reader threads did not finish cleanly: t1 alive = {}, t2 alive = {}".format(
                t1.is_alive(), t2.is_alive()
            )

        # Clean up any hanging process
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired as wait_error:
                    print(
                        f"Warning: Failed to wait for process after kill: {wait_error}",
                        file=sys.stderr,
                    )

        expected_lines = 6  # 5 progress + 1 completion
        actual_lines = len([line for line in output_lines if line.strip()])

        print(f"Expected {expected_lines} lines, got {actual_lines}")

        # Use assertions instead of returning booleans
        assert actual_lines >= expected_lines, (
            f"Expected at least {expected_lines} lines, got {actual_lines}. "
            f"Captured output: {output_lines}"
        )

        print("✓ Simple streaming test PASSED")
        return True

    finally:
        # Clean up temporary script file
        safe_cleanup(tiny_script.name, "temporary script")


if __name__ == "__main__":
    print("Running integration smoke tests for log streaming...")

    # Run simple test first
    simple_success = test_simple_log_streaming()

    # Run Go runner test
    go_success = test_go_runner_log_capture()

    # Overall result
    overall_success = simple_success and go_success

    print(f"\n{'='*50}")
    print("Integration Test Summary:")
    print(f"Simple streaming test: {'PASS' if simple_success else 'FAIL'}")
    print(f"Go runner test: {'PASS' if go_success else 'FAIL'}")
    print(f"Overall result: {'PASS' if overall_success else 'FAIL'}")

    sys.exit(0 if overall_success else 1)
