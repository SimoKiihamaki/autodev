"""Local iteration loop coordinating implementation agents and CodeRabbit.

This module orchestrates the local implementation phase, running either Codex or
Claude (based on policy configuration) to implement features, with CodeRabbit
providing automated code review feedback between iterations.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .agents import (
    claude_exec,
    coderabbit_has_findings,
    coderabbit_prompt_only,
    codex_exec,
)
from .checkpoint import save_checkpoint, update_phase_state
from .command import CalledProcessError, TimeoutExpired
from .constants import (
    CODERABBIT_FINDINGS_CHAR_LIMIT,
    CODEX_READONLY_ERROR_MSG,
    get_tool_allowlist,
)
from .git_ops import git_head_sha, git_status_snapshot
from .logging_utils import logger
from .policy import policy_runner
from .utils import checkbox_stats, detect_readonly_block, parse_tasks_left

LOCAL_QA_SNIPPET = """
Use zsh for shell commands.
Run `make ci` (or create the Makefile above if missing) and keep rerunning until green.
CI expectations: unit + e2e tests, lint, typecheck, format check.
Commit frequently with Conventional Commits, include rationale and test notes.
Keep the PRD in sync (checkboxes, remaining tasks) and finish with TASKS_LEFT=<N>.
"""

LOCAL_QA_REMINDER = "Remember the QA SOP from your first pass: `make ci` must be green; rerun as needed."

NO_FINDINGS_STREAK_LIMIT = 2
MAX_EMPTY_CHANGE_STREAK = 3
NO_CHANGES_ERROR = (
    "Codex iterations produced no file changes or commits after multiple passes."
)

# Retry configuration for implementation passes.
# MAX_IMPL_RETRIES=2 provides 3 total attempts (initial + 2 retries), balancing
# resilience against transient failures with reasonable total runtime.
MAX_IMPL_RETRIES = 2

# Base delay for exponential backoff between retries (seconds).
# Uses formula: IMPL_RETRY_BACKOFF_BASE * (2**attempt) for delays of 10s, 20s.
IMPL_RETRY_BACKOFF_BASE = 10

# Exit codes that indicate non-retryable conditions.
# 126: Command not executable (permission denied)
# 127: Command not found
# 137: Process killed by SIGKILL (often OOM)
# 139: Segmentation fault (SIGSEGV)
NON_RETRYABLE_EXIT_CODES = frozenset({126, 127, 137, 139})


def should_stop_for_completion(
    done_by_checkboxes: bool,
    done_by_codex: bool,
    has_findings: bool,
    tasks_left: int | None,
) -> tuple[bool, str]:
    if has_findings or not (done_by_checkboxes or done_by_codex):
        return False, ""
    if tasks_left is None and not done_by_checkboxes:
        return (
            False,
            "Completion cannot be confirmed (no TASKS_LEFT and no checkboxes); continuing loop.",
        )
    return (
        True,
        "Local loop stopping: PRD appears complete and CodeRabbit has no findings.",
    )


def orchestrate_local_loop(
    prd_path: Path,
    repo_root: Path,
    base_branch: str,
    max_iters: int,
    codex_model: str,
    allow_unsafe_execution: bool,
    dry_run: bool,
    checkpoint: dict[str, Any] | None = None,
) -> tuple[int, bool]:
    """Orchestrate the local Codex/CodeRabbit iteration loop.

    Args:
        prd_path: Path to the PRD file.
        repo_root: Repository root directory.
        base_branch: Base branch for CodeRabbit comparison.
        max_iters: Maximum number of iterations.
        codex_model: Codex model to use.
        allow_unsafe_execution: Allow unsafe execution mode.
        dry_run: If True, skip actual execution.
        checkpoint: Optional checkpoint dict for resume support.

    Returns:
        Tuple of (tasks_left, appears_complete).
    """
    unchecked, total_checkboxes = checkbox_stats(prd_path)
    print(f"Unchecked checkboxes in PRD (heuristic): {unchecked}/{total_checkboxes}")

    # Initialize state - restore from checkpoint if resuming
    # Defensive checks for potentially corrupted or missing checkpoint data
    local_state: dict = {}
    if (
        checkpoint
        and isinstance(checkpoint, dict)
        and "phases" in checkpoint
        and isinstance(checkpoint.get("phases"), dict)
        and "local" in checkpoint["phases"]
        and isinstance(checkpoint["phases"].get("local"), dict)
    ):
        local_state = checkpoint["phases"]["local"]

    start_iteration = (
        local_state.get("iteration", 0) + 1
        if local_state.get("status") == "in_progress"
        else 1
    )

    # Restore tasks_left from checkpoint if present.
    # Use explicit key check to distinguish between:
    # - Key missing: no checkpoint data (tasks_left = None)
    # - Key present with value >= 0: valid task count
    # - Key present with value -1: sentinel for "no tasks_left reported"
    tasks_left: int | None
    if "tasks_left" in local_state:
        stored_tasks_left = local_state["tasks_left"]
        tasks_left = stored_tasks_left if stored_tasks_left >= 0 else None
    else:
        tasks_left = None
    appears_complete = False
    no_findings_streak = local_state.get("no_findings_streak", 0)
    skipped_review_streak = local_state.get("skipped_review_streak", 0)
    qa_context_shared = local_state.get("qa_context_shared", False)
    empty_change_streak = local_state.get("empty_change_streak", 0)

    # Get current git state
    previous_status = git_status_snapshot(repo_root)
    previous_head = git_head_sha(repo_root)

    # If resuming, restore from checkpoint state if available
    if start_iteration > 1:
        logger.info("Resuming local loop from iteration %d", start_iteration)
        print(
            f"Resuming from iteration {start_iteration} (streaks: empty={empty_change_streak}, no_findings={no_findings_streak})"
        )

    # Handle edge case where start_iteration exceeds max_iters explicitly.
    if start_iteration > max_iters:
        logger.warning(
            "Start iteration (%d) exceeds max_iters (%d); no iterations will be performed.",
            start_iteration,
            max_iters,
        )
        return tasks_left if tasks_left is not None else -1, appears_complete

    for i in range(start_iteration, max_iters + 1):
        print(
            f"\n=== Iteration {i}/{max_iters}: Codex implements next chunk ===",
            flush=True,
        )
        previous_tasks_left = tasks_left
        before_status = previous_status
        before_head = previous_head

        qa_section = LOCAL_QA_SNIPPET if not qa_context_shared else LOCAL_QA_REMINDER
        impl_prompt = f"""
