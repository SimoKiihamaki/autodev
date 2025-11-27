"""Session Startup Protocol - Verification sequence run at the start of every agent session.

This module implements the session startup protocol from Anthropic's
"Effective Harnesses for Long-Running Agents". Every agent session begins with
this verification sequence:

1. Verify working directory
2. Review git history
3. Load feature spec (tracker)
4. Check environment health
5. Run baseline tests
6. Select next feature

This ensures consistent state before any work begins.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from .checkpoint import prd_changed_since_checkpoint
from .command import run_cmd
from .git_ops import git_current_branch, git_head_sha, git_root, git_status_snapshot
from .logging_utils import logger
from .tracker_generator import (
    compute_prd_hash,
    get_next_feature,
    get_tracker_path,
    load_tracker,
)


@dataclass
class StepResult:
    """Result of a single startup step."""

    step: str
    success: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    duration_seconds: float = 0.0


@dataclass
class StartupResult:
    """Result of the complete startup sequence."""

    success: bool
    steps: list[StepResult] = field(default_factory=list)
    failed_at: str | None = None
    tracker: dict[str, Any] | None = None
    next_feature: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def can_proceed(self) -> bool:
        """Check if we can proceed with work after startup."""
        return self.success and self.tracker is not None


class SessionStartup:
    """Session startup protocol - run at the beginning of every agent session.

    This protocol ensures consistent state before any work begins by:
    1. Verifying the working directory is correct
    2. Reviewing git history for context
    3. Loading the feature tracker
    4. Checking environment health
    5. Running baseline tests
    6. Selecting the next feature to work on

    Usage:
        startup = SessionStartup(repo_root, prd_path)
        result = startup.execute()
        if result.can_proceed:
            print(f"Ready to work on: {result.next_feature['name']}")
        else:
            print(f"Startup failed at: {result.failed_at}")
    """

    # Steps to execute in order
    STEPS: ClassVar[list[str]] = [
        "verify_working_directory",
        "review_git_history",
        "load_tracker",
        "check_environment_health",
        "run_baseline_tests",
        "select_next_feature",
    ]

    def __init__(
        self,
        repo_root: Path,
        prd_path: Path | None = None,
        checkpoint: dict[str, Any] | None = None,
        skip_tests: bool = False,
        require_clean: bool = False,
    ):
        """Initialize the startup protocol.

        Args:
            repo_root: Repository root directory
            prd_path: Path to PRD file (for hash verification)
            checkpoint: Checkpoint to resume from (optional)
            skip_tests: Skip baseline tests for faster startup
            require_clean: Require clean working directory
        """
        self.repo_root = repo_root
        self.prd_path = prd_path
        self.checkpoint = checkpoint
        self.skip_tests = skip_tests
        self.require_clean = require_clean

        self.tracker: dict[str, Any] | None = None
        self.next_feature: dict[str, Any] | None = None
        self.warnings: list[str] = []

    def execute(self) -> StartupResult:
        """Execute the full startup sequence.

        Returns:
            StartupResult with success status and any collected data
        """
        import time

        results: list[StepResult] = []
        failed_at: str | None = None

        logger.info("Starting session startup protocol")

        for step_name in self.STEPS:
            start_time = time.time()

            try:
                step_method = getattr(self, step_name)
                result = step_method()
                result.duration_seconds = time.time() - start_time
                results.append(result)

                if not result.success:
                    failed_at = step_name
                    logger.error(
                        "Startup failed at step: %s - %s", step_name, result.message
                    )
                    break
                else:
                    logger.info(
                        "Startup step %s completed (%.2fs)",
                        step_name,
                        result.duration_seconds,
                    )
            except Exception as e:
                result = StepResult(
                    step=step_name,
                    success=False,
                    message=f"Exception: {e}",
                    duration_seconds=time.time() - start_time,
                )
                results.append(result)
                failed_at = step_name
                logger.exception("Startup step %s raised exception", step_name)
                break

        success = failed_at is None
        logger.info(
            "Startup sequence %s%s",
            "completed successfully" if success else "failed",
            f" at {failed_at}" if failed_at else "",
        )

        return StartupResult(
            success=success,
            steps=results,
            failed_at=failed_at,
            tracker=self.tracker,
            next_feature=self.next_feature,
            warnings=self.warnings,
        )

    def verify_working_directory(self) -> StepResult:
        """Step 1: Verify we're in the correct working directory."""
        details: dict[str, Any] = {}

        # Check repo_root exists
        if not self.repo_root.exists():
            return StepResult(
                step="verify_working_directory",
                success=False,
                message=f"Repository root does not exist: {self.repo_root}",
            )

        # Check it's a git repo
        try:
            actual_root = git_root()
            details["git_root"] = str(actual_root)

            if actual_root.resolve() != self.repo_root.resolve():
                return StepResult(
                    step="verify_working_directory",
                    success=False,
                    message=f"Git root mismatch: expected {self.repo_root}, got {actual_root}",
                    details=details,
                )
        except Exception as e:
            return StepResult(
                step="verify_working_directory",
                success=False,
                message=f"Not a git repository: {e}",
            )

        # Check PRD exists if specified
        if self.prd_path and not self.prd_path.exists():
            return StepResult(
                step="verify_working_directory",
                success=False,
                message=f"PRD file not found: {self.prd_path}",
                details=details,
            )

        details["prd_path"] = str(self.prd_path) if self.prd_path else None

        return StepResult(
            step="verify_working_directory",
            success=True,
            message="Working directory verified",
            details=details,
        )

    def review_git_history(self) -> StepResult:
        """Step 2: Review git history for context."""
        details: dict[str, Any] = {}

        try:
            # Get current branch
            current_branch = git_current_branch(self.repo_root)
            details["current_branch"] = current_branch

            # Get HEAD SHA
            head_sha = git_head_sha(self.repo_root)
            details["head_sha"] = head_sha

            # Get working directory status
            status = git_status_snapshot(self.repo_root)
            details["dirty_files"] = len(status)
            details["status_snapshot"] = list(status)[:10]  # Limit for readability

            # Check for uncommitted changes
            if status and self.require_clean:
                return StepResult(
                    step="review_git_history",
                    success=False,
                    message=f"Working directory has {len(status)} uncommitted changes",
                    details=details,
                )
            elif status:
                self.warnings.append(
                    f"Working directory has {len(status)} uncommitted changes"
                )

            # Get recent commits for context
            try:
                out, *_ = run_cmd(
                    ["git", "log", "--oneline", "-5"],
                    cwd=self.repo_root,
                    check=True,
                )
                details["recent_commits"] = out.strip().split("\n")
            except subprocess.CalledProcessError:
                details["recent_commits"] = []

            return StepResult(
                step="review_git_history",
                success=True,
                message=f"On branch {current_branch} at {head_sha[:7]}",
                details=details,
            )
        except Exception as e:
            return StepResult(
                step="review_git_history",
                success=False,
                message=f"Failed to review git history: {e}",
                details=details,
            )

    def load_tracker(self) -> StepResult:
        """Step 3: Load the feature tracker."""
        details: dict[str, Any] = {}

        tracker_path = get_tracker_path(self.repo_root)
        details["tracker_path"] = str(tracker_path)

        # Check tracker exists
        if not tracker_path.exists():
            return StepResult(
                step="load_tracker",
                success=False,
                message="Tracker not found - run initializer first",
                details=details,
            )

        # Load tracker
        tracker = load_tracker(self.repo_root)
        if not tracker:
            return StepResult(
                step="load_tracker",
                success=False,
                message="Failed to load tracker (invalid JSON?)",
                details=details,
            )

        # Verify PRD hash matches (if PRD path provided)
        if self.prd_path:
            current_hash = compute_prd_hash(self.prd_path)
            stored_hash = tracker.get("metadata", {}).get("prd_hash", "")
            details["current_prd_hash"] = current_hash
            details["stored_prd_hash"] = stored_hash

            if current_hash != stored_hash:
                self.warnings.append(
                    f"PRD content has changed since tracker was generated "
                    f"(stored: {stored_hash}, current: {current_hash})"
                )

        # Check for checkpoint PRD changes
        if self.checkpoint:
            if self.prd_path is not None and self.prd_path.exists():
                if prd_changed_since_checkpoint(self.checkpoint, self.prd_path):
                    self.warnings.append("PRD has changed since checkpoint was created")
            else:
                self.warnings.append(
                    "Cannot verify PRD changes against checkpoint: PRD path not available"
                )

        # Store tracker for later steps
        self.tracker = tracker

        # Collect summary stats
        features = tracker.get("features", [])
        details["total_features"] = len(features)
        details["features_by_status"] = {}
        for feature in features:
            status = feature.get("status", "unknown")
            details["features_by_status"][status] = (
                details["features_by_status"].get(status, 0) + 1
            )

        return StepResult(
            step="load_tracker",
            success=True,
            message=f"Loaded tracker with {len(features)} features",
            details=details,
        )

    def check_environment_health(self) -> StepResult:
        """Step 4: Check environment health."""
        details: dict[str, Any] = {}

        # Check for required tools
        required_tools = ["git", "gh"]
        optional_tools = ["make", "npm", "pnpm", "pytest", "codex", "claude"]

        missing_required: list[str] = []
        available_optional: list[str] = []

        for tool in required_tools:
            if not self._command_exists(tool):
                missing_required.append(tool)

        for tool in optional_tools:
            if self._command_exists(tool):
                available_optional.append(tool)

        details["missing_required"] = missing_required
        details["available_tools"] = available_optional

        if missing_required:
            return StepResult(
                step="check_environment_health",
                success=False,
                message=f"Missing required tools: {', '.join(missing_required)}",
                details=details,
            )

        # Check for .aprd directory
        aprd_dir = self.repo_root / ".aprd"
        details["aprd_dir_exists"] = aprd_dir.exists()

        # Check environment variables
        env_vars = {
            "CI": os.getenv("CI"),
            "AUTO_PRD_CODEX_TIMEOUT_SECONDS": os.getenv(
                "AUTO_PRD_CODEX_TIMEOUT_SECONDS"
            ),
            "AUTO_PRD_CLAUDE_TIMEOUT_SECONDS": os.getenv(
                "AUTO_PRD_CLAUDE_TIMEOUT_SECONDS"
            ),
        }
        details["env_vars"] = {k: v for k, v in env_vars.items() if v}

        return StepResult(
            step="check_environment_health",
            success=True,
            message=f"Environment healthy ({len(available_optional)} optional tools available)",
            details=details,
        )

    def run_baseline_tests(self) -> StepResult:
        """Step 5: Run baseline tests."""
        details: dict[str, Any] = {}

        if self.skip_tests:
            return StepResult(
                step="run_baseline_tests",
                success=True,
                message="Baseline tests skipped (skip_tests=True)",
                details={"skipped": True},
            )

        # Try common test commands
        test_commands = [
            (["make", "ci"], self.repo_root / "Makefile"),
            (["make", "test"], self.repo_root / "Makefile"),
            (["npm", "test"], self.repo_root / "package.json"),
            (["pnpm", "test"], self.repo_root / "package.json"),
            (["pytest", "-x", "-q"], self.repo_root / "pyproject.toml"),
            (["go", "test", "./..."], self.repo_root / "go.mod"),
        ]

        for cmd, marker_file in test_commands:
            if marker_file.exists():
                try:
                    logger.info("Running baseline tests: %s", " ".join(cmd))
                    out, _, exit_code = run_cmd(
                        cmd,
                        cwd=self.repo_root,
                        check=False,
                        timeout=300,
                    )
                    details["command"] = cmd
                    details["exit_code"] = exit_code
                    details["output_lines"] = len(out.split("\n")) if out else 0

                    if exit_code == 0:
                        return StepResult(
                            step="run_baseline_tests",
                            success=True,
                            message=f"Baseline tests passed ({' '.join(cmd)})",
                            details=details,
                        )
                    else:
                        # Tests failed - this is a problem
                        self.warnings.append(
                            f"Baseline tests failed with exit code {exit_code}"
                        )
                        # Still continue but warn
                        return StepResult(
                            step="run_baseline_tests",
                            success=True,  # Don't block on test failures
                            message=f"Baseline tests failed (exit code {exit_code})",
                            details=details,
                        )
                except subprocess.TimeoutExpired:
                    return StepResult(
                        step="run_baseline_tests",
                        success=False,
                        message="Baseline tests timed out after 300s",
                        details=details,
                    )
                except FileNotFoundError:
                    continue

        # No test command found - that's okay
        return StepResult(
            step="run_baseline_tests",
            success=True,
            message="No test command found (skipping baseline tests)",
            details={"no_tests_found": True},
        )

    def select_next_feature(self) -> StepResult:
        """Step 6: Select the next feature to work on."""
        details: dict[str, Any] = {}

        if not self.tracker:
            return StepResult(
                step="select_next_feature",
                success=False,
                message="No tracker loaded - cannot select feature",
                details=details,
            )

        # Get next available feature
        next_feature = get_next_feature(self.tracker)
        self.next_feature = next_feature

        if not next_feature:
            # Check if all features are complete
            features = self.tracker.get("features", [])
            completed = sum(
                1 for f in features if f.get("status") in ("completed", "verified")
            )
            details["completed_features"] = completed
            details["total_features"] = len(features)

            if completed == len(features):
                return StepResult(
                    step="select_next_feature",
                    success=True,
                    message="All features completed!",
                    details=details,
                )
            else:
                # Some features are blocked
                blocked = [f for f in features if f.get("status") == "blocked"]
                details["blocked_features"] = [f.get("id") for f in blocked]
                return StepResult(
                    step="select_next_feature",
                    success=True,
                    message=f"{len(blocked)} features are blocked",
                    details=details,
                )

        details["selected_feature"] = {
            "id": next_feature.get("id"),
            "name": next_feature.get("name"),
            "priority": next_feature.get("priority"),
            "complexity": next_feature.get("complexity"),
            "status": next_feature.get("status"),
            "tasks_count": len(next_feature.get("tasks", [])),
        }

        return StepResult(
            step="select_next_feature",
            success=True,
            message=f"Selected feature {next_feature['id']}: {next_feature['name']}",
            details=details,
        )

    def _command_exists(self, cmd: str) -> bool:
        """Check if a command exists in PATH."""
        try:
            run_cmd(["which", cmd], cwd=self.repo_root, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False


def run_startup(
    repo_root: Path,
    prd_path: Path | None = None,
    checkpoint: dict[str, Any] | None = None,
    skip_tests: bool = False,
    require_clean: bool = False,
) -> StartupResult:
    """Convenience function to run the startup protocol.

    Args:
        repo_root: Repository root directory
        prd_path: Path to PRD file (optional)
        checkpoint: Checkpoint to resume from (optional)
        skip_tests: Skip baseline tests for faster startup
        require_clean: Require clean working directory

    Returns:
        StartupResult with startup status
    """
    startup = SessionStartup(
        repo_root=repo_root,
        prd_path=prd_path,
        checkpoint=checkpoint,
        skip_tests=skip_tests,
        require_clean=require_clean,
    )
    return startup.execute()
