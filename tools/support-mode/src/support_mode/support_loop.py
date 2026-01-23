"""Support loop - continuous monitoring and review."""

from __future__ import annotations

import logging
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .command import run_cmd
from .git_ops import git_current_branch, git_head_sha, git_status_snapshot
from .guardrails import load_guardrails
from .state import load_support_state, save_support_state
from .tracker import compute_prd_hash, load_tracker, validate_tracker
from .tracker_validator import validate_tracker_state
from .verification import VerificationPersistence, VerificationStatus

logger = logging.getLogger(__name__)

MIN_POLL_SECONDS = 5
DEFAULT_RECENT_COMMITS = 8
MAX_ITEMS = 8


def _normalize_text(text: str) -> str:
    """Normalize text for comparison."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _extract_prd_checkboxes(prd_content: str) -> list[str]:
    """Extract checkbox items from PRD markdown."""
    items = []
    pattern = re.compile(r"^\s*[-*]\s+\[( |x|X)\]\s*(.*)$")
    for line in prd_content.splitlines():
        match = pattern.match(line)
        if match:
            item = match.group(2).strip()
            if item:
                items.append(item)
    return items


def _collect_tracker_text(tracker: dict[str, Any]) -> list[str]:
    """Collect all text content from tracker for comparison."""
    texts = []
    raw_features = tracker.get("features", [])
    if not isinstance(raw_features, list):
        raw_features = []
    for feature in raw_features:
        if not isinstance(feature, dict):
            continue
        for key in ("name", "description"):
            val = feature.get(key)
            if isinstance(val, str) and val.strip():
                texts.append(val)
        raw_tasks = feature.get("tasks", [])
        if not isinstance(raw_tasks, list):
            raw_tasks = []
        for task in raw_tasks:
            if not isinstance(task, dict):
                continue
            desc = task.get("description")
            if isinstance(desc, str) and desc.strip():
                texts.append(desc)
    return texts


def _recent_commits(repo_root: Path, last_sha: str, limit: int) -> list[str]:
    """Get recent commits since last review."""
    if last_sha:
        try:
            out, _, _ = run_cmd(
                ["git", "log", "--oneline", f"{last_sha}..HEAD"],
                cwd=repo_root,
                check=True,
            )
            lines = [line for line in out.splitlines() if line.strip()]
            return lines
        except (OSError, subprocess.CalledProcessError):
            # Gracefully fall back to full log if SHA-range query fails
            logger.debug("Support mode: falling back to recent commit scan")
    try:
        out, _, _ = run_cmd(
            ["git", "log", "--oneline", f"-{limit}"],
            cwd=repo_root,
            check=True,
        )
        return [line for line in out.splitlines() if line.strip()]
    except (OSError, subprocess.CalledProcessError) as exc:
        logger.warning("Support mode: unable to read git log: %s", exc)
        return []


def _limit(items: list[str], max_items: int = MAX_ITEMS) -> tuple[list[str], int]:
    """Limit items to max_items, returning items and extra count."""
    if len(items) <= max_items:
        return items, 0
    return items[:max_items], len(items) - max_items


def run_support_mode(repo_root: Path, prd_path: Path, poll_seconds: int) -> None:
    """Run continuous support mode monitoring loop.

    Args:
        repo_root: Repository root directory
        prd_path: Path to PRD markdown file
        poll_seconds: Polling interval in seconds
    """
    poll_seconds = max(MIN_POLL_SECONDS, poll_seconds or 0)
    print("=== Support Mode (continuous reviewer) ===", flush=True)
    print(f"-> Polling every {poll_seconds}s", flush=True)

    state = load_support_state(repo_root)
    iteration = state.iteration or 1

    while True:
        try:
            current_sha = git_head_sha(repo_root)
            current_branch = git_current_branch(repo_root)
            current_prd_hash = compute_prd_hash(prd_path) if prd_path.exists() else ""

            print(f"\n=== Iteration {iteration}: Support Review ===", flush=True)
            print(f"-> {current_branch} @ {current_sha[:7]}", flush=True)

            status = git_status_snapshot(repo_root)
            if status:
                print(
                    f"⚠️ Working tree has {len(status)} uncommitted change(s).",
                    flush=True,
                )

            commits = _recent_commits(
                repo_root, state.last_reviewed_sha, DEFAULT_RECENT_COMMITS
            )
            if commits:
                print("-> Recent commits:", flush=True)
                commit_lines, extra = _limit(commits)
                for line in commit_lines:
                    print(f"-> {line}", flush=True)
                if extra:
                    print(f"-> …and {extra} more", flush=True)
            else:
                print("-> No new commits since last review.", flush=True)

            issues: list[str] = []
            warnings: list[str] = []
            suggestions: list[str] = []
            info: list[str] = []

            tracker = load_tracker(repo_root)
            if tracker is None:
                issues.append(
                    "Tracker file not found at .aprd/tracker.json. "
                    "Support mode requires an existing tracker."
                )
            else:
                valid, errors = validate_tracker(tracker)
                if not valid:
                    issues.extend(errors)
                else:
                    state_issues = validate_tracker_state(tracker)
                    warnings.extend(state_issues)

                    raw_features = tracker.get("features", [])
                    if not isinstance(raw_features, list):
                        raw_features = []
                    features = [
                        {
                            **f,
                            "tasks": (
                                f.get("tasks")
                                if isinstance(f.get("tasks"), list)
                                else []
                            ),
                        }
                        for f in raw_features
                        if isinstance(f, dict)
                    ]
                    total_features = len(features)
                    total_tasks = sum(len(f.get("tasks", [])) for f in features)
                    completed_tasks = sum(
                        1
                        for f in features
                        for t in f.get("tasks", [])
                        if isinstance(t, dict) and t.get("status") == "completed"
                    )
                    tasks_left = total_tasks - completed_tasks
                    print(f"TASKS_LEFT={tasks_left}", flush=True)

                    info.append(
                        f"Tracker: {total_features} features, {total_tasks} tasks "
                        f"({completed_tasks} completed)"
                    )

                    stored_hash = tracker.get("metadata", {}).get("prd_hash", "")
                    if (
                        stored_hash
                        and current_prd_hash
                        and stored_hash != current_prd_hash
                    ):
                        warnings.append(
                            "PRD content hash differs from tracker metadata; scope may have drifted."
                        )

            if prd_path.exists():
                prd_content = prd_path.read_text(encoding="utf-8", errors="ignore")
                checkboxes = _extract_prd_checkboxes(prd_content)
                if checkboxes and tracker and valid:
                    tracker_texts = [
                        _normalize_text(t) for t in _collect_tracker_text(tracker)
                    ]
                    missing = []
                    for item in checkboxes:
                        normalized = _normalize_text(item)
                        if not normalized:
                            continue
                        covered = any(
                            normalized in t or t in normalized for t in tracker_texts
                        )
                        if not covered:
                            missing.append(item)
                    if missing:
                        suggestion_lines, extra = _limit(missing)
                        suggestions.append(
                            "PRD checkbox items not represented in tracker tasks: "
                            + "; ".join(suggestion_lines)
                            + (f" (and {extra} more)" if extra else "")
                        )
            else:
                warnings.append(
                    f"PRD file not found at '{prd_path}'; checkbox validation skipped."
                )

            try:
                diff_out, _, _ = run_cmd(
                    ["git", "diff", "--check"], cwd=repo_root, check=False
                )
                if diff_out.strip():
                    warnings.append(
                        "Whitespace/style issues detected (git diff --check)."
                    )
            except (OSError, subprocess.CalledProcessError) as exc:
                logger.warning("Support mode: git diff --check failed: %s", exc)

            vp = VerificationPersistence(repo_root)
            latest = vp.get_latest_run()
            if latest is None:
                warnings.append(
                    "No verification runs found; acceptance criteria may be unverified."
                )
            else:
                if latest.overall_status == VerificationStatus.FAILED:
                    warnings.append(
                        f"Latest verification run failed (run_id={latest.run_id})."
                    )
                if not vp.is_run_fresh(latest, current_prd_hash):
                    warnings.append(
                        "Latest verification run is stale for current HEAD/PRD."
                    )

            signs = load_guardrails(repo_root)
            info.append(f"Guardrails: {len(signs)} sign(s) on record.")

            for line in info:
                print(f"✓ {line}", flush=True)

            if issues:
                items, extra = _limit(issues)
                for line in items:
                    print(f"❌ {line}", flush=True)
                if extra:
                    print(f"❌ …and {extra} more issue(s)", flush=True)

            if warnings:
                items, extra = _limit(warnings)
                for line in items:
                    print(f"⚠️ {line}", flush=True)
                if extra:
                    print(f"⚠️ …and {extra} more warning(s)", flush=True)

            if suggestions:
                items, extra = _limit(suggestions)
                for line in items:
                    print(f"-> Suggestion: {line}", flush=True)
                if extra:
                    print(f"-> …and {extra} more suggestion(s)", flush=True)

            if not issues and not warnings:
                print("✓ Support review clean (no issues detected).", flush=True)

            iteration += 1
            state.iteration = iteration
            state.last_reviewed_sha = current_sha
            state.last_reviewed_prd_hash = current_prd_hash
            state.last_reviewed_at = datetime.now(timezone.utc).isoformat()
            save_support_state(repo_root, state)
            time.sleep(poll_seconds)
        except KeyboardInterrupt:
            print("\nSupport mode stopped.", flush=True)
            return
        except Exception as exc:
            logger.exception("Support mode iteration failed")
            print(f"❌ Support review crashed: {exc}", flush=True)
            # Backoff to prevent tight crash loops on deterministic errors
            time.sleep(poll_seconds)
