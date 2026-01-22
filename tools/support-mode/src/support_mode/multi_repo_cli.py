"""CLI for multi-repository monitoring."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .multi_repo import check_repositories_parallel, format_repo_table


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser.

    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        description="Monitor multiple repositories for AI-assisted development",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--config",
        type=Path,
        help="Path to config file with repository list",
    )
    parser.add_argument(
        "--repo",
        action="append",
        nargs=2,
        metavar=("PATH", "PRD"),
        help="Add repository (can be used multiple times)",
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=4,
        help="Maximum parallel workers",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=120,
        help="Table width",
    )

    return parser


def main() -> int:
    """Main CLI entry point.

    Returns:
        Exit code (0 for success, 1 for errors).
    """
    parser = build_parser()
    args = parser.parse_args()

    repos = []

    # Load from config if provided
    if args.config:
        from .config_file import Config

        config = Config.load(args.config)
        if config.multi_repo.enabled and config.multi_repo.repos:
            repos = config.multi_repo.repos

    # Add CLI-specified repos
    if args.repo:
        for path, prd in args.repo:
            repos.append({"path": path, "prd": prd})

    if not repos:
        print(
            "Error: No repositories specified. Use --config or --repo.", file=sys.stderr
        )
        return 1

    # Check all repositories
    statuses = check_repositories_parallel(repos, max_workers=args.parallel)

    # Format and print results
    table = format_repo_table(statuses, width=args.width)
    print(table)

    return 0


if __name__ == "__main__":
    sys.exit(main())
