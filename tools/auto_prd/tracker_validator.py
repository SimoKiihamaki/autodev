"""Tracker state validation and repair utilities.

This module provides validation functions to ensure tracker.json state
remains consistent with actual implementation progress.
"""

from __future__ import annotations

from typing import Any


class TrackerValidationError(Exception):
    """Raised when tracker state is invalid."""


def _as_list(value: Any) -> list[Any]:
    """Coerce value to a list, returning empty list if not already a list."""
    return value if isinstance(value, list) else []


def validate_tracker_state(tracker: dict[str, Any]) -> list[str]:
    """Validate tracker state and return list of issues.

    Args:
        tracker: Tracker dictionary to validate

    Returns:
        List of error messages (empty if valid)
    """
    issues: list[str] = []

    # Check 1: Verify completed tasks have timestamps
    for feature in _as_list(tracker.get("features", [])):
        if not isinstance(feature, dict):
            issues.append("Tracker feature entry is not an object")
            continue
        for task in _as_list(feature.get("tasks", [])):
            if not isinstance(task, dict):
                continue
            if task.get("status") == "completed":
                if not task.get("completed_at"):
                    issues.append(
                        f"Task {task.get('id')} marked completed "
                        f"but missing completed_at timestamp"
                    )

    # Check 2: Verify feature status matches task status
    for feature in _as_list(tracker.get("features", [])):
        if not isinstance(feature, dict):
            continue
        feature_status = feature.get("status")
        tasks = _as_list(feature.get("tasks", []))

        if feature_status == "completed":
            completed_count = sum(
                1
                for t in tasks
                if isinstance(t, dict) and t.get("status") == "completed"
            )
            if completed_count != len(tasks):
                issues.append(
                    f"Feature {feature.get('id')} marked completed "
                    f"but only {completed_count}/{len(tasks)} tasks completed"
                )

        # Check 3: Feature cannot be verified if tasks are pending
        if feature_status == "verified":
            pending_count = sum(
                1
                for t in tasks
                if isinstance(t, dict) and t.get("status") != "completed"
            )
            if pending_count > 0:
                issues.append(
                    f"Feature {feature.get('id')} marked verified "
                    f"but {pending_count} tasks are not completed"
                )

    # Check 4: Validate TASKS_LEFT vs tracker state
    completed_tasks = sum(
        1
        for f in _as_list(tracker.get("features", []))
        if isinstance(f, dict)
        for t in _as_list(f.get("tasks", []))
        if isinstance(t, dict) and t.get("status") == "completed"
    )
    total_tasks = sum(
        len(_as_list(f.get("tasks", [])))
        for f in _as_list(tracker.get("features", []))
        if isinstance(f, dict)
    )

    if total_tasks > 0 and completed_tasks == 0:
        # This is OK for initial state, but should be flagged if running
        pass  # Will be caught by iteration-level validation

    return issues


def validate_completion_consistency(
    tracker: dict[str, Any],
    agent_tasks_left: int | None,
    agent_completed: bool,
) -> tuple[bool, str]:
    """Validate that agent completion claims match tracker state.

    Args:
        tracker: Current tracker state
        agent_tasks_left: Tasks left reported by agent
        agent_completed: Whether agent claims completion

    Returns:
        Tuple of (is_consistent, error_message)
    """
    # Count actual completion
    completed_tasks = sum(
        1
        for f in _as_list(tracker.get("features", []))
        if isinstance(f, dict)
        for t in _as_list(f.get("tasks", []))
        if isinstance(t, dict) and t.get("status") == "completed"
    )
    total_tasks = sum(
        len(_as_list(f.get("tasks", [])))
        for f in _as_list(tracker.get("features", []))
        if isinstance(f, dict)
    )

    # Case 1: Agent claims 0 tasks left but tracker shows no progress
    # Guard: empty tracker (total_tasks == 0) shouldn't be considered inconsistent
    if total_tasks > 0 and agent_tasks_left == 0 and completed_tasks == 0:
        return (
            False,
            "Agent claims TASKS_LEFT=0 but tracker shows 0 completed tasks. "
            "Tracker state is inconsistent.",
        )

    # Case 2: Agent claims completion but no tasks completed
    # Guard: empty tracker (total_tasks == 0) shouldn't be considered inconsistent
    if total_tasks > 0 and agent_completed and completed_tasks == 0:
        return (
            False,
            "Agent claims completion but tracker shows 0 completed tasks. "
            "Tracker state is inconsistent.",
        )

    # Case 3: Agent claims fewer tasks than tracker shows pending
    if agent_tasks_left is not None:
        pending_tasks = total_tasks - completed_tasks
        if agent_tasks_left < pending_tasks:
            return (
                False,
                f"Agent reports TASKS_LEFT={agent_tasks_left} but tracker shows "
                f"{pending_tasks} pending tasks. Agent may have missed tasks.",
            )

    # Case 4: All checks passed
    return (True, "")


