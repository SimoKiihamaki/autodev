"""Tests for command execution module."""

import subprocess
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
    try:
        run_cmd(["nonexistent_command_xyz"])
        assert False, "Should have raised FileNotFoundError"
    except FileNotFoundError:
        # Expected exception - test passes if we reach here
        pass


def test_command_result_tuple_unpacking():
    """Test backward-compatible tuple unpacking."""
    result = CommandResult(stdout="out", stderr="err", exit_code=0)
    stdout, stderr, exit_code = result
    assert stdout == "out"
    assert stderr == "err"
    assert exit_code == 0
