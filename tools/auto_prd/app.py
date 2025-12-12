from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Optional

from .checkpoint import (
    create_checkpoint,
    generate_session_id,
    mark_phase_complete,
    mark_phase_started,
    mark_session_complete,
    save_checkpoint,
    update_phase_state,
)
from .command import ensure_claude_debug_dir, register_safe_cwd, run_cmd
from .constants import DEFAULT_LOG_DIR_NAME, PHASES_WITH_COMMIT_RISK, VALID_PHASES
from .gh_ops import get_pr_number_for_head, post_final_comment
from .git_ops import (
    StashConflictError,
    ensure_gh_alias,
    git_add,
    git_branch_exists,
    git_commit,
    git_current_branch,
    git_default_branch,
    git_has_staged_changes,
    git_push_branch,
    git_root,
    git_stage_all,
    git_stash_worktree,
    git_status_snapshot,
    parse_owner_repo_from_git,
    print_codex_diagnostics,
    safe_stash_pop,
)
from .local_loop import orchestrate_local_loop
from .logging_utils import logger, setup_file_logging
from .executor import resolve_executor_policy
from .policy import policy_runner
from .tracker_generator import generate_tracker, get_tracker_path, load_tracker
from .pr_flow import open_or_get_pr
from .review_loop import review_fix_loop
from .utils import extract_called_process_error_details, now_stamp, slugify

PRD_NOT_FOUND_ERROR = "PRD path not found: {path}"
PRD_NOT_FILE_ERROR = "PRD path must be a file: {path}"


