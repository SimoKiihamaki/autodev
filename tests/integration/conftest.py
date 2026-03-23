"""
Pytest configuration and fixtures for AutoDev Phase 9 Integration Tests.

This conftest.py provides fixtures for testing the integration between:
- TrainingOrchestrator
- SWEBenchRunner
- MetricsDashboard
- Training pipeline components

Based on: ~/Documents/Obsidian/Hermes/Knowledge/AutoDev/Integration_Tests_Spec.md
"""

import asyncio
import json
import logging
import os
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union
from unittest.mock import MagicMock, Mock, AsyncMock, patch

import pytest

# Configure Python path for imports
_project_root = Path(__file__).parent.parent.parent
_src_dir = _project_root / "src"

if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


# =============================================================================
# Test Markers Configuration
# =============================================================================

def pytest_configure(config):
    """Configure custom pytest markers for integration tests."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow (> 60s)"
    )
    config.addinivalue_line(
        "markers", "requires_gpu: mark test as requiring GPU"
    )
    config.addinivalue_line(
        "markers", "requires_network: mark test as requiring network access"
    )
    config.addinivalue_line(
        "markers", "e2e: mark test as end-to-end test"
    )
    config.addinivalue_line(
        "markers", "checkpoint: mark test as checkpoint/recovery test"
    )
    config.addinivalue_line(
        "markers", "evaluation: mark test as evaluation pipeline test"
    )
    config.addinivalue_line(
        "markers", "cost_tracking: mark test as cost tracking test"
    )
    config.addinivalue_line(
        "markers", "shutdown: mark test as graceful shutdown test"
    )


# =============================================================================
# Enum Definitions (mirroring real implementations)
# =============================================================================

class MockOrchestratorStage(Enum):
    """Mock stages of the orchestrator training cycle."""
    IDLE = "idle"
    INITIALIZING = "initializing"
    COLLECTING_DATA = "collecting_data"
    COMPUTING_REWARDS = "computing_rewards"
    TRAINING = "training"
    EVALUATING = "evaluating"
    REGISTERING_MODEL = "registering_model"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MockTraceStatus(Enum):
    """Mock trace status values."""
    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    ERROR = "error"
    PARTIAL = "partial"


class MockTrainingStage(Enum):
    """Mock training stage values."""
    SFT = "sft"
    GRPO = "grpo"
    EVALUATION = "evaluation"
    COMPLETE = "complete"


# =============================================================================
# Mock Data Classes
# =============================================================================

@dataclass
class MockExecutionTrace:
    """Mock execution trace for testing."""
    trace_id: str
    task_id: str
    status: MockTraceStatus
    steps: List[Dict[str, Any]] = field(default_factory=list)
    final_answer: str = ""
    resolution_passed: bool = False
    tokens_used: Dict[str, int] = field(default_factory=lambda: {"input": 0, "output": 0})
    execution_time: float = 0.0
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "task_id": self.task_id,
            "status": self.status.value,
            "steps": self.steps,
            "final_answer": self.final_answer,
            "resolution_passed": self.resolution_passed,
            "tokens_used": self.tokens_used,
            "execution_time": self.execution_time,
            "error_message": self.error_message,
            "metadata": self.metadata,
        }


@dataclass
class MockRewardComponents:
    """Mock reward components for testing."""
    resolution_reward: float = 0.0
    efficiency_reward: float = 0.0
    correctness_reward: float = 0.0
    penalty: float = 0.0
    total_reward: float = 0.0
    
    def to_dict(self) -> Dict[str, float]:
        return {
            "resolution_reward": self.resolution_reward,
            "efficiency_reward": self.efficiency_reward,
            "correctness_reward": self.correctness_reward,
            "penalty": self.penalty,
            "total_reward": self.total_reward,
        }


@dataclass
class MockTrainingMetrics:
    """Mock training metrics for testing."""
    step: int = 0
    loss: float = 0.0
    reward_mean: float = 0.0
    kl_divergence: float = 0.0
    learning_rate: float = 0.0
    epoch: int = 0
    stage: MockTrainingStage = MockTrainingStage.SFT
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "loss": self.loss,
            "reward_mean": self.reward_mean,
            "kl_divergence": self.kl_divergence,
            "learning_rate": self.learning_rate,
            "epoch": self.epoch,
            "stage": self.stage.value,
        }


@dataclass
class MockSWEBenchTask:
    """Mock SWE-bench task for testing."""
    task_id: str
    repo: str
    version: str
    problem_statement: str
    hints_text: str = ""
    test_patch: str = ""
    difficulty: str = "medium"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "repo": self.repo,
            "version": self.version,
            "problem_statement": self.problem_statement,
            "hints_text": self.hints_text,
            "test_patch": self.test_patch,
            "difficulty": self.difficulty,
        }


@dataclass
class MockEvaluationResult:
    """Mock evaluation result for testing."""
    task_id: str
    resolved: bool
    execution_time: float
    error: Optional[str] = None
    tokens_used: Dict[str, int] = field(default_factory=lambda: {"input": 0, "output": 0})
    cost: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "resolved": self.resolved,
            "execution_time": self.execution_time,
            "error": self.error,
            "tokens_used": self.tokens_used,
            "cost": self.cost,
        }


@dataclass
class MockCheckpointState:
    """Mock checkpoint state for testing."""
    checkpoint_id: str
    timestamp: str
    stage: MockOrchestratorStage
    training_step: int
    model_path: str
    metrics: Dict[str, float] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "timestamp": self.timestamp,
            "stage": self.stage.value,
            "training_step": self.training_step,
            "model_path": self.model_path,
            "metrics": self.metrics,
        }


@dataclass
class MockProgressInfo:
    """Mock progress info for testing."""
    stage: MockOrchestratorStage = MockOrchestratorStage.IDLE
    stage_progress: float = 0.0
    total_episodes: int = 0
    completed_episodes: int = 0
    total_steps: int = 0
    completed_steps: int = 0
    current_epoch: int = 0
    traces_collected: int = 0
    traces_processed: int = 0
    evaluations_completed: int = 0
    best_resolution_rate: float = 0.0
    elapsed_time: float = 0.0
    estimated_remaining: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        data = {
            "stage": self.stage.value,
            "stage_progress": self.stage_progress,
            "total_episodes": self.total_episodes,
            "completed_episodes": self.completed_episodes,
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "current_epoch": self.current_epoch,
            "traces_collected": self.traces_collected,
            "traces_processed": self.traces_processed,
            "evaluations_completed": self.evaluations_completed,
            "best_resolution_rate": self.best_resolution_rate,
            "elapsed_time": self.elapsed_time,
            "estimated_remaining": self.estimated_remaining,
        }
        return data


# =============================================================================
# Mock Component Classes
# =============================================================================

class MockTrainingOrchestrator:
    """
    Mock TrainingOrchestrator for integration testing.
    
    Simulates the behavior of the real TrainingOrchestrator without
    requiring actual model training or SWE-bench evaluation.
    """
    
    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        auto_progress: bool = True,
    ):
        self.config = config or {}
        self.auto_progress = auto_progress
        
        # State
        self._stage = MockOrchestratorStage.IDLE
        self._progress = MockProgressInfo()
        self._shutdown_requested = False
        self._shutdown_reason = "none"
        self._start_time: Optional[float] = None
        
        # Callbacks
        self._progress_callbacks: List[Callable] = []
        
        # Tracking
        self._collected_traces: List[MockExecutionTrace] = []
        self._checkpoints: List[MockCheckpointState] = []
        self._current_step = 0
        
        # Results storage for assertions
        self.calls_log: List[Dict[str, Any]] = []
        
    @property
    def stage(self) -> MockOrchestratorStage:
        return self._stage
    
    @property
    def progress(self) -> MockProgressInfo:
        return self._progress
    
    @property
    def is_shutdown_requested(self) -> bool:
        return self._shutdown_requested
    
    def request_shutdown(self, reason: str = "user_request") -> None:
        self._shutdown_requested = True
        self._shutdown_reason = reason
        self.calls_log.append({"action": "shutdown_requested", "reason": reason})
    
    def add_progress_callback(self, callback: Callable) -> None:
        self._progress_callbacks.append(callback)
    
    def remove_progress_callback(self, callback: Callable) -> None:
        if callback in self._progress_callbacks:
            self._progress_callbacks.remove(callback)
    
    def _set_stage(self, stage: MockOrchestratorStage) -> None:
        self._stage = stage
        self._progress.stage = stage
        self._notify_progress()
        self.calls_log.append({"action": "stage_change", "stage": stage.value})
    
    def _notify_progress(self) -> None:
        for callback in self._progress_callbacks:
            try:
                callback(self._progress)
            except Exception:
                pass
    
    def _update_progress(self, **kwargs) -> None:
        for key, value in kwargs.items():
            if hasattr(self._progress, key):
                setattr(self._progress, key, value)
        self._notify_progress()
    
    async def run_training_cycle(
        self,
        base_model: str = "test-model",
        swebench_subset: str = "lite",
        num_eval_tasks: int = 10,
        resume: bool = True,
    ) -> Dict[str, Any]:
        """
        Run a mock training cycle.
        
        Returns a result dictionary similar to TrainingCycleResult.
        """
        self._start_time = time.time()
        self.calls_log.append({
            "action": "run_training_cycle",
            "base_model": base_model,
            "swebench_subset": swebench_subset,
            "num_eval_tasks": num_eval_tasks,
            "resume": resume,
        })
        
        result = {
            "success": False,
            "model_path": "",
            "model_version": "",
            "resolution_rate": 0.0,
            "baseline_resolution_rate": 0.20,
            "improvement": 0.0,
            "traces_collected": 0,
            "training_steps": 0,
            "training_time": 0.0,
            "evaluations_run": 0,
            "error": None,
            "cancelled": False,
        }
        
        try:
            # Simulate stages
            stages = [
                (MockOrchestratorStage.INITIALIZING, 0.05),
                (MockOrchestratorStage.COLLECTING_DATA, 0.20),
                (MockOrchestratorStage.COMPUTING_REWARDS, 0.10),
                (MockOrchestratorStage.TRAINING, 0.40),
                (MockOrchestratorStage.EVALUATING, 0.20),
                (MockOrchestratorStage.REGISTERING_MODEL, 0.05),
            ]
            
            total_steps = self.config.get("max_training_steps", 100)
            
            for stage, duration_fraction in stages:
                if self._shutdown_requested:
                    result["cancelled"] = True
                    self._set_stage(MockOrchestratorStage.CANCELLED)
                    return result
                
                self._set_stage(stage)
                
                # Simulate work
                if self.auto_progress:
                    steps_for_stage = int(total_steps * duration_fraction)
                    for i in range(steps_for_stage):
                        if self._shutdown_requested:
                            result["cancelled"] = True
                            self._set_stage(MockOrchestratorStage.CANCELLED)
                            return result
                        
                        self._current_step += 1
                        self._update_progress(
                            completed_steps=self._current_step,
                            stage_progress=i / max(steps_for_stage, 1),
                        )
                        await asyncio.sleep(0.001)  # Small delay for realism
            
            # Complete
            self._set_stage(MockOrchestratorStage.COMPLETED)
            result["success"] = True
            result["traces_collected"] = self.config.get("data_collection_episodes", 100)
            result["training_steps"] = total_steps
            result["resolution_rate"] = 0.25  # Mock improvement
            result["improvement"] = 0.05
            result["model_path"] = str(Path(self.config.get("model_output_dir", "/tmp/models")) / "test_model")
            result["training_time"] = time.time() - self._start_time
            
        except Exception as e:
            self._set_stage(MockOrchestratorStage.FAILED)
            result["error"] = str(e)
        
        return result
    
    def save_checkpoint(self, checkpoint_id: Optional[str] = None) -> MockCheckpointState:
        """Save a mock checkpoint."""
        checkpoint = MockCheckpointState(
            checkpoint_id=checkpoint_id or str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            stage=self._stage,
            training_step=self._current_step,
            model_path=str(Path(self.config.get("checkpoint_dir", "/tmp/checkpoints")) / "model"),
            metrics={"loss": 0.1, "reward_mean": 0.5},
        )
        self._checkpoints.append(checkpoint)
        self.calls_log.append({"action": "save_checkpoint", "checkpoint_id": checkpoint.checkpoint_id})
        return checkpoint
    
    def load_checkpoint(self, checkpoint_id: str) -> Optional[MockCheckpointState]:
        """Load a mock checkpoint."""
        for checkpoint in self._checkpoints:
            if checkpoint.checkpoint_id == checkpoint_id:
                self._stage = checkpoint.stage
                self._current_step = checkpoint.training_step
                self.calls_log.append({"action": "load_checkpoint", "checkpoint_id": checkpoint_id})
                return checkpoint
        return None
    
    def list_checkpoints(self) -> List[MockCheckpointState]:
        """List all mock checkpoints."""
        return list(self._checkpoints)


class MockSWEBenchRunner:
    """
    Mock SWEBenchRunner for integration testing.
    
    Simulates running SWE-bench evaluations without actual model inference.
    """
    
    def __init__(
        self,
        model_path: str = "/tmp/test_model",
        resolution_rate: float = 0.25,
        avg_execution_time: float = 120.0,
    ):
        self.model_path = model_path
        self.resolution_rate = resolution_rate
        self.avg_execution_time = avg_execution_time
        
        # Tracking
        self.calls_log: List[Dict[str, Any]] = []
        self._evaluations_run: List[Dict[str, Any]] = []
    
    async def evaluate(
        self,
        subset: str = "lite",
        num_tasks: int = 10,
        timeout_per_task: int = 1800,
        task_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Run a mock evaluation.
        
        Returns results similar to real SWEBenchRunner.evaluate().
        """
        self.calls_log.append({
            "action": "evaluate",
            "subset": subset,
            "num_tasks": num_tasks,
            "timeout_per_task": timeout_per_task,
            "task_ids": task_ids,
        })
        
        # Generate mock results
        results = []
        resolved_count = 0
        
        tasks = task_ids or [f"task_{i}" for i in range(num_tasks)]
        
        for task_id in tasks:
            resolved = hash(task_id) % 100 < (self.resolution_rate * 100)
            if resolved:
                resolved_count += 1
            
            result = MockEvaluationResult(
                task_id=task_id,
                resolved=resolved,
                execution_time=self.avg_execution_time * (0.5 + hash(task_id) % 100 / 100),
                tokens_used={"input": 1000 + hash(task_id) % 500, "output": 500 + hash(task_id) % 300},
                cost=0.01 + (hash(task_id) % 100) / 10000,
            )
            results.append(result)
        
        evaluation_result = {
            "model_path": self.model_path,
            "subset": subset,
            "total_tasks": len(tasks),
            "resolved": resolved_count,
            "failed": len(tasks) - resolved_count,
            "timeouts": 0,
            "resolution_rate": resolved_count / len(tasks) if tasks else 0.0,
            "total_cost": sum(r.cost for r in results),
            "total_tokens": sum(r.tokens_used["input"] + r.tokens_used["output"] for r in results),
            "results": [r.to_dict() for r in results],
        }
        
        self._evaluations_run.append(evaluation_result)
        return evaluation_result
    
    async def compare_with_baseline(
        self,
        baseline_model: str,
        tasks: List[str],
    ) -> Dict[str, Any]:
        """Compare current model with baseline."""
        self.calls_log.append({
            "action": "compare_with_baseline",
            "baseline_model": baseline_model,
            "tasks": tasks,
        })
        
        # Mock comparison
        baseline_rate = 0.20  # 20% baseline
        improved_rate = self.resolution_rate
        
        return {
            "baseline_model": baseline_model,
            "current_model": self.model_path,
            "baseline_resolution_rate": baseline_rate,
            "current_resolution_rate": improved_rate,
            "improvement": improved_rate - baseline_rate,
            "tasks_improved": int(len(tasks) * 0.3),
            "tasks_regressed": int(len(tasks) * 0.1),
            "tasks_unchanged": int(len(tasks) * 0.6),
        }
    
    def generate_report(self, results: Dict[str, Any]) -> str:
        """Generate a mock markdown report."""
        self.calls_log.append({"action": "generate_report", "results": results})
        return f"""# SWE-bench Evaluation Report

**Model:** {self.model_path}
**Subset:** {results.get('subset', 'lite')}
**Total Tasks:** {results.get('total_tasks', 0)}
**Resolved:** {results.get('resolved', 0)}
**Resolution Rate:** {results.get('resolution_rate', 0):.1%}
**Total Cost:** ${results.get('total_cost', 0):.2f}
"""


