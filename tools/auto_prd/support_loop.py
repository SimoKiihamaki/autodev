from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .command import run_cmd
from .git_ops import git_current_branch, git_head_sha, git_status_snapshot
from .guardrails import load_guardrails
from .logging_utils import logger
from .tracker_generator import compute_prd_hash, load_tracker, validate_tracker
from .tracker_validator import validate_tracker_state
from .verification_persistence import VerificationPersistence, VerificationStatus

STATE_FILENAME = "support_state.json"
MAX_ITEMS = 8
DEFAULT_RECENT_COMMITS = 8
MIN_POLL_SECONDS = 5


@dataclass
class SupportState:
    iteration: int = 1
    last_reviewed_sha: str = ""
    last_reviewed_prd_hash: str = ""
    last_reviewed_at: str = ""


def _state_path(repo_root: Path) -> Path:
    return repo_root / ".aprd" / STATE_FILENAME


def load_support_state(repo_root: Path) -> SupportState:
    path = _state_path(repo_root)
    if not path.exists():
        return SupportState()
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return SupportState()
    return SupportState(
        iteration=int(data.get("iteration", 1) or 1),
        last_reviewed_sha=str(data.get("last_reviewed_sha", "") or ""),
        last_reviewed_prd_hash=str(data.get("last_reviewed_prd_hash", "") or ""),
        last_reviewed_at=str(data.get("last_reviewed_at", "") or ""),
    )


def save_support_state(repo_root: Path, state: SupportState) -> None:
    path = _state_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(state)
    path.write_text(json.dumps(payload, indent=2))


def _normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _extract_prd_checkboxes(prd_content: str) -> list[str]:
    items = []
    pattern = re.compile(r"^\s*[-*]\s+\[( |x|X)\]\s+(.*)$")
    for line in prd_content.splitlines():
        match = pattern.match(line)
        if match:
            item = match.group(2).strip()
            if item:
                items.append(item)
    return items


def _collect_tracker_text(tracker: dict[str, Any]) -> list[str]:
    texts = []
    for feature in tracker.get("features", []):
        for key in ("name", "description"):
            val = feature.get(key)
            if isinstance(val, str) and val.strip():
                texts.append(val)
        for task in feature.get("tasks", []):
            desc = task.get("description")
            if isinstance(desc, str) and desc.strip():
                texts.append(desc)
    return texts


def _recent_commits(repo_root: Path, last_sha: str, limit: int) -> list[str]:
    if last_sha:
        try:
            out, _, _ = run_cmd(
                ["git", "log", "--oneline", f"{last_sha}..HEAD"],
                cwd=repo_root,
                check=True,
            )
            lines = [line for line in out.splitlines() if line.strip()]
            return lines
        except Exception:
            logger.debug("Support mode: falling back to recent commit scan")
    out, _, _ = run_cmd(
        ["git", "log", "--oneline", f"-{limit}"],
        cwd=repo_root,
        check=True,
    )
    return [line for line in out.splitlines() if line.strip()]


def _limit(items: list[str], max_items: int = MAX_ITEMS) -> tuple[list[str], int]:
    if len(items) <= max_items:
        return items, 0
    return items[:max_items], len(items) - max_items


