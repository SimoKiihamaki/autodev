"""
AutoDev Agent System

Hierarchical agent architecture with Manager-Coder-Reviewer pattern.
Phase 2: Enhanced with LLM and MCP integration.
"""

from .base import (
    BaseAgent,
    AgentRole,
    AgentState,
    TaskSpec,
    TaskResult,
    SubTask,
)
from .states import (
    StateMachine,
    ManagerState,
    CoderState,
    ReviewerState,
)
from .communication import (
    AgentMessage,
    MessageType,
    TaskAssignment,
    ReviewResult,
    Finding,
    MessageRouter,
)

# Import concrete agent implementations
from .manager import ManagerAgent
from .coder import CoderAgent
from .reviewer import ReviewerAgent

__all__ = [
    # Base classes
    "BaseAgent",
    "AgentRole",
    "AgentState",
    "TaskSpec",
    "TaskResult",
    "SubTask",
    # State machines
    "StateMachine",
    "ManagerState",
    "CoderState",
    "ReviewerState",
    # Communication
    "AgentMessage",
    "MessageType",
    "TaskAssignment",
    "ReviewResult",
    "Finding",
    "MessageRouter",
    # Agent implementations
    "ManagerAgent",
    "CoderAgent",
    "ReviewerAgent",
]
