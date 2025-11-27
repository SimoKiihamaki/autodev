"""Initializer Agent - First-run setup agent that creates tracker and prepares workspace.

This module implements the initializer agent pattern from Anthropic's
"Effective Harnesses for Long-Running Agents". The initializer is responsible for:
1. Generating the implementation tracker from the PRD
2. Committing the tracker to git
3. Running baseline tests
4. Selecting the first feature to implement
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .checkpoint import save_checkpoint, update_phase_state
from .command import run_cmd
from .git_ops import git_commit, git_has_staged_changes
from .logging_utils import logger
from .tracker_generator import (
    generate_tracker,
    get_next_feature,
    get_tracker_path,
    load_tracker,
    update_feature_status,
)
from .utils import extract_called_process_error_details


@dataclass
class InitResult:
    """Result of initializer agent run."""

    tracker: dict[str, Any]
    tracker_path: Path
    baseline_passed: bool
    baseline_output: str
    next_feature: dict[str, Any] | None
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """Check if initialization was successful."""
        return len(self.errors) == 0 and self.tracker is not None


@dataclass
class BaselineResult:
    """Result of baseline test run."""

    success: bool
    output: str
    exit_code: int
    errors: list[str] = field(default_factory=list)


class InitializerAgent:
    """First-run setup agent - creates tracker and prepares workspace.

    The initializer agent follows Anthropic's two-agent pattern:
    - Initializer (this): Creates tracker, runs baseline tests, selects first feature
    - Worker: Implements features one at a time using the tracker

    Usage:
        agent = InitializerAgent(repo_root, executor="claude")
        result = agent.run(prd_path)
        if result.success:
            print(f"Ready to implement: {result.next_feature['name']}")
    """

    def __init__(
        self,
        repo_root: Path,
        executor: str = "claude",
        allow_unsafe_execution: bool = True,
        dry_run: bool = False,
    ):
        """Initialize the agent.

        Args:
            repo_root: Repository root directory
            executor: Which agent to use ("claude" or "codex")
            allow_unsafe_execution: Allow unsafe execution mode
            dry_run: If True, skip actual execution
        """
        self.repo_root = repo_root
        self.executor = executor
        self.allow_unsafe_execution = allow_unsafe_execution
        self.dry_run = dry_run

    def run(
        self,
        prd_path: Path,
        force_regenerate: bool = False,
        checkpoint: dict[str, Any] | None = None,
    ) -> InitResult:
        """Run the initializer agent.

        Args:
            prd_path: Path to the PRD file
            force_regenerate: Force tracker regeneration even if exists
            checkpoint: Optional checkpoint for state persistence

        Returns:
            InitResult with tracker, baseline results, and next feature
        """
        errors: list[str] = []
        tracker: dict[str, Any] | None = None
        tracker_path = get_tracker_path(self.repo_root)
        baseline_result = BaselineResult(success=True, output="", exit_code=0)
        next_feature: dict[str, Any] | None = None

        # Step 1: Generate or load tracker
        logger.info("Initializer: Step 1 - Generate/load tracker")
        try:
            tracker = self._generate_or_load_tracker(prd_path, force_regenerate)
            logger.info(
                "Tracker ready: %d features, %d tasks",
                tracker["validation_summary"]["total_features"],
                tracker["validation_summary"]["total_tasks"],
            )
        except Exception as e:
            error_msg = f"Failed to generate tracker: {e}"
            logger.error(error_msg)
            errors.append(error_msg)
            return InitResult(
                tracker={},
                tracker_path=tracker_path,
                baseline_passed=False,
                baseline_output="",
                next_feature=None,
                errors=errors,
            )

        # Step 2: Commit tracker to git
        logger.info("Initializer: Step 2 - Commit tracker")
        try:
            self._commit_tracker()
        except Exception as e:
            logger.warning("Failed to commit tracker: %s", e)
            # Non-fatal - continue even if commit fails

        # Update checkpoint if provided
        if checkpoint:
            update_phase_state(
                checkpoint,
                "local",
                {
                    "tracker_generated": True,
                    "tracker_path": str(tracker_path),
                    "tracker_features": tracker["validation_summary"]["total_features"],
                    "tracker_tasks": tracker["validation_summary"]["total_tasks"],
                },
            )
            save_checkpoint(checkpoint)

        # Step 3: Run baseline tests
        logger.info("Initializer: Step 3 - Run baseline tests")
        try:
            baseline_result = self._run_baseline_tests()
            if not baseline_result.success:
                logger.warning(
                    "Baseline tests failed (exit code %d)", baseline_result.exit_code
                )
                # Non-fatal - we can still proceed
        except Exception as e:
            logger.warning("Failed to run baseline tests: %s", e)
            baseline_result = BaselineResult(
                success=False, output=str(e), exit_code=-1, errors=[str(e)]
            )

        # Step 4: Select first feature
        logger.info("Initializer: Step 4 - Select first feature")
        next_feature = get_next_feature(tracker)
        if next_feature:
            logger.info(
                "Selected feature %s: %s (priority: %s, complexity: %s)",
                next_feature["id"],
                next_feature["name"],
                next_feature.get("priority", "unknown"),
                next_feature.get("complexity", "unknown"),
            )
            # Mark feature as in_progress
            update_feature_status(
                tracker, next_feature["id"], "in_progress", self.repo_root
            )
        else:
            logger.warning("No features available to implement")

        # Update checkpoint with initialization results
        if checkpoint:
            update_phase_state(
                checkpoint,
                "local",
                {
                    "initialization_complete": True,
                    "baseline_passed": baseline_result.success,
                    "next_feature_id": next_feature["id"] if next_feature else None,
                },
            )
            save_checkpoint(checkpoint)

        return InitResult(
            tracker=tracker,
            tracker_path=tracker_path,
            baseline_passed=baseline_result.success,
            baseline_output=baseline_result.output,
            next_feature=next_feature,
            errors=errors,
        )

    def _generate_or_load_tracker(
        self, prd_path: Path, force: bool = False
    ) -> dict[str, Any]:
        """Generate or load the implementation tracker.

        Args:
            prd_path: Path to the PRD file
            force: Force regeneration even if exists

        Returns:
            Tracker dictionary

        Raises:
            ValueError: If tracker generation fails
        """
        existing = load_tracker(self.repo_root)
        if existing and not force:
            logger.info("Using existing tracker")
            return existing

        logger.info("Generating new tracker from PRD")
        return generate_tracker(
            prd_path=prd_path,
            repo_root=self.repo_root,
            executor=self.executor,
            force=force,
            dry_run=self.dry_run,
            allow_unsafe_execution=self.allow_unsafe_execution,
        )

    def _commit_tracker(self) -> None:
        """Commit the tracker to git."""
        if self.dry_run:
            logger.info("Dry run: skipping tracker commit")
            return

        tracker_path = get_tracker_path(self.repo_root)
        if not tracker_path.exists():
            logger.warning("Tracker file does not exist, cannot commit")
            return

        try:
            run_cmd(["git", "add", str(tracker_path)], cwd=self.repo_root)
            if git_has_staged_changes(self.repo_root):
                git_commit(
                    self.repo_root, "chore(aprd): initialize implementation tracker"
                )
                logger.info("Committed tracker to git")
            else:
                logger.debug("No tracker changes to commit")
        except subprocess.CalledProcessError as e:
            details = extract_called_process_error_details(e)
            logger.warning("Failed to commit tracker: %s", details)

    def _run_baseline_tests(self) -> BaselineResult:
        """Run baseline tests to verify repo state.

        Returns:
            BaselineResult with test output and status
        """
        if self.dry_run:
            logger.info("Dry run: skipping baseline tests")
            return BaselineResult(
                success=True, output="DRY_RUN: Baseline tests skipped", exit_code=0
            )

        # Try common test commands in order of preference
        test_commands = [
            ["make", "ci"],
            ["make", "test"],
            ["npm", "test"],
            ["pnpm", "test"],
            ["yarn", "test"],
            ["pytest"],
            ["go", "test", "./..."],
            ["cargo", "test"],
        ]

        for cmd in test_commands:
            # Check if command exists
            if not self._command_exists(cmd[0]):
                continue

            # For make targets, check if Makefile exists
            if cmd[0] == "make" and not (self.repo_root / "Makefile").exists():
                continue

            # For npm/pnpm/yarn, check if package.json exists
            if cmd[0] in ("npm", "pnpm", "yarn"):
                if not (self.repo_root / "package.json").exists():
                    continue

            logger.info("Running baseline tests: %s", " ".join(cmd))
            try:
                out, err, exit_code = run_cmd(
                    cmd,
                    cwd=self.repo_root,
                    check=False,
                    timeout=300,  # 5 minute timeout for tests
                )
                output = out + ("\n" + err if err else "")
                return BaselineResult(
                    success=(exit_code == 0),
                    output=output,
                    exit_code=exit_code,
                )
            except subprocess.TimeoutExpired:
                return BaselineResult(
                    success=False,
                    output="Baseline tests timed out after 300 seconds",
                    exit_code=-1,
                    errors=["Test timeout"],
                )
            except Exception as e:
                logger.warning("Baseline test command failed: %s", e)
                continue

        # No test command found
        logger.info("No test command found, assuming baseline passes")
        return BaselineResult(
            success=True,
            output="No test command found; assuming baseline passes",
            exit_code=0,
        )

    def _command_exists(self, cmd: str) -> bool:
        """Check if a command exists in PATH."""
        try:
            run_cmd(["which", cmd], cwd=self.repo_root, check=True)
            return True
        except subprocess.CalledProcessError:
            return False


def run_initializer(
    prd_path: Path,
    repo_root: Path,
    executor: str = "claude",
    allow_unsafe_execution: bool = True,
    dry_run: bool = False,
    force_regenerate: bool = False,
    checkpoint: dict[str, Any] | None = None,
) -> InitResult:
    """Convenience function to run the initializer agent.

    Args:
        prd_path: Path to the PRD file
        repo_root: Repository root directory
        executor: Which agent to use ("claude" or "codex")
        allow_unsafe_execution: Allow unsafe execution mode
        dry_run: If True, skip actual execution
        force_regenerate: Force tracker regeneration
        checkpoint: Optional checkpoint for state persistence

    Returns:
        InitResult with tracker and next feature
    """
    agent = InitializerAgent(
        repo_root=repo_root,
        executor=executor,
        allow_unsafe_execution=allow_unsafe_execution,
        dry_run=dry_run,
    )
    return agent.run(prd_path, force_regenerate=force_regenerate, checkpoint=checkpoint)
