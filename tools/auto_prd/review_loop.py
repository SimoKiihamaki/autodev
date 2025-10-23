"""Review/fix loop management for PR feedback."""

from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Optional

from .gh_ops import acknowledge_review_items, get_unresolved_feedback, trigger_copilot
from .git_ops import git_head_sha
from .logging_utils import logger
from .policy import policy_runner

JITTER_MIN_SECONDS = 0.0
JITTER_MAX_SECONDS = 3.0


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

    # Track processed comment IDs locally so we can inject deterministic state during tests
    # and avoid relying on hidden module globals. TODO: consider persisting across runs to
    # prevent duplicate acknowledgements after restarts.
    processed_comment_ids: set[int] = set()

    def sleep_with_jitter(base: float) -> None:
        jitter = random.uniform(JITTER_MIN_SECONDS, JITTER_MAX_SECONDS)  # nosec S311 - non-crypto jitter
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
            review_runner, _ = policy_runner(None, phase="review_fix")

            review_runner(
                fix_prompt,
                repo_root,
                model=codex_model,
                enable_search=True,
                allow_unsafe_execution=allow_unsafe_execution,
            )
            trigger_copilot(owner_repo, pr_number, repo_root)
            processed_comment_ids = acknowledge_review_items(owner_repo, pr_number, unresolved, processed_comment_ids)
            last_activity = time.time()
            sleep_with_jitter(float(poll))
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
        sleep_with_jitter(float(poll))
    print("Review loop complete.")
