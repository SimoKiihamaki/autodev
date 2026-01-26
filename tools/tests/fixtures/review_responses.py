"""Mock fixtures for review round testing.

This module provides mock agent responses and git diffs for testing
the review round functionality under various scenarios.
"""

from __future__ import annotations

# ============================================================================
# Mock Agent Response Fixtures
# ============================================================================

# Successful review with all tasks confirmed
REVIEW_SUCCESSFUL = """```json
{
  "overall_assessment": "passed",
  "tasks_reviewed": [
    {
      "task_id": "T001",
      "current_status": "completed",
      "recommended_status": "completed",
      "reasoning": "Implementation is complete and working correctly",
      "findings": "Code well-structured with proper error handling"
    },
    {
      "task_id": "T002",
      "current_status": "completed",
      "recommended_status": "completed",
      "reasoning": "All acceptance criteria met",
      "findings": "Good test coverage provided"
    }
  ],
  "insights": {
    "positive": [
      "Clean code structure following project conventions",
      "Comprehensive test coverage for new features",
      "Proper error handling edge cases"
    ],
    "negative": [],
    "patterns": [
      "Consistent use of type hints",
      "Good docstring coverage"
    ]
  },
  "next_steps": [
    "Continue with next feature implementation",
    "Maintain current code quality standards"
  ],
  "summary": "All tasks completed successfully with high code quality"
}
```"""

# Partial review with some tasks needing reversion
REVIEW_PARTIAL = """```json
{
  "overall_assessment": "partial",
  "tasks_reviewed": [
    {
      "task_id": "T001",
      "current_status": "completed",
      "recommended_status": "completed",
      "reasoning": "Backend implementation is complete",
      "findings": "API endpoints implemented correctly"
    },
    {
      "task_id": "T002",
      "current_status": "completed",
      "recommended_status": "in_progress",
      "reasoning": "Login form exists but missing validation",
      "findings": "Form created but client-side validation not implemented"
    },
    {
      "task_id": "T003",
      "current_status": "in_progress",
      "recommended_status": "completed",
      "reasoning": "Database migration is actually complete",
      "findings": "Migration script tested and working"
    }
  ],
  "insights": {
    "positive": [
      "Good progress on backend implementation",
      "Database schema well-designed"
    ],
    "negative": [
      "Task T002 marked complete but missing validation logic",
      "Incomplete acceptance criteria verification"
    ],
    "patterns": [
      "Backend tasks progressing faster than frontend",
      "Need more thorough acceptance testing"
    ]
  },
  "next_steps": [
    "Add form validation to T002",
    "Verify all acceptance criteria before marking tasks complete",
    "Focus on frontend implementation next"
  ],
  "summary": "Mixed results: some tasks complete, others need work"
}
```"""

# Failed review with critical issues
REVIEW_FAILED = """```json
{
  "overall_assessment": "failed",
  "tasks_reviewed": [
    {
      "task_id": "T001",
      "current_status": "completed",
      "recommended_status": "pending",
      "reasoning": "No implementation found for this task",
      "findings": "Git diff shows no changes related to authentication"
    },
    {
      "task_id": "T002",
      "current_status": "completed",
      "recommended_status": "in_progress",
      "reasoning": "Partial implementation with critical bugs",
      "findings": "Authentication bypass vulnerability detected"
    }
  ],
  "insights": {
    "positive": [],
    "negative": [
      "Critical security vulnerability in authentication",
      "Tasks marked complete without actual implementation",
      "No tests provided for authentication logic"
    ],
    "patterns": [
      "Premature task completion",
      "Missing security review process"
    ]
  },
  "next_steps": [
    "URGENT: Fix authentication bypass vulnerability",
    "Implement actual T001 authentication logic",
    "Add comprehensive security tests",
    "Review task completion process"
  ],
  "summary": "CRITICAL: Security issues and incomplete implementation"
}
```"""

# Review output without markdown code blocks (plain JSON)
REVIEW_PLAIN_JSON = """{
  "overall_assessment": "passed",
  "tasks_reviewed": [
    {
      "task_id": "T001",
      "current_status": "completed",
      "recommended_status": "completed",
      "reasoning": "Implementation complete",
      "findings": "Code looks good"
    }
  ],
  "insights": {
    "positive": ["Good implementation"],
    "negative": [],
    "patterns": ["Clean code"]
  },
  "next_steps": ["Continue"],
  "summary": "All good"
}"""

