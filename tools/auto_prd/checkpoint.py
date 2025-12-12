"""Session checkpointing for resumable automation runs.

This module provides checkpoint management for long-running automation sessions,
enabling recovery from interruptions and resume capability.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .logging_utils import logger

# Checkpoint schema version for future migrations
CHECKPOINT_VERSION = 1

# Default session directory under XDG config
DEFAULT_SESSIONS_DIR = "sessions"


def get_sessions_dir() -> Path:
    """Get the sessions directory, creating if needed.

    Returns:
        Path to ~/.config/aprd/sessions/
    """
    xdg_config = os.getenv("XDG_CONFIG_HOME", None)
    if xdg_config and xdg_config.strip():
        base_config = Path(xdg_config).expanduser()
    else:
        base_config = Path.home() / ".config"

    sessions_dir = base_config / "aprd" / DEFAULT_SESSIONS_DIR
    sessions_dir.mkdir(parents=True, exist_ok=True)
    return sessions_dir


def generate_session_id(prd_path: Path) -> str:
    """Generate a unique session ID from PRD name and timestamp.

    Args:
        prd_path: Path to the PRD file.

    Returns:
        Session ID like 'prd-feature-auth-20240101-143052-abc12'
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    # Use first 5 chars of hash for uniqueness
    content_hash = hashlib.sha256(str(prd_path).encode()).hexdigest()[:5]
    stem = prd_path.stem.lower().replace("_", "-").replace(" ", "-")[:30]
    return f"prd-{stem}-{timestamp}-{content_hash}"


def compute_prd_hash(prd_path: Path) -> str:
    """Compute SHA-256 hash of PRD file contents.

    Args:
        prd_path: Path to the PRD file.

    Returns:
        Hash string like 'sha256:abc123...'
    """
    try:
        content = prd_path.read_bytes()
        hash_value = hashlib.sha256(content).hexdigest()[:16]
        return f"sha256:{hash_value}"
    except OSError as e:
        logger.warning("Failed to hash PRD file %s: %s", prd_path, e)
        return "sha256:unknown"


def get_checkpoint_path(session_id: str) -> Path:
    """Get the checkpoint file path for a session.

    Args:
        session_id: The session identifier.

    Returns:
        Path to the checkpoint JSON file.
    """
    return get_sessions_dir() / f"{session_id}.json"


def create_checkpoint(
    session_id: str,
    prd_path: Path,
    repo_root: Path,
    base_branch: str,
    feature_branch: str,
    selected_phases: set[str],
) -> dict[str, Any]:
    """Create a new checkpoint structure.

    Args:
        session_id: Unique session identifier.
        prd_path: Path to the PRD file.
        repo_root: Repository root directory.
        base_branch: Base branch name.
        feature_branch: Feature branch name.
        selected_phases: Set of phases to run.

    Returns:
        Checkpoint dictionary.
    """
    now = datetime.now(timezone.utc).isoformat()
    return {
        "version": CHECKPOINT_VERSION,
        "session_id": session_id,
        "created_at": now,
        "updated_at": now,
        "status": "in_progress",
        "prd_path": str(prd_path),
        "prd_hash": compute_prd_hash(prd_path),
        "repo_root": str(repo_root),
        "base_branch": base_branch,
        "feature_branch": feature_branch,
        "selected_phases": sorted(selected_phases),
        "current_phase": None,
        "phases": {
            "local": {
                "status": "pending",
                "started_at": None,
                "completed_at": None,
                "iteration": 0,
                "max_iters": None,
                "tasks_left": -1,
                "no_findings_streak": 0,
                "empty_change_streak": 0,
                "skipped_review_streak": 0,
                "qa_context_shared": False,
                "last_head_sha": None,
                "last_status_snapshot": [],
            },
            "pr": {
                "status": "pending",
                "started_at": None,
                "completed_at": None,
                "pr_number": None,
                "branch_pushed": False,
            },
            "review_fix": {
                "status": "pending",
                "started_at": None,
                "completed_at": None,
                "processed_comment_ids": [],
                # Wall-clock timestamp for operational visibility (e.g., user checking
                # "when was the last activity?") and for future resume heuristics.
                # NOT used for idle timeout computation - that uses in-process
                # time.monotonic() which cannot persist across process restarts.
                #
                # Rationale for inclusion in checkpoint:
                # - Helps users diagnose stalled sessions ("last activity was 3 hours ago")
                # - Could inform future "resume stale session?" prompts
                # - Minimal overhead (single float per checkpoint save)
                "last_activity_wall_clock": None,
                "cycles": 0,
            },
        },
        "git_state": {
            "stash_selector": None,
            "original_branch": None,
        },
        "errors": [],
    }


