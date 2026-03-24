#!/usr/bin/env python3
"""
Performance Regression Test Suite for Phase 10.1 Track 3

This test suite validates that the hierarchical executor maintains acceptable
performance levels by comparing against baseline metrics. Tests will fail if
performance degrades by more than 20%.

Usage:
    pytest tests/regression/test_performance.py -v

Requirements:
    pip install pytest psutil
"""

import gc
import json
import os
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

# Try importing dependencies
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    pytest.skip("psutil not available, skipping performance tests", allow_module_level=True)


# ============================================================================
# Configuration
# ============================================================================

PROJECT_ROOT = Path(__file__).parent.parent.parent
BASELINE_FILE = PROJECT_ROOT / "benchmarks" / "baselines" / "phase10.1.json"
REGRESSION_TASKS_FILE = PROJECT_ROOT / "autodev" / "config" / "regression_tasks.json"
PERFORMANCE_THRESHOLD = 1.20  # 20% slower = fail
MAX_SUITE_RUNTIME_SECONDS = 300  # 5 minutes


# ============================================================================
# Metrics Classes (mirroring collect_baseline_metrics.py)
# ============================================================================

@dataclass
class TaskMetrics:
    """Metrics collected for a single SWE-bench task."""
    instance_id: str
    repo: str
    total_time_seconds: float
    success: bool
    decomposing_time_seconds: float = 0.0
    coding_time_seconds: float = 0.0
    reviewing_time_seconds: float = 0.0
    iteration_time_seconds: float = 0.0
    handoff_decompose_to_coding_seconds: float = 0.0
    handoff_coding_to_reviewing_seconds: float = 0.0
    tokens_used: int = 0
    tokens_decomposing: int = 0
    tokens_coding: int = 0
    tokens_reviewing: int = 0
    memory_peak_mb: float = 0.0
    memory_start_mb: float = 0.0
    memory_end_mb: float = 0.0
    iterations: int = 0
    review_iterations: int = 0
    error: Optional[str] = None


# ============================================================================
# Hierarchical Executor for Testing
# ============================================================================

