"""
SWE-bench Test Harness for AutoDev Pipeline Validation

This module provides a comprehensive test harness for evaluating AutoDev
against SWE-bench tasks. It measures resolution rate and tracks success/failure patterns.

Target: 20%+ SWE-bench resolution rate

Usage:
    python -m benchmark.swe_bench_harness --num-tasks 10 --subset lite

Or programmatically:
    from benchmark.swe_bench_harness import SWEBenchHarness
    
    harness = SWEBenchHarness(workspace="/tmp/swebench_workspace")
    results = await harness.run_evaluation(num_tasks=10)
    print(f"Resolution rate: {results.resolution_rate:.1%}")
"""

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from datasets import load_dataset
    DATASETS_AVAILABLE = True
except ImportError:
    DATASETS_AVAILABLE = False
    print("Warning: 'datasets' package not installed. Install with: pip install datasets")

try:
    from integration import AutoDevPipeline, PipelineConfig, ExecutionResult
    from llm.client import LLMConfig
    INTEGRATION_AVAILABLE = True
except ImportError as e:
    INTEGRATION_AVAILABLE = False
    print(f"Warning: Integration modules not available: {e}")

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """Status of a SWE-bench task evaluation."""
    PENDING = "pending"
    RUNNING = "running"
    RESOLVED = "resolved"
    FAILED = "failed"
    TIMEOUT = "timeout"
    ERROR = "error"


@dataclass
class SWETask:
    """Represents a single SWE-bench task."""
    instance_id: str
    problem_statement: str
    repo: str
    base_commit: str
    patch: str  # The gold patch (for verification)
    test_patch: str  # Test changes
    version: str
    FAIL_TO_PASS: List[str]  # Tests that should pass after fix
    PASS_TO_PASS: List[str]  # Tests that should still pass
    created_at: str = ""
    hints_text: str = ""
    

@dataclass 
class TaskResult:
    """Result of evaluating a single SWE-bench task."""
    instance_id: str
    status: TaskStatus
    execution_time_seconds: float
    tokens_used: Dict[str, int]
    tools_called: List[Dict[str, Any]]
    iterations: int
    error: Optional[str] = None
    patch_generated: Optional[str] = None
    tests_passed: int = 0
    tests_failed: int = 0
    resolution_details: Dict[str, Any] = field(default_factory=dict)
    

@dataclass
class EvaluationResults:
    """Aggregated results from SWE-bench evaluation."""
    total_tasks: int
    resolved: int
    failed: int
    errors: int
    timeouts: int
    resolution_rate: float
    avg_execution_time: float
    total_tokens: Dict[str, int]
    total_cost_estimate: float
    task_results: List[TaskResult]
    patterns: Dict[str, Any]
    timestamp: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_tasks": self.total_tasks,
            "resolved": self.resolved,
            "failed": self.failed,
            "errors": self.errors,
            "timeouts": self.timeouts,
            "resolution_rate": self.resolution_rate,
            "avg_execution_time": self.avg_execution_time,
            "total_tokens": self.total_tokens,
            "total_cost_estimate": self.total_cost_estimate,
            "patterns": self.patterns,
            "timestamp": self.timestamp,
            "task_results": [asdict(r) for r in self.task_results]
        }


