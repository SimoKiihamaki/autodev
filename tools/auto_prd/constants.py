"""Shared constants for the auto PRD pipeline."""

from __future__ import annotations

import os
import re
import shutil
import threading
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import MappingProxyType

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
# Valid phase names for the --phases CLI argument.
# These are the authoritative phase identifiers used in CLI args and checkpoints.
#
# Phase name mapping (Python CLI ← Go TUI):
#   - "local"      ← FlagNameLocal ("local")
#   - "pr"         ← FlagNamePR ("pr")
#   - "review_fix" ← FlagNameReview ("review")  (NOTE: different display name in TUI!)
#
# See internal/tui/model.go for Go-side definitions.
VALID_PHASES = ("local", "pr", "review_fix")
PHASES_WITH_COMMIT_RISK = {"local", "pr"}

# Per-phase tool allowlists for Claude Code headless mode.
# These restrict which tools Claude can use during each execution phase,
# reducing blast radius and improving security.
#
# IMPORTANT: Phase Name Mapping
# These internal phase names differ from CLI phase names (VALID_PHASES above):
#   - "implement" (here) corresponds to "local" (CLI) - local implementation phase
#   - "fix" (here only) - CodeRabbit fix phase, not exposed in CLI
#   - "pr" (same) - Pull request creation phase
#   - "review_fix" (same) - Review and fix phase
#
# When calling get_tool_allowlist(), use the internal names from this mapping,
# not the CLI names. For example:
#   - get_tool_allowlist("implement")  # Correct
#   - get_tool_allowlist("local")      # Wrong - will raise ValueError
#
# Tool syntax follows Claude Code's --allowedTools format:
# - Simple tools: "Read", "Edit", "Write", "Glob", "Grep"
# - Bash with patterns: "Bash(command:*)" allows specific commands
#   Multiple commands can be comma-separated: "Bash(git:*,make:*,npm:*)"
# - Each tool in the list becomes a separate --allowedTools argument
#
# See: https://code.claude.com/docs/en/cli-reference
#
# Note: This mapping is immutable (MappingProxyType with tuple values) to prevent
# accidental modification at runtime. Use get_tool_allowlist() for safe access.
_HEADLESS_TOOL_ALLOWLISTS_RAW: dict[str, tuple[str, ...]] = {
    # Local/implement phase: needs full file access + build commands
    "implement": (
        "Bash(git:*,make:*,npm:*,pnpm:*,yarn:*,pytest:*,cargo:*,go:*)",
        "Read",
        "Edit",
        "Write",
        "Glob",
        "Grep",
    ),
    # Fix phase (CodeRabbit fixes): limited to editing existing files
    "fix": (
        "Bash(git:*,make:*,npm:*,pnpm:*,pytest:*)",
        "Read",
        "Edit",
    ),
    # PR phase: git + GitHub CLI only
    "pr": (
        "Bash(git:*,gh:*)",
        "Read",
    ),
    # Review/fix phase: needs edit access + GitHub for PR updates
    "review_fix": (
        "Bash(git:*,gh:*,make:*,npm:*,pnpm:*,pytest:*)",
        "Read",
        "Edit",
        "Write",
    ),
}

# Immutable view of tool allowlists - prevents accidental modification.
HEADLESS_TOOL_ALLOWLISTS: Mapping[str, Sequence[str]] = MappingProxyType(
    _HEADLESS_TOOL_ALLOWLISTS_RAW
)


def get_tool_allowlist(phase: str) -> list[str]:
    """Get the tool allowlist for a phase with clear error on invalid phase.

    This function provides a safer alternative to direct dictionary access,
    giving clear error messages when an invalid phase name is used.

    Args:
        phase: The execution phase (implement, fix, pr, review_fix).

    Returns:
        List of allowed tools for the phase.

    Raises:
        ValueError: If phase is not a valid phase name.
    """
    if phase not in HEADLESS_TOOL_ALLOWLISTS:
        valid_phases = sorted(HEADLESS_TOOL_ALLOWLISTS.keys())
        msg = f"Invalid phase '{phase}'; valid phases are: {valid_phases}"
        raise ValueError(msg)
    return list(HEADLESS_TOOL_ALLOWLISTS[phase])


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

# Codex CLI review bot logins (the standalone `codex` CLI tool from OpenAI, distinct
# from GitHub Copilot which is handled by COPILOT_REVIEW_LOGINS above).
# These are the GitHub account names used by the Codex CLI when posting PR comments.
CODEX_REVIEW_LOGINS = {
    login.lower()
    for login in {
        "chatgpt-codex-connector",
        "chatgpt-codex-connector[bot]",
        "codex",
        "codex[bot]",
    }
}

REVIEW_BOT_LOGINS = (
    CODERABBIT_REVIEW_LOGINS | COPILOT_REVIEW_LOGINS | CODEX_REVIEW_LOGINS
)
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
