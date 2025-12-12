"""Integrations with external agents (Codex, CodeRabbit, Claude)."""

from __future__ import annotations

import errno
import os
import random
import re
import select
import subprocess
import sys
import time
from contextlib import suppress
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import IO, Any, Callable, Optional

from .command import (
    run_cmd,
    verify_unsafe_execution_ready,
    popen_streaming,
    validate_stdin,
)
from .logging_utils import logger
from .utils import extract_called_process_error_details

# fcntl is Unix-only; import conditionally to allow module import on Windows.
# We use a boolean flag (HAS_FCNTL) for type-safe availability checks, avoiding
# the type: ignore comments that would be needed if fcntl could be None.
# On Windows, HAS_FCNTL is False and streaming functions will raise OSError.
try:
    import fcntl

    HAS_FCNTL = True
except ImportError:  # pragma: no cover (Windows)
    HAS_FCNTL = False

RATE_LIMIT_JITTER_MIN = -3
RATE_LIMIT_JITTER_MAX = 3
RATE_LIMIT_MIN_SLEEP_SECONDS = 5
RATE_LIMIT_MAX_SLEEP_SECONDS = 900
CODERABBIT_PROMPT_TIMEOUT_SECONDS = 900

# Maximum characters of stderr to include in error messages to prevent
# excessively long exception messages. Stderr can contain binary data or
# very long output from crashed processes.
STDERR_ERROR_MESSAGE_MAX_CHARS = 1000

# Patterns for sanitizing sensitive information from stderr before including
# in exception messages. These patterns catch common credential/token formats.
_SENSITIVE_STDERR_PATTERNS = [
    # API keys/tokens with common prefixes
    (re.compile(r"\b(sk-[a-zA-Z0-9]{20,})\b"), "<REDACTED_API_KEY>"),
    (re.compile(r"\b(ghp_[a-zA-Z0-9]{36,})\b"), "<REDACTED_GH_TOKEN>"),
    (re.compile(r"\b(gho_[a-zA-Z0-9]{36,})\b"), "<REDACTED_GH_TOKEN>"),
    (re.compile(r"\b(github_pat_[a-zA-Z0-9_]{22,})\b"), "<REDACTED_GH_PAT>"),
    # Bearer tokens
    (re.compile(r"(Bearer\s+)[a-zA-Z0-9_\-\.]+", re.IGNORECASE), r"\1<REDACTED>"),
    # Basic auth (base64 encoded credentials)
    (re.compile(r"(Basic\s+)[a-zA-Z0-9+/=]+", re.IGNORECASE), r"\1<REDACTED>"),
    # Key=value patterns for sensitive keys
    (
        re.compile(
            r"\b(api[_-]?key|token|secret|password|credential|auth)[=:]\s*['\"]?[^\s'\"]+['\"]?",
            re.IGNORECASE,
        ),
        r"\1=<REDACTED>",
    ),
    # File paths that might reveal usernames or directory structure (Unix)
    (re.compile(r"/home/[a-zA-Z0-9_\-]+/"), "/home/<USER>/"),
    (re.compile(r"/Users/[a-zA-Z0-9_\-]+/"), "/Users/<USER>/"),
    # Windows user directory paths (e.g., C:\Users\username\ or D:/Users/username/)
    # Handles both backslash and forward slash path separators via [\\/]+ pattern.
    # The trailing separator is optional ([\\/]*) to match paths like "C:\Users\username"
    # without a trailing slash, which commonly appear in error messages.
    #
    # PATH NORMALIZATION BEHAVIOR: The replacement ALWAYS uses backslashes regardless
    # of the original path's separator style. This means:
    # - Input:  "D:/Users/alice/file.txt" (forward slashes)
    # - Output: "<DRIVE>:\Users\<USER>\" (backslashes)
    #
    # Rationale for backslash normalization:
    # 1. Windows users expect backslashes in path output and will find it clearer
    # 2. Sanitized paths appear in error messages/logs meant for user debugging
    # 3. Consistency with how Windows displays paths natively
    # 4. Forward slashes in Windows paths are typically from cross-platform code
    #    (e.g., Python's pathlib), so normalizing improves debugging context
    #
    # Trade-off: Paths that intentionally used forward slashes (which Windows accepts)
    # will be normalized to backslashes. This is acceptable because the sanitized output
    # is for display/logging only, not for programmatic path operations.
    (
        re.compile(r"[A-Za-z]:[\\/]+Users[\\/][^\\/]+[\\/]*", re.IGNORECASE),
        r"<DRIVE>:\\Users\\<USER>\\",
    ),
]


def _sanitize_stderr_for_exception(stderr: str, max_chars: int) -> str:
    """Sanitize stderr content before including in exception messages.

    Removes/redacts potentially sensitive information like API keys, tokens,
    passwords, and user-specific file paths from stderr to prevent accidental
    exposure in exception messages or logs.

    Args:
        stderr: Raw stderr content to sanitize.
        max_chars: Maximum characters to include (truncates if exceeded).

    Returns:
        Sanitized and potentially truncated stderr string.
    """
    if not stderr:
        return ""

    sanitized = stderr
    for pattern, replacement in _SENSITIVE_STDERR_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)

    if len(sanitized) > max_chars:
        return sanitized[:max_chars] + "...(truncated)"
    return sanitized


# I/O buffer and polling constants for claude_exec_streaming.
# These values can be overridden via environment variables for performance tuning.
#
# IMPORTANT: These environment variables are read ONCE at module import time.
# To configure different values:
# - Set the environment variable BEFORE importing tools.auto_prd.agents
# - For tests that need different values, use unittest.mock.patch on the
#   STREAMING_READ_CHUNK_SIZE or STREAMING_SELECT_TIMEOUT_SECONDS constants
#
# This design trades off runtime configurability for startup performance,
# as these values typically don't need to change during execution.

# Read streaming chunk size from environment once at import time.
# The default 4KB chunk size balances memory usage with system call overhead
# for typical streaming scenarios.
_raw_chunk_size = os.getenv("AUTO_PRD_STREAMING_CHUNK_SIZE")
if _raw_chunk_size is None:
    STREAMING_READ_CHUNK_SIZE = 4096
else:
    try:
        _chunk_size_val = int(_raw_chunk_size)
        if _chunk_size_val > 0:
            STREAMING_READ_CHUNK_SIZE = _chunk_size_val
        else:
            logger.warning(
                "AUTO_PRD_STREAMING_CHUNK_SIZE must be > 0, got %r; using default 4096",
                _raw_chunk_size,
            )
            STREAMING_READ_CHUNK_SIZE = 4096
    except ValueError:
        logger.warning(
            "Invalid AUTO_PRD_STREAMING_CHUNK_SIZE value %r; using default 4096",
            _raw_chunk_size,
        )
        STREAMING_READ_CHUNK_SIZE = 4096

