"""Integrations with external agents (Codex, CodeRabbit, Claude)."""

from __future__ import annotations

import errno
import fcntl
import os
import random
import re
import select
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Callable, Optional

from .command import run_cmd, verify_unsafe_execution_ready, env_with_zsh
from .logging_utils import logger
from .utils import extract_called_process_error_details, scrub_cli_text

RATE_LIMIT_JITTER_MIN = -3
RATE_LIMIT_JITTER_MAX = 3
RATE_LIMIT_MIN_SLEEP_SECONDS = 5
RATE_LIMIT_MAX_SLEEP_SECONDS = 900
CODERABBIT_PROMPT_TIMEOUT_SECONDS = 900

# I/O buffer and polling constants for claude_exec_streaming
# Read chunk size: 4KB is a reasonable default for buffered I/O, balancing
# memory usage with system call overhead.
STREAMING_READ_CHUNK_SIZE = 4096
# Select poll timeout: 100ms provides a balance between responsive streaming
# and CPU efficiency. Lower values increase responsiveness but consume more CPU.
STREAMING_SELECT_TIMEOUT_SECONDS = 0.1


def _timeout_from_env(env_key: str, default: int | None) -> int | None:
    raw = os.getenv(env_key)
    if raw is None:
        return default

    normalized = raw.strip().lower()
    if not normalized or normalized in {"none", "no", "off", "disable", "disabled"}:
        return None

    try:
        parsed = int(normalized)
    except ValueError:
        default_str = "no timeout" if default is None else str(default)
        logger.warning(
            "Invalid %s value %r; falling back to %s", env_key, raw, default_str
        )
        return default

    if parsed <= 0:
        return None
    return parsed


def get_codex_exec_timeout() -> int | None:
    """Get the Codex execution timeout from environment variables."""
    return _timeout_from_env("AUTO_PRD_CODEX_TIMEOUT_SECONDS", None)


def get_claude_exec_timeout() -> int | None:
    """Get the Claude execution timeout from environment variables."""
    return _timeout_from_env("AUTO_PRD_CLAUDE_TIMEOUT_SECONDS", None)


# Use a cryptographically secure RNG for backoff jitter to avoid predictable retry cadences.
_rate_limit_rng = random.SystemRandom()


def codex_exec(
    prompt: str,
    repo_root: Path,
    model: str = "gpt-5-codex",
    enable_search: bool = True,
    yolo: Optional[bool] = None,
    allow_unsafe_execution: Optional[bool] = None,
    dry_run: bool = False,
    extra: Optional[list[str]] = None,
) -> tuple[str, str]:
    os.environ.setdefault("CI", "1")
    allow_flag = allow_unsafe_execution
    if yolo is not None:
        logger.warning(
            "codex_exec: 'yolo' is deprecated; use allow_unsafe_execution instead"
        )
        if allow_flag is None:
            allow_flag = yolo
        else:
            allow_flag = allow_flag or yolo
    allow_flag = bool(allow_flag)
    args: list[str] = ["codex"]
    if enable_search:
        args.append("--search")
    if not allow_flag and not dry_run:
        raise PermissionError(
            "Codex executor requires allow_unsafe_execution=True to bypass permissions."
        )
    if allow_flag:
        verify_unsafe_execution_ready()
        args.append("--dangerously-bypass-approvals-and-sandbox")
        args.extend(["--config", 'sandbox_mode="danger-full-access"'])
        args.extend(["--config", 'shell_environment_policy.inherit="all"'])
    if extra:
        args.extend(extra)
    args.extend(["exec", "--model", model, "-"])
    if dry_run:
        logger.info("Dry run enabled; skipping Codex execution. Args: %s", args)
        return "DRY_RUN", ""
    out, stderr, _ = run_cmd(
        args,
        cwd=repo_root,
        check=True,
        stdin=prompt,
        timeout=get_codex_exec_timeout(),
    )

    # Log warning if stdout is empty but stderr has content (may indicate rate limiting)
    if not out.strip() and stderr.strip():
        logger.warning(
            "Codex returned empty stdout. Stderr content: %s",
            stderr[:500] if len(stderr) > 500 else stderr,
        )

    return out, stderr


