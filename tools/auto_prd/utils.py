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
)
def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return re.sub(r"-+", "-", value).strip("-") or "task"


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


def extract_called_process_error_details(exc: subprocess.CalledProcessError) -> str:
    stderr = getattr(exc, "stderr", None)
    stdout = getattr(exc, "output", None)
    if stdout is None:
        stdout = getattr(exc, "stdout", None)
    return (stderr or stdout or "").strip() or f"exit code {exc.returncode}"


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
