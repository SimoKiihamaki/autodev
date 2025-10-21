"""Integrations with external agents (Codex, CodeRabbit, Claude)."""

from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path
from typing import Optional

from .command import run_cmd, verify_unsafe_execution_ready
from .logging_utils import logger
from .utils import extract_called_process_error_details


def codex_exec(
    prompt: str,
    repo_root: Path,
    model: str = "gpt-5-codex",
    enable_search: bool = True,
    yolo: bool = False,
    allow_unsafe_execution: bool = False,
    dry_run: bool = False,
    extra: Optional[list[str]] = None,
) -> str:
    os.environ.setdefault("CI", "1")
    args: list[str] = ["codex"]
    if enable_search:
        args.append("--search")
    if yolo or allow_unsafe_execution:
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
    out, _, _ = run_cmd(args, cwd=repo_root, check=True, stdin=prompt)
    return out


def parse_rate_limit_sleep(message: str) -> Optional[int]:
    if not message:
        return None
    match = re.search(
        r"try after (\d+)\s+(?:minute(?:s)?|min(?:s)?)\s+and\s+(\d+)\s+(?:second(?:s)?|sec(?:s)?)",
        message,
        re.IGNORECASE,
    )
    if match:
        minutes = int(match.group(1))
        seconds = int(match.group(2))
        return minutes * 60 + seconds + 5
    match = re.search(r"try after (\d+)\s+(?:second(?:s)?|sec(?:s)?)", message, re.IGNORECASE)
    if match:
        seconds = int(match.group(1))
        return seconds + 5
    return None


def coderabbit_prompt_only(base_branch: str | None, repo_root: Path) -> str:
    args = ["coderabbit", "--prompt-only"]
    if base_branch:
        args += ["--base", base_branch]
    attempts = 0
    while True:
        attempts += 1
        try:
            out, _, _ = run_cmd(args, cwd=repo_root)
            return out.strip()
        except subprocess.CalledProcessError as exc:
            msg = extract_called_process_error_details(exc)
            sleep_secs = parse_rate_limit_sleep(msg)
            if sleep_secs and attempts <= 3:
                logger.warning("CodeRabbit rate limited; sleeping %s seconds before retry", sleep_secs)
                time.sleep(sleep_secs)
                continue
            logger.warning("CodeRabbit prompt-only run failed: %s", msg or exc)
            return ""


def coderabbit_has_findings(text: str) -> bool:
    if not text.strip():
        return False
    lowered = text.lower()
    for marker in ("file:", "line", "issue", "prompt for ai agent", "consider", "fix", "security", "leak", "race"):
        if marker in lowered:
            return True
    return False


def claude_exec(
    prompt: str,
    repo_root: Path,
    model: str | None = None,
    enable_search: bool = True,
    yolo: bool = False,
    allow_unsafe_execution: bool = False,
    dry_run: bool = False,
    extra: Optional[list[str]] = None,
) -> str:
    """Execute a Claude command. Parameters mirror codex_exec for API compatibility."""
    if not (yolo or allow_unsafe_execution):
        raise SystemExit("Claude executor requires allow_unsafe_execution=True to bypass permissions.")
    os.environ.setdefault("CI", "1")
    verify_unsafe_execution_ready()
    args: list[str] = ["claude", "--dangerously-skip-permissions"]
    if extra:
        args.extend(extra)
    args.extend(["-p", "-"])
    if dry_run:
        logger.info("Dry run enabled; skipping Claude execution. Args: %s", args)
        return "DRY_RUN"
    out, _, _ = run_cmd(args, cwd=repo_root, check=True, stdin=prompt)
    return out
