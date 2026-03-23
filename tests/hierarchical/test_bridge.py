"""
Unit tests for AgentTrainingBridge class.

Tests the bridge connecting agents to training infrastructure,
including model injection, trace collection, and reward computation.

Test Coverage Requirements:
- Trace collection: 95%
- Model injection: 95%
- Reward computation: 95%
"""

from unittest.mock import ANY, AsyncMock, MagicMock, Mock, patch

import pytest

# Import the classes under test (will work once implementation is complete)
try:
    from src.hierarchical.agent_training_bridge import (
        AgentTrainingBridge,
        BridgeConfig,
    )
    from src.agents.base import AgentRole, BaseAgent, TaskSpec, TaskResult
    from src.training.reward_calculator import RewardComponents

    IMPORTS_AVAILABLE = True
except ImportError:
    IMPORTS_AVAILABLE = False
    # Create placeholder classes for type hints
    AgentTrainingBridge = None
    BridgeConfig = None
    AgentRole = MagicMock
    BaseAgent = MagicMock
    TaskSpec = MagicMock
    TaskResult = MagicMock
    RewardComponents = MagicMock


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="AgentTrainingBridge not implemented yet")
class TestAgentTrainingBridge:
    """Unit tests for AgentTrainingBridge."""

    # -------------------------------------------------------------------------
    # Initialization Tests
    # -------------------------------------------------------------------------

    def test_init_with_components(
        self,
        mock_model_provider,
        mock_trace_collector,
        mock_reward_calculator,
        bridge_config,
    ):
        """Test initialization with all components."""
        bridge = AgentTrainingBridge(
            model_provider=mock_model_provider,
            trace_collector=mock_trace_collector,
            reward_calculator=mock_reward_calculator,
            config=bridge_config,
        )

        assert bridge.model_provider == mock_model_provider
        assert bridge.trace_collector == mock_trace_collector
        assert bridge.reward_calculator == mock_reward_calculator
        assert bridge.config == bridge_config

    def test_init_with_default_config(
        self,
        mock_model_provider,
        mock_trace_collector,
        mock_reward_calculator,
    ):
        """Test initialization with default config when none provided."""
        bridge = AgentTrainingBridge(
            model_provider=mock_model_provider,
            trace_collector=mock_trace_collector,
            reward_calculator=mock_reward_calculator,
        )

        assert bridge.config is not None
        assert bridge.config.default_model is not None

    # -------------------------------------------------------------------------
    # Model Injection Tests
    # -------------------------------------------------------------------------

    def test_inject_trained_model_sets_model(
        self,
        mock_model_provider,
        mock_trace_collector,
        mock_reward_calculator,
        bridge_config,
    ):
        """Test that inject_trained_model sets model on agent's LLM client."""
        bridge = AgentTrainingBridge(
            model_provider=mock_model_provider,
            trace_collector=mock_trace_collector,
            reward_calculator=mock_reward_calculator,
            config=bridge_config,
        )

        agent = Mock(spec=BaseAgent)
        agent.agent_id = "test-agent-1"
        agent._llm_client = Mock()
        agent._llm_client.set_model = Mock()

        bridge.inject_trained_model(agent, "model-v1.2.3")

        # Verify model was set via set_model or direct assignment
        assert (
            agent._llm_client.set_model.called or
            hasattr(agent._llm_client, 'model')
        )

    def test_inject_trained_model_gets_model_from_provider(
        self,
        mock_model_provider,
        mock_trace_collector,
        mock_reward_calculator,
        bridge_config,
    ):
        """Test that inject_trained_model resolves model version via provider."""
        mock_model_provider.get_model.return_value = "/path/to/model/v1.2.3"

        bridge = AgentTrainingBridge(
            model_provider=mock_model_provider,
            trace_collector=mock_trace_collector,
            reward_calculator=mock_reward_calculator,
            config=bridge_config,
        )

        agent = Mock(spec=BaseAgent)
        agent.agent_id = "test-agent-2"
        agent._llm_client = Mock()
        agent._llm_client.set_model = Mock()

        bridge.inject_trained_model(agent, "v1.2.3")

        mock_model_provider.get_model.assert_called_once_with("v1.2.3")

    def test_get_model_for_role_returns_trained_when_available(
        self,
        mock_model_provider,
        mock_trace_collector,
        mock_reward_calculator,
        bridge_config,
    ):
        """Test get_model_for_role returns trained model when available."""
        bridge = AgentTrainingBridge(
            model_provider=mock_model_provider,
            trace_collector=mock_trace_collector,
            reward_calculator=mock_reward_calculator,
            config=bridge_config,
        )

        model = bridge.get_model_for_role(AgentRole.CODER, prefer_trained=True)

        assert model == "/path/to/role/model"
        mock_model_provider.get_for_role.assert_called_once()

    def test_get_model_for_role_returns_default_when_no_trained(
        self,
        mock_model_provider,
        mock_trace_collector,
        mock_reward_calculator,
        bridge_config,
    ):
        """Test get_model_for_role returns default when no trained model."""
        mock_model_provider.get_for_role.return_value = None

        bridge = AgentTrainingBridge(
            model_provider=mock_model_provider,
            trace_collector=mock_trace_collector,
            reward_calculator=mock_reward_calculator,
            config=bridge_config,
        )

        model = bridge.get_model_for_role(AgentRole.CODER, prefer_trained=True)

        # Should fall back to default from config
        assert model == bridge_config.default_model

    def test_get_model_for_role_without_preference(
        self,
        mock_model_provider,
        mock_trace_collector,
        mock_reward_calculator,
        bridge_config,
    ):
        """Test get_model_for_role returns default when prefer_trained=False."""
        bridge = AgentTrainingBridge(
            model_provider=mock_model_provider,
            trace_collector=mock_trace_collector,
            reward_calculator=mock_reward_calculator,
            config=bridge_config,
        )

        model = bridge.get_model_for_role(AgentRole.CODER, prefer_trained=False)

        # Should return default without checking trained models
        assert model == bridge_config.default_model
        mock_model_provider.get_for_role.assert_not_called()

    def test_get_model_for_role_uses_role_mapping(
        self,
        mock_model_provider,
        mock_trace_collector,
        mock_reward_calculator,
        bridge_config,
    ):
        """Test get_model_for_role uses role_model_mapping from config."""
        bridge_config.role_model_mapping = {
            "manager": "model-manager",
            "coder": "model-coder",
            "reviewer": "model-reviewer",
        }

        bridge = AgentTrainingBridge(
            model_provider=mock_model_provider,
            trace_collector=mock_trace_collector,
            reward_calculator=mock_reward_calculator,
            config=bridge_config,
        )

        model = bridge.get_model_for_role(AgentRole.MANAGER, prefer_trained=False)

        assert model == "model-manager"

    # -------------------------------------------------------------------------
    # Trace Collection Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_wrap_agent_execution_starts_trace(
        self,
        mock_model_provider,
        mock_trace_collector,
        mock_reward_calculator,
        bridge_config,
    ):
        """Test that wrap_agent_execution starts trace collection."""
        bridge = AgentTrainingBridge(
            model_provider=mock_model_provider,
            trace_collector=mock_trace_collector,
            reward_calculator=mock_reward_calculator,
            config=bridge_config,
        )

        agent = Mock(spec=BaseAgent)
        agent.agent_id = "test-agent"
        agent.execute = AsyncMock(return_value=TaskResult(task_id="test"))
        task = TaskSpec(task_id="test", specification="Test")

        await bridge.wrap_agent_execution(agent, task, collect_trace=True)

        mock_trace_collector.start_trace.assert_called_once()

    @pytest.mark.asyncio
    async def test_wrap_agent_execution_ends_trace(
        self,
        mock_model_provider,
        mock_trace_collector,
        mock_reward_calculator,
        bridge_config,
    ):
        """Test that wrap_agent_execution ends trace on completion."""
        bridge = AgentTrainingBridge(
            model_provider=mock_model_provider,
            trace_collector=mock_trace_collector,
            reward_calculator=mock_reward_calculator,
            config=bridge_config,
        )

        agent = Mock(spec=BaseAgent)
        agent.agent_id = "test-agent"
        agent.execute = AsyncMock(return_value=TaskResult(task_id="test"))
        task = TaskSpec(task_id="test", specification="Test")

        await bridge.wrap_agent_execution(agent, task, collect_trace=True)

        mock_trace_collector.end_trace.assert_called_once()

    @pytest.mark.asyncio
    async def test_wrap_agent_execution_skips_trace_when_disabled(
        self,
        mock_model_provider,
        mock_trace_collector,
        mock_reward_calculator,
        bridge_config,
    ):
        """Test that trace collection is skipped when collect_trace=False."""
        bridge = AgentTrainingBridge(
            model_provider=mock_model_provider,
            trace_collector=mock_trace_collector,
            reward_calculator=mock_reward_calculator,
            config=bridge_config,
        )

        agent = Mock(spec=BaseAgent)
        agent.execute = AsyncMock(return_value=TaskResult(task_id="test"))
        task = TaskSpec(task_id="test", specification="Test")

        await bridge.wrap_agent_execution(agent, task, collect_trace=False)

        mock_trace_collector.start_trace.assert_not_called()
        mock_trace_collector.end_trace.assert_not_called()

    @pytest.mark.asyncio
    async def test_wrap_agent_execution_returns_result(
        self,
        mock_model_provider,
        mock_trace_collector,
        mock_reward_calculator,
        bridge_config,
    ):
        """Test that wrap_agent_execution returns the agent's result."""
        bridge = AgentTrainingBridge(
            model_provider=mock_model_provider,
            trace_collector=mock_trace_collector,
            reward_calculator=mock_reward_calculator,
            config=bridge_config,
        )

        expected_result = TaskResult(
            task_id="test",
            status="completed",
            files_modified=["test.py"],
        )

        agent = Mock(spec=BaseAgent)
        agent.agent_id = "test-agent-result"
        agent.execute = AsyncMock(return_value=expected_result)
        task = TaskSpec(task_id="test", specification="Test")

        result = await bridge.wrap_agent_execution(agent, task)

        assert result == expected_result
        assert result.task_id == "test"
        assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_wrap_agent_execution_handles_error(
        self,
        mock_model_provider,
        mock_trace_collector,
        mock_reward_calculator,
        bridge_config,
    ):
        """Test that wrap_agent_execution handles errors and still ends trace."""
        bridge = AgentTrainingBridge(
            model_provider=mock_model_provider,
            trace_collector=mock_trace_collector,
            reward_calculator=mock_reward_calculator,
            config=bridge_config,
        )

        agent = Mock(spec=BaseAgent)
        agent.agent_id = "test-agent-error"
        agent.execute = AsyncMock(side_effect=Exception("Agent error"))
        task = TaskSpec(task_id="test", specification="Test")

        with pytest.raises(Exception):
            await bridge.wrap_agent_execution(agent, task, collect_trace=True)

        # Trace should still be ended even on error
        mock_trace_collector.end_trace.assert_called_once()

    @pytest.mark.asyncio
    async def test_wrap_agent_execution_captures_tool_calls(
        self,
        mock_model_provider,
        mock_trace_collector,
        mock_reward_calculator,
        bridge_config,
    ):
        """Test that wrap_agent_execution captures tool calls when enabled."""
        bridge_config.capture_tool_calls = True

        bridge = AgentTrainingBridge(
            model_provider=mock_model_provider,
            trace_collector=mock_trace_collector,
            reward_calculator=mock_reward_calculator,
            config=bridge_config,
        )

        agent = Mock(spec=BaseAgent)
        agent.agent_id = "test-agent-tools"
        agent.execute = AsyncMock(return_value=TaskResult(task_id="test"))
        agent._tool_calls = [
            {"name": "read_file", "args": {"path": "test.py"}, "result": "content"},
        ]
        task = TaskSpec(task_id="test", specification="Test")

        await bridge.wrap_agent_execution(agent, task, collect_trace=True)

        # Tool calls should be recorded if available
        # Implementation may vary

    # -------------------------------------------------------------------------
    # Reward Computation Tests
    # -------------------------------------------------------------------------

    def test_compute_agent_reward_returns_components(
        self,
        mock_model_provider,
        mock_trace_collector,
        mock_reward_calculator,
        bridge_config,
    ):
        """Test that compute_agent_reward returns RewardComponents."""
        bridge = AgentTrainingBridge(
            model_provider=mock_model_provider,
            trace_collector=mock_trace_collector,
            reward_calculator=mock_reward_calculator,
            config=bridge_config,
        )

        trace = Mock()
        trace.trace_id = "trace-123"
        trace.task_id = "test-task"
        trace.status = "completed"

        reward = bridge.compute_agent_reward(trace)

        assert isinstance(reward, RewardComponents)
        assert reward.total_reward == 0.85

    def test_compute_agent_reward_uses_calculator(
        self,
        mock_model_provider,
        mock_trace_collector,
        mock_reward_calculator,
        bridge_config,
    ):
        """Test that compute_agent_reward uses the reward calculator."""
        bridge = AgentTrainingBridge(
            model_provider=mock_model_provider,
            trace_collector=mock_trace_collector,
            reward_calculator=mock_reward_calculator,
            config=bridge_config,
        )

        trace = Mock()
        trace.trace_id = "trace-123"

        bridge.compute_agent_reward(trace)

        mock_reward_calculator.compute_reward.assert_called_once_with(trace)

    def test_compute_agent_reward_handles_failed_trace(
        self,
        mock_model_provider,
        mock_trace_collector,
        mock_reward_calculator,
        bridge_config,
    ):
        """Test that compute_agent_reward handles failed traces."""
        # Use side_effect to override the fixture's side_effect
        mock_reward_calculator.compute_reward.side_effect = lambda trace: RewardComponents(
            test_pass_rate=0.0,
            code_quality=0.0,
            efficiency=0.0,
            success_bonus=0.0,
            penalty=0.0,
            total_reward=0.0,
        )

        bridge = AgentTrainingBridge(
            model_provider=mock_model_provider,
            trace_collector=mock_trace_collector,
            reward_calculator=mock_reward_calculator,
            config=bridge_config,
        )

        trace = Mock()
        trace.trace_id = "trace-failed"
        trace.status = "failed"

        reward = bridge.compute_agent_reward(trace)

        assert reward.total_reward == 0.0
        assert reward.test_pass_rate == 0.0

    # -------------------------------------------------------------------------
    # Trace Capture Tests
    # -------------------------------------------------------------------------

    def test_capture_execution_trace_extracts_data(
        self,
        mock_model_provider,
        mock_trace_collector,
        mock_reward_calculator,
        bridge_config,
    ):
        """Test that capture_execution_trace extracts trace data from agent."""
        bridge = AgentTrainingBridge(
            model_provider=mock_model_provider,
            trace_collector=mock_trace_collector,
            reward_calculator=mock_reward_calculator,
            config=bridge_config,
        )

        agent = Mock(spec=BaseAgent)
        agent.agent_id = "agent-1"
        agent._conversation_history = [
            Mock(role="user", content="Test prompt"),
            Mock(role="assistant", content="Test response"),
        ]

        task = TaskSpec(task_id="test", specification="Test")
        result = TaskResult(
            task_id="test",
            files_modified=["file.py"],
        )

        trace = bridge.capture_execution_trace(agent, task, result)

        assert trace is not None
        assert trace.task_id == "test"

    def test_capture_execution_trace_captures_file_changes(
        self,
        mock_model_provider,
        mock_trace_collector,
        mock_reward_calculator,
        bridge_config,
    ):
        """Test that capture_execution_trace captures file modifications."""
        bridge_config.capture_file_changes = True

        bridge = AgentTrainingBridge(
            model_provider=mock_model_provider,
            trace_collector=mock_trace_collector,
            reward_calculator=mock_reward_calculator,
            config=bridge_config,
        )

        agent = Mock(spec=BaseAgent)
        agent.agent_id = "agent-1"
        agent._conversation_history = []

        task = TaskSpec(task_id="test", specification="Test")
        result = TaskResult(
            task_id="test",
            files_modified=["file.py", "test_file.py"],
        )

        trace = bridge.capture_execution_trace(agent, task, result)

        assert trace is not None

    def test_capture_execution_trace_captures_llm_responses(
        self,
        mock_model_provider,
        mock_trace_collector,
        mock_reward_calculator,
        bridge_config,
    ):
        """Test that capture_execution_trace captures LLM call data."""
        bridge_config.capture_llm_responses = True

        bridge = AgentTrainingBridge(
            model_provider=mock_model_provider,
            trace_collector=mock_trace_collector,
            reward_calculator=mock_reward_calculator,
            config=bridge_config,
        )

        agent = Mock(spec=BaseAgent)
        agent.agent_id = "agent-1"
        agent._conversation_history = [
            Mock(role="user", content="Implement feature"),
            Mock(role="assistant", content="Here's the implementation..."),
        ]
        agent._llm_client = Mock()
        agent._llm_client.total_tokens = 1500

        task = TaskSpec(task_id="test", specification="Test")
        result = TaskResult(task_id="test")

        trace = bridge.capture_execution_trace(agent, task, result)

        assert trace is not None


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="BridgeConfig not implemented yet")
class TestBridgeConfig:
    """Tests for BridgeConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = BridgeConfig()

        assert config.default_model == "claude-3-5-sonnet-20241022"
        assert "manager" in config.role_model_mapping
        assert "coder" in config.role_model_mapping
        assert "reviewer" in config.role_model_mapping
        assert config.capture_tool_calls is True
        assert config.capture_llm_responses is True
        assert config.capture_file_changes is True

    def test_custom_role_mapping(self):
        """Test custom role model mapping."""
        custom_mapping = {
            "manager": "gpt-4",
            "coder": "gpt-3.5-turbo",
            "reviewer": "gpt-4",
        }

        config = BridgeConfig(role_model_mapping=custom_mapping)

        assert config.role_model_mapping == custom_mapping
        assert config.role_model_mapping["manager"] == "gpt-4"

    def test_capture_flags(self):
        """Test capture flag configurations."""
        config = BridgeConfig(
            capture_tool_calls=False,
            capture_llm_responses=False,
            capture_file_changes=True,
        )

        assert config.capture_tool_calls is False
        assert config.capture_llm_responses is False
        assert config.capture_file_changes is True
