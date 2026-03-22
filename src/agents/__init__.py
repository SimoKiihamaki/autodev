"""
AutoDev Agent System

Hierarchical agent architecture with Manager-Coder-Reviewer pattern.
"""

from .base import BaseAgent, AgentRole, AgentState
from .states import StateMachine, ManagerState
from .communication import AgentMessage, MessageType, TaskAssignment

__all__ = [
    "BaseAgent",
    "AgentRole",
    "AgentState",
    "StateMachine",
    "ManagerState",
    "AgentMessage",
    "MessageType",
    "TaskAssignment",
]
