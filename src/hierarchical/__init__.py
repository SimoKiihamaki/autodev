"""
AutoDev Hierarchical Multi-Agent Orchestration System

Phase 10: Hierarchical Multi-Agent Orchestration with production workloads.

This module provides the infrastructure for coordinating Manager-Coder-Reviewer
patterns with the existing training pipeline and Hermes integration.

Key Components:
- Agent Pipeline: Connects agents to the Training Orchestrator
- Hermes Integration: Full delegate_task tool integration
- Memory System: Persistent context across tasks
- Coordination: Dynamic task routing and conflict resolution

Usage:
    from hierarchical import AgentPipeline, HermesIntegration
    from hierarchical.memory import AgentMemory, ContextManager
    from hierarchical.coordination import TaskRouter, ConflictResolver

Dependencies:
- src/agents/: Existing agent framework (Manager, Coder, Reviewer)
- src/training/: Training Orchestrator and GRPO Trainer
- Hermes delegate_task API
"""

from .agent_pipeline import (
    AgentPipeline,
    PipelineConfig,
    PipelineState,
    PipelineResult,
)
from .hermes_integration import (
    HermesIntegration,
    DelegateTaskConfig,
    TaskDelegateResult,
)
from .agent_training_bridge import (
    AgentTrainingBridge,
    BridgeConfig,
)
from .hierarchical_executor import (
    HierarchicalExecutor,
    ExecutionPhase,
    PhaseResult,
    IterationRecord,
    HierarchicalResult,
)

# Aliases for test compatibility
AgentPipelineConfig = PipelineConfig

__version__ = "0.1.0"
__phase__ = "10 - Hierarchical Multi-Agent Orchestration"

__all__ = [
    # Agent Pipeline
    "AgentPipeline",
    "PipelineConfig",
    "AgentPipelineConfig",  # Alias
    "PipelineState",
    "PipelineResult",
    # Hermes Integration
    "HermesIntegration",
    "DelegateTaskConfig",
    "TaskDelegateResult",
    # Agent Training Bridge
    "AgentTrainingBridge",
    "BridgeConfig",
    # Hierarchical Executor
    "HierarchicalExecutor",
    "ExecutionPhase",
    "PhaseResult",
    "IterationRecord",
    "HierarchicalResult",
]