def save_checkpoint(checkpoint: dict[str, Any]) -> None:
    """Atomically save checkpoint to disk.

    Uses write-to-temp-then-rename pattern for atomicity.

    Args:
        checkpoint: Checkpoint dictionary to save.
    """
    checkpoint["updated_at"] = datetime.now(timezone.utc).isoformat()
    session_id = checkpoint["session_id"]
    target_path = get_checkpoint_path(session_id)

    # Write to temp file then rename for atomicity.
    # fd is wrapped in try-finally immediately to prevent fd leak if an exception
    # occurs before os.fdopen takes ownership of the file descriptor.
    fd, temp_path = tempfile.mkstemp(
        suffix=".json.tmp",
        prefix=f"{session_id}-",
        dir=target_path.parent,
    )
    fd_closed = False
    try:
        # os.fdopen takes ownership; fd will be closed by context manager.
        # We only mark fd_closed = True AFTER os.fdopen succeeds to ensure
        # we close the fd manually if os.fdopen itself raises an exception.
        with os.fdopen(fd, "w") as f:
            fd_closed = True
            json.dump(checkpoint, f, indent=2, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.rename(temp_path, target_path)
        logger.debug("Saved checkpoint to %s", target_path)
    except Exception:
        # Close fd if os.fdopen was never called (prevents fd leak)
        if not fd_closed:
            try:
                os.close(fd)
            except OSError:
                # Ignore errors closing fd; it may already be closed or invalid during cleanup.
                pass
        # Clean up temp file on failure
        try:
            os.unlink(temp_path)
        except OSError:
            # Ignore errors deleting temp file; it may not exist or may have already been removed.
            pass
        raise


def load_checkpoint(session_id: str) -> Optional[dict[str, Any]]:
    """Load checkpoint from disk.

    Args:
        session_id: The session identifier.

    Returns:
        Checkpoint dictionary or None if not found.
    """
    checkpoint_path = get_checkpoint_path(session_id)
    if not checkpoint_path.exists():
        return None

    try:
        with open(checkpoint_path) as f:
            checkpoint = json.load(f)
        logger.debug("Loaded checkpoint from %s", checkpoint_path)
        return checkpoint
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load checkpoint %s: %s", checkpoint_path, e)
        return None


def find_resumable_session(prd_path: Path, repo_root: Path) -> Optional[dict[str, Any]]:
    """Find the most recent in-progress session matching PRD and repo.

    Args:
        prd_path: Path to the PRD file.
        repo_root: Repository root directory.

    Returns:
        Checkpoint dictionary or None if no resumable session found.
    """
    sessions_dir = get_sessions_dir()
    if not sessions_dir.exists():
        return None

    prd_str = str(prd_path.resolve())
    repo_str = str(repo_root.resolve())

    candidates = []
    for checkpoint_file in sessions_dir.glob("*.json"):
        try:
            with open(checkpoint_file) as f:
                checkpoint = json.load(f)

            # Must be in_progress
            if checkpoint.get("status") != "in_progress":
                continue

            # Must match PRD and repo
            if checkpoint.get("prd_path") != prd_str:
                continue
            if checkpoint.get("repo_root") != repo_str:
                continue

            candidates.append(checkpoint)
        except (json.JSONDecodeError, OSError, KeyError):
            continue

    if not candidates:
        return None

    # Sort by updated_at descending, return most recent
    candidates.sort(key=lambda c: c.get("updated_at", ""), reverse=True)
    return candidates[0]


def list_sessions(
    status_filter: Optional[str] = None, limit: int = 20
) -> list[dict[str, Any]]:
    """List all sessions, optionally filtered by status.

    Args:
        status_filter: Optional status to filter by ('in_progress', 'completed', etc.)
        limit: Maximum number of sessions to return.

    Returns:
        List of checkpoint summaries (id, status, prd, updated_at).
    """
    sessions_dir = get_sessions_dir()
    if not sessions_dir.exists():
        return []

    sessions = []
    for checkpoint_file in sessions_dir.glob("*.json"):
        try:
            with open(checkpoint_file) as f:
                checkpoint = json.load(f)

            status = checkpoint.get("status", "unknown")
            if status_filter and status != status_filter:
                continue

            sessions.append(
                {
                    "session_id": checkpoint.get("session_id", checkpoint_file.stem),
                    "status": status,
                    "prd_path": checkpoint.get("prd_path", "unknown"),
                    "current_phase": checkpoint.get("current_phase"),
                    "updated_at": checkpoint.get("updated_at", ""),
                    "created_at": checkpoint.get("created_at", ""),
                }
            )
        except (json.JSONDecodeError, OSError):
            continue

    # Sort by updated_at descending
    sessions.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
    return sessions[:limit]


def update_phase_state(
    checkpoint: dict[str, Any], phase: str, updates: dict[str, Any]
) -> None:
    """Update a specific phase's state in the checkpoint.

    Args:
        checkpoint: Checkpoint dictionary to update (modified in place).
        phase: Phase name ('local', 'pr', 'review_fix').
        updates: Dictionary of updates to merge into phase state.
    """
    if phase not in checkpoint.get("phases", {}):
        logger.warning("Unknown phase %s in checkpoint", phase)
        return

    checkpoint["phases"][phase].update(updates)
    checkpoint["current_phase"] = phase


def mark_phase_started(checkpoint: dict[str, Any], phase: str) -> None:
    """Mark a phase as started.

    Args:
        checkpoint: Checkpoint dictionary to update.
        phase: Phase name.
    """
    now = datetime.now(timezone.utc).isoformat()
    update_phase_state(
        checkpoint,
        phase,
        {
            "status": "in_progress",
            "started_at": now,
        },
    )


def mark_phase_complete(checkpoint: dict[str, Any], phase: str) -> None:
    """Mark a phase as completed.

    Args:
        checkpoint: Checkpoint dictionary to update.
        phase: Phase name.
    """
    now = datetime.now(timezone.utc).isoformat()
    update_phase_state(
        checkpoint,
        phase,
        {
            "status": "completed",
            "completed_at": now,
        },
    )


def mark_session_complete(checkpoint: dict[str, Any]) -> None:
    """Mark the entire session as completed.

    Args:
        checkpoint: Checkpoint dictionary to update.
    """
    checkpoint["status"] = "completed"
    checkpoint["updated_at"] = datetime.now(timezone.utc).isoformat()


def mark_session_failed(checkpoint: dict[str, Any], error: str) -> None:
    """Mark the session as failed with error details.

    Args:
        checkpoint: Checkpoint dictionary to update.
        error: Error description.
    """
    checkpoint["status"] = "failed"
    checkpoint["errors"].append(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": error,
        }
    )


