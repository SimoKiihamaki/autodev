"""
AutoDev Phase 9: Evaluation Module

This module provides evaluation runners for benchmarking trained models
against SWE-bench and other code generation benchmarks.

Key components:
- SWEBenchRunner: Production-ready parallel evaluation runner
- Baseline comparison and improvement tracking
- Cost tracking and token usage analysis
- Report generation in multiple formats
"""

from .swebench_runner import (
    SWEBenchRunner,
    RunnerConfig,
    EvaluationResults,
    TaskResult,
    TaskStatus,
    EvaluationReport,
    ComparisonResult,
    CheckpointState,
    ProgressInfo,
    RunnerStage,
)

__all__ = [
    "SWEBenchRunner",
    "RunnerConfig",
    "EvaluationResults",
    "TaskResult",
    "TaskStatus",
    "EvaluationReport",
    "ComparisonResult",
    "CheckpointState",
    "ProgressInfo",
    "RunnerStage",
]
