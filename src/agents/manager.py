"""
Manager Agent Implementation

The Manager Agent is the orchestrator in the hierarchical agent architecture.
It decomposes tasks, dispatches work to specialized agents, monitors progress,
and synthesizes results.

State Machine: INIT → DECOMPOSE → DISPATCH → MONITOR → SYNTHESIZE → COMPLETE

As specified in Section 2.1 of the Hierarchical Architecture Specification.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import logging
import uuid

from .base import BaseAgent, AgentRole, AgentState, SubTask, TaskSpec, TaskResult
from .states import StateMachine, ManagerState, MANAGER_TRANSITIONS
from .communication import (
    AgentMessage,
    MessageType,
    TaskAssignment,
    MessageRouter,
    ConflictReport,
    StatusUpdate,
    ErrorReport
)

logger = logging.getLogger(__name__)


@dataclass
class ProgressReport:
    """
    Progress report for monitoring active tasks.
    
    Attributes:
        timestamp: When the report was generated
        active_tasks: Currently active tasks
        completed_tasks: Completed tasks
        failed_tasks: Failed tasks
        pending_tasks: Tasks waiting to be dispatched
        overall_progress: Overall completion percentage
    """
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    active_tasks: List[str] = field(default_factory=list)
    completed_tasks: List[str] = field(default_factory=list)
    failed_tasks: List[str] = field(default_factory=list)
    pending_tasks: List[str] = field(default_factory=list)
    overall_progress: float = 0.0


@dataclass
class Resolution:
    """
    Resolution for a conflict between parallel workers.
    
    Attributes:
        conflict_id: ID of the conflict being resolved
        strategy: Resolution strategy used
        action: Action to take
        details: Additional resolution details
    """
    conflict_id: str
    strategy: str  # merge, prefer_first, prefer_second, custom
    action: str
    details: Dict[str, Any] = field(default_factory=dict)


class ManagerAgent(BaseAgent):
    """
    Manager Agent - Orchestrator in the hierarchical system.
    
    The Manager Agent is responsible for:
    - Task decomposition and prioritization
    - Work distribution to specialized agents (Coder, Reviewer, Tester)
    - Progress monitoring and convergence detection
    - Conflict resolution and synthesis
    - Quality gate enforcement
    
    State Machine:
        INIT → DECOMPOSE → DISPATCH → MONITOR → SYNTHESIZE → COMPLETE
    
    Example:
        >>> manager = ManagerAgent()
        >>> await manager.initialize()
        >>> result = await manager.execute(task_spec)
        >>> print(result.status)
        'completed'
    
    Attributes:
        state_machine: State machine managing manager state
        subtasks: List of decomposed subtasks
        active_workers: Currently active worker agents
        message_router: Router for inter-agent communication
    """
    
    def __init__(
        self,
        agent_id: str = None,
        mcp_config_path: str = "~/.config/autodev/mcp_config.json",
        repo_root: str = ".",
        max_concurrent_workers: int = 3,
        task_timeout_seconds: int = 300,
        llm_config: Optional[Any] = None
    ):
        super().__init__(
            agent_id=agent_id,
            role=AgentRole.MANAGER,
            mcp_config_path=mcp_config_path,
            repo_root=repo_root,
            llm_config=llm_config
        )
        
        # Initialize state machine
        self.state_machine = StateMachine(
            initial_state=ManagerState.INIT,
            valid_transitions=MANAGER_TRANSITIONS
        )
        
        # Task management
        self.subtasks: List[SubTask] = []
        self.active_workers: Dict[str, Any] = {}
        self.worker_results: Dict[str, TaskResult] = {}
        
        # Configuration
        self.max_concurrent_workers = max_concurrent_workers
        self.task_timeout_seconds = task_timeout_seconds
        
        # Communication
        self.message_router = MessageRouter()
        
        # Current task tracking
        self._current_task: Optional[TaskSpec] = None
        self._stall_detection_counter = 0
        self._max_no_progress_iterations = 3
    
    async def initialize(self) -> None:
        """
        Initialize the Manager Agent.
        
        - Connects to MCP servers
        - Initializes LLM client
        - Prepares for task execution
        """
        logger.info(f"Initializing Manager Agent {self.agent_id}")
        
        self.update_state(AgentState.INITIALIZING)
        
        # Initialize LLM client (Phase 2)
        await self._initialize_llm()
        
        # Initialize MCP client (Phase 2)
        await self._initialize_mcp()
        
        # Initialize tool executor (Phase 2)
        await self._initialize_tool_executor(max_iterations=25)
        
        self.update_state(AgentState.IDLE)
        logger.info("Manager Agent initialized successfully")
    
    async def shutdown(self) -> None:
        """
        Clean shutdown of the Manager Agent.
        
        - Cancels active tasks
        - Disconnects from MCP servers
        - Saves state
        """
        logger.info(f"Shutting down Manager Agent {self.agent_id}")
        
        # Cancel active workers
        for task_id, worker in self.active_workers.items():
            logger.info(f"Cancelling active task: {task_id}")
            # TODO: Implement worker cancellation
        
        # Disconnect MCP client (Phase 2)
        if self._mcp_client and hasattr(self._mcp_client, 'disconnect_all'):
            try:
                await self._mcp_client.disconnect_all()
            except Exception as e:
                logger.warning(f"Error disconnecting MCP client: {e}")
        
        # Log final usage stats
        stats = self.get_llm_usage_stats()
        if stats:
            logger.info(f"Final LLM usage stats: {stats}")
        
        self.update_state(AgentState.COMPLETED)
        logger.info("Manager Agent shutdown complete")
    
    async def execute(self, task: TaskSpec) -> TaskResult:
        """
        Execute a task using the hierarchical agent system.
        
        This is the main entry point for task execution. The manager
        orchestrates the full pipeline from decomposition to completion.
        
        Args:
            task: Task specification to execute
            
        Returns:
            TaskResult with the final outcome
        """
        logger.info(f"Executing task {task.task_id}: {task.task_type}")
        
        self._current_task = task
        result = TaskResult(task_id=task.task_id, status="running")
        
        try:
            # State: INIT
            await self._state_init(task)
            
            # State: DECOMPOSE
            subtasks = await self._state_decompose(task)
            self.subtasks = subtasks
            
            # State: DISPATCH
            await self._state_dispatch(subtasks)
            
            # State: MONITOR (loops until completion or stall)
            await self._state_monitor()
            
            # State: SYNTHESIZE
            final_output = await self._state_synthesize()
            
            # State: COMPLETE
            await self._state_complete()
            
            # Build result
            result.status = "completed"
            result.completed_at = datetime.now(timezone.utc)
            result.files_modified = final_output.get("files_modified", [])
            result.summary = final_output.get("summary", "Task completed successfully")
            result.result = final_output
            
        except Exception as e:
            logger.error(f"Task execution failed: {e}")
            result.status = "failed"
            result.error = str(e)
            self.update_state(AgentState.FAILED)
        
        return result
    
    # -------------------------------------------------------------------------
    # State Machine Handlers
    # -------------------------------------------------------------------------
    
    async def _state_init(self, task: TaskSpec) -> None:
        """
        INIT state: Load PRD, tracker, and context.
        
        Args:
            task: Task specification
        """
        self.state_machine.transition(ManagerState.DECOMPOSE, reason="Task loaded")
        logger.info(f"State: INIT - Loaded task {task.task_id}")
    
    async def _state_decompose(self, task: TaskSpec) -> List[SubTask]:
        """
        DECOMPOSE state: Analyze requirements and create subtasks.
        
        This method breaks down the main task into atomic, executable subtasks
        that can be assigned to worker agents.
        
        Args:
            task: Task specification to decompose
            
        Returns:
            List of subtasks
        """
        self.state_machine.transition(ManagerState.DISPATCH, reason="Task decomposed")
        logger.info(f"State: DECOMPOSE - Decomposing task {task.task_id}")
        
        # TODO: Implement actual task decomposition using LLM
        # This is a stub that creates a placeholder subtask
        
        subtasks = [
            SubTask(
                parent_task_id=task.task_id,
                name="Placeholder implementation task",
                description=task.specification,
                task_type=task.task_type,
                priority="high",
                assigned_to=AgentRole.CODER,
                context={
                    "target_files": task.target_files,
                    "constraints": task.constraints
                }
            )
        ]
        
        # Detect dependencies between subtasks
        subtasks = self._detect_dependencies(subtasks)
        
        logger.info(f"Created {len(subtasks)} subtasks")
        return subtasks
    
    async def _state_dispatch(self, subtasks: List[SubTask]) -> None:
        """
        DISPATCH state: Assign subtasks to workers.
        
        Prioritizes tasks by dependency order and dispatches to appropriate
        worker agents (Coder, Reviewer, Tester).
        
        Args:
            subtasks: List of subtasks to dispatch
        """
        self.state_machine.transition(ManagerState.MONITOR, reason="Tasks dispatched")
        logger.info(f"State: DISPATCH - Dispatching {len(subtasks)} subtasks")
        
        # Prioritize by dependencies
        prioritized = self._prioritize_tasks(subtasks)
        
        # Dispatch to workers
        for subtask in prioritized:
            assignment = TaskAssignment(
                task_id=subtask.subtask_id,
                task_type=subtask.task_type,
                priority=subtask.priority,
                specification=subtask.description,
                context=subtask.context,
                dependencies=subtask.dependencies,
                timeout_seconds=self.task_timeout_seconds
            )
            
            message = AgentMessage(
                sender=AgentRole.MANAGER,
                receiver=subtask.assigned_to,
                type=MessageType.TASK_ASSIGNMENT,
                payload=assignment.to_dict()
            )
            
            self.message_router.send(message)
            logger.info(f"Dispatched subtask {subtask.subtask_id} to {subtask.assigned_to.value}")
    
    async def _state_monitor(self) -> None:
        """
        MONITOR state: Track execution and handle failures.
        
        Loops until all tasks complete or a stall is detected.
        Handles failures and reassigns tasks as needed.
        """
        logger.info("State: MONITOR - Monitoring task execution")
        
        iteration = 0
        while not self._all_tasks_complete():
            iteration += 1
            
            # Check for stalls
            if self._detect_stall():
                logger.warning("Stall detected - no progress being made")
                self._handle_stall()
            
            # Process incoming messages
            await self._process_messages()
            
            # Brief pause to avoid busy waiting
            await asyncio.sleep(1)
            
            # Safety check for infinite loops
            if iteration > 1000:
                logger.error("Monitor loop exceeded maximum iterations")
                break
    
    async def _state_synthesize(self) -> Dict[str, Any]:
        """
        SYNTHESIZE state: Combine outputs and resolve conflicts.
        
        Collects results from all workers and combines them into
        a cohesive final output.
        
        Returns:
            Synthesized output dictionary
        """
        self.state_machine.transition(
            ManagerState.SYNTHESIZE,
            reason="All tasks completed"
        )
        logger.info("State: SYNTHESIZE - Combining worker outputs")
        
        # Check for conflicts
        conflicts = self._detect_conflicts()
        if conflicts:
            await self._resolve_conflicts(conflicts)
        
        # Synthesize final output
        # TODO: Implement actual synthesis logic
        
        return {
            "files_modified": [],
            "summary": "Task completed successfully",
            "details": {}
        }
    
    async def _state_complete(self) -> None:
        """
        COMPLETE state: Final state with cleanup.
        """
        self.state_machine.transition(
            ManagerState.COMPLETE,
            reason="Task fully completed"
        )
        logger.info("State: COMPLETE - Task execution finished")
    
    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------
    
    async def decompose_task_with_llm(self, prd: str, tracker: dict) -> List[SubTask]:
        """
        Break down PRD into atomic subtasks using LLM.
        
        Phase 2 implementation using the LLM client.
        
        Args:
            prd: Product Requirements Document text
            tracker: Project tracker data
            
        Returns:
            List of decomposed subtasks
        """
        if not self._llm_client:
            logger.warning("LLM client not available, using fallback decomposition")
            return self._fallback_decompose(prd, tracker)
        
        prompt = f"""Analyze the following task specification and break it down into atomic subtasks.

