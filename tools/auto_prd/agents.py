"""Integrations with external agents (Codex, CodeRabbit, Claude)."""

from __future__ import annotations

import os
import random
import re
import subprocess
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional

from .command import run_cmd, verify_unsafe_execution_ready
from .logging_utils import logger
from .utils import extract_called_process_error_details

RATE_LIMIT_JITTER_MIN = -3
RATE_LIMIT_JITTER_MAX = 3
RATE_LIMIT_MIN_SLEEP_SECONDS = 5
RATE_LIMIT_MAX_SLEEP_SECONDS = 900
CODERABBIT_PROMPT_TIMEOUT_SECONDS = 900


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
        logger.warning("Invalid %s value %r; falling back to %s", env_key, raw, default)
        return default

    if parsed <= 0:
        return None
    return parsed


def get_codex_exec_timeout() -> int | None:
    """Get the Codex execution timeout from environment variables."""
    return _timeout_from_env("AUTO_PRD_CODEX_TIMEOUT_SECONDS", None)


def get_claude_exec_timeout() -> int | None:
    """Get the Claude execution timeout from environment variables."""
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
) -> str:
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
        return "DRY_RUN"
    out, _, _ = run_cmd(
        args,
        cwd=repo_root,
        check=True,
        stdin=prompt,
        timeout=get_codex_exec_timeout(),
    )
    return out


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
            logger.warning("CodeRabbit prompt-only run failed: %s", msg or exc)
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


def claude_exec(
    prompt: str,
    repo_root: Path,
    model: str | None = None,
    enable_search: bool = True,
    yolo: Optional[bool] = None,
    allow_unsafe_execution: Optional[bool] = None,
    dry_run: bool = False,
    extra: Optional[list[str]] = None,
) -> str:
    """Execute a Claude command. Parameters mirror codex_exec for API compatibility."""
    allow_flag = allow_unsafe_execution
    if yolo is not None:
        logger.warning(
            "claude_exec: 'yolo' is deprecated; use allow_unsafe_execution instead"
        )
        if allow_flag is None:
            allow_flag = yolo
        else:
            allow_flag = allow_flag or yolo
    allow_flag = bool(allow_flag)
    if not allow_flag and not dry_run:
        raise PermissionError(
            "Claude executor requires allow_unsafe_execution=True to bypass permissions."
        )
    os.environ.setdefault("CI", "1")
    if allow_flag:
        verify_unsafe_execution_ready()
    args: list[str] = ["claude"]
    if allow_flag:
        args.append("--dangerously-skip-permissions")
    if model:
        args.extend(["--model", model])
    if not enable_search:
        logger.info(
            "Claude CLI does not yet expose a --no-search flag; ignoring enable_search=False"
        )
    if extra:
        args.extend(extra)
    args.extend(["-p", "-"])
    if dry_run:
        logger.info("Dry run enabled; skipping Claude execution. Args: %s", args)
        return "DRY_RUN"
    out, _, _ = run_cmd(
        args,
        cwd=repo_root,
        check=True,
        stdin=prompt,
        timeout=get_claude_exec_timeout(),
    )
    return out
