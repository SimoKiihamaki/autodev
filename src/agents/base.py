"""
Base Agent Classes and Interfaces

Defines the base class for all AutoDev agents and common interfaces.
Updated for Phase 2 with LLM and MCP integration.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
import logging

# Import LLM types (with fallback for standalone use)
try:
    from ..llm.base_client import (
        ChatMessage,
        MessageRole,
        LLMConfig,
        BaseLLMClient,
    )
    from ..llm.anthropic_client import AnthropicClient
    LLM_AVAILABLE = True
except ImportError:
    try:
        # Fallback for running from src directory
        from llm.base_client import (
            ChatMessage,
            MessageRole,
            LLMConfig,
            BaseLLMClient,
        )
        from llm.anthropic_client import AnthropicClient
        LLM_AVAILABLE = True
    except ImportError:
        LLM_AVAILABLE = False
        ChatMessage = None
        MessageRole = None
        LLMConfig = None
        BaseLLMClient = None
        AnthropicClient = None

logger = logging.getLogger(__name__)


class AgentRole(Enum):
    """Roles available in the agent hierarchy."""
    MANAGER = "manager"
    CODER = "coder"
    REVIEWER = "reviewer"
    TESTER = "tester"


class AgentState(Enum):
    """Common agent states."""
    IDLE = "idle"
    INITIALIZING = "initializing"
    ACTIVE = "active"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TaskSpec:
    """
    Task specification for agent execution.
    
    Attributes:
        task_id: Unique identifier for this task
        task_type: Type of development task (implement, review, test, refactor, debug)
        specification: Task specification or PRD excerpt
        target_files: Optional list of files to modify
        constraints: Task constraints (preserve_api, maintain_coverage, etc.)
        verification_command: Optional command to verify success
        timeout_seconds: Maximum execution time
        created_at: Task creation timestamp
    """
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_type: str = "implement"
    specification: str = ""
    target_files: List[str] = field(default_factory=list)
    constraints: Dict[str, Any] = field(default_factory=dict)
    verification_command: Optional[str] = None
    timeout_seconds: int = 300
    created_at: datetime = field(default_factory=datetime.utcnow)
    repo_root: str = "."


@dataclass
class TaskResult:
    """
    Result from task execution.
    
    Attributes:
        task_id: ID of the executed task
        status: Current status (running, completed, failed, timeout)
        started_at: When execution started
        completed_at: When execution completed (if applicable)
        files_modified: List of files that were modified
        summary: Human-readable summary of what was done
        review_verdict: Review result (approved, needs_changes, rejected)
        test_results: Test execution results
        error: Error message if failed
        result: Raw result data
    """
    task_id: str
    status: str = "running"
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    files_modified: List[str] = field(default_factory=list)
    summary: str = ""
    review_verdict: Optional[str] = None
    test_results: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    result: Any = None


@dataclass
class SubTask:
    """
    Decomposed subtask from Manager Agent.
    
    Attributes:
        subtask_id: Unique identifier
        parent_task_id: ID of parent task
        name: Human-readable name
        description: Detailed description
        task_type: Type of subtask
        priority: Priority level (critical, high, medium, low)
        dependencies: List of blocking subtask IDs
        assigned_to: Agent role this is assigned to
        context: Relevant context (files, related tasks, etc.)
        status: Current status
    """
    subtask_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_task_id: str = ""
    name: str = ""
    description: str = ""
    task_type: str = "implement"
    priority: str = "medium"
    dependencies: List[str] = field(default_factory=list)
    assigned_to: AgentRole = AgentRole.CODER
    context: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"


class BaseAgent(ABC):
    """
    Abstract base class for all AutoDev agents.
    
    All agents (Manager, Coder, Reviewer) inherit from this class
    and implement the required abstract methods.
    
    Updated with LLM and MCP integration for Phase 2.
    
    Attributes:
        agent_id: Unique identifier for this agent instance
        role: Agent's role in the hierarchy
        state: Current agent state
        mcp_config_path: Path to MCP configuration file
        repo_root: Root directory of the repository
        _llm_client: LLM client for completions
        _mcp_client: MCP client for tool execution
        _tool_executor: Tool execution loop
        _conversation_history: Conversation history for context
    """
    
    def __init__(
        self,
        agent_id: str = None,
        role: AgentRole = None,
        mcp_config_path: str = "~/.config/autodev/mcp_config.json",
        repo_root: str = ".",
        llm_config: Optional[Any] = None
    ):
        self.agent_id = agent_id or str(uuid.uuid4())
        self.role = role or AgentRole.CODER
        self.state = AgentState.IDLE
        self.mcp_config_path = mcp_config_path
        self.repo_root = repo_root
        
        # LLM and MCP clients (Phase 2)
        self._llm_config = llm_config
        self._llm_client: Optional[Any] = None
        self._mcp_client: Optional[Any] = None
        self._tool_executor: Optional[Any] = None
        
        # Message queue for inter-agent communication
        self._message_queue: List[Any] = []
        
        # Conversation history for context (Phase 2)
        self._conversation_history: List[Any] = []
    
    @abstractmethod
    async def execute(self, task: TaskSpec) -> TaskResult:
        """
        Execute a task and return the result.
        
        Args:
            task: Task specification to execute
            
        Returns:
            TaskResult with execution outcome
        """
        pass
    
    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize the agent.
        
        Connects to MCP servers, initializes LLM client, prepares for execution.
        """
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """
        Clean shutdown of the agent.
        
        Disconnects from MCP servers, saves state, releases resources.
        """
        pass
    
    async def _initialize_llm(self) -> None:
        """
        Initialize the LLM client.
        
        Uses the agent's role to select appropriate model and system prompt.
        """
        if not LLM_AVAILABLE:
            logger.warning("LLM modules not available, skipping LLM initialization")
            return
        
        # Create default config if not provided
        if self._llm_config is None:
            self._llm_config = LLMConfig()
        
        # Set model based on role
        role_models = {
            AgentRole.MANAGER: "claude-3-5-sonnet-20241022",
            AgentRole.CODER: "claude-3-5-sonnet-20241022",
            AgentRole.REVIEWER: "claude-3-5-sonnet-20241022",
            AgentRole.TESTER: "claude-3-5-sonnet-20241022",
        }
        self._llm_config.model = role_models.get(self.role, self._llm_config.model)
        
        # Initialize Anthropic client
        self._llm_client = AnthropicClient(self._llm_config)
        logger.info(f"Initialized LLM client for {self.role.value} with model {self._llm_config.model}")
    
    async def _initialize_mcp(self) -> None:
        """
        Initialize the MCP client.
        
        Attempts to connect to configured MCP servers.
        Uses real MCP client when available, falls back to mock.
        """
        try:
            # Try to import real MCP client first
            mcp_client_class = None
            try:
                from ..mcp.client import AutoDevMCPClient
                mcp_client_class = AutoDevMCPClient
            except ImportError:
                try:
                    from mcp.client import AutoDevMCPClient
                    mcp_client_class = AutoDevMCPClient
                except ImportError:
                    pass
            
            if mcp_client_class:
                self._mcp_client = mcp_client_class(self.mcp_config_path)
                await self._mcp_client.connect_all()
                logger.info(f"Initialized real MCP client for {self.role.value}")
            else:
                # Fall back to mock client
                try:
                    from .tool_executor import MockMCPClient
                except ImportError:
                    from tool_executor import MockMCPClient
                self._mcp_client = MockMCPClient()
                await self._mcp_client.connect_all()
                logger.info(f"Initialized mock MCP client for {self.role.value}")
                
        except Exception as e:
            logger.warning(f"Could not initialize MCP client: {e}")
            # Try mock as last resort
            try:
                try:
                    from .tool_executor import MockMCPClient
                except ImportError:
                    from tool_executor import MockMCPClient
                self._mcp_client = MockMCPClient()
                await self._mcp_client.connect_all()
            except Exception:
                self._mcp_client = None
    
    async def _initialize_tool_executor(self, max_iterations: int = 20) -> None:
        """
        Initialize the tool execution loop.
        
        Args:
            max_iterations: Maximum tool calling iterations
        """
        if self._llm_client and self._mcp_client:
            try:
                from .tool_executor import ToolExecutionLoop
            except ImportError:
                from tool_executor import ToolExecutionLoop
            self._tool_executor = ToolExecutionLoop(
                llm_client=self._llm_client,
                mcp_client=self._mcp_client,
                max_iterations=max_iterations
            )
            logger.info(f"Initialized tool executor for {self.role.value}")
    
    async def _call_llm(
        self,
        prompt: str,
        use_tools: bool = True,
        system_prompt: Optional[str] = None
    ) -> str:
        """
        Call LLM with optional tool support.
        
        Args:
            prompt: User prompt
            use_tools: Whether to enable tool calling
            system_prompt: Optional system prompt override
            
        Returns:
            LLM response
        """
        if not self._llm_client:
            raise RuntimeError("LLM client not initialized")
        
        # Create message objects if available
        if LLM_AVAILABLE and ChatMessage and MessageRole:
            # Add to conversation history
            self._conversation_history.append(ChatMessage(
                role=MessageRole.USER,
                content=prompt
            ))
            
            if use_tools and self._tool_executor:
                # Execute with tool loop
                response = await self._tool_executor.execute_with_tools(
                    initial_messages=self._conversation_history,
                    system_prompt=system_prompt or self._get_default_system_prompt(),
                    on_tool_call=self._on_tool_call
                )
            else:
                # Simple completion without tools
                llm_response = await self._llm_client.complete(
                    messages=self._conversation_history,
                    system_prompt=system_prompt or self._get_default_system_prompt()
                )
                response = llm_response.content
            
            # Add response to history
            self._conversation_history.append(ChatMessage(
                role=MessageRole.ASSISTANT,
                content=response
            ))
            
            return response
        else:
            # Fallback without ChatMessage
            raise RuntimeError("LLM types not available")
    
    def _on_tool_call(self, tool_name: str, tool_input: Dict[str, Any]) -> None:
        """
        Callback when a tool is called (for logging/monitoring).
        
        Args:
            tool_name: Name of the tool being called
            tool_input: Tool input parameters
        """
        logger.info(f"Agent {self.agent_id} ({self.role.value}) calling tool: {tool_name}")
    
    def _get_default_system_prompt(self) -> str:
        """
        Get the default system prompt for this agent type.
        
        Returns:
            System prompt string
        """
        if LLM_AVAILABLE and AnthropicClient:
            return AnthropicClient.get_system_prompt(self.role.value)
        return f"You are a {self.role.value} agent in the AutoDev system."
    
    def receive_message(self, message: Any) -> None:
        """
        Receive a message from another agent.
        
        Args:
            message: Message to receive
        """
        self._message_queue.append(message)
    
    def get_next_message(self) -> Optional[Any]:
        """
        Get the next message from the queue.
        
        Returns:
            Next message or None if queue is empty
        """
        if self._message_queue:
            return self._message_queue.pop(0)
        return None
    
    def update_state(self, new_state: AgentState) -> None:
        """
        Update the agent's state.
        
        Args:
            new_state: New state to transition to
        """
        old_state = self.state
        self.state = new_state
        logger.debug(f"Agent {self.agent_id} state: {old_state.value} -> {new_state.value}")
    
    def get_llm_usage_stats(self) -> Dict[str, Any]:
        """
        Get LLM usage statistics.
        
        Returns:
            Dictionary with usage statistics or empty dict if not available
        """
        if self._llm_client and hasattr(self._llm_client, 'get_usage_stats'):
            return self._llm_client.get_usage_stats()
        return {}
    
    def clear_conversation_history(self) -> None:
        """Clear the conversation history."""
        self._conversation_history = []
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self.agent_id}, role={self.role.value}, state={self.state.value})"
