#!/usr/bin/env python3
"""
SWE-bench Lite Validation Script

This script runs the SWE-bench Lite benchmark subset and reports metrics.
SWE-bench Lite is a curated subset of ~300 issues from the full SWE-bench dataset,
designed for faster evaluation while maintaining representativeness.

Usage:
    python validate_swebench_lite.py [--subset N] [--output-dir DIR] [--verbose]

Requirements:
    pip install swebench-metrics datasets
"""

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class BenchmarkResult:
    """Result of running a single SWE-bench instance"""
    instance_id: str
    repo: str
    problem_statement: str
    resolved: bool
    tests_passed: int
    tests_failed: int
    time_seconds: float
    error_message: Optional[str] = None
    patch_applied: bool = False
    patch_content: Optional[str] = None


@dataclass
class BenchmarkMetrics:
    """Aggregated metrics for SWE-bench Lite run"""
    total_instances: int
    resolved_count: int
    failed_count: int
    timeout_count: int
    error_count: int
    resolution_rate: float
    avg_time_seconds: float
    total_time_seconds: float
    timestamp: str
    instances: List[BenchmarkResult]
    
    def to_dict(self) -> dict:
        return {
            'summary': {
                'total_instances': self.total_instances,
                'resolved_count': self.resolved_count,
                'failed_count': self.failed_count,
                'timeout_count': self.timeout_count,
                'error_count': self.error_count,
                'resolution_rate': f"{self.resolution_rate:.2%}",
                'avg_time_seconds': round(self.avg_time_seconds, 2),
                'total_time_seconds': round(self.total_time_seconds, 2),
                'timestamp': self.timestamp
            },
            'instances': [asdict(i) for i in self.instances]
        }