# Read streaming poll timeout from environment once at import time.
# The default 100ms timeout provides a balance between responsive streaming
# and CPU efficiency. Lower values increase responsiveness but consume more CPU.
_raw_poll_timeout = os.getenv("AUTO_PRD_STREAMING_POLL_TIMEOUT")
if _raw_poll_timeout is None:
    STREAMING_SELECT_TIMEOUT_SECONDS = 0.1
else:
    try:
        _timeout_val = float(_raw_poll_timeout)
        if _timeout_val > 0:
            STREAMING_SELECT_TIMEOUT_SECONDS = _timeout_val
        else:
            logger.warning(
                "AUTO_PRD_STREAMING_POLL_TIMEOUT must be > 0, got %r; using default 0.1",
                _raw_poll_timeout,
            )
            STREAMING_SELECT_TIMEOUT_SECONDS = 0.1
    except ValueError:
        logger.warning(
            "Invalid AUTO_PRD_STREAMING_POLL_TIMEOUT value %r; using default 0.1",
            _raw_poll_timeout,
        )
        STREAMING_SELECT_TIMEOUT_SECONDS = 0.1

# Clean up module-level temporaries to avoid polluting namespace.
# Note: _chunk_size_val and _timeout_val are only defined when:
# - The environment variable is set (not None), AND
# - The int()/float() parsing succeeds.
# If the env var is unset or parsing fails, the variable won't be defined.
# We use contextlib.suppress(NameError) to unconditionally attempt deletion,
# which is cleaner than try/except blocks and handles all cases uniformly.
del _raw_chunk_size, _raw_poll_timeout
with suppress(NameError):
    del _chunk_size_val
with suppress(NameError):
    del _timeout_val


def _timeout_from_env(env_key: str, default: int | None) -> int | None:
    raw = os.getenv(env_key)
    if raw is None:
        return default

    normalized = raw.strip().lower()
    if not normalized or normalized in {"none", "no", "off", "disable", "disabled"}:
        return None

    try:
        parsed = int(normalized)
    except ValueError:
        default_str = "no timeout" if default is None else str(default)
        logger.warning(
            "Invalid %s value %r; falling back to %s", env_key, raw, default_str
        )
        return default

    if parsed <= 0:
        return None
    return parsed


def get_codex_exec_timeout() -> int | None:
    """Get the Codex execution timeout from environment variables.

    Returns:
        The timeout in seconds from AUTO_PRD_CODEX_TIMEOUT_SECONDS, or None if:
        - The environment variable is not set (default: no timeout)
        - The value is explicitly "none", "no", "off", "disable", or "disabled"
        - The value is <= 0 (treated as "no timeout")
    """
    return _timeout_from_env("AUTO_PRD_CODEX_TIMEOUT_SECONDS", None)


def get_claude_exec_timeout() -> int | None:
    """Get the Claude execution timeout from environment variables.

    Returns:
        The timeout in seconds from AUTO_PRD_CLAUDE_TIMEOUT_SECONDS, or None if:
        - The environment variable is not set (default: no timeout)
        - The value is explicitly "none", "no", "off", "disable", or "disabled"
        - The value is <= 0 (treated as "no timeout")

    Note:
        When this function returns None, claude_exec and claude_exec_streaming
        will run without any time limit. This is intentional for long-running
        operations where timeout is not desired. Callers who need guaranteed
        timeout enforcement should pass an explicit timeout parameter.
    """
    return _timeout_from_env("AUTO_PRD_CLAUDE_TIMEOUT_SECONDS", None)


# Use a cryptographically secure RNG for backoff jitter to avoid predictable retry cadences.
_rate_limit_rng = random.SystemRandom()


def codex_exec(
    prompt: str,
    repo_root: Path,
    model: str = "gpt-5-codex",
    enable_search: bool = True,
    yolo: Optional[bool] = None,
    allow_unsafe_execution: Optional[bool] = None,
    dry_run: bool = False,
    extra: Optional[list[str]] = None,
) -> tuple[str, str]:
    os.environ.setdefault("CI", "1")
    allow_flag = allow_unsafe_execution
    if yolo is not None:
        logger.warning(
            "codex_exec: 'yolo' is deprecated; use allow_unsafe_execution instead"
        )
        if allow_flag is None:
            allow_flag = yolo
        else:
            allow_flag = allow_flag or yolo
    allow_flag = bool(allow_flag)
    args: list[str] = ["codex"]
    if enable_search:
        args.append("--search")
    if not allow_flag and not dry_run:
        raise PermissionError(
            "Codex executor requires allow_unsafe_execution=True to bypass permissions."
        )
    if allow_flag:
        verify_unsafe_execution_ready()
        args.append("--dangerously-bypass-approvals-and-sandbox")
        args.extend(["--config", 'sandbox_mode="danger-full-access"'])
        args.extend(["--config", 'shell_environment_policy.inherit="all"'])
    if extra:
        args.extend(extra)
    args.extend(["exec", "--model", model, "-"])
    if dry_run:
        logger.info("Dry run enabled; skipping Codex execution. Args: %s", args)
        return "DRY_RUN", ""
    out, stderr, _ = run_cmd(
        args,
        cwd=repo_root,
        check=True,
        stdin=prompt,
        timeout=get_codex_exec_timeout(),
    )

    # Log warning if stdout is empty but stderr has content (may indicate rate limiting)
    if not out.strip() and stderr.strip():
        logger.warning(
            "Codex returned empty stdout. Stderr content: %s",
            stderr[:500] if len(stderr) > 500 else stderr,
        )

    return out, stderr


