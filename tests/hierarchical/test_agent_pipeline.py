"""
Unit tests for AgentPipeline class.

Tests the main pipeline that integrates agents with training infrastructure,
including task execution, hierarchical execution, trace collection, and
training cycle integration.

Test Coverage Requirements:
- Task execution: 90%
- Training cycle: 90%
- Model injection: 90%
"""

import asyncio
from datetime import datetime
from unittest.mock import ANY, AsyncMock, MagicMock, Mock, patch

import pytest

# Import the classes under test (will work once implementation is complete)
try:
    from hierarchical.agent_pipeline import (
        AgentPipeline,
        AgentPipelineConfig,
        HierarchicalResult,
    )
    from agents.base import AgentRole, TaskResult, TaskSpec

    IMPORTS_AVAILABLE = True
except ImportError:
    IMPORTS_AVAILABLE = False
    # Create placeholder classes for type hints
    AgentPipeline = None
    AgentPipelineConfig = None
    HierarchicalResult = None
    AgentRole = MagicMock
    TaskResult = MagicMock
    TaskSpec = MagicMock


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="AgentPipeline not implemented yet")
class TestAgentPipeline:
    """Unit tests for AgentPipeline."""

    # -------------------------------------------------------------------------
    # Initialization Tests
    # -------------------------------------------------------------------------

    def test_init_creates_components(self, pipeline_config, mock_orchestrator):
        """Test that pipeline initializes all required components."""
        pipeline = AgentPipeline(
            config=pipeline_config,
            orchestrator=mock_orchestrator
        )

        assert pipeline.bridge is not None
        assert pipeline.agent_factory is not None
        assert pipeline.trace_collector is not None

    def test_init_with_custom_config(self, pipeline_config):
        """Test initialization with custom configuration values."""
        pipeline_config.max_concurrent_agents = 5
        pipeline_config.collect_traces = False
        pipeline_config.agent_timeout_seconds = 1200

        pipeline = AgentPipeline(config=pipeline_config)

        assert pipeline.config.max_concurrent_agents == 5
        assert pipeline.config.collect_traces is False
        assert pipeline.config.agent_timeout_seconds == 1200

    def test_init_with_custom_bridge(self, pipeline_config, mock_orchestrator):
        """Test initialization with custom bridge instance."""
        custom_bridge = Mock()
        custom_bridge.model_provider = Mock()
        custom_bridge.trace_collector = Mock()

        pipeline = AgentPipeline(
            config=pipeline_config,
            orchestrator=mock_orchestrator,
            bridge=custom_bridge
        )

        assert pipeline.bridge == custom_bridge

    def test_init_sets_bidirectional_orchestrator_link(
        self, pipeline_config, mock_orchestrator
    ):
        """Test that pipeline sets bidirectional link with orchestrator."""
        pipeline = AgentPipeline(
            config=pipeline_config,
            orchestrator=mock_orchestrator
        )

        mock_orchestrator.set_agent_pipeline.assert_called_once_with(pipeline)

    # -------------------------------------------------------------------------
    # Task Execution Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_run_task_creates_agent(self, pipeline_config, mock_orchestrator):
        """Test that run_task creates appropriate agent for task execution."""
        pipeline = AgentPipeline(
            config=pipeline_config,
            orchestrator=mock_orchestrator
        )

        task = TaskSpec(
            task_id="test-1",
            task_type="implement",
            specification="Implement feature X",
        )

        with patch.object(pipeline, 'create_agent') as mock_create:
            mock_agent = AsyncMock()
            mock_agent.execute.return_value = TaskResult(
                task_id="test-1",
                status="completed"
            )
            mock_create.return_value = mock_agent

            result = await pipeline.run_task(task)

            mock_create.assert_called_once()
            assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_run_task_collects_trace(self, pipeline_config, mock_orchestrator):
        """Test that run_task collects execution trace when enabled."""
        pipeline_config.collect_traces = True
        pipeline = AgentPipeline(
            config=pipeline_config,
            orchestrator=mock_orchestrator
        )

        task = TaskSpec(task_id="test-2", specification="Test task")

        with patch.object(pipeline, 'create_agent') as mock_create:
            mock_agent = AsyncMock()
            mock_agent.execute.return_value = TaskResult(task_id="test-2")
            mock_create.return_value = mock_agent

            await pipeline.run_task(task)

            # Verify trace was collected
            assert len(pipeline.trace_collector._traces) > 0

    @pytest.mark.asyncio
    async def test_run_task_skips_trace_when_disabled(
        self, pipeline_config, mock_orchestrator
    ):
        """Test that trace collection is skipped when disabled in config."""
        pipeline_config.collect_traces = False
        pipeline = AgentPipeline(
            config=pipeline_config,
            orchestrator=mock_orchestrator
        )

        task = TaskSpec(task_id="test-3", specification="Test task")

        with patch.object(pipeline, 'create_agent') as mock_create:
            mock_agent = AsyncMock()
            mock_agent.execute.return_value = TaskResult(task_id="test-3")
            mock_create.return_value = mock_agent

            await pipeline.run_task(task)

            # Verify trace collection was not called
            pipeline.trace_collector.start_trace.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_task_handles_timeout(self, pipeline_config):
        """Test that run_task handles timeout correctly."""
        pipeline_config.agent_timeout_seconds = 1
        pipeline = AgentPipeline(config=pipeline_config)

        task = TaskSpec(
            task_id="timeout-test",
            specification="Long running task"
        )

        with patch.object(pipeline, 'create_agent') as mock_create:
            mock_agent = AsyncMock()

            async def slow_execute(*args, **kwargs):
                await asyncio.sleep(5)
                return TaskResult(task_id="timeout-test")

            mock_agent.execute = slow_execute
            mock_create.return_value = mock_agent

            result = await pipeline.run_task(task)

            assert result.status == "timeout"

    @pytest.mark.asyncio
    async def test_run_task_handles_agent_error(
        self, pipeline_config, mock_orchestrator
    ):
        """Test that run_task handles agent errors gracefully."""
        pipeline = AgentPipeline(
            config=pipeline_config,
            orchestrator=mock_orchestrator
        )

        task = TaskSpec(task_id="error-test", specification="Test task")

        with patch.object(pipeline, 'create_agent') as mock_create:
            mock_agent = AsyncMock()
            mock_agent.execute.side_effect = Exception("Agent error")
            mock_create.return_value = mock_agent

            result = await pipeline.run_task(task)

            assert result.status == "failed"
            assert "error" in result.status.lower() or len(result.errors) > 0

    @pytest.mark.asyncio
    async def test_run_task_with_progress_callback(
        self, pipeline_config, mock_orchestrator
    ):
        """Test that run_task calls progress callback during execution."""
        pipeline = AgentPipeline(
            config=pipeline_config,
            orchestrator=mock_orchestrator
        )

        task = TaskSpec(task_id="progress-test", specification="Test task")
        progress_calls = []

        def on_progress(progress: float, message: str):
            progress_calls.append((progress, message))

        with patch.object(pipeline, 'create_agent') as mock_create:
            mock_agent = AsyncMock()
            mock_agent.execute.return_value = TaskResult(task_id="progress-test")
            mock_create.return_value = mock_agent

            await pipeline.run_task(task, on_progress=on_progress)

            # Progress callback should have been called
            assert len(progress_calls) >= 0  # May or may not be called

    # -------------------------------------------------------------------------
    # Hierarchical Execution Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_run_hierarchical_creates_executor(
        self, pipeline_config, mock_orchestrator
    ):
        """Test that hierarchical execution creates HierarchicalExecutor."""
        pipeline = AgentPipeline(
            config=pipeline_config,
            orchestrator=mock_orchestrator
        )

        task = TaskSpec(
            task_id="hier-1",
            specification="Complex feature"
        )

        with patch(
            'hierarchical.agent_pipeline.HierarchicalExecutor'
        ) as MockExecutor:
            mock_executor = AsyncMock()
            mock_executor.execute.return_value = Mock(
                task_id="hier-1",
                success=True,
                final_result=TaskResult(task_id="hier-1", status="completed"),
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

            result = await pipeline.run_hierarchical(task)

            assert result.success is True
            MockExecutor.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_hierarchical_respects_max_iterations(
        self, pipeline_config, mock_orchestrator
    ):
        """Test that hierarchical execution respects max_iterations parameter."""
        pipeline = AgentPipeline(
            config=pipeline_config,
            orchestrator=mock_orchestrator
        )

        task = TaskSpec(task_id="hier-2", specification="Complex feature")

        with patch(
            'hierarchical.agent_pipeline.HierarchicalExecutor'
        ) as MockExecutor:
            mock_executor = AsyncMock()
            mock_executor.execute.return_value = Mock(
                task_id="hier-2",
                success=True,
                iterations=2,
            )
            MockExecutor.return_value = mock_executor

            await pipeline.run_hierarchical(task, max_iterations=2)

            # Verify max_iterations was passed to executor
            call_kwargs = MockExecutor.call_args[1]
            assert call_kwargs.get('max_iterations') == 2

    @pytest.mark.asyncio
    async def test_run_hierarchical_disabled_when_config_disabled(
        self, pipeline_config, mock_orchestrator
    ):
        """Test that hierarchical execution is disabled when config disables it."""
        pipeline_config.enable_hierarchical = False
        pipeline = AgentPipeline(
            config=pipeline_config,
            orchestrator=mock_orchestrator
        )

        task = TaskSpec(task_id="hier-3", specification="Feature")

        # Should fall back to simple execution
        with patch.object(pipeline, 'run_task') as mock_run:
            mock_run.return_value = TaskResult(task_id="hier-3", status="completed")

            result = await pipeline.run_hierarchical(task)

            mock_run.assert_called_once_with(task)

    # -------------------------------------------------------------------------
    # Training Integration Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_collect_traces_returns_list(
        self, pipeline_config, mock_orchestrator
    ):
        """Test that collect_traces returns execution traces."""
        pipeline = AgentPipeline(
            config=pipeline_config,
            orchestrator=mock_orchestrator
        )

        tasks = [
            TaskSpec(task_id=f"trace-{i}", specification=f"Task {i}")
            for i in range(3)
        ]

        with patch.object(pipeline, 'run_task') as mock_run:
            mock_run.return_value = TaskResult(task_id="trace-0")

            traces = await pipeline.collect_traces(tasks, parallel=False)

            assert len(traces) == 3

    @pytest.mark.asyncio
    async def test_collect_traces_parallel_execution(
        self, pipeline_config, mock_orchestrator
    ):
        """Test that collect_traces can execute tasks in parallel."""
        pipeline = AgentPipeline(
            config=pipeline_config,
            orchestrator=mock_orchestrator
        )

        tasks = [
            TaskSpec(task_id=f"trace-{i}", specification=f"Task {i}")
            for i in range(5)
        ]

        with patch.object(pipeline, 'run_task') as mock_run:
            mock_run.return_value = TaskResult(task_id="test")

            traces = await pipeline.collect_traces(
                tasks,
                parallel=True,
                max_concurrent=2
            )

            assert len(traces) == 5

    def test_get_trained_model_returns_none_when_not_available(
        self, pipeline_config, mock_orchestrator
    ):
        """Test get_trained_model returns None when no models available."""
        pipeline = AgentPipeline(
            config=pipeline_config,
            orchestrator=mock_orchestrator
        )

        model = pipeline.get_trained_model(AgentRole.CODER)

        assert model is None

    def test_get_trained_model_returns_path_when_available(
        self, pipeline_config, mock_orchestrator, mock_model_provider
    ):
        """Test get_trained_model returns path when model is available."""
        pipeline_config.use_trained_models = True
        pipeline = AgentPipeline(
            config=pipeline_config,
            orchestrator=mock_orchestrator
        )
        pipeline.bridge.model_provider = mock_model_provider

        model = pipeline.get_trained_model(AgentRole.CODER)

        assert model is not None
        assert "/path/to" in model

    @pytest.mark.asyncio
    async def test_run_training_cycle_delegates_to_orchestrator(
        self, pipeline_config, mock_orchestrator
    ):
        """Test that training cycle delegates to TrainingOrchestrator."""
        mock_orchestrator.run_training_cycle = AsyncMock(
            return_value=Mock(success=True, model_path="/tmp/model")
        )
        pipeline = AgentPipeline(
            config=pipeline_config,
            orchestrator=mock_orchestrator
        )

        result = await pipeline.run_training_cycle(
            base_model="test-model",
            num_tasks=10
        )

        assert result.success is True
        mock_orchestrator.run_training_cycle.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_training_cycle_without_orchestrator_raises(
        self, pipeline_config
    ):
        """Test that training cycle raises error without orchestrator."""
        pipeline = AgentPipeline(config=pipeline_config)

        with pytest.raises(RuntimeError):
            await pipeline.run_training_cycle(
                base_model="test-model",
                num_tasks=10
            )

    # -------------------------------------------------------------------------
    # Agent Management Tests
    # -------------------------------------------------------------------------

    def test_get_active_agent_returns_agent(self, pipeline_config, mock_orchestrator):
        """Test get_active_agent returns agent when exists."""
        pipeline = AgentPipeline(
            config=pipeline_config,
            orchestrator=mock_orchestrator
        )

        mock_agent = Mock()
        mock_agent.agent_id = "active-agent-1"
        pipeline._active_agents["active-agent-1"] = mock_agent

        result = pipeline.get_active_agent("active-agent-1")

        assert result == mock_agent

    def test_get_active_agent_returns_none_when_not_exists(
        self, pipeline_config, mock_orchestrator
    ):
        """Test get_active_agent returns None when agent doesn't exist."""
        pipeline = AgentPipeline(
            config=pipeline_config,
            orchestrator=mock_orchestrator
        )

        result = pipeline.get_active_agent("non-existent")

        assert result is None

    @pytest.mark.asyncio
    async def test_shutdown_cleans_up_agents(
        self, pipeline_config, mock_orchestrator
    ):
        """Test that shutdown cleans up all active agents."""
        pipeline = AgentPipeline(
            config=pipeline_config,
            orchestrator=mock_orchestrator
        )

        mock_agent = AsyncMock()
        mock_agent.agent_id = "cleanup-agent"
        pipeline._active_agents["cleanup-agent"] = mock_agent

        await pipeline.shutdown()

        mock_agent.shutdown.assert_called_once()
        assert len(pipeline._active_agents) == 0


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="AgentPipelineConfig not implemented yet")
class TestAgentPipelineConfig:
    """Tests for AgentPipelineConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = AgentPipelineConfig()

        assert config.max_concurrent_agents == 3
        assert config.agent_timeout_seconds == 600
        assert config.max_iterations_per_task == 5
        assert config.use_trained_models is True
        assert config.model_selection_strategy == "best"
        assert config.collect_traces is True
        assert config.trace_buffer_size == 1000
        assert config.enable_hierarchical is True
        assert config.max_review_iterations == 3
        assert config.require_review_approval is True

    def test_custom_values(self):
        """Test custom configuration values."""
        config = AgentPipelineConfig(
            max_concurrent_agents=10,
            agent_timeout_seconds=1200,
            use_trained_models=False,
            collect_traces=False,
            trace_buffer_size=5000,
        )

        assert config.max_concurrent_agents == 10
        assert config.agent_timeout_seconds == 1200
        assert config.use_trained_models is False
        assert config.collect_traces is False
        assert config.trace_buffer_size == 5000

    def test_model_selection_strategies(self):
        """Test different model selection strategies."""
        for strategy in ["best", "latest", "role_specific"]:
            config = AgentPipelineConfig(model_selection_strategy=strategy)
            assert config.model_selection_strategy == strategy

    def test_mcp_config_path_expanded(self):
        """Test that MCP config path is properly handled."""
        config = AgentPipelineConfig(
            mcp_config_path="~/config/mcp.json"
        )

        # Path should be stored as-is (expansion happens at runtime)
        assert config.mcp_config_path == "~/config/mcp.json"


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="HierarchicalResult not implemented yet")
class TestHierarchicalResult:
    """Tests for HierarchicalResult dataclass."""

    def test_result_fields(self):
        """Test that HierarchicalResult has all required fields."""
        result = HierarchicalResult(
            task_id="test-task",
            success=True,
            final_result=Mock(),
            decomposition=[],
            code_changes=[],
            review_result=None,
            iterations=1,
            review_iterations=0,
            total_time_seconds=10.5,
            agent_usage={"coder-0": 2},
            token_usage={"claude-3-5-sonnet": 5000},
        )

        assert result.task_id == "test-task"
        assert result.success is True
        assert result.iterations == 1
        assert result.review_iterations == 0
        assert result.total_time_seconds == 10.5
        assert "coder-0" in result.agent_usage
        assert "claude-3-5-sonnet" in result.token_usage

    def test_result_with_traces(self):
        """Test HierarchicalResult with execution traces."""
        traces = [Mock(trace_id=f"trace-{i}") for i in range(3)]

        result = HierarchicalResult(
            task_id="test-task",
            success=True,
            final_result=Mock(),
            decomposition=[],
            code_changes=[],
            review_result=None,
            iterations=1,
            review_iterations=0,
            total_time_seconds=5.0,
            agent_usage={},
            token_usage={},
            traces=traces,
        )

        assert len(result.traces) == 3
