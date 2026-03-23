"""
Hierarchical Agent Coordination System

Provides task routing and conflict resolution for multi-agent coordination.

This submodule enables:
- Task Router: Dynamic agent assignment based on task requirements
- Conflict Resolver: Multi-agent merge strategies and conflict handling

Usage:
    from hierarchical.coordination import TaskRouter, ConflictResolver
    
    router = TaskRouter()
    assignment = router.route_task(task_spec, available_agents)
    
    resolver = ConflictResolver()
    resolved = resolver.resolve_conflicts(conflicting_changes)
"""

from .task_router import (
    TaskRouter,
    RoutingConfig,
    AgentAssignment,
    RoutingStrategy,
)
from .conflict_resolver import (
    ConflictResolver,
    ResolutionConfig,
    ConflictInfo,
    ResolutionStrategy,
)

__all__ = [
    # Task Routing
    "TaskRouter",
    "RoutingConfig",
    "AgentAssignment",
    "RoutingStrategy",
    # Conflict Resolution
    "ConflictResolver",
    "ResolutionConfig",
    "ConflictInfo",
    "ResolutionStrategy",
]
