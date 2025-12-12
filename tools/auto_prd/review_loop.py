"""Review/fix loop management for PR feedback."""

from __future__ import annotations

import os
import random
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

from .agents import (
    codex_exec,
    claude_exec,
    claude_exec_streaming,
    _sanitize_stderr_for_exception,
)
from .utils import extract_called_process_error_details
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
# Maximum consecutive runner failures before terminating the review loop.
# This prevents infinite retry loops on persistent errors (e.g., auth failures,
# rate limits, or process crashes). The counter resets on any successful execution.
MAX_CONSECUTIVE_FAILURES = 3

# Truncation limits for error messages to balance detail with readability.
# ERROR_DETAIL_TRUNCATE_CHARS: Max chars for error detail shown to user (brief summary)
ERROR_DETAIL_TRUNCATE_CHARS = 200
# STDERR_USER_TRUNCATE_CHARS: Max chars of stderr shown in user-facing output
STDERR_USER_TRUNCATE_CHARS = 500
# STDERR_LOG_TRUNCATE_CHARS: Max chars of stderr written to log files (more verbose)
STDERR_LOG_TRUNCATE_CHARS = 2000

# Box-drawing characters for streaming output formatting.
# These are lazy-loaded via _get_box_chars() to avoid reading environment variables
# at module import time when streaming may not be used.


def _get_box_chars() -> tuple[str, str]:
    """Return (horizontal, vertical) box-drawing characters.

    Uses ASCII characters if AUTO_PRD_ASCII_OUTPUT is set to a truthy value
    (1, true, yes), otherwise uses Unicode box-drawing characters.

    The environment variable is read at call time, allowing runtime configuration.
    """
    use_ascii = os.getenv("AUTO_PRD_ASCII_OUTPUT", "").lower() in ("1", "true", "yes")
    return ("-", "|") if use_ascii else ("─", "│")


_JITTER_RNG = random.Random()


def _decode_stderr(stderr: bytes | str | None) -> str:
    """Decode stderr from CalledProcessError to string."""
    if not stderr:
        return ""
    if isinstance(stderr, bytes):
        return stderr.decode("utf-8", errors="replace")
    return str(stderr)


