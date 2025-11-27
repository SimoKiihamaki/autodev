"""Git-Based Feature Rollback - Enables surgical rollback of individual features.

This module implements the rollback capabilities described in Anthropic's
"Effective Harnesses for Long-Running Agents". Key capabilities:

1. Rollback a specific feature by reverting its commits
2. Track commit SHAs per feature in the tracker
3. Support recovery from failed feature implementations
4. Maintain a clean git history for debugging

The tracker records commit SHAs for each feature, enabling targeted rollback
without affecting other completed features.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .command import run_cmd
from .git_ops import (
    git_commit,
    git_current_branch,
    git_has_staged_changes,
    git_head_sha,
)
from .logging_utils import logger
from .tracker_generator import load_tracker, save_tracker


@dataclass
class RollbackResult:
    """Result of a rollback operation."""

    feature_id: str
    success: bool
    commits_reverted: list[str] = field(default_factory=list)
    new_commit_sha: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class CommitInfo:
    """Information about a git commit."""

    sha: str
    message: str
    timestamp: str
    author: str


def get_feature_commits(
    tracker: dict[str, Any], feature_id: str
) -> list[dict[str, Any]]:
    """Get commits associated with a feature from the tracker.

    Args:
        tracker: Tracker dictionary
        feature_id: Feature ID (e.g., "F001")

    Returns:
        List of commit dictionaries from the tracker
    """
    for feature in tracker.get("features", []):
        if feature.get("id") == feature_id:
            return feature.get("commits", [])
    return []


def get_commit_info(repo_root: Path, sha: str) -> CommitInfo | None:
    """Get information about a specific commit.

    Args:
        repo_root: Repository root directory
        sha: Commit SHA

    Returns:
        CommitInfo or None if commit not found
    """
    try:
        # Use ASCII unit separator (0x1f) as delimiter to safely handle
        # commit messages containing pipe characters
        out, _, exit_code = run_cmd(
            ["git", "log", "-1", "--format=%H%x1f%s%x1f%aI%x1f%an", sha],
            cwd=repo_root,
            check=False,
        )
        if exit_code != 0 or not out.strip():
            return None

        parts = out.strip().split("\x1f", 3)
        if len(parts) < 4:
            return None

        return CommitInfo(
            sha=parts[0],
            message=parts[1],
            timestamp=parts[2],
            author=parts[3],
        )
    except Exception as e:
        logger.warning("Failed to get commit info for %s: %s", sha, e)
        return None


def verify_commit_exists(repo_root: Path, sha: str) -> bool:
    """Verify a commit exists in the repository.

    Args:
        repo_root: Repository root directory
        sha: Commit SHA to verify

    Returns:
        True if commit exists
    """
    try:
        _, _, exit_code = run_cmd(
            ["git", "cat-file", "-t", sha],
            cwd=repo_root,
            check=False,
        )
        return exit_code == 0
    except Exception:
        return False


def verify_commits_in_history(
    repo_root: Path, shas: list[str], branch: str | None = None
) -> list[str]:
    """Verify which commits are in the current branch's history.

    Args:
        repo_root: Repository root directory
        shas: List of commit SHAs to check
        branch: Branch to check (defaults to current branch)

    Returns:
        List of SHAs that are in the branch history
    """
    if not shas:
        return []

    valid = []
    target = branch or "HEAD"

    for sha in shas:
        try:
            # Check if commit is an ancestor of the branch
            _, _, exit_code = run_cmd(
                ["git", "merge-base", "--is-ancestor", sha, target],
                cwd=repo_root,
                check=False,
            )
            if exit_code == 0:
                valid.append(sha)
        except Exception:
            continue

    return valid


def revert_commit(
    repo_root: Path,
    sha: str,
    no_commit: bool = True,
) -> tuple[bool, str]:
    """Revert a single commit.

    Args:
        repo_root: Repository root directory
        sha: Commit SHA to revert
        no_commit: If True, don't create a commit (just stage changes)

    Returns:
        Tuple of (success, error_message)
    """
    cmd = ["git", "revert", "--no-edit"]
    if no_commit:
        cmd.append("--no-commit")
    cmd.append(sha)

    try:
        out, err, exit_code = run_cmd(cmd, cwd=repo_root, check=False)
        if exit_code != 0:
            error_msg = err or out or "Unknown error"
            return False, f"Failed to revert {sha[:7]}: {error_msg}"
        return True, ""
    except Exception as e:
        return False, f"Exception reverting {sha[:7]}: {e}"


def abort_revert(repo_root: Path) -> bool:
    """Abort an in-progress revert operation.

    Args:
        repo_root: Repository root directory

    Returns:
        True if abort succeeded
    """
    try:
        _, _, exit_code = run_cmd(
            ["git", "revert", "--abort"],
            cwd=repo_root,
            check=False,
        )
        return exit_code == 0
    except Exception:
        return False


def reset_hard(repo_root: Path, ref: str = "HEAD") -> bool:
    """Hard reset to a specific ref.

    Args:
        repo_root: Repository root directory
        ref: Git ref to reset to

    Returns:
        True if reset succeeded
    """
    try:
        _, _, exit_code = run_cmd(
            ["git", "reset", "--hard", ref],
            cwd=repo_root,
            check=False,
        )
        return exit_code == 0
    except Exception:
        return False


def rollback_feature(
    tracker: dict[str, Any],
    feature_id: str,
    repo_root: Path,
    dry_run: bool = False,
) -> RollbackResult:
    """Rollback a specific feature by reverting its commits.

    Args:
        tracker: Tracker dictionary
        feature_id: Feature ID to rollback (e.g., "F001")
        repo_root: Repository root directory
        dry_run: If True, don't actually make changes

    Returns:
        RollbackResult with operation status
    """
    result = RollbackResult(feature_id=feature_id, success=False)

    # Find feature in tracker
    feature = None
    for f in tracker.get("features", []):
        if f.get("id") == feature_id:
            feature = f
            break

    if not feature:
        result.errors.append(f"Feature {feature_id} not found in tracker")
        return result

    # Get commits for this feature
    commits = feature.get("commits", [])
    if not commits:
        result.warnings.append(
            f"Feature {feature_id} has no recorded commits to revert"
        )
        # Still mark as success - nothing to do
        result.success = True
        return result

    # Extract SHAs (handle both string and dict formats)
    shas = []
    for commit in commits:
        if isinstance(commit, dict):
            sha = commit.get("sha", "")
        else:
            sha = str(commit)
        if sha:
            shas.append(sha)

    if not shas:
        result.warnings.append(f"Feature {feature_id} has no valid commit SHAs")
        result.success = True
        return result

    logger.info("Rolling back feature %s: %d commits", feature_id, len(shas))

    # Verify commits exist in history
    valid_shas = verify_commits_in_history(repo_root, shas)
    missing = set(shas) - set(valid_shas)
    if missing:
        for sha in missing:
            result.warnings.append(
                f"Commit {sha[:7]} not found in history (may have been rebased)"
            )

    if not valid_shas:
        result.errors.append("No valid commits found to revert")
        return result

    if dry_run:
        logger.info(
            "Dry run: would revert commits %s",
            ", ".join(s[:7] for s in valid_shas),
        )
        result.commits_reverted = valid_shas
        result.success = True
        return result

    # Save starting point for recovery
    start_sha = git_head_sha(repo_root)

    # Revert commits in reverse order (newest first)
    # This maintains consistency when commits depend on each other
    valid_shas_reversed = list(reversed(valid_shas))

    for sha in valid_shas_reversed:
        success, error = revert_commit(repo_root, sha, no_commit=True)
        if not success:
            # Check if it's a conflict
            if "conflict" in error.lower():
                result.errors.append(
                    f"Conflict reverting {sha[:7]}: manual resolution required"
                )
                # Abort and restore
                abort_revert(repo_root)
                reset_hard(repo_root, start_sha)
                return result
            else:
                result.errors.append(error)
                # Reset to original state before attempting other commits
                # to avoid preserving staged changes from earlier reverts
                reset_hard(repo_root, start_sha)
                continue

        result.commits_reverted.append(sha)

    if not result.commits_reverted:
        result.errors.append("No commits were successfully reverted")
        return result

    # Commit the reverts
    try:
        if git_has_staged_changes(repo_root):
            commit_msg = (
                f"revert({feature_id}): rollback feature implementation\n\n"
                f"Reverted commits:\n"
                + "\n".join(f"- {sha[:7]}" for sha in result.commits_reverted)
            )
            git_commit(repo_root, commit_msg)
            result.new_commit_sha = git_head_sha(repo_root)
            logger.info("Created rollback commit: %s", result.new_commit_sha[:7])
    except subprocess.CalledProcessError as e:
        result.errors.append(f"Failed to create rollback commit: {e}")
        reset_hard(repo_root, start_sha)
        return result

    # Update tracker
    feature["status"] = "pending"  # Reset to pending so it can be re-implemented
    feature["commits"] = []  # Clear commits
    feature["verification_evidence"] = {}  # Clear verification
    for task in feature.get("tasks", []):
        task["status"] = "pending"
        task.pop("completed_at", None)
        task.pop("blockers", None)

    # Save tracker
    save_tracker(tracker, repo_root)
    logger.info("Updated tracker: feature %s reset to pending", feature_id)

    result.success = True
    return result


def rollback_to_checkpoint(
    repo_root: Path,
    checkpoint_sha: str,
    tracker: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> RollbackResult:
    """Rollback to a specific checkpoint commit.

    This is a more aggressive rollback that resets to a specific commit,
    discarding all changes after that point.

    Args:
        repo_root: Repository root directory
        checkpoint_sha: SHA to rollback to
        tracker: Optional tracker to update
        dry_run: If True, don't actually make changes

    Returns:
        RollbackResult with operation status
    """
    result = RollbackResult(feature_id="checkpoint", success=False)

    # Verify checkpoint exists
    if not verify_commit_exists(repo_root, checkpoint_sha):
        result.errors.append(f"Checkpoint commit {checkpoint_sha} not found")
        return result

    if dry_run:
        logger.info("Dry run: would reset to %s", checkpoint_sha[:7])
        result.success = True
        return result

    # Get commits that will be lost
    try:
        out, _, _ = run_cmd(
            ["git", "log", "--format=%H", f"{checkpoint_sha}..HEAD"],
            cwd=repo_root,
            check=True,
        )
        commits_to_lose = [s for s in out.strip().split("\n") if s]
        if commits_to_lose:
            logger.warning(
                "Rollback will discard %d commits after %s",
                len(commits_to_lose),
                checkpoint_sha[:7],
            )
    except subprocess.CalledProcessError:
        result.warnings.append("Could not determine commits to be discarded")

    # Create a backup branch before destructive operation
    current_branch = git_current_branch(repo_root)
    backup_branch = f"backup/{current_branch}-{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    try:
        run_cmd(
            ["git", "branch", backup_branch],
            cwd=repo_root,
            check=True,
        )
        logger.info("Created backup branch: %s", backup_branch)
    except subprocess.CalledProcessError as e:
        result.warnings.append(f"Could not create backup branch: {e}")

    # Reset to checkpoint
    if not reset_hard(repo_root, checkpoint_sha):
        result.errors.append(f"Failed to reset to {checkpoint_sha}")
        return result

    result.new_commit_sha = checkpoint_sha
    result.success = True
    logger.info("Reset to checkpoint %s", checkpoint_sha[:7])

    # Update tracker if provided
    if tracker:
        # Mark all in_progress features as pending
        for feature in tracker.get("features", []):
            if feature.get("status") == "in_progress":
                feature["status"] = "pending"
                for task in feature.get("tasks", []):
                    if task.get("status") == "in_progress":
                        task["status"] = "pending"
        save_tracker(tracker, repo_root)

    return result


def list_rollback_candidates(tracker: dict[str, Any]) -> list[dict[str, Any]]:
    """List features that can be rolled back.

    Args:
        tracker: Tracker dictionary

    Returns:
        List of features with commits that can be reverted
    """
    candidates = []
    for feature in tracker.get("features", []):
        commits = feature.get("commits", [])
        if commits and feature.get("status") not in ("pending", "blocked"):
            candidates.append(
                {
                    "id": feature.get("id"),
                    "name": feature.get("name"),
                    "status": feature.get("status"),
                    "commit_count": len(commits),
                    "commits": commits,
                }
            )
    return candidates


def run_rollback(
    repo_root: Path,
    feature_id: str,
    dry_run: bool = False,
) -> RollbackResult:
    """Convenience function to rollback a feature.

    Args:
        repo_root: Repository root directory
        feature_id: Feature ID to rollback
        dry_run: If True, don't actually make changes

    Returns:
        RollbackResult with operation status
    """
    tracker = load_tracker(repo_root)
    if not tracker:
        return RollbackResult(
            feature_id=feature_id,
            success=False,
            errors=["No tracker found - nothing to rollback"],
        )

    return rollback_feature(tracker, feature_id, repo_root, dry_run)
