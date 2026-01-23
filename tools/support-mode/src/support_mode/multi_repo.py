"""Multi-repository monitoring support.

Allows monitoring multiple repositories simultaneously with tabular output.
"""

from __future__ import annotations

import logging
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from .git_ops import git_current_branch, git_head_sha
from .tracker import load_tracker, validate_tracker

logger = logging.getLogger(__name__)


@dataclass
class RepoStatus:
    """Status of a single repository."""

    path: str
    name: str
    branch: str
    sha: str
    has_changes: bool = False
    tracker_valid: bool = False
    tasks_left: int = 0
    total_tasks: int = 0
    issues: list[str] | None = None
    warnings: list[str] | None = None


def check_repository(repo_path: Path) -> RepoStatus:
    """Check status of a single repository.

    Args:
        repo_path: Path to repository.

    Returns:
        RepoStatus with repository information.
    """
    if not repo_path.exists():
        return RepoStatus(
            path=str(repo_path),
            name=repo_path.name,
            branch="",
            sha="",
            issues=[f"Repository path not found: {repo_path}"],
        )

    try:
        branch = git_current_branch(repo_path)
        sha = git_head_sha(repo_path)
    except (OSError, Exception) as e:
        return RepoStatus(
            path=str(repo_path),
            name=repo_path.name,
            branch="",
            sha="",
            issues=[f"Git error: {e}"],
        )

    # Load tracker for task counts
    tasks_left = 0
    total_tasks = 0
    tracker_valid = False
    issues = []
    warnings = []

    tracker = load_tracker(repo_path)
    if tracker:
        valid, errors = validate_tracker(tracker)
        tracker_valid = valid
        if not valid:
            issues.extend(errors)

        raw_features = tracker.get("features", [])
        if isinstance(raw_features, list):
            total_tasks = sum(
                len(f.get("tasks", [])) if isinstance(f.get("tasks"), list) else 0
                for f in raw_features
                if isinstance(f, dict)
            )
            completed_tasks = sum(
                1
                for f in raw_features
                if isinstance(f, dict)
                for t in f.get("tasks", [])
                if isinstance(t, dict) and t.get("status") == "completed"
            )
            tasks_left = total_tasks - completed_tasks
    else:
        warnings.append("No tracker found")

    return RepoStatus(
        path=str(repo_path),
        name=repo_path.name,
        branch=branch,
        sha=sha[:7],
        has_changes=False,  # TODO: check git status
        tracker_valid=tracker_valid,
        tasks_left=tasks_left,
        total_tasks=total_tasks,
        issues=issues if issues else None,
        warnings=warnings if warnings else None,
    )


def check_repositories_parallel(
    repos: list[dict[str, str]], max_workers: int = 4
) -> list[RepoStatus]:
    """Check multiple repositories in parallel.

    Args:
        repos: List of {path: str} dicts.
        max_workers: Maximum parallel workers.

    Returns:
        List of RepoStatus for each repository.
    """
    results = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for repo in repos:
            path = Path(repo["path"])
            future = executor.submit(check_repository, path)
            futures[future] = path

        for future in concurrent.futures.as_completed(futures):
            try:
                status = future.result()
                results.append(status)
            except Exception as e:
                path = futures[future]
                logger.error(f"Error checking repository {path}: {e}")
                results.append(
                    RepoStatus(
                        path=str(path),
                        name=path.name,
                        branch="",
                        sha="",
                        issues=[f"Check failed: {e}"],
                    )
                )

    return results


def format_repo_table(statuses: list[RepoStatus], width: int = 120) -> str:
    """Format repository statuses as a table.

    Args:
        statuses: List of repository statuses.
        width: Table width in characters.

    Returns:
        Formatted table string.
    """
    if not statuses:
        return "No repositories to display."

    lines = []
    lines.append("=" * width)
    lines.append("Multi-Repository Status Monitor")
    lines.append("=" * width)
    lines.append("")

    for status in statuses:
        lines.append(f"📁 {status.name}")
        lines.append(f"   Path: {status.path}")
        lines.append(f"   Branch: {status.branch} @ {status.sha}")

        if status.issues:
            lines.append(f"   ❌ Issues: {len(status.issues)}")
            for issue in status.issues[:3]:
                lines.append(f"      - {issue}")

        if status.warnings:
            lines.append(f"   ⚠️  Warnings: {len(status.warnings)}")
            for warning in status.warnings[:2]:
                lines.append(f"      - {warning}")

        if status.total_tasks > 0:
            pct = (status.total_tasks - status.tasks_left) / status.total_tasks * 100
            lines.append(
                f"   Tasks: {status.total_tasks - status.tasks_left}/{status.total_tasks} ({pct:.0f}%)"
            )

        lines.append("")

    lines.append("=" * width)
    return "\n".join(lines)
