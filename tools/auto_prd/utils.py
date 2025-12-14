"""General utilities used by the automation pipeline."""

from __future__ import annotations

import random
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .constants import (
    CHECKBOX_ANY_RE,
    CHECKBOX_UNCHECKED_RE,
    CLI_ARG_REPLACEMENTS,
    CODEX_READONLY_ERROR_MSG,
    CODEX_READONLY_PATTERNS,
    RATE_LIMIT_STATUS,
    TASKS_LEFT_RE,
    UNSAFE_ARG_CHARS,
)
from .logging_utils import decode_output, logger


def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return re.sub(r"-+", "-", value).strip("-") or "task"


def scrub_cli_text(value: str) -> str:
    """Return a version of value without shell metacharacters reserved by the safety policy."""
    if not value:
        return value

    first_unsafe_index: int | None = None
    for idx, char in enumerate(value):
        if char in UNSAFE_ARG_CHARS:
            first_unsafe_index = idx
            break
    if first_unsafe_index is None:
        return value

    cleaned_chars: list[str] = list(value[:first_unsafe_index])
    for char in value[first_unsafe_index:]:
        if char in UNSAFE_ARG_CHARS:
            replacement = CLI_ARG_REPLACEMENTS.get(char)
            if replacement is None:
                logger.warning(
                    "Unmapped unsafe character %r encountered in CLI argument; replacing with space. "
                    "Update CLI_ARG_REPLACEMENTS if this character should have a specific representation.",
                    char,
                )
                replacement = " "
            cleaned_chars.append(replacement)
        else:
            cleaned_chars.append(char)
    cleaned = "".join(cleaned_chars)
    logger.debug(
        "Sanitized CLI text to remove unsafe shell metacharacters: %r -> %r",
        value,
        cleaned,
    )
    return cleaned


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def checkbox_stats(md: Path) -> tuple[int, int]:
    if not md.exists():
        return 0, 0
    txt = md.read_text(encoding="utf-8", errors="ignore")
    total = len(CHECKBOX_ANY_RE.findall(txt))
    unchecked = len(CHECKBOX_UNCHECKED_RE.findall(txt))
    return unchecked, total


def parse_tasks_left(output: str) -> int | None:
    if not output:
        return None
    match = TASKS_LEFT_RE.search(output)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def extract_http_status(exc: subprocess.CalledProcessError) -> str | None:
    stdout, stderr = _extract_stdout_stderr(exc)
    text = (stderr or "") + "\n" + (stdout or "")
    match = re.search(r"HTTP\s+(\d{3})", text)
    if match:
        return match.group(1)
    return None


def _coerce_text(data: Any) -> str:
    if data is None:
        return ""
    if isinstance(data, bytes):
        return decode_output(data)
    return str(data)


def _extract_stdout_stderr(exc: subprocess.CalledProcessError) -> tuple[str, str]:
    """
    Extract stdout and stderr from a CalledProcessError, handling both `output` and `stdout` attributes.

    In Python 3.5+, CalledProcessError.output is always an alias for stdout. However, depending on
    how the exception was raised, different attributes may be populated:

    - subprocess.run(..., capture_output=True, check=True) populates `stdout` and `stderr`.
    - subprocess.check_output() and subprocess.check_call() populate `output` (alias for `stdout`).

    This function checks both `output` and `stdout` for robustness, ensuring compatibility with
    different subprocess invocation patterns and Python versions.

    Returns:
        tuple[str, str]: A tuple containing (stdout, stderr) as strings.
    """
    stderr = _coerce_text(getattr(exc, "stderr", None))
    output_val = getattr(exc, "output", None)
    stdout = _coerce_text(output_val)
    if output_val is None:
        stdout = _coerce_text(getattr(exc, "stdout", None))
    return stdout, stderr


def extract_called_process_error_details(exc: subprocess.CalledProcessError) -> str:
    """Extract error details from CalledProcessError using stderr only.

    Returns stderr content if available; otherwise returns "exit code N".
    Stdout is never included to prevent sensitive model output from appearing
    in error messages.

    Args:
        exc: The CalledProcessError exception to extract details from.

    Returns:
        A string containing stderr content if available, otherwise "exit code N".
    """
    stdout, stderr = _extract_stdout_stderr(exc)
    text = (stderr or "").strip()
    if not text:
        # Log at DEBUG level when falling back to exit code - this helps identify
        # cases where callers might have previously relied on stdout content.
        # The stdout length is logged (not content) to indicate if data was available.
        if stdout and stdout.strip():
            logger.debug(
                "extract_called_process_error_details: stderr empty, stdout has %d chars "
                "(not used for security; returning exit code fallback)",
                len(stdout),
            )
        return f"exit code {exc.returncode}"
    return text


def call_with_backoff(action, *, retries: int = 3, base_delay: float = 1.0) -> Any:
    attempt = 0
    while True:
        try:
            return action()
        except subprocess.CalledProcessError as exc:
            status = extract_http_status(exc)
            if status not in RATE_LIMIT_STATUS or attempt >= retries:
                raise
            sleep_for = base_delay * (2**attempt) + random.uniform(0.0, 0.5)
            time.sleep(sleep_for)
            attempt += 1


def detect_readonly_block(output: str) -> str | None:
    if not output:
        return None
    lowered = output.lower()
    for pattern in CODEX_READONLY_PATTERNS:
        if pattern.lower() in lowered:
            return pattern
    return None


def report_readonly_error(pattern: str) -> None:
    raise RuntimeError(CODEX_READONLY_ERROR_MSG.format(pattern=pattern))


def is_valid_int(value: object) -> bool:
    """Check if value is a valid integer, excluding booleans.

    Python's bool is a subclass of int, so isinstance(True, int) returns True.
    This function explicitly excludes booleans when checking for integer values,
    which is useful when parsing numeric fields from JSON/checkpoint data where
    boolean values are semantically incorrect.

    Args:
        value: The value to check.

    Returns:
        True if value is an int (but not a bool), False otherwise.

    Examples:
        >>> is_valid_int(42)
        True
        >>> is_valid_int(True)  # bool is a subclass of int
        False
        >>> is_valid_int(3.14)
        False
        >>> is_valid_int("42")
        False
    """
    return isinstance(value, int) and not isinstance(value, bool)


def is_valid_numeric(value: object) -> bool:
    """Check if value is a valid numeric (int or float), excluding booleans.

    Python's bool is a subclass of int, so isinstance(True, int) returns True.
    This function explicitly excludes booleans when checking for numeric values,
    which is useful when parsing numeric fields from JSON/checkpoint data where
    boolean values are semantically incorrect.

    Args:
        value: The value to check.

    Returns:
        True if value is an int or float (but not a bool), False otherwise.

    Examples:
        >>> is_valid_numeric(42)
        True
        >>> is_valid_numeric(3.14)
        True
        >>> is_valid_numeric(True)  # bool is a subclass of int
        False
        >>> is_valid_numeric("42")
        False
    """
    return isinstance(value, int | float) and not isinstance(value, bool)


def sanitize_for_cli(text: str) -> str:
    """Sanitize text to replace unsafe CLI characters.

    Replaces characters that could trigger validate_command_args() security
    checks when the text is passed as CLI arguments. This is used for context
    strings that are passed via --append-system-prompt.

    Args:
        text: The text to sanitize.

    Returns:
        Sanitized text with unsafe characters replaced according to CLI_ARG_REPLACEMENTS.
    """
    for unsafe, safe in CLI_ARG_REPLACEMENTS.items():
        text = text.replace(unsafe, safe)
    return text
