"""Tests for the generate_tracker CLI tool.

This module tests the standalone CLI tool for generating implementation trackers.
"""

import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# We need to add the tools directory to the path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from tools.generate_tracker import (
    VALID_EXECUTORS,
    build_parser,
    read_stdin_to_temp_file,
    resolve_repo_root,
)


class BuildParserTests(unittest.TestCase):
    """Tests for the argument parser."""

    def test_prd_and_stdin_are_mutually_exclusive(self) -> None:
        """--prd and --stdin should be mutually exclusive."""
        parser = build_parser()

        # Both should fail
        with self.assertRaises(SystemExit):
            parser.parse_args(["--prd", "test.md", "--stdin"])

    def test_one_of_prd_or_stdin_required(self) -> None:
        """Either --prd or --stdin must be provided."""
        parser = build_parser()

        with self.assertRaises(SystemExit):
            parser.parse_args([])

    def test_prd_argument_accepts_path(self) -> None:
        """--prd should accept a file path."""
        parser = build_parser()
        args = parser.parse_args(["--prd", "feature.md"])
        self.assertEqual(args.prd, Path("feature.md"))

    def test_stdin_flag_is_boolean(self) -> None:
        """--stdin should be a boolean flag."""
        parser = build_parser()
        args = parser.parse_args(["--stdin"])
        self.assertTrue(args.stdin)

    def test_executor_default_is_claude(self) -> None:
        """Default executor should be claude."""
        parser = build_parser()
        args = parser.parse_args(["--prd", "test.md"])
        self.assertEqual(args.executor, "claude")

    def test_executor_accepts_valid_values(self) -> None:
        """--executor should accept claude and codex."""
        parser = build_parser()

        for executor in VALID_EXECUTORS:
            args = parser.parse_args(["--prd", "test.md", "--executor", executor])
            self.assertEqual(args.executor, executor)

    def test_executor_rejects_invalid_values(self) -> None:
        """--executor should reject invalid values."""
        parser = build_parser()

        with self.assertRaises(SystemExit):
            parser.parse_args(["--prd", "test.md", "--executor", "invalid"])

        with self.assertRaises(SystemExit):
            parser.parse_args(["--prd", "test.md", "--executor", "codex-first"])

    def test_force_flag(self) -> None:
        """--force should be a boolean flag."""
        parser = build_parser()

        args = parser.parse_args(["--prd", "test.md"])
        self.assertFalse(args.force)

        args = parser.parse_args(["--prd", "test.md", "--force"])
        self.assertTrue(args.force)

    def test_dry_run_flag(self) -> None:
        """--dry-run should be a boolean flag."""
        parser = build_parser()

        args = parser.parse_args(["--prd", "test.md"])
        self.assertFalse(args.dry_run)

        args = parser.parse_args(["--prd", "test.md", "--dry-run"])
        self.assertTrue(args.dry_run)

    def test_quiet_flag(self) -> None:
        """--quiet should be a boolean flag."""
        parser = build_parser()

        args = parser.parse_args(["--prd", "test.md"])
        self.assertFalse(args.quiet)

        args = parser.parse_args(["--prd", "test.md", "--quiet"])
        self.assertTrue(args.quiet)


class ResolveRepoRootTests(unittest.TestCase):
    """Tests for resolve_repo_root function."""

    def test_explicit_repo_path_is_used(self) -> None:
        """Explicit --repo path should be used."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = resolve_repo_root(Path(tmp_dir))
            self.assertEqual(result, Path(tmp_dir).resolve())

    def test_invalid_repo_path_raises_error(self) -> None:
        """Invalid repo path should raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            resolve_repo_root(Path("/nonexistent/path"))
        self.assertIn("not a directory", str(ctx.exception))

    @patch("tools.generate_tracker.git_root")
    def test_git_root_used_when_repo_not_specified(
        self, mock_git_root: MagicMock
    ) -> None:
        """git_root should be used when --repo is not specified."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            mock_git_root.return_value = tmp_dir
            result = resolve_repo_root(None)
            self.assertEqual(result, Path(tmp_dir))


class ReadStdinToTempFileTests(unittest.TestCase):
    """Tests for read_stdin_to_temp_file function."""

    @patch("sys.stdin", new_callable=io.StringIO)
    def test_creates_temp_file_with_content(self, mock_stdin: io.StringIO) -> None:
        """Should create temp file with stdin content."""
        mock_stdin.write("# Test PRD\n\nThis is a test.")
        mock_stdin.seek(0)

        temp_path, content_hash = read_stdin_to_temp_file()

        try:
            self.assertTrue(temp_path.exists())
            self.assertEqual(temp_path.read_text(), "# Test PRD\n\nThis is a test.")
            self.assertEqual(len(content_hash), 16)  # 16 char hash
        finally:
            temp_path.unlink()

    @patch("sys.stdin", new_callable=io.StringIO)
    def test_empty_input_raises_error(self, mock_stdin: io.StringIO) -> None:
        """Empty stdin should raise ValueError."""
        mock_stdin.write("")
        mock_stdin.seek(0)

        with self.assertRaises(ValueError) as ctx:
            read_stdin_to_temp_file()
        self.assertIn("Empty input", str(ctx.exception))

    @patch("sys.stdin", new_callable=io.StringIO)
    def test_whitespace_only_input_raises_error(self, mock_stdin: io.StringIO) -> None:
        """Whitespace-only stdin should raise ValueError."""
        mock_stdin.write("   \n\n   ")
        mock_stdin.seek(0)

        with self.assertRaises(ValueError) as ctx:
            read_stdin_to_temp_file()
        self.assertIn("Empty input", str(ctx.exception))


class ValidExecutorsTests(unittest.TestCase):
    """Tests for VALID_EXECUTORS constant."""

    def test_only_claude_and_codex_are_valid(self) -> None:
        """Only 'claude' and 'codex' should be valid executors."""
        self.assertEqual(VALID_EXECUTORS, {"claude", "codex"})

    def test_policy_strings_are_not_valid_executors(self) -> None:
        """Policy strings like 'codex-first' should not be valid executors."""
        invalid = ["codex-first", "codex-only", "claude-only"]
        for policy in invalid:
            self.assertNotIn(policy, VALID_EXECUTORS)


if __name__ == "__main__":
    unittest.main()
