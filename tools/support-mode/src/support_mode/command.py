"""Simplified command execution for support-mode."""

from __future__ import annotations

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
) -> CommandResult:
    """Execute a command safely.

    Simplified version for support-mode - removes agent-specific
    validation since this tool is read-only monitoring only.

    Args:
        cmd: Command sequence to execute.
        cwd: Working directory for the command.
        check: If True, raise CalledProcessError on non-zero exit.
        capture: If True, capture stdout/stderr.

    Returns:
        CommandResult containing stdout, stderr, and exit_code fields.
        Supports backward-compatible tuple unpacking: stdout, stderr, exit_code = result.

    Raises:
        CalledProcessError: If check=True and command fails.
        FileNotFoundError: If command executable not found.
    """
    # Basic safety: ensure executable exists
    exe = shutil.which(cmd[0])
    if not exe:
        raise FileNotFoundError(f"Command not found: {cmd[0]}")

    # Execute
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=capture,
        text=True,
        check=False,
    )

    cmd_result = CommandResult(
        stdout=result.stdout,
        stderr=result.stderr,
        exit_code=result.returncode,
    )

    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, cmd, result.stdout, result.stderr
        )

    return cmd_result