def repair_tracker_state(
    tracker: dict[str, Any],
    iteration: int,
) -> tuple[bool, str, dict[str, Any]]:
    """Attempt to repair common tracker state issues.

    This function is side-effect free - it returns a repaired tracker
    but does not persist it. The caller must decide whether to save.

    Args:
        tracker: Tracker dictionary to repair
        iteration: Current iteration number (for logging)

    Returns:
        Tuple of (success, message, repaired_tracker)
    """
    import copy

    repaired = copy.deepcopy(tracker)
    changes: list[str] = []

    # Repair 1: Remove completed_at from non-completed tasks
    for feature in _as_list(repaired.get("features", [])):
        if not isinstance(feature, dict):
            continue
        for task in _as_list(feature.get("tasks", [])):
            if not isinstance(task, dict):
                continue
            if task.get("completed_at") and task.get("status") != "completed":
                del task["completed_at"]
                changes.append(f"Removed completed_at from task {task.get('id')}")

    # Repair 2: Fix inconsistent feature status
    for feature in _as_list(repaired.get("features", [])):
        if not isinstance(feature, dict):
            continue
        feature_status = feature.get("status")
        tasks = _as_list(feature.get("tasks", []))

        completed_count = sum(
            1 for t in tasks if isinstance(t, dict) and t.get("status") == "completed"
        )

        # If all tasks completed but feature not marked completed
        if (
            tasks
            and completed_count == len(tasks)
            and feature_status
            in (
                "pending",
                "in_progress",
            )
        ):
            feature["status"] = "completed"
            changes.append(f"Marked feature {feature.get('id')} as completed")

        # If no tasks completed but feature marked completed
        if (
            tasks
            and completed_count == 0
            and feature_status in ("completed", "verified")
        ):
            feature["status"] = "pending"
            changes.append(f"Reset feature {feature.get('id')} to pending")

    if changes:
        message = f"Repaired tracker state in iteration {iteration}: " + "; ".join(
            changes
        )
        return (True, message, repaired)

    return (False, "No repairs needed", tracker)


def calculate_completion_confidence(
    tracker: dict[str, Any],
    task_id: str,
    changes_detected: bool,
    tasks_left_delta: int | None,
) -> float:
    """Calculate confidence score (0.0 to 1.0) that a task was completed.

    Args:
        tracker: Current tracker state
        task_id: Task ID that was supposed to be completed
        changes_detected: Whether git changes were detected
        tasks_left_delta: Change in tasks_left value (None if not reported)

    Returns:
        Confidence score between 0.0 (low confidence) and 1.0 (high confidence)
    """
    confidence = 0.0

    # Factor 1: Task status in tracker (weight: 0.4)
    task_found = False
    for feature in _as_list(tracker.get("features", [])):
        if not isinstance(feature, dict):
            continue
        for task in _as_list(feature.get("tasks", [])):
            if not isinstance(task, dict):
                continue
            if task.get("id") == task_id:
                if task.get("status") == "completed":
                    confidence += 0.4
                task_found = True
                break
        if task_found:
            break

    # Factor 2: Git changes detected (weight: 0.3)
    if changes_detected:
        confidence += 0.3

    # Factor 3: TASKS_LEFT decreased (weight: 0.3)
    if tasks_left_delta is not None and tasks_left_delta < 0:
        confidence += 0.3

    return min(confidence, 1.0)
