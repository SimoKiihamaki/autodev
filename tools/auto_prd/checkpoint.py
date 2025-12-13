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
from typing import Any, TypedDict

from .logging_utils import logger

# TypedDict definitions for checkpoint structure.
# These provide type hints and IDE support for checkpoint dictionaries.
# The actual checkpoint is still a plain dict for JSON serialization compatibility.
#
# IMPORTANT: Runtime validation note
# ----------------------------------
# These TypedDict classes are documentation-only type hints. They provide:
# - Static type checking via mypy/pyright
# - IDE autocompletion and type information
# - Clear documentation of the checkpoint schema
#
# Actual runtime validation is handled through:
# 1. The checkpoint migration system (_migrate_checkpoint, _MIGRATIONS)
#    which validates and transforms checkpoints from older schema versions
# 2. The JSON serialization layer which ensures type compatibility
# 3. Field presence checks in code that accesses checkpoint data
#
# For complex validation needs, consider using pydantic models in the future.
# The current approach balances simplicity with type safety for this use case.


class LocalPhaseState(TypedDict, total=False):
    """State for the local implementation phase."""

    status: str  # "pending", "in_progress", "completed"
    started_at: str | None
    completed_at: str | None
    iteration: int
    max_iters: int | None
    tasks_left: int
    no_findings_streak: int
    empty_change_streak: int
    skipped_review_streak: int
    qa_context_shared: bool
    last_head_sha: str | None
    last_status_snapshot: list[str]


class PRPhaseState(TypedDict, total=False):
    """State for the PR creation phase."""

    status: str  # "pending", "in_progress", "completed"
    started_at: str | None
    completed_at: str | None
    pr_number: int | None
    branch_pushed: bool


class ReviewFixPhaseState(TypedDict, total=False):
    """State for the review/fix phase."""

    status: str  # "pending", "in_progress", "completed"
    started_at: str | None
    completed_at: str | None
    processed_comment_ids: list[int]
    last_activity_wall_clock: float | None
    cycles: int
    terminated_early: bool  # Set when review loop fails consecutively


class PhasesDict(TypedDict):
    """Container for all phase states."""

    local: LocalPhaseState
    pr: PRPhaseState
    review_fix: ReviewFixPhaseState


class GitState(TypedDict, total=False):
    """Git-related state for session recovery."""

    stash_selector: str | None
    original_branch: str | None


class CheckpointError(TypedDict, total=False):
    """Error entry in checkpoint."""

    timestamp: str
    message: str


class Checkpoint(TypedDict, total=False):
    """Full checkpoint structure for session persistence.

    This TypedDict documents the expected structure of checkpoint dictionaries.
    Use this for type hints when working with checkpoint data.

    Example:
        def process_checkpoint(cp: Checkpoint) -> None:
            session_id = cp["session_id"]
            local_phase = cp["phases"]["local"]
            if local_phase["status"] == "in_progress":
                # Resume from last iteration
                pass
    """

    version: int
    session_id: str
    created_at: str
    updated_at: str
    status: str  # "in_progress", "completed", "failed"
    prd_path: str
    prd_hash: str
    repo_root: str
    base_branch: str
    feature_branch: str
    selected_phases: list[str]
    current_phase: str | None
    phases: PhasesDict
    git_state: GitState
    errors: list[CheckpointError]


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
    """Atomically save checkpoint to disk with restricted permissions.

    Uses write-to-temp-then-rename pattern for atomicity. Checkpoint files are
    created with 0600 permissions (owner read/write only) since they may contain
    sensitive data such as PRD paths, session state, and repository information.

    Args:
        checkpoint: Checkpoint dictionary to save.
    """
    checkpoint["updated_at"] = datetime.now(timezone.utc).isoformat()
    session_id = checkpoint["session_id"]
    target_path = get_checkpoint_path(session_id)

    # Set restrictive umask for temp file creation (0077 = owner only).
    # This ensures the temp file is created with 0600 permissions by default.
    old_umask = os.umask(0o077)
    try:
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
            # Ensure final file has restrictive permissions (0600)
            os.chmod(target_path, 0o600)
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
    finally:
        # Restore original umask
        os.umask(old_umask)


