"""Shell command execution helpers with safety checks."""

from __future__ import annotations

import logging
import os
import random
import re
import shlex
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Sequence
from typing import Optional

from .constants import (
    COMMAND_ALLOWLIST,
    SAFE_CWD_ROOTS,
    SAFE_ENV_VAR,
    SAFE_STDIN_ALLOWED_CTRL,
    STDIN_MAX_BYTES,
    UNSAFE_ARG_CHARS,
    require_zsh,
)
from .logging_utils import decode_output, logger, truncate_for_log


REDACT_EQ_PATTERN = re.compile(r"(?i)^(?P<prefix>[-]{1,2})?(?P<key>[a-z0-9_]+)=(?P<value>.+)$")
SENSITIVE_KEYS = {
    "token",
    "password",
    "secret",
    "apikey",
    "api_key",
    "key",
    "access_token",
}


def sanitize_args(args: Sequence[str]) -> list[str]:
    sanitized: list[str] = []
    skip_next = False
    for idx, arg in enumerate(args):
        if skip_next:
            skip_next = False
            continue

        # Treat shell scripts passed via -c/-lc as sensitive because they can embed secrets.
        if arg in ("-c", "-lc") and idx + 1 < len(args):
            sanitized.append(arg)
            sanitized.append("<REDACTED_SCRIPT>")
            logger.debug("Sanitizing inline shell script from logs to avoid leaking sensitive input")
            skip_next = True
            continue

        match = REDACT_EQ_PATTERN.match(arg)
        if match:
            key_lower = match.group("key").lower()
            if key_lower in SENSITIVE_KEYS:
                prefix = match.group("prefix") or ""
                sanitized.append(f"{prefix}{match.group('key')}=<REDACTED>")
                continue

        stripped = arg.lstrip("-")
        normalized = stripped.lower().replace("-", "_")
        if normalized in SENSITIVE_KEYS:
            sanitized.append(arg)
            if idx + 1 < len(args):
                sanitized.append("<REDACTED>")
                skip_next = True
            continue

        sanitized.append(arg)

    return sanitized


def register_safe_cwd(path: Path) -> None:
    SAFE_CWD_ROOTS.add(path.resolve())


def is_within(path: Path, root: Path) -> bool:
    try:
        path_resolved = path.resolve(strict=True)
    except FileNotFoundError:
        path_resolved = path.resolve()
    try:
        root_resolved = root.resolve(strict=True)
    except FileNotFoundError:
        root_resolved = root.resolve()
    return path_resolved == root_resolved or root_resolved in path_resolved.parents


def validate_command_args(cmd: Sequence[str]) -> None:
    if not isinstance(cmd, Sequence) or isinstance(cmd, (str, bytes)) or not cmd:
        raise ValueError("cmd must be a non-empty sequence of strings")
    for arg in cmd:
        if not isinstance(arg, str):
            raise TypeError("command arguments must be strings")
        if any(char in arg for char in UNSAFE_ARG_CHARS):
            raise ValueError(f"cmd argument contains unsafe shell metacharacters: {arg!r}")
    binary = cmd[0]
    if binary in COMMAND_ALLOWLIST:
        return
    binary_path = Path(binary)
    if binary_path.is_absolute() and binary_path.exists():
        for root in SAFE_CWD_ROOTS:
            if is_within(binary_path, root):
                return
    raise SystemExit(f"Command not allowed: {binary}")


def validate_cwd(cwd: Optional[Path]) -> None:
    if cwd is None:
        return
    cwd = cwd.resolve()
    for root in SAFE_CWD_ROOTS:
        if is_within(cwd, root):
            return
    raise SystemExit(f"CWD {cwd} outside registered safe roots: {SAFE_CWD_ROOTS}")


def validate_stdin(stdin: Optional[str]) -> None:
    if stdin is None:
        return
    encoded = stdin.encode("utf-8")
    if len(encoded) > STDIN_MAX_BYTES:
        raise SystemExit("stdin payload too large; pass via file or truncate")
    for byte in encoded:
        if byte < 32 and byte not in SAFE_STDIN_ALLOWED_CTRL:
            raise SystemExit("unsafe control characters in stdin payload")


def validate_extra_env(extra_env: Optional[dict]) -> None:
    if not extra_env:
        return
    for key, value in extra_env.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise SystemExit(f"Environment variable keys and values must be strings: {key}={value!r}")
        if "\n" in key or "\n" in value:
            raise SystemExit(f"Environment variable keys and values must not contain newlines: {key}={value!r}")


def verify_unsafe_execution_ready() -> None:
    if os.environ.get(SAFE_ENV_VAR) == "1":
        return
    raise SystemExit(
        "AUTO_PRD_ALLOW_UNSAFE_EXECUTION=1 is required because the automation spawns child commands."
    )


def env_with_zsh(extra: dict | None = None) -> dict[str, str]:
    env = os.environ.copy()
    zsh_path = require_zsh()
    env.update({"SHELL": zsh_path, "AUTO_PRD_SHELL": zsh_path})
    if extra:
        env.update(extra)
    return env


