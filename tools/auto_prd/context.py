"""Context engineering utilities for Claude headless execution.

This module provides functions for just-in-time context loading, context compaction,
and structured memory management across execution phases.

Key concepts:
- Just-in-time loading: Provide pointers to files rather than full contents
- Context compaction: Summarize previous phase results for continuity
- Session memory: Persistent tracking of files touched, costs, and decisions

Note on persistence paths:
- Session memory files are saved to .aprd/memory/{sanitized_session_id}.json
- The session_id is sanitized by replacing non-alphanumeric characters with underscores
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from .agents import ClaudeHeadlessResponse
from .logging_utils import logger
from .utils import is_valid_numeric


class LoadFailureReason(Enum):
    """Reason why loading session memory failed.

    Used by LoadSessionResult to distinguish between different failure modes,
    allowing callers to handle each case appropriately (e.g., file not found
    is normal on first run, but corrupted JSON indicates a problem).
    """

    NOT_FOUND = "not_found"
    CORRUPTED_JSON = "corrupted_json"
    IO_ERROR = "io_error"
    INVALID_FORMAT = "invalid_format"


@dataclass(frozen=True)
class LoadSessionResult:
    """Result of loading session memory, with failure reason if unsuccessful.

    This dataclass provides a richer return type than Optional[SessionMemory],
    allowing callers to distinguish between different failure modes.

    The class enforces mutual exclusivity: either memory is set (success) or
    failure_reason is set (failure), but not both or neither.

    Attributes:
        memory: The loaded SessionMemory, or None if loading failed.
        failure_reason: Why loading failed, or None if successful.
        error_message: Human-readable error description, or None if successful.

    Raises:
        ValueError: If both memory and failure_reason are set, or neither is set.
    """

    memory: SessionMemory | None
    failure_reason: LoadFailureReason | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        """Validate mutual exclusivity of success and failure states."""
        if self.memory is not None and self.failure_reason is not None:
            msg = "LoadSessionResult cannot have both memory and failure_reason set"
            raise ValueError(msg)
        if self.memory is None and self.failure_reason is None:
            msg = "LoadSessionResult must have either memory or failure_reason set"
            raise ValueError(msg)

    @property
    def is_success(self) -> bool:
        """Return True if memory was successfully loaded."""
        return self.memory is not None


@dataclass
class SessionMemory:
    """Track session metadata across phases for observability and debugging.

    This dataclass captures the state of an autodev session, including what
    files were modified, what commits were made, and the total cost incurred.
    It is persisted to .aprd/memory/{sanitized_session_id}.json for post-mortem
    analysis (see module docstring for path sanitization details).

    Note: This class is not thread-safe. External synchronization is required
    if instances are modified from multiple threads.

    Attributes:
        session_id: Unique identifier for the session (from Claude response).
        created_at: ISO timestamp when the session started.
        phase_outcomes: Map of phase name to outcome description.
        files_touched: Set of files that were read or modified.
        commits_made: List of commit SHAs made during the session.
        total_cost_usd: Cumulative API cost in USD (must be non-negative).
        total_duration_ms: Cumulative execution time in milliseconds (must be non-negative).
        errors: List of error messages encountered.

    Raises:
        ValueError: If total_cost_usd or total_duration_ms are negative
            (validated on construction only; assignment is not validated).
    """

    session_id: str
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    phase_outcomes: dict[str, str] = field(default_factory=dict)
    files_touched: set[str] = field(default_factory=set)
    commits_made: list[str] = field(default_factory=list)
    total_cost_usd: float = 0.0
    total_duration_ms: int = 0
    errors: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate invariants after construction.

        Raises:
            ValueError: If numeric fields are negative.

        Note:
            Validation is performed only during construction (in __post_init__).
            This class does not implement __setattr__, so assignments after
            construction are not validated. This design choice avoids complexity
            with dataclass field initialization, where __setattr__ is called for
            each field before __post_init__ runs.
        """
        # Validate fields directly after construction
        if self.total_cost_usd < 0:
            msg = f"total_cost_usd must be non-negative, got {self.total_cost_usd}"
            raise ValueError(msg)
        if self.total_duration_ms < 0:
            msg = (
                f"total_duration_ms must be non-negative, got {self.total_duration_ms}"
            )
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "phase_outcomes": self.phase_outcomes,
            "files_touched": sorted(self.files_touched),
            "commits_made": self.commits_made,
            "total_cost_usd": self.total_cost_usd,
            "total_duration_ms": self.total_duration_ms,
            "errors": self.errors,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionMemory:
        """Create from dictionary (e.g., loaded from JSON).

        Performs type validation to ensure fields have correct types.
        All fields are validated before construction to provide clear error messages.

        Raises:
            TypeError: If field types don't match expected schema (string, list, dict).
            ValueError: If numeric fields cannot be converted or are negative.
        """
        # Validate string fields - must be str or None (coerced to empty string)
        session_id_raw = data.get("session_id")
        if session_id_raw is not None and not isinstance(session_id_raw, str):
            msg = f"session_id must be a string or null, got {type(session_id_raw).__name__}"
            raise TypeError(msg)

        created_at_raw = data.get("created_at")
        if created_at_raw is not None and not isinstance(created_at_raw, str):
            msg = f"created_at must be a string or null, got {type(created_at_raw).__name__}"
            raise TypeError(msg)

        # Validate container fields
        files_touched_raw = data.get("files_touched", [])
        if not isinstance(files_touched_raw, list):
            msg = (
                f"files_touched must be a list, got {type(files_touched_raw).__name__}"
            )
            raise TypeError(msg)
        if not all(isinstance(x, str) for x in files_touched_raw):
            msg = "files_touched must contain only strings"
            raise TypeError(msg)

        phase_outcomes_raw = data.get("phase_outcomes", {})
        if not isinstance(phase_outcomes_raw, dict):
            msg = f"phase_outcomes must be a dict, got {type(phase_outcomes_raw).__name__}"
            raise TypeError(msg)

        commits_made_raw = data.get("commits_made", [])
        if not isinstance(commits_made_raw, list):
            msg = f"commits_made must be a list, got {type(commits_made_raw).__name__}"
            raise TypeError(msg)
        if not all(isinstance(x, str) for x in commits_made_raw):
            msg = "commits_made must contain only strings"
            raise TypeError(msg)

        errors_raw = data.get("errors", [])
        if not isinstance(errors_raw, list):
            msg = f"errors must be a list, got {type(errors_raw).__name__}"
            raise TypeError(msg)
        if not all(isinstance(x, str) for x in errors_raw):
            msg = "errors must contain only strings"
            raise TypeError(msg)

        # Validate numeric fields using is_valid_numeric helper for consistency.
        # This catches corrupted session files with null/invalid numeric values.
        # is_valid_numeric explicitly rejects booleans (bool is a subclass of int),
        # making the boolean exclusion explicit and self-documenting.
        #
        # DESIGN NOTE: Boolean handling differs from ClaudeHeadlessResponse.from_dict().
        # - Here (session files): Raise TypeError - strictness over resilience
        # - ClaudeHeadlessResponse.from_dict(): Log warning and use default - resilience
        #
        # Rationale: Session files are under our control; corruption indicates bugs or
        # tampering that should fail fast. API responses are external and may have
        # malformed data due to upstream issues, so resilience is preferred there.
        cost_raw = data.get("total_cost_usd")
        if cost_raw is None:
            logger.warning("Session memory 'total_cost_usd' is None; using default 0.0")
            total_cost_usd = 0.0
        elif is_valid_numeric(cost_raw):
            total_cost_usd = float(cost_raw)
        else:
            msg = (
                f"total_cost_usd must be numeric or null, got {type(cost_raw).__name__}"
            )
            raise TypeError(msg)

        duration_raw = data.get("total_duration_ms")
        if duration_raw is None:
            logger.warning(
                "Session memory 'total_duration_ms' is None; using default 0"
            )
            total_duration_ms = 0
        elif is_valid_numeric(duration_raw):
            total_duration_ms = int(duration_raw)
        else:
            msg = f"total_duration_ms must be numeric or null, got {type(duration_raw).__name__}"
            raise TypeError(msg)

        # Construct with validated fields (invariant validation happens in __post_init__)
        return cls(
            session_id=session_id_raw if session_id_raw else "",
            created_at=created_at_raw if created_at_raw else "",
            phase_outcomes=dict(phase_outcomes_raw),
            files_touched=set(files_touched_raw),
            commits_made=list(commits_made_raw),
            total_cost_usd=total_cost_usd,
            total_duration_ms=total_duration_ms,
            errors=list(errors_raw),
        )

    def update_from_response(
        self, response: ClaudeHeadlessResponse, phase: str
    ) -> None:
        """Update memory with data from a Claude response.

        Args:
            response: The ClaudeHeadlessResponse from execution.
            phase: Name of the phase that was executed.
        """
        self.total_cost_usd += response.total_cost_usd
        self.total_duration_ms += response.duration_ms
        # Note: ClaudeHeadlessResponse validates non-negative values in __post_init__
        # and is frozen (immutable), so response values are guaranteed non-negative.
        # SessionMemory also validates non-negative in __post_init__ at construction.
        # The clamping here is removed as it was unnecessary defensive code.
        if response.is_error:
            self.errors.append(f"{phase}: execution reported error")
        # Session ID may be updated if this is a new session
        if response.session_id and not self.session_id:
            self.session_id = response.session_id


