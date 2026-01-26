"""Progress renderer for Ralph-style iteration history.

This module provides functionality to render progress history from journal
entries into a human-readable format, inspired by Ralph's progress.txt.
This gives visibility into what was tried during automation runs.

Key features:
- Renders iteration summaries with learnings and issues
- Tracks codebase patterns discovered during execution
- Maintains history of tasks completed and remaining
- Provides both human-readable and machine-readable formats
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .logging_utils import logger


@dataclass
class IterationSummary:
    """Summary of a single iteration for progress tracking.

    Attributes:
        iteration: Iteration number.
        timestamp: ISO timestamp of when iteration completed.
        status: Status of iteration (completed, completed_with_warnings, failed).
        files_changed: List of files that were modified/created.
        learnings: Patterns/discoveries made during iteration.
        issues_found: Problems detected during iteration.
        tasks_completed: List of task IDs completed in this iteration.
        tasks_remaining: Total tasks remaining after this iteration.
        phase: Phase where this iteration occurred (local, pr, review_fix).
        commits_made: Number of commits made during this iteration.
        review_round: Review round results if review was run.
    """

    iteration: int
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    status: str = "completed"
    files_changed: list[str] = field(default_factory=list)
    learnings: list[str] = field(default_factory=list)
    issues_found: list[str] = field(default_factory=list)
    tasks_completed: list[str] = field(default_factory=list)
    tasks_remaining: int = 0
    phase: str = "local"
    commits_made: int = 0
    review_round: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation.
        """
        return {
            "iteration": self.iteration,
            "timestamp": self.timestamp,
            "status": self.status,
            "files_changed": self.files_changed,
            "learnings": self.learnings,
            "issues_found": self.issues_found,
            "tasks_completed": self.tasks_completed,
            "tasks_remaining": self.tasks_remaining,
            "phase": self.phase,
            "commits_made": self.commits_made,
            "review_round": self.review_round,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IterationSummary:
        """Create from dictionary.

        Args:
            data: Dictionary with iteration summary data.

        Returns:
            IterationSummary instance.
        """
        return cls(
            iteration=data.get("iteration", 1),
            timestamp=data.get("timestamp", datetime.now(timezone.utc).isoformat()),
            status=data.get("status", "completed"),
            files_changed=data.get("files_changed", []),
            learnings=data.get("learnings", []),
            issues_found=data.get("issues_found", []),
            tasks_completed=data.get("tasks_completed", []),
            tasks_remaining=data.get("tasks_remaining", 0),
            phase=data.get("phase", "local"),
            commits_made=data.get("commits_made", 0),
            review_round=data.get("review_round", {}),
        )

    def to_markdown(self) -> str:
        """Convert to markdown format for progress.txt.

        Returns:
            Markdown formatted iteration entry.
        """
        lines = [
            f"### Iteration {self.iteration} - {self.timestamp}",
            f"**Status:** {self.status}",
        ]
        if self.phase:
            lines.append(f"**Phase:** {self.phase}")
        if self.commits_made:
            lines.append(f"**Commits:** {self.commits_made}")

        if self.files_changed:
            lines.append("**Files Changed:**")
            for f in self.files_changed:
                lines.append(f"- {f}")

        if self.issues_found:
            lines.append("**Issues Found:**")
            for issue in self.issues_found:
                lines.append(f"- {issue}")

        if self.learnings:
            lines.append("**Learnings:**")
            for learning in self.learnings:
                lines.append(f"- {learning}")

        if self.tasks_completed:
            lines.append(f"**Tasks Completed:** {', '.join(self.tasks_completed)}")

        if self.tasks_remaining is not None:
            lines.append(f"**Tasks Remaining:** {self.tasks_remaining}")

        return "\n".join(lines)


@dataclass
class ProgressHistory:
    """Complete progress history for a session.

    Attributes:
        session_id: Unique identifier for the session.
        started_at: Session start timestamp.
        codebase_patterns: Patterns discovered across all iterations.
        iterations: List of iteration summaries.
        total_commits: Total commits across all iterations.
        total_iterations: Total number of iterations.
    """

    session_id: str
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    codebase_patterns: list[str] = field(default_factory=list)
    iterations: list[IterationSummary] = field(default_factory=list)
    total_commits: int = 0
    total_iterations: int = 0

    def add_iteration(self, summary: IterationSummary) -> None:
        """Add an iteration summary to history.

        Args:
            summary: Iteration summary to add.
        """
        self.iterations.append(summary)
        self.total_iterations = len(self.iterations)
        self.total_commits += summary.commits_made

        # Extract new patterns from learnings
        for learning in summary.learnings:
            # Simple heuristic: learnings starting with "Pattern:" or "Discovered:"
            if any(
                learning.startswith(prefix)
                for prefix in ["Pattern:", "Discovered:", "Uses ", "All "]
            ):
                if learning not in self.codebase_patterns:
                    self.codebase_patterns.append(learning)

    def get_latest_iteration(self) -> IterationSummary | None:
        """Get the most recent iteration summary.

        Returns:
            Latest IterationSummary or None if no iterations.
        """
        return self.iterations[-1] if self.iterations else None

    def to_markdown(self) -> str:
        """Convert entire history to markdown format (Ralph progress.txt style).

        Returns:
            Complete markdown formatted progress history.
        """
        lines = [
            f"# Ralph Progress Log - Session {self.session_id}",
            f"Started: {self.started_at}",
            "",
        ]

        if self.codebase_patterns:
            lines.append("## Codebase Patterns (Discovered)")
            for pattern in self.codebase_patterns:
                lines.append(f"- {pattern}")
            lines.append("")

        lines.append("## Iteration History")
        lines.append("")

        for iteration in self.iterations:
            lines.append(iteration.to_markdown())
            lines.append("")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation.
        """
        return {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "codebase_patterns": self.codebase_patterns,
            "iterations": [i.to_dict() for i in self.iterations],
            "total_commits": self.total_commits,
            "total_iterations": self.total_iterations,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProgressHistory:
        """Create from dictionary.

        Args:
            data: Dictionary with progress history data.

        Returns:
            ProgressHistory instance.
        """
        iterations = [
            IterationSummary.from_dict(i_data) for i_data in data.get("iterations", [])
        ]
        return cls(
            session_id=data.get("session_id", ""),
            started_at=data.get("started_at", datetime.now(timezone.utc).isoformat()),
            codebase_patterns=data.get("codebase_patterns", []),
            iterations=iterations,
            total_commits=data.get("total_commits", 0),
            total_iterations=len(iterations),
        )


def get_progress_path(session_id: str) -> Path:
    """Get the path to the progress file for a session.

    Progress files are stored under ~/.config/aprd/progress/

    Args:
        session_id: Unique session identifier.

    Returns:
        Path to progress file.

    Raises:
        ValueError: If session_id contains path traversal sequences or invalid characters.
    """
    import os
    import re

    # Sanitize session_id to prevent path traversal attacks
    # Reject path separators and parent directory references
    if "/" in session_id or "\\" in session_id or ".." in session_id:
        raise ValueError(
            "Invalid session_id: contains path separators or traversal sequences"
        )

    # Only allow alphanumeric, hyphen, and underscore characters
    safe_pattern = re.compile(r"^[\w\-]+$")
    if not safe_pattern.match(session_id):
        raise ValueError(
            "Invalid session_id: must contain only alphanumeric, hyphen, or underscore characters"
        )

    xdg_config = os.getenv("XDG_CONFIG_HOME", None)
    if xdg_config and xdg_config.strip():
        base_config = Path(xdg_config).expanduser()
    else:
        base_config = Path.home() / ".config"
    progress_dir = (base_config / "aprd" / "progress").resolve()
    progress_file = (progress_dir / f"{session_id}.jsonl").resolve()

    # Ensure the final path is under the progress directory
    if not str(progress_file).startswith(str(progress_dir)):
        raise ValueError("Invalid session_id: path traversal detected")

    return progress_file


def load_progress_history(session_id: str) -> ProgressHistory:
    """Load progress history from file.

    Args:
        session_id: Session identifier to load.

    Returns:
        ProgressHistory with loaded data (empty if file doesn't exist).
    """
    progress_path = get_progress_path(session_id)
    history = ProgressHistory(session_id=session_id)

    if not progress_path.exists():
        return history

    try:
        for line in progress_path.read_text(encoding="utf-8").strip().split("\n"):
            if line:
                data = json.loads(line)
                summary = IterationSummary.from_dict(data)
                history.add_iteration(summary)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Failed to load progress history: %s", e)

    return history


def save_iteration_summary(session_id: str, summary: IterationSummary) -> None:
    """Append an iteration summary to the progress file.

    Args:
        session_id: Session identifier.
        summary: Iteration summary to save.
    """
    progress_path = get_progress_path(session_id)
    progress_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(progress_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(summary.to_dict()) + "\n")
    except OSError as e:
        logger.warning("Failed to save iteration summary: %s", e)


def format_progress_for_prompt(
    history: ProgressHistory, max_iterations: int = 3
) -> str:
    """Format recent progress history for agent context injection.

    Args:
        history: Progress history to format.
        max_iterations: Maximum number of recent iterations to include.

    Returns:
        Formatted text for system prompt injection.
    """
    if not history.iterations:
        return ""

    lines = [
        "\n[recent_progress]",
        f"Recent iterations from session {history.session_id}:",
        "",
    ]

    recent_iterations = history.iterations[-max_iterations:]
    for iteration in recent_iterations:
        lines.append(
            f"Iteration {iteration.iteration} ({iteration.phase}): {iteration.status}"
        )
        if iteration.learnings:
            for learning in iteration.learnings[-2:]:  # Last 2 learnings
                lines.append(f"  - {learning}")
        if iteration.issues_found:
            for issue in iteration.issues_found[-2:]:  # Last 2 issues
                lines.append(f"  - Issue: {issue}")

    latest = history.get_latest_iteration()
    if latest and latest.tasks_remaining is not None:
        lines.append(f"\nTasks remaining: {latest.tasks_remaining}")

    lines.append("[/recent_progress]")
    return "\n".join(lines)


def render_progress_txt(session_id: str) -> str | None:
    """Render the full progress.txt content for a session.

    Args:
        session_id: Session identifier.

    Returns:
        Markdown formatted progress.txt content, or None if no history exists.
    """
    history = load_progress_history(session_id)
    if not history.iterations:
        return None
    return history.to_markdown()


def clear_progress_history(session_id: str) -> None:
    """Clear progress history for a session.

    Args:
        session_id: Session identifier to clear.
    """
    progress_path = get_progress_path(session_id)
    if progress_path.exists():
        try:
            progress_path.unlink()
            logger.info("Cleared progress history for session %s", session_id)
        except OSError as e:
            logger.warning("Failed to clear progress history: %s", e)
