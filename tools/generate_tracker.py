#!/usr/bin/env python3
"""Standalone CLI tool for generating implementation trackers from PRD files.

This tool provides a clean interface for agents to generate trackers without
running the full automation pipeline.

Usage:
    # From file
    python tools/generate_tracker.py --prd path/to/prd.md --repo /path/to/repo --executor codex

    # From stdin
    cat prd.md | python tools/generate_tracker.py --stdin --repo /path/to/repo --executor codex
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import tempfile
from pathlib import Path

try:
    from tools.auto_prd.tracker_generator import generate_tracker, get_tracker_path
    from tools.auto_prd.git_ops import git_root
except ImportError:
    # Fallback for direct script invocation
    from auto_prd.tracker_generator import generate_tracker, get_tracker_path
    from auto_prd.git_ops import git_root


VALID_EXECUTORS = {"claude", "codex"}


def build_parser() -> argparse.ArgumentParser:
    """Build argument parser for the CLI tool."""
    parser = argparse.ArgumentParser(
        description="Generate implementation tracker from PRD file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Generate tracker from PRD file
    python generate_tracker.py --prd feature.md --executor codex

    # Generate from stdin
    cat feature.md | python generate_tracker.py --stdin --executor claude

    # Dry run (no agent execution)
    python generate_tracker.py --prd feature.md --dry-run
        """,
    )

    # Input source (mutually exclusive)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--prd",
        type=Path,
        help="Path to PRD markdown file",
    )
    input_group.add_argument(
        "--stdin",
        action="store_true",
        help="Read PRD content from stdin",
    )

    # Other options
    parser.add_argument(
        "--repo",
        type=Path,
        default=None,
        help="Repository root (default: current git root)",
    )
    parser.add_argument(
        "--executor",
        choices=sorted(VALID_EXECUTORS),
        default="claude",
        help="Executor to use for generation (default: claude)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate even if existing tracker is valid",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip agent execution, return mock tracker",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path (default: .aprd/tracker.json in repo root)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Minimal output, only print tracker path on success",
    )

    return parser


def resolve_repo_root(repo_arg: Path | None) -> Path:
    """Resolve repository root from argument or git detection."""
    if repo_arg is not None:
        repo = repo_arg.resolve()
        if not repo.is_dir():
            raise ValueError(f"Repository path is not a directory: {repo}")
        return repo

    # Try to detect git root
    detected = git_root()
    if detected:
        return Path(detected)

    # Fall back to current directory
    return Path.cwd()


def read_stdin_to_temp_file() -> tuple[Path, str]:
    """Read PRD content from stdin and write to a temporary file.

    Returns:
        Tuple of (temp_file_path, content_hash)
    """
    content = sys.stdin.read()
    if not content.strip():
        raise ValueError("Empty input received from stdin")

    # Generate a hash for the source identifier
    content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

    # Create temp file that persists until explicitly deleted
    temp_file = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".md",
        prefix=f"stdin_{content_hash}_",
        delete=False,
    )
    temp_file.write(content)
    temp_file.close()

    return Path(temp_file.name), content_hash


def main() -> int:
    """Main entry point for the CLI tool."""
    parser = build_parser()
    args = parser.parse_args()

    temp_file: Path | None = None

    try:
        # Resolve repository root
        repo_root = resolve_repo_root(args.repo)

        # Resolve PRD path
        if args.stdin:
            prd_path, content_hash = read_stdin_to_temp_file()
            temp_file = prd_path
            if not args.quiet:
                print(f"Read PRD from stdin (hash: {content_hash})", file=sys.stderr)
        else:
            prd_path = args.prd.resolve()
            if not prd_path.is_file():
                print(f"Error: PRD file not found: {prd_path}", file=sys.stderr)
                return 1

        # Validate executor
        if args.executor not in VALID_EXECUTORS:
            print(
                f"Error: Invalid executor '{args.executor}'. "
                f"Must be one of: {', '.join(sorted(VALID_EXECUTORS))}",
                file=sys.stderr,
            )
            return 1

        if not args.quiet:
            print(f"Generating tracker from: {prd_path}", file=sys.stderr)
            print(f"Repository root: {repo_root}", file=sys.stderr)
            print(f"Executor: {args.executor}", file=sys.stderr)

        # Generate tracker
        tracker = generate_tracker(
            prd_path=prd_path,
            repo_root=repo_root,
            executor=args.executor,
            force=args.force,
            dry_run=args.dry_run,
            allow_unsafe_execution=True,
        )

        # Determine output path
        if args.output:
            output_path = args.output.resolve()
        else:
            output_path = get_tracker_path(repo_root)

        # Report success
        if not args.quiet:
            total_features = tracker["validation_summary"]["total_features"]
            total_tasks = tracker["validation_summary"]["total_tasks"]
            print(
                f"Tracker generated: {total_features} features, {total_tasks} tasks",
                file=sys.stderr,
            )

        # Print tracker path to stdout for agent consumption
        print(str(output_path))
        return 0

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error generating tracker: {e}", file=sys.stderr)
        return 1
    finally:
        # Clean up temp file if created
        if temp_file is not None and temp_file.exists():
            try:
                temp_file.unlink()
            except OSError:
                pass


if __name__ == "__main__":
    sys.exit(main())
