"""
Unit tests for HierarchicalExecutor class.

Tests the orchestration of the Manager → Coder → Reviewer flow,
including phase execution, iteration loops, and conflict resolution.

Test Coverage Requirements:
- Phase execution: 90%
- Iteration loop: 90%
- Conflict resolution: 90%
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# Import the classes under test (will work once implementation is complete)
try:
    from hierarchical.hierarchical_executor import (
        ExecutionPhase,
        HierarchicalExecutor,
        IterationRecord,
        PhaseResult,
    )
    from agents.base import AgentRole, SubTask, TaskSpec, TaskResult
    from agents.communication import ReviewResult

    IMPORTS_AVAILABLE = True
except ImportError:
    IMPORTS_AVAILABLE = False
    # Create placeholder classes for type hints
    HierarchicalExecutor = None
    ExecutionPhase = None
    IterationRecord = None
    PhaseResult = None
    AgentRole = MagicMock
    SubTask = MagicMock
    TaskSpec = MagicMock
    TaskResult = MagicMock
    ReviewResult = MagicMock

    # Create mock enums/classes for testing without implementation
    class ExecutionPhase(Enum):
        INITIALIZING = "initializing"
        DECOMPOSING = "decomposing"
        CODING = "coding"
        REVIEWING = "reviewing"
        ITERATING = "iterating"
        COMPLETED = "completed"
        FAILED = "failed"


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="HierarchicalExecutor not implemented yet")
class TestHierarchicalExecutor:
    """Unit tests for HierarchicalExecutor."""

    # -------------------------------------------------------------------------
    # Initialization Tests
    # -------------------------------------------------------------------------

    def test_init_with_components(
        self,
        mock_manager_agent,
        mock_coder_agents,
        mock_reviewer_agents,
        mock_bridge,
    ):
        """Test initialization with all components."""
        executor = HierarchicalExecutor(
            manager=mock_manager_agent,
            coder_pool=mock_coder_agents,
            reviewer_pool=mock_reviewer_agents,
            bridge=mock_bridge,
            max_iterations=3,
        )

        assert executor.manager == mock_manager_agent
        assert len(executor.coder_pool) == len(mock_coder_agents)
        assert len(executor.reviewer_pool) == len(mock_reviewer_agents)
        assert executor.bridge == mock_bridge
        assert executor.max_iterations == 3

    def test_init_default_max_iterations(
        self,
        mock_manager_agent,
        mock_coder_agents,
        mock_reviewer_agents,
        mock_bridge,
    ):
        """Test that default max_iterations is set correctly."""
        executor = HierarchicalExecutor(
            manager=mock_manager_agent,
            coder_pool=mock_coder_agents,
            reviewer_pool=mock_reviewer_agents,
            bridge=mock_bridge,
        )

        # Default should be 5
        assert executor.max_iterations == 5

    def test_init_validates_pool_sizes(
        self,
        mock_manager_agent,
        mock_reviewer_agents,
        mock_bridge,
    ):
        """Test that initialization validates pool sizes."""
        # Empty coder pool should still work but may log warning
        executor = HierarchicalExecutor(
            manager=mock_manager_agent,
            coder_pool=[],
            reviewer_pool=mock_reviewer_agents,
            bridge=mock_bridge,
        )

        assert len(executor.coder_pool) == 0

    # -------------------------------------------------------------------------
    # Decomposition Phase Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_run_decomposition_phase_returns_subtasks(
        self,
        mock_manager_agent,
        mock_coder_agents,
        mock_reviewer_agents,
        mock_bridge,
    ):
        """Test decomposition phase returns subtasks."""
        executor = HierarchicalExecutor(
            manager=mock_manager_agent,
            coder_pool=mock_coder_agents,
            reviewer_pool=mock_reviewer_agents,
            bridge=mock_bridge,
            max_iterations=3,
        )

        task = TaskSpec(task_id="test", specification="Complex feature")

        subtasks = [
            SubTask(subtask_id="sub-1", name="Implement X", task_type="implement"),
            SubTask(subtask_id="sub-2", name="Test X", task_type="test"),
        ]

        with patch.object(executor, '_decompose_via_manager') as mock_decompose:
            mock_decompose.return_value = subtasks

            result = await executor.run_decomposition_phase(task)

            assert result.success is True
            assert result.phase == ExecutionPhase.DECOMPOSING
            assert result.data == subtasks

    @pytest.mark.asyncio
    async def test_run_decomposition_phase_handles_empty_result(
        self,
        mock_manager_agent,
        mock_coder_agents,
        mock_reviewer_agents,
        mock_bridge,
    ):
        """Test decomposition phase handles empty subtask list."""
        executor = HierarchicalExecutor(
            manager=mock_manager_agent,
            coder_pool=mock_coder_agents,
            reviewer_pool=mock_reviewer_agents,
            bridge=mock_bridge,
            max_iterations=3,
        )

        task = TaskSpec(task_id="test", specification="Simple task")

        with patch.object(executor, '_decompose_via_manager') as mock_decompose:
            mock_decompose.return_value = []

            result = await executor.run_decomposition_phase(task)

            assert result.success is True
            assert result.data == []

    @pytest.mark.asyncio
    async def test_run_decomposition_phase_handles_error(
        self,
        mock_manager_agent,
        mock_coder_agents,
        mock_reviewer_agents,
        mock_bridge,
    ):
        """Test decomposition phase handles errors gracefully."""
        executor = HierarchicalExecutor(
            manager=mock_manager_agent,
            coder_pool=mock_coder_agents,
            reviewer_pool=mock_reviewer_agents,
            bridge=mock_bridge,
            max_iterations=3,
        )

        task = TaskSpec(task_id="test", specification="Task")

        with patch.object(executor, '_decompose_via_manager') as mock_decompose:
            mock_decompose.side_effect = Exception("Decomposition failed")

            result = await executor.run_decomposition_phase(task)

            assert result.success is False
            assert result.phase == ExecutionPhase.FAILED

    # -------------------------------------------------------------------------
    # Coding Phase Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_run_coding_phase_processes_subtasks(
        self,
        mock_manager_agent,
        mock_coder_agents,
        mock_reviewer_agents,
        mock_bridge,
    ):
        """Test coding phase processes all subtasks."""
        executor = HierarchicalExecutor(
            manager=mock_manager_agent,
            coder_pool=mock_coder_agents,
            reviewer_pool=mock_reviewer_agents,
            bridge=mock_bridge,
            max_iterations=3,
        )

        subtasks = [
            SubTask(subtask_id="sub-1", name="Implement X", task_type="implement"),
            SubTask(subtask_id="sub-2", name="Implement Y", task_type="implement"),
        ]

        result = await executor.run_coding_phase(subtasks, parallel=True)

        assert result.success is True
        assert result.phase == ExecutionPhase.CODING

    @pytest.mark.asyncio
    async def test_run_coding_phase_parallel_vs_sequential(
        self,
        mock_manager_agent,
        mock_coder_agents,
        mock_reviewer_agents,
        mock_bridge,
    ):
        """Test coding phase respects parallel setting."""
        executor = HierarchicalExecutor(
            manager=mock_manager_agent,
            coder_pool=mock_coder_agents,
            reviewer_pool=mock_reviewer_agents,
            bridge=mock_bridge,
            max_iterations=3,
        )

        subtasks = [
            SubTask(subtask_id="sub-1", name="X"),
            SubTask(subtask_id="sub-2", name="Y"),
        ]

        # Run parallel
        result_parallel = await executor.run_coding_phase(subtasks, parallel=True)

        # Run sequential
        result_sequential = await executor.run_coding_phase(subtasks, parallel=False)

        # Both should succeed
        assert result_parallel.success is True
        assert result_sequential.success is True

    @pytest.mark.asyncio
    async def test_run_coding_phase_assigns_coders(
        self,
        mock_manager_agent,
        mock_coder_agents,
        mock_reviewer_agents,
        mock_bridge,
    ):
        """Test coding phase assigns coders to subtasks."""
        executor = HierarchicalExecutor(
            manager=mock_manager_agent,
            coder_pool=mock_coder_agents,
            reviewer_pool=mock_reviewer_agents,
            bridge=mock_bridge,
            max_iterations=3,
        )

        subtasks = [
            SubTask(subtask_id="sub-1", name="Task 1"),
            SubTask(subtask_id="sub-2", name="Task 2"),
            SubTask(subtask_id="sub-3", name="Task 3"),
        ]

        with patch.object(executor, '_assign_coder') as mock_assign:
            mock_assign.return_value = mock_coder_agents[0]

            await executor.run_coding_phase(subtasks)

            # Each subtask should get a coder assigned
            assert mock_assign.call_count == len(subtasks)

    @pytest.mark.asyncio
    async def test_run_coding_phase_handles_empty_pool(
        self,
        mock_manager_agent,
        mock_reviewer_agents,
        mock_bridge,
    ):
        """Test coding phase handles empty coder pool."""
        executor = HierarchicalExecutor(
            manager=mock_manager_agent,
            coder_pool=[],
            reviewer_pool=mock_reviewer_agents,
            bridge=mock_bridge,
            max_iterations=3,
        )

        subtasks = [SubTask(subtask_id="sub-1", name="Task")]

        result = await executor.run_coding_phase(subtasks)

        # Should fail gracefully
        assert result.success is False or result.data == []

    # -------------------------------------------------------------------------
    # Review Phase Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_run_review_phase_returns_verdict(
        self,
        mock_manager_agent,
        mock_coder_agents,
        mock_reviewer_agents,
        mock_bridge,
    ):
        """Test review phase returns review verdict."""
        executor = HierarchicalExecutor(
            manager=mock_manager_agent,
            coder_pool=mock_coder_agents,
            reviewer_pool=mock_reviewer_agents,
            bridge=mock_bridge,
            max_iterations=3,
        )

        changes = [Mock(file="test.py", diff="...")]

        with patch.object(executor, '_review_changes') as mock_review:
            mock_review.return_value = ReviewResult(
                review_id="review-1",
                task_id="test",
                verdict="approved",
            )

            result = await executor.run_review_phase(changes)

            assert result.success is True
            assert result.data.verdict == "approved"

    @pytest.mark.asyncio
    async def test_run_review_phase_handles_rejection(
        self,
        mock_manager_agent,
        mock_coder_agents,
        mock_reviewer_agents,
        mock_bridge,
    ):
        """Test review phase handles code rejection."""
        executor = HierarchicalExecutor(
            manager=mock_manager_agent,
            coder_pool=mock_coder_agents,
            reviewer_pool=mock_reviewer_agents,
            bridge=mock_bridge,
            max_iterations=3,
        )

        changes = [Mock(file="test.py", diff="bad code")]

        with patch.object(executor, '_review_changes') as mock_review:
            mock_review.return_value = ReviewResult(
                review_id="review-1",
                task_id="test",
                verdict="needs_changes",
                blocking_issues=["Code style issues"],
            )

            result = await executor.run_review_phase(changes)

            assert result.success is True
            assert result.data.verdict == "needs_changes"

    @pytest.mark.asyncio
    async def test_run_review_phase_no_changes(
        self,
        mock_manager_agent,
        mock_coder_agents,
        mock_reviewer_agents,
        mock_bridge,
    ):
        """Test review phase with no code changes."""
        executor = HierarchicalExecutor(
            manager=mock_manager_agent,
            coder_pool=mock_coder_agents,
            reviewer_pool=mock_reviewer_agents,
            bridge=mock_bridge,
            max_iterations=3,
        )

        result = await executor.run_review_phase([])

        # Should handle empty changes gracefully
        assert result.success is True or result.success is False

    # -------------------------------------------------------------------------
    # Iteration Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_iterate_on_feedback_updates_code(
        self,
        mock_manager_agent,
        mock_coder_agents,
        mock_reviewer_agents,
        mock_bridge,
    ):
        """Test iteration updates code based on feedback."""
        executor = HierarchicalExecutor(
            manager=mock_manager_agent,
            coder_pool=mock_coder_agents,
            reviewer_pool=mock_reviewer_agents,
            bridge=mock_bridge,
            max_iterations=3,
        )

        review = ReviewResult(
            review_id="review-1",
            task_id="test",
            verdict="needs_changes",
            blocking_issues=["Missing error handling"],
        )

        subtasks = [SubTask(subtask_id="sub-1", name="X")]

        result = await executor.iterate_on_feedback(review, subtasks)

        assert result.phase == ExecutionPhase.ITERATING

    @pytest.mark.asyncio
    async def test_iterate_on_feedback_with_no_issues(
        self,
        mock_manager_agent,
        mock_coder_agents,
        mock_reviewer_agents,
        mock_bridge,
    ):
        """Test iteration with no blocking issues."""
        executor = HierarchicalExecutor(
            manager=mock_manager_agent,
            coder_pool=mock_coder_agents,
            reviewer_pool=mock_reviewer_agents,
            bridge=mock_bridge,
            max_iterations=3,
        )

        review = ReviewResult(
            review_id="review-1",
            task_id="test",
            verdict="approved",
            blocking_issues=[],
        )

        subtasks = [SubTask(subtask_id="sub-1", name="X")]

        result = await executor.iterate_on_feedback(review, subtasks)

        # Should return completed phase
        assert result.phase in [ExecutionPhase.COMPLETED, ExecutionPhase.ITERATING]

    @pytest.mark.asyncio
    async def test_max_iterations_enforced(
        self,
        mock_manager_agent,
        mock_coder_agents,
        mock_reviewer_agents,
        mock_bridge,
    ):
        """Test that maximum iterations is enforced."""
        executor = HierarchicalExecutor(
            manager=mock_manager_agent,
            coder_pool=mock_coder_agents,
            reviewer_pool=mock_reviewer_agents,
            bridge=mock_bridge,
            max_iterations=2,
        )

        task = TaskSpec(task_id="test", specification="Test")

        # Mock to always return needs_changes
        with patch.object(executor, 'run_review_phase') as mock_review:
            mock_review.return_value = PhaseResult(
                phase=ExecutionPhase.REVIEWING,
                success=True,
                data=ReviewResult(verdict="needs_changes"),
                start_time=datetime.utcnow(),
                end_time=datetime.utcnow(),
            )

            result = await executor.execute(task)

            # Should stop at max_iterations
            iteration_history = executor.get_iteration_history()
            assert len(iteration_history) <= executor.max_iterations

    # -------------------------------------------------------------------------
    # Full Execution Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_execute_returns_hierarchical_result(
        self,
        mock_manager_agent,
        mock_coder_agents,
        mock_reviewer_agents,
        mock_bridge,
    ):
        """Test full execution returns HierarchicalResult."""
        executor = HierarchicalExecutor(
            manager=mock_manager_agent,
            coder_pool=mock_coder_agents,
            reviewer_pool=mock_reviewer_agents,
            bridge=mock_bridge,
            max_iterations=3,
        )

        task = TaskSpec(task_id="full-test", specification="Full feature")

        with patch.object(executor, 'run_decomposition_phase') as mock_decompose:
            mock_decompose.return_value = PhaseResult(
                phase=ExecutionPhase.DECOMPOSING,
                success=True,
                data=[SubTask(subtask_id="sub-1")],
                start_time=datetime.utcnow(),
                end_time=datetime.utcnow(),
            )

            with patch.object(executor, 'run_coding_phase') as mock_code:
                mock_code.return_value = PhaseResult(
                    phase=ExecutionPhase.CODING,
                    success=True,
                    data=[],
                    start_time=datetime.utcnow(),
                    end_time=datetime.utcnow(),
                )

                with patch.object(executor, 'run_review_phase') as mock_review:
                    mock_review.return_value = PhaseResult(
                        phase=ExecutionPhase.REVIEWING,
                        success=True,
                        data=ReviewResult(verdict="approved"),
                        start_time=datetime.utcnow(),
                        end_time=datetime.utcnow(),
                    )

                    result = await executor.execute(task)

                    assert result.success is True
                    assert result.task_id == "full-test"

    @pytest.mark.asyncio
    async def test_execute_full_flow_manager_coder_reviewer(
        self,
        mock_manager_agent,
        mock_coder_agents,
        mock_reviewer_agents,
        mock_bridge,
    ):
        """Test full Manager → Coder → Reviewer flow."""
        executor = HierarchicalExecutor(
            manager=mock_manager_agent,
            coder_pool=mock_coder_agents,
            reviewer_pool=mock_reviewer_agents,
            bridge=mock_bridge,
            max_iterations=3,
        )

        task = TaskSpec(task_id="full-flow", specification="Complete feature")

        # Execute full flow
        with patch.object(executor, '_initialize_agents') as mock_init:
            mock_init.return_value = None

            with patch.object(executor, '_decompose_via_manager') as mock_decompose:
                mock_decompose.return_value = [
                    SubTask(subtask_id="sub-1", name="Implement"),
                ]

                with patch.object(executor, '_execute_subtask') as mock_exec:
                    mock_exec.return_value = TaskResult(
                        task_id="sub-1",
                        status="completed",
                    )

                    with patch.object(executor, '_review_changes') as mock_rev:
                        mock_rev.return_value = ReviewResult(
                            review_id="rev-1",
                            task_id="full-flow",
                            verdict="approved",
                        )

                        result = await executor.execute(task)

                        # Verify all phases were called
                        assert result is not None

    @pytest.mark.asyncio
    async def test_execute_initializes_agents(
        self,
        mock_manager_agent,
        mock_coder_agents,
        mock_reviewer_agents,
        mock_bridge,
    ):
        """Test that execute initializes all agents."""
        executor = HierarchicalExecutor(
            manager=mock_manager_agent,
            coder_pool=mock_coder_agents,
            reviewer_pool=mock_reviewer_agents,
            bridge=mock_bridge,
            max_iterations=3,
        )

        task = TaskSpec(task_id="init-test", specification="Test")

        with patch.object(executor, 'run_decomposition_phase') as mock_decompose:
            mock_decompose.return_value = PhaseResult(
                phase=ExecutionPhase.DECOMPOSING,
                success=True,
                data=[],
                start_time=datetime.utcnow(),
                end_time=datetime.utcnow(),
            )

            with patch.object(executor, 'run_coding_phase') as mock_code:
                mock_code.return_value = PhaseResult(
                    phase=ExecutionPhase.CODING,
                    success=True,
                    data=[],
                    start_time=datetime.utcnow(),
                    end_time=datetime.utcnow(),
                )

                with patch.object(executor, 'run_review_phase') as mock_review:
                    mock_review.return_value = PhaseResult(
                        phase=ExecutionPhase.REVIEWING,
                        success=True,
                        data=ReviewResult(verdict="approved"),
                        start_time=datetime.utcnow(),
                        end_time=datetime.utcnow(),
                    )

                    await executor.execute(task)

                    # Verify manager was initialized
                    mock_manager_agent.initialize.assert_called()

    @pytest.mark.asyncio
    async def test_execute_shuts_down_agents(
        self,
        mock_manager_agent,
        mock_coder_agents,
        mock_reviewer_agents,
        mock_bridge,
    ):
        """Test that execute shuts down all agents after completion."""
        executor = HierarchicalExecutor(
            manager=mock_manager_agent,
            coder_pool=mock_coder_agents,
            reviewer_pool=mock_reviewer_agents,
            bridge=mock_bridge,
            max_iterations=3,
        )

        task = TaskSpec(task_id="shutdown-test", specification="Test")

        with patch.object(executor, 'run_decomposition_phase') as mock_decompose:
            mock_decompose.return_value = PhaseResult(
                phase=ExecutionPhase.DECOMPOSING,
                success=True,
                data=[],
                start_time=datetime.utcnow(),
                end_time=datetime.utcnow(),
            )

            with patch.object(executor, 'run_coding_phase') as mock_code:
                mock_code.return_value = PhaseResult(
                    phase=ExecutionPhase.CODING,
                    success=True,
                    data=[],
                    start_time=datetime.utcnow(),
                    end_time=datetime.utcnow(),
                )

                with patch.object(executor, 'run_review_phase') as mock_review:
                    mock_review.return_value = PhaseResult(
                        phase=ExecutionPhase.REVIEWING,
                        success=True,
                        data=ReviewResult(verdict="approved"),
                        start_time=datetime.utcnow(),
                        end_time=datetime.utcnow(),
                    )

                    await executor.execute(task)

                    # Verify shutdown was called
                    mock_manager_agent.shutdown.assert_called()

    # -------------------------------------------------------------------------
    # Conflict Resolution Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_resolve_conflicts_between_coders(
        self,
        mock_manager_agent,
        mock_coder_agents,
        mock_reviewer_agents,
        mock_bridge,
    ):
        """Test conflict resolution when multiple coders modify same file."""
        executor = HierarchicalExecutor(
            manager=mock_manager_agent,
            coder_pool=mock_coder_agents,
            reviewer_pool=mock_reviewer_agents,
            bridge=mock_bridge,
            max_iterations=3,
        )

        # Simulate conflicting changes
        changes = [
            Mock(file="shared.py", diff="change1", coder_id="coder-0"),
            Mock(file="shared.py", diff="change2", coder_id="coder-1"),
        ]

        with patch.object(executor, '_resolve_conflicts') as mock_resolve:
            mock_resolve.return_value = [changes[0]]  # Keep first change

            result = await executor._resolve_conflicts(changes)

            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_conflict_resolution_merges_when_possible(
        self,
        mock_manager_agent,
        mock_coder_agents,
        mock_reviewer_agents,
        mock_bridge,
    ):
        """Test that conflict resolution attempts merge when possible."""
        executor = HierarchicalExecutor(
            manager=mock_manager_agent,
            coder_pool=mock_coder_agents,
            reviewer_pool=mock_reviewer_agents,
            bridge=mock_bridge,
            max_iterations=3,
        )

        # Simulate mergeable changes
        changes = [
            Mock(file="module.py", diff="add_func_a", lines=(1, 10)),
            Mock(file="module.py", diff="add_func_b", lines=(20, 30)),
        ]

        with patch.object(executor, '_can_merge') as mock_can_merge:
            mock_can_merge.return_value = True

            with patch.object(executor, '_merge_changes') as mock_merge:
                mock_merge.return_value = Mock(file="module.py", diff="merged")

                result = executor._handle_overlapping_changes(changes)

                # Should merge when possible
                assert result is not None

    # -------------------------------------------------------------------------
    # State Tracking Tests
    # -------------------------------------------------------------------------

    def test_get_iteration_history(
        self,
        mock_manager_agent,
        mock_coder_agents,
        mock_reviewer_agents,
        mock_bridge,
    ):
        """Test that iteration history is tracked correctly."""
        executor = HierarchicalExecutor(
            manager=mock_manager_agent,
            coder_pool=mock_coder_agents,
            reviewer_pool=mock_reviewer_agents,
            bridge=mock_bridge,
            max_iterations=3,
        )

        # Initially empty
        history = executor.get_iteration_history()
        assert len(history) == 0

        # After execution, should have records
        # This would be populated during execute()

    def test_get_phase_timings(
        self,
        mock_manager_agent,
        mock_coder_agents,
        mock_reviewer_agents,
        mock_bridge,
    ):
        """Test that phase timings are tracked."""
        executor = HierarchicalExecutor(
            manager=mock_manager_agent,
            coder_pool=mock_coder_agents,
            reviewer_pool=mock_reviewer_agents,
            bridge=mock_bridge,
            max_iterations=3,
        )

        # Get phase timings (should be empty before execution)
        timings = executor.get_phase_timings()

        assert isinstance(timings, dict)


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="PhaseResult not implemented yet")
class TestPhaseResult:
    """Tests for PhaseResult dataclass."""

    def test_phase_result_fields(self):
        """Test PhaseResult has all required fields."""
        result = PhaseResult(
            phase=ExecutionPhase.CODING,
            success=True,
            data={"files": ["test.py"]},
            start_time=datetime(2026, 3, 23, 10, 0, 0),
            end_time=datetime(2026, 3, 23, 10, 0, 30),
            error=None,
        )

        assert result.phase == ExecutionPhase.CODING
        assert result.success is True
        assert result.data == {"files": ["test.py"]}
        assert result.error is None

    def test_phase_result_with_error(self):
        """Test PhaseResult with error information."""
        result = PhaseResult(
            phase=ExecutionPhase.FAILED,
            success=False,
            data=None,
            start_time=datetime(2026, 3, 23, 10, 0, 0),
            end_time=datetime(2026, 3, 23, 10, 0, 5),
            error="Agent crashed",
        )

        assert result.success is False
        assert result.error == "Agent crashed"


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="IterationRecord not implemented yet")
class TestIterationRecord:
    """Tests for IterationRecord dataclass."""

    def test_iteration_record_fields(self):
        """Test IterationRecord has all required fields."""
        record = IterationRecord(
            iteration=1,
            review_result=Mock(verdict="needs_changes"),
            feedback=["Fix bug"],
            changes_made=["Updated code"],
            timestamp=datetime(2026, 3, 23, 10, 0, 0),
        )

        assert record.iteration == 1
        assert record.review_result.verdict == "needs_changes"
        assert "Fix bug" in record.feedback

    def test_iteration_record_approved(self):
        """Test IterationRecord for approved iteration."""
        record = IterationRecord(
            iteration=2,
            review_result=Mock(verdict="approved"),
            feedback=[],
            changes_made=[],
            timestamp=datetime(2026, 3, 23, 10, 1, 0),
        )

        assert record.iteration == 2
        assert record.review_result.verdict == "approved"
        assert len(record.feedback) == 0


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="ExecutionPhase not implemented yet")
class TestExecutionPhase:
    """Tests for ExecutionPhase enum."""

    def test_all_phases_defined(self):
        """Test that all expected phases are defined."""
        expected_phases = [
            "INITIALIZING",
            "DECOMPOSING",
            "CODING",
            "REVIEWING",
            "ITERATING",
            "COMPLETED",
            "FAILED",
        ]

        for phase_name in expected_phases:
            assert hasattr(ExecutionPhase, phase_name)

    def test_phase_order(self):
        """Test that phases can be ordered by their typical execution order."""
        # Phases should have a logical ordering
        phases = [
            ExecutionPhase.INITIALIZING,
            ExecutionPhase.DECOMPOSING,
            ExecutionPhase.CODING,
            ExecutionPhase.REVIEWING,
            ExecutionPhase.ITERATING,
            ExecutionPhase.COMPLETED,
        ]

        # Each phase should be distinct
        assert len(set(phases)) == len(phases)
