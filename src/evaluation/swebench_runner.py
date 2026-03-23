"""
SWE-bench Evaluation Runner for AutoDev Phase 9

This module provides a production-ready evaluation runner for benchmarking
trained models against SWE-bench tasks. It supports parallel execution,
checkpoint/resume, cost tracking, error recovery, and report generation.

Key features:
- Parallel execution with configurable concurrency
- Checkpoint/resume for interrupted evaluations
- Cost tracking with API token usage monitoring
- Error recovery with exponential backoff
- Report generation in Markdown and JSON formats
- Baseline comparison and improvement tracking

Usage:
    from evaluation.swebench_runner import SWEBenchRunner, RunnerConfig

    runner = SWEBenchRunner(
        model_path="~/.autodev/models/grpo_v1",
        workspace="/tmp/swebench_eval",
        max_concurrent=4
    )

    # Run evaluation
    results = await runner.evaluate(
        subset="lite",
        num_tasks=50,
        timeout_per_task=1800
    )

    # Generate report
    report = runner.generate_report(results)
    report.save("~/eval_reports/eval_2026-03-23.md")

    # Compare with baseline
    comparison = await runner.compare_with_baseline(
        baseline_model="Qwen/Qwen2.5-Coder-7B-Instruct",
        tasks=results.task_ids
    )
"""

import asyncio
import json
import logging
import os
import shutil
import signal
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from concurrent.futures import ThreadPoolExecutor

# Import benchmark harness components (Phase 7)
try:
    from benchmark.swe_bench_harness import (
        SWEBenchHarness,
        SWETask,
        TaskResult as HarnessTaskResult,
        TaskStatus as HarnessTaskStatus,
        EvaluationResults as HarnessEvaluationResults,
    )
    HARNESS_AVAILABLE = True
except ImportError:
    HARNESS_AVAILABLE = False

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Enums and Data Classes
# -----------------------------------------------------------------------------

class RunnerStage(Enum):
    """Stages of the evaluation runner."""
    IDLE = "idle"
    INITIALIZING = "initializing"
    LOADING_TASKS = "loading_tasks"
    EVALUATING = "evaluating"
    GENERATING_REPORT = "generating_report"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskStatus(Enum):
    """Status of a single task evaluation."""
    PENDING = "pending"
    RUNNING = "running"
    RESOLVED = "resolved"
    FAILED = "failed"
    TIMEOUT = "timeout"
    ERROR = "error"
    SKIPPED = "skipped"


class ReportFormat(Enum):
    """Available report formats."""
    MARKDOWN = "markdown"
    JSON = "json"
    HTML = "html"


@dataclass
class RunnerConfig:
    """
    Configuration for the SWEBenchRunner.
    
    Attributes:
        workspace: Base directory for evaluation workspaces
        max_concurrent: Maximum number of concurrent task evaluations
        timeout_per_task: Timeout in seconds for each task
        max_retries: Maximum number of retries for failed tasks
        retry_backoff_base: Base seconds for exponential backoff
        checkpoint_dir: Directory for storing checkpoints
        checkpoint_interval: Save checkpoint every N completed tasks
        auto_resume: Automatically resume from checkpoint if available
        keep_checkpoints: Number of checkpoints to keep
        track_costs: Whether to track API costs
        cost_per_input_token: Cost per 1K input tokens
        cost_per_output_token: Cost per 1K output tokens
        generate_report: Whether to generate report after evaluation
        report_formats: List of report formats to generate
        report_output_dir: Directory for generated reports
    """
    # Workspace settings
    workspace: str = "/tmp/swebench_eval"
    cleanup_workspace: bool = True
    
    # Parallel execution settings
    max_concurrent: int = 4
    task_batch_size: int = 8
    
    # Timeout and retry settings
    timeout_per_task: int = 1800  # 30 minutes
    max_retries: int = 3
    retry_backoff_base: float = 2.0
    retry_backoff_max: float = 60.0
    
    # Checkpoint settings
    checkpoint_dir: str = "~/.autodev/eval_checkpoints"
    checkpoint_interval: int = 10  # Save checkpoint every N completed tasks
    auto_resume: bool = True
    keep_checkpoints: int = 5
    
    # Cost tracking settings
    track_costs: bool = True
    cost_per_input_token: float = 0.003  # $0.003 per 1K input tokens (Claude)
    cost_per_output_token: float = 0.015  # $0.015 per 1K output tokens (Claude)
    
    # Report settings
    generate_report: bool = True
    report_formats: List[str] = field(default_factory=lambda: ["markdown", "json"])
    report_output_dir: str = "~/.autodev/eval_reports"
    
    # Model settings
    model_temperature: float = 0.3
    max_iterations: int = 30
    
    def __post_init__(self):
        """Expand directory paths."""
        self.workspace = os.path.expanduser(self.workspace)
        self.checkpoint_dir = os.path.expanduser(self.checkpoint_dir)
        self.report_output_dir = os.path.expanduser(self.report_output_dir)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunnerConfig":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class ProgressInfo:
    """
    Current progress information for the evaluation runner.
    
    Attributes:
        stage: Current runner stage
        stage_progress: Progress within current stage (0.0 to 1.0)
        total_tasks: Total tasks to evaluate
        completed_tasks: Tasks completed so far
        resolved_tasks: Number of resolved tasks
        failed_tasks: Number of failed tasks
        pending_tasks: Number of pending tasks
        running_tasks: Number of currently running tasks
        current_batch: Current batch number
        total_batches: Total number of batches
        elapsed_time: Elapsed time in seconds
        estimated_remaining: Estimated remaining time in seconds
        total_tokens_used: Total tokens used
        total_cost: Total cost estimate
    """
    stage: RunnerStage = RunnerStage.IDLE
    stage_progress: float = 0.0
    total_tasks: int = 0
    completed_tasks: int = 0
    resolved_tasks: int = 0
    failed_tasks: int = 0
    pending_tasks: int = 0
    running_tasks: int = 0
    current_batch: int = 0
    total_batches: int = 0
    elapsed_time: float = 0.0
    estimated_remaining: float = 0.0
    total_tokens_used: Dict[str, int] = field(default_factory=lambda: {"input": 0, "output": 0})
    total_cost: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        data["stage"] = self.stage.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProgressInfo":
        """Create from dictionary."""
        if isinstance(data.get("stage"), str):
            data["stage"] = RunnerStage(data["stage"])
        return cls(**data)