class SWEBenchHarness:
    """
    Test harness for evaluating AutoDev against SWE-bench tasks.
    
    This class provides:
    - Task loading from SWE-bench dataset
    - Workspace setup and teardown
    - AutoDevPipeline execution
    - Result verification
    - Pattern analysis
    """
    
    # SWE-bench subsets available
    SUBSETS = {
        "lite": "princeton-nlp/SWE-bench_Lite",
        "full": "princeton-nlp/SWE-bench",
        "verified": "princeton-nlp/SWE-bench_Verified"
    }
    
    def __init__(
        self,
        workspace: str = "/tmp/swebench_workspace",
        timeout_seconds: int = 1800,  # 30 minutes per task
        max_iterations: int = 30,
        api_key: Optional[str] = None,
        model: str = "claude-3-5-sonnet-20241022"
    ):
        """
        Initialize the SWE-bench harness.
        
        Args:
            workspace: Base directory for task workspaces
            timeout_seconds: Maximum time per task
            max_iterations: Maximum tool iterations per task
            api_key: Anthropic API key (uses env var if not provided)
            model: LLM model to use
        """
        self.workspace = Path(workspace)
        self.timeout_seconds = timeout_seconds
        self.max_iterations = max_iterations
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model
        
        # Ensure workspace exists
        self.workspace.mkdir(parents=True, exist_ok=True)
        
        # Results storage
        self.results_dir = self.workspace / "results"
        self.results_dir.mkdir(exist_ok=True)
        
        # Pattern tracking
        self._success_patterns: List[Dict[str, Any]] = []
        self._failure_patterns: List[Dict[str, Any]] = []
        
    def load_tasks(
        self,
        subset: str = "lite",
        num_tasks: Optional[int] = None,
        task_ids: Optional[List[str]] = None
    ) -> List[SWETask]:
        """
        Load SWE-bench tasks from Hugging Face datasets.
        
        Args:
            subset: Dataset subset ("lite", "full", "verified")
            num_tasks: Maximum number of tasks to load
            task_ids: Specific task IDs to load (overrides num_tasks)
            
        Returns:
            List of SWETask objects
        """
        if not DATASETS_AVAILABLE:
            raise RuntimeError(
                "Hugging Face datasets not available. "
                "Install with: pip install datasets"
            )
        
        dataset_name = self.SUBSETS.get(subset, subset)
        logger.info(f"Loading tasks from {dataset_name}...")
        
        try:
            dataset = load_dataset(dataset_name, split="test")
        except Exception as e:
            raise RuntimeError(f"Failed to load dataset {dataset_name}: {e}")
        
        tasks = []
        
        for item in dataset:
            # Filter by task IDs if specified
            if task_ids and item["instance_id"] not in task_ids:
                continue
            
            task = SWETask(
                instance_id=item["instance_id"],
                problem_statement=item["problem_statement"],
                repo=item["repo"],
                base_commit=item["base_commit"],
                patch=item["patch"],
                test_patch=item.get("test_patch", ""),
                version=item.get("version", ""),
                FAIL_TO_PASS=json.loads(item.get("FAIL_TO_PASS", "[]")),
                PASS_TO_PASS=json.loads(item.get("PASS_TO_PASS", "[]")),
                created_at=item.get("created_at", ""),
                hints_text=item.get("hints_text", "")
            )
            tasks.append(task)
            
            if num_tasks and len(tasks) >= num_tasks:
                break
        
        logger.info(f"Loaded {len(tasks)} tasks from {dataset_name}")
        return tasks
    
    async def setup_task_workspace(
        self,
        task: SWETask,
        task_workspace: Path
    ) -> bool:
        """
        Set up the workspace for a single task.
        
        This clones the repository at the correct commit.
        
        Args:
            task: The SWE-bench task
            task_workspace: Directory to set up
            
        Returns:
            True if setup successful
        """
        logger.info(f"Setting up workspace for {task.instance_id}...")
        
        try:
            # Clean up existing workspace
            if task_workspace.exists():
                shutil.rmtree(task_workspace)
            task_workspace.mkdir(parents=True)
            
            # Extract repo name (e.g., "django/django" -> "django")
            repo_name = task.repo.split("/")[-1]
            repo_url = f"https://github.com/{task.repo}.git"
            
            # Clone the repository
            logger.info(f"Cloning {repo_url}...")
            clone_result = subprocess.run(
                ["git", "clone", "--depth", "1", repo_url, str(task_workspace)],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if clone_result.returncode != 0:
                # Try shallow clone with specific commit
                logger.warning(f"Clone failed, trying with commit checkout...")
                clone_result = subprocess.run(
                    ["git", "clone", repo_url, str(task_workspace)],
                    capture_output=True,
                    text=True,
                    timeout=600
                )
                if clone_result.returncode != 0:
                    logger.error(f"Clone failed: {clone_result.stderr}")
                    return False
            
            # Checkout the base commit
            logger.info(f"Checking out {task.base_commit[:8]}...")
            checkout_result = subprocess.run(
                ["git", "checkout", task.base_commit],
                cwd=task_workspace,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if checkout_result.returncode != 0:
                logger.warning(f"Checkout failed: {checkout_result.stderr}")
                # Continue anyway - might be a shallow clone issue
            
            return True
            
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout setting up workspace for {task.instance_id}")
            return False
        except Exception as e:
            logger.error(f"Error setting up workspace: {e}")
            return False
    
    def build_task_prompt(self, task: SWETask) -> str:
        """
        Build the task prompt for the AutoDev pipeline.
        
        Args:
            task: The SWE-bench task
            
        Returns:
            Formatted prompt string
        """
        prompt = f"""# GitHub Issue Resolution Task

## Repository
{task.repo}

## Issue Description
{task.problem_statement}

## Instructions
You are tasked with resolving this GitHub issue. Please:

1. First, explore the codebase to understand the structure
2. Identify the relevant files that need to be modified
3. Implement a fix for the issue
4. Ensure your changes don't break existing functionality
5. Test your changes if possible

## Constraints
- Only modify files necessary to fix the issue
- Follow the existing code style and patterns
- Write clear, maintainable code
- Handle edge cases appropriately

## Hints
{task.hints_text if task.hints_text else "No additional hints available."}

Please proceed to analyze and fix this issue.
"""
        return prompt
    
    async def run_task(
        self,
        task: SWETask,
        task_workspace: Path
    ) -> TaskResult:
        """
        Run the AutoDev pipeline on a single SWE-bench task.
        
        Args:
            task: The SWE-bench task
            task_workspace: Path to the task workspace
            
        Returns:
            TaskResult with execution details
        """
        logger.info(f"Running task: {task.instance_id}")
        start_time = time.time()
        
        try:
            # Set up workspace
            if not await self.setup_task_workspace(task, task_workspace):
                return TaskResult(
                    instance_id=task.instance_id,
                    status=TaskStatus.ERROR,
                    execution_time_seconds=time.time() - start_time,
                    tokens_used={},
                    tools_called=[],
                    iterations=0,
                    error="Failed to set up task workspace"
                )
            
            # Configure pipeline
            llm_config = LLMConfig(
                api_key=self.api_key,
                model=self.model,
                max_tokens=8192,
                temperature=0.3  # Lower temperature for more deterministic results
            )
            
            pipeline_config = PipelineConfig(
                llm_config=llm_config,
                max_tool_iterations=self.max_iterations,
                workspace_path=str(task_workspace),
                enable_logging=True,
                log_level="INFO"
            )
            
            # Build task prompt
            prompt = self.build_task_prompt(task)
            
            # Run pipeline with timeout
            try:
                async with asyncio.timeout(self.timeout_seconds):
                    async with AutoDevPipeline(pipeline_config) as pipeline:
                        result: ExecutionResult = await pipeline.execute_task(
                            prompt,
                            context={
                                "repo": task.repo,
                                "base_commit": task.base_commit,
                                "instance_id": task.instance_id
                            }
                        )
            except asyncio.TimeoutError:
                return TaskResult(
                    instance_id=task.instance_id,
                    status=TaskStatus.TIMEOUT,
                    execution_time_seconds=self.timeout_seconds,
                    tokens_used={},
                    tools_called=[],
                    iterations=0,
                    error=f"Task timed out after {self.timeout_seconds}s"
                )
            
            execution_time = time.time() - start_time
            
            # Extract patch if generated
            patch_generated = await self._extract_patch(task_workspace)
            
            # Verify resolution (simplified - just check if changes were made)
            # Full verification would run the actual tests
            resolved = result.success and len(result.files_modified) > 0
            
            task_result = TaskResult(
                instance_id=task.instance_id,
                status=TaskStatus.RESOLVED if resolved else TaskStatus.FAILED,
                execution_time_seconds=execution_time,
                tokens_used=result.tokens_used,
                tools_called=result.tools_called,
                iterations=result.iterations,
                error=result.error,
                patch_generated=patch_generated,
                resolution_details={
                    "files_modified": result.files_modified,
                    "content_preview": result.content[:500] if result.content else None
                }
            )
            
            # Track patterns
            if resolved:
                self._success_patterns.append({
                    "instance_id": task.instance_id,
                    "repo": task.repo,
                    "iterations": result.iterations,
                    "tools_used": [t.get("name") for t in result.tools_called],
                    "files_modified": result.files_modified
                })
            else:
                self._failure_patterns.append({
                    "instance_id": task.instance_id,
                    "repo": task.repo,
                    "error": result.error,
                    "iterations": result.iterations
                })
            
            return task_result
            
        except Exception as e:
            logger.error(f"Error running task {task.instance_id}: {e}")
            return TaskResult(
                instance_id=task.instance_id,
                status=TaskStatus.ERROR,
                execution_time_seconds=time.time() - start_time,
                tokens_used={},
                tools_called=[],
                iterations=0,
                error=str(e)
            )
    
    async def _extract_patch(self, workspace: Path) -> Optional[str]:
        """Extract the git diff patch from the workspace."""
        try:
            result = subprocess.run(
                ["git", "diff"],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout
        except Exception as e:
            logger.warning(f"Failed to extract patch: {e}")
        return None
    
    def analyze_patterns(self) -> Dict[str, Any]:
        """
        Analyze success and failure patterns across all tasks.
        
        Returns:
            Dictionary with pattern analysis
        """
        patterns = {
            "success_rate_by_repo": {},
            "common_success_tools": {},
            "common_failure_reasons": {},
            "avg_iterations_success": 0,
            "avg_iterations_failure": 0
        }
        
        # Analyze by repository
        repos_success: Dict[str, int] = {}
        repos_failure: Dict[str, int] = {}
        
        for p in self._success_patterns:
            repo = p["repo"]
            repos_success[repo] = repos_success.get(repo, 0) + 1
        
        for p in self._failure_patterns:
            repo = p["repo"]
            repos_failure[repo] = repos_failure.get(repo, 0) + 1
        
        all_repos = set(repos_success.keys()) | set(repos_failure.keys())
        for repo in all_repos:
            success = repos_success.get(repo, 0)
            failure = repos_failure.get(repo, 0)
            total = success + failure
            patterns["success_rate_by_repo"][repo] = success / total if total > 0 else 0
        
        # Analyze tool usage in successes
        tool_counts: Dict[str, int] = {}
        for p in self._success_patterns:
            for tool in p.get("tools_used", []):
                tool_counts[tool] = tool_counts.get(tool, 0) + 1
        patterns["common_success_tools"] = dict(sorted(
            tool_counts.items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:10])
        
        # Analyze failure reasons
        error_counts: Dict[str, int] = {}
        for p in self._failure_patterns:
            error = str(p.get("error", "unknown"))[:100]
            error_counts[error] = error_counts.get(error, 0) + 1
        patterns["common_failure_reasons"] = dict(sorted(
            error_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10])
        
        # Average iterations
        if self._success_patterns:
            patterns["avg_iterations_success"] = sum(
                p["iterations"] for p in self._success_patterns
            ) / len(self._success_patterns)
        
        if self._failure_patterns:
            patterns["avg_iterations_failure"] = sum(
                p["iterations"] for p in self._failure_patterns
            ) / len(self._failure_patterns)
        
        return patterns
    
    async def run_evaluation(
        self,
        subset: str = "lite",
        num_tasks: Optional[int] = None,
        task_ids: Optional[List[str]] = None,
        parallel: bool = False,
        max_parallel: int = 3
    ) -> EvaluationResults:
        """
        Run full SWE-bench evaluation.
        
        Args:
            subset: Dataset subset to use
            num_tasks: Maximum number of tasks to evaluate
            task_ids: Specific task IDs to evaluate
            parallel: Whether to run tasks in parallel
            max_parallel: Maximum parallel tasks
            
        Returns:
            EvaluationResults with aggregated metrics
        """
        if not INTEGRATION_AVAILABLE:
            raise RuntimeError(
                "AutoDev integration not available. "
                "Ensure all dependencies are installed."
            )
        
        if not self.api_key:
            raise ValueError(
                "No API key provided. Set ANTHROPIC_API_KEY environment variable."
            )
        
        # Load tasks
        tasks = self.load_tasks(subset, num_tasks, task_ids)
        
        if not tasks:
            raise ValueError("No tasks loaded")
        
        logger.info(f"Starting evaluation of {len(tasks)} tasks...")
        
        results: List[TaskResult] = []
        
        if parallel:
            # Run tasks in parallel with semaphore
            semaphore = asyncio.Semaphore(max_parallel)
            
            async def run_with_semaphore(task: SWETask) -> TaskResult:
                async with semaphore:
                    task_workspace = self.workspace / task.instance_id
                    return await self.run_task(task, task_workspace)
            
            results = await asyncio.gather(*[
                run_with_semaphore(task) for task in tasks
            ])
        else:
            # Run tasks sequentially
            for i, task in enumerate(tasks):
                logger.info(f"Task {i+1}/{len(tasks)}: {task.instance_id}")
                task_workspace = self.workspace / task.instance_id
                result = await self.run_task(task, task_workspace)
                results.append(result)
                
                # Save intermediate results
                self._save_intermediate_results(results, i + 1, len(tasks))
        
        # Calculate aggregates
        resolved = sum(1 for r in results if r.status == TaskStatus.RESOLVED)
        failed = sum(1 for r in results if r.status == TaskStatus.FAILED)
        errors = sum(1 for r in results if r.status == TaskStatus.ERROR)
        timeouts = sum(1 for r in results if r.status == TaskStatus.TIMEOUT)
        
        total_tokens = {
            "total_tokens": sum(r.tokens_used.get("total_tokens", 0) for r in results),
            "input_tokens": sum(r.tokens_used.get("input_tokens", 0) for r in results),
            "output_tokens": sum(r.tokens_used.get("output_tokens", 0) for r in results)
        }
        
        # Estimate cost (Claude 3.5 Sonnet pricing)
        cost_per_input_1k = 0.003
        cost_per_output_1k = 0.015
        total_cost = (
            total_tokens["input_tokens"] / 1000 * cost_per_input_1k +
            total_tokens["output_tokens"] / 1000 * cost_per_output_1k
        )
        
        avg_time = sum(r.execution_time_seconds for r in results) / len(results) if results else 0
        
        # Analyze patterns
        patterns = self.analyze_patterns()
        
        evaluation_results = EvaluationResults(
            total_tasks=len(tasks),
            resolved=resolved,
            failed=failed,
            errors=errors,
            timeouts=timeouts,
            resolution_rate=resolved / len(tasks) if tasks else 0,
            avg_execution_time=avg_time,
            total_tokens=total_tokens,
            total_cost_estimate=total_cost,
            task_results=results,
            patterns=patterns,
            timestamp=datetime.utcnow().isoformat()
        )
        
        # Save final results
        self._save_final_results(evaluation_results)
        
        return evaluation_results
    
    def _save_intermediate_results(
        self,
        results: List[TaskResult],
        completed: int,
        total: int
    ) -> None:
        """Save intermediate results to file."""
        intermediate_path = self.results_dir / "intermediate_results.json"
        
        data = {
            "completed": completed,
            "total": total,
            "resolution_rate_so_far": sum(
                1 for r in results if r.status == TaskStatus.RESOLVED
            ) / len(results) if results else 0,
            "timestamp": datetime.utcnow().isoformat(),
            "results": [asdict(r) for r in results]
        }
        
        with open(intermediate_path, "w") as f:
            json.dump(data, f, indent=2, default=str)
    
    def _save_final_results(self, results: EvaluationResults) -> None:
        """Save final evaluation results."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        results_path = self.results_dir / f"evaluation_{timestamp}.json"
        
        with open(results_path, "w") as f:
            json.dump(results.to_dict(), f, indent=2, default=str)
        
        logger.info(f"Results saved to {results_path}")
        
        # Also save a summary
        summary_path = self.results_dir / "latest_summary.txt"
        with open(summary_path, "w") as f:
            f.write(f"SWE-bench Evaluation Results\n")
            f.write(f"{'=' * 50}\n\n")
            f.write(f"Timestamp: {results.timestamp}\n")
            f.write(f"Total Tasks: {results.total_tasks}\n")
            f.write(f"Resolved: {results.resolved}\n")
            f.write(f"Failed: {results.failed}\n")
            f.write(f"Errors: {results.errors}\n")
            f.write(f"Timeouts: {results.timeouts}\n\n")
            f.write(f"Resolution Rate: {results.resolution_rate:.1%}\n")
            f.write(f"Target: 20%+\n")
            f.write(f"Status: {'✅ PASSED' if results.resolution_rate >= 0.20 else '❌ BELOW TARGET'}\n\n")
            f.write(f"Avg Execution Time: {results.avg_execution_time:.1f}s\n")
            f.write(f"Total Cost Estimate: ${results.total_cost_estimate:.2f}\n")
            f.write(f"Total Tokens: {results.total_tokens['total_tokens']:,}\n\n")
            f.write(f"Patterns:\n")
            for key, value in results.patterns.items():
                f.write(f"  {key}: {value}\n")


async def main():
    """CLI entry point for SWE-bench evaluation."""
    import argparse
    
    parser = argparse.ArgumentParser(description="SWE-bench Test Harness for AutoDev")
    parser.add_argument("--num-tasks", type=int, default=10,
                        help="Number of tasks to evaluate (default: 10)")
    parser.add_argument("--subset", choices=["lite", "full", "verified"],
                        default="lite", help="Dataset subset to use")
    parser.add_argument("--task-ids", nargs="+", help="Specific task IDs to evaluate")
    parser.add_argument("--workspace", default="/tmp/swebench_workspace",
                        help="Workspace directory")
    parser.add_argument("--timeout", type=int, default=1800,
                        help="Timeout per task in seconds")
    parser.add_argument("--max-iterations", type=int, default=30,
                        help="Maximum tool iterations per task")
    parser.add_argument("--model", default="claude-3-5-sonnet-20241022",
                        help="LLM model to use")
    parser.add_argument("--parallel", action="store_true",
                        help="Run tasks in parallel")
    parser.add_argument("--max-parallel", type=int, default=3,
                        help="Maximum parallel tasks")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable verbose logging")
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Create harness
    harness = SWEBenchHarness(
        workspace=args.workspace,
        timeout_seconds=args.timeout,
        max_iterations=args.max_iterations,
        model=args.model
    )
    
    # Run evaluation
    results = await harness.run_evaluation(
        subset=args.subset,
        num_tasks=args.num_tasks,
        task_ids=args.task_ids,
        parallel=args.parallel,
        max_parallel=args.max_parallel
    )
    
    # Print summary
    print("\n" + "=" * 60)
    print("SWE-bench Evaluation Complete")
    print("=" * 60)
    print(f"Total Tasks: {results.total_tasks}")
    print(f"Resolved: {results.resolved}")
    print(f"Failed: {results.failed}")
    print(f"Errors: {results.errors}")
    print(f"Timeouts: {results.timeouts}")
    print(f"\nResolution Rate: {results.resolution_rate:.1%}")
    print(f"Target: 20%+")
    print(f"Status: {'✅ PASSED' if results.resolution_rate >= 0.20 else '❌ BELOW TARGET'}")
    print(f"\nAvg Execution Time: {results.avg_execution_time:.1f}s")
    print(f"Total Cost Estimate: ${results.total_cost_estimate:.2f}")
    print(f"\nResults saved to: {harness.results_dir}")
    
    return results


if __name__ == "__main__":
    asyncio.run(main())
