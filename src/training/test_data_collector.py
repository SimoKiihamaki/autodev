"""
Tests for Training Data Collector

Run with: pytest src/training/test_data_collector.py -v
"""

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from training.data_collector import (
    ExecutionTrace,
    TraceStep,
    CodeChange,
    TraceStatus,
    DataCollectionConfig,
    TrainingDataCollector,
    create_collector,
)


class TestTraceStep:
    """Tests for TraceStep dataclass."""
    
    def test_create_trace_step(self):
        """Test creating a trace step."""
        step = TraceStep(
            step_number=1,
            timestamp="2026-03-23T12:00:00",
            prompt="Test prompt",
            response="Test response",
            model="test-model",
            tokens_used={"input": 100, "output": 50},
            tool_calls=[{"name": "read_file", "args": {"path": "test.py"}}],
            tool_results=[{"content": "file contents"}],
            latency_seconds=1.5
        )
        
        assert step.step_number == 1
        assert step.prompt == "Test prompt"
        assert len(step.tool_calls) == 1
    
    def test_trace_step_serialization(self):
        """Test serializing and deserializing a trace step."""
        step = TraceStep(
            step_number=1,
            timestamp="2026-03-23T12:00:00",
            prompt="Test",
            response="Response"
        )
        
        data = step.to_dict()
        assert data["step_number"] == 1
        
        restored = TraceStep.from_dict(data)
        assert restored.step_number == step.step_number
        assert restored.prompt == step.prompt


class TestCodeChange:
    """Tests for CodeChange dataclass."""
    
    def test_create_code_change(self):
        """Test creating a code change."""
        change = CodeChange(
            file_path="src/main.py",
            change_type="modify",
            original_content="old code",
            new_content="new code",
            diff="--- a/src/main.py\n+++ b/src/main.py\n@@ -1 +1 @@",
            language="python"
        )
        
        assert change.file_path == "src/main.py"
        assert change.change_type == "modify"
    
    def test_code_change_serialization(self):
        """Test serializing and deserializing a code change."""
        change = CodeChange(
            file_path="test.py",
            change_type="create",
            new_content="print('hello')"
        )
        
        data = change.to_dict()
        restored = CodeChange.from_dict(data)
        
        assert restored.file_path == change.file_path
        assert restored.new_content == change.new_content


class TestExecutionTrace:
    """Tests for ExecutionTrace dataclass."""
    
    def test_create_execution_trace(self):
        """Test creating an execution trace."""
        trace = ExecutionTrace(
            trace_id="",
            task_id="test-task-123",
            timestamp="",
            problem_statement="Fix the bug"
        )
        
        assert trace.task_id == "test-task-123"
        assert trace.trace_id.startswith("trace_")
        assert trace.status == TraceStatus.FAILED  # default
    
    def test_add_steps(self):
        """Test adding steps to a trace."""
        trace = ExecutionTrace(
            trace_id="",
            task_id="test-task",
            timestamp="",
            problem_statement="Test"
        )
        
        step = TraceStep(
            step_number=1,
            timestamp="2026-03-23T12:00:00",
            prompt="prompt",
            response="response"
        )
        
        trace.add_step(step)
        assert len(trace.steps) == 1
        assert trace.iterations == 1
    
    def test_add_code_changes(self):
        """Test adding code changes to a trace."""
        trace = ExecutionTrace(
            trace_id="",
            task_id="test-task",
            timestamp="",
            problem_statement="Test"
        )
        
        change = CodeChange(
            file_path="test.py",
            change_type="create",
            new_content="print('hello')"
        )
        
        trace.add_code_change(change)
        assert len(trace.code_changes) == 1
    
    def test_trace_serialization(self):
        """Test serializing and deserializing a trace."""
        trace = ExecutionTrace(
            trace_id="",
            task_id="test-task",
            timestamp="",
            problem_statement="Fix bug",
            status=TraceStatus.SUCCESS,
            tests_passed=["test_one", "test_two"],
            execution_time_seconds=10.5,
            reward=0.85
        )
        
        data = trace.to_dict()
        restored = ExecutionTrace.from_dict(data)
        
        assert restored.task_id == trace.task_id
        assert restored.status == TraceStatus.SUCCESS
        assert restored.tests_passed == trace.tests_passed
        assert restored.execution_time_seconds == 10.5
        assert restored.reward == 0.85
    
    def test_get_formatted_prompt(self):
        """Test getting formatted prompt for training."""
        trace = ExecutionTrace(
            trace_id="",
            task_id="django__django-12345",
            timestamp="",
            problem_statement="Fix the ORM bug",
            repo_context={"repo": "django/django", "version": "4.0"},
            prompt="Custom prompt"
        )
        
        # Should use explicit prompt if set
        assert trace.get_formatted_prompt() == "Custom prompt"
        
        # Should build from components otherwise
        trace.prompt = ""
        formatted = trace.get_formatted_prompt()
        assert "django__django-12345" in formatted
        assert "Fix the ORM bug" in formatted
    
    def test_get_formatted_completion(self):
        """Test getting formatted completion for training."""
        trace = ExecutionTrace(
            trace_id="",
            task_id="test",
            timestamp="",
            problem_statement="Test",
            completion="Custom completion"
        )
        
        # Should use explicit completion if set
        assert trace.get_formatted_completion() == "Custom completion"
        
        # Should build from code changes otherwise
        trace.completion = ""
        trace.add_code_change(CodeChange(
            file_path="main.py",
            change_type="create",
            new_content="print('hello')"
        ))
        
        formatted = trace.get_formatted_completion()
        assert "main.py" in formatted
        assert "print('hello')" in formatted


