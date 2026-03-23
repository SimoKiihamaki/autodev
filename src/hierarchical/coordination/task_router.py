"""
Task Router for Hierarchical Agents

Provides dynamic task routing and agent assignment based on task
requirements, agent capabilities, and current workload.

This module implements:
- Task analysis: Understand task requirements
- Agent matching: Match tasks to capable agents
- Load balancing: Distribute work evenly
- Priority scheduling: Handle urgent tasks first

Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │                     Task Router                             │
    ├─────────────────────────────────────────────────────────────┤
    │  Incoming Task → Requirement Analysis → Agent Matching →    │
    │                 → Load Balancing → Assignment Output        │
    │                                                              │
    │  Agent Registry: [Manager, Coder_1, Coder_2, Reviewer]      │
    └─────────────────────────────────────────────────────────────┘

Usage:
    from hierarchical.coordination.task_router import TaskRouter, RoutingConfig
    
    router = TaskRouter()
    router.register_agent(coder_agent)
    assignment = await router.route_task(task_spec)
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set
import logging
import uuid

from ..hermes_integration import TaskPriority, TaskType
from ...agents.base import BaseAgent, AgentRole, AgentState, TaskSpec

logger = logging.getLogger(__name__)


class RoutingStrategy(Enum):
    """Strategies for task routing."""
    CAPABILITY_FIRST = "capability_first"  # Best capability match
    LOAD_BALANCED = "load_balanced"        # Even workload distribution
    PRIORITY_FIRST = "priority_first"      # Priority-based assignment
    ROUND_ROBIN = "round_robin"           # Simple round-robin
    SPECIALIZED = "specialized"           # Domain-specific matching


@dataclass
class AgentCapability:
    """
    Describes an agent's capabilities for routing.
    
    Attributes:
        agent_id: Agent identifier
        role: Agent role
        specializations: Areas of expertise
        languages: Programming languages known
        frameworks: Frameworks known
        max_concurrent: Maximum concurrent tasks
        current_load: Current task load
        success_rate: Historical success rate
        avg_completion_time: Average task completion time
    """
    agent_id: str = ""
    role: AgentRole = AgentRole.CODER
    specializations: Set[str] = field(default_factory=set)
    languages: Set[str] = field(default_factory=set)
    frameworks: Set[str] = field(default_factory=set)
    max_concurrent: int = 3
    current_load: int = 0
    success_rate: float = 0.8
    avg_completion_time: float = 300.0  # seconds

    @property
    def available_capacity(self) -> int:
        """Calculate available capacity."""
        return max(0, self.max_concurrent - self.current_load)

    @property
    def is_available(self) -> bool:
        """Check if agent can accept tasks."""
        return self.available_capacity > 0


@dataclass
class RoutingConfig:
    """
    Configuration for Task Router.
    
    Attributes:
        strategy: Default routing strategy
        max_retries: Maximum assignment retries
        retry_delay_seconds: Delay between retries
        balance_threshold: Load imbalance threshold
        capability_weight: Weight for capability matching
        load_weight: Weight for load balancing
        success_weight: Weight for historical success
    """
    strategy: RoutingStrategy = RoutingStrategy.LOAD_BALANCED
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    balance_threshold: float = 0.3
    capability_weight: float = 0.5
    load_weight: float = 0.3
    success_weight: float = 0.2


@dataclass
class AgentAssignment:
    """
    Result of task routing - agent assignment.
    
    Attributes:
        assignment_id: Unique identifier
        task_id: Assigned task ID
        agent_id: Assigned agent ID
        agent_role: Role of assigned agent
        strategy_used: Routing strategy used
        score: Assignment quality score
        rationale: Reasoning for assignment
        estimated_start: Estimated start time
        estimated_duration: Estimated completion time
        created_at: Assignment creation timestamp
    """
    assignment_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str = ""
    agent_id: str = ""
    agent_role: AgentRole = AgentRole.CODER
    strategy_used: RoutingStrategy = RoutingStrategy.LOAD_BALANCED
    score: float = 0.0
    rationale: str = ""
    estimated_start: Optional[datetime] = None
    estimated_duration: float = 300.0
    created_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def estimated_completion(self) -> Optional[datetime]:
        """Calculate estimated completion time."""
        if self.estimated_start:
            return datetime.fromtimestamp(
                self.estimated_start.timestamp() + self.estimated_duration
            )
        return None


class TaskRouter:
    """
    Dynamic task router for hierarchical agent coordination.
    
    This class provides:
    - Agent registration and capability tracking
    - Task analysis and requirement extraction
    - Intelligent task-to-agent matching
    - Load balancing and priority scheduling
    
    Example:
        >>> router = TaskRouter()
        >>> router.register_agent(coder_agent)
        >>> assignment = await router.route_task(task_spec)
        >>> print(f"Task assigned to {assignment.agent_id}")
    """
    
    def __init__(self, config: Optional[RoutingConfig] = None):
        """
        Initialize Task Router.
        
        Args:
            config: Routing configuration
        """
        self.config = config or RoutingConfig()
        self._agents: Dict[str, AgentCapability] = {}
        self._assignments: Dict[str, AgentAssignment] = {}
        self._task_queue: List[TaskSpec] = []
        self._round_robin_index: int = 0
        
        logger.info(f"TaskRouter initialized with strategy {self.config.strategy.value}")

    def register_agent(
        self,
        agent: BaseAgent,
        capabilities: Optional[AgentCapability] = None,
    ) -> None:
        """
        Register an agent with the router.
        
        Args:
            agent: Agent instance to register
            capabilities: Optional capability specification
        """
        if capabilities is None:
            capabilities = AgentCapability(
                agent_id=agent.agent_id,
                role=agent.role,
            )
        
        self._agents[agent.agent_id] = capabilities
        logger.info(f"Registered agent {agent.agent_id} with role {agent.role.value}")

    def unregister_agent(self, agent_id: str) -> bool:
        """
        Unregister an agent from the router.
        
        Args:
            agent_id: ID of agent to unregister
            
        Returns:
            True if agent was removed, False if not found
        """
        if agent_id in self._agents:
            del self._agents[agent_id]
            logger.info(f"Unregistered agent {agent_id}")
            return True
        return False

    def update_agent_load(self, agent_id: str, delta: int) -> None:
        """
        Update an agent's current load.
        
        Args:
            agent_id: Agent ID
            delta: Load change (+1 for new task, -1 for completed)
        """
        if agent_id in self._agents:
            self._agents[agent_id].current_load += delta
            self._agents[agent_id].current_load = max(
                0, self._agents[agent_id].current_load
            )

    async def route_task(
        self,
        task_spec: TaskSpec,
        required_role: Optional[AgentRole] = None,
        strategy: Optional[RoutingStrategy] = None,
    ) -> Optional[AgentAssignment]:
        """
        Route a task to the most appropriate agent.
        
        Args:
            task_spec: Task specification
            required_role: Optional required agent role
            strategy: Optional routing strategy override
            
        Returns:
            AgentAssignment if successful, None if no agent available
        """
        strategy = strategy or self.config.strategy
        
        # Analyze task requirements
        requirements = self._analyze_task(task_spec)
        
        # Get candidates
        candidates = self._get_candidates(required_role or AgentRole.CODER)
        
        if not candidates:
            logger.warning(f"No available agents for task {task_spec.task_id}")
            return None
        
        # Score and rank candidates
        scored = self._score_candidates(candidates, requirements, task_spec)
        
        # Select best candidate based on strategy
        selected = self._select_agent(scored, strategy)
        
        if selected is None:
            return None
        
        # Create assignment
        assignment = AgentAssignment(
            task_id=task_spec.task_id,
            agent_id=selected.agent_id,
            agent_role=selected.role,
            strategy_used=strategy,
            score=scored[selected.agent_id],
            rationale=self._generate_rationale(selected, requirements, strategy),
            estimated_start=datetime.utcnow(),
            estimated_duration=selected.avg_completion_time,
        )
        
        self._assignments[assignment.assignment_id] = assignment
        self.update_agent_load(selected.agent_id, +1)
        
        logger.info(
            f"Routed task {task_spec.task_id} to agent {selected.agent_id} "
            f"(score: {assignment.score:.2f})"
        )
        
        return assignment

    async def route_batch(
        self,
        tasks: List[TaskSpec],
        strategy: Optional[RoutingStrategy] = None,
    ) -> List[AgentAssignment]:
        """
        Route multiple tasks with coordination.
        
        Args:
            tasks: List of task specifications
            strategy: Optional routing strategy
            
        Returns:
            List of assignments
        """
        assignments = []
        
        # Sort by priority if using priority strategy
        if strategy == RoutingStrategy.PRIORITY_FIRST:
            tasks = sorted(
                tasks,
                key=lambda t: t.constraints.get("priority", "normal"),
                reverse=True
            )
        
        for task in tasks:
            assignment = await self.route_task(task, strategy=strategy)
            if assignment:
                assignments.append(assignment)
        
        return assignments

    def _analyze_task(self, task_spec: TaskSpec) -> Dict[str, Any]:
        """
        Analyze task to extract requirements.
        
        Args:
            task_spec: Task specification
            
        Returns:
            Dictionary of requirements
        """
        requirements = {
            "task_type": task_spec.task_type,
            "languages": set(),
            "frameworks": set(),
            "domains": set(),
            "complexity": "medium",
            "priority": task_spec.constraints.get("priority", "normal"),
        }
        
        # Extract from target files
        for file_path in task_spec.target_files:
            if file_path.endswith(".py"):
                requirements["languages"].add("python")
            elif file_path.endswith(".js") or file_path.endswith(".ts"):
                requirements["languages"].add("javascript")
            elif file_path.endswith(".go"):
                requirements["languages"].add("go")
            elif file_path.endswith(".rs"):
                requirements["languages"].add("rust")
        
        # Extract from specification text
        spec_lower = task_spec.specification.lower()
        
        # Check for frameworks
        framework_keywords = {
            "django": "django",
            "flask": "flask",
            "fastapi": "fastapi",
            "react": "react",
            "vue": "vue",
            "pytest": "pytest",
            "sqlalchemy": "sqlalchemy",
        }
        
        for keyword, framework in framework_keywords.items():
            if keyword in spec_lower:
                requirements["frameworks"].add(framework)
        
        # Estimate complexity
        complexity_indicators = [
            ("simple", "low"),
            ("basic", "low"),
            ("complex", "high"),
            ("advanced", "high"),
            ("refactor", "high"),
            ("migration", "high"),
        ]
        
        for keyword, level in complexity_indicators:
            if keyword in spec_lower:
                requirements["complexity"] = level
                break
        
        return requirements

    def _get_candidates(
        self,
        required_role: AgentRole,
    ) -> List[AgentCapability]:
        """
        Get available agents matching role requirement.
        
        Args:
            required_role: Required agent role
            
        Returns:
            List of available agent capabilities
        """
        candidates = []
        
        for capability in self._agents.values():
            if capability.role == required_role and capability.is_available:
                candidates.append(capability)
        
        return candidates

    def _score_candidates(
        self,
        candidates: List[AgentCapability],
        requirements: Dict[str, Any],
        task_spec: TaskSpec,
    ) -> Dict[str, float]:
        """
        Score candidates for task assignment.
        
        Args:
            candidates: Available candidates
            requirements: Task requirements
            task_spec: Task specification
            
        Returns:
            Dictionary of agent_id -> score
        """
        scores = {}
        
        for candidate in candidates:
            score = 0.0
            
            # Capability match
            capability_score = self._calculate_capability_score(
                candidate, requirements
            )
            score += capability_score * self.config.capability_weight
            
            # Load balance
            load_score = candidate.available_capacity / candidate.max_concurrent
            score += load_score * self.config.load_weight
            
            # Historical success
            score += candidate.success_rate * self.config.success_weight
            
            scores[candidate.agent_id] = score
        
        return scores

    def _calculate_capability_score(
        self,
        candidate: AgentCapability,
        requirements: Dict[str, Any],
    ) -> float:
        """
        Calculate capability match score.
        
        Args:
            candidate: Agent capability
            requirements: Task requirements
            
        Returns:
            Capability score (0.0 to 1.0)
        """
        score = 0.0
        
        # Language match
        required_langs = requirements.get("languages", set())
        if required_langs:
            lang_overlap = len(candidate.languages & required_langs)
            score += 0.4 * (lang_overlap / len(required_langs))
        else:
            score += 0.2  # Partial score if no language requirement
        
        # Framework match
        required_frameworks = requirements.get("frameworks", set())
        if required_frameworks:
            fw_overlap = len(candidate.frameworks & required_frameworks)
            score += 0.3 * (fw_overlap / len(required_frameworks))
        else:
            score += 0.15
        
        # Specialization match
        required_domains = requirements.get("domains", set())
        if required_domains:
            domain_overlap = len(candidate.specializations & required_domains)
            score += 0.3 * (domain_overlap / len(required_domains))
        else:
            score += 0.15
        
        return min(score, 1.0)

    def _select_agent(
        self,
        scored_candidates: Dict[str, float],
        strategy: RoutingStrategy,
    ) -> Optional[AgentCapability]:
        """
        Select agent based on strategy.
        
        Args:
            scored_candidates: Scored candidates
            strategy: Selection strategy
            
        Returns:
            Selected agent capability or None
        """
        if not scored_candidates:
            return None
        
        if strategy == RoutingStrategy.ROUND_ROBIN:
            # Round-robin selection
            agent_ids = list(self._agents.keys())
            if agent_ids:
                self._round_robin_index = (
                    self._round_robin_index + 1
                ) % len(agent_ids)
                selected_id = agent_ids[self._round_robin_index]
                return self._agents.get(selected_id)
        
        # Default: highest score
        best_id = max(scored_candidates.keys(), key=lambda x: scored_candidates[x])
        return self._agents.get(best_id)

    def _generate_rationale(
        self,
        selected: AgentCapability,
        requirements: Dict[str, Any],
        strategy: RoutingStrategy,
    ) -> str:
        """
        Generate human-readable rationale for assignment.
        
        Args:
            selected: Selected agent
            requirements: Task requirements
            strategy: Strategy used
            
        Returns:
            Rationale string
        """
        parts = []
        
        parts.append(f"Strategy: {strategy.value}")
        
        if selected.languages & requirements.get("languages", set()):
            parts.append(f"Language match: {selected.languages & requirements['languages']}")
        
        if selected.frameworks & requirements.get("frameworks", set()):
            parts.append(f"Framework match: {selected.frameworks & requirements['frameworks']}")
        
        parts.append(f"Available capacity: {selected.available_capacity}")
        parts.append(f"Success rate: {selected.success_rate:.1%}")
        
        return " | ".join(parts)

    def get_assignment(self, assignment_id: str) -> Optional[AgentAssignment]:
        """
        Get an assignment by ID.
        
        Args:
            assignment_id: Assignment ID
            
        Returns:
            AgentAssignment if found, None otherwise
        """
        return self._assignments.get(assignment_id)

    def complete_assignment(self, assignment_id: str) -> bool:
        """
        Mark an assignment as complete and update agent load.
        
        Args:
            assignment_id: Assignment ID
            
        Returns:
            True if successful, False if not found
        """
        assignment = self._assignments.get(assignment_id)
        if assignment:
            self.update_agent_load(assignment.agent_id, -1)
            logger.info(f"Completed assignment {assignment_id}")
            return True
        return False

    def get_agent_stats(self) -> Dict[str, Any]:
        """
        Get statistics about registered agents.
        
        Returns:
            Dictionary of agent statistics
        """
        total_agents = len(self._agents)
        available_agents = sum(1 for a in self._agents.values() if a.is_available)
        total_capacity = sum(a.available_capacity for a in self._agents.values())
        
        by_role = {}
        for agent in self._agents.values():
            role_name = agent.role.value
            by_role[role_name] = by_role.get(role_name, 0) + 1
        
        return {
            "total_agents": total_agents,
            "available_agents": available_agents,
            "total_capacity": total_capacity,
            "active_assignments": len(self._assignments),
            "by_role": by_role,
        }
