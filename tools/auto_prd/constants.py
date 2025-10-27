"""Shared constants for the auto PRD pipeline."""

from __future__ import annotations

import os
import re
import shutil
import threading
from pathlib import Path


CHECKBOX_ANY_RE = re.compile(r"^\s*[-*]\s*\[[ xX]\]", flags=re.MULTILINE)
CHECKBOX_UNCHECKED_RE = re.compile(r"^\s*[-*]\s*\[\s\]", flags=re.MULTILINE)
TASKS_LEFT_RE = re.compile(r"TASKS_LEFT\s*=\s*(\d+)", flags=re.IGNORECASE)
CODEX_READONLY_PATTERNS = (
    "sandbox is read-only",
    "sandbox: read-only",
    "writing outside of the project",
    "Operation not permitted",
    "EPERM",
    "blocked because the repo is mounted read-only",
    'approval policy "never" prevents escalation',
)
CODEX_READONLY_ERROR_MSG = (
    "Codex reported it cannot modify the workspace (detected phrase: {pattern!r}). "
    "Confirm your sandbox/approval settings in ~/.codex/config.toml or via `codex --help` so the agent has write access."
)

ZSH_REQUIRED_ERROR = (
    "zsh binary not found on PATH; required for shell environment policy."
)
ALLOW_NO_ZSH_ENV = "AUTO_PRD_ALLOW_NO_ZSH"

COMMAND_ALLOWLIST = {
    "codex",
    "coderabbit",
    "git",
    "gh",
    "zsh",
    "claude",
    # "python",  # Removed for security: only allow specific scripts by full path
    # "python3", # Removed for security: only allow specific scripts by full path
}
ZSH_PATH: str | None = None
UNSAFE_ARG_CHARS = set("|;><`")
CLI_ARG_REPLACEMENTS = {
    "`": "'",
    "|": "/",
    ";": ",",
    "<": "(",
    ">": ")",
}
STDIN_MAX_BYTES = 200_000
SAFE_STDIN_ALLOWED_CTRL = {9, 10, 13}
SAFE_ENV_VAR = "AUTO_PRD_ALLOW_UNSAFE_EXECUTION"
SAFE_CWD_ROOTS: set[Path] = {Path(__file__).resolve().parent}
VALID_PHASES = ("local", "pr", "review_fix")
PHASES_WITH_COMMIT_RISK = {"local", "pr"}

COMMAND_VERIFICATION_TIMEOUT_SECONDS = 8

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
DEFAULT_LOG_DIR_NAME = "logs"
COMMAND_OUTPUT_LOG_LIMIT = 4000
CODERABBIT_FINDINGS_CHAR_LIMIT = 20_000

PRINT_LOGGER_NAME = "auto_prd.print"

VALID_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
ACCEPTED_LOG_LEVELS = (*VALID_LOG_LEVELS, "WARN")

RATE_LIMIT_STATUS = {"403", "429"}
CODERABBIT_REVIEW_LOGINS = {
    login.lower()
    for login in {
        "coderabbitai",
        "coderabbitai[bot]",
        "coderabbit",
        "coderabbit-ai",
    }
}

COPILOT_REVIEW_LOGINS = {
    login.lower()
    for login in {
        "copilot",
        "copilot-pull-request-reviewer",
        "copilot-pull-request-reviewer[bot]",
        "github-copilot",
        "github-copilot[bot]",
    }
}

REVIEW_BOT_LOGINS = CODERABBIT_REVIEW_LOGINS | COPILOT_REVIEW_LOGINS
REVIEW_FALLBACK_MENTION = "@reviewer"

_ZSH_LOCK = threading.Lock()


def require_zsh() -> str:
    """Return the path to zsh or raise if unavailable (unless explicitly allowed)."""
    global ZSH_PATH
    with _ZSH_LOCK:
        if ZSH_PATH:
            return ZSH_PATH
        maybe_skip = os.environ.get(ALLOW_NO_ZSH_ENV, "").strip()
        resolved = shutil.which("zsh")
        if resolved:
            ZSH_PATH = resolved
            COMMAND_ALLOWLIST.update({Path(resolved).name, resolved})
            return resolved
        if maybe_skip:
            ZSH_PATH = "zsh"
            return "zsh"
        raise RuntimeError(ZSH_REQUIRED_ERROR)
