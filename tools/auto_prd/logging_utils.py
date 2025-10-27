"""Logging helpers shared across modules."""

from __future__ import annotations

import builtins
import io
import logging
import sys
import threading
from pathlib import Path

from .constants import (
    ACCEPTED_LOG_LEVELS,
    COMMAND_OUTPUT_LOG_LIMIT,
    LOG_FORMAT,
    PRINT_LOGGER_NAME,
)


logger = logging.getLogger("auto_prd")

CURRENT_LOG_PATH: Path | None = None
USER_LOG_LEVEL = logging.INFO
ORIGINAL_PRINT = builtins.print
PRINT_HOOK_INSTALLED = False
PRINT_HOOK_LOCK = threading.Lock()
SETUP_LOCK = threading.Lock()


def resolve_log_level(level_name: str) -> int:
    name = level_name.upper()
    if name == "WARN":
        name = "WARNING"
    level_value = getattr(logging, name, None)
    if isinstance(level_value, int):
        return level_value
    valid_levels = ", ".join(ACCEPTED_LOG_LEVELS)
    raise ValueError(
        f"Invalid log level: {level_name}. Valid levels are: {valid_levels}"
    )


def setup_file_logging(log_path: Path, level_name: str) -> None:
    global CURRENT_LOG_PATH, USER_LOG_LEVEL
    numeric_level = resolve_log_level(level_name)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        log_path.parent.chmod(0o700)
    except Exception:  # pragma: no cover - permissions vary by platform
        logger.debug("Unable to enforce permissions on %s", log_path.parent)

    with SETUP_LOCK:
        USER_LOG_LEVEL = numeric_level

        root_logger = logging.getLogger()
        paths_to_remove = {str(log_path)}
        if CURRENT_LOG_PATH:
            paths_to_remove.add(str(CURRENT_LOG_PATH))
        for handler in list(root_logger.handlers):
            base_filename = getattr(handler, "baseFilename", None)
            if (
                base_filename
                and base_filename in paths_to_remove
                and isinstance(handler, logging.FileHandler)
            ):
                root_logger.removeHandler(handler)
                try:
                    handler.close()
                except Exception:  # pragma: no cover - defensive close
                    logger.debug(
                        "Failed to close previous log handler for %s", base_filename
                    )

        root_logger.setLevel(numeric_level)

        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        root_logger.addHandler(file_handler)
        CURRENT_LOG_PATH = log_path
        logger.setLevel(numeric_level)

    try:
        log_path.chmod(0o600)
    except Exception:  # pragma: no cover - permissions vary by platform
        logger.debug("Unable to enforce permissions on %s", log_path)

    install_print_logger()


def format_print_message(*args, **kwargs) -> str:
    if not args and not kwargs:
        return ""
    sep = kwargs.get("sep", " ")
    end = kwargs.get("end", "\n")
    if end is None:
        end = ""
    message = sep.join(str(arg) for arg in args)
    return f"{message}{end}"


def ensure_line_buffering() -> None:
    """Ensure stdout/stderr are line-buffered when piped to prevent stalls."""
    import os

    # Set PYTHONUNBUFFERED early for maximum effect
    os.environ["PYTHONUNBUFFERED"] = "1"

    # Check if stdout is connected to a terminal
    if not sys.stdout.isatty():
        # stdout is piped, ensure line buffering
        try:
            # Reopen stdout with line buffering (Python 3.7+)
            sys.stdout.reconfigure(line_buffering=True)
        except (AttributeError, io.UnsupportedOperation):
            # Python < 3.7 fallback: already set PYTHONUNBUFFERED above
            pass

    if not sys.stderr.isatty():
        # stderr is piped, ensure line buffering
        try:
            sys.stderr.reconfigure(line_buffering=True)
        except (AttributeError, io.UnsupportedOperation):
            # Python < 3.7 fallback: already set PYTHONUNBUFFERED above
            pass


def initialize_output_buffering() -> None:
    """
    Initialize output buffering fixes as early as possible.
    This function should be called at application startup to prevent
    any stdout buffering issues when the process is piped.
    """
    ensure_line_buffering()


def install_print_logger() -> None:
    global PRINT_HOOK_INSTALLED
    if PRINT_HOOK_INSTALLED:
        return

    with PRINT_HOOK_LOCK:
        if PRINT_HOOK_INSTALLED:
            return

        # Ensure line buffering first
        ensure_line_buffering()

        print_logger = logging.getLogger(PRINT_LOGGER_NAME)
        print_logger.setLevel(logging.INFO)

        def tee_print(*args, **kwargs):
            message = format_print_message(*args, **kwargs)
            if message:
                stream = kwargs.get("file") or sys.stdout
                is_stderr = False
                try:
                    is_stderr = stream.fileno() == sys.stderr.fileno()
                except (AttributeError, ValueError, io.UnsupportedOperation):
                    is_stderr = stream is sys.stderr or stream is getattr(
                        sys, "__stderr__", None
                    )
                target_level = logging.WARNING if is_stderr else logging.INFO
                log_message = message[:-1] if message.endswith("\n") else message
                if log_message:
                    # Logging already appends its own newline, so trim the print newline to avoid doubles.
                    print_logger.log(target_level, log_message)

            # Force flush=True for all output to prevent buffering stalls
            kwargs["flush"] = True

            # Call original print
            ORIGINAL_PRINT(*args, **kwargs)

            # Additional explicit flush of the target stream for maximum reliability
            try:
                stream = kwargs.get("file") or sys.stdout
                if hasattr(stream, "flush"):
                    stream.flush()
            except Exception:
                # Ignore flush errors - print output already went through
                pass

        builtins.print = tee_print
        PRINT_HOOK_INSTALLED = True


def uninstall_print_logger() -> None:
    global PRINT_HOOK_INSTALLED
    with PRINT_HOOK_LOCK:
        if PRINT_HOOK_INSTALLED:
            builtins.print = ORIGINAL_PRINT
            PRINT_HOOK_INSTALLED = False


def truncate_for_log(text: str, limit: int = COMMAND_OUTPUT_LOG_LIMIT) -> str:
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    return f"{text[:limit]}... (truncated {omitted} chars)"


def decode_output(data: bytes) -> str:
    if not data:
        return ""
    return data.decode("utf-8", errors="replace")


def print_flush(*args, **kwargs) -> None:
    """Print with explicit flushing to ensure immediate output when piped."""
    kwargs["flush"] = True
    ORIGINAL_PRINT(*args, **kwargs)