def build_phase_context(
    phase: str,
    prd_path: Path,
    repo_root: Path,
    *,
    iteration: int = 1,
    previous_summary: str | None = None,
    additional_context: dict[str, str] | None = None,
) -> str:
    """Build minimal context for a phase execution.

    This function creates a just-in-time context string that provides Claude
    with pointers to relevant files rather than dumping entire file contents.
    This keeps the context size manageable while giving Claude the information
    it needs to operate effectively.

    Phase Names:
        This function accepts any phase string for context building (it simply
        includes the string in the context output). It does NOT validate phase
        names because:

        1. Context building is separate from tool restriction - this function
           creates informational context for Claude, not security boundaries
        2. Different parts of the codebase use different phase name conventions:
           - CLI uses: "local", "pr", "review_fix"
           - Tool allowlists use: "implement", "fix", "pr", "review_fix"
        3. The flexibility allows callers to use descriptive phase names that
           match their calling context

        If you need tool restrictions, call get_tool_allowlist() separately with
        the appropriate internal phase name ("implement", not "local").

    Args:
        phase: The execution phase name (used only for context display, not
            validated). Common values:
            - implement: Internal name for local implementation phase
            - local: CLI alias for implement phase (both work here)
            - fix: CodeRabbit fix phase (internal)
            - pr: Pull request creation phase
            - review_fix: Review and fix phase
        prd_path: Path to the PRD file.
        repo_root: Repository root directory.
        iteration: Current iteration number (1-indexed).
        previous_summary: Optional compact summary from previous iteration.
        additional_context: Optional dict of additional context key-value pairs.

    Returns:
        Context string suitable for --append-system-prompt.
    """
    context_parts: list[str] = []

    # Phase and iteration info
    context_parts.append("<phase_context>")
    context_parts.append(f"Phase: {phase}")
    context_parts.append(f"Iteration: {iteration}")
    context_parts.append(f"PRD location: {prd_path}")
    context_parts.append(f"Repository root: {repo_root}")

    # Add previous iteration summary if available
    if previous_summary:
        context_parts.append(f"\nPrevious iteration summary:\n{previous_summary}")

    # Add any additional context
    if additional_context:
        context_parts.append("\nAdditional context:")
        for key, value in additional_context.items():
            context_parts.append(f"  {key}: {value}")

    context_parts.append("</phase_context>")

    return "\n".join(context_parts)


