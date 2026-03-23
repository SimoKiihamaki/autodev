"""
AutoDev Solver for SWE-bench

This module integrates HierarchicalExecutor with SWEbenchRunner to enable
actual benchmark execution using AutoDev's hierarchical agent system.

The solver function takes a SWE-bench instance dict and returns a patch string,
which can be passed directly to SWEbenchRunner.set_solver().
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
import uuid

logger = logging.getLogger(__name__)

# Import with fallbacks for different execution contexts
try:
    from agents.base import AgentRole, BaseAgent, TaskSpec, TaskResult, SubTask
    from agents.manager import ManagerAgent
    from agents.coder import CoderAgent
    from agents.reviewer import ReviewerAgent
    from hierarchical.hierarchical_executor import (
        HierarchicalExecutor,
        HierarchicalResult,
        ExecutionPhase,
    )
    AGENTS_AVAILABLE = True
except ImportError:
    try:
        from ..agents.base import AgentRole, BaseAgent, TaskSpec, TaskResult, SubTask
        from ..agents.manager import ManagerAgent
        from ..agents.coder import CoderAgent
        from ..agents.reviewer import ReviewerAgent
        from ..hierarchical.hierarchical_executor import (
            HierarchicalExecutor,
            HierarchicalResult,
            ExecutionPhase,
        )
        AGENTS_AVAILABLE = True
    except ImportError:
        AGENTS_AVAILABLE = False
        logger.warning("Agent imports not available - using mock implementations")


@dataclass
class SWEBenchInstance:
    """Structured representation of a SWE-bench instance."""
    instance_id: str
    repo: str
    base_commit: str
    problem_statement: str
    hints_text: Optional[str] = None
    created_at: Optional[str] = None
    version: Optional[str] = None
    FAIL_TO_PASS: Optional[str] = None
    PASS_TO_PASS: Optional[str] = None
    environment_setup_commit: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict) -> "SWEBenchInstance":
        """Create instance from raw dictionary."""
        return cls(
            instance_id=data.get("instance_id", str(uuid.uuid4())),
            repo=data.get("repo", "unknown"),
            base_commit=data.get("base_commit", ""),
            problem_statement=data.get("problem_statement", ""),
            hints_text=data.get("hints_text"),
            created_at=data.get("created_at"),
            version=data.get("version"),
            FAIL_TO_PASS=data.get("FAIL_TO_PASS"),
            PASS_TO_PASS=data.get("PASS_TO_PASS"),
            environment_setup_commit=data.get("environment_setup_commit"),
        )


@dataclass
class SolverConfig:
    """Configuration for the AutoDev solver."""
    max_iterations: int = 5
    num_coders: int = 2
    num_reviewers: int = 1
    timeout_seconds: int = 600
    enable_parallel_coding: bool = True
    repo_root: str = "."
    llm_config: Optional[Dict] = None
    

class AutoDevSolver:
    """
    AutoDev solver that uses HierarchicalExecutor to generate patches.
    
    This class wraps the hierarchical agent system to provide a solver
    function compatible with SWEbenchRunner.
    
    Example:
        >>> solver = AutoDevSolver(config=SolverConfig())
        >>> runner = SWEbenchRunner()
        >>> runner.set_solver(solver.solve)
        >>> metrics = runner.run_benchmark(subset_size=10)
    """
    
    def __init__(self, config: Optional[SolverConfig] = None):
        """
        Initialize the AutoDev solver.
        
        Args:
            config: Solver configuration. Uses defaults if not provided.
        """
        self.config = config or SolverConfig()
        self._executor: Optional[HierarchicalExecutor] = None
        self._agents_initialized = False
        
        logger.info(f"AutoDevSolver initialized with config: {self.config}")
    
    def _create_task_spec(self, instance: SWEBenchInstance) -> TaskSpec:
        """
        Convert a SWE-bench instance to a TaskSpec for execution.
        
        Args:
            instance: SWE-bench instance
            
        Returns:
            TaskSpec for the hierarchical executor
        """
        if AGENTS_AVAILABLE:
            return TaskSpec(
                task_id=f"swebench-{instance.instance_id}",
                task_type="bugfix",  # SWE-bench tasks are bug fixes
                specification=instance.problem_statement,
                target_files=[],
                constraints={
                    "repo": instance.repo,
                    "base_commit": instance.base_commit,
                    "hints": instance.hints_text,
                    "tests_to_pass": instance.FAIL_TO_PASS,
                    "tests_to_preserve": instance.PASS_TO_PASS,
                },
                timeout_seconds=self.config.timeout_seconds,
                repo_root=self.config.repo_root,
            )
        else:
            # Mock TaskSpec
            return type('TaskSpec', (), {
                'task_id': f"swebench-{instance.instance_id}",
                'task_type': "bugfix",
                'specification': instance.problem_statement,
                'target_files': [],
                'constraints': {
                    "repo": instance.repo,
                    "base_commit": instance.base_commit,
                },
                'timeout_seconds': self.config.timeout_seconds,
                'repo_root': self.config.repo_root,
            })()
    
    def _initialize_agents(self) -> None:
        """Initialize the hierarchical agent system."""
        if self._agents_initialized:
            return
        
        if not AGENTS_AVAILABLE:
            logger.warning("Agents not available - using mock implementations")
            self._agents_initialized = True
            return
        
        try:
            # Create manager agent
            self._manager = ManagerAgent(
                agent_id="manager-swebench",
                role=AgentRole.MANAGER,
            )
            
            # Create coder pool
            self._coder_pool = [
                CoderAgent(
                    agent_id=f"coder-{i}",
                    role=AgentRole.CODER,
                )
                for i in range(self.config.num_coders)
            ]
            
            # Create reviewer pool
            self._reviewer_pool = [
                ReviewerAgent(
                    agent_id=f"reviewer-{i}",
                    role=AgentRole.REVIEWER,
                )
                for i in range(self.config.num_reviewers)
            ]
            
            # Create executor
            self._executor = HierarchicalExecutor(
                manager=self._manager,
                coder_pool=self._coder_pool,
                reviewer_pool=self._reviewer_pool,
                max_iterations=self.config.max_iterations,
            )
            
            self._agents_initialized = True
            logger.info(
                f"Agents initialized: 1 manager, {len(self._coder_pool)} coders, "
                f"{len(self._reviewer_pool)} reviewers"
            )
            
        except Exception as e:
            logger.error(f"Failed to initialize agents: {e}")
            self._agents_initialized = True  # Prevent retry loops
    
    def _extract_patch(self, result: HierarchicalResult) -> Optional[str]:
        """
        Extract a unified diff patch from the execution result.
        
        Args:
            result: Result from HierarchicalExecutor
            
        Returns:
            Unified diff patch string, or None if no patch could be generated
        """
        if not result.success:
            logger.warning(f"Execution was not successful for {result.task_id}")
            return None
        
        # Collect diffs from code changes
        diffs = []
        for change in result.code_changes:
            diff = getattr(change, 'diff', None)
            if diff:
                diffs.append(diff)
        
        if not diffs:
            logger.warning(f"No diffs found in code changes for {result.task_id}")
            return None
        
        # Combine all diffs into a single patch
        combined_patch = "\n".join(diffs)
        
        # Validate patch format
        if not combined_patch.startswith("diff --git"):
            # Wrap in proper diff format if needed
            combined_patch = self._format_as_diff(combined_patch, result)
        
        logger.info(f"Generated patch of {len(combined_patch)} bytes for {result.task_id}")
        return combined_patch
    
    def _format_as_diff(self, content: str, result: HierarchicalResult) -> str:
        """Format content as a proper unified diff."""
        lines = []
        
        # Get files modified
        files_modified = []
        if hasattr(result.final_result, 'files_modified'):
            files_modified = result.final_result.files_modified
        
        if not files_modified:
            files_modified = ['unknown_file.py']
        
        for file_path in files_modified:
            lines.append(f"diff --git a/{file_path} b/{file_path}")
            lines.append(f"--- a/{file_path}")
            lines.append(f"+++ b/{file_path}")
        
        lines.append(content)
        
        return "\n".join(lines)
    
    async def solve_async(self, instance: Dict) -> Optional[str]:
        """
        Async version of solve method.
        
        Args:
            instance: SWE-bench instance dictionary
            
        Returns:
            Patch string or None if generation failed
        """
        # Initialize agents if needed
        self._initialize_agents()
        
        # Parse instance
        swebench_instance = SWEBenchInstance.from_dict(instance)
        logger.info(f"Solving instance: {swebench_instance.instance_id}")
        
        # Create task spec
        task_spec = self._create_task_spec(swebench_instance)
        
        try:
            if AGENTS_AVAILABLE and self._executor:
                # Execute using hierarchical system
                result = await self._executor.execute(task_spec)
                
                # Extract patch from result
                patch = self._extract_patch(result)
                
                return patch
            else:
                # Fallback: generate mock patch
                return self._generate_mock_patch(swebench_instance)
                
        except Exception as e:
            logger.error(f"Error solving {swebench_instance.instance_id}: {e}")
            return None
    
    def solve(self, instance: Dict) -> Optional[str]:
        """
        Synchronous solver function compatible with SWEbenchRunner.
        
        This is the main entry point that gets passed to runner.set_solver().
        
        Args:
            instance: SWE-bench instance dictionary containing:
                - instance_id: Unique identifier
                - repo: Repository name (e.g., "django/django")
                - base_commit: Git commit hash
                - problem_statement: Issue description
                - hints_text: Optional hints
                - FAIL_TO_PASS: Tests that should pass after fix
                - PASS_TO_PASS: Tests that should still pass
                
        Returns:
            Unified diff patch string, or None if generation failed
        """
        # Get or create event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're already in an async context, create a new loop
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self.solve_async(instance))
                    return future.result(timeout=self.config.timeout_seconds)
        except RuntimeError:
            loop = None
        
        if loop and not loop.is_running():
            return loop.run_until_complete(self.solve_async(instance))
        else:
            return asyncio.run(self.solve_async(instance))
    
    def _generate_mock_patch(self, instance: SWEBenchInstance) -> Optional[str]:
        """
        Generate a mock patch for testing when agents are not available.
        
        Args:
            instance: SWE-bench instance
            
        Returns:
            A simple mock patch
        """
        # This is a placeholder that returns None to indicate no real patch
        # In production, this would never be called
        logger.warning(f"Returning mock patch for {instance.instance_id}")
        return None


def create_solver(
    max_iterations: int = 5,
    num_coders: int = 2,
    num_reviewers: int = 1,
    timeout_seconds: int = 600,
    **kwargs
) -> Callable[[Dict], Optional[str]]:
    """
    Factory function to create a configured solver.
    
    This is a convenience function that creates an AutoDevSolver
    and returns its solve method.
    
    Args:
        max_iterations: Maximum review-implement iterations
        num_coders: Number of coder agents in the pool
        num_reviewers: Number of reviewer agents in the pool
        timeout_seconds: Timeout per instance
        **kwargs: Additional configuration options
        
    Returns:
        Solver function compatible with SWEbenchRunner.set_solver()
        
    Example:
        >>> from swebench import SWEbenchRunner, create_solver
        >>> runner = SWEbenchRunner()
        >>> runner.set_solver(create_solver(max_iterations=3))
        >>> metrics = runner.run_benchmark(subset_size=10)
    """
    config = SolverConfig(
        max_iterations=max_iterations,
        num_coders=num_coders,
        num_reviewers=num_reviewers,
        timeout_seconds=timeout_seconds,
        **kwargs
    )
    
    solver = AutoDevSolver(config=config)
    return solver.solve


# Convenience exports
__all__ = [
    'AutoDevSolver',
    'SolverConfig',
    'SWEBenchInstance',
    'create_solver',
]
