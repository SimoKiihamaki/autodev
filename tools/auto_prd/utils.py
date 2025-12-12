"""General utilities used by the automation pipeline."""

from __future__ import annotations

import random
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Tuple

from .constants import (
    CLI_ARG_REPLACEMENTS,
    CHECKBOX_ANY_RE,
    CHECKBOX_UNCHECKED_RE,
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


def checkbox_stats(md: Path) -> Tuple[int, int]:
    if not md.exists():
        return 0, 0
    txt = md.read_text(encoding="utf-8", errors="ignore")
    total = len(CHECKBOX_ANY_RE.findall(txt))
    unchecked = len(CHECKBOX_UNCHECKED_RE.findall(txt))
    return unchecked, total


def parse_tasks_left(output: str) -> Optional[int]:
    if not output:
        return None
    match = TASKS_LEFT_RE.search(output)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def extract_http_status(exc: subprocess.CalledProcessError) -> Optional[str]:
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

    SECURITY: This function intentionally does NOT fall back to stdout.
    Stdout may contain model output which could include sensitive data
    (secrets, PII, tokens) that should not be logged or displayed to users,
    even after sanitization. Using stderr-only ensures error messages come
    from the process's error stream, not from potentially sensitive output.

    BREAKING CHANGE: Previous versions of this function fell back to stdout
    when stderr was empty::

        text = (stderr or stdout or "").strip()  # OLD behavior

    This was changed to stderr-only for security reasons. Code that previously
    received stdout content in error details will now receive "exit code N"
    instead. Callers who need stdout content should access the exception's
    `output` or `stdout` attribute directly after appropriate sanitization.

    Args:
        exc: The CalledProcessError exception to extract details from.

    Returns:
        A string containing stderr content if available, otherwise a simple
        "exit code N" fallback. Never includes stdout content.
    """
    _, stderr = _extract_stdout_stderr(exc)
    text = (stderr or "").strip()
    return text or f"exit code {exc.returncode}"


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


def detect_readonly_block(output: str) -> Optional[str]:
    if not output:
        return None
    lowered = output.lower()
    for pattern in CODEX_READONLY_PATTERNS:
        if pattern.lower() in lowered:
            return pattern
    return None


def report_readonly_error(pattern: str) -> None:
    raise RuntimeError(CODEX_READONLY_ERROR_MSG.format(pattern=pattern))