Read the spec at '{prd_path}'. Implement the NEXT uncompleted tasks in '{repo_root}'.

{qa_section}

At the end, print: TASKS_LEFT=<N>
"""
        runner, runner_name = policy_runner(None, i=i, phase="implement")
        print("→ Launching implementation pass with", runner_name, "…", flush=True)
        runner_kwargs: dict[str, Any] = {
            "repo_root": repo_root,
            "enable_search": True,
            "allow_unsafe_execution": allow_unsafe_execution,
            "dry_run": dry_run,
        }
        if runner is codex_exec:
            runner_kwargs["model"] = codex_model
        elif runner is claude_exec:
            # Add phase-specific tool restrictions for Claude
            runner_kwargs["allowed_tools"] = get_tool_allowlist("implement")

        # Implementation pass with retry logic for transient failures.
        # Retries on CalledProcessError and TimeoutExpired which may include transient
        # failures (rate limits, network issues). Non-retryable exit codes (126, 127,
        # 137, 139) skip retries to avoid wasting time on permanent failures.
        impl_output = ""
        last_impl_error: CalledProcessError | TimeoutExpired | None = None
        for impl_attempt in range(MAX_IMPL_RETRIES + 1):
            try:
                impl_output, _ = runner(impl_prompt, **runner_kwargs)
                last_impl_error = None
                break
            except (CalledProcessError, TimeoutExpired) as e:
                last_impl_error = e
                exit_code = getattr(e, "returncode", -1)
                is_timeout = isinstance(e, TimeoutExpired)
                error_type = (
                    "timed out" if is_timeout else f"failed (exit code {exit_code})"
                )

                # Don't retry non-retryable exit codes
                if not is_timeout and exit_code in NON_RETRYABLE_EXIT_CODES:
                    logger.error(
                        "%s implementation pass %s; not retrying (non-retryable exit code)",
                        runner_name,
                        error_type,
                    )
                    print(
                        f"  ❌  {runner_name} {error_type}. "
                        "This exit code indicates a configuration or system issue.",
                        flush=True,
                    )
                    break

                if impl_attempt < MAX_IMPL_RETRIES:
                    wait_time = IMPL_RETRY_BACKOFF_BASE * (2**impl_attempt)
                    logger.warning(
                        "%s implementation pass %s (attempt %d/%d); retrying in %ds",
                        runner_name,
                        error_type,
                        impl_attempt + 1,
                        MAX_IMPL_RETRIES + 1,
                        wait_time,
                    )
                    print(
                        f"  ⚠️  {runner_name} {error_type}. "
                        f"Retrying in {wait_time}s "
                        f"(attempt {impl_attempt + 1}/{MAX_IMPL_RETRIES + 1})…",
                        flush=True,
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(
                        "%s implementation pass %s after %d attempts",
                        runner_name,
                        error_type,
                        MAX_IMPL_RETRIES + 1,
                    )
                    print(
                        f"  ❌  {runner_name} implementation {error_type} after "
                        f"{MAX_IMPL_RETRIES + 1} attempts.",
                        flush=True,
                    )

        # Re-raise if all retries exhausted for implementation (critical path).
        # Implementation failures halt the pipeline because without successful
        # implementation, there is no code to review or fix. In contrast, fix pass
        # failures (see below) are non-fatal because the implementation already
        # exists and the loop can continue with potentially incomplete fixes.
        if last_impl_error is not None:
            raise last_impl_error

        # Check for empty output which may indicate the runner failed silently
        if not impl_output.strip():
            logger.warning(
                "%s returned empty output during implementation pass; "
                "implementation may not have completed",
                runner_name,
            )
            print(
                f"  ⚠️  Warning: {runner_name} returned no output during implementation pass. "
                "Results may be incomplete.",
                flush=True,
            )
        else:
            print(f"✓ {runner_name} implementation pass completed.", flush=True)
        readonly_indicator = detect_readonly_block(impl_output)
        if readonly_indicator:
            raise RuntimeError(
                CODEX_READONLY_ERROR_MSG.format(pattern=readonly_indicator)
            )
        iter_tasks_left = parse_tasks_left(impl_output)
        if iter_tasks_left is not None:
            tasks_left = iter_tasks_left
            print(f"Codex reported TASKS_LEFT={tasks_left}")
        else:
            print("Codex did not report TASKS_LEFT (continuing)")

        qa_context_shared = True

        if not dry_run:
            status_after_impl = git_status_snapshot(repo_root)
            head_after_impl = git_head_sha(repo_root)
        else:
            status_after_impl = before_status
            head_after_impl = before_head

        repo_changed_before_review = (
            status_after_impl != before_status or head_after_impl != before_head
        )
        tasks_progress = (
            previous_tasks_left is not None
            and tasks_left is not None
            and tasks_left < previous_tasks_left
        )

        has_findings = False
        fix_pass_failed = False  # Track if fix pass was attempted but failed
        status_after_iteration = status_after_impl
        head_after_iteration = head_after_impl

        if not repo_changed_before_review and not tasks_progress:
            skipped_review_streak += 1
            print(
                "No new file changes detected; skipping CodeRabbit review this iteration."
            )
            print(f"CodeRabbit skip streak: {skipped_review_streak}")
        else:
            print("\n=== CodeRabbit CLI review (prompt-only) ===", flush=True)
            cr = coderabbit_prompt_only(base_branch=base_branch, repo_root=repo_root)
            has_findings = coderabbit_has_findings(cr)
            skipped_review_streak = 0
            if has_findings:
                no_findings_streak = 0
                print("\n=== Codex applies CodeRabbit findings ===", flush=True)
                fix_prompt = f"""
