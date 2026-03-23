"""
Reviewer Agent Implementation

The Reviewer Agent is a worker agent responsible for quality assurance and code review.
It reviews code changes, validates acceptance criteria, checks coding standards,
and ensures output quality before commit.

As specified in Section 2.3 of the Hierarchical Architecture Specification.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import logging
import uuid

from .base import BaseAgent, AgentRole, AgentState, TaskSpec, TaskResult
from .states import StateMachine, ReviewerState, REVIEWER_TRANSITIONS
from .communication import (
    AgentMessage,
    MessageType,
    ReviewResult,
    Finding
)

logger = logging.getLogger(__name__)


class ReviewVerdict(Enum):
    """Possible review verdicts."""
    APPROVED = "approved"
    NEEDS_CHANGES = "needs_changes"
    REJECTED = "rejected"


class FindingCategory(Enum):
    """Categories for review findings."""
    CORRECTNESS = "correctness"
    QUALITY = "quality"
    SECURITY = "security"
    PERFORMANCE = "performance"
    STYLE = "style"


class FindingSeverity(Enum):
    """Severity levels for findings."""
    BLOCKING = "blocking"
    MAJOR = "major"
    MINOR = "minor"
    SUGGESTION = "suggestion"


@dataclass
class CodeChange:
    """
    Represents a code change to review.
    
    Attributes:
        file_path: Path to the changed file
        change_type: Type of change (create, modify, delete)
        diff: Unified diff of the change
        content: Full content of the file (if applicable)
    """
    file_path: str = ""
    change_type: str = "modify"
    diff: str = ""
    content: str = ""


@dataclass
class StandardsReport:
    """
    Report on code standards compliance.
    
    Attributes:
        language: Programming language
        standards_checked: Standards that were checked
        violations: List of violations found
        score: Compliance score (0-100)
    """
    language: str = ""
    standards_checked: List[str] = field(default_factory=list)
    violations: List[str] = field(default_factory=list)
    score: float = 100.0


@dataclass
class ValidationReport:
    """
    Report on acceptance criteria validation.
    
    Attributes:
        criteria: List of criteria checked
        passed: Number of criteria passed
        failed: Number of criteria failed
        details: Detailed results for each criterion
    """
    criteria: List[str] = field(default_factory=list)
    passed: int = 0
    failed: int = 0
    details: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class Issue:
    """
    Detected issue in code.
    
    Attributes:
        issue_id: Unique identifier
        category: Issue category
        severity: Issue severity
        file: File where issue was found
        line: Line number
        description: Description of the issue
        recommendation: Recommended fix
    """
    issue_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    category: str = "correctness"
    severity: str = "minor"
    file: str = ""
    line: Optional[int] = None
    description: str = ""
    recommendation: str = ""


class ReviewerAgent(BaseAgent):
    """
    Reviewer Agent - Worker for quality assurance and code review.
    
    The Reviewer Agent is responsible for:
    - Reviewing code changes for quality and correctness
    - Validating acceptance criteria
    - Checking coding standards
    - Detecting bugs, security issues, and anti-patterns
    
    Capabilities:
    - Code review with checklist-based analysis
    - Acceptance criteria validation
    - Standards compliance checking
    - Issue detection
    
    Example:
        >>> reviewer = ReviewerAgent()
        >>> await reviewer.initialize()
        >>> result = await reviewer.execute(task_spec)
        >>> print(result.review_verdict)
        'approved'
    
    Attributes:
        state_machine: State machine managing reviewer state
        strict_mode: Whether to use strict review mode
        auto_fix_enabled: Whether to automatically fix minor issues
    """
    
    def __init__(
        self,
        agent_id: str = None,
        mcp_config_path: str = "~/.config/autodev/mcp_config.json",
        repo_root: str = ".",
        strict_mode: bool = True,
        auto_fix_enabled: bool = True,
        llm_config: Optional[Any] = None
    ):
        super().__init__(
            agent_id=agent_id,
            role=AgentRole.REVIEWER,
            mcp_config_path=mcp_config_path,
            repo_root=repo_root,
            llm_config=llm_config
        )
        
        # Initialize state machine
        self.state_machine = StateMachine(
            initial_state=ReviewerState.IDLE,
            valid_transitions=REVIEWER_TRANSITIONS
        )
        
        # Configuration
        self.strict_mode = strict_mode
        self.auto_fix_enabled = auto_fix_enabled
        
        # Review tracking
        self._current_review: Optional[ReviewResult] = None
        self._review_history: List[ReviewResult] = []
    
    async def initialize(self) -> None:
        """
        Initialize the Reviewer Agent.
        
        - Connects to MCP servers (filesystem, git, lsp)
        - Initializes LLM client
        - Prepares for review execution
        """
        logger.info(f"Initializing Reviewer Agent {self.agent_id}")
        
        self.update_state(AgentState.INITIALIZING)
        
        # Initialize LLM client (Phase 2)
        await self._initialize_llm()
        
        # Initialize MCP client (Phase 2)
        await self._initialize_mcp()
        
        # Initialize tool executor (Phase 2)
        await self._initialize_tool_executor(max_iterations=20)
        
        self.update_state(AgentState.IDLE)
        logger.info("Reviewer Agent initialized successfully")
    
    async def shutdown(self) -> None:
        """
        Clean shutdown of the Reviewer Agent.
        
        - Saves review history
        - Disconnects from MCP servers
        - Releases resources
        """
        logger.info(f"Shutting down Reviewer Agent {self.agent_id}")
        
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
        logger.info("Reviewer Agent shutdown complete")
    
    async def execute(self, task: TaskSpec) -> TaskResult:
        """
        Execute a review task.
        
        This is the main entry point for review execution. The reviewer
        analyzes the specified changes and provides a verdict.
        
        Args:
            task: Task specification containing changes to review
            
        Returns:
            TaskResult with the review outcome
        """
        logger.info(f"Executing review task {task.task_id}")
        
        result = TaskResult(task_id=task.task_id, status="running")
        
        try:
            # Transition to reviewing state
            self.state_machine.transition(ReviewerState.REVIEWING)
            
            # Extract code changes from task context
            # In a real implementation, this would come from git diff or task context
            code_changes = task.context.get("code_changes", []) if hasattr(task, "context") else []
            
            # Perform review
            review = await self.review_changes(code_changes)
            
            # Validate acceptance criteria if provided
            if task.constraints and "acceptance_criteria" in task.constraints:
                validation = await self.validate_acceptance_criteria(
                    code_changes,
                    task.constraints["acceptance_criteria"]
                )
                # Incorporate validation into review
                if validation.failed > 0:
                    review.verdict = "needs_changes"
                    review.blocking_issues.append(
                        f"{validation.failed} acceptance criteria not met"
                    )
            
            # Store review
            self._current_review = review
            self._review_history.append(review)
            
            # Update state based on verdict
            if review.verdict == "approved":
                self.state_machine.transition(ReviewerState.APPROVED)
            elif review.verdict == "needs_changes":
                self.state_machine.transition(ReviewerState.NEEDS_CHANGES)
            else:
                self.state_machine.transition(ReviewerState.REJECTED)
            
            # Build result
            result.status = "completed"
            result.review_verdict = review.verdict
            result.summary = review.summary
            result.result = review.to_dict()
            
        except Exception as e:
            logger.error(f"Review failed: {e}")
            result.status = "failed"
            result.error = str(e)
        
        return result
    
    # -------------------------------------------------------------------------
    # Core Capabilities
    # -------------------------------------------------------------------------
    
    async def review_changes(
        self,
        code_changes: List[CodeChange]
    ) -> ReviewResult:
        """
        Review code changes for quality and correctness.
        
        Performs a comprehensive review using the review checklist,
        checking for correctness, quality, security, and performance.
        
        Args:
            code_changes: List of code changes to review
            
        Returns:
            ReviewResult with findings and verdict
            
        Example:
            >>> changes = [
            ...     CodeChange(file_path="src/main.py", diff="...")
            ... ]
            >>> result = await reviewer.review_changes(changes)
            >>> print(result.verdict)
            'approved'
        """
        logger.info(f"Reviewing {len(code_changes)} code changes")
        
        findings: List[Finding] = []
        blocking_issues: List[str] = []
        
        for change in code_changes:
            # Perform various checks
            change_findings = await self._analyze_change(change)
            findings.extend(change_findings)
            
            # Identify blocking issues
            for finding in change_findings:
                if finding.severity == "blocking":
                    blocking_issues.append(
                        f"{finding.file}: {finding.description}"
                    )
        
        # Determine overall verdict
        verdict = self._determine_verdict(findings)
        
        # Generate summary
        summary = self._generate_summary(findings, verdict)
        
        return ReviewResult(
            task_id=str(uuid.uuid4()),
            verdict=verdict,
            findings=findings,
            summary=summary,
            blocking_issues=blocking_issues
        )
    
    async def validate_acceptance_criteria(
        self,
        changes: List[CodeChange],
        criteria: List[str]
    ) -> ValidationReport:
        """
        Check if changes meet acceptance criteria.
        
        Validates each criterion against the implemented changes.
        
        Args:
            changes: Code changes to validate
            criteria: List of acceptance criteria
            
        Returns:
            ValidationReport with results
            
        Example:
            >>> criteria = [
            ...     "Users can log in with email",
            ...     "Password must be at least 8 characters"
            ... ]
            >>> report = await reviewer.validate_acceptance_criteria(changes, criteria)
            >>> print(f"Passed: {report.passed}/{len(criteria)}")
        """
        logger.info(f"Validating {len(criteria)} acceptance criteria")
        
        details: List[Dict[str, Any]] = []
        passed = 0
        failed = 0
        
        for criterion in criteria:
            # TODO: Implement actual criterion validation using LLM
            # This would analyze the changes to determine if each criterion is met
            is_passed = True  # Placeholder
            
            details.append({
                "criterion": criterion,
                "passed": is_passed,
                "evidence": "To be implemented"
            })
            
            if is_passed:
                passed += 1
            else:
                failed += 1
        
        return ValidationReport(
            criteria=criteria,
            passed=passed,
            failed=failed,
            details=details
        )
    
    async def check_standards(
        self,
        code: str,
        language: str
    ) -> StandardsReport:
        """
        Verify code follows style and quality standards.
        
        Checks for compliance with language-specific standards
        (e.g., PEP 8 for Python, Google Style Guide for Go).
        
        Args:
            code: Code to check
            language: Programming language
            
        Returns:
            StandardsReport with compliance results
            
        Example:
            >>> report = await reviewer.check_standards(code, "python")
            >>> print(f"Compliance score: {report.score}%")
        """
        logger.info(f"Checking standards for {language} code")
        
        # TODO: Implement actual standards checking
        # This could use:
        # - Linters (pylint, eslint, golangci-lint)
        # - Formatters (black, prettier, gofmt)
        # - Static analysis tools
        
        standards_checked = []
        violations = []
        
        if language == "python":
            standards_checked = ["PEP 8", "Type hints", "Docstrings"]
        elif language == "go":
            standards_checked = ["gofmt", "go vet", "Effective Go"]
        elif language in ["javascript", "typescript"]:
            standards_checked = ["ESLint", "Prettier"]
        
        return StandardsReport(
            language=language,
            standards_checked=standards_checked,
            violations=violations,
            score=100.0 - len(violations) * 5
        )
    
    async def detect_issues(self, code: str) -> List[Issue]:
        """
        Identify bugs, security issues, and anti-patterns.
        
        Scans code for common issues including:
        - Potential bugs
        - Security vulnerabilities
        - Anti-patterns
        - Performance issues
        
        Args:
            code: Code to analyze
            
        Returns:
            List of detected issues
            
        Example:
            >>> issues = await reviewer.detect_issues(code)
            >>> for issue in issues:
            ...     print(f"{issue.severity}: {issue.description}")
        """
        logger.info("Detecting issues in code")
        
        issues: List[Issue] = []
        
        # TODO: Implement actual issue detection using LLM
        # This would analyze the code for:
        # - Unhandled exceptions
        # - SQL injection vulnerabilities
        # - XSS vulnerabilities
        # - Memory leaks
        # - Race conditions
        # - N+1 queries
        # - Code smells
        
        return issues
    
    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------
    
    async def _analyze_change(self, change: CodeChange) -> List[Finding]:
        """
        Analyze a single code change for issues.
        
        Args:
            change: Code change to analyze
            
        Returns:
            List of findings
        """
        findings: List[Finding] = []
        
        # TODO: Implement comprehensive analysis
        # 1. Check correctness
        # 2. Check quality
        # 3. Check security
        # 4. Check performance
        # 5. Check style
        
        # Placeholder - would use LLM for actual analysis
        if change.diff:
            # Analyze diff for common issues
            pass
        
        return findings
    
    def _determine_verdict(self, findings: List[Finding]) -> str:
        """
        Determine overall review verdict based on findings.
        
        Args:
            findings: List of findings from review
            
        Returns:
            Verdict string (approved, needs_changes, rejected)
        """
        has_blocking = any(f.severity == "blocking" for f in findings)
        has_major = any(f.severity == "major" for f in findings)
        
        if has_blocking:
            return ReviewVerdict.REJECTED.value
        elif has_major:
            return ReviewVerdict.NEEDS_CHANGES.value
        else:
            return ReviewVerdict.APPROVED.value
    
    def _generate_summary(
        self,
        findings: List[Finding],
        verdict: str
    ) -> str:
        """
        Generate a human-readable summary of the review.
        
        Args:
            findings: List of findings
            verdict: Review verdict
            
        Returns:
            Summary string
        """
        if not findings:
            return "No issues found. Code approved."
        
        by_severity = {}
        for f in findings:
            by_severity[f.severity] = by_severity.get(f.severity, 0) + 1
        
        summary_parts = []
        for severity in ["blocking", "major", "minor", "suggestion"]:
            if severity in by_severity:
                summary_parts.append(f"{by_severity[severity]} {severity}")
        
        return f"Found {', '.join(summary_parts)} issues. Verdict: {verdict}"
    
    def get_review_checklist(self) -> str:
        """
        Get the review checklist template.
        
        Returns:
            Markdown-formatted checklist
        """
        return """# REVIEWER AGENT - Code Review Task

