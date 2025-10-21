"""CLI wrapper that parses arguments and delegates to the app runner."""

from __future__ import annotations

import argparse

from .app import run
from .constants import SAFE_ENV_VAR, ACCEPTED_LOG_LEVELS
from .logging_utils import CURRENT_LOG_PATH, ORIGINAL_PRINT, logger


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Autonomous PRD→PR loop with Codex (YOLO), CodeRabbit & Copilot"
    )
    parser.add_argument("--prd", required=True, help="Path to PRD/task .md file")
    parser.add_argument("--repo", default=None, help="Path to repo root (default: current git root)")
    parser.add_argument("--repo-slug", default=None, help="owner/repo; default parsed from git remote")
    parser.add_argument(
        "--log-file",
        default=None,
        help="Write detailed run output to this file (default: repo logs/auto_prd_<timestamp>.log)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=ACCEPTED_LOG_LEVELS,
        help="Log level for command diagnostics (default: INFO)",
    )
    parser.add_argument("--base", default=None, help="Base branch (default: repository default branch)")
    parser.add_argument("--branch", default=None, help="Feature branch (default: from PRD filename)")
    parser.add_argument("--codex-model", default="gpt-5-codex", help="Codex model to use (default: gpt-5-codex)")
    parser.add_argument("--wait-minutes", type=int, default=0, help="Initial wait for PR bot reviews (default: 0)")
    parser.add_argument(
        "--review-poll-seconds",
        type=int,
        default=120,
        help="Polling interval when watching for reviews (default: 120)",
    )
    parser.add_argument(
        "--idle-grace-minutes",
        type=int,
        default=10,
        help="Stop after this many minutes with no unresolved feedback (default: 10)",
    )
    parser.add_argument(
        "--max-local-iters",
        type=int,
        default=50,
        help="Safety cap for local Codex<->CodeRabbit passes (default: 50)",
    )
    parser.add_argument(
        "--infinite-reviews",
        action="store_true",
        help="Continue indefinitely while feedback exists (overrides --idle-grace-minutes)",
    )
    parser.add_argument(
        "--sync-git",
        action="store_true",
        help="Fetch & fast-forward the base branch before creating the working branch",
    )
    parser.add_argument(
        "--allow-unsafe-execution",
        action="store_true",
        help=f"Allow Codex to run with unsafe capabilities (requires {SAFE_ENV_VAR}=1 and CI=1).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not execute Codex commands; useful for tests.")
    parser.add_argument(
        "--executor-policy",
        choices=("codex-first", "codex-only", "claude-only"),
        default=None,
        help="Executor policy: 'codex-first' (default), 'codex-only', or 'claude-only'. Can also use AUTO_PRD_EXECUTOR_POLICY.",
    )
    parser.add_argument(
        "--phases",
        default=None,
        help="Comma-separated list of phases to run (local,pr,review_fix). Default: all phases.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # pragma: no cover - capture unexpected failures for operators
        logger.exception("Fatal error during automation run")
        if CURRENT_LOG_PATH:
            ORIGINAL_PRINT(f"Fatal error: {exc}. See detailed logs at {CURRENT_LOG_PATH}")
        else:
            ORIGINAL_PRINT(f"Fatal error: {exc}")
        raise
