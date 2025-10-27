#!/usr/bin/env python3
"""
Script to reproduce the stalled feed issue by generating incremental logs
similar to the auto_prd runner, but with controlled timing and explicit timestamps.
"""

import sys
import time


# Simulate the print hook behavior that would be installed by logging_utils.py
def tee_print_simulation(*args, **kwargs):
    """Simulate the tee_print function that prints to stdout with optional buffering delay."""
    message = " ".join(str(arg) for arg in args)

    # Print the message (this should be immediate but may be block-buffered)
    print(message)

    # Simulate potential buffering issues
    if kwargs.get("simulate_buffering", False):
        # This simulates what happens when output is block-buffered
        time.sleep(0.1)  # Small delay to accumulate buffer


def simulate_automation_loop():
    """Simulate the automation loop with progress indicators."""
    print("Starting automation loop simulation...")

    # Simulate the initial setup phase
    tee_print_simulation("Repository root: /tmp/test_repo")
    tee_print_simulation("Using PRD: /tmp/test_prd.md")

    # Simulate multiple iterations with different timing patterns
    for i in range(1, 6):
        # Iteration header (this should appear immediately)
        tee_print_simulation(f"\n=== Iteration {i}/5: Codex implements next chunk ===")

        # Launch message
        tee_print_simulation("→ Launching implementation pass with codex …")

        # Simulate some work with variable timing
        work_time = 2.0 + (i * 0.5)  # Increasing work time

        # Simulate intermediate progress that might get buffered
        for j in range(10):
            tee_print_simulation(
                f"Working on step {j}/10...", simulate_buffering=(j < 8)
            )
            time.sleep(work_time / 10)

        # Completion message
        tee_print_simulation("✓ Codex implementation pass completed.")

        # Simulate TASKS_LEFT reporting
        tasks_left = max(0, 10 - (i * 2))
        tee_print_simulation(f"Codex reported TASKS_LEFT={tasks_left}")

        # Simulate CodeRabbit phase
        tee_print_simulation("\n=== CodeRabbit CLI review (prompt-only) ===")
        time.sleep(1.0)

        if i < 3:
            tee_print_simulation("\n=== Codex applies CodeRabbit findings ===")
            tee_print_simulation(
                "→ Launching fix pass with codex based on CodeRabbit feedback…"
            )
            time.sleep(1.5)
            tee_print_simulation("✓ Codex fix pass completed.")
            tee_print_simulation(
                f"Codex reported TASKS_LEFT={tasks_left - 1} after applying findings"
            )
        else:
            tee_print_simulation("No CodeRabbit findings detected in this pass.")
            tee_print_simulation(f"CodeRabbit no-findings streak: {i - 2}")

    tee_print_simulation("\nAutomation loop completed!")
    tee_print_simulation("Final TASKS_LEFT=0")


def test_buffering_behavior():
    """Test different buffering scenarios."""
    print("Testing output buffering behavior...")

    # Test 1: Rapid small outputs (should be line-buffered)
    print("\n=== Test 1: Rapid small outputs ===")
    for i in range(10):
        print(f"Small output {i}")
        time.sleep(0.05)

    # Test 2: Large outputs (might trigger block buffering)
    print("\n=== Test 2: Large outputs ===")
    large_text = "x" * 1000  # 1KB output
    for i in range(5):
        print(f"Large output {i}: {large_text}")
        time.sleep(0.1)

    # Test 3: Mixed outputs with explicit flush
    print("\n=== Test 3: Mixed outputs with explicit flush ===")
    for i in range(5):
        print(f"Mixed output {i}...", flush=True)  # Explicit flush
        time.sleep(0.2)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test-buffering":
        test_buffering_behavior()
    else:
        simulate_automation_loop()
