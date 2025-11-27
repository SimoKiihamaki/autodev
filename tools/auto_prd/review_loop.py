"""Review/fix loop management for PR feedback."""

from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Any, Optional

from .agents import codex_exec
from .checkpoint import save_checkpoint, update_phase_state
from .constants import CODERABBIT_FINDINGS_CHAR_LIMIT
from .gh_ops import (
    acknowledge_review_items,
    get_unresolved_feedback,
    should_stop_review_after_push,
    trigger_copilot,
)
from .git_ops import git_head_sha
from .logging_utils import logger
from .policy import policy_runner

JITTER_MIN_SECONDS = 0.0
JITTER_MAX_SECONDS = 3.0
_JITTER_RNG = random.Random()


def review_fix_loop(
    pr_number: Optional[int],
    owner_repo: str,
    repo_root: Path,
    idle_grace: int,
    poll_interval: int,
    codex_model: str,
    allow_unsafe_execution: bool = False,
    dry_run: bool = False,
    initial_wait_minutes: int = 0,
    infinite_reviews: bool = False,
    checkpoint: Optional[dict[str, Any]] = None,
) -> None:
    """Run the review/fix loop for a PR.

    Args:
        pr_number: The PR number.
        owner_repo: Owner/repo string.
        repo_root: Repository root directory.
        idle_grace: Idle grace period in minutes.
        poll_interval: Polling interval in seconds.
        codex_model: Codex model to use.
        allow_unsafe_execution: Allow unsafe execution.
        dry_run: If True, skip actual execution.
        initial_wait_minutes: Initial wait for bot reviews.
        infinite_reviews: Continue indefinitely while feedback exists.
        checkpoint: Optional checkpoint dict for resume support.
    """
    if pr_number is None:
        return
    if dry_run:
        logger.info("Dry run enabled; skipping review loop for PR #%s.", pr_number)
        return

    trigger_copilot(owner_repo, pr_number, repo_root)
    initial_wait_seconds = max(0, initial_wait_minutes * 60)
    if initial_wait_seconds:
        print(f"Waiting {initial_wait_minutes} minutes for bot reviews...", flush=True)
        time.sleep(initial_wait_seconds)

    idle_grace_seconds = max(0, idle_grace * 60)
    if infinite_reviews:
        idle_grace_seconds = float("inf")
    poll = max(15, poll_interval)
    last_activity = time.monotonic()
    print("\n=== Entering review/fix loop (continues while feedback exists) ===")

    # Track processed comment IDs - restore from checkpoint if resuming
    review_state = (
        checkpoint.get("phases", {}).get("review_fix", {}) if checkpoint else {}
    )
    processed_comment_ids: set[int] = set(review_state.get("processed_comment_ids", []))
    cycles = review_state.get("cycles", 0)

    if processed_comment_ids:
        logger.info(
            "Resumed with %d previously processed comment IDs",
            len(processed_comment_ids),
        )
        print(
            f"Resuming with {len(processed_comment_ids)} previously processed comments."
        )

    def sleep_with_jitter(base: float) -> None:
        jitter = _JITTER_RNG.uniform(JITTER_MIN_SECONDS, JITTER_MAX_SECONDS)
        duration = max(1.0, base + jitter)
        time.sleep(duration)

    while True:
        current_head = git_head_sha(repo_root)
        unresolved_raw = get_unresolved_feedback(owner_repo, pr_number, current_head)
        unresolved = []
        for item in unresolved_raw:
            comment_id = item.get("comment_id")
            if isinstance(comment_id, int) and comment_id in processed_comment_ids:
                continue
            unresolved.append(item)
        if unresolved:
            bullets = format_unresolved_bullets(
                unresolved, CODERABBIT_FINDINGS_CHAR_LIMIT
            )
            print(
                "\nUnresolved feedback detected, asking the bot to fix...", flush=True
            )
            fix_prompt = f"""
Resolve ALL items below, commit fixes, ensure QA passes, and push to the SAME PR (do not create a new one).
Before every push, run `make ci` locally and confirm it succeeds; only push after `make ci` passes cleanly.
Tag the relevant code areas and keep changes minimal.

Unresolved review items:
{bullets}

After pushing, print: REVIEW_FIXES_PUSHED=YES
"""
            review_runner, _ = policy_runner(None, phase="review_fix")

            runner_kwargs = {
                "repo_root": repo_root,
                "enable_search": True,
                "allow_unsafe_execution": allow_unsafe_execution,
                "dry_run": dry_run,
            }
            if review_runner is codex_exec:
                runner_kwargs["model"] = codex_model

            try:
                _, _ = review_runner(
                    fix_prompt, **runner_kwargs
                )  # returns tuple[str, str]
            except Exception:  # pragma: no cover - best-effort resilience
                logger.exception("Review runner failed")
                sleep_with_jitter(float(poll))
                continue
            trigger_copilot(owner_repo, pr_number, repo_root)
            acknowledge_review_items(
                owner_repo, pr_number, unresolved, processed_comment_ids
            )

            # Persist checkpoint with updated processed comment IDs
            cycles += 1
            if checkpoint:
                update_phase_state(
                    checkpoint,
                    "review_fix",
                    {
                        "processed_comment_ids": list(processed_comment_ids),
                        "cycles": cycles,
                        "last_activity_time": time.monotonic(),
                    },
                )
                save_checkpoint(checkpoint)
                logger.debug(
                    "Saved review checkpoint: %d comments processed, cycle %d",
                    len(processed_comment_ids),
                    cycles,
                )

            last_activity = time.monotonic()
            sleep_with_jitter(float(poll))
            continue

        if should_stop_review_after_push(
            owner_repo, pr_number, current_head, repo_root
        ):
            print("Automatic reviewers report no new findings; stopping.")
            break

        if idle_grace_seconds == 0:
            print("No unresolved feedback; stopping.")
            break
        elapsed = time.monotonic() - last_activity
        if elapsed >= idle_grace_seconds:
            minutes = "∞" if infinite_reviews else idle_grace
            print(f"No unresolved feedback for {minutes} minutes; finishing.")
            break
        print("No unresolved feedback right now; waiting for potential new comments...")
        sleep_with_jitter(float(poll))
    print("Review loop complete.")


def format_unresolved_bullets(unresolved: list[dict], limit: int) -> str:
    lines: list[str] = []
    for entry in unresolved:
        summary = entry.get("summary")
        if not isinstance(summary, str):
            continue
        lines.append(f"* {summary.strip()}")
    text = "\n".join(lines)
    if len(text) <= limit:
        return text
    truncated = text[:limit]
    boundary = max(truncated.rfind("\n* "), truncated.rfind("\n- "))
    if boundary <= 0:
        boundary = truncated.rfind("\n")
    if boundary <= 0:
        return text[:limit] + "\n* (truncated; see remaining items in GitHub)"
    trimmed = truncated[:boundary].rstrip()
    return trimmed + "\n* (truncated; see remaining items in GitHub)"
