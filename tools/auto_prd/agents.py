"""Integrations with external agents (Codex, CodeRabbit, Claude)."""

from __future__ import annotations

import errno
import os
import random
import re
import select
import subprocess
import sys
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Callable, Optional

from .command import (
    run_cmd,
    verify_unsafe_execution_ready,
    popen_streaming,
    validate_stdin,
)
from .logging_utils import logger
from .utils import extract_called_process_error_details

# fcntl is Unix-only; import conditionally to allow module import on Windows.
# On Windows, fcntl will be None and streaming functions will raise OSError.
try:
    import fcntl  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover (Windows)
    fcntl = None  # type: ignore[assignment]

RATE_LIMIT_JITTER_MIN = -3
RATE_LIMIT_JITTER_MAX = 3
RATE_LIMIT_MIN_SLEEP_SECONDS = 5
RATE_LIMIT_MAX_SLEEP_SECONDS = 900
CODERABBIT_PROMPT_TIMEOUT_SECONDS = 900

# I/O buffer and polling constants for claude_exec_streaming
# These values can be overridden via environment variables for performance tuning.


def _get_streaming_chunk_size() -> int:
    """Get the streaming read chunk size from environment, default 4096 bytes.

    The default 4KB chunk size balances memory usage with system call overhead
    for typical streaming scenarios.
    """
    raw = os.getenv("AUTO_PRD_STREAMING_CHUNK_SIZE")
    if raw is None:
        return 4096
    try:
        val = int(raw)
        if val > 0:
            return val
        logger.warning(
            "AUTO_PRD_STREAMING_CHUNK_SIZE must be > 0, got %r; using default 4096", raw
        )
        return 4096
    except ValueError:
        logger.warning(
            "Invalid AUTO_PRD_STREAMING_CHUNK_SIZE value %r; using default 4096", raw
        )
        return 4096


def _get_streaming_poll_timeout() -> float:
    """Get the streaming select poll timeout from environment, default 0.1 seconds.

    The default 100ms timeout provides a balance between responsive streaming
    and CPU efficiency. Lower values increase responsiveness but consume more CPU.
    """
    raw = os.getenv("AUTO_PRD_STREAMING_POLL_TIMEOUT")
    if raw is None:
        return 0.1
    try:
        val = float(raw)
        if val > 0:
            return val
        logger.warning(
            "AUTO_PRD_STREAMING_POLL_TIMEOUT must be > 0, got %r; using default 0.1",
            raw,
        )
        return 0.1
    except ValueError:
        logger.warning(
            "Invalid AUTO_PRD_STREAMING_POLL_TIMEOUT value %r; using default 0.1", raw
        )
        return 0.1


STREAMING_READ_CHUNK_SIZE = _get_streaming_chunk_size()
STREAMING_SELECT_TIMEOUT_SECONDS = _get_streaming_poll_timeout()


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
            "claude_exec: requires allow_unsafe_execution=True to bypass permissions."
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

    # Log warning if stdout is empty but stderr has content. This pattern may indicate:
    # - Rate limiting (API returns error in stderr but no output)
    # - Process crashed after partial execution
    # - Configuration issues preventing normal output
    if not out.strip() and stderr.strip():
        logger.warning(
            "Claude returned empty stdout. Stderr content: %s",
            stderr[:500] if len(stderr) > 500 else stderr,
        )

    return out, stderr


def _set_nonblocking(fd: int) -> None:
    """Set a file descriptor to non-blocking mode.

    Raises:
        OSError: If fcntl is not available (Windows) or fcntl operations fail.
    """
    if fcntl is None:
        raise OSError("Non-blocking I/O requires fcntl (Unix-only).")
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
    appending each line to the `lines` list in place and optionally calling
    `output_handler` for each line. The remaining incomplete line (if any) is
    returned for subsequent buffering.

    Args:
        buffer: Input buffer potentially containing newline-terminated lines.
        lines: List to append complete lines to (in/out parameter, modified in place).
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


