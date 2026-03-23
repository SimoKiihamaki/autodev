"""
Tests for SWE-bench Test Harness

Run with: pytest test_swe_bench_harness.py -v
"""

import asyncio
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import the harness components
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmark.swe_bench_harness import (
    SWEBenchHarness,
    SWETask,
    TaskResult,
    TaskStatus,
    EvaluationResults
)
from benchmark.verification import (
    PatchVerifier,
    MockVerifier,
    TestResult,
    VerificationResult
)
from benchmark.reporting import ResultsReporter, generate_comparison_report


# ============ Fixtures ============

@pytest.fixture
def sample_task() -> SWETask:
    """Create a sample SWE-bench task for testing."""
    return SWETask(
        instance_id="django__django-12345",
        problem_statement="Fix bug in Django ORM where queries fail under specific conditions",
        repo="django/django",
        base_commit="abc123def456",
        patch="diff --git a/django/db/models/query.py\n--- a/django/db/models/query.py\n+++ b/django/db/models/query.py\n",
        test_patch="",
        version="3.2",
        FAIL_TO_PASS=["test_query_failure", "test_orm_conditions"],
        PASS_TO_PASS=["test_basic_query", "test_model_save"],
        created_at="2024-01-01T00:00:00Z",
        hints_text="Check the QuerySet._clone method"
    )


@pytest.fixture
def sample_task_result() -> TaskResult:
    """Create a sample task result for testing."""
    return TaskResult(
        instance_id="django__django-12345",
        status=TaskStatus.RESOLVED,
        execution_time_seconds=120.5,
        tokens_used={"total_tokens": 5000, "input_tokens": 3000, "output_tokens": 2000},
        tools_called=[{"name": "read_file", "input": {"path": "test.py"}}],
        iterations=5,
        error=None,
        patch_generated="diff --git a/test.py",
        tests_passed=2,
        tests_failed=0
    )


@pytest.fixture
def sample_evaluation_results(sample_task_result) -> EvaluationResults:
    """Create sample evaluation results for testing."""
    return EvaluationResults(
        total_tasks=2,
        resolved=1,
        failed=1,
        errors=0,
        timeouts=0,
        resolution_rate=0.5,
        avg_execution_time=100.0,
        total_tokens={"total_tokens": 10000, "input_tokens": 6000, "output_tokens": 4000},
        total_cost_estimate=0.50,
        task_results=[sample_task_result],
        patterns={"avg_iterations_success": 5.0},
        timestamp=datetime.utcnow().isoformat()
    )


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


# ============ SWETask Tests ============

class TestSWETask:
    """Tests for SWETask dataclass."""
    
    def test_task_creation(self, sample_task):
        """Test task creation with all fields."""
        assert sample_task.instance_id == "django__django-12345"
        assert sample_task.repo == "django/django"
        assert len(sample_task.FAIL_TO_PASS) == 2
        assert len(sample_task.PASS_TO_PASS) == 2
    
    def test_task_defaults(self):
        """Test task creation with minimal fields."""
        task = SWETask(
            instance_id="test-1",
            problem_statement="Test issue",
            repo="test/repo",
            base_commit="abc123",
            patch="",
            test_patch="",
            version="1.0",
            FAIL_TO_PASS=[],
            PASS_TO_PASS=[]
        )
        assert task.hints_text == ""
        assert task.created_at == ""


# ============ TaskResult Tests ============

class TestTaskResult:
    """Tests for TaskResult dataclass."""
    
    def test_result_creation(self, sample_task_result):
        """Test result creation."""
        assert sample_task_result.status == TaskStatus.RESOLVED
        assert sample_task_result.execution_time_seconds == 120.5
        assert sample_task_result.iterations == 5
    
    def test_result_status_enum(self):
        """Test all status values."""
        statuses = [TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.RESOLVED,
                    TaskStatus.FAILED, TaskStatus.TIMEOUT, TaskStatus.ERROR]
        for status in statuses:
            result = TaskResult(
                instance_id="test",
                status=status,
                execution_time_seconds=0,
                tokens_used={},
                tools_called=[],
                iterations=0
            )
            assert result.status == status


# ============ EvaluationResults Tests ============