class MockMetricsDashboard:
    """
    Mock MetricsDashboard for integration testing.
    
    Captures metrics for assertions without requiring a real dashboard.
    """
    
    def __init__(
        self,
        storage_backend: str = "memory",
        db_path: Optional[str] = None,
    ):
        self.storage_backend = storage_backend
        self.db_path = db_path
        
        # In-memory storage
        self._training_metrics: List[Dict[str, Any]] = []
        self._evaluation_results: List[Dict[str, Any]] = []
        self._alerts: List[Dict[str, Any]] = []
        self._callbacks_received: List[Dict[str, Any]] = []
        
        # Current state
        self._current_state: Dict[str, Any] = {
            "stage": "idle",
            "stage_progress": 0.0,
            "traces_collected": 0,
            "elapsed_time": 0.0,
            "resolution_rate": 0.0,
            "cost": 0.0,
        }
        
        # Tracking
        self.calls_log: List[Dict[str, Any]] = []
    
    def log_training_step(
        self,
        step: int,
        loss: float,
        reward_mean: float,
        kl_divergence: float = 0.0,
        **kwargs,
    ) -> None:
        """Log a training step metric."""
        metric = {
            "step": step,
            "loss": loss,
            "reward_mean": reward_mean,
            "kl_divergence": kl_divergence,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **kwargs,
        }
        self._training_metrics.append(metric)
        self.calls_log.append({"action": "log_training_step", **metric})
    
    def log_evaluation_result(
        self,
        model_version: str,
        task_id: str,
        resolved: bool,
        execution_time: float,
        **kwargs,
    ) -> None:
        """Log an evaluation result."""
        result = {
            "model_version": model_version,
            "task_id": task_id,
            "resolved": resolved,
            "execution_time": execution_time,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **kwargs,
        }
        self._evaluation_results.append(result)
        self.calls_log.append({"action": "log_evaluation_result", **result})
    
    def update_state(self, **kwargs) -> None:
        """Update current dashboard state."""
        self._current_state.update(kwargs)
        self._callbacks_received.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **kwargs,
        })
        self.calls_log.append({"action": "update_state", **kwargs})
    
    def create_callback(self) -> Callable:
        """Create a callback function that updates this dashboard."""
        def callback(progress_info: Union[MockProgressInfo, Any]) -> None:
            if hasattr(progress_info, 'to_dict'):
                data = progress_info.to_dict()
            elif hasattr(progress_info, '__dict__'):
                data = vars(progress_info)
            else:
                data = dict(progress_info) if hasattr(progress_info, '__iter__') else {}
            
            self.update_state(**data)
        
        return callback
    
    def get_summary(self, model_version: Optional[str] = None) -> Dict[str, Any]:
        """Get summary statistics."""
        evals = self._evaluation_results
        if model_version:
            evals = [e for e in evals if e.get("model_version") == model_version]
        
        resolved = sum(1 for e in evals if e.get("resolved"))
        total = len(evals)
        
        return {
            "total_evaluations": total,
            "resolved": resolved,
            "resolution_rate": resolved / total if total > 0 else 0.0,
            "avg_execution_time": sum(e.get("execution_time", 0) for e in evals) / total if total > 0 else 0.0,
            "training_steps_logged": len(self._training_metrics),
        }
    
    def add_alert(self, alert_type: str, message: str, **kwargs) -> None:
        """Add an alert."""
        alert = {
            "type": alert_type,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **kwargs,
        }
        self._alerts.append(alert)
        self.calls_log.append({"action": "add_alert", **alert})
    
    def export_metrics(self, format: str = "json") -> Union[str, Dict]:
        """Export metrics in specified format."""
        data = {
            "training_metrics": self._training_metrics,
            "evaluation_results": self._evaluation_results,
            "alerts": self._alerts,
            "state": self._current_state,
        }
        
        if format == "json":
            return data
        elif format == "csv":
            # Simplified CSV export
            lines = ["step,loss,reward_mean,kl_divergence"]
            for m in self._training_metrics:
                lines.append(f"{m.get('step', 0)},{m.get('loss', 0)},{m.get('reward_mean', 0)},{m.get('kl_divergence', 0)}")
            return "\n".join(lines)
        
        return data
    
    @property
    def current_state(self) -> Dict[str, Any]:
        return dict(self._current_state)
    
    @property
    def callbacks_received(self) -> List[Dict[str, Any]]:
        return list(self._callbacks_received)


