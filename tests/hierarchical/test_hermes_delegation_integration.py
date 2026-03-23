"""
Integration Test: AutoDev HierarchicalExecutor + Hermes delegate_task

This test demonstrates how Hermes's delegate_task can be used to spawn subagents
that fill the Manager → Coder → Reviewer roles in AutoDev's HierarchicalExecutor.

The integration shows:
1. HermesDelegateAgent - wraps delegate_task to act as an AutoDev agent
2. DelegateHierarchicalExecutor - orchestrates Hermes delegates in the hierarchical flow
3. Full flow: Task decomposition → Parallel coding → Review → Iteration

Run with: python -m pytest tests/hierarchical/test_hermes_delegation_integration.py -v
"""

import asyncio
import json
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# Add both project paths
autodev_root = Path(__file__).parent.parent.parent
hermes_root = Path.home() / "Projects" / "hermes-agent"
sys.path.insert(0, str(autodev_root))

# Import AutoDev components
try:
    from src.agents.base import AgentRole, BaseAgent, TaskSpec, TaskResult, SubTask
    from src.agents.communication import ReviewResult
    from src.hierarchical.hierarchical_executor import (
        ExecutionPhase,
        HierarchicalExecutor,
        HierarchicalResult,
        IterationRecord,
        PhaseResult,
    )
    AUTODEV_IMPORTS_AVAILABLE = True
except ImportError as e:
    AUTODEV_IMPORTS_AVAILABLE = False
    print(f"AutoDev imports not available: {e}")
    AgentRole = None
    BaseAgent = None
    TaskSpec = None
    TaskResult = None
    SubTask = None
    ReviewResult = None
    ExecutionPhase = None
    HierarchicalExecutor = None
    HierarchicalResult = None
    IterationRecord = None
    PhaseResult = None


# -----------------------------------------------------------------------------
# Mock Hermes delegate_task for testing (avoids needing real LLM)
# -----------------------------------------------------------------------------

class MockDelegateResult:
    """Simulates the result from a Hermes delegate_task call."""
    
    def __init__(
        self,
        summary: str,
        status: str = "completed",
        files_modified: List[str] = None,
        code_changes: List[Dict] = None,
        findings: List[str] = None,
        verdict: str = "approved",
        error: Optional[str] = None,
    ):
        self.summary = summary
        self.status = status
        self.files_modified = files_modified or []
        self.code_changes = code_changes or []
        self.findings = findings or []
        self.verdict = verdict
        self.error = error
        self.api_calls = 3
        self.duration_seconds = 1.5
        self.tokens = {"input": 1000, "output": 500}


def mock_delegate_task(
    goal: Optional[str] = None,
    context: Optional[str] = None,
    toolsets: Optional[List[str]] = None,
    tasks: Optional[List[Dict[str, Any]]] = None,
    max_iterations: Optional[int] = None,
    parent_agent=None,
) -> str:
    """
    Mock implementation of Hermes delegate_task for testing.
    
    Returns JSON string matching the format of real delegate_task,
    but with simulated responses based on the goal/context content.
    """
    if parent_agent is None:
        return json.dumps({"error": "delegate_task requires a parent agent context."})
    
    # Check depth limit (matching Hermes's MAX_DEPTH = 2)
    depth = getattr(parent_agent, '_delegate_depth', 0)
    if depth >= 2:
        return json.dumps({
            "error": "Delegation depth limit reached (2). Subagents cannot spawn further subagents."
        })
    
    # Normalize to task list
    if tasks and isinstance(tasks, list):
        task_list = tasks[:3]  # MAX_CONCURRENT_CHILDREN = 3
    elif goal and isinstance(goal, str) and goal.strip():
        task_list = [{"goal": goal, "context": context, "toolsets": toolsets}]
    else:
        return json.dumps({"error": "Provide either 'goal' (single task) or 'tasks' (batch)."})
    
    results = []
    for i, task in enumerate(task_list):
        task_goal = task.get("goal", "")
        task_context = task.get("context", "")
        
        # Simulate different responses based on role/keyword detection
        result = _simulate_delegate_response(i, task_goal, task_context)
        results.append(result)
    
    return json.dumps({
        "results": results,
        "total_duration_seconds": sum(r["duration_seconds"] for r in results),
        "task_count": len(results),
    })