def parse_rate_limit_sleep(message: str) -> Optional[int]:
    if not message:
        return None

    # Match rate limit messages like:
    #   "try after 10 minutes and 14 seconds"
    #   "try again after 5 mins and 2 secs"
    #   "try after 1 minute 30 seconds"
    #   "try again after 12 min 5 sec"
    #   "try after 0 minutes and 45 seconds"
    # This pattern extracts minutes and seconds when both are present.
    match = re.search(
        r"try (?:again )?after\s+(\d+)\s*(?:minute(?:s)?|min(?:s)?)\s+(?:and\s+)?(\d+)\s*(?:second(?:s)?|sec(?:s)?)",
        message,
        re.IGNORECASE,
    )
    if match:
        minutes = int(match.group(1))
        seconds = int(match.group(2))
        return minutes * 60 + seconds + 5

    # HTTP Retry-After with HTTP-date, e.g., "Retry-After: Wed, 21 Oct 2015 07:28:00 GMT"
    http_date = re.search(
        r"retry-after[:=]\s*([A-Za-z]{3},\s*\d{1,2}\s*[A-Za-z]{3}\s*\d{4}\s*\d{2}:\d{2}:\d{2}\s*GMT)",
        message,
        re.IGNORECASE,
    )
    if http_date:
        try:
            retry_at = parsedate_to_datetime(http_date.group(1))
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            retry_at = retry_at.astimezone(timezone.utc)
            delta = (retry_at - datetime.now(timezone.utc)).total_seconds()
            if delta > 0:
                return int(delta) + 5
        except (TypeError, ValueError):
            logger.debug(
                "Failed to parse HTTP-date Retry-After: %s", http_date.group(1)
            )

    # e.g. "try again in 10m 14s" (gh output) or "2m 30s"
    match = re.search(r"\b(\d+)\s*m\s*(\d+)\s*s\b", message, re.IGNORECASE)
    if match:
        return int(match.group(1)) * 60 + int(match.group(2)) + 5

    # e.g. "try again in 5 minutes" or "in 12 min"
    match = re.search(
        r"(?:try (?:again )?(?:after|in)|in)\s+(\d+)\s*(?:minute(?:s)?|min(?:s)?)\b",
        message,
        re.IGNORECASE,
    )
    if match:
        return int(match.group(1)) * 60 + 5

    # e.g. "try again in 75 seconds" or "try after 75 sec"
    match = re.search(
        r"(?:try (?:again )?(?:after|in)|in)\s+(\d+)\s*(?:second(?:s)?|sec(?:s)?)\b",
        message,
        re.IGNORECASE,
    )
    if match:
        return int(match.group(1)) + 5

    # HTTP "Retry-After: 600"
    match = re.search(r"retry-after[:=]\s*(\d+)", message, re.IGNORECASE)
    if match:
        return int(match.group(1)) + 5

    return None


def coderabbit_prompt_only(base_branch: str | None, repo_root: Path) -> str:
    args = ["coderabbit", "--prompt-only"]
    if base_branch:
        args += ["--base", base_branch]
    attempts = 0
    while True:
        attempts += 1
        try:
            out, _, _ = run_cmd(
                args, cwd=repo_root, timeout=CODERABBIT_PROMPT_TIMEOUT_SECONDS
            )
            return out.strip()
        except subprocess.CalledProcessError as exc:
            msg = extract_called_process_error_details(exc)
            sleep_secs = parse_rate_limit_sleep(msg)
            if sleep_secs and attempts <= 3:
                capped = max(
                    RATE_LIMIT_MIN_SLEEP_SECONDS,
                    min(RATE_LIMIT_MAX_SLEEP_SECONDS, sleep_secs),
                )
                jitter = _rate_limit_rng.randint(
                    RATE_LIMIT_JITTER_MIN, RATE_LIMIT_JITTER_MAX
                )
                wait = max(1, capped + jitter)
                sleep_for = min(wait, RATE_LIMIT_MAX_SLEEP_SECONDS)
                logger.warning(
                    "CodeRabbit rate limited; sleeping %s seconds before retry (attempt %d/3)",
                    sleep_for,
                    attempts,
                )
                time.sleep(sleep_for)
                continue
            # Determine appropriate log level based on error type:
            # - INFO: CodeRabbit intentionally not configured (expected, not actionable)
            # - WARNING: Rate limiting, service errors, or other failures that may result
            #   in incomplete review and warrant user attention
            error_str = (msg or str(exc)).lower()
            is_config_skip = "not configured" in error_str or "not found" in error_str
            log_fn = logger.info if is_config_skip else logger.warning
            log_fn(
                "CodeRabbit analysis unavailable after %d attempts: %s. "
                "Continuing without CodeRabbit findings - manual review recommended.",
                attempts,
                msg or exc,
            )
            return ""


def coderabbit_has_findings(text: str) -> bool:
    if not text.strip():
        return False
    lowered = text.lower()
    for marker in (
        "file:",
        "line",
        "issue",
        "prompt for ai agent",
        "consider",
        "fix",
        "security",
        "leak",
        "race",
    ):
        if marker in lowered:
            return True
    return False


def _resolve_unsafe_flag(
    allow_unsafe_execution: Optional[bool],
    yolo: Optional[bool],
    caller: str,
) -> bool:
    """Resolve the allow_unsafe_execution flag, handling deprecated yolo parameter."""
    allow_flag = allow_unsafe_execution
    if yolo is not None:
        logger.warning("%s: 'yolo' is deprecated; use allow_unsafe_execution", caller)
        if allow_flag is None:
            allow_flag = yolo
        else:
            allow_flag = allow_flag or yolo
    return bool(allow_flag)


def _build_claude_args(
    allow_flag: bool,
    model: str | None,
    enable_search: bool,
    extra: list[str] | tuple[str, ...] | None,
) -> list[str]:
    """Build the CLI arguments for Claude execution.

    This is the centralized location for argument construction and validation.
    All callers (claude_exec, claude_exec_streaming) delegate argument building
    here to ensure consistent validation and construction.

    Args:
        allow_flag: Whether to add --dangerously-skip-permissions flag.
        model: Optional model name to use.
        enable_search: Whether search is enabled (currently ignored by Claude CLI).
        extra: Optional list of additional string arguments to pass to Claude.
            Must be a list or tuple of strings if provided. Validated here
            before any arguments are constructed to fail fast with clear errors.

    Returns:
        List of CLI arguments for Claude execution.

    Raises:
        TypeError: If extra is provided but is not a list/tuple of strings.
            This is raised immediately upon entry, before any other processing,
            to provide clear error messages with full caller context.
    """
    # Validate 'extra' first, before any argument construction.
    # Early validation ensures clear error messages with caller stack context.
    if extra is not None:
        if not isinstance(extra, (list, tuple)):
            msg = f"'extra' must be a list or tuple of strings, got {type(extra).__name__}"
            raise TypeError(msg)
        if not all(isinstance(x, str) for x in extra):
            invalid_types = [type(x).__name__ for x in extra if not isinstance(x, str)]
            msg = f"'extra' must contain only strings, found: {invalid_types}"
            raise TypeError(msg)

    args: list[str] = ["claude"]
    if allow_flag:
        args.append("--dangerously-skip-permissions")
    if model:
        args.extend(["--model", model])
    if not enable_search:
        logger.info(
            "Claude CLI does not yet expose a --no-search flag; ignoring enable_search=False"
        )
    # 'extra' was already validated at function entry; just extend if present
    if extra:
        args.extend(extra)
    args.extend(["-p", "-"])
    return args


