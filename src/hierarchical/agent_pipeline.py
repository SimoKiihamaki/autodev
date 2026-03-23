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
try:
    from agents.base import (
        BaseAgent,
        AgentRole,
        AgentState,
        TaskSpec,
        TaskResult,
        SubTask,
    )
    from agents.manager import ManagerAgent
    from agents.coder import CoderAgent
    from agents.reviewer import ReviewerAgent
    from agents.communication import AgentMessage, MessageType, MessageRouter

    # Import from training module
    from training.orchestrator import TrainingOrchestrator
    from training.data_collector import DataCollector
    from training.data_collector import (
        ExecutionTrace,
        TraceStatus,
        CodeChange,
        TrainingDataCollector,
        DataCollectionConfig,
    )
    from training.reward_calculator import (
        RewardCalculator,
        RewardComponents,
        RewardConfig,
    )
except ImportError:
    # Fallback for when running as standalone or in testing
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
    from ..training.data_collector import (
        ExecutionTrace,
        TraceStatus,
        CodeChange,
        TrainingDataCollector,
        DataCollectionConfig,
    )
    from ..training.reward_calculator import (
        RewardCalculator,
        RewardComponents,
        RewardConfig,
    )

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


# =============================================================================
# Agent Training Bridge - Connects Agents to Training Infrastructure
# =============================================================================

@dataclass
class BridgeConfig:
    """
    Configuration for AgentTrainingBridge.
    
    Attributes:
        enable_trace_collection: Whether to collect execution traces
        enable_reward_computation: Whether to compute rewards
        enable_model_injection: Whether to support model injection
        trace_storage_dir: Directory for storing traces
        default_model_version: Default model version to use
        role_model_mapping: Mapping of agent roles to model versions
        reward_weights: Custom weights for reward components
    """
    enable_trace_collection: bool = True
    enable_reward_computation: bool = True
    enable_model_injection: bool = True
    trace_storage_dir: str = "~/.autodev/agent_traces"
    default_model_version: str = "base"
    role_model_mapping: Dict[str, str] = field(default_factory=lambda: {
        "manager": "base",
        "coder": "base", 
        "reviewer": "base",
        "tester": "base",
    })
    reward_weights: Optional[Dict[str, float]] = None


@dataclass
class TrainedModelProvider:
    """
    Provides access to trained models for agent injection.
    
    Attributes:
        model_registry_path: Path to the model registry
        available_models: Dictionary of available model versions
        default_model: Default model to use when none specified
    """
    model_registry_path: str = "~/.autodev/model_registry"
    available_models: Dict[str, str] = field(default_factory=dict)
    default_model: str = "Qwen/Qwen2.5-Coder-7B-Instruct"
    
    def get_model_path(self, model_version: str) -> Optional[str]:
        """
        Get the path to a specific model version.
        
        Args:
            model_version: Version identifier for the model
            
        Returns:
            Path to the model, or None if not found
        """
        if model_version in self.available_models:
            return self.available_models[model_version]
        if model_version == "base":
            return self.default_model
        return None
    
    def register_model(self, version: str, path: str) -> None:
        """Register a new model version."""
        self.available_models[version] = path
        logger.info(f"Registered model version {version} at {path}")
    
    def list_available_models(self) -> List[str]:
        """List all available model versions."""
        return list(self.available_models.keys()) + ["base"]