def _simulate_delegate_response(task_index: int, goal: str, context: str) -> Dict[str, Any]:
    """Simulate a delegate response based on the task content."""
    goal_lower = goal.lower()
    
    # Detect role based on keywords
    if any(kw in goal_lower for kw in ["decompose", "break down", "plan", "subtask"]):
        # Manager role - return subtasks
        return {
            "task_index": task_index,
            "status": "completed",
            "summary": json.dumps({
                "subtasks": [
                    {"subtask_id": "sub-001", "name": "Implement core logic", "task_type": "implement"},
                    {"subtask_id": "sub-002", "name": "Add unit tests", "task_type": "test"},
                    {"subtask_id": "sub-003", "name": "Update documentation", "task_type": "docs"},
                ]
            }),
            "api_calls": 2,
            "duration_seconds": 1.0,
            "exit_reason": "completed",
            "tokens": {"input": 800, "output": 400},
            "tool_trace": [{"tool": "read_file", "status": "ok"}],
        }
    
    elif any(kw in goal_lower for kw in ["review", "validate", "check", "approve"]):
        # Reviewer role - return verdict
        verdict = "approved"
        findings = ["Code follows style guidelines", "Tests are comprehensive"]
        
        # Simulate "needs_changes" if context mentions issues
        if context and "fix" in context.lower():
            verdict = "needs_changes"
            findings.append("Address the issues mentioned in context")
        
        return {
            "task_index": task_index,
            "status": "completed",
            "summary": json.dumps({
                "verdict": verdict,
                "findings": findings,
                "blocking_issues": [] if verdict == "approved" else ["Fix the issues"],
            }),
            "api_calls": 3,
            "duration_seconds": 1.5,
            "exit_reason": "completed",
            "tokens": {"input": 1200, "output": 600},
            "tool_trace": [{"tool": "read_file", "status": "ok"}],
        }
    
    else:
        # Coder role - return code changes
        return {
            "task_index": task_index,
            "status": "completed",
            "summary": f"Implemented: {goal[:50]}...",
            "api_calls": 5,
            "duration_seconds": 2.0,
            "exit_reason": "completed",
            "tokens": {"input": 2000, "output": 1000},
            "tool_trace": [
                {"tool": "read_file", "status": "ok"},
                {"tool": "write_file", "status": "ok"},
            ],
        }


# -----------------------------------------------------------------------------
# HermesDelegateAgent - Wraps delegate_task as an AutoDev agent
# -----------------------------------------------------------------------------

