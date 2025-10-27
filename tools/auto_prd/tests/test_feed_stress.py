#!/usr/bin/env python3
"""
Stress test for the live feed system to reproduce stalling issues.
This script creates a long-running automation with various output patterns
to stress-test the TUI's log ingestion and display system.
"""

import sys
import time
import logging
import argparse
from pathlib import Path

try:
    from ..logging_utils import setup_file_logging, print_flush
except ImportError:
    # Fallback if we can't import from the main module
    def setup_file_logging(*args, **kwargs):
        print(
            "Warning: logging_utils not available, setup_file_logging is no-op",
            file=sys.stderr,
        )

    def print_flush(*args, **kwargs):
        print(*args, **kwargs)


def simulate_bursty_output(
    burst_count=5, lines_per_burst=100, delay_between_bursts=2.0
):
    """Simulate bursty output that might cause buffer issues."""
    for burst in range(burst_count):
        print(f"=== BURST {burst + 1}/{burst_count} ===", flush=True)

        for i in range(lines_per_burst):
            timestamp = time.time()
            print(
                f"[{timestamp:.3f}] Burst line {i + 1}/{lines_per_burst} - Processing data batch item {i}",
                flush=True,
            )

            # Mix in some iteration headers
            if i % 25 == 0 and i > 0:
                print(
                    f"===== Iteration {burst + 1}.{i // 25 + 1}: Processing Burst =====",
                    flush=True,
                )

            # Mix in action indicators
            if i % 10 == 0:
                print(f"→ Processing item {i} with detailed analysis", flush=True)
            elif i % 10 == 5:
                print(f"✓ Completed item {i} successfully", flush=True)

            # Small delays to simulate real work
            if i % 20 == 0:
                time.sleep(0.01)

        print(f"*** Completed burst {burst + 1} ***", flush=True)
        if burst < burst_count - 1:
            time.sleep(delay_between_bursts)


def simulate_slow_drip_output(line_count=200, delay=0.1):
    """Simulate slow, steady output that should always be visible."""
    print("=== SLOW DRIP PHASE ===", flush=True)

    for i in range(line_count):
        timestamp = time.time()
        print(
            f"[{timestamp:.3f}] Slow drip line {i + 1}/{line_count} - Methodical processing",
            flush=True,
        )

        if i % 50 == 0 and i > 0:
            print(f"===== Iteration 2.{i // 50 + 1}: Slow Processing =====", flush=True)
            print(f"→ Starting slow chunk {i // 50 + 1}", flush=True)

        if i % 25 == 0:
            print(f"✓ Processed chunk {i // 25 + 1}", flush=True)

        time.sleep(delay)


def simulate_large_output_blocks(block_count=3, lines_per_block=1000):
    """Simulate very large output blocks that might overwhelm buffers."""
    for block in range(block_count):
        print(f"=== LARGE BLOCK {block + 1}/{block_count} ===", flush=True)
        print(
            f"===== Iteration 3.{block + 1}: Large Block Processing =====", flush=True
        )

        start_time = time.time()

        for i in range(lines_per_block):
            if i % 100 == 0:
                print(
                    f"[{time.time():.3f}] Block {block + 1} progress: {i}/{lines_per_block}",
                    flush=True,
                )
            else:
                # Print some lines without explicit flush to test default behavior
                print(
                    f"Block {block + 1} line {i} - detailed data processing with lots of text to fill buffers"
                )

        elapsed = time.time() - start_time
        print(f"✓ Completed block {block + 1} in {elapsed:.2f}s", flush=True)
        print(f"*** End of large block {block + 1} ***", flush=True)