def _migrate_v0_to_v1(checkpoint: dict[str, Any]) -> None:
    """Migrate checkpoint from v0 (unversioned) to v1.

    Changes in v1:
    - Added 'version' field
    - Renamed review_fix.last_activity_time -> last_activity_wall_clock

    Note: Modifies checkpoint in place.
    """
    review_fix = checkpoint.get("phases", {}).get("review_fix", {})
    if (
        "last_activity_time" in review_fix
        and "last_activity_wall_clock" not in review_fix
    ):
        review_fix["last_activity_wall_clock"] = review_fix.pop("last_activity_time")
        logger.debug(
            "Migrated checkpoint field: last_activity_time -> last_activity_wall_clock"
        )


# Migration functions keyed by source version.
# Each function takes a checkpoint dict and modifies it in place to the next version.
# To add a new migration:
# 1. Define a function _migrate_vN_to_vM(checkpoint) that modifies checkpoint in place
# 2. Add entry N: _migrate_vN_to_vM to _MIGRATIONS
# 3. Increment CHECKPOINT_VERSION at the top of this file
_MIGRATIONS: dict[int, Any] = {
    0: _migrate_v0_to_v1,
    # Future migrations:
    # 1: _migrate_v1_to_v2,
}


def _migrate_checkpoint(checkpoint: dict[str, Any]) -> dict[str, Any]:
    """Migrate checkpoint from older schema versions to current version.

    This function handles backward compatibility for checkpoints created by older
    versions of the software. It applies migrations sequentially from the checkpoint's
    version to CHECKPOINT_VERSION.

    Migration versioning:
    - Checkpoints without a 'version' field are treated as version 0
    - Each migration function handles one version increment
    - Migrations are applied in sequence until reaching CHECKPOINT_VERSION
    - The 'version' field is updated after all migrations complete

    Args:
        checkpoint: Checkpoint dictionary to migrate.

    Returns:
        The migrated checkpoint (same object, modified in place).
    """
    # Checkpoints without a version field are from before versioning was added (v0)
    current_version = checkpoint.get("version", 0)

    if current_version > CHECKPOINT_VERSION:
        logger.warning(
            "Checkpoint version %d is newer than supported version %d. "
            "Some features may not work correctly.",
            current_version,
            CHECKPOINT_VERSION,
        )
        return checkpoint

    if current_version == CHECKPOINT_VERSION:
        return checkpoint

    # Apply migrations sequentially
    logger.debug(
        "Migrating checkpoint from version %d to %d",
        current_version,
        CHECKPOINT_VERSION,
    )
    while current_version < CHECKPOINT_VERSION:
        migration_fn = _MIGRATIONS.get(current_version)
        if migration_fn is None:
            logger.warning(
                "No migration function for version %d to %d; skipping remaining migrations",
                current_version,
                current_version + 1,
            )
            # Keep version at the last successfully applied version and return early.
            # Do NOT set version to CHECKPOINT_VERSION - that would "bless" an
            # unmigrated structure as if it were fully migrated.
            checkpoint["version"] = current_version
            return checkpoint
        migration_fn(checkpoint)
        current_version += 1
        # Update version after each successful migration step. This ensures the
        # in-memory checkpoint reflects the current migration state, which will be
        # persisted on the next save_checkpoint() call.
        #
        # Note: The checkpoint is NOT automatically persisted here - persistence only
        # occurs when save_checkpoint() is explicitly called (typically after phase
        # state updates). If the process crashes mid-migration, the next load will
        # re-apply migrations from the on-disk version.
        #
        # Migrations are idempotent (guarded by field presence checks), so
        # re-applying them is safe but wasteful. This in-memory update avoids
        # unnecessary work within the same session.
        checkpoint["version"] = current_version

    checkpoint["version"] = CHECKPOINT_VERSION
    logger.debug(
        "Checkpoint migration complete (now at version %d)", CHECKPOINT_VERSION
    )

    return checkpoint


def load_checkpoint(session_id: str) -> dict[str, Any] | None:
    """Load checkpoint from disk.

    Args:
        session_id: The session identifier.

    Returns:
        Checkpoint dictionary or None if not found.

    Note:
        Automatically migrates checkpoints from older schema versions.
    """
    checkpoint_path = get_checkpoint_path(session_id)
    if not checkpoint_path.exists():
        return None

    try:
        with open(checkpoint_path) as f:
            checkpoint = json.load(f)
        # Migrate from older schema versions if needed
        checkpoint = _migrate_checkpoint(checkpoint)
        logger.debug("Loaded checkpoint from %s", checkpoint_path)
        return checkpoint
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load checkpoint %s: %s", checkpoint_path, e)
        return None


def find_resumable_session(prd_path: Path, repo_root: Path) -> dict[str, Any] | None:
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
    status_filter: str | None = None, limit: int = 20
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