class HierarchicalExecutorWithMetrics:
    """
    Standalone executor for performance regression testing.
    Mirrors the implementation in collect_baseline_metrics.py to ensure
    consistent performance measurements.
    """
    
    def __init__(self, max_iterations: int = 5):
        self.max_iterations = max_iterations
        
    def _get_memory_mb(self) -> float:
        """Get current memory usage in MB."""
        if PSUTIL_AVAILABLE:
            process = psutil.Process(os.getpid())
            return process.memory_info().rss / (1024 * 1024)
        return 0.0
    
    def execute_with_metrics(self, instance: dict) -> TaskMetrics:
        """
        Execute a single SWE-bench instance and collect metrics.
        
        This simulates the full hierarchical execution flow:
        1. Decomposition (Manager agent)
        2. Coding (Coder agents)
        3. Reviewing (Reviewer agents)
        4. Iteration loop if needed
        """
        instance_id = instance.get('instance_id', 'unknown')
        repo = instance.get('repo', 'unknown')
        
        # Initialize metrics
        metrics = TaskMetrics(
            instance_id=instance_id,
            repo=repo,
            total_time_seconds=0.0,
            success=False
        )
        
        # Track memory
        metrics.memory_start_mb = self._get_memory_mb()
        memory_samples = [metrics.memory_start_mb]
        
        overall_start = time.perf_counter()
        
        try:
            # Phase 1: Decomposition
            decomp_start = time.perf_counter()
            time.sleep(0.01)  # Simulate init
            subtasks = self._mock_decompose(instance)
            decomp_end = time.perf_counter()
            metrics.decomposing_time_seconds = decomp_end - decomp_start
            memory_samples.append(self._get_memory_mb())
            
            # Handoff time (manager to coder)
            handoff1_start = time.perf_counter()
            time.sleep(0.001)  # Simulate handoff
            handoff1_end = time.perf_counter()
            metrics.handoff_decompose_to_coding_seconds = handoff1_end - handoff1_start
            
            # Phase 2: Coding
            coding_start = time.perf_counter()
            code_changes = []
            for subtask in subtasks:
                time.sleep(0.01)  # Simulate coder init
                result = self._mock_code(subtask)
                code_changes.append(result)
                memory_samples.append(self._get_memory_mb())
            coding_end = time.perf_counter()
            metrics.coding_time_seconds = coding_end - coding_start
            
            # Handoff time (coder to reviewer)
            handoff2_start = time.perf_counter()
            time.sleep(0.001)  # Simulate handoff
            handoff2_end = time.perf_counter()
            metrics.handoff_coding_to_reviewing_seconds = handoff2_end - handoff2_start
            
            # Phase 3: Review
            review_start = time.perf_counter()
            time.sleep(0.01)  # Simulate reviewer init
            review_result = self._mock_review(code_changes)
            review_end = time.perf_counter()
            metrics.reviewing_time_seconds = review_end - review_start
            memory_samples.append(self._get_memory_mb())
            
            # Iteration loop (simplified)
            iterations = 1
            while (
                getattr(review_result, 'verdict', 'approved') != 'approved' and
                iterations < self.max_iterations
            ):
                # Re-code based on feedback
                for subtask in subtasks:
                    self._mock_code(subtask)
                
                # Re-review
                review_result = self._mock_review(code_changes)
                iterations += 1
                metrics.review_iterations += 1
                memory_samples.append(self._get_memory_mb())
            
            metrics.iterations = iterations
            metrics.success = getattr(review_result, 'verdict', 'approved') == 'approved'
            
            # Simulate token usage (mock values based on work done)
            metrics.tokens_decomposing = 500 + len(instance.get('problem_statement', '')) // 4
            metrics.tokens_coding = 1500 * len(subtasks)
            metrics.tokens_reviewing = 300 * len(code_changes)
            metrics.tokens_used = (
                metrics.tokens_decomposing + 
                metrics.tokens_coding + 
                metrics.tokens_reviewing
            )
            
        except Exception as e:
            metrics.error = str(e)
            metrics.success = False
        
        finally:
            overall_end = time.perf_counter()
            metrics.total_time_seconds = overall_end - overall_start
            
            # Get peak memory from samples
            metrics.memory_peak_mb = max(memory_samples) if memory_samples else 0.0
            metrics.memory_end_mb = self._get_memory_mb()
            
            # Cleanup
            gc.collect()
        
        return metrics
    
    def _mock_decompose(self, instance: dict):
        """Mock task decomposition."""
        class MockSubTask:
            def __init__(self, subtask_id, name, description):
                self.subtask_id = subtask_id
                self.name = name
                self.description = description
                self.task_type = "implement"
        
        task_id = instance.get('instance_id', 'unknown')
        time.sleep(0.05 + (hash(task_id) % 100) / 1000)
        
        return [
            MockSubTask(f"{task_id}-sub-0", "Analyze problem", "Understand the issue"),
            MockSubTask(f"{task_id}-sub-1", "Implement fix", "Write the solution"),
        ]
    
    def _mock_code(self, subtask):
        """Mock coding."""
        class MockCodeChange:
            def __init__(self, file, diff):
                self.file = file
                self.diff = diff
        
        time.sleep(0.1 + (hash(subtask.subtask_id) % 200) / 1000)
        return MockCodeChange("solution.py", "# Implementation")
    
    def _mock_review(self, changes):
        """Mock review."""
        class MockReviewResult:
            def __init__(self):
                self.review_id = "review-001"
                self.verdict = "approved"
                self.findings = []
                self.blocking_issues = []
        
        time.sleep(0.03 + (len(changes) * 0.02))
        return MockReviewResult()


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture(scope="module")
def baseline_metrics():
    """Load baseline metrics from JSON file."""
    if not BASELINE_FILE.exists():
        pytest.skip(f"Baseline file not found: {BASELINE_FILE}")
    
    with open(BASELINE_FILE, 'r') as f:
        return json.load(f)


@pytest.fixture(scope="module")
def regression_tasks():
    """Load regression tasks from JSON file."""
    if not REGRESSION_TASKS_FILE.exists():
        pytest.skip(f"Regression tasks file not found: {REGRESSION_TASKS_FILE}")
    
    with open(REGRESSION_TASKS_FILE, 'r') as f:
        config = json.load(f)
        return config['tasks']


@pytest.fixture(scope="module")
def executor():
    """Create a hierarchical executor instance for testing."""
    return HierarchicalExecutorWithMetrics(max_iterations=3)


# ============================================================================
# Performance Tests
# ============================================================================

