"""Integrations with external agents (Codex, CodeRabbit, Claude)."""

from __future__ import annotations

import errno
import json
import os
import random
import re
import select
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from types import MappingProxyType
from typing import IO, Any

from .command import (
    popen_streaming,
    run_cmd,
    validate_stdin,
    verify_unsafe_execution_ready,
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

# Timeout for process cleanup operations (waiting after kill(), draining stderr).
# Used throughout the streaming implementation to prevent indefinite hangs during
# error recovery. This is distinct from execution timeout (how long to let the
# command run) - cleanup timeout bounds how long we wait for graceful termination.
PROCESS_CLEANUP_TIMEOUT_SECONDS = 5.0

# Shorter timeout for waiting after kill() signal. Since kill() is forceful,
# the process should terminate quickly. A shorter timeout avoids unnecessarily
# long waits for zombie processes while still allowing reasonable cleanup time.
PROCESS_KILL_WAIT_TIMEOUT_SECONDS = 2.0

# Maximum characters of stderr to include in error messages to prevent
# excessively long exception messages. Stderr can contain binary data or
# very long output from crashed processes.
STDERR_ERROR_MESSAGE_MAX_CHARS = 1000

# Patterns for sanitizing sensitive information from stderr before including
# in exception messages. These patterns catch common credential/token formats.
#
# PERFORMANCE NOTE: Patterns are compiled ONCE at module import time (via re.compile()),
# not on each sanitization call. The list iteration during sanitization is O(n) where
# n is the number of patterns (~10), which is negligible compared to the actual regex
# matching.
#
# OPTIMIZATION ALTERNATIVES CONSIDERED AND REJECTED:
# 1. Combining API key patterns into single regex with alternation (sk-|ghp_|gho_|...):
#    - Would reduce pattern count but complicate replacement logic (each needs different text)
#    - Makes adding/removing patterns error-prone
#    - Minimal performance gain since this runs only on error paths, not hot paths
# 2. Trie-based prefix matching for known prefixes (sk-, ghp_, etc.):
#    - Overkill for ~10 patterns; adds complexity without proportional benefit
# 3. Early exit if stderr is short:
#    - Not implemented; we sanitize first, then truncate, to avoid leaking
#      secrets that may appear late in stderr.
#
# Current design prioritizes maintainability: each pattern is independent and self-documenting.
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
    # Two separate patterns to preserve the original separator style for debugging clarity:
    # 1. Backslash pattern: C:\Users\username\ -> <DRIVE>:\Users\<USER>\
    # 2. Forward slash pattern: D:/Users/alice/ -> <DRIVE>:/Users/<USER>/
    #
    # Preserving original separator style improves debugging because:
    # - Users can match sanitized paths to their original error messages
    # - Cross-platform code (pathlib) commonly uses forward slashes on Windows
    # - The sanitized output format matches what the user actually saw
    #
    # NOTE: These use literal replacements (not capture group backreferences like \1)
    # because the entire match is replaced with a fixed pattern. The patterns above
    # (Bearer, Basic, key=value) use backreferences to preserve the prefix/key name
    # while redacting only the sensitive value. For Windows paths, we redact everything
    # (drive letter and username) with fixed placeholders, so no backreferences needed.
    (
        re.compile(r"[A-Za-z]:\\+Users\\[^\\]+\\?", re.IGNORECASE),
        r"<DRIVE>:\\Users\\<USER>\\",
    ),
    (
        re.compile(r"[A-Za-z]:/+Users/[^/]+/?", re.IGNORECASE),
        r"<DRIVE>:/Users/<USER>/",
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
        del _chunk_size_val  # Clean up immediately after use
    except ValueError:
        logger.warning(
            "Invalid AUTO_PRD_STREAMING_CHUNK_SIZE value %r; using default 4096",
            _raw_chunk_size,
        )
        STREAMING_READ_CHUNK_SIZE = 4096
del _raw_chunk_size  # Clean up raw string

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
        del _timeout_val  # Clean up immediately after use
    except ValueError:
        logger.warning(
            "Invalid AUTO_PRD_STREAMING_POLL_TIMEOUT value %r; using default 0.1",
            _raw_poll_timeout,
        )
        STREAMING_SELECT_TIMEOUT_SECONDS = 0.1
del _raw_poll_timeout  # Clean up raw string


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


# Default timeout for Claude execution: 60 minutes (3600 seconds).
# This prevents infinite hangs while allowing long-running operations.
# Can be overridden via AUTO_PRD_CLAUDE_TIMEOUT_SECONDS environment variable.
DEFAULT_CLAUDE_TIMEOUT_SECONDS = 3600


def get_claude_exec_timeout() -> int | None:
    """Get the Claude execution timeout from environment variables.

    Returns:
        The timeout in seconds from AUTO_PRD_CLAUDE_TIMEOUT_SECONDS, or:
        - DEFAULT_CLAUDE_TIMEOUT_SECONDS (3600 = 60 minutes) if env var is not set
        - None if the value is explicitly "none", "no", "off", "disable", or "disabled"
        - None if the value is <= 0 (treated as "no timeout")

    Note:
        The default 60-minute timeout prevents infinite hangs during review loops
        while allowing ample time for complex operations. To disable the timeout
        entirely, set AUTO_PRD_CLAUDE_TIMEOUT_SECONDS=off in your environment.
    """
    return _timeout_from_env(
        "AUTO_PRD_CLAUDE_TIMEOUT_SECONDS", DEFAULT_CLAUDE_TIMEOUT_SECONDS
    )


@dataclass(frozen=True)
class ClaudeHeadlessResponse:
    """Structured response from Claude headless JSON output.

    This dataclass represents the parsed response from Claude when using
    --output-format json. It provides structured access to execution metadata
    and results, enabling better observability and error handling.

    The dataclass is frozen (immutable) to prevent accidental modification
    after parsing. The raw_json field returns an immutable view.

    Attributes:
        result: The text output from Claude's execution.
        session_id: Unique identifier for the Claude session.
        is_error: True if the execution encountered an error.
        total_cost_usd: Total API cost in USD for this execution.
        duration_ms: Execution duration in milliseconds.
        duration_api_ms: API call duration in milliseconds (network + inference).
        num_turns: Number of conversational turns in the session.
        raw_json: Immutable view of the complete raw JSON response.
    """

    result: str
    session_id: str
    is_error: bool
    total_cost_usd: float
    duration_ms: int
    duration_api_ms: int
    num_turns: int
    raw_json: Mapping[str, Any]

    def __post_init__(self) -> None:
        """Validate invariants after construction.

        Raises:
            ValueError: If duration values are negative or cost is negative.
        """
        if self.duration_ms < 0:
            msg = f"duration_ms must be non-negative, got {self.duration_ms}"
            raise ValueError(msg)
        if self.duration_api_ms < 0:
            msg = f"duration_api_ms must be non-negative, got {self.duration_api_ms}"
            raise ValueError(msg)
        if self.total_cost_usd < 0:
            msg = f"total_cost_usd must be non-negative, got {self.total_cost_usd}"
            raise ValueError(msg)
        if self.num_turns < 0:
            msg = f"num_turns must be non-negative, got {self.num_turns}"
            raise ValueError(msg)

    @classmethod
    def from_json(cls, json_str: str) -> ClaudeHeadlessResponse:
        """Parse a JSON string from Claude --output-format json.

        Args:
            json_str: Raw JSON string from Claude stdout.

        Returns:
            Parsed ClaudeHeadlessResponse instance.

        Raises:
            ValueError: If parsing fails for any reason:
                - Input is not valid JSON (json.JSONDecodeError wrapped as ValueError)
                - Parsed JSON is not an object/dict (e.g., array, string, number)
                - Required fields ("result", "session_id") are missing as keys
                Note: Required fields must exist as keys but may have null values,
                which are coerced to empty strings with debug logging.
        """
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            msg = f"Failed to parse Claude JSON response: {e}"
            raise ValueError(msg) from e

        # Validate that parsed JSON is a dict (object), not array/string/number.
        # This prevents AttributeError when calling data.get() below.
        if not isinstance(data, dict):
            msg = f"Claude JSON response must be an object, got {type(data).__name__}"
            raise ValueError(msg)

        # Claude JSON output structure (from documentation):
        # {
        #   "result": "...",
        #   "session_id": "...",
        #   "is_error": false,
        #   "total_cost_usd": 0.05,
        #   "duration_ms": 1234,
        #   "duration_api_ms": 1100,
        #   "num_turns": 3,
        #   ...
        # }
        required_fields = ["result", "session_id"]
        missing = [f for f in required_fields if f not in data]
        if missing:
            msg = f"Claude JSON response missing required fields: {missing}"
            raise ValueError(msg)

        # Extract values with explicit None checks and debug logging for observability.
        # Explicit None checks and type validation handle null values from JSON (e.g., "cost": null)
        # to prevent TypeError in float()/int() conversion and improve robustness.
        result_raw = data.get("result")
        session_id_raw = data.get("session_id")

        # Log when required fields contain None (indicates potential API issue)
        if result_raw is None:
            logger.debug("Claude response 'result' field is None; using empty string")
        if session_id_raw is None:
            logger.debug(
                "Claude response 'session_id' field is None; session tracking unavailable"
            )

        # Extract numeric fields with explicit type checking and logging.
        # Log at WARNING when null/missing since this indicates incomplete API response.
        cost_raw = data.get("total_cost_usd")
        if cost_raw is None:
            logger.warning(
                "Claude response 'total_cost_usd' is None; cost tracking unavailable"
            )
            total_cost_usd = 0.0
        elif not isinstance(cost_raw, int | float):
            logger.warning(
                "Claude response 'total_cost_usd' has unexpected type %s; attempting conversion",
                type(cost_raw).__name__,
            )
            total_cost_usd = float(cost_raw)
        else:
            total_cost_usd = float(cost_raw)

        duration_ms_raw = data.get("duration_ms")
        if duration_ms_raw is None:
            logger.warning(
                "Claude response 'duration_ms' is None; duration tracking unavailable"
            )
            duration_ms = 0
        elif not isinstance(duration_ms_raw, int | float):
            logger.warning(
                "Claude response 'duration_ms' has unexpected type %s; attempting conversion",
                type(duration_ms_raw).__name__,
            )
            duration_ms = int(duration_ms_raw)
        else:
            duration_ms = int(duration_ms_raw)

        duration_api_ms_raw = data.get("duration_api_ms")
        if duration_api_ms_raw is None:
            logger.debug("Claude response 'duration_api_ms' is None; using 0")
            duration_api_ms = 0
        elif not isinstance(duration_api_ms_raw, int | float):
            logger.warning(
                "Claude response 'duration_api_ms' has unexpected type %s; attempting conversion",
                type(duration_api_ms_raw).__name__,
            )
            duration_api_ms = int(duration_api_ms_raw)
        else:
            duration_api_ms = int(duration_api_ms_raw)

        num_turns_raw = data.get("num_turns")
        if num_turns_raw is None:
            logger.debug("Claude response 'num_turns' is None; using 0")
            num_turns = 0
        elif not isinstance(num_turns_raw, int | float):
            logger.warning(
                "Claude response 'num_turns' has unexpected type %s; attempting conversion",
                type(num_turns_raw).__name__,
            )
            num_turns = int(num_turns_raw)
        else:
            num_turns = int(num_turns_raw)

        # Wrap raw_json in MappingProxyType to prevent mutation of internal state.
        return cls(
            result=result_raw if isinstance(result_raw, str) else "",
            session_id=session_id_raw if isinstance(session_id_raw, str) else "",
            is_error=bool(data.get("is_error")),
            total_cost_usd=total_cost_usd,
            duration_ms=duration_ms,
            duration_api_ms=duration_api_ms,
            num_turns=num_turns,
            raw_json=MappingProxyType(data),
        )


def parse_claude_json_response(
    stdout: str,
    *,
    strict: bool = False,
) -> ClaudeHeadlessResponse | None:
    """Attempt to parse Claude stdout as JSON response.

    This function provides two modes of operation:

    **Lenient mode (strict=False, default):**
    Returns None if the output is not valid JSON rather than raising an exception.
    This allows callers to gracefully fall back to treating stdout as plain text.
    A warning is logged with a content preview for debugging.

    **Strict mode (strict=True):**
    Raises ValueError if parsing fails. Use this when output_format="json" was
    explicitly requested and you need to ensure the response was properly formatted.
    Strict mode is appropriate when the caller has no fallback behavior and needs
    to surface parsing failures to the user.

    **Usage guidance:**
    When calling Claude with output_format="json", prefer strict=True to surface
    parsing failures. Only use lenient mode (strict=False) when you have a robust
    fallback for plain text output and can accept losing the structured metadata
    (cost, duration, session_id) on parse failure.

    Args:
        stdout: Raw stdout from Claude execution.
        strict: If True, raise ValueError on parse failure instead of returning None.
            Use strict=True when output_format="json" was explicitly requested
            and parsing failure indicates a real problem (timeout, truncation, etc.).

    Returns:
        ClaudeHeadlessResponse if stdout is valid JSON, None if not (and strict=False).

    Raises:
        ValueError: If strict=True and parsing fails (empty input, invalid JSON,
            or missing required fields).
    """
    if not stdout.strip():
        if strict:
            msg = "Claude stdout is empty; expected JSON response"
            raise ValueError(msg)
        logger.debug("Claude stdout is empty; cannot parse as JSON")
        return None

    try:
        return ClaudeHeadlessResponse.from_json(stdout)
    except ValueError as e:
        # Log at WARNING since JSON parsing failure when --output-format json
        # was requested indicates an unexpected condition (timeout, truncation, etc.)
        # Sanitize the preview to redact potential secrets/PII before logging or
        # including in exception messages. Model output can contain tokens,
        # credentials, PR URLs with embedded auth, etc.
        preview_raw = stdout[:200] + "..." if len(stdout) > 200 else stdout
        preview = _sanitize_stderr_for_exception(preview_raw, 200)
        if strict:
            msg = (
                f"Failed to parse Claude JSON response: {e}. Output preview: {preview}"
            )
            raise ValueError(msg) from e
        logger.warning(
            "Failed to parse Claude output as JSON: %s. Output preview: %s",
            e,
            preview,
        )
        return None


# Use a cryptographically secure RNG for backoff jitter to avoid predictable retry cadences.
_rate_limit_rng = random.SystemRandom()


def codex_exec(
    prompt: str,
    repo_root: Path,
    model: str = "gpt-5-codex",
    enable_search: bool = True,
    yolo: bool | None = None,
    allow_unsafe_execution: bool | None = None,
    dry_run: bool = False,
    extra: list[str] | None = None,
) -> tuple[str, str]:
    os.environ.setdefault("CI", "1")
    allow_flag = allow_unsafe_execution
    if yolo is not None:
        logger.warning(
            "codex_exec: 'yolo' is deprecated; use allow_unsafe_execution instead"
        )
        allow_flag = yolo if allow_flag is None else allow_flag or yolo
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


def parse_rate_limit_sleep(message: str) -> int | None:
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
    allow_unsafe_execution: bool | None,
    yolo: bool | None,
    caller: str,
) -> bool:
    """Resolve the allow_unsafe_execution flag, handling deprecated yolo parameter."""
    allow_flag = allow_unsafe_execution
    if yolo is not None:
        logger.warning("%s: 'yolo' is deprecated; use allow_unsafe_execution", caller)
        allow_flag = yolo if allow_flag is None else allow_flag or yolo
    return bool(allow_flag)


def _safe_typename(obj: object) -> str:
    """Get the type name of an object safely, handling edge cases.

    Returns the type name for error messages. Handles edge cases where
    type(x).__name__ might fail (e.g., proxy objects, broken __class__).

    Args:
        obj: The object to get the type name for.

    Returns:
        A string representing the type name, or a fallback string on failure.
    """
    try:
        return type(obj).__name__
    except (TypeError, AttributeError) as e:
        # Narrow exception types to avoid catching unrelated system errors
        logger.debug("Failed to get type name via __name__: %s", e)
        try:
            return str(type(obj))
        except (TypeError, AttributeError):
            return "<unknown type>"


def _build_claude_args(
    allow_flag: bool,
    model: str | None,
    enable_search: bool,
    extra: list[str] | tuple[str, ...] | None,
    *,
    caller: str = "claude_exec or claude_exec_streaming",
    output_format: str | None = None,
    allowed_tools: list[str] | None = None,
    system_prompt_suffix: str | None = None,
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
        caller: Name of the calling function for clearer error messages.
            Defaults to "claude_exec or claude_exec_streaming" for generic context.
        output_format: Optional output format for structured responses.
            Valid values: "json", "stream-json". When set, Claude returns
            structured JSON output with metadata (session_id, cost, duration).
        allowed_tools: Optional list of tools to allow. Restricts which tools
            Claude can use during execution. Use HEADLESS_TOOL_ALLOWLISTS from
            constants.py for phase-specific restrictions.
        system_prompt_suffix: Optional text to append to system prompt via
            --append-system-prompt. Used for injecting context like compacted
            history from previous iterations.

    Returns:
        List of CLI arguments for Claude execution.

    Raises:
        TypeError: If extra is provided but is not a list/tuple of strings.
            This is raised immediately upon entry, before any other processing,
            to provide clear error messages with full caller context.
        ValueError: If output_format is not a valid format.
    """
    # Validate 'extra' first, before any argument construction.
    # Early validation ensures clear error messages with caller stack context.
    if extra is not None:
        if not isinstance(extra, list | tuple):
            msg = f"{caller}: 'extra' must be a list or tuple of strings, got {_safe_typename(extra)}"
            raise TypeError(msg)
        if not all(isinstance(x, str) for x in extra):
            invalid_types = [_safe_typename(x) for x in extra if not isinstance(x, str)]
            msg = f"{caller}: 'extra' must contain only strings, found: {invalid_types}"
            raise TypeError(msg)

    # Validate output_format
    valid_output_formats = {"json", "stream-json"}
    if output_format is not None and output_format not in valid_output_formats:
        msg = f"{caller}: 'output_format' must be one of {valid_output_formats}, got {output_format!r}"
        raise ValueError(msg)

    # Validate 'allowed_tools' - must be a list or tuple of strings if provided
    if allowed_tools is not None:
        if not isinstance(allowed_tools, list | tuple):
            msg = f"{caller}: 'allowed_tools' must be a list or tuple of strings, got {_safe_typename(allowed_tools)}"
            raise TypeError(msg)
        if not all(isinstance(x, str) for x in allowed_tools):
            invalid_types = [
                _safe_typename(x) for x in allowed_tools if not isinstance(x, str)
            ]
            msg = f"{caller}: 'allowed_tools' must contain only strings, found: {invalid_types}"
            raise TypeError(msg)

    args: list[str] = ["claude"]
    if allow_flag:
        args.append("--dangerously-skip-permissions")
    if model:
        args.extend(["--model", model])

    # Add structured output format for JSON responses
    if output_format:
        args.extend(["--output-format", output_format])

    # Add tool restrictions for security
    if allowed_tools:
        # Each tool requires a separate --allowedTools argument per CLI docs
        for tool in allowed_tools:
            args.extend(["--allowedTools", tool])

    # Add system prompt suffix for context injection
    if system_prompt_suffix:
        args.extend(["--append-system-prompt", system_prompt_suffix])

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
    yolo: bool | None = None,
    allow_unsafe_execution: bool | None = None,
    dry_run: bool = False,
    extra: list[str] | None = None,
    *,
    output_format: str | None = None,
    allowed_tools: list[str] | None = None,
    system_prompt_suffix: str | None = None,
) -> tuple[str, str]:
    """Execute a Claude command.

    Args:
        prompt: The prompt to send to Claude.
        repo_root: Repository root directory.
        model: Optional model name override.
        enable_search: Enable search (not currently used by Claude CLI).
        yolo: Deprecated alias for allow_unsafe_execution.
        allow_unsafe_execution: Must be True for actual (non-dry-run) execution.
        dry_run: If True, skip actual execution and return ("DRY_RUN", "").
        extra: Additional CLI arguments passed directly to claude.
        output_format: Optional output format ("json" or "stream-json") for
            structured responses with metadata (session_id, cost, duration).
        allowed_tools: Optional list of tools to allow. Use HEADLESS_TOOL_ALLOWLISTS
            from constants.py for phase-specific restrictions.
        system_prompt_suffix: Optional text to append to system prompt via
            --append-system-prompt for context injection.

    Returns:
        Tuple of (stdout, stderr) containing all output.

    Raises:
        PermissionError: If allow_unsafe_execution is False and dry_run is False.
        FileNotFoundError: If the claude executable is not found in PATH.
        subprocess.CalledProcessError: If claude returns a non-zero exit code.
    """
    allow_flag = _resolve_unsafe_flag(allow_unsafe_execution, yolo, "claude_exec")
    if not allow_flag and not dry_run:
        msg = "Claude executor requires allow_unsafe_execution=True to bypass permissions."
        raise PermissionError(msg)
    os.environ.setdefault("CI", "1")
    if allow_flag:
        verify_unsafe_execution_ready()

    args = _build_claude_args(
        allow_flag,
        model,
        enable_search,
        extra,
        caller="claude_exec",
        output_format=output_format,
        allowed_tools=allowed_tools,
        system_prompt_suffix=system_prompt_suffix,
    )
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
        msg = "Non-blocking I/O requires fcntl."
        raise OSError(msg)
    try:
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    except (OSError, ValueError) as e:
        logger.error("Failed to set non-blocking mode on fd %d: %s", fd, e)
        msg = "Failed to configure non-blocking I/O."
        raise OSError(msg) from e


def _process_buffer(
    buffer: str,
    lines: list[str],
    output_handler: Callable[[str], None] | None = None,
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


def _should_exit_streaming_loop(process_exited: bool, fds_to_check: list[Any]) -> bool:
    """Determine if the streaming loop should exit.

    The streaming loop should exit when BOTH conditions are met:
    1. The subprocess has exited (process_exited is True)
    2. There are no more file descriptors with potential data (fds_to_check is empty)

    This helper consolidates the termination logic that appears twice in the
    streaming loop:
    - Check #1 (before select): Uses readable_fds (fds to pass to select)
    - Check #2 (after select): Uses readable (fds that select reported as ready)

    Both checks use the same logic but operate on different fd lists because:
    - Check #1 catches when ALL fds reached EOF in previous iterations
    - Check #2 catches when remaining fds reach EOF in the current iteration

    Args:
        process_exited: True if proc.poll() returned a non-None value.
        fds_to_check: List of file descriptors to check. Empty list triggers exit
            when combined with process_exited=True.

    Returns:
        True if the loop should exit, False to continue.
    """
    return process_exited and not fds_to_check


def _drain_fds_best_effort(
    fds: list[Any],
    proc_stdout: IO[str] | None,
    proc_stderr: IO[str] | None,
    stdout_buffer: str,
    stderr_buffer: str,
    max_drain_bytes: int = 65536,
) -> tuple[str, str]:
    """Best-effort drain of file descriptors into buffers.

    Used during error recovery to capture any remaining data before breaking
    out of the streaming loop. Uses select() with zero timeout to avoid blocking
    on processes that may still be alive, and caps total bytes read to prevent
    unbounded memory usage.

    Args:
        fds: List of file descriptors to drain.
        proc_stdout: The process stdout file object for comparison.
        proc_stderr: The process stderr file object for comparison.
        stdout_buffer: Current stdout buffer contents.
        stderr_buffer: Current stderr buffer contents.
        max_drain_bytes: Maximum total bytes to drain per fd (default 64KB).

    Returns:
        Tuple of (updated_stdout_buffer, updated_stderr_buffer).
    """
    for fd in fds:
        try:
            if fd.closed:
                continue
            # Use select with zero timeout to check if data is available
            # without blocking. This is critical because the process may
            # still be alive (e.g., during error recovery after timeout).
            bytes_read = 0
            while bytes_read < max_drain_bytes:
                readable, _, _ = select.select([fd], [], [], 0)
                if not readable:
                    break
                chunk = fd.read(STREAMING_READ_CHUNK_SIZE)
                if not chunk:
                    break
                bytes_read += len(chunk)
                if fd == proc_stdout:
                    stdout_buffer += chunk
                elif fd == proc_stderr:
                    stderr_buffer += chunk
        except (OSError, ValueError) as drain_exc:
            # Expected exceptions during best-effort drain operations:
            # - OSError: fd already closed, pipe broken, or other I/O failures
            # - ValueError: fd invalid or in an unusable state (e.g., closed fd passed
            #   from select() error recovery, or fd was closed between select() and read())
            # Any other exceptions (e.g., TypeError, AttributeError) would indicate
            # a programming error and should propagate up.
            #
            # Log at DEBUG level since this function is explicitly designed for "best-effort"
            # cleanup during error recovery, where some data loss is already expected.
            # WARNING would be misleading since the caller has already acknowledged the
            # possibility of incomplete output by using this function.
            logger.debug(
                "Best-effort drain failed for fd during error recovery "
                "(expected; some output may be lost): %s (%s)",
                drain_exc,
                type(drain_exc).__name__,
            )
    return stdout_buffer, stderr_buffer


def _cleanup_failed_process(
    proc: subprocess.Popen[str],
    wait_timeout: float = PROCESS_CLEANUP_TIMEOUT_SECONDS,
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

        # Wait for process with bounded timeout, kill if necessary.
        # Initial wait uses wait_timeout (caller's configured cleanup timeout).
        # Post-kill wait uses PROCESS_KILL_WAIT_TIMEOUT_SECONDS (shorter) since
        # kill() is forceful and the process should terminate quickly.
        try:
            proc.wait(timeout=wait_timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=PROCESS_KILL_WAIT_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                logger.warning(
                    "Process did not terminate after kill() and %.1fs wait; "
                    "possible zombie process (pid=%s)",
                    PROCESS_KILL_WAIT_TIMEOUT_SECONDS,
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
            except (OSError, ValueError) as stderr_exc:
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
    yolo: bool | None = None,
    allow_unsafe_execution: bool | None = None,
    dry_run: bool = False,
    extra: list[str] | None = None,
    on_output: Callable[[str], None] | None = None,
    timeout: int | None = None,
    *,
    output_format: str | None = None,
    allowed_tools: list[str] | None = None,
    system_prompt_suffix: str | None = None,
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
        output_format: Optional output format ("json" or "stream-json") for
            structured responses with metadata (session_id, cost, duration).
        allowed_tools: Optional list of tools to allow. Use HEADLESS_TOOL_ALLOWLISTS
            from constants.py for phase-specific restrictions.
        system_prompt_suffix: Optional text to append to system prompt via
            --append-system-prompt for context injection.

    Returns:
        Tuple of (stdout, stderr) containing all accumulated output.

        **LINE ENDING NORMALIZATION**: Unlike claude_exec which preserves exact
        output formatting, this function normalizes line endings for streaming
        efficiency. Output is collected line-by-line and rejoined with single
        newlines ("\\n".join(lines)). This means:

        - Trailing newlines from the original output are NOT preserved
        - CRLF line endings (\\r\\n) are converted to LF (\\n)
        - Empty lines (consecutive newlines) ARE preserved as empty strings
          in the lines list, maintaining visual blank line structure

        If exact output preservation is required (e.g., for binary-like text
        or format-sensitive processing), use claude_exec instead.

        **INCOMPLETE OUTPUT WARNING**: If I/O errors occur during streaming but
        the process exits with code 0, this function returns successfully with
        potentially incomplete output. A warning is logged at ERROR level with
        details of the read errors. Callers requiring guaranteed complete output
        should monitor logs for "Claude execution completed with N read errors"
        messages, or use claude_exec (non-streaming) instead which doesn't have
        this limitation. This design choice prioritizes returning partial results
        over failing entirely when some data was successfully captured.

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

    args = _build_claude_args(
        allow_flag,
        model,
        enable_search,
        extra,
        caller="claude_exec_streaming",
        output_format=output_format,
        allowed_tools=allowed_tools,
        system_prompt_suffix=system_prompt_suffix,
    )
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
    #
    # Note: get_claude_exec_timeout() can also return None, so effective_timeout
    # may be None after this block, which is intentional for unlimited execution.
    # When effective_timeout is None, the timeout check at line ~1079 is skipped.
    effective_timeout: int | None = None
    if timeout is not None:
        effective_timeout = timeout
    else:
        env_timeout = get_claude_exec_timeout()
        if env_timeout is not None:
            effective_timeout = env_timeout

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
            proc.wait(timeout=PROCESS_CLEANUP_TIMEOUT_SECONDS)
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
        # Use the shared cleanup helper to handle process termination and stderr capture.
        # This consolidates the deeply nested try/except/finally logic into a single,
        # well-tested function that handles stdin close, wait with timeout, kill if
        # necessary, stderr capture, and fd cleanup.
        captured_stderr = _cleanup_failed_process(
            proc, wait_timeout=PROCESS_CLEANUP_TIMEOUT_SECONDS, capture_stderr=True
        )
        # User-facing error message - simple and actionable
        error_msg = "Claude process terminated unexpectedly before reading input"
        if captured_stderr:
            # Sanitize stderr to remove sensitive information (API keys, tokens, paths)
            # and truncate to prevent excessively long exception messages.
            sanitized_stderr = _sanitize_stderr_for_exception(
                captured_stderr, STDERR_ERROR_MESSAGE_MAX_CHARS
            )
            error_msg = f"{error_msg}. Stderr: {sanitized_stderr}"
        # DEFENSIVE CHECK: After _cleanup_failed_process() calls proc.wait(), returncode
        # should always be set. This check guards against a hypothetical race condition where:
        # 1. proc.wait() completes but the returncode attribute update is somehow delayed
        # 2. The OS/kernel has issues with zombie process handling
        # 3. There's a bug in the subprocess module implementation
        #
        # In practice, this condition should never trigger because wait() is synchronous
        # and sets returncode before returning. If it does trigger, it indicates a serious
        # system-level issue that warrants investigation, not silent recovery.
        if proc.returncode is None:
            # Re-poll to confirm the process state (purely diagnostic, won't change outcome)
            poll_result = proc.poll()
            logger.error(
                "UNEXPECTED SUBPROCESS STATE: returncode is None after _cleanup_failed_process() "
                "called proc.wait(). This should never happen under normal conditions. "
                "Possible causes: OS kernel bug, subprocess module bug, or zombie process leak. "
                "Diagnostics: command=%s, pid=%s, poll()=%r",
                sanitized_args[0],
                getattr(proc, "pid", None),
                poll_result,
            )
            raise RuntimeError("Subprocess did not terminate as expected.") from None
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
            proc.wait(timeout=PROCESS_CLEANUP_TIMEOUT_SECONDS)
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

    # Track read() errors for surfacing at the end of streaming.
    # NOTE: Read errors during streaming are logged and reported but do NOT cause
    # the function to raise an exception if the process exit code is 0. This is
    # intentional: the primary success criterion is the process exit code, not
    # complete I/O capture. If read errors occur but the process exits successfully,
    # we return the (potentially incomplete) output with a warning rather than
    # failing entirely. Callers who need guaranteed complete output should check
    # for read_errors warnings in the logs after calling.
    #
    # Note: This tracks errors from read() operations only, not select() errors
    # (which cause immediate RuntimeError). The name "read_errors" reflects this
    # specific scope.
    read_errors: list[tuple[str, int | None, str]] = []

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
                # Check if process already exited between timeout check and kill.
                # This handles a subtle race condition: the process may have completed
                # naturally in the time between checking elapsed >= timeout and now.
                # We check this BEFORE logging the error to avoid misleading error
                # messages when the process completes naturally just as timeout is reached.
                #
                # IMPORTANT: Capture poll() result once and use it consistently to avoid
                # a race window where the process terminates between poll() and subsequent
                # operations. Using a single poll result ensures we make decisions based
                # on a consistent process state snapshot.
                poll_result = proc.poll()
                if poll_result is None:
                    # Process is still running - log timeout error and terminate it.
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
                    proc.kill()
                    try:
                        proc.wait(timeout=PROCESS_CLEANUP_TIMEOUT_SECONDS)
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
                    # Process exited naturally just as timeout was reached.
                    # poll_result contains the exit code (captured above to avoid race).
                    #
                    # Behavior depends on exit code:
                    # - Exit code 0: Return success (no TimeoutExpired raised)
                    # - Non-zero exit code: Raise CalledProcessError (not TimeoutExpired)
                    #
                    # Rationale: The process DID finish executing before we killed it. Raising
                    # TimeoutExpired would be misleading since the command completed. The exit
                    # code tells us whether the command succeeded (0) or failed (non-zero).
                    # For non-zero exits, CalledProcessError is more accurate than TimeoutExpired
                    # because the process wasn't interrupted - it ran to completion and failed.
                    logger.debug(
                        "Process exited naturally (code=%d) just as timeout was reached; "
                        "using exit code to determine success/failure (not raising TimeoutExpired)",
                        poll_result,
                    )
                    # Close fds BEFORE returning since this is an early return path.
                    # Unlike the normal success path (which closes fds after the main streaming
                    # loop below), early returns must clean up explicitly here to prevent
                    # resource leaks. This is the same pattern used by all other early exit
                    # points (timeout kill, BrokenPipeError, etc.).
                    if proc.stdin and not proc.stdin.closed:
                        proc.stdin.close()
                    if proc.stdout:
                        proc.stdout.close()
                    if proc.stderr:
                        proc.stderr.close()
                    # If process exited with non-zero code, raise CalledProcessError
                    # Note: Use poll_result (captured above) for consistency
                    if poll_result != 0:
                        raise subprocess.CalledProcessError(
                            poll_result,
                            sanitized_args,
                            output=stdout_so_far.encode(),
                            stderr=stderr_so_far.encode(),
                        )
                    # Success - return the output
                    return stdout_so_far, stderr_so_far

        process_exited = proc.poll() is not None
        # Exclude fds that have reached EOF - they would cause select to return
        # immediately with nothing to read, spinning the loop forever
        readable_fds = [
            fd
            for fd in (proc.stdout, proc.stderr)
            if fd is not None and fd not in eof_fds
        ]

        # Termination check #1 (before select): Exit if process finished and all fds
        # reached EOF in previous iterations. See _should_exit_streaming_loop for details.
        if _should_exit_streaming_loop(process_exited, readable_fds):
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
            # Kill and wait for process BEFORE draining fds.
            # If we drain first, fd.read() has no readiness guarantee after select()
            # failed, and could block indefinitely waiting for EOF.
            proc.kill()
            try:
                proc.wait(timeout=PROCESS_CLEANUP_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                logger.warning(
                    "Process did not terminate after kill signal within timeout; "
                    "continuing cleanup."
                )
            # Now attempt to drain any remaining buffered data (best-effort).
            # Return values are intentionally discarded since we're raising immediately.
            _drain_fds_best_effort(
                readable_fds, proc.stdout, proc.stderr, stdout_buffer, stderr_buffer
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
            # Kill and wait for process BEFORE draining fds.
            # If we drain first, fd.read() has no readiness guarantee after select()
            # failed, and could block indefinitely waiting for EOF.
            proc.kill()
            try:
                proc.wait(timeout=PROCESS_CLEANUP_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                logger.warning(
                    "Process did not terminate after kill signal within timeout; "
                    "continuing cleanup."
                )
            # Now attempt to drain any remaining buffered data (best-effort).
            # Return values are intentionally discarded since we're raising immediately.
            _drain_fds_best_effort(
                readable_fds, proc.stdout, proc.stderr, stdout_buffer, stderr_buffer
            )
            # Defensive cleanup for stdin - already closed after prompt write,
            # but included for consistency with other error handlers.
            if proc.stdin and not proc.stdin.closed:
                proc.stdin.close()
            if proc.stdout:
                proc.stdout.close()
            if proc.stderr:
                proc.stderr.close()
            msg = f"select() failed (OSError, errno={e.errno}): {e}; streaming aborted"
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
            except OSError as e:
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
                read_errors.append((fd_name, e.errno, str(e)))
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
                # Handle the specific case where the file descriptor was closed during read.
                # This can happen if the process terminates abruptly between select() and read().
                #
                # Decision logic:
                # 1. If fd lacks 'closed' attribute: unexpected object type, re-raise
                # 2. If fd.closed is False: unexpected ValueError (not a closure issue), re-raise
                # 3. If fd.closed is True: handle as I/O error from closed fd
                #
                # Only case (3) is handled; cases (1) and (2) re-raise to surface bugs.
                if hasattr(fd, "closed") and fd.closed:
                    fd_name = "stdout" if fd == proc.stdout else "stderr"
                    logger.error(
                        "ValueError reading from Claude process (fd=%s, closed=%s): %s - "
                        "fd closed during read, OUTPUT MAY BE INCOMPLETE",
                        fd_name,
                        fd.closed,
                        e,
                    )
                    read_errors.append((fd_name, getattr(e, "errno", None), str(e)))
                    print(
                        f"  [WARNING] Read error on {fd_name} (fd closed) - "
                        "some output may be missing",
                        file=sys.stderr,
                        flush=True,
                    )
                    eof_fds.add(fd)
                else:
                    # Unexpected ValueError: either fd lacks 'closed' attribute (unusual
                    # file-like object) or fd.closed is False (ValueError for other reason).
                    # Re-raise to surface the issue rather than silently masking it.
                    raise

        # Termination check #2 (after processing readable fds): Exit if process finished
        # and select() returned no readable fds. See _should_exit_streaming_loop for details.
        if _should_exit_streaming_loop(process_exited, readable):
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

    # Surface any read errors that occurred during streaming
    if read_errors:
        # Format errors with fd_name context for easier debugging
        formatted_errors = [
            f"{fd_name} (errno={errno}): {err}" for fd_name, errno, err in read_errors
        ]
        logger.error(
            "Claude execution completed with %d read errors - output may be incomplete:\n%s",
            len(read_errors),
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
