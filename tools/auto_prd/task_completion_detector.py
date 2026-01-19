"""Automatic task completion detection based on multiple signals.

This module analyzes implementation evidence to determine if a task
was actually completed, not just claimed complete.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .git_ops import git_head_sha, git_status_snapshot
from .tracker_generator import load_tracker


def detect_completed_task_from_changes(
    tracker: dict[str, Any],
    repo_root: Path,
    assigned_task_id: str,
    assigned_feature_id: str,
    before_status: tuple[str, ...],
    after_status: tuple[str, ...],
    before_head: str,
    after_head: str,
) -> dict[str, Any]:
    """Analyze changes to detect if assigned task was completed.

    Args:
        tracker: Current tracker state
        repo_root: Repository root directory
        assigned_task_id: Task ID assigned to this iteration
        assigned_feature_id: Feature ID for this iteration
        before_status: Git status before implementation
        after_status: Git status after implementation
        before_head: Git HEAD before implementation
        after_head: Git HEAD after implementation

    Returns:
        Detection result dict with keys:
        - completed: bool (detected as completed)
        - confidence: float (0.0-1.0)
        - evidence: list[str] (supporting evidence)
        - actual_task_id: str | None (detected task ID if different)
    """
    result = {
        "completed": False,
        "confidence": 0.0,
        "evidence": [],
        "actual_task_id": None,
    }

    # Evidence 1: Git changes detected
    if before_status != after_status or before_head != after_head:
        result["evidence"].append("Git changes detected")
        result["confidence"] += 0.3

    # Evidence 2: Tracker already updated (agent manually updated)
    for feature in tracker.get("features", []):
        if feature.get("id") == assigned_feature_id:
            for task in feature.get("tasks", []):
                if task.get("id") == assigned_task_id:
                    if task.get("status") == "completed":
                        result["evidence"].append(
                            f"Task {assigned_task_id} already marked completed in tracker"
                        )
                        result["confidence"] += 0.5
                        result["completed"] = True

    # Evidence 3: Check if changes match task files
    # This requires accessing the feature's file mapping
    for feature in tracker.get("features", []):
        if feature.get("id") == assigned_feature_id:
            files_to_create = set(feature.get("files", {}).get("to_create", []))
            files_to_modify = set(feature.get("files", {}).get("to_modify", []))

            # Extract changed files from git status
            changed_files = set()
            for line in after_status:
                if len(line) >= 4:  # git status --porcelain format
                    filepath = line[3:] if line[0:2] in ("  ", "??") else line[3:]
                    changed_files.add(filepath.strip())

            # Check overlap
            relevant_changes = changed_files & (files_to_create | files_to_modify)
            if relevant_changes:
                result["evidence"].append(
                    f"Changes to {len(relevant_changes)} task-relevant files detected"
                )
                result["confidence"] += 0.2

    # Determine completion based on confidence threshold
    CONFIDENCE_THRESHOLD = 0.5

    if result["confidence"] >= CONFIDENCE_THRESHOLD:
        result["completed"] = True

    return result


def validate_tasks_left_progression(
    previous_tasks_left: int | None,
    current_tasks_left: int | None,
    iteration: int,
) -> tuple[bool, str]:
    """Validate that TASKS_LEFT progression is reasonable.

    Args:
        previous_tasks_left: Tasks left from previous iteration
        current_tasks_left: Tasks left from current iteration
        iteration: Current iteration number

    Returns:
        Tuple of (is_valid, error_message)
    """
    # If no previous value, cannot validate
    if previous_tasks_left is None:
        return (True, "")

    # If current value missing, that's OK (agent stopped reporting)
    if current_tasks_left is None:
        return (True, "")

    # Check 1: TASKS_LEFT should not increase
    if current_tasks_left > previous_tasks_left:
        return (
            False,
            f"TASKS_LEFT increased from {previous_tasks_left} to {current_tasks_left} "
            f"between iterations. Agent may be confused.",
        )

    # Check 2: Large decreases are suspicious
    decrease = previous_tasks_left - current_tasks_left
    if decrease > 10:
        return (
            False,
            f"TASKS_LEFT decreased by {decrease} (from {previous_tasks_left} to {current_tasks_left}). "
            "Large decreases suggest agent hallucination.",
        )

    # Check 3: Tasks left should not be negative
    if current_tasks_left < 0:
        return (
            False,
            f"TASKS_LEFT is negative ({current_tasks_left}). Invalid value.",
        )

    return (True, "")
