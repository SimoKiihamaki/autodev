#!/usr/bin/env python3
"""
Run SWE-bench Lite with AutoDev's Hierarchical Executor

This script demonstrates how to use the integrated AutoDev solver
with the SWE-bench runner for actual benchmark execution.

Usage:
    python run_swebench_with_autodev.py [--subset N] [--output-dir DIR]
"""

import argparse
import logging
import sys
from pathlib import Path

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path.parent))

from src.swebench import SWEbenchRunner, AutoDevSolver, SolverConfig, create_solver

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Run SWE-bench Lite with AutoDev's Hierarchical Executor"
    )
    parser.add_argument(
        '--subset',
        type=int,
        default=10,
        help='Number of instances to run (default: 10)'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='results',
        help='Directory to save results'
    )
    parser.add_argument(
        '--max-iterations',
        type=int,
        default=5,
        help='Maximum review-implement iterations'
    )
    parser.add_argument(
        '--num-coders',
        type=int,
        default=2,
        help='Number of coder agents'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=600,
        help='Timeout per instance in seconds'
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 70)
    logger.info("SWE-bench Lite with AutoDev Hierarchical Executor")
    logger.info("=" * 70)
    
    # Create the runner
    runner = SWEbenchRunner(output_dir=args.output_dir)
    
    # Create the solver with configuration
    solver = create_solver(
        max_iterations=args.max_iterations,
        num_coders=args.num_coders,
        timeout_seconds=args.timeout,
    )
    
    # Set the solver on the runner
    runner.set_solver(solver)
    logger.info("AutoDev solver configured")
    
    # Run the benchmark
    logger.info(f"Running benchmark with {args.subset} instances...")
    metrics = runner.run_benchmark(subset_size=args.subset)
    
    # Print results
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    print(f"Total Instances:   {metrics.get('total_instances', 0)}")
    print(f"Resolved:          {metrics.get('resolved_count', 0)}")
    print(f"Resolution Rate:   {metrics.get('resolution_rate', 0):.2%}")
    print(f"Target (Phase 10): 30.00%")
    print(f"Status:            {'✓ TARGET MET' if metrics.get('target_met', False) else '✗ BELOW TARGET'}")
    print("=" * 70)
    
    # Exit with appropriate code
    sys.exit(0 if metrics.get('target_met', False) else 1)


if __name__ == "__main__":
    main()
