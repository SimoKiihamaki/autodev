"""Progress journal for session observability and debugging.

This module provides structured logging of actions and milestones during
automation runs, enabling post-hoc analysis and debugging.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from .logging_utils import logger


class ActionType(str, Enum):
    """Types of actions that can be journaled."""

    SESSION_START = "session_start"
    SESSION_END = "session_end"
    PHASE_START = "phase_start"
    PHASE_END = "phase_end"
    ITERATION_START = "iteration_start"
    ITERATION_END = "iteration_end"
    RUNNER_START = "runner_start"
    RUNNER_END = "runner_end"
    GIT_OP = "git_op"
    API_CALL = "api_call"
    CHECKPOINT_SAVE = "checkpoint_save"
    CHECKPOINT_RESTORE = "checkpoint_restore"
    ERROR = "error"
    WARNING = "warning"
    MILESTONE = "milestone"


class Journal:
    """Session journal for progress tracking and observability.

    Writes structured JSONL entries to a journal file for each session.
    """

    def __init__(self, session_id: str, journal_dir: Path | None = None):
        """Initialize journal for a session.

        Args:
            session_id: Unique session identifier.
            journal_dir: Optional directory for journal files.
        """
        self.session_id = session_id
        self._journal_dir = journal_dir or self._get_default_journal_dir()
        self._journal_dir.mkdir(parents=True, exist_ok=True)
        self._journal_path = self._journal_dir / f"{session_id}.jsonl"
        self._entry_count = 0

    @staticmethod
    def _get_default_journal_dir() -> Path:
        """Get default journal directory under XDG config."""
        xdg_config = os.getenv("XDG_CONFIG_HOME", None)
        if xdg_config and xdg_config.strip():
            base_config = Path(xdg_config).expanduser()
        else:
            base_config = Path.home() / ".config"
        return base_config / "aprd" / "journals"

    def _write_entry(self, entry: dict[str, Any]) -> None:
        """Write a single entry to the journal file.

        Args:
            entry: Dictionary to write as JSON line.
        """
        try:
            with open(self._journal_path, "a") as f:
                f.write(json.dumps(entry, sort_keys=True) + "\n")
            self._entry_count += 1
        except OSError as e:
            logger.warning("Failed to write journal entry: %s", e)

    def log(
        self,
        action_type: ActionType,
        message: str,
        *,
        phase: str | None = None,
        iteration: int | None = None,
        details: dict[str, Any] | None = None,
        duration_ms: int | None = None,
        success: bool | None = None,
    ) -> None:
        """Log an action to the journal.

        Args:
            action_type: Type of action being logged.
            message: Human-readable description.
            phase: Current phase (local, pr, review_fix).
            iteration: Current iteration number if applicable.
            details: Additional structured data.
            duration_ms: Duration in milliseconds if timed action.
            success: Whether the action succeeded.
        """
        entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": self.session_id,
            "action": action_type.value,
            "message": message,
        }

        if phase is not None:
            entry["phase"] = phase
        if iteration is not None:
            entry["iteration"] = iteration
        if details is not None:
            entry["details"] = details
        if duration_ms is not None:
            entry["duration_ms"] = duration_ms
        if success is not None:
            entry["success"] = success

        self._write_entry(entry)

    def session_start(
        self,
        prd_path: str,
        repo_root: str,
        selected_phases: list[str],
        resumed: bool = False,
    ) -> None:
        """Log session start."""
        self.log(
            ActionType.SESSION_START,
            "Resumed session" if resumed else "Started new session",
            details={
                "prd_path": prd_path,
                "repo_root": repo_root,
                "selected_phases": selected_phases,
                "resumed": resumed,
            },
        )

    def session_end(self, success: bool, summary: str | None = None) -> None:
        """Log session end."""
        self.log(
            ActionType.SESSION_END,
            summary
            or ("Session completed successfully" if success else "Session failed"),
            success=success,
            details={"total_entries": self._entry_count},
        )

    def phase_start(self, phase: str) -> None:
        """Log phase start."""
        self.log(
            ActionType.PHASE_START,
            f"Starting {phase} phase",
            phase=phase,
        )

    def phase_end(self, phase: str, success: bool, summary: str | None = None) -> None:
        """Log phase end."""
        self.log(
            ActionType.PHASE_END,
            summary or f"Completed {phase} phase",
            phase=phase,
            success=success,
        )

    def iteration_start(self, phase: str, iteration: int, max_iters: int) -> None:
        """Log iteration start."""
        self.log(
            ActionType.ITERATION_START,
            f"Starting iteration {iteration}/{max_iters}",
            phase=phase,
            iteration=iteration,
            details={"max_iterations": max_iters},
        )

    def iteration_end(
        self,
        phase: str,
        iteration: int,
        *,
        tasks_left: int | None = None,
        has_findings: bool = False,
        repo_changed: bool = False,
    ) -> None:
        """Log iteration end."""
        self.log(
            ActionType.ITERATION_END,
            f"Completed iteration {iteration}",
            phase=phase,
            iteration=iteration,
            details={
                "tasks_left": tasks_left,
                "has_findings": has_findings,
                "repo_changed": repo_changed,
            },
        )

    def runner_start(
        self, runner_name: str, phase: str, prompt_preview: str = ""
    ) -> None:
        """Log runner execution start."""
        preview = (
            prompt_preview[:200] + "..."
            if len(prompt_preview) > 200
            else prompt_preview
        )
        self.log(
            ActionType.RUNNER_START,
            f"Launching {runner_name}",
            phase=phase,
            details={"runner": runner_name, "prompt_preview": preview},
        )

    def runner_end(
        self,
        runner_name: str,
        phase: str,
        success: bool,
        duration_ms: int | None = None,
        output_preview: str = "",
    ) -> None:
        """Log runner execution end."""
        preview = (
            output_preview[:200] + "..."
            if len(output_preview) > 200
            else output_preview
        )
        self.log(
            ActionType.RUNNER_END,
            f"{runner_name} {'completed' if success else 'failed'}",
            phase=phase,
            success=success,
            duration_ms=duration_ms,
            details={"runner": runner_name, "output_preview": preview},
        )

    def git_operation(
        self,
        operation: str,
        success: bool,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Log a git operation."""
        self.log(
            ActionType.GIT_OP,
            f"Git {operation}",
            success=success,
            details={"operation": operation, **(details or {})},
        )

    def api_call(
        self,
        endpoint: str,
        success: bool,
        duration_ms: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Log an API call."""
        self.log(
            ActionType.API_CALL,
            f"API call to {endpoint}",
            success=success,
            duration_ms=duration_ms,
            details={"endpoint": endpoint, **(details or {})},
        )

    def checkpoint_saved(self, phase: str, state_summary: str) -> None:
        """Log checkpoint save."""
        self.log(
            ActionType.CHECKPOINT_SAVE,
            f"Checkpoint saved: {state_summary}",
            phase=phase,
        )

    def checkpoint_restored(self, phase: str, state_summary: str) -> None:
        """Log checkpoint restore."""
        self.log(
            ActionType.CHECKPOINT_RESTORE,
            f"Checkpoint restored: {state_summary}",
            phase=phase,
        )

    def error(
        self,
        message: str,
        *,
        phase: str | None = None,
        exception_type: str | None = None,
        recoverable: bool = True,
    ) -> None:
        """Log an error."""
        self.log(
            ActionType.ERROR,
            message,
            phase=phase,
            success=False,
            details={
                "exception_type": exception_type,
                "recoverable": recoverable,
            },
        )

    def warning(self, message: str, *, phase: str | None = None) -> None:
        """Log a warning."""
        self.log(
            ActionType.WARNING,
            message,
            phase=phase,
        )

    def milestone(self, message: str, *, phase: str | None = None) -> None:
        """Log a significant milestone."""
        self.log(
            ActionType.MILESTONE,
            message,
            phase=phase,
        )

    @property
    def journal_path(self) -> Path:
        """Get the path to the journal file."""
        return self._journal_path

    @property
    def entry_count(self) -> int:
        """Get the number of entries written."""
        return self._entry_count


def load_journal(
    session_id: str, journal_dir: Path | None = None
) -> list[dict[str, Any]]:
    """Load all entries from a session journal.

    Args:
        session_id: Session identifier.
        journal_dir: Optional directory containing journals.

    Returns:
        List of journal entry dictionaries.
    """
    if journal_dir is None:
        xdg_config = os.getenv("XDG_CONFIG_HOME", None)
        if xdg_config and xdg_config.strip():
            base_config = Path(xdg_config).expanduser()
        else:
            base_config = Path.home() / ".config"
        journal_dir = base_config / "aprd" / "journals"

    journal_path = journal_dir / f"{session_id}.jsonl"
    if not journal_path.exists():
        return []

    entries = []
    try:
        with open(journal_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except OSError as e:
        logger.warning("Failed to load journal %s: %s", journal_path, e)

    return entries


def summarize_journal(
    entries: list[dict[str, Any]], journal_path: Path | None = None
) -> dict[str, Any]:
    """Generate a summary of journal entries.

    Args:
        entries: List of journal entry dictionaries.
        journal_path: Optional path to the journal file (for error context).

    Returns:
        Summary dictionary with statistics and key events.
    """
    if not entries:
        return {"total_entries": 0}

    summary: dict[str, Any] = {
        "total_entries": len(entries),
        "phases": {},
        "errors": [],
        "milestones": [],
        "duration_ms": None,
    }

    # Track phase statistics
    phase_stats: dict[str, dict[str, Any]] = {}
    start_time = None
    end_time = None

    for entry in entries:
        action = entry.get("action", "")
        phase = entry.get("phase")
        timestamp = entry.get("timestamp", "")

        # Track overall duration
        if start_time is None and timestamp:
            start_time = timestamp
        if timestamp:
            end_time = timestamp

        # Track phase stats
        if phase and phase not in phase_stats:
            phase_stats[phase] = {
                "iterations": 0,
                "runner_calls": 0,
                "errors": 0,
                "started_at": timestamp,
            }

        if action == ActionType.ITERATION_END.value and phase:
            phase_stats[phase]["iterations"] += 1

        if action == ActionType.RUNNER_END.value and phase:
            phase_stats[phase]["runner_calls"] += 1

        if action == ActionType.ERROR.value:
            summary["errors"].append(
                {
                    "message": entry.get("message", "Unknown error"),
                    "phase": phase,
                    "timestamp": timestamp,
                }
            )
            if phase and phase in phase_stats:
                phase_stats[phase]["errors"] += 1

        if action == ActionType.MILESTONE.value:
            summary["milestones"].append(
                {
                    "message": entry.get("message", ""),
                    "phase": phase,
                    "timestamp": timestamp,
                }
            )

    summary["phases"] = phase_stats

    # Calculate duration if we have timestamps
    if start_time and end_time:
        try:
            start = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            end = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
            summary["duration_ms"] = int((end - start).total_seconds() * 1000)
        except ValueError as e:
            logger.warning(
                "Failed to parse journal entry timestamps in %s: start_time=%r, end_time=%r. Error: %s",
                journal_path or "unknown journal",
                start_time,
                end_time,
                e,
            )

    return summary