class TestEvaluationResults:
    """Tests for EvaluationResults dataclass."""
    
    def test_results_to_dict(self, sample_evaluation_results):
        """Test conversion to dictionary."""
        d = sample_evaluation_results.to_dict()
        
        assert d["total_tasks"] == 2
        assert d["resolved"] == 1
        assert d["resolution_rate"] == 0.5
        assert len(d["task_results"]) == 1
    
    def test_resolution_rate_calculation(self):
        """Test resolution rate calculation."""
        results = EvaluationResults(
            total_tasks=10,
            resolved=2,
            failed=5,
            errors=2,
            timeouts=1,
            resolution_rate=0.2,
            avg_execution_time=100.0,
            total_tokens={},
            total_cost_estimate=1.0,
            task_results=[],
            patterns={},
            timestamp="2024-01-01"
        )
        
        assert results.resolution_rate == 0.2
        assert results.resolved / results.total_tasks == 0.2


# ============ SWEBenchHarness Tests ============

class TestSWEBenchHarness:
    """Tests for SWEBenchHarness class."""
    
    def test_harness_initialization(self, temp_workspace):
        """Test harness initialization."""
        harness = SWEBenchHarness(
            workspace=str(temp_workspace),
            api_key="test_key"
        )
        
        assert harness.workspace == temp_workspace
        assert harness.timeout_seconds == 1800
        assert harness.max_iterations == 20
        assert harness.api_key == "test_key"
    
    def test_harness_custom_config(self, temp_workspace):
        """Test harness with custom configuration."""
        harness = SWEBenchHarness(
            workspace=str(temp_workspace),
            timeout_seconds=600,
            max_iterations=50,
            model="claude-3-opus-20240229"
        )
        
        assert harness.timeout_seconds == 600
        assert harness.max_iterations == 50
        assert harness.model == "claude-3-opus-20240229"
    
    def test_build_task_prompt(self, temp_workspace, sample_task):
        """Test task prompt building."""
        harness = SWEBenchHarness(workspace=str(temp_workspace))
        prompt = harness.build_task_prompt(sample_task)
        
        assert "django/django" in prompt
        assert sample_task.problem_statement in prompt
        assert sample_task.hints_text in prompt
        assert "GitHub Issue Resolution Task" in prompt
    
    @pytest.mark.skipif(
        not os.environ.get("ANTHROPIC_API_KEY"),
        reason="Requires ANTHROPIC_API_KEY"
    )
    @pytest.mark.asyncio
    async def test_run_single_task(self, temp_workspace, sample_task):
        """Test running a single task (requires API key)."""
        harness = SWEBenchHarness(
            workspace=str(temp_workspace),
            max_iterations=5,
            timeout_seconds=60
        )
        
        task_workspace = temp_workspace / sample_task.instance_id
        # This test would actually clone the repo and run the pipeline
        # For now, we'll skip if no API key
        pass
    
    def test_pattern_analysis(self, temp_workspace):
        """Test pattern analysis."""
        harness = SWEBenchHarness(workspace=str(temp_workspace))
        
        # Add some success patterns
        harness._success_patterns = [
            {"repo": "django/django", "iterations": 5, "tools_used": ["read_file", "write_file"]},
            {"repo": "flask-admin/flask-admin", "iterations": 3, "tools_used": ["read_file"]}
        ]
        
        # Add some failure patterns
        harness._failure_patterns = [
            {"repo": "django/django", "iterations": 20, "error": "Timeout"},
            {"repo": "pytest-dev/pytest", "iterations": 15, "error": "Max iterations"}
        ]
        
        patterns = harness.analyze_patterns()
        
        assert "success_rate_by_repo" in patterns
        assert "common_success_tools" in patterns
        assert "common_failure_reasons" in patterns
        assert patterns["avg_iterations_success"] == 4.0


# ============ Verification Tests ============