def run_support_mode(repo_root: Path, prd_path: Path, poll_seconds: int) -> None:
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
            if not tracker:
                issues.append(
                    "Tracker not found at .aprd/tracker.json. Generate it from the PRD."
                )
            else:
                valid, errors = validate_tracker(tracker)
                if not valid:
                    issues.extend(errors)

                state_issues = validate_tracker_state(tracker)
                warnings.extend(state_issues)

                features = tracker.get("features", [])
                total_features = len(features)
                total_tasks = sum(len(f.get("tasks", [])) for f in features)
                completed_tasks = sum(
                    1
                    for f in features
                    for t in f.get("tasks", [])
                    if t.get("status") == "completed"
                )
                tasks_left = total_tasks - completed_tasks
                print(f"TASKS_LEFT={tasks_left}", flush=True)

                info.append(
                    f"Tracker: {total_features} features, {total_tasks} tasks "
                    f"({completed_tasks} completed)"
                )

                summary = tracker.get("validation_summary", {})
                if summary:
                    expected_features = summary.get("total_features")
                    expected_tasks = summary.get("total_tasks")
                    if (
                        isinstance(expected_features, int)
                        and expected_features != total_features
                    ):
                        warnings.append(
                            f"validation_summary.total_features={expected_features} but tracker has {total_features} feature(s)."
                        )
                    if (
                        isinstance(expected_tasks, int)
                        and expected_tasks != total_tasks
                    ):
                        warnings.append(
                            f"validation_summary.total_tasks={expected_tasks} but tracker has {total_tasks} task(s)."
                        )

                stored_hash = tracker.get("metadata", {}).get("prd_hash", "")
                if stored_hash and current_prd_hash and stored_hash != current_prd_hash:
                    warnings.append(
                        "PRD content hash differs from tracker metadata; scope may have drifted."
                    )

                stored_source = tracker.get("metadata", {}).get("prd_source", "")
                if stored_source and prd_path and stored_source != str(prd_path):
                    warnings.append(
                        f"Tracker prd_source='{stored_source}' does not match selected PRD '{prd_path}'."
                    )

                feature_by_id = {f.get("id"): f for f in features}
                for feature in features:
                    feature_id = feature.get("id", "?")
                    deps = feature.get("dependencies", []) or []
                    if deps:
                        unresolved = []
                        missing = []
                        for dep in deps:
                            dep_feature = feature_by_id.get(dep)
                            if not dep_feature:
                                missing.append(dep)
                                continue
                            if dep_feature.get("status") not in (
                                "completed",
                                "verified",
                            ):
                                unresolved.append(dep)
                        if missing:
                            warnings.append(
                                f"Feature {feature_id} depends on missing feature(s): {', '.join(missing)}."
                            )
                        if unresolved and feature.get("status") in (
                            "in_progress",
                            "completed",
                            "verified",
                        ):
                            warnings.append(
                                f"Feature {feature_id} is {feature.get('status')} but dependencies incomplete: {', '.join(unresolved)}."
                            )

                    criteria = feature.get("acceptance_criteria", []) or []
                    if not criteria:
                        warnings.append(
                            f"Feature {feature_id} has no acceptance criteria."
                        )
                    else:
                        seen = set()
                        dupes = 0
                        for criterion in criteria:
                            text = criterion.get("criterion", "")
                            key = _normalize_text(text)
                            if key:
                                if key in seen:
                                    dupes += 1
                                else:
                                    seen.add(key)
                        if dupes:
                            warnings.append(
                                f"Feature {feature_id} has {dupes} duplicate acceptance criteria entries."
                            )

                    if feature.get("status") in ("completed", "verified"):
                        pending = [
                            c
                            for c in criteria
                            if c.get("status", "pending") != "passed"
                        ]
                        if pending:
                            warnings.append(
                                f"Feature {feature_id} marked {feature.get('status')} but {len(pending)} acceptance criteria are not passed."
                            )

                    for task in feature.get("tasks", []):
                        task_id = task.get("id", "?")
                        status = task.get("status", "")
                        blockers = task.get("blockers") or []
                        if status == "blocked" and not blockers:
                            warnings.append(
                                f"Task {task_id} is blocked but has no blockers listed."
                            )
                        if status != "blocked" and blockers:
                            warnings.append(
                                f"Task {task_id} has blockers but status is {status}."
                            )
                        if status == "completed" and not task.get("completed_at"):
                            warnings.append(
                                f"Task {task_id} completed without completed_at timestamp."
                            )

                if prd_path.exists():
                    prd_content = prd_path.read_text(encoding="utf-8", errors="ignore")
                    checkboxes = _extract_prd_checkboxes(prd_content)
                    if checkboxes:
                        tracker_texts = [
                            _normalize_text(t) for t in _collect_tracker_text(tracker)
                        ]
                        missing = []
                        for item in checkboxes:
                            normalized = _normalize_text(item)
                            if not normalized:
                                continue
                            covered = any(
                                normalized in t or t in normalized
                                for t in tracker_texts
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

            try:
                diff_out, _, _ = run_cmd(
                    ["git", "diff", "--check"], cwd=repo_root, check=False
                )
                if diff_out.strip():
                    warnings.append(
                        "Whitespace/style issues detected (git diff --check)."
                    )
            except Exception:
                logger.debug("Support mode: git diff --check failed")

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
                if not vp.is_run_fresh(latest):
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

            state.iteration = iteration + 1
            state.last_reviewed_sha = current_sha
            state.last_reviewed_prd_hash = current_prd_hash
            state.last_reviewed_at = datetime.now(timezone.utc).isoformat()
            save_support_state(repo_root, state)

            iteration += 1
            time.sleep(poll_seconds)
        except KeyboardInterrupt:
            print("\nSupport mode stopped.", flush=True)
            return
        except Exception as exc:
            logger.exception("Support mode iteration failed")
            print(f"❌ Support review crashed: {exc}", flush=True)
            time.sleep(poll_seconds)