def compact_context(
    response: ClaudeHeadlessResponse,
    phase: str,
    *,
    max_length: int = 500,
) -> str:
    """Create compact summary of execution for next phase.

    This function extracts key information from a Claude response and creates
    a brief summary suitable for passing to the next execution phase. The goal
    is to maintain continuity without bloating context.

    Args:
        response: The ClaudeHeadlessResponse to summarize.
        phase: The phase that was just executed.
        max_length: Maximum length of the summary. Must be at least 10 to produce
            a meaningful summary; smaller values raise ValueError.

    Returns:
        Compact summary string.

    Raises:
        ValueError: If max_length is less than 10 (minimum meaningful length).
    """
    # Minimum length to produce any meaningful output. Values smaller than this
    # would truncate even a short marker like "...(+N)" and produce confusing output.
    # Using lowercase for function-local constant per Python naming conventions.
    min_meaningful_length = 10
    if max_length < min_meaningful_length:
        msg = (
            f"max_length ({max_length}) is too small to produce a meaningful summary "
            f"(minimum {min_meaningful_length})"
        )
        raise ValueError(msg)

    # Extract key metrics
    parts: list[str] = []

    parts.append(f"Phase '{phase}' completed:")
    parts.append(f"  - Duration: {response.duration_ms}ms")
    parts.append(f"  - Cost: ${response.total_cost_usd:.4f}")
    parts.append(f"  - Turns: {response.num_turns}")

    if response.is_error:
        parts.append("  - Status: ERROR")

    # Try to extract key actions from the result
    result = response.result or ""
    if result:
        # Look for common action patterns
        actions: list[str] = []
        if "commit" in result.lower():
            actions.append("committed changes")
        if "push" in result.lower():
            actions.append("pushed to remote")
        if "fixed" in result.lower() or "fix" in result.lower():
            actions.append("applied fixes")
        if "test" in result.lower():
            actions.append("ran tests")

        if actions:
            parts.append(f"  - Actions: {', '.join(actions)}")

    summary = "\n".join(parts)

    # Truncate if needed, ensuring final length does not exceed max_length.
    # Use a shorter marker when max_length is small but still valid.
    # Using lowercase for function-local constants per Python naming conventions.
    truncation_marker = "\n  ...(truncated)"
    short_truncation_marker = "...(+)"
    if len(summary) > max_length:
        # Choose marker based on available space
        if max_length >= len(truncation_marker) + min_meaningful_length:
            marker = truncation_marker
        else:
            marker = short_truncation_marker
        summary = summary[: max_length - len(marker)] + marker

    return summary