# Review output with explanatory text before JSON
REVIEW_WITH_PREFIX = """Here's my review of the implementation:

After analyzing the git diff and comparing against task requirements, I found the following:

```json
{
  "overall_assessment": "passed",
  "tasks_reviewed": [
    {
      "task_id": "T001",
      "current_status": "completed",
      "recommended_status": "completed",
      "reasoning": "Implementation is complete",
      "findings": "All requirements met"
    }
  ],
  "insights": {
    "positive": ["Well implemented"],
    "negative": [],
    "patterns": ["Good patterns"]
  },
  "next_steps": ["Next steps"],
  "summary": "Review complete"
}
```

Let me know if you need any clarification."""

# Malformed JSON - missing closing brace
REVIEW_MALFORMED_INCOMPLETE = """```json
{
  "overall_assessment": "passed",
  "tasks_reviewed": [
    {
      "task_id": "T001",
      "current_status": "completed",
      "recommended_status": "completed",
      "reasoning": "Implementation complete",
      "findings": "Code looks good"
    }
  ],
  "insights": {
    "positive": ["Good implementation"],
    "negative": [],
    "patterns": ["Clean code"]
```"""

# Malformed JSON - invalid syntax
REVIEW_MALFORMED_SYNTAX = """```json
{
  "overall_assessment": "passed",
  "tasks_reviewed": [
    {
      "task_id": "T001",
      "current_status": "completed",
      "recommended_status": "completed",
      "reasoning": "Implementation complete",
      "findings": "Code looks good"
    }  ,,,,,,,  <- extra commas
  ],
  "insights": {
    "positive": ["Good implementation"],
    "negative": [],
    "patterns": ["Clean code"]
  },
  "next_steps": ["Continue"],
  "summary": "All good"
}
```"""

# Review output with no valid JSON at all
REVIEW_NO_JSON = """
I've reviewed the implementation but I'm unable to provide a JSON response at this time.
Please check the git diff manually for any issues.
"""

# Empty response
REVIEW_EMPTY = ""

# Review with special characters and escaped content
REVIEW_SPECIAL_CHARS = r"""```json
{
  "overall_assessment": "passed",
  "tasks_reviewed": [
    {
      "task_id": "T001",
      "current_status": "completed",
      "recommended_status": "completed",
      "reasoning": "Implementation complete with proper escaping",
      "findings": "Handles \"quotes\" and \n newlines correctly"
    }
  ],
  "insights": {
    "positive": ["Proper string handling"],
    "negative": [],
    "patterns": ["Good escape sequences"]
  },
  "next_steps": ["Continue"],
  "summary": "All good with special chars"
}
```"""

# ============================================================================
# Mock Git Diff Fixtures
# ============================================================================

# Empty git diff
GIT_DIFF_EMPTY = ""

# Small git diff - minimal changes (no triple quotes in content)
GIT_DIFF_SMALL = """diff --git a/example.py b/example.py
index 1234567..abcdefg 100644
--- a/example.py
+++ b/example.py
@@ -1,3 +1,4 @@
 def hello():
     print("Hello")
+    print("World")
     return True
"""

# Medium git diff - typical feature implementation
# Using single quotes for docstrings to avoid Python syntax conflicts
GIT_DIFF_MEDIUM = """diff --git a/tools/auto_prd/example.py b/tools/auto_prd/example.py
index 1234567..abcdefg 100644
--- a/tools/auto_prd/example.py
+++ b/tools/auto_prd/example.py
@@ -1,10 +1,25 @@
-from typing import Any
+from typing import Any, NotRequired

+
+class ReviewConfig:
+    'Configuration for review round.'
+    enabled: bool = True
+    executor: str = "claude"
+

+
 def hello():
     print("Hello")
     return True

+
+def review_round(config: ReviewConfig) -> None:
+    'Execute review round.'
+    if config.enabled:
+        print("Running review...")
+        return
+    print("Review disabled")
+
+
+if __name__ == "__main__":
+    review_round(ReviewConfig())
"""