def parse_rate_limit_sleep(message: str) -> Optional[int]:
    if not message:
        return None

    # Match rate limit messages like:
    #   "try after 10 minutes and 14 seconds"
    #   "try again after 5 mins and 2 secs"
    #   "try after 1 minute 30 seconds"
    #   "try again after 12 min 5 sec"
    #   "try after 0 minutes and 45 seconds"
    # This pattern extracts minutes and seconds when both are present.
    match = re.search(
        r"try (?:again )?after\s+(\d+)\s*(?:minute(?:s)?|min(?:s)?)\s+(?:and\s+)?(\d+)\s*(?:second(?:s)?|sec(?:s)?)",
        message,
        re.IGNORECASE,
    )
    if match:
        minutes = int(match.group(1))
        seconds = int(match.group(2))
        return minutes * 60 + seconds + 5

    # HTTP Retry-After with HTTP-date, e.g., "Retry-After: Wed, 21 Oct 2015 07:28:00 GMT"
    http_date = re.search(
        r"retry-after[:=]\s*([A-Za-z]{3},\s*\d{1,2}\s*[A-Za-z]{3}\s*\d{4}\s*\d{2}:\d{2}:\d{2}\s*GMT)",
        message,
        re.IGNORECASE,
    )
    if http_date:
        try:
            retry_at = parsedate_to_datetime(http_date.group(1))
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            retry_at = retry_at.astimezone(timezone.utc)
            delta = (retry_at - datetime.now(timezone.utc)).total_seconds()
            if delta > 0:
                return int(delta) + 5
        except (TypeError, ValueError):
            logger.debug(
                "Failed to parse HTTP-date Retry-After: %s", http_date.group(1)
            )

    # e.g. "try again in 10m 14s" (gh output) or "2m 30s"
    match = re.search(r"\b(\d+)\s*m\s*(\d+)\s*s\b", message, re.IGNORECASE)
    if match:
        return int(match.group(1)) * 60 + int(match.group(2)) + 5

    # e.g. "try again in 5 minutes" or "in 12 min"
    match = re.search(
        r"(?:try (?:again )?(?:after|in)|in)\s+(\d+)\s*(?:minute(?:s)?|min(?:s)?)\b",
        message,
        re.IGNORECASE,
    )
    if match:
        return int(match.group(1)) * 60 + 5

    # e.g. "try again in 75 seconds" or "try after 75 sec"
    match = re.search(
        r"(?:try (?:again )?(?:after|in)|in)\s+(\d+)\s*(?:second(?:s)?|sec(?:s)?)\b",
        message,
        re.IGNORECASE,
    )
    if match:
        return int(match.group(1)) + 5

    # HTTP "Retry-After: 600"
    match = re.search(r"retry-after[:=]\s*(\d+)", message, re.IGNORECASE)
    if match:
        return int(match.group(1)) + 5

    return None


def coderabbit_prompt_only(base_branch: str | None, repo_root: Path) -> str:
    args = ["coderabbit", "--prompt-only"]
    if base_branch:
        args += ["--base", base_branch]
    attempts = 0
    while True:
        attempts += 1
        try:
            out, _, _ = run_cmd(
                args, cwd=repo_root, timeout=CODERABBIT_PROMPT_TIMEOUT_SECONDS
            )
            return out.strip()
        except subprocess.CalledProcessError as exc:
            msg = extract_called_process_error_details(exc)
            sleep_secs = parse_rate_limit_sleep(msg)
            if sleep_secs and attempts <= 3:
                capped = max(
                    RATE_LIMIT_MIN_SLEEP_SECONDS,
                    min(RATE_LIMIT_MAX_SLEEP_SECONDS, sleep_secs),
                )
                jitter = _rate_limit_rng.randint(
                    RATE_LIMIT_JITTER_MIN, RATE_LIMIT_JITTER_MAX
                )
                wait = max(1, capped + jitter)
                sleep_for = min(wait, RATE_LIMIT_MAX_SLEEP_SECONDS)
                logger.warning(
                    "CodeRabbit rate limited; sleeping %s seconds before retry (attempt %d/3)",
                    sleep_for,
                    attempts,
                )
                time.sleep(sleep_for)
                continue
            logger.warning("CodeRabbit prompt-only run failed: %s", msg or exc)
            return ""