def ensure_claude_debug_dir() -> Optional[Path]:
    existing = os.getenv("CLAUDE_CODE_DEBUG_LOGS_DIR")
    candidates: list[Path] = []
    if existing:
        try:
            candidates.append(Path(existing).expanduser())
        except (ValueError, RuntimeError, OSError) as exc:
            logger.warning(
                "Failed to expand CLAUDE_CODE_DEBUG_LOGS_DIR=%r: %s. Falling back to other candidates.",
                existing,
                exc,
            )
    candidates += [
        Path(tempfile.gettempdir()) / "claude_code_logs",
        Path.cwd() / ".claude-debug",
    ]
    for base in candidates:
        try:
            base.mkdir(parents=True, exist_ok=True)
            if os.access(base, os.W_OK):
                now_iso = datetime.now(timezone.utc).isoformat()
                rand_str = f"{random.getrandbits(64):016x}"
                test_content = f"writecheck-{os.getpid()}-{now_iso}-{rand_str}"
                test: Optional[Path] = None
                try:
                    with tempfile.NamedTemporaryFile(
                        mode="w+",
                        encoding="utf-8",
                        dir=base,
                        prefix=".writecheck_",
                        suffix=".tmp",
                        delete=False,
                    ) as tmpf:
                        tmpf.write(test_content)
                        tmpf.flush()
                        os.fsync(tmpf.fileno())
                        tmpf_name = tmpf.name
                    test = Path(tmpf_name)
                    with open(tmpf_name, "r", encoding="utf-8") as verify_f:
                        read_back = verify_f.read()
                    if read_back != test_content:
                        logger.warning(
                            "Write verification failed for %s: expected %r, got %r",
                            base,
                            test_content,
                            read_back,
                        )
                        continue
                finally:
                    if test and test.exists():
                        test.unlink(missing_ok=True)
                os.environ["CLAUDE_CODE_DEBUG_LOGS_DIR"] = str(base)
                return base
        except OSError:
            continue
    return None


def run_cmd(
    cmd: list[str],
    *,
    cwd: Optional[Path] = None,
    check: bool = True,
    capture: bool = True,
    timeout: Optional[int] = None,
    extra_env: Optional[dict] = None,
    stdin: Optional[str] = None,
) -> tuple[str, str, int]:
    validate_command_args(cmd)
    validate_cwd(cwd)
    validate_stdin(stdin)
    validate_extra_env(extra_env)
    exe = shutil.which(cmd[0])
    if not exe:
        raise FileNotFoundError(f"Command not found: {cmd[0]}")
    env = env_with_zsh(extra_env)
    cmd_display = shlex.join(sanitize_args(cmd))
    logger.info("Running command: %s", cmd_display)
    if cwd:
        logger.debug("Command cwd: %s", cwd)
    if timeout is not None:
        logger.debug("Command timeout: %ss", timeout)
    stdin_bytes: Optional[bytes] = None
    if stdin is not None:
        stdin_bytes = stdin.encode("utf-8")
        logger.debug("Command stdin bytes: %s", len(stdin_bytes))
    start_time = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            check=False,
            capture_output=capture,
            text=False,
            timeout=timeout,
            env=env,
            input=stdin_bytes,
        )
    except Exception:
        duration = time.monotonic() - start_time
        logger.exception("Command execution error after %.2fs: %s", duration, cmd_display)
        raise
    duration = time.monotonic() - start_time
    stdout_bytes = proc.stdout or b""
    stderr_bytes = proc.stderr or b""
    stdout_text = decode_output(stdout_bytes)
    stderr_text = decode_output(stderr_bytes)
    if capture:
        if stdout_text:
            logger.debug("Command stdout: %s", truncate_for_log(stdout_text))
        if stderr_text:
            level = logging.ERROR if proc.returncode != 0 else logging.DEBUG
            logger.log(level, "Command stderr: %s", truncate_for_log(stderr_text))
    else:
        logger.debug("Command output not captured (capture=False)")
    if proc.returncode == 0:
        logger.info("Command succeeded in %.2fs: %s", duration, cmd_display)
    else:
        level = logging.ERROR if check else logging.WARNING
        logger.log(level, "Command exited with code %s after %.2fs: %s", proc.returncode, duration, cmd_display)
    if check and proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd, output=stdout_bytes, stderr=stderr_bytes)
    return stdout_text, stderr_text, proc.returncode


def run_sh(
    script: str,
    *,
    cwd: Optional[Path] = None,
    check: bool = True,
    capture: bool = True,
    timeout: Optional[int] = None,
    extra_env: Optional[dict] = None,
) -> tuple[str, str, int]:
    verify_unsafe_execution_ready()
    return run_cmd(
        [require_zsh(), "-lc", script],
        cwd=cwd,
        check=check,
        capture=capture,
        timeout=timeout,
        extra_env=extra_env,
    )