def cleanup_session(session_id: str) -> bool:
    """Delete a checkpoint file.

    Args:
        session_id: The session identifier.

    Returns:
        True if deleted, False if not found.
    """
    checkpoint_path = get_checkpoint_path(session_id)
    if checkpoint_path.exists():
        checkpoint_path.unlink()
        logger.info("Deleted checkpoint %s", checkpoint_path)
        return True
    return False


def cleanup_old_sessions(max_age_days: int = 30, keep_completed: int = 10) -> int:
    """Clean up old completed sessions.

    Args:
        max_age_days: Delete completed sessions older than this.
        keep_completed: Minimum number of completed sessions to keep.

    Returns:
        Number of sessions deleted.
    """
    sessions_dir = get_sessions_dir()
    if not sessions_dir.exists():
        return 0

    now = datetime.now(timezone.utc)
    completed_sessions = []
    deleted = 0

    for checkpoint_file in sessions_dir.glob("*.json"):
        try:
            with open(checkpoint_file) as f:
                checkpoint = json.load(f)

            status = checkpoint.get("status")
            if status != "completed":
                continue

            updated_at = checkpoint.get("updated_at", "")
            if updated_at:
                try:
                    updated = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                    age_days = (now - updated).days
                    completed_sessions.append((checkpoint_file, age_days))
                except ValueError:
                    logger.warning(
                        "Skipping checkpoint file %s: cannot parse updated_at=%r as ISO timestamp",
                        checkpoint_file,
                        updated_at,
                    )
        except (json.JSONDecodeError, OSError):
            continue

    # Sort by age descending (oldest first)
    completed_sessions.sort(key=lambda x: x[1], reverse=True)

    # Delete old sessions, keeping at least keep_completed newest.
    # After sorting oldest-first, the newest sessions are at the end.
    # We delete from the beginning (oldest) up to len - keep_completed.
    if len(completed_sessions) > keep_completed:
        to_delete = completed_sessions[: len(completed_sessions) - keep_completed]
        for checkpoint_file, age_days in to_delete:
            if age_days > max_age_days:
                try:
                    checkpoint_file.unlink()
                    deleted += 1
                except OSError as e:
                    logger.warning(
                        "Failed to delete checkpoint file %s: %s", checkpoint_file, e
                    )

    if deleted > 0:
        logger.info("Cleaned up %d old checkpoint files", deleted)

    return deleted


def prd_changed_since_checkpoint(checkpoint: dict[str, Any], prd_path: Path) -> bool:
    """Check if PRD content has changed since checkpoint was created.

    Args:
        checkpoint: Checkpoint dictionary.
        prd_path: Path to the PRD file.

    Returns:
        True if PRD has been modified.
    """
    saved_hash = checkpoint.get("prd_hash", "")
    current_hash = compute_prd_hash(prd_path)
    return saved_hash != current_hash
