"""Progress tracking for real-time session monitoring.

This module provides metrics collection and progress reporting for
automation runs, enabling real-time visibility into execution state.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .logging_utils import logger


@dataclass
class PhaseMetrics:
    """Metrics for a single phase."""

    name: str
    started_at: float | None = None
    completed_at: float | None = None
    iterations: int = 0
    runner_calls: int = 0
    runner_success: int = 0
    runner_failures: int = 0
    findings_detected: int = 0
    commits_made: int = 0
    errors: int = 0

    @property
    def duration_seconds(self) -> float | None:
        """Get phase duration in seconds."""
        if self.started_at is None:
            return None
        end_time = self.completed_at or time.monotonic()
        return end_time - self.started_at

    @property
    def is_running(self) -> bool:
        """Check if phase is currently running."""
        return self.started_at is not None and self.completed_at is None

    @property
    def runner_success_rate(self) -> float | None:
        """Get runner success rate as percentage."""
        total = self.runner_success + self.runner_failures
        if total == 0:
            return None
        return (self.runner_success / total) * 100


@dataclass
class SessionProgress:
    """Real-time progress tracking for a session."""

    session_id: str
    started_at: float = field(default_factory=time.monotonic)
    current_phase: str | None = None
    phases: dict[str, PhaseMetrics] = field(default_factory=dict)
    total_runner_calls: int = 0
    total_commits: int = 0
    tasks_total: int | None = None
    tasks_completed: int = 0

    def start_phase(self, phase: str) -> None:
        """Mark a phase as started.

        Args:
            phase: Phase name.
        """
        if phase not in self.phases:
            self.phases[phase] = PhaseMetrics(name=phase)
        self.phases[phase].started_at = time.monotonic()
        self.phases[phase].completed_at = None
        self.current_phase = phase
        logger.debug("Progress: started phase %s", phase)

    def end_phase(self, phase: str) -> None:
        """Mark a phase as completed.

        Args:
            phase: Phase name.
        """
        if phase in self.phases:
            self.phases[phase].completed_at = time.monotonic()
            if self.current_phase == phase:
                self.current_phase = None
            logger.debug(
                "Progress: completed phase %s (%.1fs)",
                phase,
                self.phases[phase].duration_seconds or 0,
            )

    def increment_iteration(self, phase: str | None = None) -> None:
        """Increment iteration count for a phase.

        Args:
            phase: Phase name (uses current phase if not specified).
        """
        phase = phase or self.current_phase
        if phase and phase in self.phases:
            self.phases[phase].iterations += 1

    def record_runner_call(
        self, phase: str | None = None, success: bool = True
    ) -> None:
        """Record a runner execution.

        Args:
            phase: Phase name (uses current phase if not specified).
            success: Whether the runner succeeded.
        """
        self.total_runner_calls += 1
        phase = phase or self.current_phase
        if phase and phase in self.phases:
            self.phases[phase].runner_calls += 1
            if success:
                self.phases[phase].runner_success += 1
            else:
                self.phases[phase].runner_failures += 1

    def record_findings(self, count: int = 1, phase: str | None = None) -> None:
        """Record detected findings.

        Args:
            count: Number of findings.
            phase: Phase name (uses current phase if not specified).
        """
        phase = phase or self.current_phase
        if phase and phase in self.phases:
            self.phases[phase].findings_detected += count

    def record_commit(self, phase: str | None = None) -> None:
        """Record a git commit.

        Args:
            phase: Phase name (uses current phase if not specified).
        """
        self.total_commits += 1
        phase = phase or self.current_phase
        if phase and phase in self.phases:
            self.phases[phase].commits_made += 1

    def record_error(self, phase: str | None = None) -> None:
        """Record an error.

        Args:
            phase: Phase name (uses current phase if not specified).
        """
        phase = phase or self.current_phase
        if phase and phase in self.phases:
            self.phases[phase].errors += 1

    def update_tasks(
        self, total: int | None = None, completed: int | None = None
    ) -> None:
        """Update task counts.

        Args:
            total: Total number of tasks.
            completed: Number of completed tasks.
        """
        if total is not None:
            self.tasks_total = total
        if completed is not None:
            self.tasks_completed = completed

    @property
    def elapsed_seconds(self) -> float:
        """Get total elapsed time in seconds."""
        return time.monotonic() - self.started_at

    @property
    def completion_percentage(self) -> float | None:
        """Get estimated completion percentage based on tasks."""
        if self.tasks_total is None or self.tasks_total == 0:
            return None
        return (self.tasks_completed / self.tasks_total) * 100

    def get_status_line(self) -> str:
        """Get a single-line status summary.

        Returns:
            Status string like "local[3/10] 45% 2m30s"
        """
        parts = []

        # Current phase and iteration
        if self.current_phase:
            phase_metrics = self.phases.get(self.current_phase)
            if phase_metrics:
                parts.append(f"{self.current_phase}[iter:{phase_metrics.iterations}]")
            else:
                parts.append(self.current_phase)

        # Task completion
        if self.tasks_total is not None:
            remaining = self.tasks_total - self.tasks_completed
            parts.append(f"tasks_left:{remaining}")

        # Time elapsed
        elapsed = self.elapsed_seconds
        if elapsed >= 3600:
            parts.append(f"{elapsed / 3600:.1f}h")
        elif elapsed >= 60:
            parts.append(f"{elapsed / 60:.1f}m")
        else:
            parts.append(f"{elapsed:.0f}s")

        return " | ".join(parts)

    def to_dict(self) -> dict:
        """Convert progress to dictionary format.

        Returns:
            Dictionary representation of progress state.
        """
        return {
            "session_id": self.session_id,
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "current_phase": self.current_phase,
            "total_runner_calls": self.total_runner_calls,
            "total_commits": self.total_commits,
            "tasks_total": self.tasks_total,
            "tasks_completed": self.tasks_completed,
            "completion_percentage": (
                round(self.completion_percentage, 1)
                if self.completion_percentage
                else None
            ),
            "phases": {
                name: {
                    "duration_seconds": (
                        round(m.duration_seconds, 1) if m.duration_seconds else None
                    ),
                    "is_running": m.is_running,
                    "iterations": m.iterations,
                    "runner_calls": m.runner_calls,
                    "runner_success_rate": (
                        round(m.runner_success_rate, 1)
                        if m.runner_success_rate
                        else None
                    ),
                    "findings_detected": m.findings_detected,
                    "commits_made": m.commits_made,
                    "errors": m.errors,
                }
                for name, m in self.phases.items()
            },
        }


def format_progress_report(progress: SessionProgress) -> str:
    """Format a detailed progress report.

    Args:
        progress: Session progress object.

    Returns:
        Multi-line formatted progress report.
    """
    lines = []
    lines.append(f"Session: {progress.session_id}")
    lines.append(f"Elapsed: {progress.elapsed_seconds:.1f}s")
    lines.append("")

    if progress.tasks_total is not None:
        remaining = progress.tasks_total - progress.tasks_completed
        pct = progress.completion_percentage or 0
        lines.append(
            f"Tasks: {progress.tasks_completed}/{progress.tasks_total} ({pct:.0f}%)"
        )
        lines.append(f"Remaining: {remaining}")
        lines.append("")

    lines.append("Phases:")
    for name, metrics in progress.phases.items():
        status = "RUNNING" if metrics.is_running else "done"
        duration = (
            f"{metrics.duration_seconds:.1f}s" if metrics.duration_seconds else "-"
        )
        lines.append(f"  {name}: {status} ({duration})")
        lines.append(f"    Iterations: {metrics.iterations}")
        lines.append(f"    Runner calls: {metrics.runner_calls}")
        if metrics.runner_success_rate is not None:
            lines.append(f"    Success rate: {metrics.runner_success_rate:.0f}%")
        if metrics.findings_detected:
            lines.append(f"    Findings: {metrics.findings_detected}")
        if metrics.commits_made:
            lines.append(f"    Commits: {metrics.commits_made}")
        if metrics.errors:
            lines.append(f"    Errors: {metrics.errors}")

    lines.append("")
    lines.append(f"Total runner calls: {progress.total_runner_calls}")
    lines.append(f"Total commits: {progress.total_commits}")

    return "\n".join(lines)
