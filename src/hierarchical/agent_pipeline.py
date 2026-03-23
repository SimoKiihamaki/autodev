"""
Agent Pipeline Integration

Connects the hierarchical agent system (Manager-Coder-Reviewer) to the
Training Orchestrator for continuous learning and improvement.

This module bridges:
- Agent execution traces → Training data collection
- Model improvements → Agent capability upgrades
- Performance metrics → Reward signals

Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │                     Agent Pipeline                          │
    ├─────────────────────────────────────────────────────────────┤
    │  Task Input → Manager (Plan) → Coder (Implement) →          │
    │              → Reviewer (Validate) → Result Output          │
    │                         ↓                                   │
    │              Training Orchestrator (Learn)                  │
    └─────────────────────────────────────────────────────────────┘

Usage:
    from hierarchical.agent_pipeline import AgentPipeline, PipelineConfig
    
    config = PipelineConfig(enable_learning=True)
    pipeline = AgentPipeline(config)
    result = await pipeline.execute(task_spec)
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Callable, Awaitable
import asyncio
import logging
import uuid

# Import from existing agent framework
from ..agents.base import (
    BaseAgent,
    AgentRole,
    AgentState,
    TaskSpec,
    TaskResult,
    SubTask,
)
from ..agents.manager import ManagerAgent
from ..agents.coder import CoderAgent
from ..agents.reviewer import ReviewerAgent
from ..agents.communication import AgentMessage, MessageType, MessageRouter

# Import from training module
from ..training.orchestrator import TrainingOrchestrator
from ..training.data_collector import DataCollector

logger = logging.getLogger(__name__)


class PipelineState(Enum):
    """Pipeline execution states."""
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    REVIEWING = "reviewing"
    LEARNING = "learning"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class PipelineConfig:
    """
    Configuration for the Agent Pipeline.
    
    Attributes:
        enable_learning: Whether to collect traces for training
        enable_review: Whether to run reviewer agent
        max_iterations: Maximum planning-implementation cycles
        timeout_seconds: Maximum pipeline execution time
        collect_traces: Whether to collect execution traces
        trace_output_dir: Directory for trace storage
        parallel_execution: Enable parallel subtask execution
    """
    enable_learning: bool = True
    enable_review: bool = True
    max_iterations: int = 3
    timeout_seconds: int = 1800  # 30 minutes
    collect_traces: bool = True
    trace_output_dir: str = "./traces"
    parallel_execution: bool = False
    llm_config: Optional[Dict[str, Any]] = None
    mcp_config: Optional[Dict[str, Any]] = None


@dataclass
class PipelineResult:
    """
    Result from pipeline execution.
    
    Attributes:
        pipeline_id: Unique identifier for this pipeline run
        task_spec: Original task specification
        state: Final pipeline state
        manager_plan: Plan created by manager
        coder_results: Results from coder agents
        review_result: Review result from reviewer
        final_result: Aggregated final result
        traces: Collected execution traces
        metrics: Performance metrics
        started_at: Pipeline start timestamp
        completed_at: Pipeline completion timestamp
        error: Error message if failed
    """
    pipeline_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_spec: Optional[TaskSpec] = None
    state: PipelineState = PipelineState.IDLE
    manager_plan: Optional[Dict[str, Any]] = None
    coder_results: List[TaskResult] = field(default_factory=list)
    review_result: Optional[Dict[str, Any]] = None
    final_result: Optional[TaskResult] = None
    traces: List[Dict[str, Any]] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        """Check if pipeline completed successfully."""
        return self.state == PipelineState.COMPLETED and self.error is None

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate pipeline duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


class AgentPipeline:
    """
    Main pipeline for hierarchical agent execution with training integration.
    
    This class orchestrates the Manager → Coder → Reviewer flow and connects
    execution traces to the training orchestrator for continuous learning.
    
    Example:
        >>> config = PipelineConfig(enable_learning=True)
        >>> pipeline = AgentPipeline(config)
        >>> result = await pipeline.execute(task_spec)
        >>> if result.success:
        ...     print(f"Completed in {result.duration_seconds:.1f}s")
    """
    
    def __init__(
        self,
        config: Optional[PipelineConfig] = None,
        training_orchestrator: Optional[TrainingOrchestrator] = None,
        data_collector: Optional[DataCollector] = None,
    ):
        """
        Initialize the Agent Pipeline.
        
        Args:
            config: Pipeline configuration
            training_orchestrator: Optional training orchestrator for learning
            data_collector: Optional data collector for trace gathering
        """
        self.config = config or PipelineConfig()
        self.training_orchestrator = training_orchestrator
        self.data_collector = data_collector
        self.state = PipelineState.IDLE
        self._current_result: Optional[PipelineResult] = None
        
        # Initialize agents lazily
        self._manager: Optional[ManagerAgent] = None
        self._coders: List[CoderAgent] = []
        self._reviewer: Optional[ReviewerAgent] = None
        self._message_router: Optional[MessageRouter] = None
        
        logger.info(f"AgentPipeline initialized with config: {self.config}")

    async def execute(self, task_spec: TaskSpec) -> PipelineResult:
        """
        Execute a task through the hierarchical agent pipeline.
        
        Flow:
        1. Manager analyzes task and creates implementation plan
        2. Coder(s) implement the planned subtasks
        3. Reviewer validates the implementation
        4. (Optional) Training orchestrator learns from execution
        
        Args:
            task_spec: Task specification to execute
            
        Returns:
            PipelineResult with execution details and outcomes
        """
        result = PipelineResult(
            task_spec=task_spec,
            started_at=datetime.utcnow()
        )
        self._current_result = result
        
        try:
            # Phase 1: Planning
            result.state = PipelineState.PLANNING
            plan = await self._plan(task_spec)
            result.manager_plan = plan
            
            # Phase 2: Execution
            result.state = PipelineState.EXECUTING
            coder_results = await self._execute_plan(plan, task_spec)
            result.coder_results = coder_results
            
            # Phase 3: Review
            if self.config.enable_review:
                result.state = PipelineState.REVIEWING
                review = await self._review(task_spec, coder_results)
                result.review_result = review
                
                # Iterate if review failed and iterations remain
                iteration = 1
                while not review.get("approved", False) and iteration < self.config.max_iterations:
                    iteration += 1
                    logger.info(f"Review not approved, iteration {iteration}")
                    coder_results = await self._execute_plan(plan, task_spec, review)
                    result.coder_results.extend(coder_results)
                    review = await self._review(task_spec, coder_results)
            
            # Phase 4: Learning
            if self.config.enable_learning and self.training_orchestrator:
                result.state = PipelineState.LEARNING
                await self._learn(result)
            
            result.state = PipelineState.COMPLETED
            result.final_result = self._aggregate_results(task_spec, result)
            
        except Exception as e:
            result.state = PipelineState.FAILED
            result.error = str(e)
            logger.error(f"Pipeline execution failed: {e}", exc_info=True)
        
        finally:
            result.completed_at = datetime.utcnow()
            self._current_result = None
            self.state = PipelineState.IDLE
        
        return result

    async def _plan(self, task_spec: TaskSpec) -> Dict[str, Any]:
        """
        Have the manager agent create an implementation plan.
        
        Args:
            task_spec: Task specification
            
        Returns:
            Implementation plan with subtasks
        """
        manager = await self._get_manager()
        plan = await manager.plan(task_spec)
        return plan

    async def _execute_plan(
        self,
        plan: Dict[str, Any],
        task_spec: TaskSpec,
        review_feedback: Optional[Dict[str, Any]] = None
    ) -> List[TaskResult]:
        """
        Execute the implementation plan using coder agents.
        
        Args:
            plan: Implementation plan from manager
            task_spec: Original task specification
            review_feedback: Optional feedback from previous review
            
        Returns:
            List of results from coder execution
        """
        subtasks = plan.get("subtasks", [])
        results = []
        
        if self.config.parallel_execution and len(subtasks) > 1:
            # Parallel execution
            tasks = [
                self._execute_subtask(subtask, task_spec, review_feedback)
                for subtask in subtasks
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            results = [r for r in results if not isinstance(r, Exception)]
        else:
            # Sequential execution
            for subtask in subtasks:
                result = await self._execute_subtask(subtask, task_spec, review_feedback)
                results.append(result)
        
        return results

    async def _execute_subtask(
        self,
        subtask: Dict[str, Any],
        task_spec: TaskSpec,
        review_feedback: Optional[Dict[str, Any]] = None
    ) -> TaskResult:
        """
        Execute a single subtask using a coder agent.
        
        Args:
            subtask: Subtask specification
            task_spec: Parent task specification
            review_feedback: Optional review feedback
            
        Returns:
            TaskResult from coder execution
        """
        coder = await self._get_coder()
        result = await coder.execute(subtask, task_spec, review_feedback)
        
        # Collect trace if enabled
        if self.config.collect_traces and self._current_result:
            trace = {
                "subtask_id": subtask.get("id"),
                "timestamp": datetime.utcnow().isoformat(),
                "result_status": result.status,
                "files_modified": result.files_modified,
                "duration_seconds": result.duration_seconds,
            }
            self._current_result.traces.append(trace)
        
        return result

    async def _review(
        self,
        task_spec: TaskSpec,
        coder_results: List[TaskResult]
    ) -> Dict[str, Any]:
        """
        Have the reviewer agent validate the implementation.
        
        Args:
            task_spec: Original task specification
            coder_results: Results from coder execution
            
        Returns:
            Review result with approval status and feedback
        """
        reviewer = await self._get_reviewer()
        review = await reviewer.review(task_spec, coder_results)
        return review

    async def _learn(self, result: PipelineResult) -> None:
        """
        Submit execution traces to the training orchestrator.
        
        Args:
            result: Pipeline execution result
        """
        if self.data_collector:
            await self.data_collector.collect_pipeline_trace(result)
        
        if self.training_orchestrator:
            await self.training_orchestrator.submit_learning_data(result)

    def _aggregate_results(
        self,
        task_spec: TaskSpec,
        result: PipelineResult
    ) -> TaskResult:
        """
        Aggregate results into a final TaskResult.
        
        Args:
            task_spec: Original task specification
            result: Pipeline execution result
            
        Returns:
            Aggregated TaskResult
        """
        # Determine overall success
        all_success = all(
            r.status in ("completed", "success")
            for r in result.coder_results
        )
        review_approved = result.review_result.get("approved", True) if result.review_result else True
        
        # Aggregate files modified
        all_files = []
        for r in result.coder_results:
            all_files.extend(getattr(r, "files_modified", []))
        
        return TaskResult(
            task_id=task_spec.task_id,
            status="completed" if all_success and review_approved else "failed",
            started_at=result.started_at,
            completed_at=result.completed_at,
            files_modified=list(set(all_files)),
            output=result.review_result or {},
        )

    async def _get_manager(self) -> ManagerAgent:
        """Get or create the manager agent."""
        if self._manager is None:
            self._manager = ManagerAgent(
                agent_id="pipeline_manager",
                llm_config=self.config.llm_config,
                mcp_config=self.config.mcp_config,
            )
            await self._manager.initialize()
        return self._manager

    async def _get_coder(self) -> CoderAgent:
        """Get or create a coder agent."""
        if not self._coders:
            coder = CoderAgent(
                agent_id=f"pipeline_coder_{len(self._coders)}",
                llm_config=self.config.llm_config,
                mcp_config=self.config.mcp_config,
            )
            await coder.initialize()
            self._coders.append(coder)
        return self._coders[0]

    async def _get_reviewer(self) -> ReviewerAgent:
        """Get or create the reviewer agent."""
        if self._reviewer is None:
            self._reviewer = ReviewerAgent(
                agent_id="pipeline_reviewer",
                llm_config=self.config.llm_config,
                mcp_config=self.config.mcp_config,
            )
            await self._reviewer.initialize()
        return self._reviewer

    async def shutdown(self) -> None:
        """Clean up pipeline resources."""
        if self._manager:
            await self._manager.shutdown()
        for coder in self._coders:
            await coder.shutdown()
        if self._reviewer:
            await self._reviewer.shutdown()
        logger.info("AgentPipeline shutdown complete")
