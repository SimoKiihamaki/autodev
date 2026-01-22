"""Minimal git operations for support-mode."""

from __future__ import annotations

from pathlib import Path

from .command import run_cmd


def git_root() -> Path:
    """Find repository root directory.

    Returns:
        Path to the repository root directory.

    Raises:
        CalledProcessError: If git rev-parse fails.
    """
    out, _, _ = run_cmd(["git", "rev-parse", "--show-toplevel"])
    return Path(out.strip())


def git_current_branch(repo_root: Path) -> str:
    """Get current branch name.

    Args:
        repo_root: Path to the repository root.

    Returns:
        Current branch name.

    Raises:
        CalledProcessError: If git rev-parse fails.
    """
    result = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_root)
    return result.stdout.strip()


def git_head_sha(repo_root: Path) -> str:
    """Get HEAD commit SHA.

    Args:
        repo_root: Path to the repository root.

    Returns:
        Current HEAD commit SHA.

    Raises:
        CalledProcessError: If git rev-parse fails.
    """
    result = run_cmd(["git", "rev-parse", "HEAD"], cwd=repo_root)
    return result.stdout.strip()


def git_status_snapshot(repo_root: Path) -> tuple[str, ...]:
    """Get working tree status snapshot.

    Args:
        repo_root: Path to the repository root.

    Returns:
        Tuple of sorted git status porcelain output lines.
        Empty tuple if working tree is clean.
    """
    result = run_cmd(["git", "status", "--porcelain"], cwd=repo_root, check=False)
    return tuple(sorted(result.stdout.splitlines()))
