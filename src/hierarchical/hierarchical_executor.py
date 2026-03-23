"""
Hierarchical Executor

Orchestrates the Manager → Coder → Reviewer flow for complex tasks.

This module implements the hierarchical execution pattern:
1. Manager decomposes tasks into subtasks
2. Coders implement subtasks (optionally in parallel)
3. Reviewers validate implementation
4. Iterate based on feedback until approved or max iterations reached
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import asyncio
import logging
import uuid

# Import from existing modules with fallbacks
try:
    from agents.base import AgentRole, BaseAgent, TaskSpec, TaskResult, SubTask
    from agents.communication import ReviewResult
    from hierarchical.agent_training_bridge import AgentTrainingBridge
    IMPORTS_AVAILABLE = True
except ImportError:
    try:
        from ..agents.base import AgentRole, BaseAgent, TaskSpec, TaskResult, SubTask
        from ..agents.communication import ReviewResult
        from .agent_training_bridge import AgentTrainingBridge
        IMPORTS_AVAILABLE = True
    except ImportError:
        IMPORTS_AVAILABLE = False
        AgentRole = None
        BaseAgent = None
        TaskSpec = None
        TaskResult = None
        SubTask = None
        ReviewResult = None
        AgentTrainingBridge = None

logger = logging.getLogger(__name__)


class ExecutionPhase(Enum):
    """Phases of hierarchical execution."""
    INITIALIZING = "initializing"
    DECOMPOSING = "decomposing"
    CODING = "coding"
    REVIEWING = "reviewing"
    ITERATING = "iterating"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class PhaseResult:
    """Result from a single execution phase."""
    phase: ExecutionPhase
    success: bool
    data: Any
    start_time: datetime
    end_time: datetime
    error: Optional[str] = None


@dataclass
class IterationRecord:
    """Record of a single review-implement iteration."""
    iteration: int
    review_result: Any  # ReviewResult
    feedback: List[str]
    changes_made: List[str]
    timestamp: datetime


@dataclass
class HierarchicalResult:
    """Result from hierarchical agent execution."""
    task_id: str
    success: bool
    final_result: TaskResult
    
    # Phase results
    decomposition: List[SubTask]
    code_changes: List[Any]  # List of CodeChange
    review_result: Optional[ReviewResult]
    
    # Iteration tracking
    iterations: int
    review_iterations: int
    
    # Metrics
    total_time_seconds: float
    agent_usage: Dict[str, int]  # agent_id -> call count
    token_usage: Dict[str, int]  # model -> token count
    
    # Training data
    traces: List[Any] = field(default_factory=list)


class HierarchicalExecutor:
    """
    Orchestrates the Manager → Coder → Reviewer flow.
    
    This class manages:
    - Task decomposition by manager
    - Parallel or sequential subtask execution by coders
    - Review and validation by reviewers
    - Iteration based on feedback
    - Conflict resolution between coders
    """
    
    def __init__(
        self,
        manager,  # ManagerAgent
        coder_pool: List,  # List[CoderAgent]
        reviewer_pool: List,  # List[ReviewerAgent]
        bridge: Optional[AgentTrainingBridge] = None,
        max_iterations: int = 5,
    ):
        """
        Initialize the Hierarchical Executor.
        
        Args:
            manager: Manager agent for task decomposition
            coder_pool: Pool of coder agents for implementation
            reviewer_pool: Pool of reviewer agents for validation
            bridge: Optional bridge for training integration
            max_iterations: Maximum review-implement iterations
        """
        self.manager = manager
        self.coder_pool = coder_pool
        self.reviewer_pool = reviewer_pool
        self.bridge = bridge
        self.max_iterations = max_iterations
        
        # State tracking
        self._iteration_history: List[IterationRecord] = []
        self._phase_timings: Dict[ExecutionPhase, float] = {}
        self._current_execution_id: Optional[str] = None
        
        logger.info(
            f"HierarchicalExecutor initialized with {len(coder_pool)} coders, "
            f"{len(reviewer_pool)} reviewers, max_iterations={max_iterations}"
        )
    
    async def execute(self, task: TaskSpec) -> HierarchicalResult:
        """
        Execute a task through the hierarchical flow.
        
        Args:
            task: Task specification to execute
            
        Returns:
            HierarchicalResult with full execution details
        """
        start_time = datetime.utcnow()
        self._current_execution_id = str(uuid.uuid4())
        
        try:
            # Initialize agents
            await self._initialize_agents()
            
            # Phase 1: Decomposition
            decomp_result = await self.run_decomposition_phase(task)
            if not decomp_result.success:
                return self._create_failed_result(task, start_time, "Decomposition failed")
            
            subtasks = decomp_result.data
            
            # Phase 2: Coding
            coding_result = await self.run_coding_phase(subtasks, parallel=True)
            if not coding_result.success:
                return self._create_failed_result(task, start_time, "Coding failed")
            
            code_changes = coding_result.data
            
            # Phase 3: Review
            review_result = await self.run_review_phase(code_changes)
            
            # Iteration loop
            iterations = 1
            review_iterations = 0
            
            while (
                review_result.success and
                review_result.data and
                getattr(review_result.data, 'verdict', 'approved') != 'approved' and
                iterations < self.max_iterations
            ):
                # Iterate based on feedback
                iteration_result = await self.iterate_on_feedback(
                    review_result.data, subtasks
                )
                
                if iteration_result.phase == ExecutionPhase.COMPLETED:
                    break
                
                # Re-run coding and review
                coding_result = await self.run_coding_phase(subtasks, parallel=True)
                code_changes.extend(coding_result.data)
                
                review_result = await self.run_review_phase(code_changes)
                
                iterations += 1
                review_iterations += 1
            
            # Create final result
            final_result = self._aggregate_final_result(task, code_changes)
            
            return HierarchicalResult(
                task_id=task.task_id,
                success=review_result.success and getattr(review_result.data, 'verdict', 'approved') == 'approved',
                final_result=final_result,
                decomposition=subtasks,
                code_changes=code_changes,
                review_result=review_result.data if review_result.success else None,
                iterations=iterations,
                review_iterations=review_iterations,
                total_time_seconds=(datetime.utcnow() - start_time).total_seconds(),
                agent_usage=self._get_agent_usage(),
                token_usage=self._get_token_usage(),
                traces=[],
            )
            
        except Exception as e:
            logger.error(f"Hierarchical execution failed: {e}", exc_info=True)
            return self._create_failed_result(task, start_time, str(e))
        
        finally:
            await self._shutdown_agents()
    
    async def run_decomposition_phase(self, task: TaskSpec) -> PhaseResult:
        """
        Run the decomposition phase where manager breaks down the task.
        
        Args:
            task: Task to decompose
            
        Returns:
            PhaseResult with subtasks
        """
        start_time = datetime.utcnow()
        
        try:
            subtasks = await self._decompose_via_manager(task)
            
            return PhaseResult(
                phase=ExecutionPhase.DECOMPOSING,
                success=True,
                data=subtasks,
                start_time=start_time,
                end_time=datetime.utcnow(),
            )
            
        except Exception as e:
            logger.error(f"Decomposition phase failed: {e}")
            return PhaseResult(
                phase=ExecutionPhase.FAILED,
                success=False,
                data=None,
                start_time=start_time,
                end_time=datetime.utcnow(),
                error=str(e),
            )
    
    async def run_coding_phase(
        self,
        subtasks: List[SubTask],
        parallel: bool = True
    ) -> PhaseResult:
        """
        Run the coding phase where coders implement subtasks.
        
        Args:
            subtasks: Subtasks to implement
            parallel: Whether to execute in parallel
            
        Returns:
            PhaseResult with code changes
        """
        start_time = datetime.utcnow()
        
        try:
            if not subtasks:
                return PhaseResult(
                    phase=ExecutionPhase.CODING,
                    success=True,
                    data=[],
                    start_time=start_time,
                    end_time=datetime.utcnow(),
                )
            
            code_changes = []
            
            if parallel and len(subtasks) > 1:
                # Parallel execution
                tasks = [
                    self._execute_subtask(subtask)
                    for subtask in subtasks
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for result in results:
                    if not isinstance(result, Exception):
                        code_changes.append(result)
            else:
                # Sequential execution
                for subtask in subtasks:
                    result = await self._execute_subtask(subtask)
                    code_changes.append(result)
            
            return PhaseResult(
                phase=ExecutionPhase.CODING,
                success=True,
                data=code_changes,
                start_time=start_time,
                end_time=datetime.utcnow(),
            )
            
        except Exception as e:
            logger.error(f"Coding phase failed: {e}")
            return PhaseResult(
                phase=ExecutionPhase.FAILED,
                success=False,
                data=[],
                start_time=start_time,
                end_time=datetime.utcnow(),
                error=str(e),
            )
    
    async def run_review_phase(self, changes: List) -> PhaseResult:
        """
        Run the review phase where reviewers validate the code.
        
        Args:
            changes: Code changes to review
            
        Returns:
            PhaseResult with review result
        """
        start_time = datetime.utcnow()
        
        try:
            if not changes:
                # No changes to review - approve
                mock_review = type('ReviewResult', (), {
                    'review_id': 'empty-review',
                    'task_id': self._current_execution_id or 'unknown',
                    'verdict': 'approved',
                    'findings': [],
                    'blocking_issues': [],
                })()
                
                return PhaseResult(
                    phase=ExecutionPhase.REVIEWING,
                    success=True,
                    data=mock_review,
                    start_time=start_time,
                    end_time=datetime.utcnow(),
                )
            
            review = await self._review_changes(changes)
            
            return PhaseResult(
                phase=ExecutionPhase.REVIEWING,
                success=True,
                data=review,
                start_time=start_time,
                end_time=datetime.utcnow(),
            )
            
        except Exception as e:
            logger.error(f"Review phase failed: {e}")
            return PhaseResult(
                phase=ExecutionPhase.FAILED,
                success=False,
                data=None,
                start_time=start_time,
                end_time=datetime.utcnow(),
                error=str(e),
            )
    
    async def iterate_on_feedback(
        self,
        review: ReviewResult,
        subtasks: List[SubTask]
    ) -> PhaseResult:
        """
        Iterate based on review feedback.
        
        Args:
            review: Review result with feedback
            subtasks: Subtasks to re-implement
            
        Returns:
            PhaseResult indicating iteration status
        """
        start_time = datetime.utcnow()
        
        # Check if approved
        if getattr(review, 'verdict', 'needs_changes') == 'approved':
            return PhaseResult(
                phase=ExecutionPhase.COMPLETED,
                success=True,
                data=None,
                start_time=start_time,
                end_time=datetime.utcnow(),
            )
        
        # Record iteration
        iteration_record = IterationRecord(
            iteration=len(self._iteration_history) + 1,
            review_result=review,
            feedback=getattr(review, 'blocking_issues', []),
            changes_made=[],
            timestamp=datetime.utcnow(),
        )
        self._iteration_history.append(iteration_record)
        
        return PhaseResult(
            phase=ExecutionPhase.ITERATING,
            success=True,
            data=review,
            start_time=start_time,
            end_time=datetime.utcnow(),
        )
    
    async def _initialize_agents(self) -> None:
        """Initialize all agents."""
        if hasattr(self.manager, 'initialize'):
            await self.manager.initialize()
        
        for coder in self.coder_pool:
            if hasattr(coder, 'initialize'):
                await coder.initialize()
        
        for reviewer in self.reviewer_pool:
            if hasattr(reviewer, 'initialize'):
                await reviewer.initialize()
    
    async def _shutdown_agents(self) -> None:
        """Shutdown all agents."""
        if hasattr(self.manager, 'shutdown'):
            await self.manager.shutdown()
        
        for coder in self.coder_pool:
            if hasattr(coder, 'shutdown'):
                await coder.shutdown()
        
        for reviewer in self.reviewer_pool:
            if hasattr(reviewer, 'shutdown'):
                await reviewer.shutdown()
    
    async def _decompose_via_manager(self, task: TaskSpec) -> List[SubTask]:
        """Decompose task using manager agent."""
        if hasattr(self.manager, 'decompose'):
            return await self.manager.decompose(task)
        
        # Fallback: create a single subtask
        if IMPORTS_AVAILABLE:
            return [SubTask(
                subtask_id=f"{task.task_id}-sub-0",
                name="Implement task",
                task_type=task.task_type,
                description=task.specification,
            )]
        
        # Mock subtask if imports not available
        return [type('SubTask', (), {
            'subtask_id': f"{task.task_id}-sub-0",
            'name': "Implement task",
            'task_type': task.task_type,
            'description': task.specification,
        })()]
    
    async def _execute_subtask(self, subtask: SubTask) -> Any:
        """Execute a single subtask using a coder."""
        coder = self._assign_coder(subtask)
        
        if self.bridge:
            task_spec = TaskSpec(
                task_id=subtask.subtask_id,
                task_type=getattr(subtask, 'task_type', 'implement'),
                specification=getattr(subtask, 'description', ''),
            ) if IMPORTS_AVAILABLE else type('TaskSpec', (), {
                'task_id': subtask.subtask_id,
                'task_type': getattr(subtask, 'task_type', 'implement'),
                'specification': getattr(subtask, 'description', ''),
            })()
            
            result = await self.bridge.wrap_agent_execution(coder, task_spec)
        else:
            if hasattr(coder, 'execute'):
                result = await coder.execute(subtask)
            else:
                result = type('CodeChange', (), {
                    'file': 'test.py',
                    'diff': '// implementation',
                })()
        
        return result
    
    def _assign_coder(self, subtask: SubTask) -> BaseAgent:
        """Assign a coder to a subtask."""
        if not self.coder_pool:
            raise ValueError("No coders available in pool")
        
        # Simple round-robin assignment
        idx = hash(subtask.subtask_id) % len(self.coder_pool)
        return self.coder_pool[idx]
    
    async def _review_changes(self, changes: List) -> ReviewResult:
        """Review code changes."""
        if not self.reviewer_pool:
            # No reviewer available - auto-approve
            return type('ReviewResult', (), {
                'review_id': 'auto-review',
                'task_id': self._current_execution_id or 'unknown',
                'verdict': 'approved',
                'findings': [],
                'blocking_issues': [],
            })()
        
        reviewer = self.reviewer_pool[0]
        
        if hasattr(reviewer, 'review'):
            return await reviewer.review(changes)
        
        # Fallback: auto-approve
        return type('ReviewResult', (), {
            'review_id': 'fallback-review',
            'task_id': self._current_execution_id or 'unknown',
            'verdict': 'approved',
            'findings': [],
            'blocking_issues': [],
        })()
    
    def _resolve_conflicts(self, changes: List) -> List:
        """Resolve conflicts between coders."""
        # Group changes by file
        file_changes = {}
        for change in changes:
            file_path = getattr(change, 'file', 'unknown')
            if file_path not in file_changes:
                file_changes[file_path] = []
            file_changes[file_path].append(change)
        
        # For now, keep only the first change per file
        # TODO: Implement proper merge logic
        resolved = []
        for file_path, file_change_list in file_changes.items():
            if file_change_list:
                resolved.append(file_change_list[0])
        
        return resolved
    
    def _handle_overlapping_changes(self, changes: List) -> List:
        """Handle overlapping changes between coders."""
        return self._resolve_conflicts(changes)
    
    def _can_merge(self, changes: List) -> bool:
        """Check if changes can be merged."""
        # Simple heuristic: if changes affect different line ranges, can merge
        if len(changes) <= 1:
            return True
        
        # Check for overlapping line ranges
        for i, change1 in enumerate(changes):
            for change2 in changes[i+1:]:
                lines1 = getattr(change1, 'lines', (0, 0))
                lines2 = getattr(change2, 'lines', (0, 0))
                
                if lines1 and lines2:
                    # Check for overlap
                    if not (lines1[1] < lines2[0] or lines2[1] < lines1[0]):
                        return False
        
        return True
    
    def _merge_changes(self, changes: List) -> Any:
        """Merge multiple changes."""
        # Simple merge: combine diffs
        combined_diff = '\n'.join(
            getattr(change, 'diff', '') for change in changes
        )
        
        return type('MergedChange', (), {
            'file': changes[0].file if changes else 'unknown',
            'diff': combined_diff,
        })()
    
    def get_iteration_history(self) -> List[IterationRecord]:
        """Get history of review iterations."""
        return self._iteration_history.copy()
    
    def get_phase_timings(self) -> Dict[ExecutionPhase, float]:
        """Get timing data for each phase."""
        return self._phase_timings.copy()
    
    def _create_failed_result(
        self,
        task: TaskSpec,
        start_time: datetime,
        error: str
    ) -> HierarchicalResult:
        """Create a failed HierarchicalResult."""
        # Create a failed TaskResult
        if IMPORTS_AVAILABLE:
            failed_result = TaskResult(
                task_id=task.task_id,
                status='failed',
                error=error,
            )
        else:
            failed_result = type('TaskResult', (), {
                'task_id': task.task_id,
                'status': 'failed',
                'error': error,
            })()
        
        return HierarchicalResult(
            task_id=task.task_id,
            success=False,
            final_result=failed_result,
            decomposition=[],
            code_changes=[],
            review_result=None,
            iterations=0,
            review_iterations=0,
            total_time_seconds=(datetime.utcnow() - start_time).total_seconds(),
            agent_usage={},
            token_usage={},
            traces=[],
        )
    
    def _aggregate_final_result(self, task: TaskSpec, changes: List) -> TaskResult:
        """Aggregate changes into final TaskResult."""
        files_modified = []
        for change in changes:
            if hasattr(change, 'files_modified'):
                files_modified.extend(change.files_modified)
            elif hasattr(change, 'file'):
                files_modified.append(change.file)
        
        if IMPORTS_AVAILABLE:
            return TaskResult(
                task_id=task.task_id,
                status='completed',
                files_modified=list(set(files_modified)),
            )
        
        return type('TaskResult', (), {
            'task_id': task.task_id,
            'status': 'completed',
            'files_modified': list(set(files_modified)),
        })()
    
    def _get_agent_usage(self) -> Dict[str, int]:
        """Get usage count per agent."""
        usage = {}
        
        if hasattr(self.manager, 'agent_id'):
            usage[self.manager.agent_id] = 1
        
        for coder in self.coder_pool:
            if hasattr(coder, 'agent_id'):
                usage[coder.agent_id] = usage.get(coder.agent_id, 0) + 1
        
        for reviewer in self.reviewer_pool:
            if hasattr(reviewer, 'agent_id'):
                usage[reviewer.agent_id] = usage.get(reviewer.agent_id, 0) + 1
        
        return usage
    
    def _get_token_usage(self) -> Dict[str, int]:
        """Get token usage per model."""
        # TODO: Implement actual token tracking
        return {}
