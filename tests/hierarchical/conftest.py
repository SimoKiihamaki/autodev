"""
Shared pytest fixtures for hierarchical agent pipeline tests.

This module provides fixtures for testing the agent pipeline integration,
including mock agents, mock training components, and test configurations.
"""

import sys
from pathlib import Path

# Add project root to Python path so 'src' package can be imported
# This allows tests to import from src.agents, src.training, src.hierarchical, etc.
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

# Import type hints for type annotations
# These will be available once the implementation is complete
try:
    from src.agents.base import AgentRole, BaseAgent, TaskSpec, TaskResult
    from src.agents.coder import CoderAgent
    from src.agents.communication import ReviewResult
    from src.agents.manager import ManagerAgent
    from src.agents.reviewer import ReviewerAgent
    from src.training.orchestrator import OrchestratorConfig, TrainingOrchestrator
    from src.training.reward_calculator import RewardComponents

    IMPORTS_AVAILABLE = True
except ImportError:
    IMPORTS_AVAILABLE = False
    # Create placeholder types for type hints
    AgentRole = MagicMock
    BaseAgent = MagicMock
    TaskSpec = MagicMock
    TaskResult = MagicMock
    CoderAgent = MagicMock
    ReviewerAgent = MagicMock
    ManagerAgent = MagicMock
    ReviewResult = MagicMock
    TrainingOrchestrator = MagicMock
    OrchestratorConfig = MagicMock
    RewardComponents = MagicMock


# -----------------------------------------------------------------------------
# Configuration Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def pipeline_config():
    """Create a default AgentPipelineConfig for testing."""
    from dataclasses import dataclass

    @dataclass
    class AgentPipelineConfig:
        """Test configuration for Agent Pipeline."""
        max_concurrent_agents: int = 2
        agent_timeout_seconds: int = 600
        max_iterations_per_task: int = 5
        use_trained_models: bool = False
        model_selection_strategy: str = "best"
        collect_traces: bool = True
        trace_buffer_size: int = 100
        enable_hierarchical: bool = True
        max_review_iterations: int = 3
        require_review_approval: bool = True
        mcp_config_path: str = "/tmp/test_mcp_config.json"
        checkpoint_dir: str = "/tmp/test_checkpoints"
        training_config: Optional[Any] = None

    return AgentPipelineConfig()


@pytest.fixture
def bridge_config():
    """Create a default BridgeConfig for testing."""
    from dataclasses import dataclass, field

    @dataclass
    class BridgeConfig:
        """Test configuration for Agent-Training bridge."""
        default_model: str = "claude-3-5-sonnet-20241022"
        role_model_mapping: Dict[str, str] = field(default_factory=lambda: {
            "manager": "claude-3-5-sonnet-20241022",
            "coder": "claude-3-5-sonnet-20241022",
            "reviewer": "claude-3-5-sonnet-20241022",
        })
        capture_tool_calls: bool = True
        capture_llm_responses: bool = True
        capture_file_changes: bool = True
        reward_config: Optional[Any] = None

    return BridgeConfig()


# -----------------------------------------------------------------------------
# Mock Agent Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def mock_base_agent():
    """Create a mock BaseAgent for testing."""
    agent = Mock(spec=BaseAgent)
    agent.agent_id = "test-agent-001"
    agent.role = AgentRole.CODER if IMPORTS_AVAILABLE else "coder"
    agent._llm_client = Mock()
    agent._conversation_history = []
    agent.state = "idle"

    async def mock_execute(task):
        return TaskResult(
            task_id=task.task_id if hasattr(task, 'task_id') else "test-task",
            status="completed",
            files_modified=["test.py"],
        ) if IMPORTS_AVAILABLE else Mock(task_id="test-task", status="completed")

    agent.execute = AsyncMock(side_effect=mock_execute)
    agent.initialize = AsyncMock()
    agent.shutdown = AsyncMock()

    return agent


@pytest.fixture
def mock_manager_agent():
    """Create a mock ManagerAgent for testing."""
    manager = Mock(spec=ManagerAgent) if IMPORTS_AVAILABLE else Mock()
    manager.agent_id = "manager-001"
    manager.role = AgentRole.MANAGER if IMPORTS_AVAILABLE else "manager"
    manager._llm_client = Mock()
    manager._conversation_history = []
    manager.state = "idle"
    manager.subtasks = []
    manager.workers = {}

    manager.initialize = AsyncMock()
    manager.shutdown = AsyncMock()
    manager.decompose = AsyncMock(return_value=[])
    manager.dispatch = AsyncMock()
    manager.monitor = AsyncMock()
    manager.synthesize = AsyncMock()

    return manager