def _generate_session_filename(memory: SessionMemory) -> str:
    """Generate a filename-safe identifier for a session memory file.

    This function encapsulates the fallback logic for generating filenames when
    session_id is empty or unavailable. It provides multiple fallback layers:
    1. Use session_id if available
    2. Parse created_at as ISO timestamp and format as YYYYMMDDTHHMMSS_ffffff
    3. Extract digits from created_at as a fallback
    4. Use current UTC timestamp if all else fails

    The result is sanitized by replacing non-alphanumeric characters with underscores.

    Args:
        memory: The SessionMemory to generate a filename for.

    Returns:
        A sanitized filename string (without extension) suitable for filesystem use.
    """
    # Use session_id if available, otherwise generate a filename-safe timestamp.
    # Format created_at as YYYYMMDDTHHMMSS with microseconds to ensure uniqueness
    # and avoid colons and other special characters in the filename.
    if memory.session_id:
        filename = memory.session_id
    else:
        try:
            dt = datetime.fromisoformat(memory.created_at)
            # Always include microseconds to ensure uniqueness when multiple
            # sessions are created in rapid succession without session_id.
            safe_ts = dt.strftime("%Y%m%dT%H%M%S_%f")
            filename = f"session_{safe_ts}"
        except ValueError:
            # Fallback: use only the digits from created_at; if empty, use current UTC timestamp
            safe_ts = "".join(c for c in memory.created_at if c.isdigit())
            if not safe_ts:
                # Use current UTC timestamp with microseconds for uniqueness
                safe_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%f")
            filename = f"session_{safe_ts}"
    # Sanitize filename by replacing non-alphanumeric characters with underscores
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in filename)


def save_session_memory(
    memory: SessionMemory,
    repo_root: Path,
    *,
    raise_on_failure: bool = False,
) -> Path | None:
    """Save session memory to .aprd/memory/{sanitized_session_id}.json.

    Creates the directory structure if it doesn't exist. The session_id is
    sanitized by replacing non-alphanumeric characters with underscores.

    Args:
        memory: The SessionMemory to save.
        repo_root: Repository root directory.
        raise_on_failure: If True, raise OSError on failure instead of returning None.
            Use this when session memory persistence is critical and failures
            should be surfaced to the user.

    Returns:
        Path to the saved memory file, or None if save failed (and raise_on_failure=False).

    Raises:
        OSError: If raise_on_failure=True and saving fails (directory creation or file write).
    """
    memory_dir = repo_root / ".aprd" / "memory"
    try:
        memory_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.error(
            "Failed to create session memory directory %s: %s (%s)",
            memory_dir,
            e,
            type(e).__name__,
        )
        if raise_on_failure:
            raise
        return None

    filename = _generate_session_filename(memory)
    filepath = memory_dir / f"{filename}.json"

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(memory.to_dict(), f, indent=2)
    except (OSError, TypeError) as e:
        logger.error(
            "Failed to save session memory to %s: %s (%s)",
            filepath,
            e,
            type(e).__name__,
        )
        if raise_on_failure:
            # Re-raise OSError directly; wrap TypeError in OSError for consistent interface
            if isinstance(e, TypeError):
                raise OSError(f"Failed to serialize session memory: {e}") from e
            raise
        return None

    logger.debug("Saved session memory to %s", filepath)
    return filepath


