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
    CHECKBOX_ANY_RE,
    CHECKBOX_UNCHECKED_RE,
    CODEX_READONLY_ERROR_MSG,
    CODEX_READONLY_PATTERNS,
    RATE_LIMIT_STATUS,
    TASKS_LEFT_RE,
    UNSAFE_ARG_CHARS,
)
from .logging_utils import decode_output, logger


CLI_ARG_REPLACEMENTS = {
    "`": "'",
    "|": "/",
    ";": ",",
    "<": "(",
    ">": ")",
}


def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return re.sub(r"-+", "-", value).strip("-") or "task"


def scrub_cli_text(value: str) -> str:
    """Return a version of value without shell metacharacters reserved by the safety policy."""
    if not value or not any(char in UNSAFE_ARG_CHARS for char in value):
        return value

    cleaned_chars: list[str] = []
    for char in value:
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
    logger.debug("Sanitized CLI text to remove unsafe shell metacharacters: %r -> %r", value, cleaned)
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
    stderr = getattr(exc, "stderr", None)
    stdout = getattr(exc, "output", None)
    if stdout is None:
        stdout = getattr(exc, "stdout", None)
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


def extract_called_process_error_details(exc: subprocess.CalledProcessError) -> str:
    stderr = _coerce_text(getattr(exc, "stderr", None))
    stdout = _coerce_text(getattr(exc, "output", None))
    if not stdout:
        stdout = _coerce_text(getattr(exc, "stdout", None))
    text = (stderr or stdout or "").strip()
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
