"""Structured error handling and classification.

This module provides error categorization, recovery hints, and
structured error reporting for automation failures.
"""

from __future__ import annotations

import json
import os
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from .logging_utils import logger


class ErrorCategory(str, Enum):
    """Categories of errors for classification."""

    NETWORK = "network"  # Network connectivity issues
    GIT = "git"  # Git operation failures
    API = "api"  # GitHub/API rate limits or failures
    RUNNER = "runner"  # Codex/Claude execution failures
    FILESYSTEM = "filesystem"  # File I/O errors
    CONFIG = "config"  # Configuration errors
    TIMEOUT = "timeout"  # Operation timeouts
    RESOURCE = "resource"  # Memory/disk/rate limits
    VALIDATION = "validation"  # Input validation errors
    INTERNAL = "internal"  # Internal/unexpected errors


class ErrorSeverity(str, Enum):
    """Severity levels for errors."""

    DEBUG = "debug"  # Informational, auto-recovered
    WARNING = "warning"  # Handled but notable
    ERROR = "error"  # Operation failed, may recover
    CRITICAL = "critical"  # Session cannot continue


@dataclass
class StructuredError:
    """Structured error with context and recovery hints."""

    message: str
    category: ErrorCategory
    severity: ErrorSeverity
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    phase: str | None = None
    operation: str | None = None
    exception_type: str | None = None
    exception_traceback: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    recovery_hint: str | None = None
    retryable: bool = False
    retry_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp,
            "message": self.message,
            "category": self.category.value,
            "severity": self.severity.value,
            "phase": self.phase,
            "operation": self.operation,
            "exception_type": self.exception_type,
            "exception_traceback": self.exception_traceback,
            "context": self.context,
            "recovery_hint": self.recovery_hint,
            "retryable": self.retryable,
            "retry_count": self.retry_count,
        }

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict())


# Error patterns for automatic categorization
# Note: All patterns are lowercase since classify_error() uses case-insensitive matching
ERROR_PATTERNS: dict[ErrorCategory, list[str]] = {
    ErrorCategory.NETWORK: [
        "connection reset",
        "connection refused",
        "connection timed out",
        "could not resolve host",
        "network is unreachable",
        "ssl certificate",
        "socket.timeout",
        "urllib.error.urlerror",
        "requests.exceptions.connectionerror",
    ],
    ErrorCategory.GIT: [
        "fatal: ",
        "error: cannot lock ref",
        "not a git repository",
        "failed to push",
        "merge conflict",
        "unmerged files",
        "git checkout",
        "git stash",
        "your branch is behind",
    ],
    ErrorCategory.API: [
        "rate limit",
        "403 forbidden",
        "401 unauthorized",
        "api rate limit exceeded",
        "secondary rate limit",
        "gh api",
        "github api",
    ],
    ErrorCategory.RUNNER: [
        "codex",
        "claude",
        "codex execution failed",
        "runner returned non-zero",
        "codex_full_auto_block",
        "readonly mode",
        "empty response from agent",
        "no json object found in response",
        "invalid tracker",
        "tracker generation failed",
        "unbalanced braces in json response",
    ],
    ErrorCategory.TIMEOUT: [
        "timed out",
        "timeouterror",
        "operation timed out",
        "deadline exceeded",
    ],
    ErrorCategory.FILESYSTEM: [
        "permission denied",
        "no such file or directory",
        "file exists",
        "is a directory",
        "not a directory",
        "disk quota exceeded",
        "no space left on device",
    ],
}

# Recovery hints for common error patterns
# Note: All keys are lowercase since classify_error() uses case-insensitive matching
RECOVERY_HINTS: dict[str, str] = {
    "connection reset": "Network issue - will retry automatically",
    "connection timed out": "Server not responding - check network connectivity",
    "rate limit": "API rate limited - waiting before retry",
    "merge conflict": "Manual resolution required - resolve conflicts and run --resume",
    "not a git repository": "Run command from within a git repository",
    "permission denied": "Check file permissions or run with appropriate privileges",
    "no space left on device": "Free up disk space before continuing",
    "readonly mode": "Codex entered readonly mode - check CODEX_AUTO_FULL_AUTO env var",
    "codex_full_auto_block": "Unsafe execution blocked - use --allow-unsafe-execution",
    "empty response from agent": "Agent returned no output - check API rate limits and authentication",
    "no json object found in response": "Agent output was not valid JSON - may need to retry or adjust prompt",
    "unbalanced braces in json response": "Agent output was truncated - context may be too large",
}


def classify_error(
    error: Exception | str,
    *,
    operation: str | None = None,
    phase: str | None = None,
) -> StructuredError:
    """Classify an error and create a structured error object.

    Args:
        error: Exception or error message string.
        operation: The operation that failed.
        phase: Current phase when error occurred.

    Returns:
        StructuredError with category and recovery hints.
    """
    if isinstance(error, Exception):
        message = str(error)
        exception_type = type(error).__name__
        exception_traceback = traceback.format_exc()
    else:
        message = error
        exception_type = None
        exception_traceback = None

    # Determine category
    category = ErrorCategory.INTERNAL
    for cat, patterns in ERROR_PATTERNS.items():
        for pattern in patterns:
            if pattern.lower() in message.lower():
                category = cat
                break
        if category != ErrorCategory.INTERNAL:
            break

    # Determine severity
    if category in (ErrorCategory.NETWORK, ErrorCategory.TIMEOUT) or (
        category == ErrorCategory.API and "rate limit" in message.lower()
    ):
        severity = ErrorSeverity.WARNING
        retryable = True
    elif category in (ErrorCategory.GIT, ErrorCategory.RUNNER):
        severity = ErrorSeverity.ERROR
        retryable = False
    elif category == ErrorCategory.CONFIG:
        severity = ErrorSeverity.CRITICAL
        retryable = False
    else:
        severity = ErrorSeverity.ERROR
        retryable = False

    # Find recovery hint
    recovery_hint = None
    for pattern, hint in RECOVERY_HINTS.items():
        if pattern.lower() in message.lower():
            recovery_hint = hint
            break

    return StructuredError(
        message=message,
        category=category,
        severity=severity,
        phase=phase,
        operation=operation,
        exception_type=exception_type,
        exception_traceback=exception_traceback,
        recovery_hint=recovery_hint,
        retryable=retryable,
    )