def simulate_mixed_patterns():
    """Mix various output patterns that might trigger edge cases."""
    print("=== MIXED PATTERNS PHASE ===", flush=True)

    # Rapid succession
    for i in range(50):
        print(f"[{time.time():.3f}] Rapid fire {i}", flush=True)

    # Pause with potential buffering
    print(
        "PAUSING - This is where output might get buffered...", flush=False
    )  # Intentional no flush
    time.sleep(1.0)
    print("RESUMED - This should appear after pause", flush=True)

    # Mixed iteration patterns
    print("===== Iteration 4.1: Mixed Patterns =====", flush=True)
    for i in range(20):
        if i % 5 == 0:
            print(f"→ Processing mixed pattern item {i}", flush=True)
        elif i % 5 == 2:
            print(f"✓ Mixed item {i} done", flush=True)
        else:
            print(f"Mixed line {i} - standard processing", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Stress test live feed system")
    # Standard auto_prd arguments (ignored for stress testing)
    parser.add_argument("--prd", help="PRD file (ignored for stress test)")
    parser.add_argument("--repo", help="Repo path (ignored for stress test)")
    parser.add_argument("--repo-slug", help="Repo slug (ignored for stress test)")
    parser.add_argument("--base", help="Base branch (ignored for stress test)")
    parser.add_argument("--branch", help="Feature branch (ignored for stress test)")
    parser.add_argument("--codex-model", help="Codex model (ignored for stress test)")
    parser.add_argument(
        "--wait-minutes", type=int, help="Wait minutes (ignored for stress test)"
    )
    parser.add_argument(
        "--review-poll-seconds",
        type=int,
        help="Review poll seconds (ignored for stress test)",
    )
    parser.add_argument(
        "--iteration-limit", type=int, help="Iteration limit (ignored for stress test)"
    )
    parser.add_argument("--phase", help="Phase to start from (ignored for stress test)")
    parser.add_argument(
        "--initial-prompt", help="Initial prompt (ignored for stress test)"
    )
    parser.add_argument(
        "--sync-git",
        action="store_true",
        help="Sync git flag (ignored for stress test)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Dry run flag (ignored for stress test)"
    )
    parser.add_argument(
        "--infinite-reviews",
        action="store_true",
        help="Infinite reviews flag (ignored for stress test)",
    )
    parser.add_argument(
        "--idle-grace-minutes",
        type=int,
        help="Idle grace minutes (ignored for stress test)",
    )
    parser.add_argument(
        "--max-local-iters",
        type=int,
        help="Max local iterations (ignored for stress test)",
    )
    parser.add_argument(
        "--max-pr-iters", type=int, help="Max PR iterations (ignored for stress test)"
    )
    parser.add_argument(
        "--max-review-fix-iters",
        type=int,
        help="Max review fix iterations (ignored for stress test)",
    )
    parser.add_argument(
        "--disable-review-fix",
        action="store_true",
        help="Disable review fix (ignored for stress test)",
    )
    parser.add_argument(
        "--allow-unsafe",
        action="store_true",
        help="Allow unsafe execution (ignored for stress test)",
    )
    parser.add_argument(
        "--no-git",
        action="store_true",
        help="No git operations (ignored for stress test)",
    )

    # Stress test specific arguments
    parser.add_argument("--log-file", type=str, help="Optional log file for debugging")
    parser.add_argument("--log-level", type=str, default="INFO", help="Log level")
    parser.add_argument(
        "--duration",
        type=int,
        default=30,
        help="Total test duration in seconds (default: 30 for testing)",
    )

    args = parser.parse_args()

    if args.log_file:
        setup_file_logging(Path(args.log_file), args.log_level)
        print(f"Logging to file: {args.log_file}", flush=True)

    start_time = time.time()
    print(f"=== LIVE FEED STRESS TEST STARTING at {start_time:.3f} ===", flush=True)
    print(f"Test duration target: {args.duration} seconds", flush=True)

    try:
        # Phase 1: Bursty output
        print("\n*** STARTING BURSTY OUTPUT PHASE ***", flush=True)
        simulate_bursty_output(
            burst_count=3, lines_per_burst=50, delay_between_bursts=1.0
        )

        # Phase 2: Slow drip
        print("\n*** STARTING SLOW DRIP PHASE ***", flush=True)
        simulate_slow_drip_output(line_count=30, delay=0.2)

        # Phase 3: Large blocks
        print("\n*** STARTING LARGE BLOCK PHASE ***", flush=True)
        simulate_large_output_blocks(block_count=2, lines_per_block=500)

        # Phase 4: Mixed patterns
        print("\n*** STARTING MIXED PATTERNS PHASE ***", flush=True)
        simulate_mixed_patterns()

        # Phase 5: Final long iteration to test ongoing display
        print("\n*** STARTING FINAL LONG ITERATION ***", flush=True)
        print("===== Iteration 5: Final Stress Test =====", flush=True)

        elapsed_so_far = time.time() - start_time
        remaining_time = max(10, args.duration - elapsed_so_far)  # At least 10 seconds

        lines_to_generate = int(remaining_time * 5)  # 5 lines per second
        for i in range(lines_to_generate):
            timestamp = time.time()
            total_elapsed = timestamp - start_time

            if i % 100 == 0:
                print(
                    f"[{timestamp:.3f}] Final iteration progress: {i}/{lines_to_generate} (total elapsed: {total_elapsed:.1f}s)",
                    flush=True,
                )
                print(
                    f"→ Continuing final stress test batch {i // 100 + 1}", flush=True
                )
            elif i % 50 == 0:
                print(f"✓ Completed batch {i // 50 + 1}", flush=True)
            else:
                print(
                    f"[{timestamp:.3f}] Final line {i} - ongoing stress test",
                    flush=True,
                )

            time.sleep(0.2)  # 5 lines per second

        total_elapsed = time.time() - start_time
        print(
            f"\n=== STRESS TEST COMPLETED at {time.time():.3f} (total elapsed: {total_elapsed:.1f}s) ===",
            flush=True,
        )
        print("✓ All phases completed successfully", flush=True)

    except KeyboardInterrupt:
        elapsed = time.time() - start_time
        print(
            f"\n=== STRESS TEST INTERRUPTED at {time.time():.3f} (elapsed: {elapsed:.1f}s) ===",
            flush=True,
        )
        print("⚠️ Test interrupted by user", flush=True)
        return 1
    except Exception as e:
        elapsed = time.time() - start_time
        print(
            f"\n=== STRESS TEST FAILED at {time.time():.3f} (elapsed: {elapsed:.1f}s) ===",
            flush=True,
        )
        print(f"✗ Test failed with error: {e}", flush=True)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
