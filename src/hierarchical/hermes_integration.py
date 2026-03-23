"""
Hermes Integration Module

Provides integration with the Hermes delegate_task API for autonomous
task delegation and multi-project coordination.

This module enables:
- Full Hermes tool integration (autodev_task)
- Task delegation from Hermes to AutoDev agents
- Result streaming back to Hermes
- Cross-project task coordination

Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │                    Hermes Integration                       │
    ├─────────────────────────────────────────────────────────────┤
    │  Hermes Request → Task Validation → Agent Pipeline →        │
    │                  → Result Formatting → Hermes Response      │
    └─────────────────────────────────────────────────────────────┘

Usage:
    from hierarchical.hermes_integration import HermesIntegration, DelegateTaskConfig
    
    integration = HermesIntegration()
    result = await integration.delegate_task(
        task_description="Implement user authentication",
        project_path="/path/to/project",
        constraints={"preserve_api": True}
    )
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Callable, Awaitable
import asyncio
import json
import logging
import uuid

from .agent_pipeline import AgentPipeline, PipelineConfig, PipelineResult
from ..agents.base import TaskSpec, TaskResult

logger = logging.getLogger(__name__)


class TaskPriority(Enum):
    """Task priority levels for Hermes delegation."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class TaskType(Enum):
    """Task types supported by Hermes integration."""
    IMPLEMENT = "implement"
    REVIEW = "review"
    REFACTOR = "refactor"
    DEBUG = "debug"
    TEST = "test"
    DOCUMENT = "document"
    ANALYZE = "analyze"


@dataclass
class DelegateTaskConfig:
    """
    Configuration for Hermes task delegation.
    
    Attributes:
        task_type: Type of task to perform
        priority: Task priority level
        timeout_seconds: Maximum execution time
        enable_learning: Collect traces for training
        enable_review: Run reviewer validation
        max_iterations: Maximum review iterations
        notify_on_complete: Send notification on completion
        callback_url: Optional callback URL for async results
        constraints: Task constraints
        metadata: Additional task metadata
    """
    task_type: TaskType = TaskType.IMPLEMENT
    priority: TaskPriority = TaskPriority.NORMAL
    timeout_seconds: int = 1800
    enable_learning: bool = True
    enable_review: bool = True
    max_iterations: int = 3
    notify_on_complete: bool = False
    callback_url: Optional[str] = None
    constraints: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_pipeline_config(self) -> PipelineConfig:
        """Convert to PipelineConfig."""
        return PipelineConfig(
            enable_learning=self.enable_learning,
            enable_review=self.enable_review,
            max_iterations=self.max_iterations,
            timeout_seconds=self.timeout_seconds,
        )


@dataclass
class TaskDelegateResult:
    """
    Result from Hermes task delegation.
    
    Attributes:
        delegation_id: Unique identifier for this delegation
        status: Current status (pending, running, completed, failed)
        task_spec: Generated task specification
        pipeline_result: Result from agent pipeline execution
        summary: Human-readable summary
        files_modified: List of modified files
        created_at: Delegation creation timestamp
        completed_at: Delegation completion timestamp
        error: Error message if failed
    """
    delegation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: str = "pending"
    task_spec: Optional[TaskSpec] = None
    pipeline_result: Optional[PipelineResult] = None
    summary: str = ""
    files_modified: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        """Check if delegation completed successfully."""
        return self.status == "completed" and self.error is None

    def to_hermes_response(self) -> Dict[str, Any]:
        """Format result for Hermes response."""
        return {
            "delegation_id": self.delegation_id,
            "status": self.status,
            "summary": self.summary,
            "files_modified": self.files_modified,
            "success": self.success,
            "error": self.error,
            "metrics": {
                "duration_seconds": (
                    (self.completed_at - self.created_at).total_seconds()
                    if self.completed_at else None
                ),
                "iterations": (
                    len(self.pipeline_result.coder_results)
                    if self.pipeline_result else 0
                ),
            }
        }