def run(args) -> None:
    original_cwd = Path.cwd()
    repo_root = Path(args.repo).resolve() if args.repo else git_root()
    register_safe_cwd(repo_root)
    os.chdir(repo_root)
    try:
        if args.log_file:
            log_path = Path(args.log_file).expanduser()
            if not log_path.is_absolute():
                log_path = (repo_root / log_path).resolve()
        else:
            xdg_config = os.getenv("XDG_CONFIG_HOME", None)
            if xdg_config and xdg_config.strip():
                base_config = Path(xdg_config).expanduser()
            else:
                base_config = Path.home() / ".config"
            preferred_dir = base_config / "aprd" / DEFAULT_LOG_DIR_NAME
            try:
                preferred_dir.mkdir(parents=True, exist_ok=True)
                if not os.access(preferred_dir, os.W_OK | os.X_OK):
                    raise PermissionError("log directory not writable")
                log_dir = preferred_dir
            except (OSError, PermissionError):
                log_dir = repo_root / DEFAULT_LOG_DIR_NAME
                log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / f"auto_prd_{now_stamp()}.log"

        setup_file_logging(log_path, args.log_level)
        print(f"Detailed logs: {log_path}")
        logger.info("Log file initialized at %s", log_path)

        ensure_claude_debug_dir()

        if args.phases is None:
            selected_phases = set(VALID_PHASES)
        else:
            selected_phases = {
                p.strip().lower() for p in args.phases.split(",") if p.strip()
            }
            invalid = selected_phases.difference(VALID_PHASES)
            if invalid:
                raise SystemExit(
                    f"Invalid phase(s): {', '.join(sorted(invalid))}. Valid options: {', '.join(VALID_PHASES)}"
                )

        def include(phase: str) -> bool:
            return phase in selected_phases

        _, _, _ = resolve_executor_policy(args.executor_policy)

        ensure_gh_alias()

        prd_candidate = Path(args.prd)
        if prd_candidate.is_absolute():
            prd_path = prd_candidate.resolve()
        else:
            prd_path = (original_cwd / prd_candidate).resolve()
        if not prd_path.exists():
            logger.error("Resolved PRD path does not exist: %s", prd_path)
            raise SystemExit(PRD_NOT_FOUND_ERROR.format(path=prd_path))
        if not prd_path.is_file():
            logger.error("Resolved PRD path is not a file: %s", prd_path)
            raise SystemExit(PRD_NOT_FILE_ERROR.format(path=prd_path))

        print(f"Repository root: {repo_root}")
        print(f"Using PRD: {prd_path}")
        logger.info("Resolved repository root to %s", repo_root)
        logger.info("Resolved PRD path to %s", prd_path)

        # Initialize or load checkpoint
        checkpoint: Optional[dict[str, Any]] = getattr(args, "checkpoint", None)
        if checkpoint:
            # Resuming from existing checkpoint
            session_id = checkpoint["session_id"]
            print(f"Resuming session: {session_id}")
            logger.info("Resuming session %s", session_id)
        else:
            # Create new checkpoint
            session_id = generate_session_id(prd_path)
            logger.info("Creating new session %s", session_id)

        owner_repo = args.repo_slug or parse_owner_repo_from_git()
        repo_default_branch = git_default_branch(repo_root)
        base_branch = args.base or repo_default_branch or "main"
        needs_branch_setup = include("local") or include("pr")
        should_checkout_base = include("local") or args.sync_git
        if needs_branch_setup:
            new_branch = args.branch or f"codex/{slugify(prd_path.stem)}-{now_stamp()}"
        else:
            new_branch = args.branch or git_current_branch(repo_root)

        base_branch_exists = git_branch_exists(repo_root, base_branch)
        if not base_branch_exists:
            if repo_default_branch and repo_default_branch != base_branch:
                print(
                    f"Base branch '{base_branch}' not found; using '{repo_default_branch}' instead."
                )
                base_branch = repo_default_branch
                base_branch_exists = git_branch_exists(repo_root, base_branch)
        if not base_branch_exists:
            current_branch = git_current_branch(repo_root)
            print(
                f"Base branch '{base_branch}' still not found; falling back to current branch '{current_branch}'."
            )
            base_branch = current_branch

        active_phases_with_commit_risk = selected_phases.intersection(
            PHASES_WITH_COMMIT_RISK
        )
        perform_auto_pr_commit = (
            include("pr") and not include("local") and not args.dry_run
        )
        stash_selector: Optional[str] = None
        branch_pushed = False
        if not args.dry_run:
            dirty_entries = git_status_snapshot(repo_root)
            if dirty_entries:
                if active_phases_with_commit_risk:
                    print("⚠️  WARNING: Workspace has uncommitted changes!")
                    print("   This is risky for phases that might commit changes:")
                    print(
                        f"   Active phases with commit risk: {', '.join(sorted(active_phases_with_commit_risk))}"
                    )
                    if perform_auto_pr_commit:
                        print(
                            "   Autodev will stash, commit, and push these changes for the PR phase."
                        )
                    else:
                        print("   Consider committing or stashing changes first.")
                    print("\nUncommitted changes:")
                    for entry in dirty_entries:
                        print(f"   {entry}")
                    print()
                    logger.warning(
                        "Uncommitted changes detected in phases with commit risk (%s): %s",
                        ", ".join(sorted(active_phases_with_commit_risk)),
                        "; ".join(dirty_entries),
                    )
                else:
                    logger.warning(
                        "Workspace has uncommitted changes; continuing with relaxed behavior:\n%s",
                        "\n".join(f"  {entry}" for entry in dirty_entries),
                    )
                if perform_auto_pr_commit and should_checkout_base:
                    print(
                        "Stashing working tree before preparing PR branch…", flush=True
                    )
                    stash_message = f"autodev-pr-stash-{now_stamp()}"
                    stash_selector = git_stash_worktree(repo_root, stash_message)
                    if stash_selector is None:
                        raise SystemExit(
                            "Failed to stash working tree prior to PR preparation."
                        )
                elif perform_auto_pr_commit:
                    print(
                        "Proceeding with dirty working tree (no stash needed when branching from current HEAD)."
                    )

        if needs_branch_setup:
            try:
                if should_checkout_base:
                    current_branch = git_current_branch(repo_root)
                    if base_branch_exists:
                        if args.sync_git:
                            print("Synchronizing base branch from origin…", flush=True)
                            run_cmd(["git", "fetch", "origin"], cwd=repo_root)
                        else:
                            print(
                                "Skipping git fetch (pass --sync-git to enable).",
                                flush=True,
                            )
                        if current_branch != base_branch:
                            run_cmd(["git", "checkout", base_branch], cwd=repo_root)
                            current_branch = base_branch
                        if args.sync_git:
                            run_cmd(["git", "pull", "--ff-only"], cwd=repo_root)
                    else:
                        if args.sync_git:
                            print(
                                f"Cannot synchronize; base branch '{base_branch}' is unavailable."
                            )
                        print(
                            f"Base branch '{base_branch}' unavailable; staying on '{current_branch}'."
                        )

                if base_branch_exists:
                    print(
                        f"Creating/checking out working branch '{new_branch}' from '{base_branch}'…",
                        flush=True,
                    )
                    run_cmd(
                        ["git", "checkout", "-B", new_branch, base_branch],
                        cwd=repo_root,
                    )
                else:
                    print(
                        f"Base branch '{base_branch}' missing; staying on existing branch '{new_branch}'."
                    )
                    run_cmd(["git", "checkout", "-B", new_branch], cwd=repo_root)
                new_branch = git_current_branch(repo_root)
            except subprocess.CalledProcessError as exc:
                details = extract_called_process_error_details(exc)
                raise SystemExit(
                    f"Failed to prepare working branch {new_branch}: {details}"
                ) from exc
        else:
            print(f"Continuing on current branch: {new_branch}")

        # Create checkpoint if not resuming
        if checkpoint is None:
            checkpoint = create_checkpoint(
                session_id=session_id,
                prd_path=prd_path,
                repo_root=repo_root,
                base_branch=base_branch,
                feature_branch=new_branch,
                selected_phases=selected_phases,
            )
            save_checkpoint(checkpoint)
            print(f"Session: {session_id}")
            logger.info("Created checkpoint for session %s", session_id)

        if stash_selector:
            try:
                print(
                    f"Restoring stashed changes ({stash_selector}) onto branch '{new_branch}'…"
                )
                safe_stash_pop(repo_root, stash_selector)
            except StashConflictError as exc:
                # Provide actionable recovery instructions for conflicts
                logger.error("Stash conflict detected: %s", exc)
                raise SystemExit(str(exc)) from exc
            except subprocess.CalledProcessError as exc:
                details = extract_called_process_error_details(exc)
                raise SystemExit(
                    "Failed to reapply stashed changes after creating the PR branch. "
                    f"Details: {details}"
                ) from exc

        if perform_auto_pr_commit:
            try:
                git_stage_all(repo_root)
            except subprocess.CalledProcessError as exc:
                details = extract_called_process_error_details(exc)
                raise SystemExit(
                    f"Failed to stage changes before PR commit: {details}"
                ) from exc
            if git_has_staged_changes(repo_root):
                commit_message = (
                    f"chore: autodev snapshot {slugify(prd_path.stem)} {now_stamp()}"
                )
                try:
                    git_commit(repo_root, commit_message)
                except subprocess.CalledProcessError as exc:
                    details = extract_called_process_error_details(exc)
                    raise SystemExit(
                        f"Failed to commit staged changes: {details}"
                    ) from exc
                print(f"Committed changes with message: {commit_message}", flush=True)
            else:
                print(
                    "No staged changes detected before PR; skipping commit.", flush=True
                )
            try:
                git_push_branch(repo_root, new_branch)
                branch_pushed = True
                print(f"Pushed branch '{new_branch}' to origin.", flush=True)
            except subprocess.CalledProcessError as exc:
                details = extract_called_process_error_details(exc)
                raise SystemExit(
                    f"Failed to push branch '{new_branch}': {details}"
                ) from exc

        if args.allow_unsafe_execution:
            print_codex_diagnostics(repo_root)
        tasks_left = -1
        appears_complete = False

        # Local phase
        if include("local"):
            # Check if resuming from local phase
            local_state = checkpoint["phases"]["local"]
            resume_iteration = 0
            if local_state["status"] == "in_progress":
                resume_iteration = local_state.get("iteration", 0)
                logger.info("Resuming local phase from iteration %d", resume_iteration)

            mark_phase_started(checkpoint, "local")
            update_phase_state(checkpoint, "local", {"max_iters": args.max_local_iters})
            save_checkpoint(checkpoint)

            # Generate implementation tracker from PRD (Phase 3.0)
            # The tracker is the contract between all agent invocations
            tracker_path = get_tracker_path(repo_root)
            existing_tracker = load_tracker(repo_root)
            if existing_tracker is None:
                print("Generating implementation tracker from PRD...", flush=True)
                logger.info("Generating tracker for PRD: %s", prd_path)

                # Resolve executor from policy for tracker generation
                # Use policy_runner with i=1 (first iteration) to get the actual executor
                _, executor_label = policy_runner(
                    args.executor_policy, i=1, phase="implement"
                )
                tracker_executor = (
                    executor_label.lower()
                )  # "Codex" -> "codex", "Claude" -> "claude"

                try:
                    tracker = generate_tracker(
                        prd_path=prd_path,
                        repo_root=repo_root,
                        executor=tracker_executor,
                        force=False,
                        dry_run=args.dry_run,
                        allow_unsafe_execution=args.allow_unsafe_execution,
                    )
                    print(
                        f"Tracker generated: {tracker['validation_summary']['total_features']} features, "
                        f"{tracker['validation_summary']['total_tasks']} tasks",
                        flush=True,
                    )
                    logger.info(
                        "Tracker generated with %d features",
                        tracker["validation_summary"]["total_features"],
                    )
                    # Commit tracker to git - only stage the tracker file
                    # Check for pre-existing staged changes to avoid bundling
                    # unrelated work with the tracker commit
                    if not args.dry_run:
                        try:
                            had_staged_before = git_has_staged_changes(repo_root)
                            if had_staged_before:
                                logger.warning(
                                    "Pre-existing staged changes detected; "
                                    "skipping auto-commit of tracker to avoid "
                                    "bundling unrelated work. Tracker file staged "
                                    "but not committed."
                                )
                                git_add(repo_root, tracker_path)
                            else:
                                git_add(repo_root, tracker_path)
                                if git_has_staged_changes(repo_root):
                                    git_commit(
                                        repo_root,
                                        "chore(aprd): initialize implementation tracker",
                                    )
                                    logger.info("Committed tracker to git")
                                else:
                                    logger.debug("No tracker changes to commit")
                        except subprocess.CalledProcessError as exc:
                            details = extract_called_process_error_details(exc)
                            logger.warning(
                                "Failed to stage/commit tracker: %s", details
                            )
                except (IOError, OSError) as exc:
                    logger.warning(
                        "Tracker generation I/O error: %s", exc, exc_info=True
                    )
                    print(f"Warning: Tracker generation I/O error: {exc}", flush=True)
                    print("Continuing without tracker...", flush=True)
                except (ValueError, RuntimeError) as exc:
                    logger.warning("Tracker generation failed: %s", exc, exc_info=True)
                    print(f"Warning: Tracker generation failed: {exc}", flush=True)
                    print("Continuing without tracker...", flush=True)
            else:
                print(f"Using existing tracker: {tracker_path}", flush=True)
                logger.info("Loaded existing tracker from %s", tracker_path)

            tasks_left, appears_complete = orchestrate_local_loop(
                prd_path=prd_path,
                repo_root=repo_root,
                base_branch=base_branch,
                max_iters=args.max_local_iters,
                codex_model=args.codex_model,
                allow_unsafe_execution=args.allow_unsafe_execution,
                dry_run=args.dry_run,
                checkpoint=checkpoint,  # Pass checkpoint for iteration-level updates
            )

            mark_phase_complete(checkpoint, "local")
            update_phase_state(checkpoint, "local", {"tasks_left": tasks_left})
            save_checkpoint(checkpoint)

        # PR phase
        pr_number = None
        if include("pr"):
            mark_phase_started(checkpoint, "pr")
            save_checkpoint(checkpoint)

            pr_number = open_or_get_pr(
                new_branch=new_branch,
                base_branch=base_branch,
                repo_root=repo_root,
                prd_path=prd_path,
                codex_model=args.codex_model,
                allow_unsafe_execution=args.allow_unsafe_execution,
                dry_run=args.dry_run,
                skip_runner=perform_auto_pr_commit,
                already_pushed=branch_pushed,
            )

            mark_phase_complete(checkpoint, "pr")
            update_phase_state(
                checkpoint, "pr", {"pr_number": pr_number, "branch_pushed": True}
            )
            save_checkpoint(checkpoint)
        # Review/fix phase - get PR number if not running PR phase
        if include("review_fix") and not include("pr"):
            if pr_number is None:
                head_branch = git_current_branch(repo_root)
                try:
                    pr_number = get_pr_number_for_head(head_branch, repo_root)
                except (
                    ValueError,
                    RuntimeError,
                    OSError,
                    subprocess.CalledProcessError,
                    FileNotFoundError,
                ):
                    pr_number = None
                if pr_number is None:
                    print(
                        "No open PR associated with the current branch; review/fix loop will be skipped."
                    )

        # Review/fix phase
        if include("review_fix"):
            mark_phase_started(checkpoint, "review_fix")
            save_checkpoint(checkpoint)

            review_succeeded = review_fix_loop(
                pr_number=pr_number,
                owner_repo=owner_repo,
                repo_root=repo_root,
                idle_grace=args.idle_grace_minutes,
                poll_interval=args.review_poll_seconds,
                codex_model=args.codex_model,
                allow_unsafe_execution=args.allow_unsafe_execution,
                dry_run=args.dry_run,
                initial_wait_minutes=args.wait_minutes,
                infinite_reviews=args.infinite_reviews,
                checkpoint=checkpoint,  # Pass checkpoint for comment tracking
            )

            if not review_succeeded:
                logger.warning(
                    "Review loop terminated due to consecutive failures; "
                    "marking phase as incomplete"
                )
                update_phase_state(checkpoint, "review_fix", {"terminated_early": True})
                save_checkpoint(checkpoint)
                # Continue to post final comment but don't mark as complete
            else:
                mark_phase_complete(checkpoint, "review_fix")
                save_checkpoint(checkpoint)

        post_final_comment(
            pr_number=pr_number,
            owner_repo=owner_repo,
            prd_path=prd_path,
            repo_root=repo_root,
            dry_run=args.dry_run,
        )

        # Mark session complete
        mark_session_complete(checkpoint)
        save_checkpoint(checkpoint)
        print(f"Session {session_id} completed successfully.")
        logger.info("Session %s completed", session_id)

        if appears_complete:
            print(f"Final TASKS_LEFT={tasks_left}", flush=True)
    finally:
        os.chdir(original_cwd)
