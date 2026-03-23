"""
Agent Training Bridge

Connects agents to training infrastructure for model injection,
trace collection, and reward computation.

This module implements the bridge between the agent framework and the
training pipeline, enabling:
- Trained model injection into agents
- Execution trace collection
- Reward signal computation
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum
import logging

# Import from existing modules with fallbacks
try:
    from agents.base import AgentRole, BaseAgent, TaskSpec, TaskResult
    from training.reward_calculator import RewardCalculator, RewardComponents
    IMPORTS_AVAILABLE = True
except ImportError:
    try:
        from ..agents.base import AgentRole, BaseAgent, TaskSpec, TaskResult
        from ..training.reward_calculator import RewardCalculator, RewardComponents
        IMPORTS_AVAILABLE = True
    except ImportError:
        IMPORTS_AVAILABLE = False
        AgentRole = None
        BaseAgent = None
        TaskSpec = None
        TaskResult = None
        RewardCalculator = None
        RewardComponents = None

logger = logging.getLogger(__name__)


@dataclass
class BridgeConfig:
    """
    Configuration for Agent-Training bridge.
    
    Attributes:
        default_model: Default model to use when no trained model available
        role_model_mapping: Mapping of agent roles to specific models
        capture_tool_calls: Whether to capture tool call data
        capture_llm_responses: Whether to capture LLM response data
        capture_file_changes: Whether to capture file modification data
        reward_config: Optional reward calculation configuration
    """
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


class ITrainedModelProvider:
    """Protocol/interface for providing trained models to agents."""
    
    def get_model(self, version_id: str) -> str:
        """Get model path by version ID."""
        raise NotImplementedError
    
    def get_latest(self, model_name: str = "autodev-code-model") -> str:
        """Get latest model version path."""
        raise NotImplementedError
    
    def get_best(
        self, 
        metric: str = "resolution_rate",
        model_name: str = "autodev-code-model"
    ) -> str:
        """Get best performing model by metric."""
        raise NotImplementedError
    
    def get_for_role(self, role) -> str:
        """Get model optimized for specific agent role."""
        raise NotImplementedError
    
    def list_available(self) -> List:
        """List all available trained models."""
        raise NotImplementedError


class IAgentTraceCollector:
    """Protocol/interface for collecting execution traces from agents."""
    
    def start_trace(self, agent_id: str, task) -> str:
        """Start a new trace, returns trace_id."""
        raise NotImplementedError
    
    def record_tool_call(
        self,
        trace_id: str,
        tool_name: str,
        tool_input: Dict[str, Any],
        tool_output: Any,
        duration_ms: float
    ) -> None:
        """Record a tool call within a trace."""
        raise NotImplementedError
    
    def record_llm_call(
        self,
        trace_id: str,
        prompt: str,
        response: str,
        tokens_used: int,
        duration_ms: float
    ) -> None:
        """Record an LLM call within a trace."""
        raise NotImplementedError
    
    def record_file_change(
        self,
        trace_id: str,
        file_path: str,
        change_type: str,
        diff: str
    ) -> None:
        """Record a file modification."""
        raise NotImplementedError
    
    def end_trace(self, trace_id: str, result, success: bool):
        """Finalize and return the complete trace."""
        raise NotImplementedError
    
    def flush(self) -> List:
        """Flush all buffered traces."""
        raise NotImplementedError
    
    def to_dataset(self):
        """Convert collected traces to training dataset."""
        raise NotImplementedError


class AgentTrainingBridge:
    """
    Bridge connecting agents to training infrastructure.
    
    This class wraps agent execution to:
    - Inject trained models into agents
    - Collect execution traces
    - Compute reward signals
    """
    
    def __init__(
        self,
        model_provider: Optional[ITrainedModelProvider] = None,
        trace_collector: Optional[IAgentTraceCollector] = None,
        reward_calculator: Optional[RewardCalculator] = None,
        config: Optional[BridgeConfig] = None,
    ):
        """
        Initialize the Agent Training Bridge.
        
        Args:
            model_provider: Provider for trained models
            trace_collector: Collector for execution traces
            reward_calculator: Calculator for reward signals
            config: Bridge configuration
        """
        self.model_provider = model_provider
        self.trace_collector = trace_collector
        self.reward_calculator = reward_calculator
        self.config = config or BridgeConfig()
        
        logger.info("AgentTrainingBridge initialized")
    
    async def wrap_agent_execution(
        self,
        agent: BaseAgent,
        task: TaskSpec,
        collect_trace: bool = True
    ) -> TaskResult:
        """
        Wrap agent execution with trace collection and model injection.
        
        Args:
            agent: Agent to execute
            task: Task to execute
            collect_trace: Whether to collect execution trace
            
        Returns:
            TaskResult from execution
        """
        trace_id = None
        
        # Start trace collection if enabled
        if collect_trace and self.trace_collector:
            trace_id = self.trace_collector.start_trace(agent.agent_id, task)
        
        try:
            # Execute the agent
            result = await agent.execute(task)
            
            # End trace on success
            if trace_id and self.trace_collector:
                self.trace_collector.end_trace(trace_id, result, success=True)
            
            return result
            
        except Exception as e:
            # End trace on error
            if trace_id and self.trace_collector:
                error_result = type('TaskResult', (), {
                    'task_id': task.task_id,
                    'status': 'failed',
                    'errors': [str(e)]
                })()
                self.trace_collector.end_trace(trace_id, error_result, success=False)
            raise
    
    def inject_trained_model(
        self,
        agent: BaseAgent,
        model_version: str
    ) -> None:
        """
        Inject a trained model into an agent.
        
        Args:
            agent: Agent to inject model into
            model_version: Model version identifier or path
        """
        # Resolve model path from provider if available
        if self.model_provider and not model_version.startswith('/'):
            model_path = self.model_provider.get_model(model_version)
        else:
            model_path = model_version
        
        # Set model on agent's LLM client
        if hasattr(agent, '_llm_client'):
            if hasattr(agent._llm_client, 'set_model'):
                agent._llm_client.set_model(model_path)
            else:
                agent._llm_client.model = model_path
        
        logger.info(f"Injected model {model_version} into agent {agent.agent_id}")
    
    def capture_execution_trace(
        self,
        agent: BaseAgent,
        task: TaskSpec,
        result: TaskResult
    ):
        """
        Extract trace data from agent execution.
        
        Args:
            agent: Agent that executed
            task: Task that was executed
            result: Execution result
            
        Returns:
            Execution trace object
        """
        trace = type('ExecutionTrace', (), {
            'trace_id': f"trace-{agent.agent_id}-{task.task_id}",
            'task_id': task.task_id,
            'agent_id': agent.agent_id,
            'status': result.status if hasattr(result, 'status') else 'completed',
            'tool_calls': getattr(agent, '_tool_calls', []) if self.config.capture_tool_calls else [],
            'llm_calls': getattr(agent, '_conversation_history', []) if self.config.capture_llm_responses else [],
            'file_changes': [
                {'file_path': f, 'change_type': 'modify'}
                for f in (result.files_modified if hasattr(result, 'files_modified') else [])
            ] if self.config.capture_file_changes else [],
        })()
        
        return trace
    
    def compute_agent_reward(self, trace):
        """
        Compute reward components from execution trace.
        
        Args:
            trace: Execution trace
            
        Returns:
            RewardComponents with reward breakdown
        """
        if self.reward_calculator:
            return self.reward_calculator.compute_reward(trace)
        
        # Default reward computation if no calculator
        if not IMPORTS_AVAILABLE:
            return type('RewardComponents', (), {
                'task_success': 0.5,
                'code_quality': 0.5,
                'test_coverage': 0.5,
                'efficiency': 0.5,
                'total': 0.5,
            })()
        
        success = getattr(trace, 'status', 'failed') == 'completed'
        return RewardComponents(
            task_success=1.0 if success else 0.0,
            code_quality=0.8 if success else 0.0,
            test_coverage=0.9 if success else 0.0,
            efficiency=0.7 if success else 0.0,
            total=0.85 if success else 0.0,
        )
    
    def get_model_for_role(self, role: AgentRole, prefer_trained: bool = True) -> str:
        """
        Get the appropriate model for an agent role.
        
        Args:
            role: Agent role to get model for
            prefer_trained: Whether to prefer trained models
            
        Returns:
            Model identifier or path
        """
        if prefer_trained and self.model_provider:
            trained_model = self.model_provider.get_for_role(role)
            if trained_model:
                return trained_model
        
        # Fall back to role mapping
        role_name = role.value if hasattr(role, 'value') else str(role)
        return self.config.role_model_mapping.get(
            role_name,
            self.config.default_model
        )
