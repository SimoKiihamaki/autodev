"""
Hierarchical Agent Memory System

Provides persistent memory and context management for hierarchical agents.

This submodule enables:
- Agent Memory: Persistent storage of agent experiences and knowledge
- Context Management: Smart context window management for large codebases

Usage:
    from hierarchical.memory import AgentMemory, ContextManager
    
    memory = AgentMemory(agent_id="coder_1")
    memory.store_experience(task_id, trace)
    
    context = ContextManager(max_tokens=4000)
    context.add_file("src/main.py")
"""

from .agent_memory import (
    AgentMemory,
    MemoryEntry,
    ExperienceTrace,
    MemoryConfig,
)
from .context_manager import (
    ContextManager,
    ContextWindow,
    ContextConfig,
    FileSummary,
)

__all__ = [
    # Agent Memory
    "AgentMemory",
    "MemoryEntry",
    "ExperienceTrace",
    "MemoryConfig",
    # Context Management
    "ContextManager",
    "ContextWindow",
    "ContextConfig",
    "FileSummary",
]
