"""Command availability checks."""

from __future__ import annotations

import shutil
import subprocess

from .command import run_cmd
from .constants import COMMAND_VERIFICATION_TIMEOUT_SECONDS


def require_cmd(name: str) -> None:
    cmd_path = shutil.which(name)
    if cmd_path is None:
        raise RuntimeError(f"'{name}' command not found - not installed or not on PATH.")

    version_checks = [[name, "--version"], [name, "version"], [name, "--help"]]

    for args in version_checks:
        try:
            run_cmd(args, check=True, capture=True, timeout=10)
            return
        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            subprocess.TimeoutExpired,
        ):
            continue

    try:
        stdout, stderr, returncode = run_cmd(
            [name],
            check=False,
            capture=True,
            timeout=COMMAND_VERIFICATION_TIMEOUT_SECONDS,
        )
        if returncode > 2:
            print(
                f"Warning: command '{name}' returned unusual exit code {returncode}, "
                "continuing anyway."
            )
        return
    except FileNotFoundError:
        raise RuntimeError(f"'{name}' command not found - not installed or not on PATH.")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        print(
            f"Command '{name}' exists but failed execution (this may be expected if it requires arguments): {exc}"
        )