## Changes Under Review
{git_diff}

## Original Requirements
{requirements}

## Review Checklist

### 1. Correctness
- [ ] Does the code do what it's supposed to do?
- [ ] Are edge cases handled?
- [ ] Is error handling appropriate?

### 2. Quality
- [ ] Is the code readable and maintainable?
- [ ] Are naming conventions followed?
- [ ] Is there unnecessary complexity?

### 3. Security
- [ ] Are there potential security vulnerabilities?
- [ ] Is input validation present?
- [ ] Are sensitive data handled correctly?

### 4. Testing
- [ ] Are there sufficient tests?
- [ ] Do tests cover edge cases?
- [ ] Is test coverage adequate?

### 5. Performance
- [ ] Are there obvious performance issues?
- [ ] Is resource usage appropriate?

## Output Format
{
  "overall_verdict": "approved|needs_changes|rejected",
  "findings": [...],
  "recommendations": [...],
  "blocking_issues": [...]
}
"""
    
    async def read_file(self, file_path: str) -> str:
        """
        Read a file using MCP filesystem server.
        
        Args:
            file_path: Path to file
            
        Returns:
            File contents
        """
        # TODO: Use MCP filesystem server
        return ""
    
    async def get_git_diff(self, file_path: str = None) -> str:
        """
        Get git diff using MCP git server.
        
        Args:
            file_path: Optional specific file path
            
        Returns:
            Git diff string
        """
        # TODO: Use MCP git server
        return ""
    
    async def run_linter(
        self,
        file_path: str,
        linter: str = None
    ) -> List[Issue]:
        """
        Run linter on a file.
        
        Args:
            file_path: Path to file
            linter: Linter to use (auto-detected if not specified)
            
        Returns:
            List of issues found
        """
        # TODO: Run linter via MCP terminal server
        return []