# =============================================================================
# Test Data Fixtures
# =============================================================================

@pytest.fixture
def temp_checkpoint_dir(tmp_path: Path) -> Path:
    """Create an isolated checkpoint directory for testing."""
    checkpoint_dir = tmp_path / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    return checkpoint_dir


@pytest.fixture
def temp_model_dir(tmp_path: Path) -> Path:
    """Create an isolated model output directory for testing."""
    model_dir = tmp_path / "models"
    model_dir.mkdir(parents=True, exist_ok=True)
    return model_dir


@pytest.fixture
def temp_data_dir(tmp_path: Path) -> Path:
    """Create an isolated data directory for testing."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


@pytest.fixture
def training_config(
    temp_checkpoint_dir: Path,
    temp_model_dir: Path,
    temp_data_dir: Path,
) -> Dict[str, Any]:
    """
    Standard test configuration for training.
    
    Returns a configuration dictionary with sensible defaults for testing.
    """
    return {
        "data_collection_episodes": 10,
        "min_traces_for_training": 5,
        "max_training_steps": 100,
        "checkpoint_interval": 10,
        "eval_interval": 25,
        "budget_limit": 10.0,
        "checkpoint_dir": str(temp_checkpoint_dir),
        "model_output_dir": str(temp_model_dir),
        "data_dir": str(temp_data_dir),
        "keep_checkpoints": 3,
        "auto_resume": True,
        "shutdown_timeout": 5,
        "save_on_shutdown": True,
    }


@pytest.fixture
def synthetic_traces() -> List[MockExecutionTrace]:
    """
    Generate synthetic execution traces for testing.
    
    Returns a list of mock traces with various statuses.
    """
    traces = []
    
    # Success traces (60%)
    for i in range(60):
        traces.append(MockExecutionTrace(
            trace_id=f"trace_success_{i:03d}",
            task_id=f"django__django-{10000 + i}",
            status=MockTraceStatus.SUCCESS,
            steps=[
                {"action": "read_file", "file": f"file_{i}.py"},
                {"action": "write_file", "file": f"file_{i}_fixed.py"},
                {"action": "run_test", "passed": True},
            ],
            final_answer=f"Fixed issue in file_{i}.py",
            resolution_passed=True,
            tokens_used={"input": 500 + i * 10, "output": 200 + i * 5},
            execution_time=30.0 + i * 0.5,
        ))
    
    # Failure traces (25%)
    for i in range(25):
        traces.append(MockExecutionTrace(
            trace_id=f"trace_failure_{i:03d}",
            task_id=f"pytest__pytest-{20000 + i}",
            status=MockTraceStatus.FAILURE,
            steps=[
                {"action": "read_file", "file": f"file_{i}.py"},
                {"action": "write_file", "file": f"file_{i}_attempt.py"},
                {"action": "run_test", "passed": False},
            ],
            final_answer=f"Attempted fix for file_{i}.py",
            resolution_passed=False,
            tokens_used={"input": 600 + i * 15, "output": 300 + i * 10},
            execution_time=60.0 + i * 1.0,
            error_message="Tests failed",
        ))
    
    # Timeout traces (10%)
    for i in range(10):
        traces.append(MockExecutionTrace(
            trace_id=f"trace_timeout_{i:03d}",
            task_id=f"requests__requests-{30000 + i}",
            status=MockTraceStatus.TIMEOUT,
            steps=[
                {"action": "read_file", "file": f"file_{i}.py"},
            ],
            final_answer="",
            resolution_passed=False,
            tokens_used={"input": 1000, "output": 100},
            execution_time=1800.0,
            error_message="Execution timed out after 1800s",
        ))
    
    # Error traces (5%)
    for i in range(5):
        traces.append(MockExecutionTrace(
            trace_id=f"trace_error_{i:03d}",
            task_id=f"flask__flask-{40000 + i}",
            status=MockTraceStatus.ERROR,
            steps=[],
            final_answer="",
            resolution_passed=False,
            tokens_used={"input": 0, "output": 0},
            execution_time=0.0,
            error_message=f"Unexpected error: Error {i}",
        ))
    
    return traces


@pytest.fixture
def success_traces() -> List[MockExecutionTrace]:
    """Generate only success traces for positive testing."""
    return [
        MockExecutionTrace(
            trace_id=f"trace_success_{i:03d}",
            task_id=f"task_{i}",
            status=MockTraceStatus.SUCCESS,
            steps=[{"action": "fix", "success": True}],
            final_answer=f"Fixed task_{i}",
            resolution_passed=True,
            tokens_used={"input": 500, "output": 200},
            execution_time=30.0,
        )
        for i in range(100)
    ]


@pytest.fixture
def failure_traces() -> List[MockExecutionTrace]:
    """Generate only failure traces for negative testing."""
    return [
        MockExecutionTrace(
            trace_id=f"trace_failure_{i:03d}",
            task_id=f"task_{i}",
            status=MockTraceStatus.FAILURE,
            steps=[{"action": "fix", "success": False}],
            final_answer="",
            resolution_passed=False,
            tokens_used={"input": 600, "output": 300},
            execution_time=60.0,
            error_message="Resolution failed",
        )
        for i in range(100)
    ]


@pytest.fixture
def mock_swebench_tasks() -> List[MockSWEBenchTask]:
    """
    Generate mock SWE-bench tasks for testing.
    
    Returns a list of mock tasks simulating the SWE-bench Lite subset.
    """
    repos = ["django/django", "pytest-dev/pytest", "psf/requests", "pallets/flask", "python/cpython"]
    difficulties = ["easy", "medium", "hard"]
    
    tasks = []
    for i in range(10):
        repo = repos[i % len(repos)]
        difficulty = difficulties[i % len(difficulties)]
        
        tasks.append(MockSWEBenchTask(
            task_id=f"{repo.split('/')[1]}__{repo.split('/')[0]}-{10000 + i}",
            repo=repo,
            version=f"v{i}.0.0",
            problem_statement=f"Fix issue with feature {i}. This is a {difficulty} problem.",
            hints_text=f"Hint for issue {i}",
            test_patch=f"diff --git a/test_{i}.py b/test_{i}.py\n+def test_fix_{i}(): pass",
            difficulty=difficulty,
        ))
    
    return tasks


@pytest.fixture
def lite_subset_tasks() -> List[Dict[str, Any]]:
    """Generate a mock 10-task subset from SWE-bench Lite."""
    return [
        {
            "task_id": "django__django-12345",
            "repo": "django/django",
            "base_commit": "abc123",
            "problem_statement": "Fix URL routing issue",
        },
        {
            "task_id": "pytest-dev__pytest-67890",
            "repo": "pytest-dev/pytest",
            "base_commit": "def456",
            "problem_statement": "Fix assertion rewriting",
        },
        {
            "task_id": "psf__requests-11111",
            "repo": "psf/requests",
            "base_commit": "ghi789",
            "problem_statement": "Fix session handling",
        },
        {
            "task_id": "pallets__flask-22222",
            "repo": "pallets/flask",
            "base_commit": "jkl012",
            "problem_statement": "Fix blueprint registration",
        },
        {
            "task_id": "python__cpython-33333",
            "repo": "python/cpython",
            "base_commit": "mno345",
            "problem_statement": "Fix asyncio issue",
        },
        {
            "task_id": "django__django-44444",
            "repo": "django/django",
            "base_commit": "pqr678",
            "problem_statement": "Fix ORM query",
        },
        {
            "task_id": "pytest-dev__pytest-55555",
            "repo": "pytest-dev/pytest",
            "base_commit": "stu901",
            "problem_statement": "Fix fixture scoping",
        },
        {
            "task_id": "psf__requests-66666",
            "repo": "psf/requests",
            "base_commit": "vwx234",
            "problem_statement": "Fix retry logic",
        },
        {
            "task_id": "pallets__flask-77777",
            "repo": "pallets/flask",
            "base_commit": "yza567",
            "problem_statement": "Fix error handling",
        },
        {
            "task_id": "python__cpython-88888",
            "repo": "python/cpython",
            "base_commit": "bcd890",
            "problem_statement": "Fix memory leak",
        },
    ]


# =============================================================================
# Mock Component Fixtures
# =============================================================================

@pytest.fixture
def mock_orchestrator(training_config: Dict[str, Any]) -> MockTrainingOrchestrator:
    """
    Create a mock TrainingOrchestrator for testing.
    
    The mock simulates orchestrator behavior without actual model training.
    """
    return MockTrainingOrchestrator(config=training_config)


@pytest.fixture
def mock_orchestrator_no_auto(training_config: Dict[str, Any]) -> MockTrainingOrchestrator:
    """Create a mock TrainingOrchestrator without automatic progress."""
    return MockTrainingOrchestrator(config=training_config, auto_progress=False)


@pytest.fixture
def mock_swebench_runner() -> MockSWEBenchRunner:
    """
    Create a mock SWEBenchRunner for testing.
    
    The mock simulates evaluation without actual model inference.
    """
    return MockSWEBenchRunner(
        model_path="/tmp/test_model",
        resolution_rate=0.25,
        avg_execution_time=120.0,
    )


@pytest.fixture
def mock_dashboard() -> MockMetricsDashboard:
    """
    Create a mock MetricsDashboard for testing.
    
    The mock captures metrics for assertions without requiring a real dashboard.
    """
    return MockMetricsDashboard(storage_backend="memory")


@pytest.fixture
def mock_model() -> MagicMock:
    """
    Create a mock model for testing.
    
    Provides configurable behavior for model inference.
    """
    model = MagicMock()
    model.generate = AsyncMock(return_value="Generated code output")
    model.get_tokenizer = MagicMock(return_value=MagicMock())
    model.state_dict = MagicMock(return_value={"weight": MagicMock()})
    return model


# =============================================================================
# Integration Fixtures
# =============================================================================

@pytest.fixture
def integrated_pipeline(
    mock_orchestrator: MockTrainingOrchestrator,
    mock_swebench_runner: MockSWEBenchRunner,
    mock_dashboard: MockMetricsDashboard,
) -> Dict[str, Any]:
    """
    Create an integrated pipeline with all components connected.
    
    Returns a dictionary with connected mock components for end-to-end testing.
    """
    # Connect dashboard callback to orchestrator
    callback = mock_dashboard.create_callback()
    mock_orchestrator.add_progress_callback(callback)
    
    return {
        "orchestrator": mock_orchestrator,
        "runner": mock_swebench_runner,
        "dashboard": mock_dashboard,
        "callback": callback,
    }


@pytest.fixture
def event_collector() -> List[Dict[str, Any]]:
    """
    Create an event collector for tracking callback invocations.
    
    Returns a list that can be used to collect events from callbacks.
    """
    return []


@pytest.fixture
def callback_factory(event_collector: List[Dict[str, Any]]):
    """
    Factory for creating callbacks that collect events.
    
    Returns a function that creates callbacks which append to event_collector.
    """
    def create_callback(name: str) -> Callable:
        def callback(progress_info: Any) -> None:
            event = {
                "callback_name": name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            if hasattr(progress_info, 'to_dict'):
                event["data"] = progress_info.to_dict()
            elif hasattr(progress_info, '__dict__'):
                event["data"] = vars(progress_info)
            event_collector.append(event)
        return callback
    
    return create_callback


# =============================================================================
# Async Test Utilities
# =============================================================================

@pytest.fixture
def async_test_timeout() -> int:
    """Default timeout for async tests in seconds."""
    return 30


@pytest.fixture
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# =============================================================================
# Cleanup Fixtures
# =============================================================================

@pytest.fixture(autouse=True)
def cleanup_after_test():
    """Automatically cleanup after each test."""
    yield
    # Cleanup code runs after each test
    # Currently no global cleanup needed
    pass