@pytest.fixture
def mock_coder_agents():
    """Create a list of mock CoderAgents for testing."""
    coders = []
    for i in range(3):
        coder = Mock(spec=CoderAgent) if IMPORTS_AVAILABLE else Mock()
        coder.agent_id = f"coder-{i}"
        coder.role = AgentRole.CODER if IMPORTS_AVAILABLE else "coder"
        coder._llm_client = Mock()
        coder._conversation_history = []
        coder.state = "idle"
        coder.current_file = None
        coder.changes = []

        async def mock_execute(task):
            return TaskResult(
                task_id=task.task_id if hasattr(task, 'task_id') else f"task-{i}",
                status="completed",
                files_modified=[f"file_{i}.py"],
            ) if IMPORTS_AVAILABLE else Mock(task_id=f"task-{i}", status="completed")

        coder.execute = AsyncMock(side_effect=mock_execute)
        coder.initialize = AsyncMock()
        coder.shutdown = AsyncMock()
        coder.implement = AsyncMock()
        coder.refactor = AsyncMock()
        coder.fix_bug = AsyncMock()
        coder.write_test = AsyncMock()

        coders.append(coder)

    return coders


@pytest.fixture
def mock_reviewer_agents():
    """Create a list of mock ReviewerAgents for testing."""
    reviewers = []
    for i in range(2):
        reviewer = Mock(spec=ReviewerAgent) if IMPORTS_AVAILABLE else Mock()
        reviewer.agent_id = f"reviewer-{i}"
        reviewer.role = AgentRole.REVIEWER if IMPORTS_AVAILABLE else "reviewer"
        reviewer._llm_client = Mock()
        reviewer._conversation_history = []
        reviewer.state = "idle"
        reviewer.findings = []
        reviewer.verdict = None
        reviewer.blocking = []

        async def mock_review(changes):
            return ReviewResult(
                review_id=f"review-{i}",
                task_id="test-task",
                verdict="approved",
            ) if IMPORTS_AVAILABLE else Mock(review_id=f"review-{i}", verdict="approved")

        reviewer.review = AsyncMock(side_effect=mock_review)
        reviewer.validate = AsyncMock()
        reviewer.check_std = AsyncMock()
        reviewer.detect = AsyncMock()
        reviewer.initialize = AsyncMock()
        reviewer.shutdown = AsyncMock()

        reviewers.append(reviewer)

    return reviewers


# -----------------------------------------------------------------------------
# Mock Training Component Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def mock_orchestrator():
    """Create a mock TrainingOrchestrator for testing."""
    orchestrator = Mock(spec=TrainingOrchestrator) if IMPORTS_AVAILABLE else Mock()
    orchestrator.run_training_cycle = AsyncMock(
        return_value=Mock(success=True, model_path="/tmp/test_model")
    )
    orchestrator.set_agent_pipeline = Mock()
    orchestrator._agent_pipeline = None

    return orchestrator


@pytest.fixture
def mock_model_provider():
    """Create a mock TrainedModelProvider for testing."""
    provider = Mock()
    provider.get_model = Mock(return_value="/path/to/model/v1.0.0")
    provider.get_latest = Mock(return_value="/path/to/model/latest")
    provider.get_best = Mock(return_value="/path/to/best/model")
    provider.get_for_role = Mock(return_value="/path/to/role/model")
    provider.list_available = Mock(return_value=[
        Mock(version="v1.0.0", metric=0.85),
        Mock(version="v1.1.0", metric=0.90),
    ])

    return provider


@pytest.fixture
def mock_trace_collector():
    """Create a mock AgentTraceCollector for testing."""
    collector = Mock()
    collector._traces = []

    def start_trace(agent_id, task):
        trace_id = f"trace-{agent_id}-{task.task_id if hasattr(task, 'task_id') else 'unknown'}"
        return trace_id

    def end_trace(trace_id, result, success):
        trace = Mock(
            trace_id=trace_id,
            result=result,
            success=success,
            task_id="test-task",
        )
        collector._traces.append(trace)
        return trace

    collector.start_trace = Mock(side_effect=start_trace)
    collector.end_trace = Mock(side_effect=end_trace)
    collector.record_tool_call = Mock()
    collector.record_llm_call = Mock()
    collector.record_file_change = Mock()
    collector.flush = Mock(return_value=collector._traces)
    collector.to_dataset = Mock(return_value=Mock())

    return collector


@pytest.fixture
def mock_reward_calculator():
    """Create a mock RewardCalculator for testing."""
    calculator = Mock()

    def compute_reward(trace):
        return RewardComponents(
            test_pass_rate=0.9,
            code_quality=0.8,
            efficiency=0.7,
            success_bonus=0.1,
            penalty=0.0,
            total_reward=0.85,
        ) if IMPORTS_AVAILABLE else Mock(total_reward=0.85)

    calculator.compute_reward = Mock(side_effect=compute_reward)

    return calculator


@pytest.fixture
def mock_reward_components():
    """Create mock RewardComponents for testing."""
    if IMPORTS_AVAILABLE:
        return RewardComponents(
            task_success=1.0,
            code_quality=0.8,
            test_coverage=0.9,
            efficiency=0.7,
            total=0.85,
        )
    return Mock(
        task_success=1.0,
        code_quality=0.8,
        test_coverage=0.9,
        efficiency=0.7,
        total=0.85,
    )