class AgentTraceCollector:
    """
    Collects execution traces from agent runs for training.
    
    This class wraps agent execution to capture complete execution
    histories including LLM prompts, responses, tool calls, and outcomes.
    """
    
    def __init__(
        self,
        data_collector: Optional[TrainingDataCollector] = None,
        config: Optional[BridgeConfig] = None,
    ):
        """
        Initialize the trace collector.
        
        Args:
            data_collector: Optional training data collector
            config: Bridge configuration
        """
        self.config = config or BridgeConfig()
        self.data_collector = data_collector or TrainingDataCollector(
            DataCollectionConfig(output_dir=self.config.trace_storage_dir)
        )
        self._active_traces: Dict[str, ExecutionTrace] = {}
        
    def start_trace(
        self,
        agent_id: str,
        task_id: str,
        problem_statement: str,
        repo_context: Optional[Dict[str, Any]] = None,
        model: str = "",
    ) -> ExecutionTrace:
        """
        Start a new execution trace for an agent.
        
        Args:
            agent_id: ID of the agent executing
            task_id: ID of the task being executed
            problem_statement: The problem to solve
            repo_context: Repository context information
            model: Model being used
            
        Returns:
            New ExecutionTrace instance
        """
        trace = self.data_collector.start_trace(
            task_id=task_id,
            problem_statement=problem_statement,
            repo_context=repo_context,
            model=model,
            metadata={"agent_id": agent_id}
        )
        self._active_traces[trace.trace_id] = trace
        return trace
    
    def record_step(
        self,
        trace: ExecutionTrace,
        prompt: str,
        response: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        tool_results: Optional[List[Dict[str, Any]]] = None,
        tokens_used: Optional[Dict[str, int]] = None,
        latency_seconds: float = 0.0,
    ) -> None:
        """Record a step in the execution trace."""
        self.data_collector.record_step(
            trace=trace,
            prompt=prompt,
            response=response,
            tool_calls=tool_calls,
            tool_results=tool_results,
            tokens_used=tokens_used,
            latency_seconds=latency_seconds,
        )
    
    def record_code_change(
        self,
        trace: ExecutionTrace,
        file_path: str,
        change_type: str,
        original_content: Optional[str] = None,
        new_content: Optional[str] = None,
        diff: Optional[str] = None,
    ) -> None:
        """Record a code change in the trace."""
        self.data_collector.record_code_change(
            trace=trace,
            file_path=file_path,
            change_type=change_type,
            original_content=original_content,
            new_content=new_content,
            diff=diff,
        )
    
    def finalize_trace(
        self,
        trace: ExecutionTrace,
        status: TraceStatus,
        tests_passed: Optional[List[str]] = None,
        tests_failed: Optional[List[str]] = None,
        execution_time_seconds: float = 0.0,
        error: Optional[str] = None,
    ) -> bool:
        """Finalize and store the trace."""
        if trace.trace_id in self._active_traces:
            del self._active_traces[trace.trace_id]
        return self.data_collector.finalize_trace(
            trace=trace,
            status=status,
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            execution_time_seconds=execution_time_seconds,
            error=error,
        )
    
    def get_collected_traces(self) -> List[ExecutionTrace]:
        """Get all collected traces."""
        return self.data_collector._collected_traces


