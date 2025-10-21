"""Review/fix loop management for PR feedback."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from .gh_ops import acknowledge_review_items, get_unresolved_feedback, trigger_copilot
from .git_ops import git_head_sha
from .logging_utils import logger
from .policy import EXECUTOR_POLICY, policy_runner


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
) -> None:
    if pr_number is None:
        return
    if dry_run:
        logger.info("Dry run enabled; skipping review loop for PR #%s.", pr_number)
        return

    trigger_copilot(owner_repo, pr_number, repo_root)
    initial_wait_seconds = max(0, initial_wait_minutes * 60)
    if initial_wait_seconds:
        print(f"Waiting {initial_wait_minutes} minutes for bot reviews...")
        time.sleep(initial_wait_seconds)

    idle_grace_seconds = max(0, idle_grace * 60)
    if infinite_reviews:
        idle_grace_seconds = float("inf")
    poll = max(15, poll_interval)
    last_activity = time.time()
    print("\n=== Entering review/fix loop (continues while feedback exists) ===")

    processed_comment_ids: set[int] = set()

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
            bullets = "\n".join(f"* {u['summary']}" for u in unresolved)
            print("\nUnresolved feedback detected, asking the bot to fix...")
            fix_prompt = f"""
Resolve ALL items below, commit fixes, ensure QA passes, and push to the SAME PR (do not create a new one).
Before every push, run `make ci` locally and confirm it succeeds; only push after `make ci` passes cleanly.
Tag the relevant code areas and keep changes minimal.

Unresolved review items:
{bullets[:20000]}

After pushing, print: REVIEW_FIXES_PUSHED=YES
"""
            review_runner, _ = policy_runner(EXECUTOR_POLICY, phase="review_fix")

            review_runner(
                fix_prompt,
                repo_root,
                model=codex_model,
                enable_search=True,
                yolo=allow_unsafe_execution,
                allow_unsafe_execution=allow_unsafe_execution,
            )
            trigger_copilot(owner_repo, pr_number, repo_root)
            processed_comment_ids = acknowledge_review_items(owner_repo, pr_number, unresolved, processed_comment_ids)
            last_activity = time.time()
            time.sleep(poll)
            continue

        if idle_grace_seconds == 0:
            print("No unresolved feedback; stopping.")
            break
        elapsed = time.time() - last_activity
        if elapsed >= idle_grace_seconds:
            minutes = "∞" if infinite_reviews else idle_grace
            print(f"No unresolved feedback for {minutes} minutes; finishing.")
            break
        print("No unresolved feedback right now; waiting for potential new comments...")
        time.sleep(poll)

    print("Review loop complete.")