class ErrorLog:
    """Persistent error log for a session."""

    def __init__(self, session_id: str, log_dir: Path | None = None):
        """Initialize error log.

        Args:
            session_id: Session identifier.
            log_dir: Optional directory for error logs.
        """
        self.session_id = session_id
        self._log_dir = log_dir or self._get_default_log_dir()
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._log_path = self._log_dir / f"{session_id}.errors.jsonl"
        self._errors: list[StructuredError] = []

    @staticmethod
    def _get_default_log_dir() -> Path:
        """Get default error log directory."""
        xdg_config = os.getenv("XDG_CONFIG_HOME", None)
        if xdg_config and xdg_config.strip():
            base_config = Path(xdg_config).expanduser()
        else:
            base_config = Path.home() / ".config"
        return base_config / "aprd" / "errors"

    def log(self, error: StructuredError) -> None:
        """Log a structured error.

        Args:
            error: StructuredError to log.
        """
        self._errors.append(error)

        try:
            with open(self._log_path, "a") as f:
                f.write(error.to_json() + "\n")
        except OSError as e:
            logger.warning("Failed to write error log: %s", e)

        # Also log to standard logger
        log_msg = f"[{error.category.value}] {error.message}"
        if error.recovery_hint:
            log_msg += f" (Hint: {error.recovery_hint})"

        if error.severity == ErrorSeverity.CRITICAL:
            logger.critical(log_msg)
        elif error.severity == ErrorSeverity.ERROR:
            logger.error(log_msg)
        elif error.severity == ErrorSeverity.WARNING:
            logger.warning(log_msg)
        else:
            logger.debug(log_msg)

    def log_exception(
        self,
        error: Exception,
        *,
        operation: str | None = None,
        phase: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> StructuredError:
        """Log an exception with automatic classification.

        Args:
            error: The exception to log.
            operation: Operation that failed.
            phase: Current phase.
            context: Additional context.

        Returns:
            The structured error that was logged.
        """
        structured = classify_error(error, operation=operation, phase=phase)
        if context:
            structured.context.update(context)
        self.log(structured)
        return structured

    @property
    def errors(self) -> list[StructuredError]:
        """Get all logged errors."""
        return self._errors.copy()

    @property
    def critical_errors(self) -> list[StructuredError]:
        """Get critical errors that prevent continuation."""
        return [e for e in self._errors if e.severity == ErrorSeverity.CRITICAL]

    @property
    def retryable_errors(self) -> list[StructuredError]:
        """Get errors that can be retried."""
        return [e for e in self._errors if e.retryable]

    def get_summary(self) -> dict[str, Any]:
        """Get error summary statistics.

        Returns:
            Summary dictionary with counts by category and severity.
        """
        by_category: dict[str, int] = {}
        by_severity: dict[str, int] = {}

        for error in self._errors:
            by_category[error.category.value] = (
                by_category.get(error.category.value, 0) + 1
            )
            by_severity[error.severity.value] = (
                by_severity.get(error.severity.value, 0) + 1
            )

        return {
            "total": len(self._errors),
            "by_category": by_category,
            "by_severity": by_severity,
            "has_critical": len(self.critical_errors) > 0,
            "retryable_count": len(self.retryable_errors),
        }


def load_error_log(
    session_id: str, log_dir: Path | None = None
) -> list[StructuredError]:
    """Load errors from a session's error log.

    Args:
        session_id: Session identifier.
        log_dir: Optional directory containing error logs.

    Returns:
        List of StructuredError objects.
    """
    if log_dir is None:
        xdg_config = os.getenv("XDG_CONFIG_HOME", None)
        if xdg_config and xdg_config.strip():
            base_config = Path(xdg_config).expanduser()
        else:
            base_config = Path.home() / ".config"
        log_dir = base_config / "aprd" / "errors"

    log_path = log_dir / f"{session_id}.errors.jsonl"
    if not log_path.exists():
        return []

    errors = []
    try:
        with open(log_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        errors.append(
                            StructuredError(
                                message=data.get("message", "Unknown error"),
                                category=ErrorCategory(
                                    data.get("category", "internal")
                                ),
                                severity=ErrorSeverity(data.get("severity", "error")),
                                timestamp=data.get("timestamp", ""),
                                phase=data.get("phase"),
                                operation=data.get("operation"),
                                exception_type=data.get("exception_type"),
                                exception_traceback=data.get("exception_traceback"),
                                context=data.get("context", {}),
                                recovery_hint=data.get("recovery_hint"),
                                retryable=data.get("retryable", False),
                                retry_count=data.get("retry_count", 0),
                            )
                        )
                    except (json.JSONDecodeError, ValueError):
                        continue
    except OSError as e:
        logger.warning("Failed to load error log %s: %s", log_path, e)

    return errors