# Large git diff - comprehensive feature implementation
# Using single quotes for docstrings to avoid conflicts
GIT_DIFF_LARGE = """diff --git a/tools/auto_prd/review_round.py b/tools/auto_prd/review_round.py
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/tools/auto_prd/review_round.py
@@ -0,0 +1,50 @@
+'Review Round module.'
+
+from __future__ import annotations
+
+import json
+from dataclasses import dataclass, field
+from datetime import datetime, timezone
+from pathlib import Path
+from typing import Any
+
+from .agents import claude_exec, codex_exec
+from .command import CalledProcessError, TimeoutExpired, run_cmd
+from .git_ops import git_head_sha
+from .logging_utils import logger
+from .tracker_generator import save_tracker
+
+
+@dataclass
+class ReviewConfig:
+    'Configuration for review round.'
+    enabled: bool = True
+    executor: str = "claude"
+    model: str = "claude-sonnet-4-5-20250514"
+    max_review_time: int = 300
+
+
+@dataclass
+class ReviewResult:
+    'Result of a review round.'
+    iteration: int
+    reviewer: str
+    timestamp: str
+    overall_status: str
+    tasks_reviewed: int
+    statuses_updated: dict[str, str] = field(default_factory=dict)
+    insights: dict[str, list[str]] = field(default_factory=dict)
+    next_steps: list[str] = field(default_factory=list)
+    git_diff_summary: str = ""
+    summary: str = ""
+
+
+class ReviewRound:
+    'Orchestrates the review round after implementation.'
+
+    def __init__(
+        self,
+        repo_root: Path,
+        config: ReviewConfig | None = None,
+    ):
+        self.repo_root = Path(repo_root)
+        self.config = config or ReviewConfig()
+
+    def execute_review(
+        self,
+        iteration: int,
+        tracker: dict[str, Any],
+        base_branch: str,
+    ) -> ReviewResult:
+        'Execute the review round.'
+        logger.info("Starting review round for iteration %d", iteration)
+
+        git_diff = self._get_git_diff(base_branch)
+
+        if not git_diff.strip():
+            logger.info("No git changes detected; skipping review round")
+            return ReviewResult(
+                iteration=iteration,
+                reviewer=self.config.executor,
+                timestamp=datetime.now(timezone.utc).isoformat(),
+                overall_status="skipped",
+                tasks_reviewed=0,
+                git_diff_summary="No changes detected",
+                summary="Review skipped: no git changes",
+            )
+
+        prompt = self._build_review_prompt(tracker, git_diff, iteration, base_branch)
+
+        try:
+            agent_output = self._call_review_agent(prompt)
+        except (CalledProcessError, TimeoutExpired) as e:
+            logger.error("Review agent failed: %s", e)
+            return ReviewResult(
+                iteration=iteration,
+                reviewer=self.config.executor,
+                timestamp=datetime.now(timezone.utc).isoformat(),
+                overall_status="failed",
+                tasks_reviewed=0,
+                git_diff_summary=f"Review agent failed: {e}",
+                summary=f"Review failed: {e}",
+            )
+
+        result = self._parse_review_result(agent_output, iteration, git_diff)
+
+        if result.statuses_updated:
+            self._apply_review_updates(tracker, result)
+
+        return result
"""

# Git diff with only comments changed
GIT_DIFF_COMMENTS_ONLY = """diff --git a/example.py b/example.py
index 1234567..abcdefg 100644
--- a/example.py
+++ b/example.py
@@ -1,5 +1,5 @@
-# Example module
+# Example module for testing
 def hello():
-    # Says hello
+    # Prints a greeting
     print("Hello")
     return True
"""

# Git diff with test file changes (using single quotes)
GIT_DIFF_TESTS = """diff --git a/tests/test_example.py b/tests/test_example.py
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/tests/test_example.py
@@ -0,0 +1,15 @@
+'Tests for example module.'
+
+import pytest
+
+
+def test_hello():
+    'Test hello function.'
+    result = hello()
+    assert result is True
+
+
+def test_review_round():
+    'Test review round execution.'
+    config = ReviewConfig()
+    review_round(config)
"""

# Git diff with binary file change
GIT_DIFF_BINARY = """diff --git a/assets/image.png b/assets/image.png
new file mode 100644
index 0000000..1234567
Binary files /dev/null and b/assets/image.png differ
"""

# ============================================================================
# Mock Tracker Fixtures
# ============================================================================

# Minimal valid tracker
TRACKER_MINIMAL = {
    "version": "2.1.0",
    "metadata": {
        "prd_source": "test.md",
        "prd_hash": "sha256:test",
        "created_at": "2026-01-25T00:00:00Z",
        "created_by": "test",
    },
    "features": [
        {
            "id": "F001",
            "name": "Test Feature",
            "status": "in_progress",
            "tasks": [{"id": "T001", "description": "Test task", "status": "pending"}],
            "acceptance_criteria": [],
        }
    ],
    "validation_summary": {
        "total_features": 1,
        "total_tasks": 1,
        "estimated_complexity": "small",
        "critical_path": ["F001"],
    },
}

