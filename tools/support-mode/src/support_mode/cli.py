"""CLI entry point for support-mode standalone tool."""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

from .git_ops import git_root
from .support_loop import run_support_mode


def setup_logging(log_level: str = "INFO") -> None:
    """Configure logging for support mode.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
    """
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser.

    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        description="Continuous monitoring and review tool for AI-assisted development",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--prd",
        required=True,
        type=Path,
        help="Path to PRD/task .md file",
    )
    parser.add_argument(
        "--repo",
        default=None,
        type=Path,
        help="Path to repo root (default: current git root)",
    )
    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=120,
        help="Polling interval in seconds (min: 5)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level for diagnostics",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 0.1.0",
    )

    return parser


def main() -> int:
    """Main CLI entry point.

    Returns:
        Exit code (0 for success, 1 for errors).
    """
    parser = build_parser()
    args = parser.parse_args()

    # Validation
    if args.poll_seconds < 5:
        print("Error: --poll-seconds must be at least 5", file=sys.stderr)
        return 1

    if not args.prd.exists():
        print(f"Error: PRD file not found: {args.prd}", file=sys.stderr)
        return 1

    # Determine repo root
    try:
        repo_root = args.repo if args.repo else git_root()
    except (OSError, subprocess.CalledProcessError) as e:
        print(f"Error: Unable to find git repository root: {e}", file=sys.stderr)
        return 1

    if not repo_root.exists():
        print(f"Error: Repo root not found: {repo_root}", file=sys.stderr)
        return 1

    # Setup logging
    setup_logging(args.log_level)

    # Run support mode
    try:
        run_support_mode(repo_root, args.prd, args.poll_seconds)
        return 0
    except KeyboardInterrupt:
        print("\nSupport mode stopped.")
        return 0
    except Exception as e:
        logging.exception("Support mode crashed")
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

