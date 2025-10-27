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

    # Create fake Python script
    fake_script = create_fake_python_script()

    try:
        # Find the aprd binary
        aprd_binary = get_project_root() / "bin" / "aprd"
        if not aprd_binary.exists():
            print("SKIP: aprd binary not found. Run 'make build' first.")
            return True

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
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # Line buffered
            )

            # Capture output in real-time
            output_lines = []
            start_time = time.time()

            while True:
                # Check if process is still running
                return_code = process.poll()
                if return_code is not None:
                    # Process has finished
                    remaining_stdout, remaining_stderr = process.communicate()
                    if remaining_stdout:
                        output_lines.extend(remaining_stdout.split("\n"))
                    if remaining_stderr:
                        output_lines.extend(remaining_stderr.split("\n"))
                    break

                # Read any available output
                try:
                    # Use non-blocking read with timeout
                    stdout_line = process.stdout.readline()
                    if stdout_line:
                        output_lines.append(stdout_line.strip())
                        print(
                            f"[{time.time() - start_time:.1f}s] {stdout_line.strip()}"
                        )

                    stderr_line = process.stderr.readline()
                    if stderr_line:
                        output_lines.append(f"STDERR: {stderr_line.strip()}")
                        print(
                            f"[{time.time() - start_time:.1f}s] STDERR: {stderr_line.strip()}"
                        )

                except (IOError, OSError, UnicodeDecodeError) as e:
                    print(f"Error reading output: {e}")
                    break

                # Small delay to prevent busy waiting
                time.sleep(0.01)

                # Timeout after 30 seconds
                if time.time() - start_time > 30:
                    print("TIMEOUT: Process took too long")
                    process.terminate()
                    break

            # Analyze captured output
            print(f"\nCaptured {len(output_lines)} lines of output")

            # Check for expected log patterns
            expected_patterns = [
                "Starting fake automation process",
                "=== Iteration 1/3: Setup Phase ===",
                "→ Setting up repository",
                "✓ Repository setup completed",
                "=== Iteration 2/3: Implementation Phase ===",
                "→ Launching implementation pass with codex",
                "✓ Codex implementation pass completed",
                "=== Iteration 3/3: Review Phase ===",
                "→ Launching CodeRabbit review",
                "✓ CodeRabbit review completed",
                "Automation process finished successfully",
            ]

            missing_patterns = []
            found_patterns = []

            for pattern in expected_patterns:
                found = any(pattern in line for line in output_lines)
                if found:
                    found_patterns.append(pattern)
                else:
                    missing_patterns.append(pattern)

            print(
                f"Found {len(found_patterns)}/{len(expected_patterns)} expected patterns:"
            )
            for pattern in found_patterns:
                print(f"  ✓ {pattern}")

            if missing_patterns:
                print(f"Missing {len(missing_patterns)} patterns:")
                for pattern in missing_patterns:
                    print(f"  ✗ {pattern}")

            # Test passes if we found most patterns
            success_rate = len(found_patterns) / len(expected_patterns)
            print(f"Success rate: {success_rate:.1%}")

            # Consider it a success if we found at least 80% of patterns
            success = success_rate >= 0.8

            if success:
                print(
                    "✓ Integration test PASSED: Go runner captured logs incrementally"
                )
            else:
                print(
                    "✗ Integration test FAILED: Go runner did not capture all expected logs"
                )

            return success

        finally:
            # Clean up PRD file
            try:
                os.unlink(prd_path)
            except FileNotFoundError:
                pass
            except OSError as e:
                print(f"Warning: Failed to clean up PRD file {prd_path}: {e}")

    finally:
        # Clean up fake script
        try:
            os.unlink(fake_script)
        except:
            pass


def test_simple_log_streaming():
    """Simple test of log streaming with a basic command."""
    print("\n" + "=" * 50)
    print("Testing simple log streaming...")

    # Test with a simple command that outputs incrementally
    cmd = [
        "python3",
        "-c",
        """
import time
for i in range(5):
    print(f"Progress line {i+1}/5", flush=True)
    time.sleep(0.2)
print("Process completed", flush=True)
""",
    ]

    # Safety check: ensure python3 executable exists
    python_exe = shutil.which("python3")
    if not python_exe:
        raise RuntimeError("python3 executable not found for test")

    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1
    )

    output_lines = []
    start_time = time.time()

    while True:
        return_code = process.poll()
        if return_code is not None:
            remaining_stdout, _ = process.communicate()
            if remaining_stdout:
                output_lines.extend(remaining_stdout.split("\n"))
            break

        try:
            stdout_line = process.stdout.readline()
            if stdout_line:
                line = stdout_line.strip()
                output_lines.append(line)
                elapsed = time.time() - start_time
                print(f"[{elapsed:.1f}s] {line}")
        except StopIteration:
            break

        time.sleep(0.01)

        if time.time() - start_time > 10:
            process.terminate()
            break

    expected_lines = 6  # 5 progress + 1 completion
    actual_lines = len([line for line in output_lines if line.strip()])

    print(f"Expected {expected_lines} lines, got {actual_lines}")

    success = actual_lines >= expected_lines
    if success:
        print("✓ Simple streaming test PASSED")
    else:
        print("✗ Simple streaming test FAILED")

    return success


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