class HermesIntegration:
    """
    Integration layer between Hermes and AutoDev hierarchical agents.
    
    This class provides the main interface for Hermes to delegate tasks
    to the AutoDev agent pipeline and receive structured results.
    
    Example:
        >>> integration = HermesIntegration()
        >>> result = await integration.delegate_task(
        ...     task_description="Add password reset functionality",
        ...     project_path="/home/user/myapp"
        ... )
        >>> print(result.summary)
    """
    
    def __init__(
        self,
        pipeline: Optional[AgentPipeline] = None,
        default_config: Optional[DelegateTaskConfig] = None,
    ):
        """
        Initialize Hermes Integration.
        
        Args:
            pipeline: Optional pre-configured AgentPipeline
            default_config: Default configuration for delegations
        """
        self.pipeline = pipeline or AgentPipeline()
        self.default_config = default_config or DelegateTaskConfig()
        self._active_delegations: Dict[str, TaskDelegateResult] = {}
        
        logger.info("HermesIntegration initialized")

    async def delegate_task(
        self,
        task_description: str,
        project_path: str,
        target_files: Optional[List[str]] = None,
        verification_command: Optional[str] = None,
        config: Optional[DelegateTaskConfig] = None,
        **kwargs: Any
    ) -> TaskDelegateResult:
        """
        Delegate a task from Hermes to the AutoDev agent pipeline.
        
        This is the main entry point for Hermes task delegation.
        
        Args:
            task_description: Natural language task description
            project_path: Path to the project directory
            target_files: Optional list of specific files to modify
            verification_command: Optional command to verify success
            config: Optional delegation configuration
            **kwargs: Additional task specification options
            
        Returns:
            TaskDelegateResult with execution details and outcomes
        """
        config = config or self.default_config
        
        # Create delegation result
        result = TaskDelegateResult(
            status="pending",
            created_at=datetime.utcnow()
        )
        self._active_delegations[result.delegation_id] = result
        
        try:
            # Convert Hermes request to TaskSpec
            task_spec = self._create_task_spec(
                task_description=task_description,
                project_path=project_path,
                target_files=target_files,
                verification_command=verification_command,
                config=config,
                **kwargs
            )
            result.task_spec = task_spec
            result.status = "running"
            
            logger.info(
                f"Delegating task {result.delegation_id}: "
                f"{task_description[:100]}..."
            )
            
            # Execute through agent pipeline
            pipeline_result = await self.pipeline.execute(task_spec)
            result.pipeline_result = pipeline_result
            
            # Process result
            if pipeline_result.success:
                result.status = "completed"
                result.summary = self._generate_summary(pipeline_result)
                result.files_modified = self._extract_modified_files(pipeline_result)
            else:
                result.status = "failed"
                result.error = pipeline_result.error or "Pipeline execution failed"
            
        except Exception as e:
            result.status = "failed"
            result.error = str(e)
            logger.error(f"Task delegation failed: {e}", exc_info=True)
        
        finally:
            result.completed_at = datetime.utcnow()
            
            # Send callback if configured
            if config.callback_url:
                await self._send_callback(config.callback_url, result)
            
            # Clean up active delegation
            if result.delegation_id in self._active_delegations:
                del self._active_delegations[result.delegation_id]
        
        return result

    def _create_task_spec(
        self,
        task_description: str,
        project_path: str,
        target_files: Optional[List[str]],
        verification_command: Optional[str],
        config: DelegateTaskConfig,
        **kwargs: Any
    ) -> TaskSpec:
        """
        Create a TaskSpec from Hermes delegation parameters.
        
        Args:
            task_description: Task description
            project_path: Project path
            target_files: Target files
            verification_command: Verification command
            config: Delegation configuration
            **kwargs: Additional options
            
        Returns:
            TaskSpec for agent pipeline
        """
        return TaskSpec(
            task_type=config.task_type.value,
            specification=task_description,
            target_files=target_files or [],
            constraints={
                **config.constraints,
                "priority": config.priority.value,
                **kwargs.get("constraints", {})
            },
            verification_command=verification_command,
            timeout_seconds=config.timeout_seconds,
            repo_root=project_path,
        )

    def _generate_summary(self, pipeline_result: PipelineResult) -> str:
        """
        Generate a human-readable summary of the pipeline result.
        
        Args:
            pipeline_result: Result from agent pipeline
            
        Returns:
            Human-readable summary string
        """
        parts = []
        
        if pipeline_result.manager_plan:
            subtask_count = len(pipeline_result.manager_plan.get("subtasks", []))
            parts.append(f"Completed {subtask_count} subtasks")
        
        if pipeline_result.coder_results:
            files_count = len(self._extract_modified_files(pipeline_result))
            parts.append(f"modified {files_count} files")
        
        if pipeline_result.review_result:
            if pipeline_result.review_result.get("approved"):
                parts.append("review passed")
            else:
                parts.append("review had issues")
        
        if pipeline_result.duration_seconds:
            parts.append(f"in {pipeline_result.duration_seconds:.1f}s")
        
        return " | ".join(parts) if parts else "Task completed"

    def _extract_modified_files(self, pipeline_result: PipelineResult) -> List[str]:
        """
        Extract list of all modified files from pipeline result.
        
        Args:
            pipeline_result: Result from agent pipeline
            
        Returns:
            List of unique modified file paths
        """
        files = set()
        
        for coder_result in pipeline_result.coder_results:
            if hasattr(coder_result, "files_modified"):
                files.update(coder_result.files_modified)
        
        return sorted(list(files))

    async def _send_callback(
        self,
        callback_url: str,
        result: TaskDelegateResult
    ) -> None:
        """
        Send result to callback URL.
        
        Args:
            callback_url: URL to send result to
            result: Delegation result
        """
        # TODO: Implement HTTP callback
        logger.info(f"Callback to {callback_url}: {result.to_hermes_response()}")

    async def get_delegation_status(
        self,
        delegation_id: str
    ) -> Optional[TaskDelegateResult]:
        """
        Get the status of an active delegation.
        
        Args:
            delegation_id: ID of the delegation to check
            
        Returns:
            TaskDelegateResult if found, None otherwise
        """
        return self._active_delegations.get(delegation_id)

    async def cancel_delegation(
        self,
        delegation_id: str
    ) -> bool:
        """
        Cancel an active delegation.
        
        Args:
            delegation_id: ID of the delegation to cancel
            
        Returns:
            True if cancelled, False if not found
        """
        if delegation_id in self._active_delegations:
            # TODO: Implement actual cancellation
            result = self._active_delegations[delegation_id]
            result.status = "cancelled"
            result.completed_at = datetime.utcnow()
            del self._active_delegations[delegation_id]
            logger.info(f"Cancelled delegation {delegation_id}")
            return True
        return False

    async def list_active_delegations(self) -> List[TaskDelegateResult]:
        """
        List all active delegations.
        
        Returns:
            List of active TaskDelegateResult objects
        """
        return list(self._active_delegations.values())

    async def shutdown(self) -> None:
        """Clean up integration resources."""
        # Cancel active delegations
        for delegation_id in list(self._active_delegations.keys()):
            await self.cancel_delegation(delegation_id)
        
        # Shutdown pipeline
        await self.pipeline.shutdown()
        
        logger.info("HermesIntegration shutdown complete")


# Hermes Tool Registration Helper
def create_autodev_tool_spec() -> Dict[str, Any]:
    """
    Create tool specification for Hermes autodev_task tool.
    
    This function generates the tool specification that can be
    registered with Hermes for autonomous task delegation.
    
    Returns:
        Tool specification dict for Hermes registration
    """
    return {
        "name": "autodev_task",
        "description": (
            "Delegate a software development task to AutoDev agents. "
            "The task will be planned by a Manager agent, implemented by "
            "Coder agents, and validated by a Reviewer agent."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task_description": {
                    "type": "string",
                    "description": "Natural language description of the task"
                },
                "project_path": {
                    "type": "string",
                    "description": "Path to the project directory"
                },
                "target_files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of specific files to modify"
                },
                "task_type": {
                    "type": "string",
                    "enum": ["implement", "review", "refactor", "debug", "test"],
                    "default": "implement",
                    "description": "Type of task to perform"
                },
                "constraints": {
                    "type": "object",
                    "description": "Task constraints (preserve_api, maintain_coverage, etc.)"
                },
                "timeout_seconds": {
                    "type": "integer",
                    "default": 1800,
                    "description": "Maximum execution time"
                }
            },
            "required": ["task_description", "project_path"]
        }
    }
