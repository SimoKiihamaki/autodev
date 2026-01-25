"""Review Round - Independent validation of implementation rounds.

This module implements a review round that runs after each implementation
pass to validate that claimed work matches actual changes and provides
actionable feedback for the next iteration.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .agents import claude_exec
from .command import CalledProcessError, TimeoutExpired, run_cmd
from .constants import HEADLESS_TOOL_ALLOWLISTS
from .git_ops import git_head_sha
from .logging_utils import logger
from .tracker_generator import save_tracker

# Review agent prompt template
REVIEW_PROMPT = """# Task: Review Implementation Round

You are a senior code reviewer conducting an impartial review of an implementation round.
Your goal is to validate that claimed work matches actual changes and provide actionable feedback.

## Context

- **Iteration**: {iteration}
- **Base Branch**: {base_branch}
- **Git SHA**: {git_sha}

## Tasks/Features to Review

{tasks_to_review}

## Current Tracker State

{tracker_summary}

## Git Diff (What Actually Changed)

```diff
{git_diff}
```

## Your Responsibilities

### 1. Validate Task Statuses

For each task marked "completed":
- Does the git diff show implementation of this task?
- Are all acceptance criteria met?
- Should status remain "completed" or revert to "in_progress"?

For each task marked "in_progress":
- Is there evidence of progress in the diff?
- Should it be marked "completed" instead?

### 2. Generate Review Insights

**What went well** (patterns to reinforce):
- Implementation patterns that should continue
- Good test coverage, documentation, etc.

**What went wrong** (issues to fix):
- Missing or incomplete implementations
- Tasks marked complete but not actually done
- Code quality issues

**Next steps** (specific actions):
- Concrete steps for the next implementation round
- Priority ordering of remaining work

## Output Format

Respond with a JSON object (no markdown, no explanation):

```json
{{
  "overall_assessment": "passed|partial|failed",
  "tasks_reviewed": [
    {{
      "task_id": "T001",
      "current_status": "completed",
      "recommended_status": "completed|in_progress|pending",
      "reasoning": "Why this status is recommended",
      "findings": "Specific observations from git diff"
    }}
  ],
  "insights": {{
    "positive": ["What went well"],
    "negative": ["What went wrong"],
    "patterns": ["Patterns observed"]
  }},
  "next_steps": ["Specific next step 1", "Specific next step 2"],
  "summary": "One-line summary of review"
}}
```

