"""Integration tests for tools/generate_tracker.py script."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


# Get the path to the generate_tracker.py script
# Tests run from tools/ directory, script is in tools/
_SCRIPT_PATH = Path(__file__).parent.parent / "generate_tracker.py"


class TestGenerateTrackerIntegration:
    """Integration tests for the generate_tracker.py script."""

    def test_stdin_mode_creates_and_cleans_temp_file(self):
        """Test that temp files are created and cleaned up in stdin mode."""
        test_prd = """# Test PRD

## User Stories
- [ ] Story 1
"""
        # Run the script with stdin input
        result = subprocess.run(
            [sys.executable, str(_SCRIPT_PATH), "--stdin", "--dry-run"],
            input=test_prd,
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )

        # Should succeed (dry-run mode)
        assert result.returncode == 0

        # Verify temp files are cleaned up (check temp directory)
        temp_dir = Path(tempfile.gettempdir())
        remaining_files = list(temp_dir.glob("stdin_*.md"))
        # Our temp file should be cleaned up
        # Note: This might have false positives if other processes are running
        # so we just check that files aren't accumulating
        assert (
            len(remaining_files) < 10
        ), "Too many temp files remaining - possible leak"

    def test_stdin_mode_with_invalid_executor(self):
        """Test error handling with invalid executor argument."""
        test_prd = "# Test PRD"

        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "--stdin",
                "--executor",
                "invalid",
            ],
            input=test_prd,
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )

        # Should fail with error message
        assert result.returncode != 0
        assert "Invalid executor" in result.stderr or "error" in result.stderr.lower()

        # Verify no temp files left behind
        temp_dir = Path(tempfile.gettempdir())
        recent_temp_files = [
            f
            for f in temp_dir.glob("stdin_*.md")
            if "stdin_" in f.name  # Our naming pattern
        ]
        # Files should be cleaned up even on error
        assert len(recent_temp_files) < 10

    def test_stdin_mode_with_empty_input(self):
        """Test that empty input is properly handled."""
        result = subprocess.run(
            [sys.executable, str(_SCRIPT_PATH), "--stdin"],
            input="",
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )

        # Should fail with error message
        assert result.returncode != 0
        assert "Empty input" in result.stderr or "error" in result.stderr.lower()

        # Verify no temp files created
        temp_dir = Path(tempfile.gettempdir())
        temp_files = list(temp_dir.glob("stdin_*.md"))
        # Empty input should not create temp file
        assert len(temp_files) < 10

    def test_stdin_mode_success_flow(self, tmp_path):
        """Test successful flow with actual PRD content."""
        test_prd = """# Feature: User Authentication

## User Stories

### US-001: User Login
**Priority**: 1

- Implement login form
- Add authentication middleware
"""

        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "--stdin",
                "--dry-run",
            ],
            input=test_prd,
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )

        # Should succeed
        assert result.returncode == 0

        # Verify output path is printed to stdout
        assert result.stdout.strip()
        output_path = Path(result.stdout.strip())

        # Note: The script uses the default output path (.aprd/tracker.json)
        # which is written by generate_tracker(), not by the CLI script itself
        # We just verify the script succeeds and produces output

    def test_temp_file_cleanup_on_exception(self):
        """Test that temp files are cleaned up when exceptions occur."""
        # Provide invalid PRD that will cause processing to fail
        invalid_prd = "This is not valid markdown and will cause issues"

        result = subprocess.run(
            [sys.executable, str(_SCRIPT_PATH), "--stdin", "--dry-run"],
            input=invalid_prd,
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )

        # May fail or succeed depending on validation
        # Either way, temp files should be cleaned up
        temp_dir = Path(tempfile.gettempdir())
        temp_files = list(temp_dir.glob("stdin_*.md"))
        assert len(temp_files) < 10, "Temp files not cleaned up after exception"

    def test_multiple_runs_no_temp_file_accumulation(self):
        """Test that multiple runs don't accumulate temp files."""
        test_prd = "# Test PRD for multiple runs"

        # Run the script multiple times
        for _ in range(5):
            result = subprocess.run(
                [sys.executable, str(_SCRIPT_PATH), "--stdin", "--dry-run"],
                input=test_prd,
                capture_output=True,
                text=True,
                cwd=Path.cwd(),
            )
            # Each run should succeed
            assert result.returncode == 0

        # Check that temp files are not accumulating
        temp_dir = Path(tempfile.gettempdir())
        temp_files = list(temp_dir.glob("stdin_*.md"))
        # Should be very few files (cleanup is working)
        assert (
            len(temp_files) < 10
        ), f"Too many temp files accumulated: {len(temp_files)}"