def _handle_runner_failure(
    failure_count: int,
    error_detail: str,
    stderr_text: str = "",
    error_type: str = "",
) -> bool:
    """Log failure details and determine if loop should stop.

    Args:
        failure_count: Current count of consecutive failures (1 for first failure,
            2 for second, etc.). The caller increments the counter before calling
            this function, so this represents the total failures including the
            current one. Compared against MAX_CONSECUTIVE_FAILURES to determine
            if the loop should terminate.
        error_detail: Description of the error
        stderr_text: Optional stderr output from the process
        error_type: Optional error type name for user feedback

    Returns:
        True if loop should stop due to max failures reached.
    """
    logger.warning(
        "Review runner failed (attempt %d/%d): %s",
        failure_count,
        MAX_CONSECUTIVE_FAILURES,
        error_detail,
    )
    # Provide user-facing feedback with error type if available
    type_suffix = f" ({error_type})" if error_type else ""
    print(
        f"\nReview runner failed{type_suffix} "
        f"(attempt {failure_count}/{MAX_CONSECUTIVE_FAILURES})",
        flush=True,
    )
    # Show truncated error detail to user
    if error_detail:
        brief_detail = (
            error_detail[:ERROR_DETAIL_TRUNCATE_CHARS] + "..."
            if len(error_detail) > ERROR_DETAIL_TRUNCATE_CHARS
            else error_detail
        )
        print(f"  Error: {brief_detail}", flush=True)
    if stderr_text.strip():
        # Sanitize stderr to redact potentially sensitive information (tokens, secrets,
        # credentials, user paths) before logging. This is critical because stderr can
        # contain echoed config values, auth tokens, or file paths that reveal PII.
        sanitized_stderr = _sanitize_stderr_for_exception(
            stderr_text, STDERR_LOG_TRUNCATE_CHARS
        )
        # Log sanitized stderr at WARNING level for failed executions only. This is
        # acceptable because: (1) failures need debugging context, (2) stderr typically
        # contains error messages not model output, (3) content is now sanitized.
        logger.warning("Review runner stderr:\n%s", sanitized_stderr)
        # For user-facing output, also sanitize and apply shorter truncation limit
        sanitized_user_stderr = _sanitize_stderr_for_exception(
            stderr_text, STDERR_USER_TRUNCATE_CHARS
        )
        print(f"  Stderr: {sanitized_user_stderr}", flush=True)

    if failure_count >= MAX_CONSECUTIVE_FAILURES:
        logger.error(
            "Stopping review loop after %d consecutive failures",
            failure_count,
        )
        print(
            f"\nStopping: {failure_count} consecutive failures. "
            f"Last error: {error_type or 'unknown'}",
            flush=True,
        )
        return True
    return False


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
) -> bool:
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

    Returns:
        True if the loop terminated gracefully (i.e., completed work, timed out, no feedback
        found, or was stopped by policy/user action such as should_stop_review_after_push).
        False if the loop terminated due to reaching MAX_CONSECUTIVE_FAILURES consecutive
        runner failures.

    Raises:
        The following exceptions are re-raised immediately if encountered and are considered
        unrecoverable errors (i.e., not handled by the retry logic):

        PermissionError: If a file or directory cannot be accessed due to
            insufficient permissions during subprocess execution.
        FileNotFoundError: If a required file or directory is missing, such as
            missing executables or repository paths.
        MemoryError: If the process runs out of memory during execution of
            subprocess commands or large data processing.
        AttributeError: If an expected attribute is missing from an object,
            typically from malformed API responses or configuration.
        TypeError: If an operation or function is applied to an object of
            inappropriate type, such as invalid argument types.
        NameError: If a variable or function name is not found, typically
            indicating a configuration or import issue.
        KeyError: If a required key is missing from a dictionary or mapping,
            such as missing fields in API responses or checkpoint data.

    Note:
        Transient/recoverable errors (such as subprocess.CalledProcessError,
        subprocess.TimeoutExpired, and other transient failures) are handled
        internally with retry logic up to MAX_CONSECUTIVE_FAILURES. Only the
        unrecoverable errors listed above are re-raised immediately. If the
        maximum number of consecutive recoverable failures is reached, the
        function returns False instead of raising an exception.
    """
    if pr_number is None:
        return True
    if dry_run:
        logger.info("Dry run enabled; skipping review loop for PR #%s.", pr_number)
        return True

    trigger_copilot(owner_repo, pr_number, repo_root)
    initial_wait_seconds = max(0, initial_wait_minutes * 60)
    if initial_wait_seconds:
        print(f"Waiting {initial_wait_minutes} minutes for bot reviews...", flush=True)
        time.sleep(initial_wait_seconds)

    # Use float type only when infinite_reviews is True (for float("inf") support);
    # otherwise, keep as int for cleaner numeric comparisons with finite values.
    idle_grace_seconds: float | int = max(0, idle_grace * 60)
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

    consecutive_failures = 0

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
            review_runner, runner_name = policy_runner(None, phase="review_fix")

            runner_kwargs = {
                "repo_root": repo_root,
                "enable_search": True,
                "allow_unsafe_execution": allow_unsafe_execution,
                "dry_run": dry_run,
            }
            if review_runner is codex_exec:
                runner_kwargs["model"] = codex_model

            # Use streaming variant for claude_exec to show real-time progress.
            # When the policy selects claude_exec, we switch to claude_exec_streaming
            # which provides line-by-line output via the on_output callback.
            use_claude_streaming = review_runner is claude_exec
            if use_claude_streaming:
                box_h, box_v = _get_box_chars()
                print(f"\n{box_h * 60}")
                print(f"  Running {runner_name or 'claude'} (streaming output)...")
                print(f"{box_h * 60}", flush=True)

                def output_handler(line: str, vert: str = box_v) -> None:
                    print(f"  {vert} {line}", flush=True)
                    # Note: Intentionally not logging model output to avoid persisting
                    # potentially sensitive data (secrets, PII) to log files.
                    # If logging is needed for debugging specific issues, callers should
                    # implement their own output_handler with appropriate sanitization
                    # and log level controls (e.g., DEBUG with opt-in environment flag).

                runner_kwargs["on_output"] = output_handler
                actual_runner = claude_exec_streaming
            else:
                actual_runner = review_runner

            try:
                _, stderr = actual_runner(fix_prompt, **runner_kwargs)
                # Note: Stderr is logged at debug level for diagnostics, but NOT at higher
                # levels to minimize exposure of potentially sensitive data. Debug logs are
                # typically disabled in production. Stdout is not logged at all (see
                # output_handler above) as it contains actual model responses.
                if stderr and stderr.strip():
                    logger.debug("Review runner stderr (debug only): %s", stderr[:500])
                consecutive_failures = 0
                # Determine completion status message (independent of streaming mode)
                if not (stderr and stderr.strip()):
                    status_msg = "Review fix completed successfully"
                else:
                    status_msg = "Review fix completed (with warnings)"
                # Display completion status with appropriate formatting
                if use_claude_streaming:
                    print(f"{box_h * 60}")
                    print(f"  {status_msg}")
                    print(f"{box_h * 60}\n", flush=True)
                else:
                    print(status_msg, flush=True)
            except subprocess.TimeoutExpired as exc:
                # Timeout - count as failure but provide specific feedback
                consecutive_failures += 1
                timeout_secs = getattr(exc, "timeout", "unknown")
                error_detail = f"Execution timed out after {timeout_secs} seconds"
                stderr_text = _decode_stderr(getattr(exc, "stderr", None))
                if _handle_runner_failure(
                    consecutive_failures,
                    error_detail,
                    stderr_text,
                    error_type="TimeoutExpired",
                ):
                    return False
                sleep_with_jitter(float(poll))
                continue
            except subprocess.CalledProcessError as exc:
                consecutive_failures += 1
                error_detail = extract_called_process_error_details(exc)
                stderr_text = _decode_stderr(exc.stderr)
                if _handle_runner_failure(
                    consecutive_failures,
                    error_detail,
                    stderr_text,
                    error_type="CalledProcessError",
                ):
                    return False
                sleep_with_jitter(float(poll))
                continue
            except (PermissionError, FileNotFoundError) as exc:
                # Configuration/environment errors - don't retry, fail immediately
                error_type = type(exc).__name__
                logger.error(
                    "Review runner failed with unrecoverable error (%s): %s",
                    error_type,
                    exc,
                )
                print(f"\nFatal error ({error_type}): {exc}", flush=True)
                print(
                    "This error cannot be resolved by retrying. "
                    "Please check your configuration.",
                    flush=True,
                )
                raise
            except MemoryError as exc:
                # System resource exhaustion - don't retry
                logger.error("Review runner failed due to memory exhaustion: %s", exc)
                print("\nFatal error: Out of memory", flush=True)
                raise
            except (AttributeError, TypeError, NameError, KeyError) as exc:
                # Programming errors - fail immediately, don't retry
                error_type = type(exc).__name__
                logger.error(
                    "Review runner failed with programming error (%s): %s - not retrying",
                    error_type,
                    exc,
                )
                print(f"\nProgramming error ({error_type}): {exc}", flush=True)
                print(
                    "This appears to be a bug in the code. Please report this issue.",
                    flush=True,
                )
                raise
            except (SystemExit, KeyboardInterrupt):
                # Allow clean shutdown and user cancellation to propagate
                raise
            except Exception as exc:  # pragma: no cover - best-effort resilience
                consecutive_failures += 1
                error_type = type(exc).__name__
                logger.exception(
                    "Review runner failed with unexpected error (%s)", error_type
                )
                if _handle_runner_failure(
                    consecutive_failures,
                    str(exc),
                    error_type=error_type,
                ):
                    return False
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
                        # Use time.time() for checkpoint persistence: provides wall-clock time
                        # suitable for cross-process timestamps. time.monotonic() is relative
                        # to an arbitrary epoch (often system boot) and cannot be compared
                        # across process restarts.
                        "last_activity_time": time.time(),
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
            print("Review loop complete.")
            return True

        if idle_grace_seconds == 0:
            print("No unresolved feedback; stopping.")
            print("Review loop complete.")
            return True
        elapsed = time.monotonic() - last_activity
        if elapsed >= idle_grace_seconds:
            minutes = "∞" if infinite_reviews else idle_grace
            print(f"No unresolved feedback for {minutes} minutes; finishing.")
            print("Review loop complete.")
            return True
        print("No unresolved feedback right now; waiting for potential new comments...")
        sleep_with_jitter(float(poll))


def format_unresolved_bullets(unresolved: list[dict], limit: int) -> str:
    lines: list[str] = []
    malformed_count = 0
    for entry in unresolved:
        summary = entry.get("summary")
        if not isinstance(summary, str):
            malformed_count += 1
            # Log first malformed entry at WARNING to surface potential API issues,
            # subsequent entries at DEBUG to avoid log spam
            log_level = logger.warning if malformed_count == 1 else logger.debug
            log_level(
                "Skipping unresolved entry with invalid summary type: comment_id=%s, type=%s",
                entry.get("comment_id", "unknown"),
                type(summary).__name__,
            )
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
