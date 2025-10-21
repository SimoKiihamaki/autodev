"""Shared constants for the auto PRD pipeline."""

from __future__ import annotations

import re
import shutil
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
    "Check `codex config show --effective` and adjust sandbox/approval settings so the agent has write access."
)

ZSH_PATH = shutil.which("zsh")
if not ZSH_PATH:
    raise RuntimeError(
        "'zsh' binary not found on PATH; zsh is required for the shell environment policy. "
        "Install zsh or update your PATH to include it before continuing."
    )
COMMAND_ALLOWLIST = {
    "codex",
    "coderabbit",
    "git",
    "gh",
    Path(ZSH_PATH).name,
    ZSH_PATH,
    "claude",
}
UNSAFE_ARG_CHARS = set("|;><`")
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

PRINT_LOGGER_NAME = "auto_prd.print"

VALID_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
ACCEPTED_LOG_LEVELS = (*VALID_LOG_LEVELS, "WARN")

RATE_LIMIT_STATUS = {"403", "429"}
REVIEW_BOT_LOGINS = {
    login.lower()
    for login in {
        "coderabbitai",
        "coderabbit",
        "coderabbit-ai",
        "copilot",
        "copilot-pull-request-reviewer",
        "copilot-pull-request-reviewer[bot]",
        "github-copilot",
        "github-copilot[bot]",
    }
}