TASK SPECIFICATION:
{prd}

PROJECT CONTEXT:
{tracker if tracker else 'No additional context provided'}

Create a list of subtasks that:
1. Are atomic and independently executable
2. Have clear dependencies on other subtasks (if any)
3. Can be assigned to appropriate worker types (coder, reviewer, tester)
4. Are prioritized by importance

For each subtask, provide:
- name: Short descriptive name
- description: Detailed description of what needs to be done
- task_type: Type of work (implement, review, test, refactor, debug)
- priority: critical, high, medium, or low
- assigned_to: coder, reviewer, or tester
- dependencies: List of other subtask names this depends on (if any)

Format your response as a JSON list of subtask objects."""
        
        try:
            response = await self._call_llm(
                prompt=prompt,
                use_tools=False  # Don't use tools for decomposition
            )
            
            # Parse the response to extract subtasks
            subtasks = self._parse_decomposition_response(response, prd)
            return subtasks
            
        except Exception as e:
            logger.error(f"LLM decomposition failed: {e}")
            return self._fallback_decompose(prd, tracker)
    
    def _parse_decomposition_response(self, response: str, prd: str) -> List[SubTask]:
        """
        Parse LLM response into SubTask objects.
        
        Args:
            response: LLM response text
            prd: Original PRD text
            
        Returns:
            List of SubTask objects
        """
        import json
        import re
        
        subtasks = []
        
        # Try to extract JSON from the response
        try:
            # Look for JSON array in the response
            json_match = re.search(r'\[\s*\{.*\}\s*\]', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                
                # Map string roles to AgentRole
                role_map = {
                    "coder": AgentRole.CODER,
                    "reviewer": AgentRole.REVIEWER,
                    "tester": AgentRole.TESTER,
                }
                
                for item in data:
                    assigned_str = item.get("assigned_to", "coder").lower()
                    subtask = SubTask(
                        name=item.get("name", "Unnamed task"),
                        description=item.get("description", ""),
                        task_type=item.get("task_type", "implement"),
                        priority=item.get("priority", "medium"),
                        assigned_to=role_map.get(assigned_str, AgentRole.CODER),
                        context={
                            "prd_excerpt": prd[:500],
                            "dependencies": item.get("dependencies", [])
                        }
                    )
                    subtasks.append(subtask)
                    
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to parse LLM response as JSON: {e}")
        
        return subtasks if subtasks else self._fallback_decompose(prd, {})
    
    def _fallback_decompose(self, prd: str, tracker: dict) -> List[SubTask]:
        """
        Fallback decomposition when LLM is not available.
        
        Args:
            prd: Product Requirements Document text
            tracker: Project tracker data
            
        Returns:
            List of basic subtasks
        """
        return [
            SubTask(
                name="Implement main task",
                description=prd,
                task_type="implement",
                priority="high",
                assigned_to=AgentRole.CODER,
                context={"tracker": tracker}
            )
        ]
    
    def decompose_task(self, prd: str, tracker: dict) -> List[SubTask]:
        """
        Break down PRD into atomic subtasks.
        
        Note: This is a sync wrapper. For LLM-based decomposition,
        use decompose_task_with_llm instead.
        
        Args:
            prd: Product Requirements Document text
            tracker: Project tracker data
            
        Returns:
            List of decomposed subtasks
        """
        return self._fallback_decompose(prd, tracker)
    
    def prioritize_tasks(self, subtasks: List[SubTask]) -> List[SubTask]:
        """
        Order subtasks by dependency and priority.
        
        Args:
            subtasks: List of subtasks to prioritize
            
        Returns:
            Prioritized list of subtasks
        """
        return self._prioritize_tasks(subtasks)
    
    def _prioritize_tasks(self, subtasks: List[SubTask]) -> List[SubTask]:
        """Internal prioritization logic."""
        # Sort by priority and dependencies
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        return sorted(
            subtasks,
            key=lambda t: (len(t.dependencies), priority_order.get(t.priority, 99))
        )
    
    def dispatch_to_worker(self, subtask: SubTask, worker_type: AgentRole) -> str:
        """
        Assign subtask to appropriate worker agent.
        
        Args:
            subtask: Subtask to assign
            worker_type: Type of worker to assign to
            
        Returns:
            Assignment ID
        """
        return subtask.subtask_id
    
    def monitor_progress(self, active_tasks: List[str]) -> ProgressReport:
        """
        Track execution status across workers.
        
        Args:
            active_tasks: List of active task IDs
            
        Returns:
            Progress report
        """
        return ProgressReport(
            active_tasks=active_tasks,
            completed_tasks=list(self.worker_results.keys())
        )
    
    def resolve_conflicts(self, conflicting_changes: List[ConflictReport]) -> Resolution:
        """
        Handle overlapping modifications from parallel workers.
        
        Args:
            conflicting_changes: List of conflict reports
            
        Returns:
            Resolution for the conflict
        """
        # TODO: Implement conflict resolution logic
        return Resolution(
            conflict_id=conflicting_changes[0].conflict_id if conflicting_changes else "",
            strategy="merge",
            action="Automatic merge attempted"
        )
    
    def synthesize_results(self, worker_outputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Combine worker outputs into cohesive result.
        
        Args:
            worker_outputs: Dictionary of worker outputs
            
        Returns:
            Synthesized final output
        """
        return {
            "files_modified": [],
            "summary": "Results synthesized",
            "outputs": worker_outputs
        }
    
    def _detect_dependencies(self, subtasks: List[SubTask]) -> List[SubTask]:
        """Detect dependencies between subtasks."""
        # TODO: Implement dependency detection
        return subtasks
    
    def _all_tasks_complete(self) -> bool:
        """Check if all tasks are complete."""
        # TODO: Implement actual completion check
        return len(self.worker_results) >= len(self.subtasks)
    
    def _detect_stall(self) -> bool:
        """Detect if execution has stalled."""
        # TODO: Implement stall detection
        self._stall_detection_counter += 1
        return self._stall_detection_counter >= self._max_no_progress_iterations
    
    def _handle_stall(self) -> None:
        """Handle a detected stall."""
        logger.warning("Handling stall - may need to reassign tasks")
        self._stall_detection_counter = 0
    
    def _detect_conflicts(self) -> List[ConflictReport]:
        """Detect conflicts between worker outputs."""
        # TODO: Implement conflict detection
        return []
    
    async def _resolve_conflicts(self, conflicts: List[ConflictReport]) -> None:
        """Resolve detected conflicts."""
        for conflict in conflicts:
            resolution = self.resolve_conflicts([conflict])
            logger.info(f"Resolved conflict {conflict.conflict_id}: {resolution.action}")
    
    async def _process_messages(self) -> None:
        """Process incoming messages from workers."""
        message = self.message_router.receive(AgentRole.MANAGER)
        while message:
            await self._handle_message(message)
            message = self.message_router.receive(AgentRole.MANAGER)
    
    async def _handle_message(self, message: AgentMessage) -> None:
        """Handle an incoming message."""
        if message.type == MessageType.TASK_COMPLETED:
            logger.info(f"Task completed: {message.payload}")
            self._stall_detection_counter = 0
        elif message.type == MessageType.ERROR_REPORT:
            logger.error(f"Error from worker: {message.payload}")
        elif message.type == MessageType.STATUS_UPDATE:
            logger.debug(f"Status update: {message.payload}")
