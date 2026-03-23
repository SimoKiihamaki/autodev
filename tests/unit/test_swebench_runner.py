"""
Unit tests for SWEBenchRunner

Tests the evaluation runner functionality including:
- Configuration and initialization
- Parallel task execution
- Checkpoint management
- Cost tracking
- Error recovery
- Report generation
"""

import asyncio
import json
import os
import tempfile
import shutil
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

# Add src to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from evaluation.swebench_runner import (
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
    ReportFormat,
    create_runner,
    run_evaluation,
)


class TestRunnerConfig:
    """Tests for RunnerConfig."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = RunnerConfig()
        
        assert config.max_concurrent == 4
        assert config.timeout_per_task == 1800
        assert config.max_retries == 3
        assert config.checkpoint_interval == 10
        assert config.auto_resume is True
        assert config.track_costs is True
    
    def test_config_path_expansion(self):
        """Test that paths are expanded."""
        config = RunnerConfig(
            workspace="~/test_workspace",
            checkpoint_dir="~/test_checkpoints",
        )
        
        assert "~" not in config.workspace
        assert "~" not in config.checkpoint_dir
    
    def test_config_serialization(self):
        """Test config to_dict and from_dict."""
        config = RunnerConfig(
            max_concurrent=8,
            timeout_per_task=900,
        )
        
        data = config.to_dict()
        restored = RunnerConfig.from_dict(data)
        
        assert restored.max_concurrent == 8
        assert restored.timeout_per_task == 900


class TestProgressInfo:
    """Tests for ProgressInfo."""
    
    def test_default_progress(self):
        """Test default progress values."""
        progress = ProgressInfo()
        
        assert progress.stage == RunnerStage.IDLE
        assert progress.total_tasks == 0
        assert progress.completed_tasks == 0
        assert progress.resolved_tasks == 0
    
    def test_progress_serialization(self):
        """Test progress to_dict and from_dict."""
        progress = ProgressInfo(
            stage=RunnerStage.EVALUATING,
            total_tasks=100,
            completed_tasks=50,
            resolved_tasks=25,
        )
        
        data = progress.to_dict()
        restored = ProgressInfo.from_dict(data)
        
        assert restored.stage == RunnerStage.EVALUATING
        assert restored.total_tasks == 100
        assert restored.completed_tasks == 50
        assert restored.resolved_tasks == 25


class TestTaskResult:
    """Tests for TaskResult."""
    
    def test_task_result_creation(self):
        """Test creating a task result."""
        result = TaskResult(
            task_id="test__task_001",
            status=TaskStatus.RESOLVED,
            execution_time_seconds=120.5,
            tokens_used={"input": 1000, "output": 500},
            cost=0.01,
        )
        
        assert result.task_id == "test__task_001"
        assert result.status == TaskStatus.RESOLVED
        assert result.execution_time_seconds == 120.5
        assert result.tokens_used["input"] == 1000
    
    def test_task_result_serialization(self):
        """Test task result to_dict and from_dict."""
        result = TaskResult(
            task_id="test__task_002",
            status=TaskStatus.FAILED,
            execution_time_seconds=60.0,
            error="Test error",
        )
        
        data = result.to_dict()
        restored = TaskResult.from_dict(data)
        
        assert restored.task_id == "test__task_002"
        assert restored.status == TaskStatus.FAILED
        assert restored.error == "Test error"


class TestEvaluationResults:
    """Tests for EvaluationResults."""
    
    def test_evaluation_results_creation(self):
        """Test creating evaluation results."""
        results = EvaluationResults(
            run_id="eval_test",
            model_path="/path/to/model",
            subset="lite",
            total_tasks=10,
            resolved=5,
            failed=3,
            errors=1,
            timeouts=1,
            skipped=0,
            resolution_rate=0.5,
            avg_execution_time=120.0,
            total_tokens={"input": 10000, "output": 5000},
            total_cost=1.50,
            task_results=[],
            patterns={},
            timestamp=datetime.now().isoformat(),
            duration_seconds=600.0,
        )
        
        assert results.run_id == "eval_test"
        assert results.resolution_rate == 0.5
        assert results.total_cost == 1.50
    
    def test_task_ids_property(self):
        """Test task_ids property."""
        results = EvaluationResults(
            run_id="test",
            model_path="/model",
            subset="lite",
            total_tasks=3,
            resolved=2,
            failed=1,
            errors=0,
            timeouts=0,
            skipped=0,
            resolution_rate=2/3,
            avg_execution_time=60.0,
            total_tokens={"input": 0, "output": 0},
            total_cost=0.0,
            task_results=[
                TaskResult(task_id="task_1", status=TaskStatus.RESOLVED, execution_time_seconds=60.0),
                TaskResult(task_id="task_2", status=TaskStatus.RESOLVED, execution_time_seconds=60.0),
                TaskResult(task_id="task_3", status=TaskStatus.FAILED, execution_time_seconds=60.0),
            ],
            patterns={},
            timestamp="",
            duration_seconds=0.0,
        )
        
        assert results.task_ids == ["task_1", "task_2", "task_3"]


class TestCheckpointState:
    """Tests for CheckpointState."""
    
    def test_checkpoint_creation(self):
        """Test creating a checkpoint state."""
        checkpoint = CheckpointState(
            checkpoint_id="ckpt_001",
            timestamp=datetime.now().isoformat(),
            stage=RunnerStage.EVALUATING,
            progress=ProgressInfo(completed_tasks=10),
            config=RunnerConfig(),
            completed_results=[],
            pending_tasks=["task_11", "task_12"],
        )
        
        assert checkpoint.checkpoint_id == "ckpt_001"
        assert checkpoint.stage == RunnerStage.EVALUATING
        assert len(checkpoint.pending_tasks) == 2
    
    def test_checkpoint_serialization(self):
        """Test checkpoint to_dict and from_dict."""
        checkpoint = CheckpointState(
            checkpoint_id="ckpt_002",
            timestamp="2026-03-23T10:00:00",
            stage=RunnerStage.COMPLETED,
            progress=ProgressInfo(completed_tasks=20),
            config=RunnerConfig(max_concurrent=8),
            completed_results=[
                TaskResult(task_id="task_1", status=TaskStatus.RESOLVED, execution_time_seconds=60.0)
            ],
            pending_tasks=[],
        )
        
        data = checkpoint.to_dict()
        restored = CheckpointState.from_dict(data)
        
        assert restored.checkpoint_id == "ckpt_002"
        assert restored.stage == RunnerStage.COMPLETED
        assert restored.progress.completed_tasks == 20
        assert restored.config.max_concurrent == 8
        assert len(restored.completed_results) == 1


class TestSWEBenchRunner:
    """Tests for SWEBenchRunner."""
    
    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace."""
        workspace = tempfile.mkdtemp()
        yield workspace
        shutil.rmtree(workspace, ignore_errors=True)
    
    @pytest.fixture
    def config(self, temp_workspace):
        """Create a test configuration."""
        return RunnerConfig(
            workspace=temp_workspace,
            checkpoint_dir=os.path.join(temp_workspace, "checkpoints"),
            report_output_dir=os.path.join(temp_workspace, "reports"),
            max_concurrent=2,
            max_retries=1,
        )
    
    @pytest.fixture
    def runner(self, config):
        """Create a test runner."""
        return SWEBenchRunner(
            model_path="/path/to/model",
            config=config,
        )
    
    def test_runner_initialization(self, runner, config):
        """Test runner initialization."""
        assert runner.model_path == "/path/to/model"
        assert runner.config == config
        assert runner.stage == RunnerStage.IDLE
    
    def test_runner_stage_property(self, runner):
        """Test stage property."""
        assert runner.stage == RunnerStage.IDLE
        
        runner._set_stage(RunnerStage.INITIALIZING)
        assert runner.stage == RunnerStage.INITIALIZING
    
    def test_runner_progress_property(self, runner):
        """Test progress property."""
        progress = runner.progress
        
        assert isinstance(progress, ProgressInfo)
        assert progress.stage == RunnerStage.IDLE
    
    def test_shutdown_request(self, runner):
        """Test shutdown request."""
        assert not runner.is_shutdown_requested
        
        runner.request_shutdown()
        
        assert runner.is_shutdown_requested
    
    def test_progress_callbacks(self, runner):
        """Test progress callbacks."""
        callback_results = []
        
        def callback(progress):
            callback_results.append(progress.stage)
        
        runner.add_progress_callback(callback)
        runner._set_stage(RunnerStage.EVALUATING)
        
        assert RunnerStage.EVALUATING in callback_results
        
        runner.remove_progress_callback(callback)
        runner._set_stage(RunnerStage.COMPLETED)
        
        # Should not have been called again
        assert len([s for s in callback_results if s == RunnerStage.COMPLETED]) == 0
    
    def test_calculate_cost(self, runner):
        """Test cost calculation."""
        tokens = {"input": 1000, "output": 500}
        cost = runner._calculate_cost(tokens)
        
        # Expected: (1000/1000 * 0.003) + (500/1000 * 0.015) = 0.003 + 0.0075 = 0.0105
        expected = (1.0 * 0.003) + (0.5 * 0.015)
        assert abs(cost - expected) < 0.0001
    
    def test_checkpoint_save_and_load(self, runner, config):
        """Test checkpoint save and load."""
        # Add some state
        runner._task_results = {
            "task_1": TaskResult(
                task_id="task_1",
                status=TaskStatus.RESOLVED,
                execution_time_seconds=60.0,
            )
        }
        runner._completed_task_ids = ["task_1"]
        runner._total_cost = 1.25
        
        # Save checkpoint
        checkpoint = runner._save_checkpoint("lite")
        
        assert checkpoint is not None
        assert len(checkpoint.completed_results) == 1
        
        # Create new runner and load checkpoint
        new_runner = SWEBenchRunner(
            model_path="/path/to/model",
            config=config,
        )
        
        loaded = new_runner._load_latest_checkpoint()
        
        assert loaded is not None
        assert len(loaded.completed_results) == 1
    
    def test_list_checkpoints(self, runner):
        """Test listing checkpoints."""
        # Save multiple checkpoints
        runner._save_checkpoint("lite")
        runner._save_checkpoint("lite")
        
        checkpoints = runner.list_checkpoints()
        
        assert len(checkpoints) == 2
    
    def test_delete_checkpoint(self, runner):
        """Test deleting a checkpoint."""
        checkpoint = runner._save_checkpoint("lite")
        
        assert runner.delete_checkpoint(checkpoint.checkpoint_id)
        assert not runner.delete_checkpoint("nonexistent")
    
    @pytest.mark.asyncio
    async def test_mock_evaluate_task(self, runner):
        """Test mock task evaluation."""
        result = await runner._mock_evaluate_task(
            task_id="test__task_001",
            timeout=60,
            started_at=datetime.now().isoformat(),
        )
        
        assert result.task_id == "test__task_001"
        assert result.status in [TaskStatus.RESOLVED, TaskStatus.FAILED]
        assert result.execution_time_seconds > 0
    
    @pytest.mark.asyncio
    async def test_evaluate_small_set(self, runner):
        """Test evaluating a small set of mock tasks."""
        results = await runner.evaluate(
            subset="lite",
            num_tasks=5,
            resume=False,
        )
        
        assert results.total_tasks == 5
        assert results.run_id.startswith("eval_")
        assert results.subset == "lite"
        assert results.duration_seconds > 0
        assert len(results.task_results) == 5
    
    @pytest.mark.asyncio
    async def test_evaluate_with_resume(self, runner):
        """Test evaluation with resume from checkpoint."""
        # First run
        results1 = await runner.evaluate(
            subset="lite",
            num_tasks=3,
            resume=False,
        )
        
        assert results1.total_tasks == 3
        
        # Save checkpoint
        runner._save_checkpoint("lite")
        
        # Create new runner with same config and resume
        new_runner = SWEBenchRunner(
            model_path=runner.model_path,
            config=runner.config,
        )
        
        # Should load checkpoint
        checkpoint = new_runner._load_latest_checkpoint()
        assert checkpoint is not None
    
    @pytest.mark.asyncio
    async def test_evaluate_single_task(self, runner):
        """Test evaluating a single task."""
        result = await runner.evaluate_single_task("test__task_001")
        
        assert result.task_id == "test__task_001"
        assert result.status in [TaskStatus.RESOLVED, TaskStatus.FAILED]
    
    def test_generate_markdown_report(self, runner):
        """Test generating a markdown report."""
        results = EvaluationResults(
            run_id="test_report",
            model_path="/path/to/model",
            subset="lite",
            total_tasks=10,
            resolved=7,
            failed=2,
            errors=1,
            timeouts=0,
            skipped=0,
            resolution_rate=0.7,
            avg_execution_time=120.0,
            total_tokens={"input": 10000, "output": 5000},
            total_cost=1.50,
            task_results=[
                TaskResult(task_id=f"task_{i}", status=TaskStatus.RESOLVED if i < 7 else TaskStatus.FAILED, execution_time_seconds=120.0)
                for i in range(10)
            ],
            patterns={},
            timestamp=datetime.now().isoformat(),
            duration_seconds=600.0,
        )
        
        report = runner.generate_report(results, format="markdown")
        
        assert report.format == ReportFormat.MARKDOWN
        assert "# SWE-bench Evaluation Report" in report.content
        assert "70.0%" in report.content  # Resolution rate
        assert report.generated_at is not None
    
    def test_generate_json_report(self, runner):
        """Test generating a JSON report."""
        results = EvaluationResults(
            run_id="test_json",
            model_path="/path/to/model",
            subset="lite",
            total_tasks=5,
            resolved=3,
            failed=2,
            errors=0,
            timeouts=0,
            skipped=0,
            resolution_rate=0.6,
            avg_execution_time=60.0,
            total_tokens={"input": 5000, "output": 2500},
            total_cost=0.75,
            task_results=[],
            patterns={},
            timestamp=datetime.now().isoformat(),
            duration_seconds=300.0,
        )
        
        report = runner.generate_report(results, format="json")
        
        assert report.format == ReportFormat.JSON
        
        # Verify it's valid JSON
        data = json.loads(report.content)
        assert data["results"]["run_id"] == "test_json"
        assert data["results"]["resolution_rate"] == 0.6
    
    def test_generate_html_report(self, runner):
        """Test generating an HTML report."""
        results = EvaluationResults(
            run_id="test_html",
            model_path="/path/to/model",
            subset="lite",
            total_tasks=5,
            resolved=4,
            failed=1,
            errors=0,
            timeouts=0,
            skipped=0,
            resolution_rate=0.8,
            avg_execution_time=45.0,
            total_tokens={"input": 3000, "output": 1500},
            total_cost=0.50,
            task_results=[],
            patterns={},
            timestamp=datetime.now().isoformat(),
            duration_seconds=225.0,
        )
        
        report = runner.generate_report(results, format="html")
        
        assert report.format == ReportFormat.HTML
        assert "<!DOCTYPE html>" in report.content
        assert "<table>" in report.content
    
    def test_report_save(self, runner, temp_workspace):
        """Test saving a report to file."""
        results = EvaluationResults(
            run_id="test_save",
            model_path="/path/to/model",
            subset="lite",
            total_tasks=2,
            resolved=1,
            failed=1,
            errors=0,
            timeouts=0,
            skipped=0,
            resolution_rate=0.5,
            avg_execution_time=30.0,
            total_tokens={"input": 1000, "output": 500},
            total_cost=0.25,
            task_results=[],
            patterns={},
            timestamp=datetime.now().isoformat(),
            duration_seconds=60.0,
        )
        
        report = runner.generate_report(results)
        save_path = os.path.join(temp_workspace, "test_report.md")
        
        report.save(save_path)
        
        assert os.path.exists(save_path)
        
        with open(save_path, "r") as f:
            content = f.read()
        
        assert "# SWE-bench Evaluation Report" in content
    
    def test_comparison_result(self):
        """Test comparison result."""
        comparison = ComparisonResult(
            model_path="/path/to/model",
            baseline_path="/path/to/baseline",
            model_resolution_rate=0.25,
            baseline_resolution_rate=0.20,
            improvement=0.05,
            improvement_percent=25.0,
            tasks_improved=["task_1", "task_2"],
            tasks_regressed=["task_3"],
            tasks_newly_resolved=["task_1", "task_2"],
            tasks_newly_failed=["task_3"],
            common_resolved=["task_4"],
            common_failed=["task_5", "task_6"],
        )
        
        data = comparison.to_dict()
        
        assert data["improvement"] == 0.05
        assert len(data["tasks_improved"]) == 2