def claude_exec(
    prompt: str,
    repo_root: Path,
    model: str | None = None,
    enable_search: bool = True,
    yolo: Optional[bool] = None,
    allow_unsafe_execution: Optional[bool] = None,
    dry_run: bool = False,
    extra: Optional[list[str]] = None,
) -> tuple[str, str]:
    """Execute a Claude command. Parameters mirror codex_exec for API compatibility."""
    allow_flag = _resolve_unsafe_flag(allow_unsafe_execution, yolo, "claude_exec")
    if not allow_flag and not dry_run:
        msg = "Claude executor requires allow_unsafe_execution=True to bypass permissions."
        raise PermissionError(msg)
    os.environ.setdefault("CI", "1")
    if allow_flag:
        verify_unsafe_execution_ready()

    args = _build_claude_args(allow_flag, model, enable_search, extra)
    if dry_run:
        # Log command name and arg count only - avoid full arg dump to prevent
        # potential secret/PII leakage via `extra` arguments
        logger.info(
            "Dry run enabled; skipping Claude execution. Command=%s args=%d",
            args[0] if args else "<empty>",
            len(args),
        )
        return "DRY_RUN", ""

    out, stderr, _ = run_cmd(
        args,
        cwd=repo_root,
        check=True,
        stdin=prompt,
        timeout=get_claude_exec_timeout(),
    )

    # Log warning if stdout is empty but stderr has content. This pattern may indicate:
    # - Rate limiting (API returns error in stderr but no output)
    # - Process crashed after partial execution
    # - Configuration issues preventing normal output
    if not out.strip() and stderr.strip():
        # Sanitize stderr to redact sensitive information (API keys, tokens, paths)
        # before logging, consistent with claude_exec_streaming behavior.
        sanitized_stderr = _sanitize_stderr_for_exception(stderr, 500)
        logger.warning(
            "Claude returned empty stdout. Stderr content: %s",
            sanitized_stderr,
        )

    return out, stderr


def _set_nonblocking(fd: int) -> None:
    """Set a file descriptor to non-blocking mode.

    Raises:
        OSError: If fcntl is not available (Windows) or fcntl operations fail.
    """
    if not HAS_FCNTL:
        raise OSError("Non-blocking I/O requires fcntl.")
    try:
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    except (OSError, ValueError) as e:
        logger.error("Failed to set non-blocking mode on fd %d: %s", fd, e)
        raise OSError("Failed to configure non-blocking I/O.") from e


def _process_buffer(
    buffer: str,
    lines: list[str],
    output_handler: Optional[Callable[[str], None]] = None,
) -> str:
    """Process complete lines from buffer, returning remainder.

    This function extracts complete lines (terminated by newlines) from the buffer,
    appends each line to the `lines` list in place and optionally calls
    `output_handler` for each line. The remaining incomplete line (if any) is
    returned for subsequent buffering.

    Args:
        buffer: Input buffer potentially containing newline-terminated lines.
        lines: List to append complete lines to (in/out parameter, modified in place).
        output_handler: Optional callback invoked for each complete line.

    Returns:
        Remaining buffer content after the last newline (may be empty string).
    """
    while "\n" in buffer:
        line, buffer = buffer.split("\n", 1)
        lines.append(line)
        if output_handler:
            output_handler(line)
    return buffer


def _drain_fds_best_effort(
    fds: list[Any],
    proc_stdout: IO[str] | None,
    proc_stderr: IO[str] | None,
    stdout_buffer: str,
    stderr_buffer: str,
) -> tuple[str, str]:
    """Best-effort drain of file descriptors into buffers.

    Used during error recovery to capture any remaining data before breaking
    out of the streaming loop. Errors are logged at warning level since this
    is a best-effort operation during abnormal termination.

    Args:
        fds: List of file descriptors to drain.
        proc_stdout: The process stdout file object for comparison.
        proc_stderr: The process stderr file object for comparison.
        stdout_buffer: Current stdout buffer contents.
        stderr_buffer: Current stderr buffer contents.

    Returns:
        Tuple of (updated_stdout_buffer, updated_stderr_buffer).
    """
    for fd in fds:
        try:
            if fd.closed:
                continue
            remaining = fd.read()
            if remaining:
                if fd == proc_stdout:
                    stdout_buffer += remaining
                elif fd == proc_stderr:
                    stderr_buffer += remaining
        except (OSError, IOError, ValueError) as drain_exc:
            # Expected exceptions during best-effort drain operations:
            # - OSError/IOError: fd already closed, pipe broken, or other I/O failures
            # - ValueError: fd invalid or in an unusable state (e.g., closed fd passed
            #   from select() error recovery, or fd was closed between select() and read())
            # Any other exceptions (e.g., TypeError, AttributeError) would indicate
            # a programming error and should propagate up.
            #
            # Always log at WARNING since we attempted to read from this fd and failed,
            # meaning we may have lost data that was available in the pipe.
            logger.warning(
                "Best-effort drain failed for fd - some output may be lost: %s (%s)",
                drain_exc,
                type(drain_exc).__name__,
            )
    return stdout_buffer, stderr_buffer