# Full tracker with review fields
TRACKER_WITH_REVIEW_FIELDS = {
    "version": "2.1.0",
    "metadata": {
        "prd_source": "test.md",
        "prd_hash": "sha256:test",
        "created_at": "2026-01-25T00:00:00Z",
        "created_by": "test",
    },
    "features": [
        {
            "id": "F001",
            "name": "Test Feature",
            "status": "in_progress",
            "tasks": [
                {
                    "id": "T001",
                    "description": "Test task 1",
                    "status": "completed",
                    "completed_at": "2026-01-25T12:00:00Z",
                    "review_insights": [
                        {
                            "iteration": 1,
                            "reviewer": "claude",
                            "status": "confirmed",
                            "notes": "Implementation verified",
                            "next_steps": [],
                        }
                    ],
                },
                {
                    "id": "T002",
                    "description": "Test task 2",
                    "status": "in_progress",
                },
            ],
            "acceptance_criteria": [],
            "review_history": [
                {
                    "iteration": 1,
                    "reviewer": "claude",
                    "overall_assessment": "partial",
                    "tasks_reviewed": 2,
                    "tasks_confirmed": 1,
                    "tasks_reverted": 0,
                    "findings": ["Good progress on T001"],
                }
            ],
        }
    ],
    "review_insights": {
        "last_review_iteration": 1,
        "common_patterns": ["Clean code structure"],
        "recurring_issues": [],
    },
    "validation_summary": {
        "total_features": 1,
        "total_tasks": 2,
        "estimated_complexity": "small",
        "critical_path": ["F001"],
    },
}

# Tracker with all tasks completed
TRACKER_ALL_COMPLETED = {
    "version": "2.1.0",
    "metadata": {
        "prd_source": "test.md",
        "prd_hash": "sha256:test",
        "created_at": "2026-01-25T00:00:00Z",
        "created_by": "test",
    },
    "features": [
        {
            "id": "F001",
            "name": "Completed Feature",
            "status": "completed",
            "tasks": [
                {
                    "id": "T001",
                    "description": "Completed task",
                    "status": "completed",
                    "completed_at": "2026-01-25T12:00:00Z",
                }
            ],
            "acceptance_criteria": [
                {
                    "id": "AC001",
                    "criterion": "Test criterion",
                    "status": "passed",
                }
            ],
        }
    ],
    "validation_summary": {
        "total_features": 1,
        "total_tasks": 1,
        "estimated_complexity": "small",
        "critical_path": ["F001"],
    },
}

# ============================================================================
# Helper functions for fixtures
# ============================================================================


def get_review_response(
    status: str,
    format_type: str = "markdown",
) -> str:
    """Get a mock review response by status and format type.

    Args:
        status: Response type - "passed", "partial", "failed"
        format_type: Output format - "markdown", "plain", "prefix", "malformed"

    Returns:
        Mock review response string
    """
    responses: dict[str, dict[str, str]] = {
        "passed": {
            "markdown": REVIEW_SUCCESSFUL,
            "plain": REVIEW_PLAIN_JSON,
            "prefix": REVIEW_WITH_PREFIX,
        },
        "partial": {
            "markdown": REVIEW_PARTIAL,
            "plain": REVIEW_PARTIAL.replace("```json", "").replace("```", ""),
        },
        "failed": {
            "markdown": REVIEW_FAILED,
            "plain": REVIEW_FAILED.replace("```json", "").replace("```", ""),
        },
        "malformed": {
            "incomplete": REVIEW_MALFORMED_INCOMPLETE,
            "syntax": REVIEW_MALFORMED_SYNTAX,
            "no_json": REVIEW_NO_JSON,
            "empty": REVIEW_EMPTY,
        },
    }

    if status == "malformed":
        return responses["malformed"].get(format_type, REVIEW_NO_JSON)
    return responses.get(status, {}).get(format_type, REVIEW_SUCCESSFUL)


def get_git_diff(size: str = "medium") -> str:
    """Get a mock git diff by size.

    Args:
        size: Diff size - "empty", "small", "medium", "large", "comments_only"

    Returns:
        Mock git diff string
    """
    diffs = {
        "empty": GIT_DIFF_EMPTY,
        "small": GIT_DIFF_SMALL,
        "medium": GIT_DIFF_MEDIUM,
        "large": GIT_DIFF_LARGE,
        "comments_only": GIT_DIFF_COMMENTS_ONLY,
        "tests": GIT_DIFF_TESTS,
        "binary": GIT_DIFF_BINARY,
    }
    return diffs.get(size, GIT_DIFF_MEDIUM)


def get_tracker(tracker_type: str = "minimal") -> dict:
    """Get a mock tracker by type.

    Args:
        tracker_type: Tracker type - "minimal", "with_review", "all_completed"

    Returns:
        Mock tracker dictionary
    """
    trackers = {
        "minimal": TRACKER_MINIMAL,
        "with_review": TRACKER_WITH_REVIEW_FIELDS,
        "all_completed": TRACKER_ALL_COMPLETED,
    }
    # Return a copy to avoid mutation issues
    import copy

    return copy.deepcopy(trackers.get(tracker_type, TRACKER_MINIMAL))
