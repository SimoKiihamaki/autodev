"""
SWE-bench Test Harness for AutoDev Pipeline Validation

This package provides tools for evaluating AutoDev against SWE-bench tasks.

Modules:
    - swe_bench_harness: Main harness for running evaluations
    - verification: Patch verification and test execution
    - reporting: Result reporting and analysis

Usage:
    from benchmark.swe_bench_harness import SWEBenchHarness
    
    harness = SWEBenchHarness(workspace="/tmp/swebench_workspace")
    results = await harness.run_evaluation(num_tasks=10)
"""

from .swe_bench_harness import (
    SWEBenchHarness,
    SWETask,
    TaskResult,
    TaskStatus,
    EvaluationResults
)

__all__ = [
    "SWEBenchHarness",
    "SWETask",
    "TaskResult",
    "TaskStatus",
    "EvaluationResults"
]

__version__ = "1.0.0"
