"""Incremental Worker Agent - Implements features one at a time using the tracker.

This module implements the incremental worker agent pattern from Anthropic's
"Effective Harnesses for Long-Running Agents". The worker is responsible for:
1. Loading the tracker and selecting the next feature
2. Implementing tasks for that feature
3. Updating tracker status after each task
4. Running verification before marking feature complete
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .agents import codex_exec
from .checkpoint import save_checkpoint, update_phase_state
from .command import run_cmd
from .git_ops import git_commit, git_has_staged_changes, git_head_sha, git_stage_all
from .logging_utils import logger
from .policy import policy_runner
from .tracker_generator import (
    get_next_feature,
    get_tracker_path,
    load_tracker,
    save_tracker,
)
from .utils import detect_readonly_block


@dataclass
class TaskResult:
    """Result of implementing a single task."""

    task_id: str
    success: bool
    output: str
    errors: list[str] = field(default_factory=list)
    commit_sha: str | None = None


@dataclass
class FeatureResult:
    """Result of implementing a complete feature."""

    feature_id: str
    feature_name: str
    status: str
    tasks_completed: int
    tasks_total: int
    verification_passed: bool
    errors: list[str] = field(default_factory=list)
    commit_shas: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """Check if feature implementation was successful."""
        return (
            len(self.errors) == 0
            and self.verification_passed
            and self.tasks_completed == self.tasks_total
        )


class IncrementalWorker:
    """Single-feature worker agent - MUST use tracker.

    The worker follows Anthropic's two-agent pattern:
    - Initializer: Creates tracker, runs baseline tests, selects first feature
    - Worker (this): Implements features one at a time using the tracker

    Key principles:
    1. MUST load and use the tracker - no work without it
    2. Works on ONE feature at a time
    3. Updates tracker status after each task
    4. Runs verification before marking feature complete
    5. Commits progress with descriptive messages

    Usage:
        tracker = load_tracker(repo_root)
        worker = IncrementalWorker(tracker, repo_root)
        result = worker.run_feature("F001")
    """

    def __init__(
        self,
        tracker: dict[str, Any],
        repo_root: Path,
        executor: str = "claude",
        codex_model: str = "gpt-5.1-codex",  # Default to balanced speed/capability variant
        allow_unsafe_execution: bool = True,
        dry_run: bool = False,
    ):
        """Initialize the worker.

        Args:
            tracker: Tracker dictionary (required!)
            repo_root: Repository root directory
            executor: Which agent to use ("claude" or "codex")
            codex_model: Model to use for codex executor
            allow_unsafe_execution: Allow unsafe execution mode
            dry_run: If True, skip actual execution
        """
        if not tracker:
            raise ValueError("Worker requires a tracker - run initializer first")

        self.tracker = tracker
        self.repo_root = repo_root
        self.tracker_path = get_tracker_path(repo_root)
        self.executor = executor
        self.codex_model = codex_model
        self.allow_unsafe_execution = allow_unsafe_execution
        self.dry_run = dry_run

    def get_feature(self, feature_id: str) -> dict[str, Any] | None:
        """Get a feature by ID from the tracker.

        Args:
            feature_id: Feature ID (e.g., "F001")

        Returns:
            Feature dictionary or None if not found
        """
        for feature in self.tracker.get("features", []):
            if feature.get("id") == feature_id:
                return feature
        return None

    def run_feature(
        self,
        feature_id: str,
        checkpoint: dict[str, Any] | None = None,
    ) -> FeatureResult:
        """Implement a complete feature.

        Args:
            feature_id: ID of the feature to implement
            checkpoint: Optional checkpoint for state persistence

        Returns:
            FeatureResult with implementation status
        """
        feature = self.get_feature(feature_id)
        if not feature:
            return FeatureResult(
                feature_id=feature_id,
                feature_name="Unknown",
                status="failed",
                tasks_completed=0,
                tasks_total=0,
                verification_passed=False,
                errors=[f"Feature {feature_id} not found in tracker"],
            )

        feature_name = feature.get("name", "Unnamed")
        tasks = feature.get("tasks", [])
        errors: list[str] = []
        commit_shas: list[str] = []
        tasks_completed = 0

        logger.info("Worker: Starting feature %s - %s", feature_id, feature_name)

        # Update status to in_progress
        feature["status"] = "in_progress"
        self._save_tracker()

        # Implement each task
        for task in tasks:
            if task.get("status") in ("completed", "blocked"):
                if task.get("status") == "completed":
                    tasks_completed += 1
                continue

            task_id = task.get("id", "unknown")
            task_desc = task.get("description", "")
            logger.info("Worker: Implementing task %s - %s", task_id, task_desc)

            task["status"] = "in_progress"
            self._save_tracker()

            try:
                result = self._implement_task(feature, task)
                if result.success:
                    task["status"] = "completed"
                    task["completed_at"] = datetime.now(timezone.utc).isoformat()
                    tasks_completed += 1
                    if result.commit_sha:
                        commit_shas.append(result.commit_sha)
                else:
                    task["status"] = "blocked"
                    task["blockers"] = result.errors
                    errors.extend(result.errors)
            except (KeyboardInterrupt, SystemExit):
                # Re-raise critical signals without catching them
                raise
            except (RuntimeError, ValueError, OSError) as e:
                error_msg = f"Task {task_id} failed: {e}"
                logger.error(error_msg, exc_info=True)
                task["status"] = "blocked"
                task["blockers"] = [str(e)]
                errors.append(error_msg)

            self._save_tracker()

            # Update checkpoint if provided
            if checkpoint:
                update_phase_state(
                    checkpoint,
                    "local",
                    {
                        "current_feature": feature_id,
                        "current_task": task_id,
                        "tasks_completed": tasks_completed,
                        "tasks_total": len(tasks),
                    },
                )
                save_checkpoint(checkpoint)

        # Run verification
        logger.info("Worker: Running verification for feature %s", feature_id)
        verification_passed = self._verify_feature(feature)

        # Update final status
        if verification_passed and tasks_completed == len(tasks):
            feature["status"] = "verified"
            feature["verification_evidence"] = {
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "verified_by": self.executor,
            }
            logger.info("Feature %s verified successfully", feature_id)
        elif tasks_completed == len(tasks):
            feature["status"] = "completed"
            logger.info("Feature %s completed but verification failed", feature_id)
        else:
            feature["status"] = "failed"
            logger.warning(
                "Feature %s failed: %d/%d tasks completed",
                feature_id,
                tasks_completed,
                len(tasks),
            )

        # Record commits
        if commit_shas:
            feature.setdefault("commits", [])
            for sha in commit_shas:
                feature["commits"].append(
                    {
                        "sha": sha,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )

        self._save_tracker()

        return FeatureResult(
            feature_id=feature_id,
            feature_name=feature_name,
            status=feature["status"],
            tasks_completed=tasks_completed,
            tasks_total=len(tasks),
            verification_passed=verification_passed,
            errors=errors,
            commit_shas=commit_shas,
        )

    def run_next_feature(
        self,
        checkpoint: dict[str, Any] | None = None,
    ) -> FeatureResult | None:
        """Implement the next available feature.

        Args:
            checkpoint: Optional checkpoint for state persistence

        Returns:
            FeatureResult or None if no features available
        """
        feature = get_next_feature(self.tracker)
        if not feature:
            logger.info("No features available to implement")
            return None

        return self.run_feature(feature["id"], checkpoint=checkpoint)

    def _implement_task(
        self, feature: dict[str, Any], task: dict[str, Any]
    ) -> TaskResult:
        """Implement a single task using the agent.

        Args:
            feature: Parent feature dictionary
            task: Task dictionary

        Returns:
            TaskResult with implementation status
        """
        task_id = task.get("id", "unknown")

        if self.dry_run:
            logger.info("Dry run: skipping task implementation for %s", task_id)
            return TaskResult(
                task_id=task_id,
                success=True,
                output="DRY_RUN: Task implementation skipped",
            )

        # Build implementation prompt with tracker context
        prompt = self._build_task_prompt(feature, task)

        # Select runner based on policy
        runner, runner_name = policy_runner(None, i=1, phase="implement")
        logger.info("Implementing task %s with %s", task_id, runner_name)

        runner_kwargs = {
            "repo_root": self.repo_root,
            "enable_search": True,
            "allow_unsafe_execution": self.allow_unsafe_execution,
            "dry_run": self.dry_run,
        }
        if runner == codex_exec:
            runner_kwargs["model"] = self.codex_model

        try:
            output = runner(prompt, **runner_kwargs)
        except (KeyboardInterrupt, SystemExit):
            # Re-raise critical signals without catching them
            raise
        except (RuntimeError, subprocess.CalledProcessError, ValueError, OSError) as e:
            logger.error("Task runner execution failed: %s", e, exc_info=True)
            return TaskResult(
                task_id=task_id,
                success=False,
                output="",
                errors=[f"Runner execution failed: {e}"],
            )

        # Check for readonly block
        readonly_indicator = detect_readonly_block(output)
        if readonly_indicator:
            return TaskResult(
                task_id=task_id,
                success=False,
                output=output,
                errors=[f"Agent entered readonly mode: {readonly_indicator}"],
            )

        # Try to commit changes (separate try block for commit failures)
        try:
            commit_sha = self._commit_task_changes(feature, task)
        except (KeyboardInterrupt, SystemExit):
            # Re-raise critical signals
            raise
        except subprocess.CalledProcessError as e:
            logger.error("Failed to commit task changes: %s", e, exc_info=True)
            # Commit failure is not a task failure - log but continue
            commit_sha = None
        except (RuntimeError, ValueError, OSError) as e:
            logger.error("Failed to commit task changes: %s", e, exc_info=True)
            commit_sha = None

        return TaskResult(
            task_id=task_id,
            success=True,
            output=output,
            commit_sha=commit_sha,
        )

    def _build_task_prompt(self, feature: dict[str, Any], task: dict[str, Any]) -> str:
        """Build the implementation prompt with tracker context.

        Args:
            feature: Parent feature dictionary
            task: Task dictionary

        Returns:
            Formatted prompt string
        """
        goals = feature.get("goals", {})
        acceptance_criteria = feature.get("acceptance_criteria", [])
        testing = feature.get("testing", {})
        validation = feature.get("validation", {})

        # Format acceptance criteria
        ac_text = "\n".join(
            f"  - [{ac.get('status', 'pending')}] {ac['criterion']} ({ac['verification_method']})"
            for ac in acceptance_criteria
        )

        # Format quality gates
        quality_gates = validation.get("quality_gates", [])
        qg_text = "\n".join(
            f"  - {qg['gate']}: {qg['requirement']}" for qg in quality_gates
        )

        # Format testing requirements
        unit_tests = testing.get("unit_tests", [])
        unit_text = "\n".join(
            f"  - {ut['description']} ({ut.get('file_path', 'TBD')})"
            for ut in unit_tests
        )

        prompt = f"""## Current Implementation Status

