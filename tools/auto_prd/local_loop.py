"""Local iteration loop coordinating Codex and CodeRabbit."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from .agents import codex_exec, coderabbit_has_findings, coderabbit_prompt_only
from .constants import CODERABBIT_FINDINGS_CHAR_LIMIT, CODEX_READONLY_ERROR_MSG
from .git_ops import git_head_sha, git_status_snapshot
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
NO_CHANGES_ERROR = "Codex iterations produced no file changes or commits after multiple passes."


def should_stop_for_completion(
    done_by_checkboxes: bool,
    done_by_codex: bool,
    has_findings: bool,
    tasks_left: Optional[int],
) -> Tuple[bool, str]:
    if has_findings or not (done_by_checkboxes or done_by_codex):
        return False, ""
    if tasks_left is None and not done_by_checkboxes:
        return False, "Completion cannot be confirmed (no TASKS_LEFT and no checkboxes); continuing loop."
    return True, "Local loop stopping: PRD appears complete and CodeRabbit has no findings."


def orchestrate_local_loop(
    prd_path: Path,
    repo_root: Path,
    base_branch: str,
    max_iters: int,
    codex_model: str,
    allow_unsafe_execution: bool,
    dry_run: bool,
) -> Tuple[int, bool]:
    unchecked, total_checkboxes = checkbox_stats(prd_path)
    print(f"Unchecked checkboxes in PRD (heuristic): {unchecked}/{total_checkboxes}")
    tasks_left: Optional[int] = None
    appears_complete = False
    no_findings_streak = 0
    skipped_review_streak = 0
    qa_context_shared = False
    previous_status = git_status_snapshot(repo_root)
    previous_head = git_head_sha(repo_root)
    empty_change_streak = 0

    for i in range(1, max_iters + 1):
        print(f"\n=== Iteration {i}/{max_iters}: Codex implements next chunk ===")
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
        print("→ Launching implementation pass with", runner_name, "…")
        runner_kwargs = {
            "repo_root": repo_root,
            "enable_search": True,
            "allow_unsafe_execution": allow_unsafe_execution,
            "dry_run": dry_run,
        }
        if runner is codex_exec:
            runner_kwargs["model"] = codex_model

        impl_output = runner(impl_prompt, **runner_kwargs)
        print("✓ Codex implementation pass completed.")
        readonly_indicator = detect_readonly_block(impl_output)
        if readonly_indicator:
            raise RuntimeError(CODEX_READONLY_ERROR_MSG.format(pattern=readonly_indicator))
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

        repo_changed_before_review = status_after_impl != before_status or head_after_impl != before_head
        tasks_progress = (
            previous_tasks_left is not None
            and tasks_left is not None
            and tasks_left < previous_tasks_left
        )

        has_findings = False
        status_after_iteration = status_after_impl
        head_after_iteration = head_after_impl

        if not repo_changed_before_review and not tasks_progress:
            skipped_review_streak += 1
            print("No new file changes detected; skipping CodeRabbit review this iteration.")
            print(f"CodeRabbit skip streak: {skipped_review_streak}")
        else:
            print("\n=== CodeRabbit CLI review (prompt-only) ===")
            cr = coderabbit_prompt_only(base_branch=base_branch, repo_root=repo_root)
            has_findings = coderabbit_has_findings(cr)
            skipped_review_streak = 0
            if has_findings:
                no_findings_streak = 0
                print("\n=== Codex applies CodeRabbit findings ===")
                fix_prompt = f"""
You are fixing findings reported by CodeRabbit CLI:

<CODE_RABBIT_FINDINGS>
{cr[:CODERABBIT_FINDINGS_CHAR_LIMIT]}
</CODE_RABBIT_FINDINGS>

Apply targeted changes, commit frequently, and re-run the QA gates until green.

{LOCAL_QA_REMINDER}
"""
                print("→ Launching fix pass with", runner_name, "based on CodeRabbit feedback…")
                fix_output = runner(fix_prompt, **runner_kwargs)
                print("✓ Codex fix pass completed.")
                readonly_indicator = detect_readonly_block(fix_output)
                if readonly_indicator:
                    raise RuntimeError(CODEX_READONLY_ERROR_MSG.format(pattern=readonly_indicator))
                fix_tasks_left = parse_tasks_left(fix_output)
                if fix_tasks_left is not None:
                    tasks_left = fix_tasks_left
                    print(f"Codex reported TASKS_LEFT={tasks_left} after applying findings")
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

        repo_changed_after_actions = status_after_iteration != before_status or head_after_iteration != before_head

        unchecked, total_checkboxes = checkbox_stats(prd_path)
        done_by_checkboxes = total_checkboxes > 0 and unchecked == 0
        done_by_codex = tasks_left == 0 if tasks_left is not None else False

        should_stop, completion_msg = should_stop_for_completion(done_by_checkboxes, done_by_codex, has_findings, tasks_left)

        if not repo_changed_after_actions:
            if should_stop:
                print(completion_msg)
                appears_complete = True
                break
            if completion_msg != "":
                print(completion_msg)
            empty_change_streak += 1
            print("⚠️  Warning: no new workspace changes detected after this iteration.")
            print(f"Empty-change streak: {empty_change_streak}/{MAX_EMPTY_CHANGE_STREAK}")
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

    return tasks_left if tasks_left is not None else -1, appears_complete
