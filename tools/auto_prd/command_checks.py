"""Command availability checks."""

from __future__ import annotations

import shutil
import subprocess

from .command import run_cmd
from .constants import COMMAND_VERIFICATION_TIMEOUT_SECONDS
from .logging_utils import logger


def require_cmd(name: str) -> None:
    cmd_path = shutil.which(name)
    if cmd_path is None:
        raise RuntimeError(f"'{name}' command not found - not installed or not on PATH.") from None

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
        _, _, returncode = run_cmd(
            [name],
            check=False,
            capture=True,
            timeout=COMMAND_VERIFICATION_TIMEOUT_SECONDS,
        )
        if returncode > 2:
            logger.warning("Command '%s' returned unusual exit code %s; continuing.", name, returncode)
        return
    except FileNotFoundError as exc:
        raise RuntimeError(f"'{name}' command not found - not installed or not on PATH.") from exc
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        logger.warning(
            "Command '%s' exists but failed execution (may require arguments): %s",
            name,
            exc,
        )
        return
