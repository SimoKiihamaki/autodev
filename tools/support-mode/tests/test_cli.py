"""Basic CLI tests."""

import subprocess
import sys

from support_mode import __version__


def test_cli_help():
    result = subprocess.run(
        [sys.executable, "-m", "support_mode", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Continuous monitoring" in result.stdout


def test_cli_version():
    result = subprocess.run(
        [sys.executable, "-m", "support_mode", "--version"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    # Version is sourced from __version__ in support_mode/__init__.py
    assert __version__ in result.stdout


def test_cli_requires_prd():
    result = subprocess.run(
        [sys.executable, "-m", "support_mode"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "required: --prd" in result.stderr