def _drain_fds_best_effort(
    fds: list,
    proc_stdout,
    proc_stderr,
    stdout_buffer: str,
    stderr_buffer: str,
) -> tuple[str, str]:
    """Best-effort drain of file descriptors into buffers.

    Used during error recovery to capture any remaining data before breaking
    out of the streaming loop. Errors are logged at debug level since this
    is a best-effort operation during abnormal termination.

    Args:
        fds: List of file descriptors to drain.
        proc_stdout: The process stdout file object for comparison.
        proc_stderr: The process stderr file object for comparison.
        stdout_buffer: Current stdout buffer contents.
        stderr_buffer: Current stderr buffer contents.

    Returns:
        Tuple of (updated_stdout_buffer, updated_stderr_buffer).
    """
    for fd in fds:
        try:
            if fd.closed:
                continue
            remaining = fd.read()
            if remaining:
                if fd == proc_stdout:
                    stdout_buffer += remaining
                elif fd == proc_stderr:
                    stderr_buffer += remaining
        except Exception as drain_exc:
            # Log at debug level - this is best-effort recovery during error handling
            logger.debug(
                "Best-effort drain failed for fd (expected during error recovery): %s",
                drain_exc,
            )
    return stdout_buffer, stderr_buffer


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

    Example:
        >>> def my_handler(line: str) -> None:
        ...     print(f"[claude] {line}", flush=True)
        ...
        >>> stdout, stderr = claude_exec_streaming(
        ...     prompt="Explain this code",
        ...     repo_root=Path("/path/to/repo"),
        ...     allow_unsafe_execution=True,
        ...     on_output=my_handler,  # Called for each line as it arrives
        ...     timeout=300,  # 5 minute timeout
        ... )

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
        Tuple of (stdout, stderr) containing all accumulated output.
        Note: Unlike claude_exec which preserves exact output formatting,
        this function normalizes line endings by joining lines with single
        newlines. Trailing newlines from the original output are not preserved.

    Raises:
        PermissionError: If allow_unsafe_execution is False and dry_run is False
        FileNotFoundError: If the claude executable is not found in PATH
        OSError: If running on Windows (fcntl not available)
        subprocess.CalledProcessError: If claude returns a non-zero exit code
        subprocess.TimeoutExpired: If execution exceeds the timeout
    """
    # Platform check - fcntl is Unix-only
    if fcntl is None or sys.platform == "win32":
        raise OSError(
            "claude_exec_streaming requires Unix fcntl module for non-blocking I/O. "
            "Use claude_exec on Windows systems."
        )
    allow_flag = _resolve_unsafe_flag(
        allow_unsafe_execution, yolo, "claude_exec_streaming"
    )
    if not allow_flag and not dry_run:
        raise PermissionError(
            "claude_exec_streaming: requires allow_unsafe_execution=True to bypass permissions."
        )
    os.environ.setdefault("CI", "1")
    if allow_flag:
        verify_unsafe_execution_ready()

    args = _build_claude_args(allow_flag, model, enable_search, extra)
    if dry_run:
        logger.info("Dry run enabled; skipping Claude execution. Args: %s", args)
        return "DRY_RUN", ""

    # Validate stdin before spawning subprocess - applies same safety checks as run_cmd
    # (size limits, control character filtering) to prevent hangs or unexpected failures.
    validate_stdin(prompt)

    # Resolve timeout - use parameter, then environment variable, then None (no timeout)
    effective_timeout = timeout if timeout is not None else get_claude_exec_timeout()
    start_time = time.monotonic()

    output_handler = on_output or (lambda line: print(line, flush=True))

    # Use popen_streaming from command.py for policy-compliant subprocess spawning.
    # This centralizes argument sanitization, validation, and environment setup.
    proc, sanitized_args = popen_streaming(args, cwd=repo_root)

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
            # Determine appropriate return code:
            # - Use actual returncode if process exited normally
            # - Use 141 (SIGPIPE on Unix) if process was killed by pipe closure
            if proc.returncode is None:
                returncode = 141  # SIGPIPE on Unix
            else:
                returncode = proc.returncode
            raise subprocess.CalledProcessError(
                returncode,
                sanitized_args,
                output=b"",
                stderr=error_msg.encode(),
            ) from None

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
                # Include any partial data still in buffers (unterminated lines)
                # to preserve output that arrived before timeout
                all_stdout = stdout_lines.copy()
                if stdout_buffer:
                    all_stdout.append(stdout_buffer)
                all_stderr = stderr_lines.copy()
                if stderr_buffer:
                    all_stderr.append(stderr_buffer)
                stdout_so_far = "\n".join(all_stdout)
                stderr_so_far = "\n".join(all_stderr)
                logger.error(
                    "Claude execution timed out after %d seconds (limit: %d). "
                    "Partial stdout (%d lines, %d buffered chars): %s",
                    int(elapsed),
                    effective_timeout,
                    len(stdout_lines),
                    len(stdout_buffer),
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
            stdout_buffer, stderr_buffer = _drain_fds_best_effort(
                readable_fds, proc.stdout, proc.stderr, stdout_buffer, stderr_buffer
            )
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
            stdout_buffer, stderr_buffer = _drain_fds_best_effort(
                readable_fds, proc.stdout, proc.stderr, stdout_buffer, stderr_buffer
            )
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
    # If process output didn't end with a newline, treat remaining buffer as the
    # complete final line since the process has exited and no more data will arrive.
    if stdout_buffer:
        stdout_lines.append(stdout_buffer)
        output_handler(stdout_buffer)
    if stderr_buffer:
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