class TestPatchVerifier:
    """Tests for PatchVerifier class."""
    
    def test_extract_modified_files(self, temp_workspace):
        """Test extracting files from a patch."""
        verifier = PatchVerifier(temp_workspace)
        
        patch = """diff --git a/file1.py b/file1.py
--- a/file1.py
+++ b/file1.py
@@ -1,3 +1,4 @@
 test
diff --git a/file2.py b/file2.py
--- a/file2.py
+++ b/file2.py
"""
        files = verifier.extract_modified_files(patch)
        
        assert "file1.py" in files
        assert "file2.py" in files
    
    def test_compare_patches(self, temp_workspace):
        """Test patch comparison."""
        verifier = PatchVerifier(temp_workspace)
        
        generated = "diff --git a/file1.py\n--- a/file1.py\n"
        gold = "diff --git a/file1.py\n--- a/file1.py\n+++ b/file1.py\n"
        
        comparison = verifier.compare_patches(generated, gold)
        
        assert "generated_files" in comparison
        assert "gold_files" in comparison
        assert "file_overlap_ratio" in comparison


class TestMockVerifier:
    """Tests for MockVerifier class."""
    
    def test_mock_verification(self):
        """Test mock verifier returns expected structure."""
        verifier = MockVerifier(success_rate=1.0)
        
        result = verifier.verify_resolution(
            fail_to_pass=["test1", "test2"],
            pass_to_pass=["test3"]
        )
        
        assert isinstance(result, VerificationResult)
        assert result.resolved is True
        assert len(result.fail_to_pass_results) == 2
        assert len(result.pass_to_pass_results) == 1
    
    def test_mock_verification_failure(self):
        """Test mock verifier with low success rate."""
        verifier = MockVerifier(success_rate=0.0)
        
        result = verifier.verify_resolution(
            fail_to_pass=["test1"],
            pass_to_pass=[]
        )
        
        assert result.resolved is False


# ============ Reporting Tests ============

class TestResultsReporter:
    """Tests for ResultsReporter class."""
    
    def test_markdown_report_generation(self, sample_evaluation_results):
        """Test markdown report generation."""
        reporter = ResultsReporter(sample_evaluation_results.to_dict())
        report = reporter.generate_markdown_report()
        
        assert "# SWE-bench Evaluation Report" in report
        assert "Resolution Rate" in report
        assert "50.0%" in report  # 0.5 as percentage
        assert "Performance Analysis" in report
    
    def test_report_sections(self, sample_evaluation_results):
        """Test report contains all expected sections."""
        reporter = ResultsReporter(sample_evaluation_results.to_dict())
        report = reporter.generate_markdown_report()
        
        expected_sections = [
            "Executive Summary",
            "Resolution Analysis",
            "Performance Analysis",
            "Pattern Analysis",
            "Task Details",
            "Recommendations"
        ]
        
        for section in expected_sections:
            assert section in report, f"Missing section: {section}"


class TestComparisonReport:
    """Tests for comparison report generation."""
    
    def test_comparison_report(self):
        """Test generating comparison report."""
        results1 = {
            "resolution_rate": 0.20,
            "total_tasks": 100,
            "resolved": 20,
            "total_cost_estimate": 10.0
        }
        results2 = {
            "resolution_rate": 0.25,
            "total_tasks": 100,
            "resolved": 25,
            "total_cost_estimate": 12.0
        }
        
        report = generate_comparison_report(
            [results1, results2],
            ["Run 1", "Run 2"]
        )
        
        assert "Run 1" in report
        assert "Run 2" in report
        assert "20.0%" in report
        assert "25.0%" in report


# ============ Integration Tests ============

class TestIntegration:
    """Integration tests for the full harness."""
    
    @pytest.mark.asyncio
    async def test_mock_evaluation_run(self, temp_workspace):
        """Test running a mock evaluation without API calls."""
        harness = SWEBenchHarness(
            workspace=str(temp_workspace),
            max_iterations=5,
            timeout_seconds=10
        )
        
        # Create mock tasks
        tasks = [
            SWETask(
                instance_id="test__test-1",
                problem_statement="Test issue 1",
                repo="test/test",
                base_commit="abc",
                patch="",
                test_patch="",
                version="1.0",
                FAIL_TO_PASS=["test1"],
                PASS_TO_PASS=[]
            )
        ]
        
        # Verify harness can load tasks (will fail without datasets)
        # This is just to test the structure
        assert harness.workspace.exists()
        assert harness.results_dir.exists()


# ============ Run Tests ============

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