You are fixing findings reported by CodeRabbit CLI:

<CODE_RABBIT_FINDINGS>
{cr[:CODERABBIT_FINDINGS_CHAR_LIMIT]}
</CODE_RABBIT_FINDINGS>

Apply targeted changes, commit frequently, and re-run the QA gates until green.

{LOCAL_QA_REMINDER}
"""
                print(
                    "→ Launching fix pass with",
                    runner_name,
                    "based on CodeRabbit feedback…",
                    flush=True,
                )
                # Use "fix" phase tool restrictions for the fix pass.
                # Note: No retry logic here - fix pass failures are non-fatal (see below),
                # so retrying would add latency without meaningful benefit.
                fix_kwargs = runner_kwargs.copy()
                if runner is claude_exec:
                    fix_kwargs["allowed_tools"] = get_tool_allowlist("fix")
                try:
                    fix_output, _ = runner(fix_prompt, **fix_kwargs)
                except (CalledProcessError, TimeoutExpired) as e:
                    # Fix pass failures are non-fatal - log and continue.
                    # Rationale: The implementation has already succeeded at this point,
                    # so we have working code. CodeRabbit fixes are quality improvements,
                    # not correctness requirements. Failing to apply fixes is acceptable;
                    # the iteration can continue and potentially address issues in
                    # subsequent passes or during PR review.
                    fix_pass_failed = True
                    exit_code = getattr(e, "returncode", -1)
                    is_timeout = isinstance(e, TimeoutExpired)
                    error_type = "timed out" if is_timeout else f"exit code {exit_code}"
                    logger.warning(
                        "%s fix pass failed (%s); CodeRabbit findings will NOT be "
                        "addressed this iteration",
                        runner_name,
                        error_type,
                    )
                    print(
                        f"  ⚠️  Warning: {runner_name} fix pass failed ({error_type}). "
                        "CodeRabbit findings will NOT be addressed this iteration.",
                        flush=True,
                    )
                    fix_output = ""
                # Check for empty output which may indicate the runner failed silently
                if not fix_output.strip():
                    logger.warning(
                        "%s returned empty output during fix pass; "
                        "fixes may not have been applied",
                        runner_name,
                    )
                    print(
                        f"  ⚠️  Warning: {runner_name} returned no output during fix pass. "
                        "Results may be incomplete.",
                        flush=True,
                    )
                else:
                    print(f"✓ {runner_name} fix pass completed.", flush=True)
                readonly_indicator = detect_readonly_block(fix_output)
                if readonly_indicator:
                    raise RuntimeError(
                        CODEX_READONLY_ERROR_MSG.format(pattern=readonly_indicator)
                    )
                fix_tasks_left = parse_tasks_left(fix_output)
                if fix_tasks_left is not None:
                    tasks_left = fix_tasks_left
                    print(
                        f"Codex reported TASKS_LEFT={tasks_left} after applying findings"
                    )
                if not dry_run:
                    status_after_iteration = git_status_snapshot(repo_root)
                    head_after_iteration = git_head_sha(repo_root)
            else:
                no_findings_streak += 1
                if not dry_run:
                    status_after_iteration = git_status_snapshot(repo_root)
                    head_after_iteration = git_head_sha(repo_root)
                print("No CodeRabbit findings detected in this pass.")
                print(f"CodeRabbit no-findings streak: {no_findings_streak}")

        repo_changed_after_actions = (
            status_after_iteration != before_status
            or head_after_iteration != before_head
        )

        unchecked, total_checkboxes = checkbox_stats(prd_path)
        done_by_checkboxes = total_checkboxes > 0 and unchecked == 0
        done_by_codex = tasks_left == 0 if tasks_left is not None else False

        should_stop, completion_msg = should_stop_for_completion(
            done_by_checkboxes, done_by_codex, has_findings, tasks_left
        )

        # Save checkpoint after each iteration
        if checkpoint:
            update_phase_state(
                checkpoint,
                "local",
                {
                    "status": "in_progress",
                    "iteration": i,
                    "tasks_left": tasks_left if tasks_left is not None else -1,
                    "no_findings_streak": no_findings_streak,
                    "empty_change_streak": empty_change_streak,
                    "skipped_review_streak": skipped_review_streak,
                    "qa_context_shared": qa_context_shared,
                    "last_head_sha": head_after_iteration,
                    "last_status_snapshot": list(status_after_iteration),
                    "fix_pass_failed": fix_pass_failed,
                },
            )
            save_checkpoint(checkpoint)
            logger.debug("Saved checkpoint at iteration %d", i)

        if not repo_changed_after_actions:
            if should_stop:
                print(completion_msg)
                appears_complete = True
                break
            if completion_msg != "":
                print(completion_msg)
            empty_change_streak += 1
            print("⚠️  Warning: no new workspace changes detected after this iteration.")
            print(
                f"Empty-change streak: {empty_change_streak}/{MAX_EMPTY_CHANGE_STREAK}"
            )
            if not dry_run and empty_change_streak >= MAX_EMPTY_CHANGE_STREAK:
                raise RuntimeError(NO_CHANGES_ERROR)
            continue
        else:
            empty_change_streak = 0
            previous_status = status_after_iteration
            previous_head = head_after_iteration
        if should_stop:
            print(completion_msg)
            appears_complete = True
            break
        if completion_msg != "":
            print(completion_msg)
            continue

        if no_findings_streak >= NO_FINDINGS_STREAK_LIMIT and not has_findings:
            print("Stopping after repeated no-finding reviews from CodeRabbit.")
            appears_complete = True
            break
    else:
        print("Reached local iteration cap, proceeding to PR step.")

    # Mark checkpoint as completed when local loop finishes successfully.
    # 'i' is always defined here because:
    # - The edge case (start_iteration > max_iters) returns early before reaching this code.
    # - Otherwise, the loop runs at least once, defining 'i'.
    if checkpoint:
        update_phase_state(
            checkpoint,
            "local",
            {
                "status": "completed",
                "iteration": i,
                "tasks_left": tasks_left if tasks_left is not None else -1,
                "no_findings_streak": no_findings_streak,
                "empty_change_streak": empty_change_streak,
                "skipped_review_streak": skipped_review_streak,
                "qa_context_shared": qa_context_shared,
            },
        )
        save_checkpoint(checkpoint)
        logger.debug("Marked local phase as completed")

    return tasks_left if tasks_left is not None else -1, appears_complete
