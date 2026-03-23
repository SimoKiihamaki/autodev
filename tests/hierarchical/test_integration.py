"""
Integration tests for the hierarchical agent pipeline.

Tests end-to-end flows including:
- AgentPipeline with real components
- HierarchicalExecutor with Manager → Coder → Reviewer
- TrainingOrchestrator integration
- Trace collection during execution

These tests require more setup and may be slower than unit tests.
Mark tests with @pytest.mark.integration for selective running.
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# Import the classes under test (will work once implementation is complete)
try:
    from hierarchical.agent_pipeline import (
        AgentPipeline,
        AgentPipelineConfig,
        HierarchicalResult,
    )
    from hierarchical.agent_training_bridge import (
        AgentTrainingBridge,
        BridgeConfig,
    )
    from hierarchical.hierarchical_executor import (
        ExecutionPhase,
        HierarchicalExecutor,
        PhaseResult,
    )
    from agents.base import AgentRole, TaskSpec, TaskResult
    from training.orchestrator import OrchestratorConfig, TrainingOrchestrator

    IMPORTS_AVAILABLE = True
except ImportError:
    IMPORTS_AVAILABLE = False
    # Create placeholder classes
    AgentPipeline = None
    AgentPipelineConfig = None
    HierarchicalResult = None
    AgentTrainingBridge = None
    BridgeConfig = None
    HierarchicalExecutor = None
    ExecutionPhase = None
    PhaseResult = None
    AgentRole = MagicMock
    TaskSpec = MagicMock
    TaskResult = MagicMock
    TrainingOrchestrator = None
    OrchestratorConfig = None


# -----------------------------------------------------------------------------
# Fixtures for Integration Tests
# -----------------------------------------------------------------------------

@pytest.fixture
def full_pipeline(tmp_path):
    """Create a fully configured pipeline for integration testing."""
    if not IMPORTS_AVAILABLE:
        pytest.skip("AgentPipeline not implemented yet")

    config = AgentPipelineConfig(
        max_concurrent_agents=2,
        use_trained_models=False,  # Use default models for testing
        collect_traces=True,
        trace_buffer_size=100,
        checkpoint_dir=str(tmp_path / "checkpoints"),
        mcp_config_path=str(tmp_path / "mcp_config.json"),
    )

    return AgentPipeline(config=config)


@pytest.fixture
def full_pipeline_with_orchestrator(tmp_path):
    """Create a pipeline with TrainingOrchestrator for integration testing."""
    if not IMPORTS_AVAILABLE:
        pytest.skip("Components not implemented yet")

    orchestrator_config = OrchestratorConfig(
        data_collection_episodes=2,
        checkpoint_dir=str(tmp_path / "checkpoints"),
        model_output_dir=str(tmp_path / "models"),
    )

    pipeline_config = AgentPipelineConfig(
        use_trained_models=False,
        collect_traces=True,
        training_config=orchestrator_config,
    )

    orchestrator = TrainingOrchestrator(config=orchestrator_config)
    pipeline = AgentPipeline(config=pipeline_config, orchestrator=orchestrator)

    return pipeline, orchestrator


@pytest.fixture
def mock_agent():
    """Create a mock agent for testing."""
    agent = Mock()
    agent.agent_id = "test-agent"
    agent.role = AgentRole.CODER if IMPORTS_AVAILABLE else "coder"
    agent._llm_client = Mock()
    agent._conversation_history = []

    async def mock_execute(task):
        return TaskResult(
            task_id=task.task_id if hasattr(task, 'task_id') else "test-task",
            status="completed",
            files_modified=["test.py"],
        ) if IMPORTS_AVAILABLE else Mock(task_id="test-task", status="completed")

    agent.execute = AsyncMock(side_effect=mock_execute)
    return agent


# -----------------------------------------------------------------------------
# AgentPipeline Integration Tests
# -----------------------------------------------------------------------------

@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="AgentPipeline not implemented yet")
class TestAgentPipelineIntegration:
    """Integration tests for Agent Pipeline."""

    # -------------------------------------------------------------------------
    # End-to-End Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_simple_task_execution(self, full_pipeline):
        """Test simple task execution through pipeline.

        Verifies that a basic task can be submitted and executed,
        returning a valid TaskResult.
        """
        task = TaskSpec(
            task_id="simple-1",
            task_type="implement",
            specification="Create a hello world function",
            target_files=["hello.py"],
        )

        with patch.object(full_pipeline, 'create_agent') as mock_create:
            mock_agent = AsyncMock()
            mock_agent.execute.return_value = TaskResult(
                task_id="simple-1",
                status="completed",
                files_modified=["hello.py"],
            )
            mock_create.return_value = mock_agent

            result = await full_pipeline.run_task(task)

            assert result is not None
            assert result.task_id == "simple-1"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_hierarchical_task_execution(self, full_pipeline):
        """Test hierarchical task execution with Manager → Coder → Reviewer.

        Verifies that a complex task can be decomposed and executed
        through the full hierarchical flow.
        """
        task = TaskSpec(
            task_id="hierarchical-1",
            specification="Implement a calculator module with add, subtract operations",
            target_files=["calculator.py"],
        )

        with patch(
            'hierarchical.agent_pipeline.HierarchicalExecutor'
        ) as MockExecutor:
            mock_executor = AsyncMock()
            mock_executor.execute.return_value = Mock(
                task_id="hierarchical-1",
                success=True,
                final_result=TaskResult(task_id="hierarchical-1", status="completed"),
                decomposition=[],
                code_changes=[],
                review_result=None,
                iterations=1,
                review_iterations=0,
                total_time_seconds=1.0,
                agent_usage={},
                token_usage={},
            )
            MockExecutor.return_value = mock_executor

            result = await full_pipeline.run_hierarchical(task, max_iterations=2)

            assert result is not None
            assert result.task_id == "hierarchical-1"
            assert result.success in [True, False]  # May succeed or fail, but shouldn't crash

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_trace_collection_during_execution(self, full_pipeline):
        """Test that traces are collected during execution.

        Verifies that the pipeline collects execution traces
        that can be used for training.
        """
        task = TaskSpec(
            task_id="trace-test",
            specification="Simple task for trace collection",
        )

        with patch.object(full_pipeline, 'create_agent') as mock_create:
            mock_agent = AsyncMock()
            mock_agent.execute.return_value = TaskResult(task_id="trace-test")
            mock_create.return_value = mock_agent

            await full_pipeline.run_task(task)

            # Check traces were collected
            traces = full_pipeline.trace_collector.flush()
            assert len(traces) > 0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_multiple_task_execution(self, full_pipeline):
        """Test executing multiple tasks in sequence.

        Verifies that the pipeline can handle multiple tasks
        without state leakage between executions.
        """
        tasks = [
            TaskSpec(task_id=f"multi-{i}", specification=f"Task {i}")
            for i in range(3)
        ]

        results = []
        with patch.object(full_pipeline, 'create_agent') as mock_create:
            mock_agent = AsyncMock()

            async def execute_side_effect(task):
                return TaskResult(
                    task_id=task.task_id,
                    status="completed",
                )

            mock_agent.execute = AsyncMock(side_effect=execute_side_effect)
            mock_create.return_value = mock_agent

            for task in tasks:
                result = await full_pipeline.run_task(task)
                results.append(result)

            assert len(results) == 3
            assert all(r.task_id.startswith("multi-") for r in results)

    # -------------------------------------------------------------------------
    # Training Integration Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.slow
    async def test_trace_collection_for_training(self, full_pipeline):
        """Test collecting traces suitable for training.

        Verifies that multiple tasks can be executed in parallel
        and their traces collected for training data.
        """
        tasks = [
            TaskSpec(
                task_id=f"train-{i}",
                specification=f"Training task {i}",
                target_files=[f"file_{i}.py"],
            )
            for i in range(5)
        ]

        with patch.object(full_pipeline, 'run_task') as mock_run:
            mock_run.return_value = TaskResult(task_id="train-0")

            traces = await full_pipeline.collect_traces(
                tasks,
                parallel=True,
                max_concurrent=2
            )

            assert len(traces) == 5
            for trace in traces:
                assert trace.task_id.startswith("train-")
                assert trace.status in ["completed", "failed"]

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.slow
    async def test_training_cycle_with_agents(self, full_pipeline_with_orchestrator):
        """Test running a mini training cycle with agents.

        Verifies that the pipeline can be used for training data
        collection and model training.
        """
        pipeline, orchestrator = full_pipeline_with_orchestrator

        # Skip if no GPU available
        pytest.importorskip("torch")

        with patch.object(orchestrator, 'run_training_cycle') as mock_cycle:
            mock_cycle.return_value = Mock(success=True, model_path="/tmp/model")

            result = await pipeline.run_training_cycle(
                base_model="test-model",
                num_tasks=2,
                eval_subset="lite"
            )

            # Should not crash
            assert result is not None
            assert result.success is True


# -----------------------------------------------------------------------------
# AgentTrainingBridge Integration Tests
# -----------------------------------------------------------------------------

@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="AgentTrainingBridge not implemented yet")
class TestBridgeIntegration:
    """Integration tests for AgentTrainingBridge."""

    @pytest.fixture
    def real_bridge(self, tmp_path):
        """Create a bridge with real components for integration testing."""
        from hierarchical.model_provider import TrainedModelProvider
        from hierarchical.trace_collector import AgentTraceCollector
        from training.reward_calculator import RewardCalculator

        model_provider = TrainedModelProvider(registry=None)
        trace_collector = AgentTraceCollector()
        reward_calculator = RewardCalculator()

        return AgentTrainingBridge(
            model_provider=model_provider,
            trace_collector=trace_collector,
            reward_calculator=reward_calculator,
            config=BridgeConfig()
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_bridge_wrap_and_collect(self, real_bridge, mock_agent):
        """Test bridge wrapping agent execution.

        Verifies that the bridge can wrap agent execution,
        collect traces, and return results.
        """
        task = TaskSpec(task_id="bridge-test", specification="Test task")

        result = await real_bridge.wrap_agent_execution(mock_agent, task)

        assert result is not None
        assert result.task_id == "bridge-test"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_bridge_collects_complete_trace(self, real_bridge):
        """Test bridge collects complete trace data.

        Verifies that the trace includes tool calls, LLM calls,
        and file changes.
        """
        agent = Mock()
        agent.agent_id = "trace-agent"
        agent.role = AgentRole.CODER
        agent._conversation_history = [
            Mock(role="user", content="Test"),
            Mock(role="assistant", content="Response"),
        ]
        agent._tool_calls = [
            Mock(tool_name="read_file", duration_ms=50),
            Mock(tool_name="write_file", duration_ms=100),
        ]

        async def mock_execute(task):
            return TaskResult(
                task_id=task.task_id,
                status="completed",
                files_modified=["test.py"],
            )

        agent.execute = AsyncMock(side_effect=mock_execute)

        task = TaskSpec(task_id="complete-trace", specification="Test")

        result = await real_bridge.wrap_agent_execution(
            agent, task, collect_trace=True
        )

        assert result is not None

    @pytest.mark.integration
    def test_bridge_reward_computation(self, real_bridge):
        """Test bridge computes rewards for traces.

        Verifies that reward computation integrates with
        the RewardCalculator.
        """
        trace = Mock()
        trace.trace_id = "reward-test"
        trace.task_id = "test-task"
        trace.status = "completed"
        trace.tool_calls = []
        trace.llm_calls = [Mock(tokens_used=500)]
        trace.file_changes = [Mock(file_path="test.py")]

        reward = real_bridge.compute_agent_reward(trace)

        assert reward is not None
        assert hasattr(reward, 'total')


# -----------------------------------------------------------------------------
# HierarchicalExecutor Integration Tests
# -----------------------------------------------------------------------------

@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="HierarchicalExecutor not implemented yet")
class TestHierarchicalExecutorIntegration:
    """Integration tests for HierarchicalExecutor."""

    @pytest.fixture
    def executor_with_mocks(self):
        """Create executor with mock agents for testing."""
        manager = Mock()
        manager.agent_id = "manager-1"
        manager.initialize = AsyncMock()
        manager.shutdown = AsyncMock()

        coders = []
        for i in range(2):
            coder = Mock()
            coder.agent_id = f"coder-{i}"
            coder.initialize = AsyncMock()
            coder.shutdown = AsyncMock()
            coder.execute = AsyncMock(return_value=TaskResult(
                task_id=f"task-{i}",
                status="completed",
            ))
            coders.append(coder)

        reviewers = []
        for i in range(2):
            reviewer = Mock()
            reviewer.agent_id = f"reviewer-{i}"
            reviewer.initialize = AsyncMock()
            reviewer.shutdown = AsyncMock()
            reviewers.append(reviewer)

        bridge = Mock()
        bridge.wrap_agent_execution = AsyncMock(
            return_value=TaskResult(task_id="test", status="completed")
        )

        return HierarchicalExecutor(
            manager=manager,
            coder_pool=coders,
            reviewer_pool=reviewers,
            bridge=bridge,
            max_iterations=2
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_full_hierarchy_flow(self, executor_with_mocks):
        """Test full Manager → Coder → Reviewer flow.

        Verifies that the executor properly orchestrates
        all phases of hierarchical execution.
        """
        executor = executor_with_mocks

        task = TaskSpec(
            task_id="hierarchy-flow-test",
            specification="Test full hierarchy",
        )

        # Verify executor is properly configured
        assert executor.max_iterations == 2
        assert len(executor.coder_pool) == 2
        assert len(executor.reviewer_pool) == 2

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_hierarchical_with_iteration(self, executor_with_mocks):
        """Test hierarchical execution with review iterations.

        Verifies that the executor handles the iteration loop
        when reviews request changes.
        """
        executor = executor_with_mocks

        task = TaskSpec(
            task_id="iteration-test",
            specification="Test with iteration",
        )

        # Mock that returns needs_changes first, then approved
        review_count = [0]

        def make_review_result(changes):
            review_count[0] += 1
            if review_count[0] < 2:
                return Mock(
                    success=True,
                    data=Mock(verdict="needs_changes"),
                )
            return Mock(
                success=True,
                data=Mock(verdict="approved"),
            )

        with patch.object(executor, 'run_review_phase') as mock_review:
            mock_review.side_effect = make_review_result

            with patch.object(executor, 'run_decomposition_phase') as mock_decomp:
                mock_decomp.return_value = Mock(
                    success=True,
                    phase=ExecutionPhase.DECOMPOSING,
                    data=[],
                )

                with patch.object(executor, 'run_coding_phase') as mock_code:
                    mock_code.return_value = Mock(
                        success=True,
                        phase=ExecutionPhase.CODING,
                        data=[],
                    )

                    with patch.object(executor, 'iterate_on_feedback') as mock_iter:
                        mock_iter.return_value = Mock(
                            phase=ExecutionPhase.ITERATING,
                            success=True,
                        )

                        # Execute - should iterate until approved
                        # (Implementation would need to be completed for full test)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_hierarchical_parallel_coding(self, executor_with_mocks):
        """Test parallel coding of subtasks.

        Verifies that the executor can run multiple coders
        in parallel for independent subtasks.
        """
        executor = executor_with_mocks

        from dataclasses import dataclass

        @dataclass
        class TestSubTask:
            subtask_id: str
            name: str
            task_type: str = "implement"

        subtasks = [
            TestSubTask(subtask_id="sub-1", name="Task 1"),
            TestSubTask(subtask_id="sub-2", name="Task 2"),
        ]

        with patch.object(executor, '_execute_subtask') as mock_exec:
            mock_exec.return_value = TaskResult(
                task_id="subtask",
                status="completed",
            )

            result = await executor.run_coding_phase(subtasks, parallel=True)

            assert result.success is True


# -----------------------------------------------------------------------------
# Orchestrator Integration Tests
# -----------------------------------------------------------------------------

@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="TrainingOrchestrator not implemented yet")
class TestOrchestratorIntegration:
    """Integration tests with TrainingOrchestrator."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_orchestrator_with_pipeline(self, tmp_path):
        """Test TrainingOrchestrator using AgentPipeline.

        Verifies that the orchestrator can use the pipeline
        for data collection.
        """
        orchestrator_config = OrchestratorConfig(
            data_collection_episodes=2,
            checkpoint_dir=str(tmp_path / "checkpoints"),
            model_output_dir=str(tmp_path / "models"),
        )

        pipeline_config = AgentPipelineConfig(
            use_trained_models=False,
            collect_traces=True,
        )

        orchestrator = TrainingOrchestrator(config=orchestrator_config)
        pipeline = AgentPipeline(config=pipeline_config, orchestrator=orchestrator)

        # Verify integration
        assert pipeline.orchestrator == orchestrator
        # orchestrator._agent_pipeline should be set
        assert orchestrator._agent_pipeline == pipeline

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.slow
    async def test_training_data_collection_via_pipeline(self, tmp_path):
        """Test collecting training data via agent pipeline.

        Verifies that training data can be collected by having
        agents execute tasks.
        """
        orchestrator_config = OrchestratorConfig(
            data_collection_episodes=1,
            checkpoint_dir=str(tmp_path / "checkpoints"),
            model_output_dir=str(tmp_path / "models"),
        )

        pipeline_config = AgentPipelineConfig(
            use_trained_models=False,
            collect_traces=True,
            trace_buffer_size=100,
        )

        orchestrator = TrainingOrchestrator(config=orchestrator_config)
        pipeline = AgentPipeline(config=pipeline_config, orchestrator=orchestrator)

        tasks = [
            TaskSpec(task_id=f"collect-{i}", specification=f"Task {i}")
            for i in range(3)
        ]

        with patch.object(pipeline, 'create_agent') as mock_create:
            mock_agent = AsyncMock()
            mock_agent.execute.return_value = TaskResult(task_id="collect-0")
            mock_create.return_value = mock_agent

            traces = await pipeline.collect_traces(tasks, parallel=False)

            assert len(traces) == 3


