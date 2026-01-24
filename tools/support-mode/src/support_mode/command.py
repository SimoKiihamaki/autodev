"""Simplified command execution for support-mode."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CommandResult:
    """Result of command execution.

    Simplified version for support-mode - removes agent-specific
    features since this tool is read-only monitoring only.

    Examples:
        # Named attribute access (preferred)
        result = run_cmd(["git", "status"], check=False)
        if result.is_success():
            print(result.stdout)

        # Tuple unpacking (backward compatible)
        stdout, stderr, exit_code = run_cmd(["git", "status"], check=False)
        if exit_code == 0:
            print(stdout)
    """

    stdout: str
    stderr: str
    exit_code: int

    def is_success(self) -> bool:
        """Check if command succeeded (exit code 0).

        Returns:
            True if exit_code is 0, False otherwise.
        """
        return self.exit_code == 0

    def __iter__(self):
        """Enable backward-compatible tuple unpacking.

        Allows existing code to continue working:
            stdout, stderr, exit_code = result

        Yields:
            Values in order: stdout, stderr, exit_code
        """
        return iter((self.stdout, self.stderr, self.exit_code))


def run_cmd(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    capture: bool = True,
    timeout: int | None = None,
) -> CommandResult:
    """Execute a command safely.

    Simplified version for support-mode - removes agent-specific
    validation since this tool is read-only monitoring only.

    Args:
        cmd: Command sequence to execute.
        cwd: Working directory for the command.
        check: If True, raise CalledProcessError on non-zero exit.
        capture: If True, capture stdout/stderr.
        timeout: Timeout in seconds for command execution.

    Returns:
        CommandResult containing stdout, stderr, and exit_code fields.
        Supports backward-compatible tuple unpacking: stdout, stderr, exit_code = result.

    Raises:
        CalledProcessError: If check=True and command fails.
        FileNotFoundError: If command executable not found.
        TimeoutExpired: If timeout is reached.
        ValueError: If cmd is empty.
    """
    # Basic safety: ensure cmd is non-empty and executable exists
    if not cmd:
        raise ValueError("cmd must be a non-empty list of strings")

    # Honor cwd when validating command paths.
    # Path-like commands (relative or absolute) are resolved against cwd,
    # bare command names fall back to PATH search via shutil.which.
    cmd_path = Path(cmd[0])
    if cmd_path.is_absolute() or len(cmd_path.parts) > 1:
        # Path-like command: resolve against cwd and check if executable
        base = Path(cwd) if cwd is not None else Path.cwd()
        resolved = (base / cmd_path).resolve()
        if not (resolved.exists() and os.access(resolved, os.X_OK)):
            raise FileNotFoundError(cmd[0])
    else:
        # Bare command name: search PATH
        exe = shutil.which(cmd[0])
        if not exe:
            raise FileNotFoundError(cmd[0])

    # Execute
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=capture,
        text=True,
        check=False,
        timeout=timeout,
    )

    # Normalize stdout/stderr to ensure they're always strings
    # (when capture=False, subprocess.run returns None for these)
    cmd_result = CommandResult(
        stdout=result.stdout or "",
        stderr=result.stderr or "",
        exit_code=result.returncode,
    )

    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, cmd, result.stdout, result.stderr
        )

    return cmd_result