class SWEbenchValidator:
    """Validates AutoDev against SWE-bench Lite benchmark"""
    
    SWEBENCH_LITE_SIZE = 300  # Approximate size of SWE-bench Lite
    
    def __init__(self, output_dir: str = "results", timeout: int = 600, verbose: bool = False):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.verbose = verbose
        
        # Check dependencies
        self._check_dependencies()
    
    def _check_dependencies(self):
        """Check if required dependencies are installed"""
        try:
            import datasets
            logger.info("✓ datasets library found")
        except ImportError:
            logger.error("✗ datasets library not found. Install with: pip install datasets")
            sys.exit(1)
        
        # Optional: swebench-metrics for evaluation
        try:
            import swebench_metrics
            logger.info("✓ swebench-metrics library found")
            self.has_swebench_metrics = True
        except ImportError:
            logger.warning("⚠ swebench-metrics not found. Install with: pip install swebench-metrics")
            self.has_swebench_metrics = False
    
    def load_swebench_lite(self, subset_size: Optional[int] = None) -> List[dict]:
        """Load SWE-bench Lite dataset from HuggingFace"""
        logger.info("Loading SWE-bench Lite dataset from HuggingFace...")
        
        try:
            from datasets import load_dataset
            
            # Load the lite version
            dataset = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
            
            instances = list(dataset)
            logger.info(f"Loaded {len(instances)} instances from SWE-bench Lite")
            
            if subset_size and subset_size < len(instances):
                import random
                random.seed(42)  # For reproducibility
                instances = random.sample(instances, subset_size)
                logger.info(f"Using subset of {len(instances)} instances")
            
            return instances
            
        except Exception as e:
            logger.error(f"Failed to load dataset: {e}")
            raise
    
    def run_single_instance(self, instance: dict) -> BenchmarkResult:
        """
        Run a single SWE-bench instance.
        
        This is where AutoDev's solver would be called.
        For now, this is a placeholder that shows the expected interface.
        """
        start_time = time.time()
        instance_id = instance.get('instance_id', 'unknown')
        repo = instance.get('repo', 'unknown')
        
        logger.info(f"Processing instance: {instance_id} from {repo}")
        
        try:
            # TODO: Integrate with AutoDev solver
            # Expected flow:
            # 1. Clone the repository at the specified base commit
            # 2. Run AutoDev to generate a patch for the issue
            # 3. Apply the generated patch
            # 4. Run the test suite
            # 5. Record results
            
            # Placeholder implementation
            # In production, this would call AutoDev's solver
            patch_content = self._generate_patch_placeholder(instance)
            resolved = False
            tests_passed = 0
            tests_failed = 0
            patch_applied = False
            error_message = None
            
            # Simulate processing time for placeholder
            time.sleep(0.1)
            
            if self.verbose:
                logger.debug(f"Instance details: {json.dumps(instance, indent=2, default=str)[:500]}")
            
        except TimeoutError:
            error_message = f"Timeout after {self.timeout} seconds"
            resolved = False
            tests_passed = 0
            tests_failed = 0
            patch_applied = False
            patch_content = None
            
        except Exception as e:
            error_message = str(e)
            resolved = False
            tests_passed = 0
            tests_failed = 0
            patch_applied = False
            patch_content = None
        
        elapsed = time.time() - start_time
        
        return BenchmarkResult(
            instance_id=instance_id,
            repo=repo,
            problem_statement=instance.get('problem_statement', '')[:200],
            resolved=resolved,
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            time_seconds=elapsed,
            error_message=error_message,
            patch_applied=patch_applied,
            patch_content=patch_content
        )
    
    def _generate_patch_placeholder(self, instance: dict) -> Optional[str]:
        """
        Placeholder for AutoDev patch generation.
        
        In production, this would:
        1. Call AutoDev's solver with the problem statement
        2. Return the generated diff/patch
        
        For actual benchmark execution, use the integrated solver:
        
            from swebench import SWEbenchRunner, create_solver
            runner = SWEbenchRunner()
            runner.set_solver(create_solver())
            metrics = runner.run_benchmark()
        """
        # Return None to indicate no patch was generated
        return None
    
    def run_benchmark(self, subset_size: Optional[int] = None) -> BenchmarkMetrics:
        """Run the full SWE-bench Lite benchmark"""
        logger.info("=" * 70)
        logger.info("SWE-bench Lite Validation Run")
        logger.info("=" * 70)
        
        # Load instances
        instances = self.load_swebench_lite(subset_size)
        total = len(instances)
        
        # Track metrics
        results: List[BenchmarkResult] = []
        resolved_count = 0
        failed_count = 0
        timeout_count = 0
        error_count = 0
        total_time = 0
        
        start_time = time.time()
        
        for idx, instance in enumerate(instances, 1):
            logger.info(f"\n[{idx}/{total}] Processing instance...")
            
            result = self.run_single_instance(instance)
            results.append(result)
            total_time += result.time_seconds
            
            if result.resolved:
                resolved_count += 1
                logger.info(f"✓ RESOLVED: {result.instance_id}")
            elif result.error_message and "timeout" in result.error_message.lower():
                timeout_count += 1
                logger.warning(f"⏱ TIMEOUT: {result.instance_id}")
            elif result.error_message:
                error_count += 1
                logger.error(f"✗ ERROR: {result.instance_id} - {result.error_message}")
            else:
                failed_count += 1
                logger.info(f"✗ FAILED: {result.instance_id}")
            
            # Log progress
            if idx % 10 == 0:
                current_rate = resolved_count / idx
                logger.info(f"Progress: {idx}/{total} | Resolution rate: {current_rate:.2%}")
        
        total_elapsed = time.time() - start_time
        resolution_rate = resolved_count / total if total > 0 else 0
        avg_time = total_time / total if total > 0 else 0
        
        metrics = BenchmarkMetrics(
            total_instances=total,
            resolved_count=resolved_count,
            failed_count=failed_count,
            timeout_count=timeout_count,
            error_count=error_count,
            resolution_rate=resolution_rate,
            avg_time_seconds=avg_time,
            total_time_seconds=total_elapsed,
            timestamp=datetime.now().isoformat(),
            instances=results
        )
        
        return metrics
    
    def save_results(self, metrics: BenchmarkMetrics, filename: str = "swebench_lite_results.json"):
        """Save benchmark results to JSON file"""
        output_path = self.output_dir / filename
        with open(output_path, 'w') as f:
            json.dump(metrics.to_dict(), f, indent=2)
        
        logger.info(f"\nResults saved to: {output_path}")
        return output_path
    
    def print_summary(self, metrics: BenchmarkMetrics):
        """Print a formatted summary of results"""
        print("\n" + "=" * 70)
        print("SWE-BENCH LITE VALIDATION SUMMARY")
        print("=" * 70)
        print(f"Timestamp: {metrics.timestamp}")
        print(f"\n{'RESULTS':=^70}")
        print(f"Total Instances:     {metrics.total_instances}")
        print(f"Resolved:            {metrics.resolved_count}")
        print(f"Failed:              {metrics.failed_count}")
        print(f"Timeouts:            {metrics.timeout_count}")
        print(f"Errors:              {metrics.error_count}")
        print(f"\n{'METRICS':=^70}")
        print(f"Resolution Rate:     {metrics.resolution_rate:.2%}")
        print(f"Target (Phase 10):   30.00%")
        print(f"Status:              {'✓ TARGET MET' if metrics.resolution_rate >= 0.30 else '✗ BELOW TARGET'}")
        print(f"\n{'TIMING':=^70}")
        print(f"Average Time:        {metrics.avg_time_seconds:.2f}s")
        print(f"Total Time:          {metrics.total_time_seconds:.2f}s")
        print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Run SWE-bench Lite validation for AutoDev",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run full benchmark
    python validate_swebench_lite.py
    
    # Run first 10 instances for quick testing
    python validate_swebench_lite.py --subset 10
    
    # Run with verbose output
    python validate_swebench_lite.py --subset 5 --verbose
    
    # Custom output directory
    python validate_swebench_lite.py --output-dir ./my_results
"""
    )
    
    parser.add_argument(
        '--subset',
        type=int,
        default=None,
        help='Number of instances to run (default: all ~300)'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='results',
        help='Directory to save results (default: results/)'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=600,
        help='Timeout per instance in seconds (default: 600)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    # Create validator
    validator = SWEbenchValidator(
        output_dir=args.output_dir,
        timeout=args.timeout,
        verbose=args.verbose
    )
    
    # Run benchmark
    metrics = validator.run_benchmark(subset_size=args.subset)
    
    # Save and print results
    validator.save_results(metrics)
    validator.print_summary(metrics)
    
    # Exit with appropriate code
    sys.exit(0 if metrics.resolution_rate >= 0.30 else 1)


if __name__ == "__main__":
    main()