# -----------------------------------------------------------------------------
# Task Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def sample_task():
    """Create a sample TaskSpec for testing."""
    if IMPORTS_AVAILABLE:
        return TaskSpec(
            task_id="test-task-001",
            task_type="implement",
            specification="Implement a hello world function",
            target_files=["hello.py"],
        )
    return Mock(
        task_id="test-task-001",
        task_type="implement",
        specification="Implement a hello world function",
        target_files=["hello.py"],
    )


@pytest.fixture
def sample_tasks():
    """Create a list of sample TaskSpecs for testing."""
    tasks = []
    for i in range(3):
        if IMPORTS_AVAILABLE:
            task = TaskSpec(
                task_id=f"test-task-{i:03d}",
                task_type="implement",
                specification=f"Task {i} specification",
                target_files=[f"file_{i}.py"],
            )
        else:
            task = Mock(
                task_id=f"test-task-{i:03d}",
                task_type="implement",
                specification=f"Task {i} specification",
                target_files=[f"file_{i}.py"],
            )
        tasks.append(task)
    return tasks


@pytest.fixture
def sample_subtasks():
    """Create a list of sample SubTasks for testing."""
    from dataclasses import dataclass
    from typing import Optional

    @dataclass
    class SubTask:
        """Test SubTask class."""
        subtask_id: str
        name: str
        task_type: str = "implement"
        description: Optional[str] = None
        assigned_agent: Optional[str] = None
        dependencies: List[str] = field(default_factory=list)
        status: str = "pending"

    return [
        SubTask(
            subtask_id="sub-001",
            name="Implement core logic",
            task_type="implement",
            description="Implement the main functionality",
        ),
        SubTask(
            subtask_id="sub-002",
            name="Add unit tests",
            task_type="test",
            description="Add comprehensive unit tests",
        ),
        SubTask(
            subtask_id="sub-003",
            name="Update documentation",
            task_type="docs",
            description="Update relevant documentation",
        ),
    ]


# -----------------------------------------------------------------------------
# Result Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def sample_task_result():
    """Create a sample TaskResult for testing."""
    if IMPORTS_AVAILABLE:
        return TaskResult(
            task_id="test-task-001",
            status="completed",
            files_modified=["hello.py", "test_hello.py"],
            output="Successfully implemented hello world",
            errors=[],
        )
    return Mock(
        task_id="test-task-001",
        status="completed",
        files_modified=["hello.py", "test_hello.py"],
        output="Successfully implemented hello world",
        errors=[],
    )


@pytest.fixture
def sample_review_result():
    """Create a sample ReviewResult for testing."""
    if IMPORTS_AVAILABLE:
        return ReviewResult(
            review_id="review-001",
            task_id="test-task-001",
            verdict="approved",
            findings=["Code looks good"],
            blocking_issues=[],
        )
    return Mock(
        review_id="review-001",
        task_id="test-task-001",
        verdict="approved",
        findings=["Code looks good"],
        blocking_issues=[],
    )


# -----------------------------------------------------------------------------
# Execution Trace Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def sample_execution_trace():
    """Create a sample ExecutionTrace for testing."""
    return Mock(
        trace_id="trace-001",
        task_id="test-task-001",
        agent_id="coder-0",
        status="completed",
        tool_calls=[
            Mock(tool_name="read_file", duration_ms=50),
            Mock(tool_name="write_file", duration_ms=100),
        ],
        llm_calls=[
            Mock(tokens_used=1000, duration_ms=200),
        ],
        file_changes=[
            Mock(file_path="hello.py", change_type="create"),
        ],
        start_time="2026-03-23T10:00:00Z",
        end_time="2026-03-23T10:00:30Z",
    )


# -----------------------------------------------------------------------------
# Pytest Configuration
# -----------------------------------------------------------------------------

def pytest_configure(config):
    """Configure custom pytest markers for hierarchical tests."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (requires full setup)"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running (may take >10 seconds)"
    )
    config.addinivalue_line(
        "markers", "gpu: mark test as requiring GPU resources"
    )
    config.addinivalue_line(
        "markers", "hierarchical: mark test as testing hierarchical agent flow"
    )


@pytest.fixture
def mock_bridge(
    mock_model_provider,
    mock_trace_collector,
    mock_reward_calculator,
    bridge_config,
):
    """Create a mock AgentTrainingBridge for testing."""
    bridge = Mock()
    bridge.model_provider = mock_model_provider
    bridge.trace_collector = mock_trace_collector
    bridge.reward_calculator = mock_reward_calculator
    bridge.config = bridge_config

    async def wrap_execution(agent, task, collect_trace=True):
        return TaskResult(
            task_id=task.task_id if hasattr(task, 'task_id') else "test-task",
            status="completed",
        ) if IMPORTS_AVAILABLE else Mock(task_id="test-task", status="completed")

    bridge.wrap_agent_execution = AsyncMock(side_effect=wrap_execution)
    bridge.inject_trained_model = Mock()
    bridge.get_model_for_role = Mock(return_value="/path/to/model")
    bridge.compute_agent_reward = Mock(return_value=mock_reward_components)
    bridge.capture_execution_trace = Mock(return_value=Mock(trace_id="trace-1"))

    return bridge


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