def _cleanup_failed_process(
    proc: subprocess.Popen[str],
    wait_timeout: float = 5.0,
    capture_stderr: bool = True,
) -> str:
    """Clean up a failed subprocess and optionally capture stderr.

    This function handles the common cleanup pattern for subprocesses that have
    failed or need to be terminated. It:
    1. Closes stdin (if open)
    2. Waits for process termination with a timeout
    3. Kills the process if wait times out
    4. Optionally captures any stderr output
    5. Closes all file descriptors

    Args:
        proc: The subprocess.Popen instance to clean up.
        wait_timeout: Maximum seconds to wait for natural termination before kill().
        capture_stderr: If True, attempt to read any remaining stderr data.

    Returns:
        Captured stderr content (empty string if capture_stderr=False or on failure).
    """
    captured_stderr = ""

    try:
        # Close stdin to release the file descriptor
        if proc.stdin and not proc.stdin.closed:
            try:
                proc.stdin.close()
            except OSError:
                pass  # Stdin may already be closed or in an error state

        # Wait for process with bounded timeout, kill if necessary
        try:
            proc.wait(timeout=wait_timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                logger.warning(
                    "Process did not terminate after kill() and 5s wait; "
                    "possible zombie process (pid=%s)",
                    proc.pid,
                )

        # Optionally capture stderr
        if capture_stderr and proc.stderr:
            try:
                # Brief timeout (0.5s) - process has exited so any buffered data
                # should be immediately available.
                readable, _, _ = select.select([proc.stderr], [], [], 0.5)
                if readable:
                    captured_stderr = proc.stderr.read() or ""
                else:
                    logger.debug(
                        "select() timed out reading stderr during cleanup - "
                        "no data available or fd in unexpected state"
                    )
            except (OSError, IOError, ValueError) as stderr_exc:
                logger.warning(
                    "Failed to capture stderr during cleanup: %s (%s)",
                    stderr_exc,
                    type(stderr_exc).__name__,
                )

    finally:
        # Defensive cleanup - ensure all fds are closed
        for fd in (proc.stdin, proc.stdout, proc.stderr):
            if fd and not fd.closed:
                try:
                    fd.close()
                except OSError:
                    pass  # Best effort - fd may already be in error state

    return captured_stderr


def claude_exec_streaming(
    prompt: str,
    repo_root: Path,
    model: str | None = None,
    enable_search: bool = True,
    yolo: Optional[bool] = None,
    allow_unsafe_execution: Optional[bool] = None,
    dry_run: bool = False,
    extra: Optional[list[str]] = None,
    on_output: Optional[Callable[[str], None]] = None,
    timeout: Optional[int] = None,
) -> tuple[str, str]:
    """Execute Claude with real-time output streaming.

    Like claude_exec but streams stdout in real-time for visibility.
    Note: This function uses fcntl for non-blocking I/O and is Unix-only.

    Example:
        >>> def my_handler(line: str) -> None:
        ...     print(f"[claude] {line}", flush=True)
        ...
        >>> stdout, stderr = claude_exec_streaming(
        ...     prompt="Explain this code",
        ...     repo_root=Path("/path/to/repo"),
        ...     allow_unsafe_execution=True,
        ...     on_output=my_handler,  # Called for each line as it arrives
        ...     timeout=300,  # 5 minute timeout
        ... )

    Args:
        prompt: The prompt to send to Claude
        repo_root: Repository root directory
        model: Optional model name override
        enable_search: Enable search (not currently used by Claude CLI)
        yolo: Deprecated alias for allow_unsafe_execution
        allow_unsafe_execution: Must be True for actual (non-dry-run) execution
        dry_run: If True, skip actual execution and return ("DRY_RUN", "")
        extra: Additional CLI arguments passed directly to claude
        on_output: Callback for each stdout line (stderr is not streamed).
            SECURITY WARNING: The line passed to this callback is raw, unsanitized
            model output that may contain sensitive data (API keys, tokens, PII,
            secrets). Callers that log or persist callback output MUST implement
            their own sanitization (e.g., using _sanitize_stderr_for_exception
            or equivalent) to prevent sensitive data exposure in logs/files.
        timeout: Optional timeout in seconds. If None, falls back to the
            AUTO_PRD_CLAUDE_TIMEOUT_SECONDS environment variable. If that is
            also unset or explicitly disabled, no timeout is applied.

    Returns:
        Tuple of (stdout, stderr) containing all accumulated output.
        Note: Unlike claude_exec which preserves exact output formatting,
        this function normalizes line endings by joining lines with single
        newlines. This means:
        - Trailing newlines from the original output are not preserved
        - Empty lines (consecutive newlines) are preserved as empty strings
          in the lines list and joined back with single newlines, maintaining
          the visual structure of blank lines in the output

    Raises:
        PermissionError: If allow_unsafe_execution is False and dry_run is False
        FileNotFoundError: If the claude executable is not found in PATH
        OSError: If running on Windows (fcntl not available)
        subprocess.CalledProcessError: If claude returns a non-zero exit code
        subprocess.TimeoutExpired: If execution exceeds the timeout
        SystemExit: If validate_stdin rejects the prompt (e.g., size limits,
            control character filtering) or if safety utilities abort execution
        RuntimeError: If select() fails unrecoverably during streaming
    """
    # Platform check - fcntl is Unix-only
    # Note: We check HAS_FCNTL (boolean flag), not sys.platform == "win32" separately.
    # On Windows, fcntl import fails and HAS_FCNTL is False due to the import guard
    # at module top, so checking HAS_FCNTL covers both "fcntl unavailable" and "Windows".
    if not HAS_FCNTL:
        msg = (
            "claude_exec_streaming requires Unix fcntl module for non-blocking I/O. "
            "Use claude_exec on Windows systems."
        )
        raise OSError(msg)
    allow_flag = _resolve_unsafe_flag(
        allow_unsafe_execution, yolo, "claude_exec_streaming"
    )
    if not allow_flag and not dry_run:
        msg = "Claude executor requires allow_unsafe_execution=True to bypass permissions."
        raise PermissionError(msg)
    os.environ.setdefault("CI", "1")
    if allow_flag:
        verify_unsafe_execution_ready()

    args = _build_claude_args(allow_flag, model, enable_search, extra)
    if dry_run:
        # Log command name and arg count only - avoid full arg dump to prevent
        # potential secret/PII leakage via `extra` arguments
        logger.info(
            "Dry run enabled; skipping Claude execution. Command=%s args=%d",
            args[0] if args else "<empty>",
            len(args),
        )
        return "DRY_RUN", ""

    # Validate stdin before spawning subprocess - applies same safety checks as run_cmd
    # (size limits, control character filtering) to prevent hangs or unexpected failures.
    validate_stdin(prompt)

    # Resolve timeout using three-level fallback:
    # 1. Use the explicit timeout parameter if provided (not None)
    # 2. Otherwise, check AUTO_PRD_CLAUDE_TIMEOUT_SECONDS environment variable
    # 3. If both are unset/None, effective_timeout will be None (meaning no timeout)
    # Note: get_claude_exec_timeout() can also return None, so effective_timeout
    # may be None after this line, which is intentional for unlimited execution.
    effective_timeout = timeout if timeout is not None else get_claude_exec_timeout()

    # Use popen_streaming from command.py for policy-compliant subprocess spawning.
    # This centralizes argument sanitization, validation, and environment setup.
    proc, sanitized_args = popen_streaming(args, cwd=repo_root)

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    # Send prompt and close stdin. start_time is set AFTER writing the prompt
    # so the timeout measures actual Claude execution time, not prompt transmission.
    # Fail loudly if stdin is missing - this indicates a subprocess configuration bug.
    if not proc.stdin:
        proc.kill()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            logger.warning(
                "Process did not terminate after kill signal within timeout; "
                "continuing cleanup."
            )
        if proc.stdout:
            proc.stdout.close()
        if proc.stderr:
            proc.stderr.close()
        msg = "Claude streaming requires stdin=PIPE (got no stdin)"
        raise RuntimeError(msg)
    try:
        proc.stdin.write(prompt)
        proc.stdin.close()
    except BrokenPipeError:
        # Process terminated before reading input - this is an error condition.
        # Log detailed diagnostic info for debugging, but keep user message simple.
        logger.error(
            "BrokenPipeError: Claude process terminated before reading input "
            "(prompt_length=%d, command=%s)",
            len(prompt),
            sanitized_args[0],  # Log only executable name, not full args
        )
        # Wrap entire cleanup in try/finally to ensure all fds are closed even if
        # an exception occurs during cleanup (e.g., proc.wait() hangs, select fails).
        captured_stderr = ""
        try:
            # Close stdin to release the file descriptor - even though write failed,
            # the pipe may still be open and needs explicit cleanup.
            try:
                proc.stdin.close()
            except OSError:
                pass  # Stdin may already be closed or in an error state
            # Don't wait forever: stdin can break even if the process is still running.
            # Use a fixed 5s timeout with kill fallback to prevent indefinite hangs.
            # Note: We use a fixed timeout (not derived from effective_timeout) because
            # cleanup timeout serves a different purpose than execution timeout:
            # - Execution timeout: how long to allow the command to run
            # - Cleanup timeout: how long to wait for graceful termination after an error
            # Even with a very short execution timeout (e.g., 1s), we want to give the
            # process time to write error output and clean up resources.
            wait_timeout = 5.0
            try:
                proc.wait(timeout=wait_timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=5.0)
                except subprocess.TimeoutExpired:
                    logger.warning(
                        "Process did not terminate after kill() and 5s wait; "
                        "possible zombie process (pid=%s)",
                        proc.pid,
                    )
            # Try to capture any stderr the process wrote before dying.
            # Use select with a short timeout to avoid hanging if stderr is in an
            # unexpected state (e.g., kernel issues, pipe anomalies).
            if proc.stderr:
                try:
                    # Brief timeout (0.5s) - process has exited so any buffered data
                    # should be immediately available. If select times out, there's
                    # likely no data or the fd is in an unexpected state.
                    readable, _, _ = select.select([proc.stderr], [], [], 0.5)
                    if readable:
                        captured_stderr = proc.stderr.read() or ""
                    else:
                        logger.debug(
                            "select() timed out reading stderr after BrokenPipeError - "
                            "no data available or fd in unexpected state"
                        )
                except (OSError, IOError, ValueError) as stderr_exc:
                    # OSError/IOError: fd already closed, pipe broken, or other I/O failures
                    # ValueError: select() got invalid fd, or read() on closed file
                    logger.warning(
                        "Failed to capture stderr after BrokenPipeError: %s (%s)",
                        stderr_exc,
                        type(stderr_exc).__name__,
                    )
        finally:
            # Defensive cleanup - ensure all fds are closed regardless of what
            # happened above. This prevents resource leaks if any step failed.
            for fd in (proc.stdin, proc.stdout, proc.stderr):
                if fd and not fd.closed:
                    try:
                        fd.close()
                    except OSError:
                        pass  # Best effort - fd may already be in error state
        # User-facing error message - simple and actionable
        error_msg = "Claude process terminated unexpectedly before reading input"
        if captured_stderr:
            # Sanitize stderr to remove sensitive information (API keys, tokens, paths)
            # and truncate to prevent excessively long exception messages.
            sanitized_stderr = _sanitize_stderr_for_exception(
                captured_stderr, STDERR_ERROR_MESSAGE_MAX_CHARS
            )
            error_msg = f"{error_msg}. Stderr: {sanitized_stderr}"
        # Determine appropriate return code - proc.wait() was called above so
        # returncode should be set. If still None, something is very wrong with
        # the subprocess module or OS (e.g., zombie process, kernel bug).
        if proc.returncode is None:
            poll_result = proc.poll()
            logger.error(
                "UNEXPECTED SUBPROCESS STATE: returncode is None after proc.wait(). "
                "This suggests a deeper issue with the subprocess module or OS. "
                "Diagnostics: command=%s, pid=%s, poll()=%r",
                sanitized_args[0],
                getattr(proc, "pid", None),
                poll_result,
            )
            msg = (
                f"UNEXPECTED SUBPROCESS STATE: Process did not terminate after proc.wait(); "
                f"returncode is None (command: {sanitized_args[0]}, pid: {getattr(proc, 'pid', None)}, "
                f"poll(): {poll_result}). This indicates a possible bug in the subprocess module or OS. "
                f"Please report this issue at https://github.com/SimoKiihamaki/autodev/issues with: "
                f"1) This error message, 2) OS name and version, 3) Python version (`python --version`), "
                f"4) Any antivirus/security software running."
            )
            raise RuntimeError(msg) from None
        raise subprocess.CalledProcessError(
            proc.returncode,
            sanitized_args,
            output=b"",
            stderr=error_msg.encode(),
        ) from None

    # Set up non-blocking I/O
    try:
        if proc.stdout:
            _set_nonblocking(proc.stdout.fileno())
        if proc.stderr:
            _set_nonblocking(proc.stderr.fileno())
    except OSError:
        # Clean up process resources before re-raising.
        # Note: proc.stdin was already closed after writing the prompt,
        # but include defensive cleanup for consistency with other error handlers.
        proc.kill()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            logger.warning(
                "Process did not terminate after kill signal within timeout; "
                "continuing cleanup."
            )
        if proc.stdin and not proc.stdin.closed:
            proc.stdin.close()
        if proc.stdout:
            proc.stdout.close()
        if proc.stderr:
            proc.stderr.close()
        raise

    # Start timeout measurement AFTER process setup and prompt transmission.
    # This ensures the timeout measures actual Claude execution time only.
    start_time = time.monotonic()

    stdout_buffer = ""
    stderr_buffer = ""

    # Track I/O errors for surfacing at the end of streaming.
    # NOTE: I/O errors during streaming are logged and reported but do NOT cause
    # the function to raise an exception if the process exit code is 0. This is
    # intentional: the primary success criterion is the process exit code, not
    # complete I/O capture. If I/O errors occur but the process exits successfully,
    # we return the (potentially incomplete) output with a warning rather than
    # failing entirely. Callers who need guaranteed complete output should check
    # for io_errors warnings in the logs after calling.
    io_errors: list[tuple[str, int | None, str]] = []

    # Track fds that have reached EOF to avoid infinite loop.
    # When a process exits, its pipes still exist as file objects (not None),
    # but select() returns them as "readable" with EOF. Without tracking EOF,
    # the loop would spin forever: read empty string -> continue -> select -> repeat.
    eof_fds: set[IO[str]] = set()

    # Stream output in real-time
    while True:
        # Only check for timeout if a timeout is configured (effective_timeout is not None).
        # Checking timeout when None would be semantically meaningless since there's no
        # limit to compare against.
        if effective_timeout is not None:
            elapsed = time.monotonic() - start_time
            if elapsed >= effective_timeout:
                # Include any partial data still in buffers (unterminated lines)
                # to preserve output that arrived before timeout
                all_stdout = stdout_lines.copy()
                if stdout_buffer:
                    all_stdout.append(stdout_buffer)
                all_stderr = stderr_lines.copy()
                if stderr_buffer:
                    all_stderr.append(stderr_buffer)
                stdout_so_far = "\n".join(all_stdout)
                stderr_so_far = "\n".join(all_stderr)
                # Log timeout metadata only - avoid logging actual stdout/stderr content
                # to prevent persisting potentially sensitive model output (secrets, PII)
                # in log files. The partial output is preserved in the exception for
                # immediate inspection but should not be written to persistent logs.
                logger.error(
                    "Claude execution timed out after %.1f seconds (limit: %d). "
                    "Partial output: %d stdout lines (%d chars), %d stderr lines (%d chars)",
                    elapsed,
                    effective_timeout,
                    len(stdout_lines),
                    len(stdout_so_far),
                    len(stderr_lines),
                    len(stderr_so_far),
                )
                # Check if process already exited between timeout check and kill.
                # This handles a subtle race condition: the process may have completed
                # naturally in the time between checking elapsed >= timeout and now.
                if proc.poll() is None:
                    proc.kill()
                    try:
                        proc.wait(timeout=5.0)
                    except subprocess.TimeoutExpired:
                        logger.warning(
                            "Process did not terminate after kill signal within timeout; "
                            "continuing with partial output."
                        )
                    # Defensive cleanup for stdin - already closed after prompt write,
                    # but included for consistency with other error handlers.
                    if proc.stdin and not proc.stdin.closed:
                        proc.stdin.close()
                    if proc.stdout:
                        proc.stdout.close()
                    if proc.stderr:
                        proc.stderr.close()
                    # Use TimeoutExpired constructor parameters (output=, stderr=), which populate
                    # the exception's standard `output` and `stderr` attributes.
                    raise subprocess.TimeoutExpired(
                        sanitized_args,
                        effective_timeout,
                        output=stdout_so_far.encode(),
                        stderr=stderr_so_far.encode(),
                    )
                else:
                    # Process completed naturally just as timeout was reached - return success
                    # rather than raising TimeoutExpired, since the operation did complete.
                    # This prevents confusing callers who would see a timeout error despite
                    # the process having finished successfully.
                    logger.debug(
                        "Process exited naturally (code=%d) just as timeout was reached; "
                        "returning output since process completed successfully",
                        proc.returncode,
                    )
                    # Defensive cleanup for stdin - already closed after prompt write,
                    # but included for consistency with other code paths.
                    if proc.stdin and not proc.stdin.closed:
                        proc.stdin.close()
                    if proc.stdout:
                        proc.stdout.close()
                    if proc.stderr:
                        proc.stderr.close()
                    # If process exited with non-zero code, raise CalledProcessError
                    if proc.returncode != 0:
                        raise subprocess.CalledProcessError(
                            proc.returncode,
                            sanitized_args,
                            output=stdout_so_far.encode(),
                            stderr=stderr_so_far.encode(),
                        )
                    # Success - return the output
                    return stdout_so_far, stderr_so_far

        ret = proc.poll()
        # Exclude fds that have reached EOF - they would cause select to return
        # immediately with nothing to read, spinning the loop forever
        readable_fds = [
            fd
            for fd in (proc.stdout, proc.stderr)
            if fd is not None and fd not in eof_fds
        ]

        # Termination check #1 (before select):
        # Checks `readable_fds` - the list of fds we *would* pass to select(), built
        # by filtering out fds that have already reached EOF in previous iterations.
        # Exit when the process has finished (ret is not None) AND there are no fds
        # left to poll (all have previously reached EOF). This prevents calling
        # select() with an empty fd list (which would be a no-op or error).
        #
        # Relationship to check #2: This check handles the case where ALL fds reached
        # EOF in previous loop iterations. Check #2 handles the case where fds reach
        # EOF during the current iteration (after select() and read() calls).
        if ret is not None and not readable_fds:
            break

        try:
            readable, _, _ = select.select(
                readable_fds, [], [], STREAMING_SELECT_TIMEOUT_SECONDS
            )
        except ValueError as e:
            # ValueError indicates invalid arguments to select() (e.g., negative timeout,
            # invalid fd). This is a programming error, not a signal interrupt, so it
            # cannot be recovered by retry.
            #
            # IMPORTANT: Don't just break and rely on proc.wait() - if the process is
            # still running, proc.wait() could block indefinitely (no timeout). Instead,
            # terminate the process explicitly and raise an error to signal the failure.
            logger.error(
                "select() raised ValueError (invalid arguments): %s - "
                "terminating process and aborting streaming",
                e,
            )
            # Attempt to drain any remaining buffered data before terminating.
            # Return values are intentionally discarded since we're raising immediately.
            _drain_fds_best_effort(
                readable_fds, proc.stdout, proc.stderr, stdout_buffer, stderr_buffer
            )
            proc.kill()
            try:
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                logger.warning(
                    "Process did not terminate after kill signal within timeout; "
                    "continuing cleanup."
                )
            # Defensive cleanup for stdin - already closed after prompt write,
            # but included for consistency with other error handlers.
            if proc.stdin and not proc.stdin.closed:
                proc.stdin.close()
            if proc.stdout:
                proc.stdout.close()
            if proc.stderr:
                proc.stderr.close()
            msg = "select() failed (ValueError); streaming aborted"
            raise RuntimeError(msg) from e
        except OSError as e:
            # EINTR can be retried (interrupted by signal)
            if e.errno == errno.EINTR:
                continue
            # Other select() failures are serious and non-recoverable.
            #
            # IMPORTANT: Don't just break and rely on proc.wait() - if the process is
            # still running, proc.wait() could block indefinitely (no timeout). Instead,
            # terminate the process explicitly and raise an error to signal the failure.
            logger.error(
                "select() failed unexpectedly (errno=%s): %s - "
                "terminating process and aborting streaming",
                e.errno,
                e,
            )
            # Attempt to drain any remaining buffered data before terminating.
            # Return values are intentionally discarded since we're raising immediately.
            _drain_fds_best_effort(
                readable_fds, proc.stdout, proc.stderr, stdout_buffer, stderr_buffer
            )
            proc.kill()
            try:
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                logger.warning(
                    "Process did not terminate after kill signal within timeout; "
                    "continuing cleanup."
                )
            # Defensive cleanup for stdin - already closed after prompt write,
            # but included for consistency with other error handlers.
            if proc.stdin and not proc.stdin.closed:
                proc.stdin.close()
            if proc.stdout:
                proc.stdout.close()
            if proc.stderr:
                proc.stderr.close()
            msg = "select() failed (OSError); streaming aborted"
            raise RuntimeError(msg) from e

        for fd in readable:
            try:
                chunk = fd.read(STREAMING_READ_CHUNK_SIZE)
                if not chunk:
                    # EOF reached - mark this fd so we don't select on it again.
                    # This prevents the infinite loop where select returns immediately
                    # with "readable" fds that only have EOF available.
                    #
                    # Note on race condition and defensive programming:
                    # Under normal conditions, once read() returns empty (EOF), no more
                    # data can arrive because the pipe's write end is closed. However,
                    # we defensively add the fd to eof_fds even in abnormal cases
                    # (process crash, kernel issues) where select() might spuriously
                    # report the fd as readable after EOF. This defensive exclusion
                    # prevents infinite loops regardless of the underlying cause.
                    eof_fds.add(fd)
                    continue
                if fd == proc.stdout:
                    stdout_buffer += chunk
                    stdout_buffer = _process_buffer(
                        stdout_buffer, stdout_lines, on_output
                    )
                elif fd == proc.stderr:
                    stderr_buffer += chunk
                    stderr_buffer = _process_buffer(stderr_buffer, stderr_lines)
            except (IOError, OSError) as e:
                # EAGAIN/EWOULDBLOCK are expected with non-blocking I/O
                if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                    continue
                # Other errors are unexpected - log and track for later surfacing
                fd_name = "stdout" if fd == proc.stdout else "stderr"
                logger.error(
                    "I/O error reading from Claude process (fd=%s, errno=%s): %s - "
                    "OUTPUT MAY BE INCOMPLETE",
                    fd_name,
                    e.errno,
                    e,
                )
                io_errors.append((fd_name, e.errno, str(e)))
                # Notify user immediately of potential data loss.
                # Write to stderr explicitly since stdout may be the problematic fd,
                # and we want this warning to be visible regardless.
                print(
                    f"  [WARNING] I/O error on {fd_name} - some output may be missing. "
                    "Results may be incomplete; consider retrying if critical.",
                    file=sys.stderr,
                    flush=True,
                )
                # Mark fd as EOF to exclude it from subsequent select() calls.
                # This prevents repeated errors from the same fd - once a non-transient
                # I/O error occurs, continuing to read from that fd is unlikely to succeed.
                # The fd is excluded from readable_fds on the next loop iteration via the
                # list comprehension that filters out eof_fds.
                eof_fds.add(fd)
            except ValueError as e:
                # TextIOWrapper.read() raises ValueError when the fd is closed between
                # select() returning and read() being called (race condition on abrupt
                # process termination). The fd.closed attribute is the reliable indicator.
                #
                # We check hasattr() first to ensure the fd has a 'closed' attribute
                # (defensive: all file objects should have it, but edge cases like
                # custom file-like objects without 'closed' should re-raise rather
                # than be silently treated as I/O errors).
                if not hasattr(fd, "closed"):
                    # Unexpected object type - re-raise to surface the bug.
                    raise
                fd_is_closed = fd.closed
                if not fd_is_closed:
                    # Unexpected ValueError - fd is open so this isn't a closure issue.
                    # Re-raise to surface the bug rather than silently masking it.
                    raise
                fd_name = "stdout" if fd == proc.stdout else "stderr"
                logger.error(
                    "ValueError reading from Claude process (fd=%s, closed=%s): %s - "
                    "fd closed during read, OUTPUT MAY BE INCOMPLETE",
                    fd_name,
                    fd_is_closed,
                    e,
                )
                io_errors.append((fd_name, getattr(e, "errno", None), str(e)))
                print(
                    f"  [WARNING] Read error on {fd_name} (fd closed) - "
                    "some output may be missing",
                    file=sys.stderr,
                    flush=True,
                )
                eof_fds.add(fd)

        # Termination check #2 (after processing readable fds):
        # Checks `readable` - the list of fds that select() reported as having data.
        # Exit when the process has finished AND select() returned no readable fds.
        #
        # Why this differs from check #1:
        # - Check #1 uses `readable_fds` (fds we passed TO select, excluding prior EOFs)
        # - Check #2 uses `readable` (fds select RETURNED as having data available)
        #
        # This check catches the case where readable_fds was non-empty entering select(),
        # but during this iteration's read() calls, all remaining fds reached EOF
        # (returning empty strings) and were added to eof_fds. When that happens,
        # select() returns empty because no fds have data, and we can exit cleanly.
        if ret is not None and not readable:
            break

    # Flush remaining buffers.
    # If process output didn't end with a newline, treat remaining buffer as the
    # complete final line since the process has exited and no more data will arrive.
    if stdout_buffer:
        stdout_lines.append(stdout_buffer)
        if on_output:
            on_output(stdout_buffer)
    if stderr_buffer:
        stderr_lines.append(stderr_buffer)

    # Note: proc.poll() already confirmed exit (returncode is set). This wait() call
    # is kept for defensive completeness to ensure subprocess resources are released,
    # though it will return immediately since the process has already terminated.
    proc.wait()

    # Explicitly close file descriptors
    if proc.stdout:
        proc.stdout.close()
    if proc.stderr:
        proc.stderr.close()

    stdout_text = "\n".join(stdout_lines)
    stderr_text = "\n".join(stderr_lines)

    # Surface any I/O or select errors that occurred during streaming
    if io_errors:
        # Format errors with fd_name context for easier debugging
        formatted_errors = [
            f"{fd_name} (errno={errno}): {err}" for fd_name, errno, err in io_errors
        ]
        logger.error(
            "Claude execution completed with %d I/O errors - output may be incomplete:\n%s",
            len(io_errors),
            "\n".join(formatted_errors),
        )
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(
            proc.returncode,
            sanitized_args,
            output=stdout_text.encode(),
            stderr=stderr_text.encode(),
        )

    if not stdout_text.strip() and stderr_text.strip():
        # Sanitize stderr to redact sensitive information (API keys, tokens, paths)
        # before logging, same as non-streaming claude_exec.
        sanitized_stderr = _sanitize_stderr_for_exception(stderr_text, 500)
        logger.warning(
            "Claude returned empty stdout. Stderr content: %s",
            sanitized_stderr,
        )

    return stdout_text, stderr_text