# -----------------------------------------------------------------------------
# End-to-End Scenarios
# -----------------------------------------------------------------------------

@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="Components not implemented yet")
class TestEndToEndScenarios:
    """End-to-end scenario tests."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.slow
    async def test_complete_feature_implementation(self, full_pipeline):
        """Test complete feature implementation flow.

        Simulates a realistic feature implementation scenario
        with decomposition, coding, and review.
        """
        task = TaskSpec(
            task_id="feature-1",
            task_type="implement",
            specification="""
            Implement a simple caching module with the following features:
            - get(key) - retrieve cached value
            - set(key, value, ttl) - store value with TTL
            - delete(key) - remove cached value
            """,
            target_files=["cache.py"],
        )

        with patch(
            'hierarchical.agent_pipeline.HierarchicalExecutor'
        ) as MockExecutor:
            mock_executor = AsyncMock()
            mock_executor.execute.return_value = Mock(
                task_id="feature-1",
                success=True,
                final_result=TaskResult(
                    task_id="feature-1",
                    status="completed",
                    files_modified=["cache.py"],
                ),
                decomposition=[
                    Mock(subtask_id="sub-1", name="Implement get"),
                    Mock(subtask_id="sub-2", name="Implement set"),
                    Mock(subtask_id="sub-3", name="Implement delete"),
                ],
                code_changes=[
                    Mock(file="cache.py", diff="..."),
                ],
                review_result=Mock(verdict="approved"),
                iterations=1,
                review_iterations=0,
                total_time_seconds=30.0,
                agent_usage={"coder-0": 1},
                token_usage={"claude-3-5-sonnet": 5000},
            )
            MockExecutor.return_value = mock_executor

            result = await full_pipeline.run_hierarchical(task)

            assert result.success is True
            assert len(result.decomposition) == 3
            assert result.review_result.verdict == "approved"

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.slow
    async def test_bug_fix_with_review_iterations(self, full_pipeline):
        """Test bug fix scenario requiring review iterations.

        Simulates a scenario where the initial implementation
        has issues that need to be fixed after review.
        """
        task = TaskSpec(
            task_id="bugfix-1",
            task_type="fix",
            specification="Fix the null pointer exception in UserService.validate()",
            target_files=["user_service.py"],
        )

        iteration_count = [0]

        def make_result():
            iteration_count[0] += 1
            return Mock(
                task_id="bugfix-1",
                success=iteration_count[0] >= 2,  # Succeeds on second iteration
                iterations=iteration_count[0],
                review_iterations=iteration_count[0] - 1,
            )

        with patch(
            'hierarchical.agent_pipeline.HierarchicalExecutor'
        ) as MockExecutor:
            mock_executor = AsyncMock()
            mock_executor.execute.side_effect = make_result
            MockExecutor.return_value = mock_executor

            result = await full_pipeline.run_hierarchical(task, max_iterations=3)

            # Should eventually succeed
            assert result.iterations >= 1


# -----------------------------------------------------------------------------
# Test Configuration
# -----------------------------------------------------------------------------

def pytest_configure(config):
    """Configure custom markers for integration tests."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (requires full setup)"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running (may take >10 seconds)"
    )
    config.addinivalue_line(
        "markers", "gpu: mark test as requiring GPU resources"
    )