def coderabbit_has_findings(text: str) -> bool:
    if not text.strip():
        return False
    lowered = text.lower()
    for marker in (
        "file:",
        "line",
        "issue",
        "prompt for ai agent",
        "consider",
        "fix",
        "security",
        "leak",
        "race",
    ):
        if marker in lowered:
            return True
    return False


def _resolve_unsafe_flag(
    allow_unsafe_execution: Optional[bool],
    yolo: Optional[bool],
    caller: str,
) -> bool:
    """Resolve the allow_unsafe_execution flag, handling deprecated yolo parameter."""
    allow_flag = allow_unsafe_execution
    if yolo is not None:
        logger.warning("%s: 'yolo' is deprecated; use allow_unsafe_execution", caller)
        if allow_flag is None:
            allow_flag = yolo
        else:
            allow_flag = allow_flag or yolo
    return bool(allow_flag)


def _build_claude_args(
    allow_flag: bool,
    model: str | None,
    enable_search: bool,
    extra: Optional[list[str]],
) -> list[str]:
    """Build the CLI arguments for Claude execution."""
    args: list[str] = ["claude"]
    if allow_flag:
        args.append("--dangerously-skip-permissions")
    if model:
        args.extend(["--model", model])
    if not enable_search:
        logger.info(
            "Claude CLI does not yet expose a --no-search flag; ignoring enable_search=False"
        )
    if extra:
        args.extend(extra)
    args.extend(["-p", "-"])
    return args


def claude_exec(
    prompt: str,
    repo_root: Path,
    model: str | None = None,
    enable_search: bool = True,
    yolo: Optional[bool] = None,
    allow_unsafe_execution: Optional[bool] = None,
    dry_run: bool = False,
    extra: Optional[list[str]] = None,
) -> tuple[str, str]:
    """Execute a Claude command. Parameters mirror codex_exec for API compatibility."""
    allow_flag = _resolve_unsafe_flag(allow_unsafe_execution, yolo, "claude_exec")
    if not allow_flag and not dry_run:
        raise PermissionError(
            "Claude executor requires allow_unsafe_execution=True to bypass permissions."
        )
    os.environ.setdefault("CI", "1")
    if allow_flag:
        verify_unsafe_execution_ready()

    args = _build_claude_args(allow_flag, model, enable_search, extra)
    if dry_run:
        logger.info("Dry run enabled; skipping Claude execution. Args: %s", args)
        return "DRY_RUN", ""

    out, stderr, _ = run_cmd(
        args,
        cwd=repo_root,
        check=True,
        stdin=prompt,
        timeout=get_claude_exec_timeout(),
    )

    if not out.strip() and stderr.strip():
        logger.warning(
            "Claude returned empty stdout. Stderr content: %s",
            stderr[:500] if len(stderr) > 500 else stderr,
        )

    return out, stderr


def _set_nonblocking(fd: int) -> None:
    """Set a file descriptor to non-blocking mode.

    Raises:
        OSError: If fcntl operations fail, with contextual error message.
    """
    try:
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    except (OSError, ValueError) as e:
        logger.error("Failed to set non-blocking mode on fd %d: %s", fd, e)
        raise OSError(
            f"Failed to configure non-blocking I/O for Claude streaming (fd={fd}): {e}"
        ) from e


def _process_buffer(
    buffer: str,
    lines: list[str],
    output_handler: Optional[Callable[[str], None]] = None,
) -> str:
    """Process complete lines from buffer, returning remainder.

    This function extracts complete lines (terminated by newlines) from the buffer,
    appending each line to the `lines` list IN-PLACE and optionally calling
    `output_handler` for each line. The remaining incomplete line (if any) is
    returned for subsequent buffering.

    Args:
        buffer: Input buffer potentially containing newline-terminated lines.
        lines: List to append complete lines to (modified in-place).
        output_handler: Optional callback invoked for each complete line.

    Returns:
        Remaining buffer content after the last newline (may be empty string).
    """
    while "\n" in buffer:
        line, buffer = buffer.split("\n", 1)
        lines.append(line)
        if output_handler:
            output_handler(line)
    return buffer