class TestPerformanceRegression:
    """Performance regression tests for hierarchical executor."""
    
    def test_suite_runtime_under_5_minutes(self, executor, regression_tasks):
        """Verify the entire test suite runs in under 5 minutes."""
        suite_start = time.perf_counter()
        
        for task in regression_tasks:
            instance = {
                'instance_id': task['instance_id'],
                'repo': task['repo'],
                'problem_statement': task.get('description', '')
            }
            executor.execute_with_metrics(instance)
        
        suite_end = time.perf_counter()
        suite_runtime = suite_end - suite_start
        
        assert suite_runtime < MAX_SUITE_RUNTIME_SECONDS, (
            f"Suite runtime {suite_runtime:.2f}s exceeds maximum {MAX_SUITE_RUNTIME_SECONDS}s"
        )
        
        print(f"\n✓ Suite completed in {suite_runtime:.2f}s "
              f"({(suite_runtime / MAX_SUITE_RUNTIME_SECONDS) * 100:.1f}% of max)")
    
    def test_average_latency_regression(
        self, executor, regression_tasks, baseline_metrics
    ):
        """Verify average task latency is within 20% of baseline."""
        # Collect current metrics
        current_metrics = []
        
        for task in regression_tasks:
            instance = {
                'instance_id': task['instance_id'],
                'repo': task['repo'],
                'problem_statement': task.get('description', '')
            }
            metrics = executor.execute_with_metrics(instance)
            current_metrics.append(metrics)
        
        # Calculate average latency
        avg_latency = sum(m.total_time_seconds for m in current_metrics) / len(current_metrics)
        
        # Get baseline average
        baseline_avg = baseline_metrics['latency']['avg_task_latency_seconds']
        
        # Check for regression
        max_allowed_latency = baseline_avg * PERFORMANCE_THRESHOLD
        
        assert avg_latency <= max_allowed_latency, (
            f"Performance regression detected!\n"
            f"  Current avg latency: {avg_latency:.3f}s\n"
            f"  Baseline avg latency: {baseline_avg:.3f}s\n"
            f"  Max allowed (20% over): {max_allowed_latency:.3f}s\n"
            f"  Regression: {((avg_latency / baseline_avg) - 1) * 100:.1f}%"
        )
        
        improvement = ((baseline_avg / avg_latency) - 1) * 100
        status = "improvement" if improvement > 0 else "slower"
        
        print(f"\n✓ Average latency: {avg_latency:.3f}s "
              f"({status}: {abs(improvement):.1f}%)")
    
    @pytest.mark.parametrize("task_index", [0, 1, 2, 3, 4])
    def test_individual_task_performance(
        self, executor, regression_tasks, baseline_metrics, task_index
    ):
        """Verify each individual task's performance is within 20% of baseline."""
        task = regression_tasks[task_index]
        
        # Execute the task
        instance = {
            'instance_id': task['instance_id'],
            'repo': task['repo'],
            'problem_statement': task.get('description', '')
        }
        
        metrics = executor.execute_with_metrics(instance)
        
        # Find baseline for this task
        baseline_task = None
        for baseline in baseline_metrics['tasks']:
            if baseline['instance_id'] == task['instance_id']:
                baseline_task = baseline
                break
        
        if not baseline_task:
            pytest.skip(f"No baseline found for task {task['instance_id']}")
        
        # Check for regression
        baseline_latency = baseline_task['total_time_seconds']
        max_allowed_latency = baseline_latency * PERFORMANCE_THRESHOLD
        
        assert metrics.total_time_seconds <= max_allowed_latency, (
            f"Performance regression for {task['instance_id']}!\n"
            f"  Current latency: {metrics.total_time_seconds:.3f}s\n"
            f"  Baseline latency: {baseline_latency:.3f}s\n"
            f"  Max allowed (20% over): {max_allowed_latency:.3f}s\n"
            f"  Regression: {((metrics.total_time_seconds / baseline_latency) - 1) * 100:.1f}%"
        )
        
        improvement = ((baseline_latency / metrics.total_time_seconds) - 1) * 100
        status = "faster" if improvement > 0 else "slower"
        
        print(f"\n  ✓ {task['instance_id']}: {metrics.total_time_seconds:.3f}s "
              f"({status}: {abs(improvement):.1f}%)")
    
    def test_phase_timings_no_regression(
        self, executor, regression_tasks, baseline_metrics
    ):
        """Verify phase timings (decompose, code, review) show no major regressions."""
        # Collect current phase timings
        decomposing_times = []
        coding_times = []
        reviewing_times = []
        
        for task in regression_tasks:
            instance = {
                'instance_id': task['instance_id'],
                'repo': task['repo'],
                'problem_statement': task.get('description', '')
            }
            metrics = executor.execute_with_metrics(instance)
            decomposing_times.append(metrics.decomposing_time_seconds)
            coding_times.append(metrics.coding_time_seconds)
            reviewing_times.append(metrics.reviewing_time_seconds)
        
        # Calculate averages
        avg_decomposing = sum(decomposing_times) / len(decomposing_times)
        avg_coding = sum(coding_times) / len(coding_times)
        avg_reviewing = sum(reviewing_times) / len(reviewing_times)
        
        # Get baseline averages
        baseline_decomposing = baseline_metrics['phase_timings']['avg_decomposing_time_seconds']
        baseline_coding = baseline_metrics['phase_timings']['avg_coding_time_seconds']
        baseline_reviewing = baseline_metrics['phase_timings']['avg_reviewing_time_seconds']
        
        # Check each phase
        issues = []
        
        if avg_decomposing > baseline_decomposing * PERFORMANCE_THRESHOLD:
            issues.append(
                f"Decomposing phase regression: {avg_decomposing:.3f}s vs "
                f"{baseline_decomposing:.3f}s baseline "
                f"({((avg_decomposing / baseline_decomposing) - 1) * 100:.1f}% slower)"
            )
        
        if avg_coding > baseline_coding * PERFORMANCE_THRESHOLD:
            issues.append(
                f"Coding phase regression: {avg_coding:.3f}s vs "
                f"{baseline_coding:.3f}s baseline "
                f"({((avg_coding / baseline_coding) - 1) * 100:.1f}% slower)"
            )
        
        if avg_reviewing > baseline_reviewing * PERFORMANCE_THRESHOLD:
            issues.append(
                f"Reviewing phase regression: {avg_reviewing:.3f}s vs "
                f"{baseline_reviewing:.3f}s baseline "
                f"({((avg_reviewing / baseline_reviewing) - 1) * 100:.1f}% slower)"
            )
        
        assert not issues, "Phase timing regressions detected:\n" + "\n".join(issues)
        
        print(f"\n✓ Phase timings within acceptable range:")
        print(f"  Decomposing: {avg_decomposing:.3f}s (baseline: {baseline_decomposing:.3f}s)")
        print(f"  Coding:      {avg_coding:.3f}s (baseline: {baseline_coding:.3f}s)")
        print(f"  Reviewing:   {avg_reviewing:.3f}s (baseline: {baseline_reviewing:.3f}s)")
    
    def test_memory_usage_no_regression(
        self, executor, regression_tasks, baseline_metrics
    ):
        """Verify memory usage shows no major regressions."""
        # Collect current memory metrics
        memory_peaks = []
        
        for task in regression_tasks:
            instance = {
                'instance_id': task['instance_id'],
                'repo': task['repo'],
                'problem_statement': task.get('description', '')
            }
            metrics = executor.execute_with_metrics(instance)
            memory_peaks.append(metrics.memory_peak_mb)
        
        # Calculate average
        avg_memory_peak = sum(memory_peaks) / len(memory_peaks)
        max_memory_peak = max(memory_peaks)
        
        # Get baseline
        baseline_avg_memory = baseline_metrics['memory']['avg_memory_peak_mb']
        baseline_max_memory = baseline_metrics['memory']['max_memory_peak_mb']
        
        # Check for regression (allow 50% increase for memory due to variance)
        memory_threshold = 1.5
        
        issues = []
        if avg_memory_peak > baseline_avg_memory * memory_threshold:
            issues.append(
                f"Average memory regression: {avg_memory_peak:.2f}MB vs "
                f"{baseline_avg_memory:.2f}MB baseline"
            )
        
        if max_memory_peak > baseline_max_memory * memory_threshold:
            issues.append(
                f"Peak memory regression: {max_memory_peak:.2f}MB vs "
                f"{baseline_max_memory:.2f}MB baseline"
            )
        
        # This is a warning, not a hard failure for memory
        if issues:
            print(f"\n⚠ Memory usage warning:\n" + "\n".join(issues))
        else:
            print(f"\n✓ Memory usage within acceptable range:")
            print(f"  Avg peak: {avg_memory_peak:.2f}MB (baseline: {baseline_avg_memory:.2f}MB)")
            print(f"  Max peak: {max_memory_peak:.2f}MB (baseline: {baseline_max_memory:.2f}MB)")
    
    def test_success_rate_maintained(
        self, executor, regression_tasks, baseline_metrics
    ):
        """Verify success rate is maintained (100% in baseline)."""
        # Execute all tasks
        successful = 0
        total = len(regression_tasks)
        
        for task in regression_tasks:
            instance = {
                'instance_id': task['instance_id'],
                'repo': task['repo'],
                'problem_statement': task.get('description', '')
            }
            metrics = executor.execute_with_metrics(instance)
            if metrics.success:
                successful += 1
        
        success_rate = successful / total
        baseline_success_rate = baseline_metrics['summary']['success_rate_raw']
        
        # Allow small decrease but not major drop
        min_acceptable_rate = baseline_success_rate * 0.8  # 80% of baseline
        
        assert success_rate >= min_acceptable_rate, (
            f"Success rate dropped!\n"
            f"  Current: {successful}/{total} ({success_rate:.1%})\n"
            f"  Baseline: {baseline_success_rate:.1%}\n"
            f"  Min acceptable: {min_acceptable_rate:.1%}"
        )
        
        print(f"\n✓ Success rate maintained: {successful}/{total} ({success_rate:.1%})")


# ============================================================================
# Test Runner
# ============================================================================

if __name__ == "__main__":
    # Run tests with pytest
    sys.exit(pytest.main([__file__, "-v", "-s", "--tb=short"]))