def load_session_memory(filepath: Path) -> LoadSessionResult:
    """Load session memory from a JSON file.

    Returns a LoadSessionResult that distinguishes between different failure modes,
    allowing callers to handle each case appropriately (e.g., file not found is
    normal on first run, but corrupted JSON indicates a problem).

    Args:
        filepath: Path to the memory file.

    Returns:
        LoadSessionResult with either:
        - memory set and failure_reason=None on success
        - memory=None with failure_reason indicating why loading failed
    """
    if not filepath.exists():
        logger.debug("Session memory file does not exist: %s", filepath)
        return LoadSessionResult(
            memory=None,
            failure_reason=LoadFailureReason.NOT_FOUND,
            error_message=f"File does not exist: {filepath}",
        )

    try:
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
        memory = SessionMemory.from_dict(data)
        return LoadSessionResult(memory=memory)
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON in {filepath}: {e}"
        logger.error("Corrupted session memory file %s: invalid JSON: %s", filepath, e)
        return LoadSessionResult(
            memory=None,
            failure_reason=LoadFailureReason.CORRUPTED_JSON,
            error_message=error_msg,
        )
    except OSError as e:
        error_msg = f"Failed to read {filepath}: {e} ({type(e).__name__})"
        logger.error(
            "Failed to read session memory from %s: %s (%s)",
            filepath,
            e,
            type(e).__name__,
        )
        return LoadSessionResult(
            memory=None,
            failure_reason=LoadFailureReason.IO_ERROR,
            error_message=error_msg,
        )
    except KeyError as e:
        # Missing expected field - format version mismatch or incomplete data
        error_msg = f"Missing required field in {filepath}: {e}"
        logger.error(
            "Session memory file %s missing required field: %s",
            filepath,
            e,
        )
        return LoadSessionResult(
            memory=None,
            failure_reason=LoadFailureReason.INVALID_FORMAT,
            error_message=error_msg,
        )
    except TypeError as e:
        # Type mismatch during construction (e.g., string where list expected)
        error_msg = f"Type mismatch in {filepath}: {e}"
        logger.error(
            "Session memory file %s has type mismatch: %s",
            filepath,
            e,
        )
        return LoadSessionResult(
            memory=None,
            failure_reason=LoadFailureReason.INVALID_FORMAT,
            error_message=error_msg,
        )
    except ValueError as e:
        # Validation failure (e.g., negative cost/duration values)
        error_msg = f"Invalid values in {filepath}: {e}"
        logger.error(
            "Session memory file %s has invalid values: %s",
            filepath,
            e,
        )
        return LoadSessionResult(
            memory=None,
            failure_reason=LoadFailureReason.INVALID_FORMAT,
            error_message=error_msg,
        )


def extract_progress_from_response(response: ClaudeHeadlessResponse) -> dict[str, Any]:
    """Extract progress metrics from a Claude response.

    This function provides a standardized way to extract observability data
    from Claude responses for tracking and monitoring.

    Args:
        response: The ClaudeHeadlessResponse to extract from.

    Returns:
        Dictionary with progress metrics.
    """
    return {
        "duration_ms": response.duration_ms,
        "duration_api_ms": response.duration_api_ms,
        "cost_usd": response.total_cost_usd,
        "session_id": response.session_id,
        "is_error": response.is_error,
        "num_turns": response.num_turns,
    }