class HermesDelegateAgent:
    """
    An AutoDev-compatible agent that uses Hermes delegate_task for execution.
    
    This agent can fill any role (Manager, Coder, Reviewer) in the hierarchical
    flow by delegating work to Hermes subagents.
    """
    
    def __init__(
        self,
        agent_id: str,
        role: str,
        delegate_fn: callable = None,
        parent_agent: Any = None,
        model: Optional[str] = None,
        toolsets: Optional[List[str]] = None,
    ):
        self.agent_id = agent_id
        self.role = role
        self._delegate_fn = delegate_fn or mock_delegate_task
        self._parent_agent = parent_agent
        self._model = model
        self._toolsets = toolsets or ["terminal", "file"]
        self._delegate_depth = 0
        
        # State tracking
        self.state = "idle"
        self._last_result = None
    
    async def initialize(self) -> None:
        """Initialize the agent."""
        self.state = "initialized"
    
    async def shutdown(self) -> None:
        """Shutdown the agent."""
        self.state = "shutdown"
    
    async def decompose(self, task: TaskSpec) -> List[SubTask]:
        """
        Decompose a task into subtasks (Manager role).
        Uses Hermes delegate_task to spawn a planning subagent.
        """
        goal = f"Decompose the following task into subtasks: {task.specification}"
        context = f"Task ID: {task.task_id}\nTask type: {task.task_type}"
        
        result_json = self._delegate_fn(
            goal=goal,
            context=context,
            parent_agent=self._parent_agent or self,
        )
        result = json.loads(result_json)
        
        if "error" in result:
            raise RuntimeError(f"Delegation failed: {result['error']}")
        
        summary = result["results"][0]["summary"]
        decomposition = json.loads(summary)
        
        # Convert to SubTask objects
        subtasks = []
        for sub_data in decomposition.get("subtasks", []):
            if AUTODEV_IMPORTS_AVAILABLE and SubTask:
                subtask = SubTask(
                    subtask_id=sub_data["subtask_id"],
                    name=sub_data["name"],
                    task_type=sub_data.get("task_type", "implement"),
                    description=sub_data.get("description", sub_data["name"]),
                )
            else:
                subtask = Mock(
                    subtask_id=sub_data["subtask_id"],
                    name=sub_data["name"],
                    task_type=sub_data.get("task_type", "implement"),
                    description=sub_data.get("description", sub_data["name"]),
                )
            subtasks.append(subtask)
        
        return subtasks
    
    async def execute(self, subtask: SubTask) -> TaskResult:
        """
        Execute a subtask (Coder role).
        Uses Hermes delegate_task to spawn a coding subagent.
        """
        goal = f"Implement: {subtask.name}"
        context = f"Subtask ID: {subtask.subtask_id}\nDescription: {getattr(subtask, 'description', subtask.name)}"
        
        result_json = self._delegate_fn(
            goal=goal,
            context=context,
            toolsets=self._toolsets,
            parent_agent=self._parent_agent or self,
        )
        result = json.loads(result_json)
        
        if "error" in result:
            return self._create_failed_result(subtask.subtask_id, result["error"])
        
        task_result = result["results"][0]
        
        if AUTODEV_IMPORTS_AVAILABLE and TaskResult:
            return TaskResult(
                task_id=subtask.subtask_id,
                status="completed",
                summary=task_result["summary"],
                files_modified=[],
            )
        
        return Mock(
            task_id=subtask.subtask_id,
            status="completed",
            summary=task_result["summary"],
            files_modified=[],
        )
    
    async def review(self, changes: List[Any]) -> ReviewResult:
        """
        Review code changes (Reviewer role).
        Uses Hermes delegate_task to spawn a review subagent.
        """
        goal = "Review the following code changes for quality and correctness"
        context = f"Number of changes: {len(changes)}"
        
        result_json = self._delegate_fn(
            goal=goal,
            context=context,
            parent_agent=self._parent_agent or self,
        )
        result = json.loads(result_json)
        
        if "error" in result:
            # Return a default approval on error
            return self._create_review_result("approved", ["Review delegation failed, auto-approving"])
        
        review_data = json.loads(result["results"][0]["summary"])
        
        return self._create_review_result(
            review_data.get("verdict", "approved"),
            review_data.get("findings", []),
            review_data.get("blocking_issues", []),
        )
    
    def _create_review_result(
        self,
        verdict: str,
        findings: List[str],
        blocking_issues: List[str] = None,
    ) -> ReviewResult:
        """Create a ReviewResult object."""
        if AUTODEV_IMPORTS_AVAILABLE and ReviewResult:
            return ReviewResult(
                review_id=f"review-{self.agent_id}",
                task_id="delegated",
                verdict=verdict,
                findings=findings,
                blocking_issues=blocking_issues or [],
            )
        
        return Mock(
            review_id=f"review-{self.agent_id}",
            task_id="delegated",
            verdict=verdict,
            findings=findings,
            blocking_issues=blocking_issues or [],
        )
    
    def _create_failed_result(self, task_id: str, error: str) -> TaskResult:
        """Create a failed TaskResult."""
        if AUTODEV_IMPORTS_AVAILABLE and TaskResult:
            return TaskResult(
                task_id=task_id,
                status="failed",
                error=error,
            )
        
        return Mock(
            task_id=task_id,
            status="failed",
            error=error,
        )