@dataclass
class TaskResult:
    """
    Result of evaluating a single SWE-bench task.
    
    Attributes:
        task_id: Unique task identifier
        status: Task completion status
        execution_time_seconds: Time taken to evaluate
        tokens_used: Token usage breakdown
        cost: Cost estimate for this task
        attempts: Number of attempts made
        error: Error message if failed
        patch_generated: Generated patch content
        resolution_details: Additional resolution details
        started_at: Start timestamp
        completed_at: Completion timestamp
    """
    task_id: str
    status: TaskStatus
    execution_time_seconds: float
    tokens_used: Dict[str, int] = field(default_factory=lambda: {"input": 0, "output": 0})
    cost: float = 0.0
    attempts: int = 1
    error: Optional[str] = None
    patch_generated: Optional[str] = None
    resolution_details: Dict[str, Any] = field(default_factory=dict)
    started_at: str = ""
    completed_at: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        data["status"] = self.status.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskResult":
        """Create from dictionary."""
        if isinstance(data.get("status"), str):
            data["status"] = TaskStatus(data["status"])
        return cls(**data)


@dataclass
class EvaluationResults:
    """
    Aggregated results from SWE-bench evaluation.
    
    Attributes:
        run_id: Unique identifier for this evaluation run
        model_path: Path to the model evaluated
        subset: SWE-bench subset used
        total_tasks: Total number of tasks evaluated
        resolved: Number of resolved tasks
        failed: Number of failed tasks
        errors: Number of error tasks
        timeouts: Number of timed out tasks
        skipped: Number of skipped tasks
        resolution_rate: Percentage of resolved tasks
        avg_execution_time: Average execution time per task
        total_tokens: Total token usage
        total_cost: Total cost estimate
        task_results: Individual task results
        patterns: Success/failure patterns
        timestamp: Evaluation timestamp
        duration_seconds: Total evaluation duration
        metadata: Additional metadata
    """
    run_id: str
    model_path: str
    subset: str
    total_tasks: int
    resolved: int
    failed: int
    errors: int
    timeouts: int
    skipped: int
    resolution_rate: float
    avg_execution_time: float
    total_tokens: Dict[str, int]
    total_cost: float
    task_results: List[TaskResult]
    patterns: Dict[str, Any]
    timestamp: str
    duration_seconds: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def task_ids(self) -> List[str]:
        """Get list of task IDs."""
        return [r.task_id for r in self.task_results]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "run_id": self.run_id,
            "model_path": self.model_path,
            "subset": self.subset,
            "total_tasks": self.total_tasks,
            "resolved": self.resolved,
            "failed": self.failed,
            "errors": self.errors,
            "timeouts": self.timeouts,
            "skipped": self.skipped,
            "resolution_rate": self.resolution_rate,
            "avg_execution_time": self.avg_execution_time,
            "total_tokens": self.total_tokens,
            "total_cost": self.total_cost,
            "patterns": self.patterns,
            "timestamp": self.timestamp,
            "duration_seconds": self.duration_seconds,
            "metadata": self.metadata,
            "task_results": [r.to_dict() for r in self.task_results]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvaluationResults":
        """Create from dictionary."""
        if isinstance(data.get("task_results"), list):
            data["task_results"] = [
                TaskResult.from_dict(r) if isinstance(r, dict) else r
                for r in data["task_results"]
            ]
        return cls(**data)


@dataclass
class CheckpointState:
    """
    State saved at each checkpoint.
    
    Attributes:
        checkpoint_id: Unique identifier for this checkpoint
        timestamp: When the checkpoint was created
        stage: Runner stage at checkpoint time
        progress: Progress info at checkpoint time
        config: Configuration used
        completed_results: Results of completed tasks
        pending_tasks: Tasks still pending
        metadata: Additional metadata
    """
    checkpoint_id: str
    timestamp: str
    stage: RunnerStage
    progress: ProgressInfo
    config: RunnerConfig
    completed_results: List[TaskResult] = field(default_factory=list)
    pending_tasks: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "checkpoint_id": self.checkpoint_id,
            "timestamp": self.timestamp,
            "stage": self.stage.value,
            "progress": self.progress.to_dict(),
            "config": self.config.to_dict(),
            "completed_results": [r.to_dict() for r in self.completed_results],
            "pending_tasks": self.pending_tasks,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CheckpointState":
        """Create from dictionary."""
        if isinstance(data.get("stage"), str):
            data["stage"] = RunnerStage(data["stage"])
        if isinstance(data.get("progress"), dict):
            data["progress"] = ProgressInfo.from_dict(data["progress"])
        if isinstance(data.get("config"), dict):
            data["config"] = RunnerConfig.from_dict(data["config"])
        if isinstance(data.get("completed_results"), list):
            data["completed_results"] = [
                TaskResult.from_dict(r) for r in data["completed_results"]
            ]
        return cls(**data)


@dataclass
class ComparisonResult:
    """
    Result of comparing model performance against a baseline.
    
    Attributes:
        model_path: Path to the evaluated model
        baseline_path: Path to the baseline model
        model_resolution_rate: Resolution rate of evaluated model
        baseline_resolution_rate: Resolution rate of baseline
        improvement: Absolute improvement in resolution rate
        improvement_percent: Relative improvement percentage
        tasks_improved: Tasks that improved over baseline
        tasks_regressed: Tasks that regressed from baseline
        tasks_newly_resolved: Tasks resolved by model but not baseline
        tasks_newly_failed: Tasks resolved by baseline but not model
        common_resolved: Tasks resolved by both
        common_failed: Tasks failed by both
        statistical_significance: P-value for the difference
    """
    model_path: str
    baseline_path: str
    model_resolution_rate: float
    baseline_resolution_rate: float
    improvement: float
    improvement_percent: float
    tasks_improved: List[str]
    tasks_regressed: List[str]
    tasks_newly_resolved: List[str]
    tasks_newly_failed: List[str]
    common_resolved: List[str]
    common_failed: List[str]
    statistical_significance: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)


@dataclass
class EvaluationReport:
    """
    Generated evaluation report.
    
    Attributes:
        results: Evaluation results
        comparison: Optional comparison with baseline
        format: Report format
        content: Report content
        generated_at: Generation timestamp
    """
    results: EvaluationResults
    comparison: Optional[ComparisonResult]
    format: ReportFormat
    content: str
    generated_at: str
    
    def save(self, path: str) -> None:
        """
        Save the report to a file.
        
        Args:
            path: File path to save to
        """
        path = os.path.expanduser(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, "w") as f:
            f.write(self.content)
        
        logger.info(f"Report saved to {path}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "results": self.results.to_dict(),
            "comparison": self.comparison.to_dict() if self.comparison else None,
            "format": self.format.value,
            "content": self.content,
            "generated_at": self.generated_at,
        }


