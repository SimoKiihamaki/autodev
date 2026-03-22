"""
Coder Agent Implementation

The Coder Agent is a worker agent responsible for code generation and modification.
It receives tasks from the Manager Agent and implements features, fixes bugs,
performs refactoring, and writes documentation.

As specified in Section 2.2 of the Hierarchical Architecture Specification.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import logging
import uuid

from .base import BaseAgent, AgentRole, AgentState, TaskSpec, TaskResult
from .states import StateMachine, CoderState, CODER_TRANSITIONS
from .communication import (
    AgentMessage,
    MessageType,
    TaskAssignment,
    ReviewResult,
    Finding
)

logger = logging.getLogger(__name__)


@dataclass
class FeatureSpec:
    """
    Feature specification for implementation.
    
    Attributes:
        feature_name: Name of the feature
        description: Detailed description
        acceptance_criteria: List of acceptance criteria
        target_files: Files to modify
        constraints: Implementation constraints
    """
    feature_name: str = ""
    description: str = ""
    acceptance_criteria: List[str] = field(default_factory=list)
    target_files: List[str] = field(default_factory=list)
    constraints: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BugReport:
    """
    Bug report for fixing.
    
    Attributes:
        bug_id: Bug identifier
        title: Bug title
        description: Detailed description
        reproduction_steps: Steps to reproduce
        expected_behavior: Expected behavior
        actual_behavior: Actual behavior
        affected_files: Files affected by the bug
    """
    bug_id: str = ""
    title: str = ""
    description: str = ""
    reproduction_steps: List[str] = field(default_factory=list)
    expected_behavior: str = ""
    actual_behavior: str = ""
    affected_files: List[str] = field(default_factory=list)


@dataclass
class RefactorScope:
    """
    Scope for refactoring operations.
    
    Attributes:
        scope_type: Type of scope (file, module, package, function)
        targets: Target files or components
        goals: Refactoring goals
        preserve_behavior: Whether to preserve existing behavior
    """
    scope_type: str = "file"  # file, module, package, function
    targets: List[str] = field(default_factory=list)
    goals: List[str] = field(default_factory=list)
    preserve_behavior: bool = True


@dataclass
class DocumentationTarget:
    """
    Target for documentation generation.
    
    Attributes:
        target_type: Type of target (module, function, class, api)
        target_files: Files to document
        format: Documentation format (markdown, rst, docstring)
        include_private: Include private members
    """
    target_type: str = "module"
    target_files: List[str] = field(default_factory=list)
    format: str = "docstring"
    include_private: bool = False


@dataclass
class CodeChange:
    """
    Represents a code change made by the Coder Agent.
    
    Attributes:
        change_id: Unique identifier
        file_path: Path to the modified file
        change_type: Type of change (create, modify, delete)
        diff: Unified diff of changes
        description: Description of the change
        rationale: Rationale for implementation choices
    """
    change_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    file_path: str = ""
    change_type: str = "modify"  # create, modify, delete
    diff: str = ""
    description: str = ""
    rationale: str = ""


class CoderAgent(BaseAgent):
    """
    Coder Agent - Worker for code generation and modification.
    
    The Coder Agent is responsible for:
    - Implementing new features
    - Fixing bugs
    - Refactoring code
    - Writing documentation
    
    Capabilities:
    - Code generation based on specifications
    - Bug fixing based on reports
    - Refactoring for quality improvements
    - Documentation generation
    
    Example:
        >>> coder = CoderAgent()
        >>> await coder.initialize()
        >>> result = await coder.execute(task_spec)
        >>> print(result.files_modified)
        ['src/main.py', 'src/utils.py']
    
    Attributes:
        state_machine: State machine managing coder state
        current_task: Currently assigned task
        iteration_count: Number of revision iterations
        max_iterations: Maximum allowed iterations
    """
    
    def __init__(
        self,
        agent_id: str = None,
        mcp_config_path: str = "~/.config/autodev/mcp_config.json",
        repo_root: str = ".",
        max_retries: int = 2,
        retry_backoff_seconds: int = 30
    ):
        super().__init__(
            agent_id=agent_id,
            role=AgentRole.CODER,
            mcp_config_path=mcp_config_path,
            repo_root=repo_root
        )
        
        # Initialize state machine
        self.state_machine = StateMachine(
            initial_state=CoderState.IDLE,
            valid_transitions=CODER_TRANSITIONS
        )
        
        # Task tracking
        self.current_task: Optional[TaskAssignment] = None
        self.code_changes: List[CodeChange] = []
        
        # Iteration management
        self.iteration_count: int = 0
        self.max_iterations: int = max_retries + 1
        
        # Configuration
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        
        # Context
        self._previous_iteration_summary: str = ""
    
    async def initialize(self) -> None:
        """
        Initialize the Coder Agent.
        
        - Connects to MCP servers (filesystem, git, lsp, terminal)
        - Loads code style preferences
        - Prepares for code generation
        """
        logger.info(f"Initializing Coder Agent {self.agent_id}")
        
        self.update_state(AgentState.INITIALIZING)
        
        # TODO: Initialize MCP client with required servers
        # Required MCP servers:
        # - filesystem: for reading/writing files
        # - git: for version control
        # - lsp: for code intelligence
        # - terminal: for running commands
        
        self.update_state(AgentState.IDLE)
        logger.info("Coder Agent initialized successfully")
    
    async def shutdown(self) -> None:
        """
        Clean shutdown of the Coder Agent.
        
        - Saves any uncommitted work
        - Disconnects from MCP servers
        - Releases resources
        """
        logger.info(f"Shutting down Coder Agent {self.agent_id}")
        
        # TODO: Disconnect MCP client
        
        self.update_state(AgentState.COMPLETED)
        logger.info("Coder Agent shutdown complete")
    
    async def execute(self, task: TaskSpec) -> TaskResult:
        """
        Execute a coding task.
        
        This is the main entry point for task execution. The coder
        implements the requested changes and submits for review.
        
        Args:
            task: Task specification to execute
            
        Returns:
            TaskResult with the implementation outcome
        """
        logger.info(f"Executing coding task {task.task_id}")
        
        result = TaskResult(task_id=task.task_id, status="running")
        
        try:
            # Create task assignment
            assignment = TaskAssignment(
                task_id=task.task_id,
                task_type=task.task_type,
                specification=task.specification,
                context={
                    "target_files": task.target_files,
                    "constraints": task.constraints
                }
            )
            
            # Execute based on task type
            if task.task_type == "implement":
                changes = await self.implement_feature(
                    FeatureSpec(
                        description=task.specification,
                        target_files=task.target_files,
                        constraints=task.constraints
                    )
                )
            elif task.task_type == "debug":
                changes = await self.fix_bug(
                    BugReport(description=task.specification)
                )
            elif task.task_type == "refactor":
                changes = await self.refactor_code(
                    RefactorScope(
                        targets=task.target_files,
                        goals=[task.specification]
                    )
                )
            else:
                # Generic implementation
                changes = await self._implement_generic(task)
            
            # Store changes
            self.code_changes = changes
            
            # Build result
            result.status = "completed"
            result.files_modified = [c.file_path for c in changes]
            result.summary = f"Implemented {len(changes)} changes"
            result.result = {
                "changes": [c.__dict__ for c in changes]
            }
            
        except Exception as e:
            logger.error(f"Task execution failed: {e}")
            result.status = "failed"
            result.error = str(e)
        
        return result
    
    # -------------------------------------------------------------------------
    # Core Capabilities
    # -------------------------------------------------------------------------
    
    async def implement_feature(self, spec: FeatureSpec) -> List[CodeChange]:
        """
        Generate code for a feature specification.
        
        Implements the feature according to the specification,
        following existing code style and patterns.
        
        Args:
            spec: Feature specification
            
        Returns:
            List of code changes made
            
        Example:
            >>> spec = FeatureSpec(
            ...     feature_name="User Authentication",
            ...     description="Implement OAuth2 authentication",
            ...     acceptance_criteria=["Users can log in", "Sessions persist"]
            ... )
            >>> changes = await coder.implement_feature(spec)
        """
        logger.info(f"Implementing feature: {spec.feature_name or spec.description[:50]}")
        
        self.state_machine.transition(CoderState.ASSIGNED)
        self.state_machine.transition(CoderState.IMPLEMENTING)
        
        changes: List[CodeChange] = []
        
        # TODO: Implement actual feature generation using LLM
        # This involves:
        # 1. Reading relevant existing code for context
        # 2. Generating implementation code
        # 3. Writing changes to files
        # 4. Following code style and patterns
        
        # Placeholder implementation
        for target_file in spec.target_files:
            changes.append(CodeChange(
                file_path=target_file,
                change_type="modify",
                description=f"Implement {spec.feature_name or 'feature'}",
                rationale="Feature implementation"
            ))
        
        return changes
    
    async def fix_bug(self, bug_report: BugReport) -> List[CodeChange]:
        """
        Implement bug fix based on report.
        
        Analyzes the bug report and implements a fix that addresses
        the root cause while maintaining existing functionality.
        
        Args:
            bug_report: Bug report with details
            
        Returns:
            List of code changes made
            
        Example:
            >>> bug = BugReport(
            ...     bug_id="BUG-123",
            ...     title="Null pointer in user service",
            ...     affected_files=["src/services/user.py"]
            ... )
            >>> changes = await coder.fix_bug(bug)
        """
        logger.info(f"Fixing bug: {bug_report.title or bug_report.description[:50]}")
        
        self.state_machine.transition(CoderState.ASSIGNED)
        self.state_machine.transition(CoderState.IMPLEMENTING)
        
        changes: List[CodeChange] = []
        
        # TODO: Implement actual bug fix using LLM
        # This involves:
        # 1. Analyzing the bug report
        # 2. Reading affected code
        # 3. Identifying root cause
        # 4. Implementing fix
        # 5. Verifying fix doesn't break other functionality
        
        for file in bug_report.affected_files:
            changes.append(CodeChange(
                file_path=file,
                change_type="modify",
                description=f"Fix: {bug_report.title}",
                rationale="Bug fix implementation"
            ))
        
        return changes
    
    async def refactor_code(self, scope: RefactorScope) -> List[CodeChange]:
        """
        Refactor code within specified scope.
        
        Improves code quality while preserving behavior (if specified).
        
        Args:
            scope: Refactoring scope and goals
            
        Returns:
            List of code changes made
            
        Example:
            >>> scope = RefactorScope(
            ...     scope_type="module",
            ...     targets=["src/legacy/"],
            ...     goals=["Improve readability", "Reduce complexity"]
            ... )
            >>> changes = await coder.refactor_code(scope)
        """
        logger.info(f"Refactoring: {scope.goals}")
        
        self.state_machine.transition(CoderState.ASSIGNED)
        self.state_machine.transition(CoderState.IMPLEMENTING)
        
        changes: List[CodeChange] = []
        
        # TODO: Implement actual refactoring using LLM
        # This involves:
        # 1. Analyzing current code structure
        # 2. Identifying refactoring opportunities
        # 3. Implementing changes
        # 4. Running tests to verify behavior preservation
        
        for target in scope.targets:
            changes.append(CodeChange(
                file_path=target,
                change_type="modify",
                description=f"Refactor: {', '.join(scope.goals)}",
                rationale="Code quality improvement"
            ))
        
        return changes
    
    async def write_documentation(
        self,
        target: DocumentationTarget
    ) -> List[CodeChange]:
        """
        Generate documentation for code.
        
        Creates documentation in the specified format for the
        target code components.
        
        Args:
            target: Documentation target specification
            
        Returns:
            List of changes (documentation files or modified source)
            
        Example:
            >>> target = DocumentationTarget(
            ...     target_type="module",
            ...     target_files=["src/api/"],
            ...     format="markdown"
            ... )
            >>> changes = await coder.write_documentation(target)
        """
        logger.info(f"Writing documentation for: {target.target_files}")
        
        changes: List[CodeChange] = []
        
        # TODO: Implement documentation generation
        
        for file in target.target_files:
            changes.append(CodeChange(
                file_path=f"{file}/README.md" if target.format == "markdown" else file,
                change_type="create" if target.format == "markdown" else "modify",
                description=f"Add documentation for {file}",
                rationale="Documentation generation"
            ))
        
        return changes
    
    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------
    
    async def _implement_generic(self, task: TaskSpec) -> List[CodeChange]:
        """Generic implementation for unspecified task types."""
        logger.info(f"Generic implementation for task type: {task.task_type}")
        return [
            CodeChange(
                file_path=".",
                description=task.specification[:100],
                rationale="Generic implementation"
            )
        ]
    
    def handle_review_feedback(self, review: ReviewResult) -> None:
        """
        Handle feedback from a code review.
        
        If changes are needed, transitions to REVISION state and
        prepares to implement feedback.
        
        Args:
            review: Review result with findings
        """
        if review.verdict == "approved":
            logger.info("Review approved - moving to DONE")
            self.state_machine.transition(CoderState.DONE)
        elif review.verdict == "needs_changes":
            logger.info("Review needs changes - moving to REVISION")
            self.state_machine.transition(CoderState.REVISION)
            self.iteration_count += 1
            
            if self.iteration_count >= self.max_iterations:
                logger.warning("Maximum iterations reached")
        else:
            logger.error("Review rejected")
            self.state_machine.transition(CoderState.DONE)
    
    async def read_file(self, file_path: str) -> str:
        """
        Read a file using MCP filesystem server.
        
        Args:
            file_path: Path to file
            
        Returns:
            File contents
        """
        # TODO: Use MCP filesystem server
        # return await self._mcp_client.call_tool(
        #     "filesystem", "read_file", {"path": file_path}
        # )
        return ""
    
    async def write_file(self, file_path: str, content: str) -> None:
        """
        Write a file using MCP filesystem server.
        
        Args:
            file_path: Path to file
            content: Content to write
        """
        # TODO: Use MCP filesystem server
        # await self._mcp_client.call_tool(
        #     "filesystem", "write_file",
        #     {"path": file_path, "content": content}
        # )
        pass
    
    async def get_code_context(
        self,
        file_path: str,
        symbol: str = None
    ) -> Dict[str, Any]:
        """
        Get code context using LSP server.
        
        Args:
            file_path: Path to file
            symbol: Optional symbol to get context for
            
        Returns:
            Code context (definitions, references, etc.)
        """
        # TODO: Use MCP LSP server
        return {}
    
    def get_prompt_template(self, task_type: str) -> str:
        """
        Get the prompt template for a task type.
        
        Args:
            task_type: Type of task
            
        Returns:
            Prompt template string
        """
        return """# CODER AGENT - Implementation Task

## Context
- **Task ID**: {task_id}
- **Feature**: {feature_name}
- **Acceptance Criteria**: {acceptance_criteria}

## Codebase Context
{relevant_files}

## Previous Context (if applicable)
{previous_iteration_summary}

## Constraints
- Follow existing code style and patterns
- Maintain backward compatibility
- Write self-documenting code
- Include error handling

## Output Format
1. Files modified with changes
2. Rationale for implementation choices
3. Any edge cases handled
4. Tests needed (if not provided)
"""