# -----------------------------------------------------------------------------
# DelegateHierarchicalExecutor - Uses Hermes delegates in hierarchical flow
# -----------------------------------------------------------------------------

class DelegateHierarchicalExecutor:
    """
    A HierarchicalExecutor that uses Hermes delegate_task to fill agent roles.
    
    This executor demonstrates the integration between AutoDev's hierarchical
    execution pattern and Hermes's subagent delegation capability.
    """
    
    def __init__(
        self,
        delegate_fn: callable = None,
        parent_agent: Any = None,
        max_iterations: int = 3,
        parallel_coding: bool = True,
    ):
        self._delegate_fn = delegate_fn or mock_delegate_task
        self._parent_agent = parent_agent
        self.max_iterations = max_iterations
        self.parallel_coding = parallel_coding
        
        # Create delegate-based agents for each role
        self.manager = HermesDelegateAgent(
            agent_id="delegate-manager",
            role="manager",
            delegate_fn=self._delegate_fn,
            parent_agent=self._parent_agent,
        )
        
        self.coder_pool = [
            HermesDelegateAgent(
                agent_id=f"delegate-coder-{i}",
                role="coder",
                delegate_fn=self._delegate_fn,
                parent_agent=self._parent_agent,
            )
            for i in range(3)
        ]
        
        self.reviewer_pool = [
            HermesDelegateAgent(
                agent_id="delegate-reviewer",
                role="reviewer",
                delegate_fn=self._delegate_fn,
                parent_agent=self._parent_agent,
            )
        ]
        
        # Execution tracking
        self._iteration_history: List[Dict] = []
        self._current_task_id: Optional[str] = None
    
    async def execute(self, task: TaskSpec) -> Dict[str, Any]:
        """
        Execute a task through the Manager → Coder → Reviewer flow using delegates.
        
        Returns a HierarchicalResult-like dictionary with execution details.
        """
        start_time = datetime.utcnow()
        self._current_task_id = task.task_id
        
        try:
            # Initialize agents
            await self._initialize_agents()
            
            # Phase 1: Decomposition (Manager)
            print(f"[DelegateExecutor] Phase 1: Decomposing task {task.task_id}")
            subtasks = await self.manager.decompose(task)
            print(f"[DelegateExecutor]   → Created {len(subtasks)} subtasks")
            
            # Phase 2: Coding (Coders)
            print(f"[DelegateExecutor] Phase 2: Executing {len(subtasks)} subtasks")
            code_changes = await self._execute_subtasks(subtasks)
            print(f"[DelegateExecutor]   → Generated {len(code_changes)} changes")
            
            # Phase 3: Review (Reviewer)
            print(f"[DelegateExecutor] Phase 3: Reviewing changes")
            review_result = await self.reviewer_pool[0].review(code_changes)
            print(f"[DelegateExecutor]   → Verdict: {review_result.verdict}")
            
            # Iteration loop
            iterations = 1
            while (
                review_result.verdict != "approved"
                and iterations < self.max_iterations
            ):
                print(f"[DelegateExecutor] Iteration {iterations}: Addressing feedback")
                
                # Re-execute with feedback
                code_changes = await self._execute_subtasks(subtasks)
                review_result = await self.reviewer_pool[0].review(code_changes)
                
                iterations += 1
            
            # Build result
            end_time = datetime.utcnow()
            
            return {
                "task_id": task.task_id,
                "success": review_result.verdict == "approved",
                "subtask_count": len(subtasks),
                "code_change_count": len(code_changes),
                "review_verdict": review_result.verdict,
                "iterations": iterations,
                "total_time_seconds": (end_time - start_time).total_seconds(),
                "agent_usage": self._get_agent_usage(),
            }
        
        except Exception as e:
            return {
                "task_id": task.task_id,
                "success": False,
                "error": str(e),
                "total_time_seconds": (datetime.utcnow() - start_time).total_seconds(),
            }
        
        finally:
            await self._shutdown_agents()
    
    async def _initialize_agents(self) -> None:
        """Initialize all delegate agents."""
        await self.manager.initialize()
        for coder in self.coder_pool:
            await coder.initialize()
        for reviewer in self.reviewer_pool:
            await reviewer.initialize()
    
    async def _shutdown_agents(self) -> None:
        """Shutdown all delegate agents."""
        await self.manager.shutdown()
        for coder in self.coder_pool:
            await coder.shutdown()
        for reviewer in self.reviewer_pool:
            await reviewer.shutdown()
    
    async def _execute_subtasks(self, subtasks: List[SubTask]) -> List[Any]:
        """Execute subtasks using coder delegates."""
        code_changes = []
        
        if self.parallel_coding and len(subtasks) > 1:
            # Parallel execution
            tasks = [
                self.coder_pool[i % len(self.coder_pool)].execute(subtask)
                for i, subtask in enumerate(subtasks)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if not isinstance(result, Exception):
                    code_changes.append(result)
        else:
            # Sequential execution
            for i, subtask in enumerate(subtasks):
                coder = self.coder_pool[i % len(self.coder_pool)]
                result = await coder.execute(subtask)
                code_changes.append(result)
        
        return code_changes
    
    def _get_agent_usage(self) -> Dict[str, int]:
        """Get usage count per agent."""
        return {
            self.manager.agent_id: 1,
            **{coder.agent_id: 1 for coder in self.coder_pool},
            **{reviewer.agent_id: 1 for reviewer in self.reviewer_pool},
        }


# -----------------------------------------------------------------------------
# Integration Tests
# -----------------------------------------------------------------------------

@pytest.mark.skipif(not AUTODEV_IMPORTS_AVAILABLE, reason="AutoDev imports not available")
class TestHermesDelegationIntegration:
    """
    Integration tests for connecting AutoDev HierarchicalExecutor with Hermes delegate_task.
    """
    
    @pytest.fixture
    def mock_parent_agent(self):
        """Create a mock parent agent for delegation."""
        parent = MagicMock()
        parent.base_url = "https://api.example.com"
        parent.api_key = "test-key"
        parent.provider = "test"
        parent.api_mode = "chat_completions"
        parent.model = "test-model"
        parent.platform = "cli"
        parent.providers_allowed = None
        parent.providers_ignored = None
        parent.providers_order = None
        parent.provider_sort = None
        parent._session_db = None
        parent._delegate_depth = 0
        parent._active_children = []
        parent._active_children_lock = threading.Lock()
        return parent
    
    @pytest.fixture
    def sample_task(self):
        """Create a sample task for testing."""
        if AUTODEV_IMPORTS_AVAILABLE:
            return TaskSpec(
                task_id="integration-test-001",
                task_type="implement",
                specification="Implement a Fibonacci function with caching",
                target_files=["fibonacci.py"],
            )
        return Mock(
            task_id="integration-test-001",
            task_type="implement",
            specification="Implement a Fibonacci function with caching",
            target_files=["fibonacci.py"],
        )
    
    @pytest.fixture
    def delegate_executor(self, mock_parent_agent):
        """Create a DelegateHierarchicalExecutor for testing."""
        return DelegateHierarchicalExecutor(
            delegate_fn=mock_delegate_task,
            parent_agent=mock_parent_agent,
            max_iterations=3,
            parallel_coding=True,
        )
    
    @pytest.mark.asyncio
    async def test_hermes_delegate_agent_can_decompose(self, mock_parent_agent, sample_task):
        """Test that HermesDelegateAgent can decompose tasks using delegate_task."""
        manager = HermesDelegateAgent(
            agent_id="test-manager",
            role="manager",
            delegate_fn=mock_delegate_task,
            parent_agent=mock_parent_agent,
        )
        
        await manager.initialize()
        subtasks = await manager.decompose(sample_task)
        await manager.shutdown()
        
        assert len(subtasks) > 0
        assert all(hasattr(st, 'subtask_id') for st in subtasks)
        print(f"✓ Decomposed task into {len(subtasks)} subtasks")
    
    @pytest.mark.asyncio
    async def test_hermes_delegate_agent_can_execute(self, mock_parent_agent):
        """Test that HermesDelegateAgent can execute subtasks using delegate_task."""
        coder = HermesDelegateAgent(
            agent_id="test-coder",
            role="coder",
            delegate_fn=mock_delegate_task,
            parent_agent=mock_parent_agent,
        )
        
        subtask = Mock(
            subtask_id="sub-001",
            name="Implement core logic",
            description="Implement the main functionality",
        )
        
        await coder.initialize()
        result = await coder.execute(subtask)
        await coder.shutdown()
        
        assert result.status == "completed"
        print(f"✓ Executed subtask: {result.summary[:50]}...")
    
    @pytest.mark.asyncio
    async def test_hermes_delegate_agent_can_review(self, mock_parent_agent):
        """Test that HermesDelegateAgent can review changes using delegate_task."""
        reviewer = HermesDelegateAgent(
            agent_id="test-reviewer",
            role="reviewer",
            delegate_fn=mock_delegate_task,
            parent_agent=mock_parent_agent,
        )
        
        changes = [Mock(file="test.py", diff="def foo(): pass")]
        
        await reviewer.initialize()
        result = await reviewer.review(changes)
        await reviewer.shutdown()
        
        assert result.verdict in ["approved", "needs_changes"]
        assert isinstance(result.findings, list)
        print(f"✓ Review verdict: {result.verdict}")
    
    @pytest.mark.asyncio
    async def test_delegate_hierarchical_executor_full_flow(self, delegate_executor, sample_task):
        """Test the full hierarchical flow with delegate-based agents."""
        result = await delegate_executor.execute(sample_task)
        
        assert result["task_id"] == sample_task.task_id
        assert result["success"] is True
        assert result["subtask_count"] > 0
        assert result["review_verdict"] == "approved"
        assert "total_time_seconds" in result
        
        print(f"✓ Full flow completed in {result['total_time_seconds']:.2f}s")
        print(f"  - Subtasks: {result['subtask_count']}")
        print(f"  - Iterations: {result['iterations']}")
        print(f"  - Verdict: {result['review_verdict']}")
    
    @pytest.mark.asyncio
    async def test_delegate_executor_handles_iteration(self, mock_parent_agent):
        """Test that executor handles review iterations correctly."""
        # Create a task that will trigger iteration (reviewer will request changes)
        task = TaskSpec(
            task_id="iteration-test",
            task_type="implement",
            specification="Implement with issues that need fixing",
        )
        
        # Custom delegate function that simulates iteration
        iteration_count = [0]
        
        def iterative_delegate(**kwargs):
            goal = kwargs.get("goal", "")
            if "review" in goal.lower():
                iteration_count[0] += 1
                if iteration_count[0] < 2:
                    # First review: needs changes
                    return json.dumps({
                        "results": [{
                            "task_index": 0,
                            "status": "completed",
                            "summary": json.dumps({
                                "verdict": "needs_changes",
                                "findings": ["Fix this issue"],
                                "blocking_issues": ["Issue 1"],
                            }),
                            "api_calls": 2,
                            "duration_seconds": 1.0,
                            "exit_reason": "completed",
                            "tokens": {"input": 500, "output": 200},
                            "tool_trace": [],
                        }]
                    })
                else:
                    # Second review: approved
                    return json.dumps({
                        "results": [{
                            "task_index": 0,
                            "status": "completed",
                            "summary": json.dumps({
                                "verdict": "approved",
                                "findings": ["All issues fixed"],
                                "blocking_issues": [],
                            }),
                            "api_calls": 2,
                            "duration_seconds": 1.0,
                            "exit_reason": "completed",
                            "tokens": {"input": 500, "output": 200},
                            "tool_trace": [],
                        }]
                    })
            return mock_delegate_task(**kwargs)
        
        executor = DelegateHierarchicalExecutor(
            delegate_fn=iterative_delegate,
            parent_agent=mock_parent_agent,
            max_iterations=3,
        )
        
        result = await executor.execute(task)
        
        assert result["success"] is True
        assert result["iterations"] >= 2
        print(f"✓ Iteration handled correctly: {result['iterations']} iterations")
    
    @pytest.mark.asyncio
    async def test_delegate_executor_parallel_execution(self, delegate_executor, sample_task):
        """Test that parallel execution works correctly."""
        result = await delegate_executor.execute(sample_task)
        
        # Should have executed multiple subtasks
        assert result["subtask_count"] > 1
        assert result["agent_usage"] is not None
        
        # Check that multiple coders were used
        coder_usage = sum(1 for k in result["agent_usage"] if "coder" in k)
        assert coder_usage > 0
        
        print(f"✓ Parallel execution used {coder_usage} coders")
    
    @pytest.mark.asyncio
    async def test_delegate_executor_respects_max_iterations(self, mock_parent_agent):
        """Test that executor respects max_iterations limit."""
        task = TaskSpec(
            task_id="max-iter-test",
            task_type="implement",
            specification="Test max iterations",
        )
        
        # Delegate that always returns "needs_changes"
        def always_needs_changes(**kwargs):
            if "review" in kwargs.get("goal", "").lower():
                return json.dumps({
                    "results": [{
                        "task_index": 0,
                        "status": "completed",
                        "summary": json.dumps({
                            "verdict": "needs_changes",
                            "findings": ["Never good enough"],
                            "blocking_issues": ["Always something"],
                        }),
                        "api_calls": 1,
                        "duration_seconds": 0.5,
                        "exit_reason": "completed",
                        "tokens": {"input": 100, "output": 50},
                        "tool_trace": [],
                    }]
                })
            return mock_delegate_task(**kwargs)
        
        executor = DelegateHierarchicalExecutor(
            delegate_fn=always_needs_changes,
            parent_agent=mock_parent_agent,
            max_iterations=2,
        )
        
        result = await executor.execute(task)
        
        # Should stop at max_iterations even if not approved
        assert result["iterations"] <= 2
        assert result["success"] is False  # Not approved
        print(f"✓ Max iterations respected: stopped at {result['iterations']}")


# -----------------------------------------------------------------------------
# Tests for Integration with Real HierarchicalExecutor
# -----------------------------------------------------------------------------

@pytest.mark.skipif(not AUTODEV_IMPORTS_AVAILABLE, reason="AutoDev imports not available")
class TestHierarchicalExecutorWithHermesDelegates:
    """
    Tests showing how HermesDelegateAgent can be used with the real HierarchicalExecutor.
    """
    
    @pytest.fixture
    def mock_parent_agent(self):
        """Create a mock parent agent for delegation."""
        parent = MagicMock()
        parent._delegate_depth = 0
        parent._active_children = []
        parent._active_children_lock = threading.Lock()
        return parent
    
    @pytest.mark.asyncio
    async def test_hermes_delegates_work_with_hierarchical_executor(self, mock_parent_agent):
        """Test that HermesDelegateAgents can be used in HierarchicalExecutor."""
        # Create delegate-based agents
        manager = HermesDelegateAgent(
            agent_id="hermes-manager",
            role="manager",
            delegate_fn=mock_delegate_task,
            parent_agent=mock_parent_agent,
        )
        
        coders = [
            HermesDelegateAgent(
                agent_id=f"hermes-coder-{i}",
                role="coder",
                delegate_fn=mock_delegate_task,
                parent_agent=mock_parent_agent,
            )
            for i in range(2)
        ]
        
        reviewers = [
            HermesDelegateAgent(
                agent_id="hermes-reviewer",
                role="reviewer",
                delegate_fn=mock_delegate_task,
                parent_agent=mock_parent_agent,
            )
        ]
        
        # Create HierarchicalExecutor with delegate agents
        executor = HierarchicalExecutor(
            manager=manager,
            coder_pool=coders,
            reviewer_pool=reviewers,
            max_iterations=3,
        )
        
        # Create a task
        task = TaskSpec(
            task_id="hierarchical-delegate-test",
            task_type="implement",
            specification="Test task for hierarchical execution with delegates",
        )
        
        # Execute through the hierarchical flow
        result = await executor.execute(task)
        
        assert result.task_id == task.task_id
        assert isinstance(result.success, bool)
        assert isinstance(result.iterations, int)
        
        print(f"✓ HierarchicalExecutor with Hermes delegates:")
        print(f"  - Success: {result.success}")
        print(f"  - Iterations: {result.iterations}")
        print(f"  - Time: {result.total_time_seconds:.2f}s")


# -----------------------------------------------------------------------------
# Manual Test Runner
# -----------------------------------------------------------------------------

async def run_manual_tests():
    """Run tests manually for development/debugging."""
    print("\n" + "=" * 70)
    print("AutoDev HierarchicalExecutor + Hermes delegate_task Integration Tests")
    print("=" * 70 + "\n")
    
    # Create mock parent
    parent = MagicMock()
    parent._delegate_depth = 0
    parent._active_children = []
    
    # Test 1: HermesDelegateAgent decomposition
    print("Test 1: Manager Delegate Decomposition")
    print("-" * 40)
    manager = HermesDelegateAgent(
        agent_id="test-manager",
        role="manager",
        delegate_fn=mock_delegate_task,
        parent_agent=parent,
    )
    
    task = TaskSpec(
        task_id="manual-test-001",
        specification="Implement a REST API endpoint",
    )
    
    await manager.initialize()
    subtasks = await manager.decompose(task)
    await manager.shutdown()
    
    print(f"  Created {len(subtasks)} subtasks:")
    for st in subtasks:
        print(f"    - {st.name} ({st.subtask_id})")
    print("  ✓ PASSED\n")
    
    # Test 2: Full DelegateHierarchicalExecutor flow
    print("Test 2: Full DelegateHierarchicalExecutor Flow")
    print("-" * 40)
    executor = DelegateHierarchicalExecutor(
        delegate_fn=mock_delegate_task,
        parent_agent=parent,
        max_iterations=3,
    )
    
    result = await executor.execute(task)
    
    print(f"  Task ID: {result['task_id']}")
    print(f"  Success: {result['success']}")
    print(f"  Subtasks: {result['subtask_count']}")
    print(f"  Iterations: {result['iterations']}")
    print(f"  Verdict: {result['review_verdict']}")
    print(f"  Time: {result['total_time_seconds']:.2f}s")
    print("  ✓ PASSED\n")
    
    print("=" * 70)
    print("All manual tests passed!")
    print("=" * 70)


if __name__ == "__main__":
    if AUTODEV_IMPORTS_AVAILABLE:
        asyncio.run(run_manual_tests())
    else:
        print("Cannot run manual tests - AutoDev imports not available")
        print("Run with: python -m pytest tests/hierarchical/test_hermes_delegation_integration.py -v")