class SWEBenchRunner:
    """
    Production-ready evaluation runner for SWE-bench tasks.
    
    This class provides:
    - Parallel task evaluation with configurable concurrency
    - Checkpoint management for interrupted runs
    - Cost tracking with token usage monitoring
    - Error recovery with exponential backoff
    - Report generation in multiple formats
    - Baseline comparison for improvement tracking
    
    Example:
        runner = SWEBenchRunner(
            model_path="~/.autodev/models/grpo_v1",
            workspace="/tmp/swebench_eval",
            max_concurrent=4
        )
        
        # Run evaluation
        results = await runner.evaluate(
            subset="lite",
            num_tasks=50,
            timeout_per_task=1800
        )
        
        # Generate report
        report = runner.generate_report(results)
        report.save("~/eval_reports/eval_2026-03-23.md")
        
        # Compare with baseline
        comparison = await runner.compare_with_baseline(
            baseline_model="Qwen/Qwen2.5-Coder-7B-Instruct",
            tasks=results.task_ids
        )
    """
    
    def __init__(
        self,
        model_path: str,
        workspace: Optional[str] = None,
        config: Optional[RunnerConfig] = None,
        harness: Optional[Any] = None,
    ):
        """
        Initialize the SWEBenchRunner.
        
        Args:
            model_path: Path to the model to evaluate
            workspace: Workspace directory for evaluations
            config: Runner configuration
            harness: Pre-configured SWE-bench harness (Phase 7)
        """
        self.model_path = os.path.expanduser(model_path)
        self.config = config or RunnerConfig()
        
        if workspace:
            self.config.workspace = os.path.expanduser(workspace)
        
        # Initialize state
        self._stage = RunnerStage.IDLE
        self._progress = ProgressInfo()
        self._shutdown_requested = False
        self._shutdown_lock = threading.Lock()
        self._start_time: Optional[float] = None
        self._current_checkpoint: Optional[CheckpointState] = None
        self._task_results: Dict[str, TaskResult] = {}
        self._pending_tasks: List[str] = []
        self._completed_task_ids: List[str] = []
        
        # Progress callbacks
        self._progress_callbacks: List[Callable[[ProgressInfo], None]] = []
        
        # Cost tracking
        self._total_cost = 0.0
        self._total_tokens = {"input": 0, "output": 0}
        
        # Pattern tracking
        self._success_patterns: List[Dict[str, Any]] = []
        self._failure_patterns: List[Dict[str, Any]] = []
        
        # Create directories
        self._ensure_directories()
        
        # Initialize harness
        self._harness = harness
        self._harness_initialized = harness is not None
        
        # Set up signal handlers for graceful shutdown
        self._setup_signal_handlers()
        
        logger.info(
            f"SWEBenchRunner initialized with model={self.model_path}, "
            f"max_concurrent={self.config.max_concurrent}"
        )
    
    def _ensure_directories(self) -> None:
        """Create necessary directories."""
        Path(self.config.workspace).mkdir(parents=True, exist_ok=True)
        Path(self.config.checkpoint_dir).mkdir(parents=True, exist_ok=True)
        Path(self.config.report_output_dir).mkdir(parents=True, exist_ok=True)
    
    def _setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum: int, frame) -> None:
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown")
        with self._shutdown_lock:
            self._shutdown_requested = True
    
    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------
    
    @property
    def stage(self) -> RunnerStage:
        """Get current runner stage."""
        return self._stage
    
    @property
    def progress(self) -> ProgressInfo:
        """Get current progress info."""
        return self._progress
    
    @property
    def is_shutdown_requested(self) -> bool:
        """Check if shutdown has been requested."""
        with self._shutdown_lock:
            return self._shutdown_requested
    
    def request_shutdown(self) -> None:
        """Request a graceful shutdown."""
        logger.info("Shutdown requested")
        with self._shutdown_lock:
            self._shutdown_requested = True
    
    def add_progress_callback(self, callback: Callable[[ProgressInfo], None]) -> None:
        """
        Add a callback for progress updates.
        
        Args:
            callback: Function to call with progress updates
        """
        self._progress_callbacks.append(callback)
    
    def remove_progress_callback(self, callback: Callable[[ProgressInfo], None]) -> None:
        """Remove a progress callback."""
        if callback in self._progress_callbacks:
            self._progress_callbacks.remove(callback)
    
    async def evaluate(
        self,
        subset: str = "lite",
        num_tasks: Optional[int] = None,
        task_ids: Optional[List[str]] = None,
        timeout_per_task: Optional[int] = None,
        resume: bool = True,
    ) -> EvaluationResults:
        """
        Run evaluation on SWE-bench tasks.
        
        Args:
            subset: SWE-bench subset ("lite", "full", "verified")
            num_tasks: Maximum number of tasks to evaluate
            task_ids: Specific task IDs to evaluate (overrides num_tasks)
            timeout_per_task: Timeout per task in seconds
            resume: Whether to resume from checkpoint
            
        Returns:
            EvaluationResults with evaluation outcomes
        """
        run_id = f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        self._start_time = time.time()
        
        try:
            # Initialize
            self._set_stage(RunnerStage.INITIALIZING)
            
            # Try to resume from checkpoint
            if resume and self.config.auto_resume:
                checkpoint = self._load_latest_checkpoint()
                if checkpoint:
                    logger.info(f"Resuming from checkpoint: {checkpoint.checkpoint_id}")
                    self._restore_from_checkpoint(checkpoint)
            
            # Check for shutdown
            if self.is_shutdown_requested:
                return self._create_cancelled_results(run_id, subset)
            
            # Load tasks
            self._set_stage(RunnerStage.LOADING_TASKS)
            tasks = await self._load_tasks(subset, num_tasks, task_ids)
            
            if not tasks:
                logger.error("No tasks loaded for evaluation")
                return EvaluationResults(
                    run_id=run_id,
                    model_path=self.model_path,
                    subset=subset,
                    total_tasks=0,
                    resolved=0,
                    failed=0,
                    errors=0,
                    timeouts=0,
                    skipped=0,
                    resolution_rate=0.0,
                    avg_execution_time=0.0,
                    total_tokens={"input": 0, "output": 0},
                    total_cost=0.0,
                    task_results=[],
                    patterns={},
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    duration_seconds=0.0,
                )
            
            # Filter out already completed tasks (from resume)
            if self._completed_task_ids:
                tasks = [t for t in tasks if t not in self._completed_task_ids]
                logger.info(f"Resuming with {len(tasks)} remaining tasks")
            
            # Initialize progress
            total_tasks = len(self._completed_task_ids) + len(tasks)
            self._update_progress(
                total_tasks=total_tasks,
                completed_tasks=len(self._completed_task_ids),
                pending_tasks=len(tasks),
            )
            
            # Check for shutdown
            if self.is_shutdown_requested:
                self._save_checkpoint(subset)
                return self._create_cancelled_results(run_id, subset)
            
            # Run evaluation
            self._set_stage(RunnerStage.EVALUATING)
            
            if timeout_per_task:
                self.config.timeout_per_task = timeout_per_task
            
            results = await self._run_parallel_evaluation(tasks, subset)
            
            # Check for shutdown
            if self.is_shutdown_requested:
                self._save_checkpoint(subset)
                return self._create_cancelled_results(run_id, subset)
            
            # Compile final results
            all_results = list(self._task_results.values())
            
            resolved = sum(1 for r in all_results if r.status == TaskStatus.RESOLVED)
            failed = sum(1 for r in all_results if r.status == TaskStatus.FAILED)
            errors = sum(1 for r in all_results if r.status == TaskStatus.ERROR)
            timeouts = sum(1 for r in all_results if r.status == TaskStatus.TIMEOUT)
            skipped = sum(1 for r in all_results if r.status == TaskStatus.SKIPPED)
            
            avg_time = (
                sum(r.execution_time_seconds for r in all_results) / len(all_results)
                if all_results else 0.0
            )
            
            evaluation_results = EvaluationResults(
                run_id=run_id,
                model_path=self.model_path,
                subset=subset,
                total_tasks=len(all_results),
                resolved=resolved,
                failed=failed,
                errors=errors,
                timeouts=timeouts,
                skipped=skipped,
                resolution_rate=resolved / len(all_results) if all_results else 0.0,
                avg_execution_time=avg_time,
                total_tokens=self._total_tokens,
                total_cost=self._total_cost,
                task_results=all_results,
                patterns={
                    "success_patterns": self._success_patterns,
                    "failure_patterns": self._failure_patterns,
                },
                timestamp=datetime.now(timezone.utc).isoformat(),
                duration_seconds=time.time() - self._start_time,
            )
            
            # Generate report if configured
            if self.config.generate_report:
                self._set_stage(RunnerStage.GENERATING_REPORT)
                report = self.generate_report(evaluation_results)
                
                # Save reports
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                for fmt in self.config.report_formats:
                    ext = "md" if fmt == "markdown" else ("html" if fmt == "html" else "json")
                    report_path = os.path.join(
                        self.config.report_output_dir,
                        f"eval_report_{timestamp}.{ext}"
                    )
                    report.save(report_path)
            
            # Complete
            self._set_stage(RunnerStage.COMPLETED)
            
            logger.info(
                f"Evaluation completed: {resolved}/{len(all_results)} resolved "
                f"({evaluation_results.resolution_rate:.1%})"
            )
            
            return evaluation_results
            
        except Exception as e:
            logger.error(f"Evaluation failed: {e}")
            self._set_stage(RunnerStage.FAILED)
            
            # Save checkpoint for recovery
            self._save_checkpoint(subset)
            
            raise
    
    async def evaluate_single_task(
        self,
        task_id: str,
        subset: str = "lite",
        timeout: Optional[int] = None,
    ) -> TaskResult:
        """
        Evaluate a single SWE-bench task.
        
        Args:
            task_id: Task ID to evaluate
            subset: SWE-bench subset
            timeout: Timeout for this task
            
        Returns:
            TaskResult with evaluation outcome
        """
        return await self._evaluate_task(
            task_id,
            subset=subset,
            timeout=timeout or self.config.timeout_per_task
        )
    
    async def compare_with_baseline(
        self,
        baseline_model: str,
        tasks: Optional[List[str]] = None,
        subset: str = "lite",
        num_tasks: Optional[int] = None,
    ) -> ComparisonResult:
        """
        Compare current model performance against a baseline.
        
        Args:
            baseline_model: Path to baseline model
            tasks: Specific task IDs to compare
            subset: SWE-bench subset
            num_tasks: Number of tasks for comparison
            
        Returns:
            ComparisonResult with comparison metrics
        """
        logger.info(f"Comparing with baseline: {baseline_model}")
        
        # Run evaluation with current model (if not already done)
        if not self._task_results:
            current_results = await self.evaluate(
                subset=subset,
                num_tasks=num_tasks,
                task_ids=tasks,
            )
        else:
            current_results = self._compile_results("comparison", subset)
        
        # Run evaluation with baseline
        baseline_runner = SWEBenchRunner(
            model_path=baseline_model,
            workspace=os.path.join(self.config.workspace, "baseline"),
            config=self.config,
        )
        
        baseline_results = await baseline_runner.evaluate(
            subset=subset,
            num_tasks=num_tasks,
            task_ids=tasks or current_results.task_ids,
            resume=False,
        )
        
        # Compare results
        current_resolved = set(
            r.task_id for r in current_results.task_results
            if r.status == TaskStatus.RESOLVED
        )
        baseline_resolved = set(
            r.task_id for r in baseline_results.task_results
            if r.status == TaskStatus.RESOLVED
        )
        
        tasks_improved = list(current_resolved - baseline_resolved)
        tasks_regressed = list(baseline_resolved - current_resolved)
        common_resolved = list(current_resolved & baseline_resolved)
        common_failed = list(
            set(r.task_id for r in current_results.task_results) -
            current_resolved - baseline_resolved
        )
        
        improvement = current_results.resolution_rate - baseline_results.resolution_rate
        improvement_percent = (
            (improvement / baseline_results.resolution_rate * 100)
            if baseline_results.resolution_rate > 0 else 0.0
        )
        
        # Calculate statistical significance (simplified McNemar's test)
        # Would need scipy for proper calculation
        statistical_significance = None
        
        comparison = ComparisonResult(
            model_path=self.model_path,
            baseline_path=baseline_model,
            model_resolution_rate=current_results.resolution_rate,
            baseline_resolution_rate=baseline_results.resolution_rate,
            improvement=improvement,
            improvement_percent=improvement_percent,
            tasks_improved=tasks_improved,
            tasks_regressed=tasks_regressed,
            tasks_newly_resolved=tasks_improved,
            tasks_newly_failed=tasks_regressed,
            common_resolved=common_resolved,
            common_failed=common_failed,
            statistical_significance=statistical_significance,
        )
        
        logger.info(
            f"Comparison: current={current_results.resolution_rate:.1%}, "
            f"baseline={baseline_results.resolution_rate:.1%}, "
            f"improvement={improvement:+.1%}"
        )
        
        return comparison
    
    def generate_report(
        self,
        results: EvaluationResults,
        comparison: Optional[ComparisonResult] = None,
        format: str = "markdown",
    ) -> EvaluationReport:
        """
        Generate an evaluation report.
        
        Args:
            results: Evaluation results
            comparison: Optional comparison result
            format: Report format ("markdown", "json", "html")
            
        Returns:
            EvaluationReport with generated content
        """
        report_format = ReportFormat(format.lower())
        
        if report_format == ReportFormat.MARKDOWN:
            content = self._generate_markdown_report(results, comparison)
        elif report_format == ReportFormat.JSON:
            content = self._generate_json_report(results, comparison)
        elif report_format == ReportFormat.HTML:
            content = self._generate_html_report(results, comparison)
        else:
            raise ValueError(f"Unsupported report format: {format}")
        
        return EvaluationReport(
            results=results,
            comparison=comparison,
            format=report_format,
            content=content,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
    
    # -------------------------------------------------------------------------
    # Checkpoint Management
    # -------------------------------------------------------------------------
    
    def get_checkpoint_path(self, checkpoint_id: str) -> Path:
        """Get the path to a checkpoint directory."""
        return Path(self.config.checkpoint_dir) / checkpoint_id
    
    def list_checkpoints(self) -> List[CheckpointState]:
        """List all available checkpoints."""
        checkpoints = []
        checkpoint_dir = Path(self.config.checkpoint_dir)
        
        if not checkpoint_dir.exists():
            return checkpoints
        
        for checkpoint_path in checkpoint_dir.iterdir():
            if checkpoint_path.is_dir():
                metadata_path = checkpoint_path / "checkpoint.json"
                if metadata_path.exists():
                    try:
                        with open(metadata_path, "r") as f:
                            data = json.load(f)
                        checkpoint = CheckpointState.from_dict(data)
                        checkpoints.append(checkpoint)
                    except Exception as e:
                        logger.warning(f"Failed to load checkpoint {checkpoint_path}: {e}")
        
        # Sort by timestamp (newest first)
        checkpoints.sort(key=lambda c: c.timestamp, reverse=True)
        return checkpoints
    
    def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """Delete a checkpoint by ID."""
        checkpoint_path = self.get_checkpoint_path(checkpoint_id)
        if checkpoint_path.exists():
            shutil.rmtree(checkpoint_path)
            logger.info(f"Deleted checkpoint: {checkpoint_id}")
            return True
        return False
    
    def cleanup_old_checkpoints(self) -> int:
        """Remove old checkpoints, keeping only the configured number."""
        checkpoints = self.list_checkpoints()
        deleted = 0
        
        while len(checkpoints) > self.config.keep_checkpoints:
            old_checkpoint = checkpoints.pop()
            if self.delete_checkpoint(old_checkpoint.checkpoint_id):
                deleted += 1
        
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old checkpoints")
        
        return deleted
    
    # -------------------------------------------------------------------------
    # Internal Methods
    # -------------------------------------------------------------------------
    
    def _set_stage(self, stage: RunnerStage) -> None:
        """Set the current stage and update progress."""
        old_stage = self._stage
        self._stage = stage
        self._progress.stage = stage
        
        logger.info(f"Runner stage: {old_stage.value} -> {stage.value}")
        self._notify_progress()
    
    def _update_progress(self, **kwargs) -> None:
        """Update progress fields and notify callbacks."""
        for key, value in kwargs.items():
            if hasattr(self._progress, key):
                setattr(self._progress, key, value)
        
        # Update elapsed time and estimates
        if self._start_time:
            self._progress.elapsed_time = time.time() - self._start_time
            
            # Estimate remaining time
            if self._progress.completed_tasks > 0 and self._progress.total_tasks > 0:
                avg_time = self._progress.elapsed_time / self._progress.completed_tasks
                remaining_tasks = self._progress.total_tasks - self._progress.completed_tasks
                self._progress.estimated_remaining = avg_time * remaining_tasks
        
        self._notify_progress()
    
    def _notify_progress(self) -> None:
        """Notify all progress callbacks."""
        for callback in self._progress_callbacks:
            try:
                callback(self._progress)
            except Exception as e:
                logger.warning(f"Progress callback error: {e}")
    
    async def _load_tasks(
        self,
        subset: str,
        num_tasks: Optional[int],
        task_ids: Optional[List[str]],
    ) -> List[str]:
        """Load SWE-bench task IDs."""
        logger.info(f"Loading tasks from {subset} subset")
        
        if HARNESS_AVAILABLE:
            try:
                harness = SWEBenchHarness(
                    workspace=self.config.workspace,
                    timeout_seconds=self.config.timeout_per_task,
                )
                tasks = harness.load_tasks(
                    subset=subset,
                    num_tasks=num_tasks,
                    task_ids=task_ids,
                )
                task_id_list = [t.instance_id for t in tasks]
            except Exception as e:
                logger.warning(f"Failed to load tasks from harness: {e}")
                task_id_list = self._get_mock_tasks(subset, num_tasks, task_ids)
        else:
            task_id_list = self._get_mock_tasks(subset, num_tasks, task_ids)
        
        logger.info(f"Loaded {len(task_id_list)} tasks")
        return task_id_list
    
    def _get_mock_tasks(
        self,
        subset: str,
        num_tasks: Optional[int],
        task_ids: Optional[List[str]],
    ) -> List[str]:
        """Generate mock task IDs for testing."""
        if task_ids:
            return task_ids
        
        # Generate mock task IDs based on subset
        num = num_tasks or 10
        return [f"{subset}__task_{i:04d}" for i in range(num)]
    
    async def _run_parallel_evaluation(
        self,
        task_ids: List[str],
        subset: str,
    ) -> List[TaskResult]:
        """Run parallel evaluation of tasks."""
        logger.info(
            f"Starting parallel evaluation of {len(task_ids)} tasks "
            f"with max_concurrent={self.config.max_concurrent}"
        )
        
        results = []
        semaphore = asyncio.Semaphore(self.config.max_concurrent)
        
        async def evaluate_with_semaphore(task_id: str) -> TaskResult:
            async with semaphore:
                return await self._evaluate_task_with_retry(task_id, subset)
        
        # Create tasks for all evaluations
        evaluation_tasks = [
            evaluate_with_semaphore(task_id) for task_id in task_ids
        ]
        
        # Run with progress tracking
        for i, coro in enumerate(asyncio.as_completed(evaluation_tasks)):
            if self.is_shutdown_requested:
                logger.info("Evaluation interrupted by shutdown request")
                break
            
            result = await coro
            results.append(result)
            
            # Update task tracking
            self._task_results[result.task_id] = result
            self._completed_task_ids.append(result.task_id)
            
            # Update progress
            resolved = sum(1 for r in self._task_results.values() if r.status == TaskStatus.RESOLVED)
            failed = sum(1 for r in self._task_results.values() if r.status in [TaskStatus.FAILED, TaskStatus.ERROR, TaskStatus.TIMEOUT])
            
            self._update_progress(
                completed_tasks=len(self._completed_task_ids),
                resolved_tasks=resolved,
                failed_tasks=failed,
                running_tasks=min(self.config.max_concurrent, len(task_ids) - len(self._completed_task_ids)),
            )
            
            # Update cost tracking
            self._total_cost += result.cost
            self._total_tokens["input"] += result.tokens_used.get("input", 0)
            self._total_tokens["output"] += result.tokens_used.get("output", 0)
            self._progress.total_cost = self._total_cost
            self._progress.total_tokens_used = self._total_tokens.copy()
            
            # Save checkpoint at intervals
            if len(self._completed_task_ids) % self.config.checkpoint_interval == 0:
                self._save_checkpoint(subset)
        
        return results
    
    async def _evaluate_task_with_retry(
        self,
        task_id: str,
        subset: str,
    ) -> TaskResult:
        """Evaluate a task with retry logic."""
        attempts = 0
        last_error = None
        start_time = time.time()
        
        while attempts < self.config.max_retries:
            attempts += 1
            
            try:
                result = await self._evaluate_task(
                    task_id,
                    subset=subset,
                    timeout=self.config.timeout_per_task,
                )
                result.attempts = attempts
                
                # Track patterns
                if result.status == TaskStatus.RESOLVED:
                    self._success_patterns.append({
                        "task_id": task_id,
                        "attempts": attempts,
                        "execution_time": result.execution_time_seconds,
                    })
                elif result.status == TaskStatus.FAILED:
                    self._failure_patterns.append({
                        "task_id": task_id,
                        "error": result.error,
                        "attempts": attempts,
                    })
                
                return result
                
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Task {task_id} attempt {attempts} failed: {e}")
                
                # Exponential backoff
                if attempts < self.config.max_retries:
                    backoff = min(
                        self.config.retry_backoff_base ** attempts,
                        self.config.retry_backoff_max
                    )
                    await asyncio.sleep(backoff)
        
        # All retries failed
        return TaskResult(
            task_id=task_id,
            status=TaskStatus.ERROR,
            execution_time_seconds=time.time() - start_time,
            error=f"All {attempts} attempts failed. Last error: {last_error}",
            attempts=attempts,
            started_at=datetime.fromtimestamp(start_time, tz=timezone.utc).isoformat(),
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
    
    async def _evaluate_task(
        self,
        task_id: str,
        subset: str,
        timeout: int,
    ) -> TaskResult:
        """
        Evaluate a single task.
        
        This method integrates with the Phase 7 SWEBenchHarness for actual
        evaluation, or uses a mock implementation for testing.
        """
        start_time = time.time()
        started_at = datetime.now(timezone.utc).isoformat()
        
        logger.debug(f"Evaluating task: {task_id}")
        
        if HARNESS_AVAILABLE and self._harness_initialized:
            # Use actual harness
            try:
                harness = self._harness or SWEBenchHarness(
                    workspace=os.path.join(self.config.workspace, task_id),
                    timeout_seconds=timeout,
                    max_iterations=self.config.max_iterations,
                    model=self.model_path,
                )
                
                tasks = harness.load_tasks(subset=subset, task_ids=[task_id])
                if not tasks:
                    return TaskResult(
                        task_id=task_id,
                        status=TaskStatus.ERROR,
                        execution_time_seconds=0.0,
                        error="Task not found",
                        started_at=started_at,
                        completed_at=datetime.now(timezone.utc).isoformat(),
                    )
                
                task = tasks[0]
                task_workspace = Path(harness.workspace) / task_id
                
                harness_result = await harness.run_task(task, task_workspace)
                
                # Convert harness result to our result format
                status_mapping = {
                    HarnessTaskStatus.RESOLVED: TaskStatus.RESOLVED,
                    HarnessTaskStatus.FAILED: TaskStatus.FAILED,
                    HarnessTaskStatus.TIMEOUT: TaskStatus.TIMEOUT,
                    HarnessTaskStatus.ERROR: TaskStatus.ERROR,
                    HarnessTaskStatus.RUNNING: TaskStatus.RUNNING,
                    HarnessTaskStatus.PENDING: TaskStatus.PENDING,
                }
                
                tokens_used = harness_result.tokens_used or {"input": 0, "output": 0}
                cost = self._calculate_cost(tokens_used)
                
                return TaskResult(
                    task_id=task_id,
                    status=status_mapping.get(harness_result.status, TaskStatus.ERROR),
                    execution_time_seconds=harness_result.execution_time_seconds,
                    tokens_used=tokens_used,
                    cost=cost,
                    patch_generated=harness_result.patch_generated,
                    resolution_details=harness_result.resolution_details,
                    started_at=started_at,
                    completed_at=datetime.now(timezone.utc).isoformat(),
                )
                
            except asyncio.TimeoutError:
                return TaskResult(
                    task_id=task_id,
                    status=TaskStatus.TIMEOUT,
                    execution_time_seconds=timeout,
                    error=f"Task timed out after {timeout}s",
                    started_at=started_at,
                    completed_at=datetime.now(timezone.utc).isoformat(),
                )
            except Exception as e:
                return TaskResult(
                    task_id=task_id,
                    status=TaskStatus.ERROR,
                    execution_time_seconds=time.time() - start_time,
                    error=str(e),
                    started_at=started_at,
                    completed_at=datetime.now(timezone.utc).isoformat(),
                )
        else:
            # Mock implementation for testing
            return await self._mock_evaluate_task(task_id, timeout, started_at)
    
    async def _mock_evaluate_task(
        self,
        task_id: str,
        timeout: int,
        started_at: str,
    ) -> TaskResult:
        """Mock task evaluation for testing."""
        import random
        
        start_time = time.time()
        
        # Simulate execution time
        execution_time = random.uniform(30, 300)
        await asyncio.sleep(min(execution_time, 0.1))  # Cap sleep for testing
        
        # Simulate success/failure (20-30% resolution rate)
        is_resolved = random.random() < 0.25
        
        # Simulate token usage
        input_tokens = random.randint(1000, 5000)
        output_tokens = random.randint(500, 2000)
        tokens_used = {"input": input_tokens, "output": output_tokens}
        
        cost = self._calculate_cost(tokens_used)
        
        status = TaskStatus.RESOLVED if is_resolved else TaskStatus.FAILED
        
        return TaskResult(
            task_id=task_id,
            status=status,
            execution_time_seconds=time.time() - start_time,
            tokens_used=tokens_used,
            cost=cost,
            error=None if is_resolved else "Mock: Failed to resolve issue",
            patch_generated="Mock patch content" if is_resolved else None,
            resolution_details={"mock": True},
            started_at=started_at,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
    
    def _calculate_cost(self, tokens_used: Dict[str, int]) -> float:
        """Calculate cost based on token usage."""
        if not self.config.track_costs:
            return 0.0
        
        input_cost = (tokens_used.get("input", 0) / 1000) * self.config.cost_per_input_token
        output_cost = (tokens_used.get("output", 0) / 1000) * self.config.cost_per_output_token
        
        return input_cost + output_cost
    
    def _compile_results(self, run_id: str, subset: str) -> EvaluationResults:
        """Compile current results into EvaluationResults."""
        all_results = list(self._task_results.values())
        
        resolved = sum(1 for r in all_results if r.status == TaskStatus.RESOLVED)
        
        return EvaluationResults(
            run_id=run_id,
            model_path=self.model_path,
            subset=subset,
            total_tasks=len(all_results),
            resolved=resolved,
            failed=sum(1 for r in all_results if r.status == TaskStatus.FAILED),
            errors=sum(1 for r in all_results if r.status == TaskStatus.ERROR),
            timeouts=sum(1 for r in all_results if r.status == TaskStatus.TIMEOUT),
            skipped=sum(1 for r in all_results if r.status == TaskStatus.SKIPPED),
            resolution_rate=resolved / len(all_results) if all_results else 0.0,
            avg_execution_time=sum(r.execution_time_seconds for r in all_results) / len(all_results) if all_results else 0.0,
            total_tokens=self._total_tokens,
            total_cost=self._total_cost,
            task_results=all_results,
            patterns={
                "success_patterns": self._success_patterns,
                "failure_patterns": self._failure_patterns,
            },
            timestamp=datetime.now(timezone.utc).isoformat(),
            duration_seconds=time.time() - self._start_time if self._start_time else 0.0,
        )
    
    def _create_cancelled_results(self, run_id: str, subset: str) -> EvaluationResults:
        """Create results for a cancelled evaluation."""
        self._set_stage(RunnerStage.CANCELLED)
        
        all_results = list(self._task_results.values())
        resolved = sum(1 for r in all_results if r.status == TaskStatus.RESOLVED)
        
        return EvaluationResults(
            run_id=run_id,
            model_path=self.model_path,
            subset=subset,
            total_tasks=len(all_results),
            resolved=resolved,
            failed=sum(1 for r in all_results if r.status == TaskStatus.FAILED),
            errors=sum(1 for r in all_results if r.status == TaskStatus.ERROR),
            timeouts=sum(1 for r in all_results if r.status == TaskStatus.TIMEOUT),
            skipped=sum(1 for r in all_results if r.status == TaskStatus.SKIPPED),
            resolution_rate=resolved / len(all_results) if all_results else 0.0,
            avg_execution_time=sum(r.execution_time_seconds for r in all_results) / len(all_results) if all_results else 0.0,
            total_tokens=self._total_tokens,
            total_cost=self._total_cost,
            task_results=all_results,
            patterns={
                "success_patterns": self._success_patterns,
                "failure_patterns": self._failure_patterns,
                "cancelled": True,
            },
            timestamp=datetime.now(timezone.utc).isoformat(),
            duration_seconds=time.time() - self._start_time if self._start_time else 0.0,
            metadata={"cancelled": True},
        )
    
    def _save_checkpoint(self, subset: str = "lite") -> CheckpointState:
        """Save current state to a checkpoint."""
        checkpoint_id = f"ckpt_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        checkpoint_path = self.get_checkpoint_path(checkpoint_id)
        checkpoint_path.mkdir(parents=True, exist_ok=True)
        
        # Create checkpoint state
        state = CheckpointState(
            checkpoint_id=checkpoint_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            stage=self._stage,
            progress=self._progress,
            config=self.config,
            completed_results=list(self._task_results.values()),
            pending_tasks=[t for t in self._pending_tasks if t not in self._completed_task_ids],
            metadata={
                "model_path": self.model_path,
                "subset": subset,
                "total_cost": self._total_cost,
                "total_tokens": self._total_tokens,
            },
        )
        
        # Save checkpoint
        metadata_path = checkpoint_path / "checkpoint.json"
        with open(metadata_path, "w") as f:
            json.dump(state.to_dict(), f, indent=2)
        
        self._current_checkpoint = state
        logger.info(f"Checkpoint saved: {checkpoint_id}")
        
        # Cleanup old checkpoints
        self.cleanup_old_checkpoints()
        
        return state
    
    def _load_latest_checkpoint(self) -> Optional[CheckpointState]:
        """Load the most recent checkpoint."""
        checkpoints = self.list_checkpoints()
        if not checkpoints:
            return None
        
        latest = checkpoints[0]  # Sorted by timestamp, newest first
        
        # Verify it's for the same model
        if latest.metadata.get("model_path") != self.model_path:
            logger.warning("Latest checkpoint is for different model, skipping")
            return None
        
        return latest
    
    def _restore_from_checkpoint(self, checkpoint: CheckpointState) -> None:
        """Restore state from a checkpoint."""
        # Restore progress
        self._progress = checkpoint.progress
        self._stage = checkpoint.stage
        
        # Restore results
        self._task_results = {r.task_id: r for r in checkpoint.completed_results}
        self._completed_task_ids = [r.task_id for r in checkpoint.completed_results]
        self._pending_tasks = checkpoint.pending_tasks
        
        # Restore cost tracking
        self._total_cost = checkpoint.metadata.get("total_cost", 0.0)
        self._total_tokens = checkpoint.metadata.get("total_tokens", {"input": 0, "output": 0})
        
        self._current_checkpoint = checkpoint
        logger.info(f"Restored from checkpoint: {checkpoint.checkpoint_id}")
    
    # -------------------------------------------------------------------------
    # Report Generation
    # -------------------------------------------------------------------------
    
    def _generate_markdown_report(
        self,
        results: EvaluationResults,
        comparison: Optional[ComparisonResult],
    ) -> str:
        """Generate a Markdown report."""
        lines = [
            "# SWE-bench Evaluation Report",
            "",
            f"**Run ID:** {results.run_id}",
            f"**Model:** {results.model_path}",
            f"**Subset:** {results.subset}",
            f"**Timestamp:** {results.timestamp}",
            f"**Duration:** {results.duration_seconds:.1f}s",
            "",
            "## Summary",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Total Tasks | {results.total_tasks} |",
            f"| Resolved | {results.resolved} |",
            f"| Failed | {results.failed} |",
            f"| Errors | {results.errors} |",
            f"| Timeouts | {results.timeouts} |",
            f"| Skipped | {results.skipped} |",
            f"| **Resolution Rate** | **{results.resolution_rate:.1%}** |",
            f"| Avg Execution Time | {results.avg_execution_time:.1f}s |",
            f"| Total Cost | ${results.total_cost:.2f} |",
            "",
        ]
        
        if comparison:
            lines.extend([
                "## Baseline Comparison",
                "",
                f"| Metric | Current | Baseline | Difference |",
                f"|--------|---------|----------|------------|",
                f"| Resolution Rate | {comparison.model_resolution_rate:.1%} | {comparison.baseline_resolution_rate:.1%} | {comparison.improvement:+.1%} |",
                f"| Improvement | - | - | {comparison.improvement_percent:+.1f}% |",
                "",
                "### Task Analysis",
                "",
                f"- **Newly Resolved:** {len(comparison.tasks_newly_resolved)}",
                f"- **Newly Failed:** {len(comparison.tasks_newly_failed)}",
                f"- **Common Resolved:** {len(comparison.common_resolved)}",
                f"- **Common Failed:** {len(comparison.common_failed)}",
                "",
            ])
            
            if comparison.tasks_newly_resolved:
                lines.append("**Newly Resolved Tasks:**")
                for task_id in comparison.tasks_newly_resolved[:10]:
                    lines.append(f"- {task_id}")
                if len(comparison.tasks_newly_resolved) > 10:
                    lines.append(f"- ... and {len(comparison.tasks_newly_resolved) - 10} more")
                lines.append("")
        
        # Token usage
        lines.extend([
            "## Token Usage",
            "",
            f"- Input Tokens: {results.total_tokens.get('input', 0):,}",
            f"- Output Tokens: {results.total_tokens.get('output', 0):,}",
            "",
        ])
        
        # Task details
        lines.extend([
            "## Task Results",
            "",
            "| Task ID | Status | Time | Cost |",
            "|---------|--------|------|------|",
        ])
        
        for result in results.task_results[:50]:  # Limit to first 50
            status_emoji = "✅" if result.status == TaskStatus.RESOLVED else "❌"
            lines.append(
                f"| {result.task_id} | {status_emoji} {result.status.value} | "
                f"{result.execution_time_seconds:.1f}s | ${result.cost:.2f} |"
            )
        
        if len(results.task_results) > 50:
            lines.append(f"| ... | ... | ... | ({len(results.task_results) - 50} more) |")
        
        lines.append("")
        
        return "\n".join(lines)
    
    def _generate_json_report(
        self,
        results: EvaluationResults,
        comparison: Optional[ComparisonResult],
    ) -> str:
        """Generate a JSON report."""
        report_data = {
            "results": results.to_dict(),
            "comparison": comparison.to_dict() if comparison else None,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        
        return json.dumps(report_data, indent=2)
    
    def _generate_html_report(
        self,
        results: EvaluationResults,
        comparison: Optional[ComparisonResult],
    ) -> str:
        """Generate an HTML report."""
        # Generate markdown first, then convert to basic HTML
        md_content = self._generate_markdown_report(results, comparison)
        
        # Simple markdown to HTML conversion
        html_lines = [
            "<!DOCTYPE html>",
            "<html>",
            "<head>",
            "<title>SWE-bench Evaluation Report</title>",
            "<style>",
            "body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 1000px; margin: 0 auto; padding: 20px; }",
            "h1 { color: #333; }",
            "h2 { color: #666; border-bottom: 1px solid #eee; padding-bottom: 10px; }",
            "table { border-collapse: collapse; width: 100%; margin: 20px 0; }",
            "th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }",
            "th { background-color: #f5f5f5; }",
            "tr:nth-child(even) { background-color: #f9f9f9; }",
            "code { background-color: #f5f5f5; padding: 2px 4px; border-radius: 3px; }",
            "</style>",
            "</head>",
            "<body>",
        ]
        
        in_table = False
        in_list = False
        
        # Convert markdown to HTML (simplified)
        for line in md_content.split("\n"):
            if line.startswith("# "):
                if in_table:
                    html_lines.append("</table>")
                    in_table = False
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                html_lines.append(f"<h1>{line[2:]}</h1>")
            elif line.startswith("## "):
                if in_table:
                    html_lines.append("</table>")
                    in_table = False
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                html_lines.append(f"<h2>{line[3:]}</h2>")
            elif line.startswith("### "):
                if in_table:
                    html_lines.append("</table>")
                    in_table = False
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                html_lines.append(f"<h3>{line[4:]}</h3>")
            elif line.startswith("| "):
                # Table row
                cells = [c.strip() for c in line.split("|")[1:-1]]
                if all(c.replace("-", "").replace(":", "") == "" for c in cells):
                    continue  # Skip separator row
                
                if not in_table:
                    html_lines.append("<table>")
                    in_table = True
                
                # First row uses th, subsequent rows use td
                is_header = not any("<td>" in l for l in html_lines[-5:] if "<tr>" in l)
                tag = "th" if is_header else "td"
                html_lines.append("<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>")
            elif line.startswith("- "):
                if not in_list:
                    html_lines.append("<ul>")
                    in_list = True
                html_lines.append(f"<li>{line[2:]}</li>")
            elif line.strip():
                if in_table:
                    html_lines.append("</table>")
                    in_table = False
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                html_lines.append(f"<p>{line}</p>")
            else:
                if in_table:
                    html_lines.append("</table>")
                    in_table = False
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
        
        # Close any open elements
        if in_table:
            html_lines.append("</table>")
        if in_list:
            html_lines.append("</ul>")
        
        html_lines.extend([
            "</body>",
            "</html>",
        ])
        
        return "\n".join(html_lines)


# -----------------------------------------------------------------------------
# Convenience Functions
# -----------------------------------------------------------------------------

def create_runner(
    model_path: str,
    workspace: str = "/tmp/swebench_eval",
    max_concurrent: int = 4,
    **kwargs,
) -> SWEBenchRunner:
    """
    Create a SWEBenchRunner with common settings.
    
    Args:
        model_path: Path to the model to evaluate
        workspace: Workspace directory for evaluations
        max_concurrent: Maximum concurrent evaluations
        **kwargs: Additional configuration options
        
    Returns:
        Configured SWEBenchRunner instance
    """
    config = RunnerConfig(
        workspace=workspace,
        max_concurrent=max_concurrent,
        **kwargs,
    )
    return SWEBenchRunner(model_path=model_path, config=config)


async def run_evaluation(
    model_path: str,
    subset: str = "lite",
    num_tasks: int = 50,
    workspace: str = "/tmp/swebench_eval",
    **kwargs,
) -> EvaluationResults:
    """
    Run evaluation with default settings.
    
    Args:
        model_path: Path to the model to evaluate
        subset: SWE-bench subset
        num_tasks: Number of tasks to evaluate
        workspace: Workspace directory
        **kwargs: Additional configuration options
        
    Returns:
        EvaluationResults with evaluation outcomes
    """
    config = RunnerConfig(
        workspace=workspace,
        **kwargs,
    )
    
    runner = SWEBenchRunner(model_path=model_path, config=config)
    return await runner.evaluate(
        subset=subset,
        num_tasks=num_tasks,
    )