class TestDataCollectionConfig:
    """Tests for DataCollectionConfig."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = DataCollectionConfig()
        
        assert config.max_traces_per_task == 10
        assert config.include_failed_attempts == True
        assert config.storage_format == "jsonl"
        assert config.compress_output == True
    
    def test_path_expansion(self):
        """Test that output_dir path is expanded."""
        config = DataCollectionConfig(output_dir="~/test_path")
        
        assert "~" not in config.output_dir
        assert config.output_dir.endswith("test_path")


class TestTrainingDataCollector:
    """Tests for TrainingDataCollector."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def collector(self, temp_dir):
        """Create a collector with temp directory."""
        config = DataCollectionConfig(
            output_dir=temp_dir,
            max_traces_per_task=5,
            flush_interval=10
        )
        return TrainingDataCollector(config)
    
    def test_collector_initialization(self, collector, temp_dir):
        """Test collector initialization."""
        assert collector.output_path == Path(temp_dir)
        assert collector.traces_path.exists()
    
    def test_start_trace(self, collector):
        """Test starting a trace."""
        trace = collector.start_trace(
            task_id="test-task-123",
            problem_statement="Fix the bug",
            repo_context={"repo": "test/repo"},
            model="test-model"
        )
        
        assert trace.task_id == "test-task-123"
        assert trace.problem_statement == "Fix the bug"
        assert trace.model == "test-model"
        assert trace.trace_id in collector._current_traces
    
    def test_record_step(self, collector):
        """Test recording a step."""
        trace = collector.start_trace(
            task_id="test-task",
            problem_statement="Test"
        )
        
        collector.record_step(
            trace=trace,
            prompt="What files should I modify?",
            response="You should modify main.py",
            tool_calls=[{"name": "read_file"}],
            tokens_used={"input": 100, "output": 50},
            latency_seconds=1.0
        )
        
        assert len(trace.steps) == 1
        assert trace.steps[0].prompt == "What files should I modify?"
        assert trace.total_tokens["input"] == 100
    
    def test_record_code_change(self, collector):
        """Test recording a code change."""
        trace = collector.start_trace(
            task_id="test-task",
            problem_statement="Test"
        )
        
        collector.record_code_change(
            trace=trace,
            file_path="src/main.py",
            change_type="modify",
            new_content="print('hello')",
            diff="+++ new content"
        )
        
        assert len(trace.code_changes) == 1
        assert trace.code_changes[0].file_path == "src/main.py"
    
    def test_finalize_trace_success(self, collector):
        """Test finalizing a successful trace."""
        trace = collector.start_trace(
            task_id="test-task",
            problem_statement="Test"
        )
        
        collector.record_step(
            trace=trace,
            prompt="Test",
            response="Response"
        )
        
        result = collector.finalize_trace(
            trace=trace,
            status=TraceStatus.SUCCESS,
            tests_passed=["test_one"],
            tests_failed=[],
            execution_time_seconds=5.0
        )
        
        assert result == True
        assert trace.status == TraceStatus.SUCCESS
        assert len(collector._collected_traces) == 1
        assert trace.trace_id not in collector._current_traces
    
    def test_finalize_trace_filter_failed(self):
        """Test filtering of failed traces."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = DataCollectionConfig(
                output_dir=tmpdir,
                include_failed_attempts=False
            )
            collector = TrainingDataCollector(config)
            
            trace = collector.start_trace(
                task_id="test-task",
                problem_statement="Test"
            )
            
            result = collector.finalize_trace(
                trace=trace,
                status=TraceStatus.FAILED,
                error="Something went wrong"
            )
            
            assert result == False
            assert len(collector._collected_traces) == 0
    
    def test_max_traces_per_task(self):
        """Test max traces per task limit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = DataCollectionConfig(
                output_dir=tmpdir,
                max_traces_per_task=2
            )
            collector = TrainingDataCollector(config)
            
            # Add 3 traces for the same task
            for i in range(3):
                trace = collector.start_trace(
                    task_id="same-task",
                    problem_statement=f"Attempt {i}"
                )
                result = collector.finalize_trace(
                    trace=trace,
                    status=TraceStatus.SUCCESS
                )
                
                if i < 2:
                    assert result == True
                else:
                    assert result == False  # Third one should be rejected
    
    def test_flush_jsonl(self, collector):
        """Test flushing traces to JSONL."""
        # Create and finalize a trace
        trace = collector.start_trace(
            task_id="test-task",
            problem_statement="Test"
        )
        collector.finalize_trace(trace, status=TraceStatus.SUCCESS)
        
        # Flush
        output_file = collector.flush()
        
        assert output_file.suffix == ".gz"  # Compressed
        assert output_file.exists()
        
        # Verify content
        import gzip
        with gzip.open(output_file, "rt") as f:
            content = f.read()
            data = json.loads(content.strip())
            assert data["task_id"] == "test-task"
    
    def test_get_statistics(self, collector):
        """Test getting collection statistics."""
        # Add some traces
        for i in range(3):
            trace = collector.start_trace(
                task_id=f"task-{i}",
                problem_statement=f"Test {i}"
            )
            trace.reward = 0.5 + (i * 0.1)
            collector.finalize_trace(
                trace=trace,
                status=TraceStatus.SUCCESS if i < 2 else TraceStatus.FAILED,
                execution_time_seconds=5.0 + i
            )
        
        stats = collector.get_statistics()
        
        assert stats["total_traces"] == 3
        assert stats["unique_tasks"] == 3
        assert "success" in stats["status_counts"]
        assert "failed" in stats["status_counts"]
        assert stats["avg_reward"] > 0
    
    def test_get_collected_traces_filtering(self, collector):
        """Test filtering collected traces."""
        # Add traces with different statuses and rewards
        for i in range(3):
            trace = collector.start_trace(
                task_id=f"task-{i}",
                problem_statement=f"Test {i}"
            )
            trace.reward = i * 0.5  # 0, 0.5, 1.0
            collector.finalize_trace(
                trace=trace,
                status=TraceStatus.SUCCESS if i > 0 else TraceStatus.FAILED
            )
        
        # Filter by status
        success_traces = collector.get_collected_traces(status=TraceStatus.SUCCESS)
        assert len(success_traces) == 2
        
        # Filter by min reward
        high_reward = collector.get_collected_traces(min_reward=0.5)
        assert len(high_reward) == 2
    
    def test_load_traces(self, collector):
        """Test loading traces from disk."""
        # Create and flush some traces
        for i in range(2):
            trace = collector.start_trace(
                task_id=f"task-{i}",
                problem_statement=f"Test {i}"
            )
            collector.finalize_trace(trace, status=TraceStatus.SUCCESS)
        
        collector.flush()
        
        # Load traces
        loaded = collector.load_traces()
        
        assert len(loaded) >= 2
        task_ids = {t.task_id for t in loaded}
        assert "task-0" in task_ids
        assert "task-1" in task_ids
    
    def test_export_for_training(self, collector):
        """Test exporting traces for training."""
        # Create some traces with rewards
        for i in range(3):
            trace = collector.start_trace(
                task_id=f"task-{i}",
                problem_statement=f"Test {i}"
            )
            trace.reward = i * 0.5
            trace.completion = f"Solution {i}"
            collector.finalize_trace(
                trace=trace,
                status=TraceStatus.SUCCESS if i > 0 else TraceStatus.FAILED
            )
        
        # Export with filters
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            output_path = Path(f.name)
        
        try:
            export_path = collector.export_for_training(
                output_path=output_path,
                min_reward=0.25,
                include_unsuccessful=False
            )
            
            # Verify export
            with open(export_path) as f:
                lines = f.readlines()
                # Should have 2 traces (reward >= 0.25 and successful)
                assert len(lines) == 2
                
                for line in lines:
                    data = json.loads(line)
                    assert "prompt" in data
                    assert "completion" in data
                    assert "reward" in data
                    assert data["reward"] >= 0.25
                    assert data["status"] == "success"
        finally:
            if output_path.exists():
                output_path.unlink()


class TestCreateCollector:
    """Tests for the create_collector convenience function."""
    
    def test_create_collector_default(self):
        """Test creating collector with defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            collector = create_collector(output_dir=tmpdir)
            
            assert isinstance(collector, TrainingDataCollector)
            assert collector.config.output_dir == tmpdir
    
    def test_create_collector_custom(self):
        """Test creating collector with custom config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            collector = create_collector(
                output_dir=tmpdir,
                max_traces_per_task=20,
                include_failed_attempts=False
            )
            
            assert collector.config.max_traces_per_task == 20
            assert collector.config.include_failed_attempts == False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