class TestConvenienceFunctions:
    """Tests for convenience functions."""
    
    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace."""
        workspace = tempfile.mkdtemp()
        yield workspace
        shutil.rmtree(workspace, ignore_errors=True)
    
    def test_create_runner(self, temp_workspace):
        """Test create_runner function."""
        runner = create_runner(
            model_path="/path/to/model",
            workspace=temp_workspace,
            max_concurrent=8,
        )
        
        assert runner.model_path == "/path/to/model"
        assert runner.config.max_concurrent == 8
    
    @pytest.mark.asyncio
    async def test_run_evaluation(self, temp_workspace):
        """Test run_evaluation function."""
        results = await run_evaluation(
            model_path="/path/to/model",
            subset="lite",
            num_tasks=3,
            workspace=temp_workspace,
            max_retries=1,
        )
        
        assert results.total_tasks == 3
        assert results.subset == "lite"


class TestErrorRecovery:
    """Tests for error recovery and retry logic."""
    
    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace."""
        workspace = tempfile.mkdtemp()
        yield workspace
        shutil.rmtree(workspace, ignore_errors=True)
    
    @pytest.mark.asyncio
    async def test_retry_logic(self, temp_workspace):
        """Test retry logic with failures."""
        config = RunnerConfig(
            workspace=temp_workspace,
            checkpoint_dir=os.path.join(temp_workspace, "checkpoints"),
            report_output_dir=os.path.join(temp_workspace, "reports"),
            max_concurrent=1,
            max_retries=2,
            retry_backoff_base=0.1,  # Fast backoff for testing
        )
        
        runner = SWEBenchRunner(
            model_path="/path/to/model",
            config=config,
        )
        
        # Test that retry logic works
        result = await runner._evaluate_task_with_retry(
            task_id="test__task_001",
            subset="lite",
        )
        
        assert result.attempts <= config.max_retries
    
    @pytest.mark.asyncio
    async def test_shutdown_during_evaluation(self, temp_workspace):
        """Test graceful shutdown during evaluation."""
        config = RunnerConfig(
            workspace=temp_workspace,
            checkpoint_dir=os.path.join(temp_workspace, "checkpoints"),
            report_output_dir=os.path.join(temp_workspace, "reports"),
            max_concurrent=2,
        )
        
        runner = SWEBenchRunner(
            model_path="/path/to/model",
            config=config,
        )
        
        # Request shutdown immediately
        runner.request_shutdown()
        
        results = await runner.evaluate(
            subset="lite",
            num_tasks=5,
            resume=False,
        )
        
        # Should have cancelled results
        assert results.metadata.get("cancelled") is True
        assert runner.stage == RunnerStage.CANCELLED


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
