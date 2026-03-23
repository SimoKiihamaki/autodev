"""
SWE-bench integration for AutoDev.

This module provides utilities for running SWE-bench Lite validation
and reporting metrics for AutoDev's performance evaluation.

Components:
- SWEbenchRunner: High-level API for running benchmarks
- AutoDevSolver: Integrates HierarchicalExecutor with the runner
- create_solver: Factory function for quick setup
"""

from .runner import SWEbenchRunner
from .autodev_solver import (
    AutoDevSolver,
    SolverConfig,
    SWEBenchInstance,
    create_solver,
)

__all__ = [
    'SWEbenchRunner',
    'AutoDevSolver',
    'SolverConfig',
    'SWEBenchInstance',
    'create_solver',
]
__version__ = '0.2.0'