class StallDetector:
    """Detect when execution appears stalled.

    This class monitors execution progress and detects two types of stalls:
    1. No output for too long (output-based detection)
    2. No progress across multiple iterations (iteration-based detection)

    **Status: NOT YET INTEGRATED (Future Enhancement)**
    This class is implemented and tested but not yet integrated into the execution loops.
    Integration is deferred intentionally: the existing timeout-based detection in
    claude_exec_streaming provides adequate stall prevention for current use cases.

    Future integration would require:
    - Wiring up on_output callback in review_loop.py streaming handler
    - Adding record_iteration calls after each fix cycle
    - Determining appropriate threshold values through production observation

    The class is maintained in working state (with full test coverage) to support
    future enhancement without requiring a major rewrite. Tests are not skipped
    because they validate the implementation correctness for when integration occurs.

    Note: This class is not thread-safe. If used from multiple threads, external
    synchronization is required.

    Usage:
        detector = StallDetector()

        # Reset at the start of each execution phase
        detector.reset()

        # During streaming, record output activity
        detector.record_output()

        # After each iteration, record progress
        detector.record_iteration(tasks_left=5)

        # Check for stalls
        is_stalled, reason = detector.check_stall()
        if is_stalled:
            logger.warning("Execution stalled: %s", reason)

    Attributes:
        no_output_threshold_seconds: Time without output before considering stalled.
        no_progress_threshold_iterations: Iterations without progress before stalled.
    """

    def __init__(
        self,
        no_output_threshold_seconds: float = 120.0,
        no_progress_threshold_iterations: int = 3,
    ) -> None:
        """Initialize the stall detector.

        Args:
            no_output_threshold_seconds: Seconds without output before stall.
                Default is 120 seconds (2 minutes). Must be positive.
            no_progress_threshold_iterations: Iterations without task progress
                before considering stalled. Default is 3 iterations. Must be >= 1.

        Raises:
            ValueError: If thresholds are not positive.
        """
        # Validate thresholds before assignment
        if no_output_threshold_seconds <= 0:
            msg = f"no_output_threshold_seconds must be positive, got {no_output_threshold_seconds}"
            raise ValueError(msg)
        if no_progress_threshold_iterations < 1:
            msg = f"no_progress_threshold_iterations must be at least 1, got {no_progress_threshold_iterations}"
            raise ValueError(msg)

        # Store thresholds as private attributes (read-only via properties)
        self._no_output_threshold_seconds = no_output_threshold_seconds
        self._no_progress_threshold_iterations = no_progress_threshold_iterations

        # Output tracking
        self._last_output_time: float = time.monotonic()

        # Progress tracking
        self._iteration_count: int = 0
        self._last_tasks_left: int | None = None
        self._no_progress_streak: int = 0

    @property
    def no_output_threshold_seconds(self) -> float:
        """Time without output before considering stalled (read-only)."""
        return self._no_output_threshold_seconds

    @property
    def no_progress_threshold_iterations(self) -> int:
        """Iterations without progress before considering stalled (read-only)."""
        return self._no_progress_threshold_iterations

    def record_output(self) -> None:
        """Record that output was received.

        Call this whenever output is received from the execution to reset
        the output timeout.
        """
        self._last_output_time = time.monotonic()

    def record_iteration(self, tasks_left: int | None = None) -> None:
        """Record the completion of an iteration.

        Args:
            tasks_left: Number of tasks remaining, if known. Used to detect
                progress (decreasing task count = progress).
        """
        self._iteration_count += 1

        if tasks_left is not None:
            if self._last_tasks_left is not None:
                if tasks_left < self._last_tasks_left:
                    # Progress! Reset the streak
                    self._no_progress_streak = 0
                else:
                    # No progress
                    self._no_progress_streak += 1
            else:
                # First observation of tasks_left - treat as progress and reset streak.
                # This ensures the first iteration doesn't incorrectly contribute to
                # stall detection when tasks_left is provided for the first time.
                self._no_progress_streak = 0
            self._last_tasks_left = tasks_left

    def check_stall(self) -> tuple[bool, str]:
        """Check if execution appears stalled.

        Returns:
            Tuple of (is_stalled, reason). If not stalled, reason is empty.
        """
        # Check output timeout
        elapsed_since_output = time.monotonic() - self._last_output_time
        if elapsed_since_output >= self.no_output_threshold_seconds:
            return (
                True,
                f"No output for {elapsed_since_output:.1f} seconds "
                f"(threshold: {self.no_output_threshold_seconds}s)",
            )

        # Check progress streak
        if self._no_progress_streak >= self.no_progress_threshold_iterations:
            return (
                True,
                f"No task progress for {self._no_progress_streak} iterations "
                f"(threshold: {self.no_progress_threshold_iterations})",
            )

        return False, ""

    def reset(self) -> None:
        """Reset all tracking state.

        Call this when starting a new execution phase.
        """
        self._last_output_time = time.monotonic()
        self._iteration_count = 0
        self._last_tasks_left = None
        self._no_progress_streak = 0

    @property
    def iteration_count(self) -> int:
        """Get the current iteration count."""
        return self._iteration_count

    @property
    def no_progress_streak(self) -> int:
        """Get the current no-progress streak."""
        return self._no_progress_streak

    @property
    def seconds_since_output(self) -> float:
        """Get seconds since last output."""
        return time.monotonic() - self._last_output_time