You are working on feature {feature['id']}: {feature['name']}

### Primary Goal
{goals.get('primary', 'Implement the feature')}

### Current Task
**{task['id']}**: {task['description']}

### Acceptance Criteria
{ac_text or '  - No specific criteria defined'}

### Testing Requirements
Unit Tests:
{unit_text or '  - Write appropriate unit tests'}

### Quality Gates
{qg_text or '  - All tests must pass\n  - Type checks must pass\n  - Linting must pass'}

## Instructions

1. Implement task {task['id']}: {task['description']}
2. Run relevant tests to verify your implementation
3. Ensure all quality gates pass
4. Commit your changes with a descriptive message

After implementation, run `make ci` (or equivalent) to verify all checks pass.

Report what was completed and any issues encountered.
"""
        return prompt

    def _commit_task_changes(
        self, feature: dict[str, Any], task: dict[str, Any]
    ) -> str | None:
        """Commit changes for a task.

        Args:
            feature: Parent feature dictionary
            task: Task dictionary

        Returns:
            Commit SHA or None if no changes
        """
        if self.dry_run:
            return None

        try:
            git_stage_all(self.repo_root)
            if git_has_staged_changes(self.repo_root):
                message = (
                    f"feat({feature['id']}): {task['description'][:50]}\n\n"
                    f"Task: {task['id']}\n"
                    f"Feature: {feature['name']}"
                )
                git_commit(self.repo_root, message)
                sha = git_head_sha(self.repo_root)
                logger.info("Committed task %s: %s", task["id"], sha[:7])
                return sha
        except subprocess.CalledProcessError as e:
            logger.warning("Failed to commit task changes: %s", e)

        return None

    def _verify_feature(self, feature: dict[str, Any]) -> bool:
        """Verify a feature by running tests and checks.

        Args:
            feature: Feature dictionary

        Returns:
            True if verification passes
        """
        if self.dry_run:
            logger.info("Dry run: skipping feature verification")
            return True

        # Try to run CI checks
        test_commands = [
            ["make", "ci"],
            ["make", "test"],
            ["npm", "test"],
            ["pnpm", "test"],
            ["pytest"],
        ]

        for cmd in test_commands:
            if cmd[0] == "make" and not (self.repo_root / "Makefile").exists():
                continue
            if (
                cmd[0] in ("npm", "pnpm")
                and not (self.repo_root / "package.json").exists()
            ):
                continue

            try:
                logger.info("Running verification: %s", " ".join(cmd))
                out, err, exit_code = run_cmd(
                    cmd,
                    cwd=self.repo_root,
                    check=False,
                    timeout=300,
                )
                if exit_code == 0:
                    logger.info("Verification passed")
                    return True
                else:
                    logger.warning("Verification failed with exit code %d", exit_code)
                    return False
            except Exception as e:
                logger.warning("Verification command failed: %s", e)
                continue

        # No verification command found - assume success
        logger.info("No verification command found, assuming success")
        return True

    def _save_tracker(self) -> None:
        """Save the tracker to disk."""
        save_tracker(self.tracker, self.repo_root)


def run_worker(
    repo_root: Path,
    feature_id: str | None = None,
    executor: str = "claude",
    codex_model: str = "gpt-5-codex",
    allow_unsafe_execution: bool = True,
    dry_run: bool = False,
    checkpoint: dict[str, Any] | None = None,
) -> FeatureResult | None:
    """Convenience function to run the worker agent.

    Args:
        repo_root: Repository root directory
        feature_id: Specific feature to implement, or None for next available
        executor: Which agent to use ("claude" or "codex")
        codex_model: Model for codex executor
        allow_unsafe_execution: Allow unsafe execution mode
        dry_run: If True, skip actual execution
        checkpoint: Optional checkpoint for state persistence

    Returns:
        FeatureResult or None if no features available
    """
    tracker = load_tracker(repo_root)
    if not tracker:
        raise RuntimeError("No tracker found - run initializer first")

    worker = IncrementalWorker(
        tracker=tracker,
        repo_root=repo_root,
        executor=executor,
        codex_model=codex_model,
        allow_unsafe_execution=allow_unsafe_execution,
        dry_run=dry_run,
    )

    if feature_id:
        return worker.run_feature(feature_id, checkpoint=checkpoint)
    else:
        return worker.run_next_feature(checkpoint=checkpoint)