Begin your review now.
"""


# Canonical default model for review rounds - must match RalphSettings, Go config, CLI
DEFAULT_REVIEW_MODEL = "claude-sonnet-4-5-20250514"


@dataclass
class ReviewConfig:
    """Configuration for review round."""

    enabled: bool = True
    executor: str = "claude"  # claude | codex
    model: str = DEFAULT_REVIEW_MODEL
    max_review_time: int = 300  # seconds


@dataclass
class ReviewResult:
    """Result of a review round."""

    iteration: int
    reviewer: str
    timestamp: str
    overall_status: str  # passed | partial | failed | skipped
    tasks_reviewed: int
    statuses_updated: dict[str, str] = field(default_factory=dict)
    insights: dict[str, list[str]] = field(default_factory=dict)
    next_steps: list[str] = field(default_factory=list)
    git_diff_summary: str = ""
    summary: str = ""


class ReviewRound:
    """Orchestrates the review round after implementation."""

    def __init__(
        self,
        repo_root: Path,
        config: ReviewConfig | None = None,
    ):
        self.repo_root = Path(repo_root)
        self.config = config or ReviewConfig()

    def execute_review(
        self,
        iteration: int,
        tracker: dict[str, Any],
        base_branch: str,
    ) -> ReviewResult:
        """Execute the review round.

        Args:
            iteration: Current iteration number
            tracker: Current tracker dictionary
            base_branch: Base branch for diff comparison

        Returns:
            ReviewResult with validation findings
        """
        # Check if review rounds are enabled
        if not self.config.enabled:
            logger.info("Review round is disabled in config; skipping")
            return ReviewResult(
                iteration=iteration,
                reviewer=self.config.executor,
                timestamp=datetime.now(timezone.utc).isoformat(),
                overall_status="skipped",
                tasks_reviewed=0,
                git_diff_summary="Review rounds disabled",
                summary="Review skipped: disabled in config",
            )

        logger.info(
            "Starting review round for iteration %d (executor: %s)",
            iteration,
            self.config.executor,
        )

        # Get git diff
        git_diff = self._get_git_diff(base_branch)

        # Skip review if no changes
        if not git_diff.strip():
            logger.info("No git changes detected; skipping review round")
            return ReviewResult(
                iteration=iteration,
                reviewer=self.config.executor,
                timestamp=datetime.now(timezone.utc).isoformat(),
                overall_status="skipped",
                tasks_reviewed=0,
                git_diff_summary="No changes detected",
                summary="Review skipped: no git changes",
            )

        # Build review prompt
        prompt = self._build_review_prompt(
            tracker=tracker,
            git_diff=git_diff,
            iteration=iteration,
            base_branch=base_branch,
        )

        # Call reviewer agent
        try:
            agent_output = self._call_review_agent(prompt)
        except (CalledProcessError, TimeoutExpired, PermissionError) as e:
            logger.error("Review agent failed: %s", e)
            return ReviewResult(
                iteration=iteration,
                reviewer=self.config.executor,
                timestamp=datetime.now(timezone.utc).isoformat(),
                overall_status="failed",
                tasks_reviewed=0,
                git_diff_summary=f"Review agent failed: {e}",
                summary=f"Review failed: {e}",
            )

        # Parse review result
        result = self._parse_review_result(agent_output, iteration, git_diff)

        # Apply updates to tracker, even if no statuses changed, so that
        # review insights and metadata (e.g., last_review_iteration) are
        # consistently persisted for every completed review.
        if (
            result.statuses_updated
            or result.insights
            or result.overall_status in ("passed", "partial", "failed")
        ):
            self._apply_review_updates(tracker, result)

        return result

    def _get_git_diff(self, base_branch: str) -> str:
        """Get git diff against base branch.

        Tries in order:
        1. Remote branch: origin/<base_branch>
        2. Local base branch using merge-base with HEAD
        3. HEAD~1 as last resort
        4. Staged changes as final fallback
        """
        try:
            # Try remote branch first
            _, _, exit_code = run_cmd(
                [
                    "git",
                    "show-ref",
                    "--verify",
                    "--quiet",
                    f"refs/remotes/origin/{base_branch}",
                ],
                cwd=self.repo_root,
                check=False,
            )

            if exit_code == 0:
                # Compare against remote base branch
                result = run_cmd(
                    ["git", "diff", f"origin/{base_branch}"],
                    cwd=self.repo_root,
                )
                return result.stdout

            # Remote not available, try local base branch
            _, _, exit_code = run_cmd(
                [
                    "git",
                    "show-ref",
                    "--verify",
                    "--quiet",
                    f"refs/heads/{base_branch}",
                ],
                cwd=self.repo_root,
                check=False,
            )

            if exit_code == 0:
                # Use merge-base to diff against local base branch
                # This captures all changes since the branch point
                result = run_cmd(
                    ["git", "merge-base", "HEAD", base_branch],
                    cwd=self.repo_root,
                    check=False,
                )
                if result.exit_code == 0 and result.stdout.strip():
                    merge_base = result.stdout.strip()
                    result = run_cmd(
                        ["git", "diff", merge_base],
                        cwd=self.repo_root,
                    )
                    return result.stdout

            # No base branch available, use HEAD~1 as last resort
            result = run_cmd(
                ["git", "diff", "HEAD~1"],
                cwd=self.repo_root,
                check=False,
            )
            if result.exit_code == 0 and result.stdout.strip():
                logger.warning(
                    "Base branch '%s' not found locally or remotely; "
                    "using HEAD~1 for diff (may miss changes in multi-commit branches)",
                    base_branch,
                )
                return result.stdout

            # Fall back to showing staged changes
            result = run_cmd(
                ["git", "diff", "--cached"],
                cwd=self.repo_root,
            )
            return result.stdout
        except Exception as e:
            logger.warning("Failed to get git diff: %s", e)
            return f"# Error getting diff: {e}"

    def _build_review_prompt(
        self,
        tracker: dict[str, Any],
        git_diff: str,
        iteration: int,
        base_branch: str,
    ) -> str:
        """Build the review prompt for the agent."""
        # Build tasks to review section
        tasks_to_review = []
        for feature in tracker.get("features", []):
            feature_id = feature.get("id", "unknown")
            feature_name = feature.get("name", "Unknown")
            feature_status = feature.get("status", "pending")

            tasks_to_review.append(f"\n### Feature {feature_id}: {feature_name}")
            tasks_to_review.append(f"Status: {feature_status}")

            for task in feature.get("tasks", []):
                task_id = task.get("id", "unknown")
                task_desc = task.get("description", "")
                task_status = task.get("status", "pending")
                tasks_to_review.append(
                    f"- {task_id}: {task_desc} (status: {task_status})"
                )

            # Include acceptance criteria
            for ac in feature.get("acceptance_criteria", []):
                ac_id = ac.get("id", "unknown")
                ac_criterion = ac.get("criterion", "")
                ac_status = ac.get("status", "pending")
                tasks_to_review.append(
                    f"  {ac_id}: {ac_criterion} (status: {ac_status})"
                )

        # Build tracker summary
        completed_count = sum(
            1
            for f in tracker.get("features", [])
            for t in f.get("tasks", [])
            if t.get("status") == "completed"
        )
        total_tasks = sum(len(f.get("tasks", [])) for f in tracker.get("features", []))

        tracker_summary = (
            f"Total tasks: {total_tasks}\n"
            f"Completed tasks: {completed_count}\n"
            f"Tasks remaining: {total_tasks - completed_count}"
        )

        # Get git SHA
        git_sha = git_head_sha(self.repo_root)

        return REVIEW_PROMPT.format(
            iteration=iteration,
            base_branch=base_branch,
            git_sha=git_sha,
            tasks_to_review="\n".join(tasks_to_review),
            tracker_summary=tracker_summary,
            git_diff=git_diff[:50000],  # Limit diff size for prompt
        )

    def _call_review_agent(self, prompt: str) -> str:
        """Call the reviewer agent with the prompt.

        Review is read-only (analyzes diffs and returns JSON), but the executor
        requires allow_unsafe_execution=True for non-dry-run execution. The agent
        only needs to read git state and produce structured output, not modify
        files or run commands.

        Uses the configured model and timeout from ReviewConfig.
        """
        # Normalize executor to lowercase for case-insensitive comparison
        executor_normalized = (
            self.config.executor.lower() if self.config.executor else ""
        )

        # Determine the model to use
        model = self.config.model
        if executor_normalized == "codex":
            # Codex requires unsafe execution; review rounds don't support Codex
            # since it doesn't have safe read-only execution mode. Fall back to
            # Claude with a Claude-compatible model instead of forwarding the Codex model.
            logger.info(
                "Codex executor selected for review round, but Codex does not "
                "support safe read-only execution; falling back to Claude."
            )
            # Since we're falling back to Claude, update the configured executor so that
            # any persisted metadata (e.g., ReviewResult.reviewer) reflects the actual
            # reviewer used rather than the original Codex configuration.
            self.config.executor = "claude"
            # Clear the model to use Claude's default model, since a configured
            # Codex model (e.g., gpt-5-codex) will fail when passed to Claude.
            model = None

        # Apply timeout from ReviewConfig via environment variable
        # This is necessary because claude_exec reads timeout from AUTO_PRD_CLAUDE_TIMEOUT_SECONDS
        original_timeout = os.environ.get("AUTO_PRD_CLAUDE_TIMEOUT_SECONDS")
        os.environ["AUTO_PRD_CLAUDE_TIMEOUT_SECONDS"] = str(self.config.max_review_time)

        try:
            output, _ = claude_exec(
                prompt=prompt,
                repo_root=self.repo_root,
                model=model,
                allow_unsafe_execution=True,
                dry_run=False,
                # Restrict the review agent to read-only tools needed for analysis.
                # Tool names must match those exposed by the agents layer.
                allowed_tools=list(HEADLESS_TOOL_ALLOWLISTS["review_round"]),
                # Ask the model to return pure JSON to simplify parsing.
                output_format="json",
            )
        finally:
            # Restore original timeout value
            if original_timeout is None:
                os.environ.pop("AUTO_PRD_CLAUDE_TIMEOUT_SECONDS", None)
            else:
                os.environ["AUTO_PRD_CLAUDE_TIMEOUT_SECONDS"] = original_timeout

        return output

    def _parse_review_result(
        self, agent_output: str, iteration: int, git_diff: str
    ) -> ReviewResult:
        """Parse structured output from review agent."""
        # Try to extract JSON from output
        json_str = self._extract_json(agent_output)

        if not json_str:
            logger.warning("Failed to extract JSON from review output")
            return ReviewResult(
                iteration=iteration,
                reviewer=self.config.executor,
                timestamp=datetime.now(timezone.utc).isoformat(),
                overall_status="failed",
                tasks_reviewed=0,
                git_diff_summary=(
                    git_diff[:200] + "..." if len(git_diff) > 200 else git_diff
                ),
                summary="Failed to parse review output",
            )

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse review JSON: %s", e)
            return ReviewResult(
                iteration=iteration,
                reviewer=self.config.executor,
                timestamp=datetime.now(timezone.utc).isoformat(),
                overall_status="failed",
                tasks_reviewed=0,
                git_diff_summary=(
                    git_diff[:200] + "..." if len(git_diff) > 200 else git_diff
                ),
                summary=f"Invalid JSON: {e}",
            )

        # Build statuses_updated map
        statuses_updated: dict[str, str] = {}
        for task_review in data.get("tasks_reviewed", []):
            task_id = task_review.get("task_id", "")
            recommended = task_review.get("recommended_status", "")
            current = task_review.get("current_status", "")
            if recommended and current and recommended != current:
                statuses_updated[task_id] = recommended

        return ReviewResult(
            iteration=iteration,
            reviewer=self.config.executor,
            timestamp=datetime.now(timezone.utc).isoformat(),
            overall_status=data.get("overall_assessment", "partial"),
            tasks_reviewed=len(data.get("tasks_reviewed", [])),
            statuses_updated=statuses_updated,
            insights=data.get("insights", {}),
            next_steps=data.get("next_steps", []),
            git_diff_summary=(
                git_diff[:200] + "..." if len(git_diff) > 200 else git_diff
            ),
            summary=data.get("summary", ""),
        )

    def _extract_json(self, text: str) -> str | None:
        """Extract JSON from agent response, handling markdown code blocks."""
        text = text.strip()

        # Try to find JSON in markdown code block
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end > start:
                return text[start:end].strip()
        elif "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            if end > start:
                return text[start:end].strip()

        # Find the actual JSON object
        brace_start = text.find("{")
        if brace_start < 0:
            return None

        # Find matching closing brace
        depth = 0
        for i, char in enumerate(text[brace_start:], start=brace_start):
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[brace_start : i + 1]

        return None

    def _apply_review_updates(
        self, tracker: dict[str, Any], result: ReviewResult
    ) -> None:
        """Apply status updates and insights to tracker."""
        # Update task statuses
        for feature in tracker.get("features", []):
            feature_id = feature.get("id", "")

            # Check if any tasks in this feature need status updates
            feature_updated = False
            feature_tasks_in_review = 0
            feature_tasks_confirmed = 0
            feature_tasks_reverted = 0

            for task in feature.get("tasks", []):
                task_id = task.get("id", "")
                if task_id in result.statuses_updated:
                    new_status = result.statuses_updated[task_id]
                    old_status = task.get("status", "")

                    # Count this task for review statistics
                    feature_tasks_in_review += 1
                    if new_status == "completed":
                        feature_tasks_confirmed += 1
                    elif new_status in ("pending", "in_progress"):
                        feature_tasks_reverted += 1

                    # Only downgrade if the new status makes sense
                    # (e.g., completed -> in_progress is valid)
                    if new_status in ("pending", "in_progress", "completed", "blocked"):
                        task["status"] = new_status
                        if new_status == "completed":
                            task["completed_at"] = datetime.now(
                                timezone.utc
                            ).isoformat()
                        else:
                            # Clear completion timestamp when reverting to a non-completed status
                            task.pop("completed_at", None)

                        # Add review insight
                        if "review_insights" not in task:
                            task["review_insights"] = []

                        task["review_insights"].append(
                            {
                                "iteration": result.iteration,
                                "reviewer": result.reviewer,
                                "status": (
                                    "reverted"
                                    if new_status in ("pending", "in_progress")
                                    else "confirmed"
                                ),
                                "notes": f"Status changed from {old_status} to {new_status} via review round",
                                "next_steps": [],
                            }
                        )

                        feature_updated = True
                        logger.info(
                            "Updated task %s/%s status: %s -> %s",
                            feature_id,
                            task_id,
                            old_status,
                            new_status,
                        )

            # Only add review history to features that had tasks in this review
            # This prevents duplicating the same review record across unrelated features
            if feature_tasks_in_review > 0:
                if "review_history" not in feature:
                    feature["review_history"] = []

                feature["review_history"].append(
                    {
                        "iteration": result.iteration,
                        "reviewer": result.reviewer,
                        "overall_assessment": result.overall_status,
                        "tasks_reviewed": feature_tasks_in_review,
                        "tasks_confirmed": feature_tasks_confirmed,
                        "tasks_reverted": feature_tasks_reverted,
                        "findings": result.insights.get("negative", [])[:3],
                    }
                )

        # Add top-level review insights
        if "review_insights" not in tracker:
            tracker["review_insights"] = {}

        tracker["review_insights"]["last_review_iteration"] = result.iteration

        # Track patterns
        if "common_patterns" not in tracker["review_insights"]:
            tracker["review_insights"]["common_patterns"] = []

        if "recurring_issues" not in tracker["review_insights"]:
            tracker["review_insights"]["recurring_issues"] = []

        # Add new insights (avoid duplicates)
        for pattern in result.insights.get("patterns", []):
            if pattern not in tracker["review_insights"]["common_patterns"]:
                tracker["review_insights"]["common_patterns"].append(pattern)

        for issue in result.insights.get("negative", []):
            if issue not in tracker["review_insights"]["recurring_issues"]:
                tracker["review_insights"]["recurring_issues"].append(issue)

        # Save updated tracker
        save_tracker(tracker, self.repo_root)