def claude_exec_streaming(
    prompt: str,
    repo_root: Path,
    model: str | None = None,
    enable_search: bool = True,
    yolo: Optional[bool] = None,
    allow_unsafe_execution: Optional[bool] = None,
    dry_run: bool = False,
    extra: Optional[list[str]] = None,
    on_output: Optional[Callable[[str], None]] = None,
    timeout: Optional[int] = None,
) -> tuple[str, str]:
    """Execute Claude with real-time output streaming.

    Like claude_exec but streams stdout in real-time for visibility.
    Note: This function uses fcntl for non-blocking I/O and is Unix-only.

    Args:
        prompt: The prompt to send to Claude
        repo_root: Repository root directory
        model: Optional model name override
        enable_search: Enable search (not currently used by Claude CLI)
        yolo: Deprecated alias for allow_unsafe_execution
        allow_unsafe_execution: Must be True for actual (non-dry-run) execution
        dry_run: If True, skip actual execution and return ("DRY_RUN", "")
        extra: Additional CLI arguments passed directly to claude
        on_output: Callback for each stdout line (stderr is not streamed)
        timeout: Optional timeout in seconds (defaults to AUTO_PRD_CLAUDE_TIMEOUT_SECONDS)

    Returns:
        Tuple of (stdout, stderr) containing all accumulated output

    Raises:
        PermissionError: If allow_unsafe_execution is False and dry_run is False
        FileNotFoundError: If the claude executable is not found in PATH
        OSError: If running on Windows (fcntl not available)
        subprocess.CalledProcessError: If claude returns a non-zero exit code
        subprocess.TimeoutExpired: If execution exceeds the timeout
    """
    # Platform check - fcntl is Unix-only
    if sys.platform == "win32":
        raise OSError(
            "claude_exec_streaming requires Unix fcntl module for non-blocking I/O. "
            "Use claude_exec on Windows systems."
        )
    allow_flag = _resolve_unsafe_flag(
        allow_unsafe_execution, yolo, "claude_exec_streaming"
    )
    if not allow_flag and not dry_run:
        raise PermissionError(
            "Claude executor requires allow_unsafe_execution=True to bypass permissions."
        )
    os.environ.setdefault("CI", "1")
    if allow_flag:
        verify_unsafe_execution_ready()

    args = _build_claude_args(allow_flag, model, enable_search, extra)
    if dry_run:
        logger.info("Dry run enabled; skipping Claude execution. Args: %s", args)
        return "DRY_RUN", ""

    if not shutil.which(args[0]):
        raise FileNotFoundError(f"Command not found: {args[0]}")

    # Sanitize args to prevent shell injection via scrub_cli_text.
    # This mirrors run_cmd's sanitize_args=True behavior for consistency.
    sanitized_args = [scrub_cli_text(arg) for arg in args]
    if args != sanitized_args:
        logger.debug(
            "Sanitized %d args before Popen (original vs sanitized): %s -> %s",
            sum(1 for a, s in zip(args, sanitized_args) if a != s),
            args,
            sanitized_args,
        )

    # Resolve timeout - use parameter, then environment variable, then None (no timeout)
    effective_timeout = timeout if timeout is not None else get_claude_exec_timeout()
    start_time = time.monotonic()

    env = env_with_zsh({})
    env["PYTHONUNBUFFERED"] = "1"

    def default_output_handler(line: str) -> None:
        # Simple print for default handler; callers provide their own formatting via on_output
        print(line, flush=True)

    output_handler = on_output or default_output_handler

    proc = subprocess.Popen(
        sanitized_args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=repo_root,
        env=env,
        text=True,
        bufsize=1,
    )

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    # Send prompt and close stdin
    if proc.stdin:
        try:
            proc.stdin.write(prompt)
            proc.stdin.close()
        except BrokenPipeError:
            # Process terminated before reading input - this is an error condition.
            # Log detailed diagnostic info for debugging, but keep user message simple.
            logger.error(
                "BrokenPipeError: Claude process terminated before reading input "
                "(prompt_length=%d, command=%s)",
                len(prompt),
                sanitized_args[0],  # Log only executable name, not full args
            )
            proc.wait()
            # Try to capture any stderr the process wrote before dying
            captured_stderr = ""
            if proc.stderr:
                try:
                    captured_stderr = proc.stderr.read() or ""
                except Exception as stderr_exc:
                    logger.warning(
                        "Failed to capture stderr after BrokenPipeError: %s (%s)",
                        stderr_exc,
                        type(stderr_exc).__name__,
                    )
                proc.stderr.close()
            if proc.stdout:
                proc.stdout.close()
            # User-facing error message - simple and actionable
            error_msg = "Claude process terminated unexpectedly before reading input"
            if captured_stderr:
                error_msg = f"{error_msg}. Stderr: {captured_stderr}"
            raise subprocess.CalledProcessError(
                proc.returncode or -1,
                sanitized_args,
                output="".encode(),
                stderr=error_msg.encode(),
            )

    # Set up non-blocking I/O
    try:
        if proc.stdout:
            _set_nonblocking(proc.stdout.fileno())
        if proc.stderr:
            _set_nonblocking(proc.stderr.fileno())
    except OSError:
        # Clean up process resources before re-raising
        proc.kill()
        proc.wait()
        if proc.stdout:
            proc.stdout.close()
        if proc.stderr:
            proc.stderr.close()
        raise

    stdout_buffer = ""
    stderr_buffer = ""

    # Track I/O errors for surfacing at the end
    io_errors: list[tuple[str, int | None, str]] = []
    select_error_occurred = False

    # Track fds that have reached EOF to avoid infinite loop.
    # When a process exits, its pipes still exist as file objects (not None),
    # but select() returns them as "readable" with EOF. Without tracking EOF,
    # the loop would spin forever: read empty string -> continue -> select -> repeat.
    eof_fds: set = set()

    # Stream output in real-time
    while True:
        # Check timeout only when a timeout is configured.
        # The time.monotonic() call is inside this conditional to avoid
        # unnecessary computation on every loop iteration when no timeout is set.
        if effective_timeout is not None:
            elapsed = time.monotonic() - start_time
            if elapsed > effective_timeout:
                stdout_so_far = "\n".join(stdout_lines)
                stderr_so_far = "\n".join(stderr_lines)
                logger.error(
                    "Claude execution timed out after %d seconds (limit: %d). "
                    "Partial stdout (%d lines): %s",
                    int(elapsed),
                    effective_timeout,
                    len(stdout_lines),
                    (
                        stdout_so_far[:2000]
                        if len(stdout_so_far) > 2000
                        else stdout_so_far
                    ),
                )
                if stderr_so_far:
                    logger.error("Partial stderr at timeout: %s", stderr_so_far[:1000])
                proc.kill()
                proc.wait()
                if proc.stdout:
                    proc.stdout.close()
                if proc.stderr:
                    proc.stderr.close()
                exc = subprocess.TimeoutExpired(sanitized_args, effective_timeout)
                exc.stdout = stdout_so_far.encode()
                exc.stderr = stderr_so_far.encode()
                raise exc

        ret = proc.poll()
        # Exclude fds that have reached EOF - they would cause select to return
        # immediately with nothing to read, spinning the loop forever
        readable_fds = [
            fd
            for fd in (proc.stdout, proc.stderr)
            if fd is not None and fd not in eof_fds
        ]

        if ret is not None and not readable_fds:
            break

        try:
            readable, _, _ = select.select(
                readable_fds, [], [], STREAMING_SELECT_TIMEOUT_SECONDS
            )
        except ValueError as e:
            # ValueError indicates invalid arguments to select() (e.g., negative timeout,
            # invalid fd). This is a programming error, not a signal interrupt, so it
            # cannot be recovered by retry. Log and exit the streaming loop.
            logger.error(
                "select() raised ValueError (invalid arguments): %s - "
                "stream reading terminated early, output may be incomplete",
                e,
            )
            select_error_occurred = True
            # Attempt to drain any remaining buffered data before breaking
            for fd in readable_fds:
                try:
                    remaining = fd.read()
                    if remaining:
                        if fd == proc.stdout:
                            stdout_buffer += remaining
                        elif fd == proc.stderr:
                            stderr_buffer += remaining
                except Exception:
                    pass  # Best effort drain
            break
        except OSError as e:
            # EINTR can be retried (interrupted by signal)
            if e.errno == errno.EINTR:
                continue
            # Other select() failures are serious - log at ERROR level
            logger.error(
                "select() failed unexpectedly (errno=%s): %s - "
                "stream reading terminated early, output may be incomplete",
                e.errno,
                e,
            )
            select_error_occurred = True
            # Attempt to drain any remaining buffered data before breaking
            for fd in readable_fds:
                try:
                    remaining = fd.read()
                    if remaining:
                        if fd == proc.stdout:
                            stdout_buffer += remaining
                        elif fd == proc.stderr:
                            stderr_buffer += remaining
                except Exception:
                    pass  # Best effort drain
            break

        for fd in readable:
            try:
                chunk = fd.read(STREAMING_READ_CHUNK_SIZE)
                if not chunk:
                    # EOF reached - mark this fd so we don't select on it again.
                    # This prevents the infinite loop where select returns immediately
                    # with "readable" fds that only have EOF available.
                    eof_fds.add(fd)
                    continue
                if fd == proc.stdout:
                    stdout_buffer += chunk
                    stdout_buffer = _process_buffer(
                        stdout_buffer, stdout_lines, output_handler
                    )
                elif fd == proc.stderr:
                    stderr_buffer += chunk
                    stderr_buffer = _process_buffer(stderr_buffer, stderr_lines)
            except (IOError, OSError) as e:
                # EAGAIN/EWOULDBLOCK are expected with non-blocking I/O
                if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                    continue
                # Other errors are unexpected - log and track for later surfacing
                fd_name = "stdout" if fd == proc.stdout else "stderr"
                logger.error(
                    "I/O error reading from Claude process (fd=%s, errno=%s): %s - "
                    "OUTPUT MAY BE INCOMPLETE",
                    fd_name,
                    e.errno,
                    e,
                )
                io_errors.append((fd_name, e.errno, str(e)))
                # Notify user immediately of potential data loss
                print(
                    f"  [WARNING] I/O error on {fd_name} - some output may be missing",
                    flush=True,
                )
                # Mark fd as EOF to exclude it from subsequent select() calls.
                # This prevents repeated errors from the same fd - once a non-transient
                # I/O error occurs, continuing to read from that fd is unlikely to succeed.
                # The fd is excluded from readable_fds on the next loop iteration via the
                # list comprehension that filters out eof_fds.
                eof_fds.add(fd)

        if ret is not None and not readable:
            break

    # Flush remaining buffers.
    # Note: If the process output did not end with a newline, the final line
    # is incomplete (i.e., the process ended mid-line or the final line was
    # intentionally unterminated). We treat this as complete for final output
    # purposes since the process has exited and no more data will arrive.
    if stdout_buffer:
        # Final line - may be incomplete if buffer didn't end with newline
        stdout_lines.append(stdout_buffer)
        output_handler(stdout_buffer)
    if stderr_buffer:
        # Final line - may be incomplete if buffer didn't end with newline
        stderr_lines.append(stderr_buffer)

    proc.wait()

    # Explicitly close file descriptors
    if proc.stdout:
        proc.stdout.close()
    if proc.stderr:
        proc.stderr.close()

    stdout_text = "\n".join(stdout_lines)
    stderr_text = "\n".join(stderr_lines)

    # Surface any I/O or select errors that occurred during streaming
    if io_errors:
        logger.error(
            "Claude execution completed with %d I/O errors - output may be incomplete: %s",
            len(io_errors),
            io_errors,
        )
    if select_error_occurred:
        logger.error(
            "Claude execution completed after select() failure - output may be incomplete"
        )

    if proc.returncode != 0:
        raise subprocess.CalledProcessError(
            proc.returncode,
            sanitized_args,
            output=stdout_text.encode(),
            stderr=stderr_text.encode(),
        )

    if not stdout_text.strip() and stderr_text.strip():
        logger.warning(
            "Claude returned empty stdout. Stderr content: %s",
            stderr_text[:500] if len(stderr_text) > 500 else stderr_text,
        )

    return stdout_text, stderr_text