class AgentTrainingBridge:
    """
    Bridge connecting hierarchical agents to the training infrastructure.
    
    This class provides the integration layer between:
    - Agent execution traces → Training data collection
    - Trained models → Agent capability upgrades
    - Performance metrics → RL reward signals
    
    The bridge wraps agent execution to collect SWE-bench compatible traces,
    enables injection of fine-tuned models, and computes reward signals for
    reinforcement learning training.
    
    Example:
        >>> bridge = AgentTrainingBridge(config)
        >>> 
        >>> # Wrap agent execution for trace collection
        >>> result = await bridge.wrap_agent_execution(coder_agent, task_spec)
        >>> 
        >>> # Inject trained model
        >>> bridge.inject_trained_model(coder_agent, "v1.2.3")
        >>> 
        >>> # Get role-specific model
        >>> model = bridge.get_model_for_role(AgentRole.CODER)
    """
    
    def __init__(
        self,
        config: Optional[BridgeConfig] = None,
        training_orchestrator: Optional[TrainingOrchestrator] = None,
        data_collector: Optional[TrainingDataCollector] = None,
        reward_calculator: Optional[RewardCalculator] = None,
        model_provider: Optional[TrainedModelProvider] = None,
    ):
        """
        Initialize the Agent Training Bridge.
        
        Args:
            config: Bridge configuration
            training_orchestrator: Optional training orchestrator
            data_collector: Optional data collector for traces
            reward_calculator: Optional reward calculator
            model_provider: Optional model provider for trained models
        """
        self.config = config or BridgeConfig()
        
        # Initialize model provider
        self.model_provider = model_provider or TrainedModelProvider()
        
        # Initialize trace collector
        self.trace_collector = AgentTraceCollector(
            data_collector=data_collector,
            config=self.config,
        )
        
        # Initialize reward calculator
        if reward_calculator is not None:
            self.reward_calculator = reward_calculator
        else:
            reward_config = RewardConfig()
            if self.config.reward_weights:
                reward_config.test_pass_weight = self.config.reward_weights.get("test_pass", 0.5)
                reward_config.code_quality_weight = self.config.reward_weights.get("code_quality", 0.3)
                reward_config.efficiency_weight = self.config.reward_weights.get("efficiency", 0.2)
            self.reward_calculator = RewardCalculator(reward_config)
        
        # Reference to training orchestrator
        self.training_orchestrator = training_orchestrator
        
        # Track active executions
        self._active_executions: Dict[str, ExecutionTrace] = {}
        
        logger.info(
            f"AgentTrainingBridge initialized with "
            f"trace_collection={self.config.enable_trace_collection}, "
            f"reward_computation={self.config.enable_reward_computation}"
        )
    
    async def wrap_agent_execution(
        self,
        agent: BaseAgent,
        task: TaskSpec,
    ) -> TaskResult:
        """
        Wrap agent execution for trace collection.
        
        This method executes the agent while capturing a complete
        execution trace suitable for SWE-bench RL training.
        
        Args:
            agent: The agent to execute
            task: The task specification
            
        Returns:
            TaskResult from the agent execution
        """
        trace = None
        start_time = datetime.utcnow()
        
        if self.config.enable_trace_collection:
            # Start trace collection
            trace = self.trace_collector.start_trace(
                agent_id=agent.agent_id,
                task_id=task.task_id,
                problem_statement=task.description,
                repo_context=getattr(task, "repo_context", {}),
                model=getattr(agent, "model", "unknown"),
            )
            self._active_executions[task.task_id] = trace
        
        try:
            # Execute the agent
            result = await agent.execute(task)
            
            # Capture execution trace
            if trace is not None:
                trace = await self.capture_execution_trace(agent, task, result)
            
            return result
            
        except Exception as e:
            # Record failure in trace
            if trace is not None:
                self.trace_collector.finalize_trace(
                    trace=trace,
                    status=TraceStatus.ERROR,
                    execution_time_seconds=(datetime.utcnow() - start_time).total_seconds(),
                    error=str(e),
                )
            raise
            
        finally:
            if task.task_id in self._active_executions:
                del self._active_executions[task.task_id]
    
    def inject_trained_model(
        self,
        agent: BaseAgent,
        model_version: str,
    ) -> None:
        """
        Inject a trained model into an agent.
        
        This method replaces the agent's LLM with a fine-tuned model
        from the training pipeline.
        
        Args:
            agent: The agent to update
            model_version: Version identifier for the trained model
        """
        if not self.config.enable_model_injection:
            logger.warning("Model injection is disabled in config")
            return
        
        model_path = self.model_provider.get_model_path(model_version)
        if model_path is None:
            logger.error(f"Model version {model_version} not found")
            raise ValueError(f"Model version {model_version} not available")
        
        # Update agent's model configuration
        if hasattr(agent, "llm_config") and agent.llm_config is not None:
            agent.llm_config.model = model_path
            logger.info(f"Injected model {model_path} into agent {agent.agent_id}")
        elif hasattr(agent, "_llm_client"):
            # Direct client update if available
            agent._llm_client.model = model_path
            logger.info(f"Injected model {model_path} into agent {agent.agent_id}")
        else:
            logger.warning(f"Could not inject model into agent {agent.agent_id}: no LLM config")
    
    async def capture_execution_trace(
        self,
        agent: BaseAgent,
        task: TaskSpec,
        result: TaskResult,
    ) -> ExecutionTrace:
        """
        Capture execution trace from an agent run.
        
        Creates a complete SWE-bench compatible trace from the
        agent execution, including all steps, tool calls, and code changes.
        
        Args:
            agent: The agent that executed
            task: The task specification
            result: The execution result
            
        Returns:
            ExecutionTrace with complete execution history
        """
        trace = self._active_executions.get(task.task_id)
        
        if trace is None:
            # Create trace from result if not actively tracking
            trace = ExecutionTrace(
                trace_id=f"trace_{task.task_id}_{uuid.uuid4().hex[:8]}",
                task_id=task.task_id,
                timestamp=datetime.utcnow().isoformat(),
                problem_statement=task.description,
                repo_context=getattr(task, "repo_context", {}),
                model=getattr(agent, "model", "unknown"),
            )
        
        # Determine trace status
        if result.status in ("completed", "success"):
            status = TraceStatus.SUCCESS
        elif result.status == "failed":
            status = TraceStatus.FAILED
        else:
            status = TraceStatus.PARTIAL
        
        # Extract code changes from result
        files_modified = getattr(result, "files_modified", [])
        for file_path in files_modified:
            self.trace_collector.record_code_change(
                trace=trace,
                file_path=file_path,
                change_type="modify",
            )
        
        # Finalize trace
        execution_time = 0.0
        if hasattr(result, "duration_seconds") and result.duration_seconds:
            execution_time = result.duration_seconds
        elif hasattr(result, "started_at") and hasattr(result, "completed_at"):
            if result.started_at and result.completed_at:
                execution_time = (result.completed_at - result.started_at).total_seconds()
        
        self.trace_collector.finalize_trace(
            trace=trace,
            status=status,
            tests_passed=getattr(result, "tests_passed", []),
            tests_failed=getattr(result, "tests_failed", []),
            execution_time_seconds=execution_time,
            error=getattr(result, "error", None),
        )
        
        # Compute and attach reward
        if self.config.enable_reward_computation:
            reward_components = self.compute_agent_reward(trace)
            trace.reward = (
                reward_components.test_pass_rate * 0.5 +
                reward_components.code_quality * 0.3 +
                reward_components.efficiency * 0.2 +
                reward_components.success_bonus +
                reward_components.penalty
            )
        
        return trace
    
    def compute_agent_reward(
        self,
        trace: ExecutionTrace,
    ) -> RewardComponents:
        """
        Compute RL reward signals from an execution trace.
        
        Analyzes the trace to compute reward components suitable for
        GRPO-based reinforcement learning training.
        
        Args:
            trace: The execution trace to analyze
            
        Returns:
            RewardComponents with individual and total rewards
        """
        if not self.config.enable_reward_computation:
            return RewardComponents()
        
        # Use reward calculator
        reward_components = self.reward_calculator.calculate(trace)
        
        logger.debug(
            f"Computed reward for trace {trace.trace_id}: "
            f"total={getattr(reward_components, 'total_reward', 0):.3f}"
        )
        
        return reward_components
    
    def get_model_for_role(
        self,
        role: AgentRole,
    ) -> str:
        """
        Get the appropriate model for a specific agent role.
        
        Returns the model version/path configured for the given role,
        enabling role-specific model selection for different agent types.
        
        Args:
            role: The agent role (MANAGER, CODER, REVIEWER, TESTER)
            
        Returns:
            Model identifier or path for the role
        """
        role_name = role.value if isinstance(role, AgentRole) else str(role)
        
        # Check role-specific mapping
        if role_name in self.config.role_model_mapping:
            model_version = self.config.role_model_mapping[role_name]
            model_path = self.model_provider.get_model_path(model_version)
            if model_path:
                return model_path
        
        # Fall back to default
        return self.model_provider.default_model
    
    def set_model_for_role(
        self,
        role: AgentRole,
        model_version: str,
    ) -> None:
        """
        Set the model version for a specific agent role.
        
        Args:
            role: The agent role
            model_version: Model version identifier
        """
        role_name = role.value if isinstance(role, AgentRole) else str(role)
        self.config.role_model_mapping[role_name] = model_version
        logger.info(f"Set model for role {role_name} to {model_version}")
    
    def get_collected_traces(self) -> List[ExecutionTrace]:
        """
        Get all collected execution traces.
        
        Returns:
            List of all traces collected by this bridge
        """
        return self.trace_collector.get_collected_traces()
    
    async def submit_traces_for_training(self) -> int:
        """
        Submit collected traces to the training orchestrator.
        
        Returns:
            Number of traces submitted
        """
        if self.training_orchestrator is None:
            logger.warning("No training orchestrator configured")
            return 0
        
        traces = self.get_collected_traces()
        
        for trace in traces:
            await self.training_orchestrator.submit_learning_data(trace)
        
        logger.info(f"Submitted {len(traces)} traces for training")
        return len(traces)
    
    def register_trained_model(
        self,
        version: str,
        model_path: str,
        set_as_default: bool = False,
    ) -> None:
        """
        Register a newly trained model with the bridge.
        
        Args:
            version: Version identifier for the model
            model_path: Path to the trained model
            set_as_default: Whether to set as default model
        """
        self.model_provider.register_model(version, model_path)
        
        if set_as_default:
            self.model_provider.default_model = model_path
            self.config.default_model_version = version
            logger.info(f"Set {version} as default model")
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current status of the bridge.
        
        Returns:
            Dictionary with bridge status information
        """
        return {
            "config": {
                "trace_collection": self.config.enable_trace_collection,
                "reward_computation": self.config.enable_reward_computation,
                "model_injection": self.config.enable_model_injection,
            },
            "traces_collected": len(self.get_collected_traces()),
            "active_executions": len(self._active_executions),
            "available_models": self.model_provider.list_available_models(),
            "role_model_mapping": self.config.role_model_mapping,
        }
