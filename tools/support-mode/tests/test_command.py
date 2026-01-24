"""Tests for command execution module."""

import pytest
from support_mode.command import CommandResult, run_cmd


def test_run_cmd_success():
    """Test successful command execution."""
    result = run_cmd(["echo", "hello"])
    assert result.is_success()
    assert result.stdout.strip() == "hello"
    assert result.exit_code == 0


def test_run_cmd_failure():
    """Test command execution with non-zero exit."""
    result = run_cmd(["false"], check=False)
    assert not result.is_success()
    assert result.exit_code == 1


def test_run_cmd_not_found():
    """Test command not found error."""
    with pytest.raises(FileNotFoundError):
        run_cmd(["nonexistent_command_xyz"])


def test_command_result_tuple_unpacking():
    """Test backward-compatible tuple unpacking."""
    result = CommandResult(stdout="out", stderr="err", exit_code=0)
    stdout, stderr, exit_code = result
    assert stdout == "out"
    assert stderr == "err"
    assert exit_code == 0
