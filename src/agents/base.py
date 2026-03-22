"""
Base Agent Classes and Interfaces

Defines the base class for all AutoDev agents and common interfaces.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


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
    
    Attributes:
        agent_id: Unique identifier for this agent instance
        role: Agent's role in the hierarchy
        state: Current agent state
        mcp_config_path: Path to MCP configuration file
        repo_root: Root directory of the repository
    """
    
    def __init__(
        self,
        agent_id: str = None,
        role: AgentRole = None,
        mcp_config_path: str = "~/.config/autodev/mcp_config.json",
        repo_root: str = "."
    ):
        self.agent_id = agent_id or str(uuid.uuid4())
        self.role = role or AgentRole.CODER
        self.state = AgentState.IDLE
        self.mcp_config_path = mcp_config_path
        self.repo_root = repo_root
        self._mcp_client = None
        self._message_queue: List[Any] = []
    
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
        
        Connects to MCP servers, loads configuration, prepares for execution.
        """
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """
        Clean shutdown of the agent.
        
        Disconnects from MCP servers, saves state, releases resources.
        """
        pass
    
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
        self.state = new_state
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self.agent_id}, role={self.role.value}, state={self.state.value})"
