"""CLI wrapper that parses arguments and delegates to the app runner."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .app import run
from .checkpoint import find_resumable_session, list_sessions, load_checkpoint
from .constants import ACCEPTED_LOG_LEVELS, SAFE_ENV_VAR
from .executor import AutoPrdError
from .policy import EXECUTOR_CHOICES
from .logging_utils import (
    CURRENT_LOG_PATH,
    ORIGINAL_PRINT,
    logger,
    initialize_output_buffering,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Autonomous PRD→PR loop with Codex (YOLO), CodeRabbit & Copilot",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    def non_negative(value: str) -> int:
        intval = int(value)
        if intval < 0:
            raise argparse.ArgumentTypeError("must be >= 0")
        return intval

    parser.add_argument("--prd", required=True, help="Path to PRD/task .md file")
    parser.add_argument(
        "--repo", default=None, help="Path to repo root (default: current git root)"
    )
    parser.add_argument(
        "--repo-slug", default=None, help="owner/repo; default parsed from git remote"
    )
    parser.add_argument(
        "--log-file",
        default=None,
        help="Write detailed run output to this file (default: repo logs/auto_prd_<timestamp>.log)",
    )
    parser.add_argument(
        "--log-level",
        type=str.upper,
        default="INFO",
        choices=ACCEPTED_LOG_LEVELS,
        help="Log level for command diagnostics (default: INFO)",
    )
    parser.add_argument(
        "--base", default=None, help="Base branch (default: repository default branch)"
    )
    parser.add_argument(
        "--branch", default=None, help="Feature branch (default: from PRD filename)"
    )
    parser.add_argument(
        "--codex-model", default="gpt-5-codex", help="Codex model to use"
    )
    parser.add_argument(
        "--wait-minutes",
        type=non_negative,
        default=0,
        help="Initial wait for PR bot reviews",
    )
    parser.add_argument(
        "--review-poll-seconds",
        type=non_negative,
        default=120,
        help="Polling interval when watching for reviews",
    )
    parser.add_argument(
        "--idle-grace-minutes",
        type=non_negative,
        default=10,
        help="Stop after this many minutes with no unresolved feedback",
    )
    parser.add_argument(
        "--max-local-iters",
        type=non_negative,
        default=50,
        help="Safety cap for local Codex<->CodeRabbit passes",
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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not execute Codex commands; useful for tests.",
    )
    parser.add_argument(
        "--executor-policy",
        choices=EXECUTOR_CHOICES,
        default=None,
        help="Executor policy: 'codex-first' (default), 'codex-only', or 'claude-only'. Can also use AUTO_PRD_EXECUTOR_POLICY.",
    )
    parser.add_argument(
        "--phases",
        default=None,
        help="Comma-separated list of phases to run (local,pr,review_fix). Default: all phases.",
    )

    # Session management arguments
    resume_group = parser.add_argument_group("session management")
    resume_group.add_argument(
        "--resume",
        action="store_true",
        help="Resume the most recent in-progress session for the given PRD.",
    )
    resume_group.add_argument(
        "--resume-session",
        metavar="SESSION_ID",
        default=None,
        help="Resume a specific session by ID.",
    )
    resume_group.add_argument(
        "--list-sessions",
        action="store_true",
        help="List available sessions and exit.",
    )
    resume_group.add_argument(
        "--force-new",
        action="store_true",
        help="Force creation of a new session even if a resumable one exists.",
    )

    return parser


def handle_list_sessions() -> None:
    """List available sessions and exit."""
    sessions = list_sessions(limit=50)
    if not sessions:
        print("No sessions found.")
        return

    print(f"{'Session ID':<50} {'Status':<12} {'Phase':<12} {'Updated':<20}")
    print("-" * 94)
    for session in sessions:
        session_id = session.get("session_id", "unknown")[:48]
        status = session.get("status", "unknown")
        phase = session.get("current_phase") or "-"
        updated = session.get("updated_at", "")[:19]  # Truncate to seconds
        print(f"{session_id:<50} {status:<12} {phase:<12} {updated:<20}")


def resolve_checkpoint(args) -> dict | None:
    """Resolve checkpoint based on CLI arguments.

    Returns:
        Checkpoint dict if resuming, None for new session.
    """
    from .git_ops import git_root

    if args.force_new:
        return None

    if args.resume_session:
        checkpoint = load_checkpoint(args.resume_session)
        if checkpoint is None:
            raise SystemExit(f"Session not found: {args.resume_session}")
        print(f"Resuming session: {args.resume_session}")
        return checkpoint

    if args.resume:
        prd_path = Path(args.prd).resolve()
        try:
            repo_root = Path(args.repo).resolve() if args.repo else git_root()
        except Exception:
            repo_root = Path.cwd()

        checkpoint = find_resumable_session(prd_path, repo_root)
        if checkpoint is None:
            print("No resumable session found. Starting new session.")
            return None

        session_id = checkpoint.get("session_id", "unknown")
        current_phase = checkpoint.get("current_phase", "unknown")
        print(f"Found resumable session: {session_id}")
        print(f"  Current phase: {current_phase}")

        # Check for PRD changes
        from .checkpoint import prd_changed_since_checkpoint

        if prd_changed_since_checkpoint(checkpoint, prd_path):
            print("  WARNING: PRD has been modified since session started.")
            print(
                "  Use --force-new to start fresh, or continue with potentially stale tasks."
            )

        return checkpoint

    return None


def main() -> None:
    # Initialize output buffering fixes BEFORE any significant output
    initialize_output_buffering()

    parser = build_parser()
    args = parser.parse_args()

    # Handle --list-sessions
    if args.list_sessions:
        handle_list_sessions()
        sys.exit(0)

    # Resolve checkpoint for resume
    checkpoint = resolve_checkpoint(args)
    args.checkpoint = checkpoint  # Attach to args for app.run()

    try:
        run(args)
    except AutoPrdError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except (
        Exception
    ) as exc:  # pragma: no cover - capture unexpected failures for operators
        logger.exception("Fatal error during automation run")
        if CURRENT_LOG_PATH:
            ORIGINAL_PRINT(
                f"Fatal error: {exc}. See detailed logs at {CURRENT_LOG_PATH}"
            )
        else:
            ORIGINAL_PRINT(f"Fatal error: {exc}")
        raise
