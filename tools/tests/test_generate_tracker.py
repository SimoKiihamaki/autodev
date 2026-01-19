"""Tests for tools/generate_tracker.py"""

import hashlib
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Import the function to test
from tools.generate_tracker import read_stdin_to_temp_file


class TestReadStdinToTempFile:
    """Test suite for read_stdin_to_temp_file function."""

    def test_read_stdin_to_temp_file_success(self):
        """Test successful reading from stdin and temp file creation."""
        test_content = "# Test PRD\n\nThis is a test PRD content."
        expected_hash = hashlib.sha256(test_content.encode()).hexdigest()[:16]

        # Mock stdin to provide test content
        with patch("sys.stdin.read", return_value=test_content):
            temp_path, content_hash = read_stdin_to_temp_file()

        # Verify the hash is correct
        assert content_hash == expected_hash

        # Verify the temp file exists
        assert temp_path.exists()

        # Verify the temp file contains the correct content
        actual_content = temp_path.read_text()
        assert actual_content == test_content

        # Verify file naming convention
        assert temp_path.suffix == ".md"
        assert f"stdin_{content_hash}_" in temp_path.name

        # Clean up
        temp_path.unlink()

    def test_read_stdin_to_temp_file_empty_input(self):
        """Test that empty input raises ValueError."""
        # Mock stdin to return empty string
        with patch("sys.stdin.read", return_value=""):
            with pytest.raises(ValueError, match="Empty input received from stdin"):
                read_stdin_to_temp_file()

    def test_read_stdin_to_temp_file_whitespace_only(self):
        """Test that whitespace-only input raises ValueError."""
        # Mock stdin to return whitespace
        with patch("sys.stdin.read", return_value="   \n\t  \n  "):
            with pytest.raises(ValueError, match="Empty input received from stdin"):
                read_stdin_to_temp_file()

    def test_read_stdin_to_temp_file_handle_closed(self):
        """Test that file handle is properly closed after function returns."""
        test_content = "# Test PRD"

        with patch("sys.stdin.read", return_value=test_content):
            temp_path, _ = read_stdin_to_temp_file()

        # Try to delete the file - should succeed because handle is closed
        # If the handle were still open, this might fail on Windows
        try:
            temp_path.unlink()
        except OSError as e:
            pytest.fail(f"Failed to unlink temp file (handle may not be closed): {e}")

    def test_read_stdin_to_temp_file_persistence(self):
        """Test that temp file persists after function returns (delete=False)."""
        test_content = "# Test PRD content that must persist"

        with patch("sys.stdin.read", return_value=test_content):
            temp_path, _ = read_stdin_to_temp_file()

        # File should still exist after function returns
        assert temp_path.exists()

        # File should be readable
        content = temp_path.read_text()
        assert content == test_content

        # Clean up
        temp_path.unlink()

    def test_read_stdin_to_temp_file_multiline_content(self):
        """Test handling of multiline content with special characters."""
        test_content = """# PRD Title

## Section 1
Content with special chars: @#$%^&*()

## Section 2
- List item 1
- List item 2
"""
        with patch("sys.stdin.read", return_value=test_content):
            temp_path, content_hash = read_stdin_to_temp_file()

        # Verify content is preserved exactly
        assert temp_path.read_text() == test_content

        # Clean up
        temp_path.unlink()

    def test_read_stdin_to_temp_file_unicode_content(self):
        """Test handling of unicode characters."""
        test_content = "# PRD with unicode: café, 日本語, 🎉"
        expected_hash = hashlib.sha256(test_content.encode()).hexdigest()[:16]

        with patch("sys.stdin.read", return_value=test_content):
            temp_path, content_hash = read_stdin_to_temp_file()

        # Verify hash
        assert content_hash == expected_hash

        # Verify content is preserved
        assert temp_path.read_text() == test_content

        # Clean up
        temp_path.unlink()
