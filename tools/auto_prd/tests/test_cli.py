"""
Tests for cli.py - command-line interface argument parsing and main entry point.

This test module verifies:
- Argument parser behavior with various inputs
- Default values for all arguments
- Boolean flags and their interactions
- Main entry point error handling
- Exit code behavior
"""

import argparse
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from .test_helpers import safe_import

# Import CLI functions
build_parser = safe_import("auto_prd.cli", "auto_prd.cli", "build_parser")
main = safe_import("auto_prd.cli", "auto_prd.cli", "main")
handle_list_sessions = safe_import("auto_prd.cli", "auto_prd.cli", "handle_list_sessions")
resolve_checkpoint = safe_import("auto_prd.cli", "auto_prd.cli", "resolve_checkpoint")


class BuildParserTests(unittest.TestCase):
    """Test build_parser() function and argument configuration."""

    def test_parser_creation(self) -> None:
        """Verify build_parser() returns a valid ArgumentParser."""
        parser = build_parser()
        self.assertIsInstance(parser, argparse.ArgumentParser)

    def test_required_arguments(self) -> None:
        """Verify --prd argument is required."""
        parser = build_parser()
        with self.assertRaises(SystemExit) as cm:
            parser.parse_args([])
        # argparse exits with code 2 for missing required arguments
        self.assertEqual(cm.exception.code, 2)

    def test_prd_argument(self) -> None:
        """Verify --prd argument parsing."""
        parser = build_parser()
        args = parser.parse_args(["--prd", "/path/to/prd.md"])
        self.assertEqual(args.prd, "/path/to/prd.md")

    def test_repo_argument(self) -> None:
        """Verify --repo argument parsing."""
        parser = build_parser()
        args = parser.parse_args([
            "--prd", "test.md",
            "--repo", "/path/to/repo"
        ])
        self.assertEqual(args.repo, "/path/to/repo")

    def test_repo_slug_argument(self) -> None:
        """Verify --repo-slug argument parsing."""
        parser = build_parser()
        args = parser.parse_args([
            "--prd", "test.md",
            "--repo-slug", "owner/repo"
        ])
        self.assertEqual(args.repo_slug, "owner/repo")

    def test_log_file_argument(self) -> None:
        """Verify --log-file argument parsing."""
        parser = build_parser()
        args = parser.parse_args([
            "--prd", "test.md",
            "--log-file", "/path/to/log.txt"
        ])
        self.assertEqual(args.log_file, "/path/to/log.txt")

    def test_log_level_argument(self) -> None:
        """Verify --log-level argument parsing with valid values."""
        parser = build_parser()

        # Test uppercase conversion
        args = parser.parse_args([
            "--prd", "test.md",
            "--log-level", "debug"
        ])
        self.assertEqual(args.log_level, "DEBUG")

        # Test default
        args = parser.parse_args(["--prd", "test.md"])
        self.assertEqual(args.log_level, "INFO")

    def test_log_level_invalid_choice(self) -> None:
        """Verify --log-level rejects invalid values."""
        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args([
                "--prd", "test.md",
                "--log-level", "INVALID"
            ])

    def test_base_argument(self) -> None:
        """Verify --base argument parsing."""
        parser = build_parser()
        args = parser.parse_args([
            "--prd", "test.md",
            "--base", "main"
        ])
        self.assertEqual(args.base, "main")

    def test_branch_argument(self) -> None:
        """Verify --branch argument parsing."""
        parser = build_parser()
        args = parser.parse_args([
            "--prd", "test.md",
            "--branch", "feature-branch"
        ])
        self.assertEqual(args.branch, "feature-branch")

    def test_codex_model_argument(self) -> None:
        """Verify --codex-model argument parsing."""
        parser = build_parser()
        args = parser.parse_args([
            "--prd", "test.md",
            "--codex-model", "gpt-4-codex"
        ])
        self.assertEqual(args.codex_model, "gpt-4-codex")

    def test_wait_minutes_argument(self) -> None:
        """Verify --wait-minutes argument parsing."""
        parser = build_parser()

        # Test valid value
        args = parser.parse_args([
            "--prd", "test.md",
            "--wait-minutes", "5"
        ])
        self.assertEqual(args.wait_minutes, 5)

        # Test default
        args = parser.parse_args(["--prd", "test.md"])
        self.assertEqual(args.wait_minutes, 0)

    def test_wait_minutes_negative_rejected(self) -> None:
        """Verify --wait-minutes rejects negative values."""
        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args([
                "--prd", "test.md",
                "--wait-minutes", "-1"
            ])

    def test_review_poll_seconds_argument(self) -> None:
        """Verify --review-poll-seconds argument parsing."""
        parser = build_parser()

        # Test custom value
        args = parser.parse_args([
            "--prd", "test.md",
            "--review-poll-seconds", "60"
        ])
        self.assertEqual(args.review_poll_seconds, 60)

        # Test default
        args = parser.parse_args(["--prd", "test.md"])
        self.assertEqual(args.review_poll_seconds, 120)

    def test_idle_grace_minutes_argument(self) -> None:
        """Verify --idle-grace-minutes argument parsing."""
        parser = build_parser()

        # Test custom value
        args = parser.parse_args([
            "--prd", "test.md",
            "--idle-grace-minutes", "15"
        ])
        self.assertEqual(args.idle_grace_minutes, 15)

        # Test default
        args = parser.parse_args(["--prd", "test.md"])
        self.assertEqual(args.idle_grace_minutes, 10)

    def test_max_local_iters_argument(self) -> None:
        """Verify --max-local-iters argument parsing."""
        parser = build_parser()

        # Test custom value
        args = parser.parse_args([
            "--prd", "test.md",
            "--max-local-iters", "100"
        ])
        self.assertEqual(args.max_local_iters, 100)

        # Test default
        args = parser.parse_args(["--prd", "test.md"])
        self.assertEqual(args.max_local_iters, 50)

    def test_infinite_reviews_flag(self) -> None:
        """Verify --infinite-reviews flag parsing."""
        parser = build_parser()

        # Test flag set
        args = parser.parse_args([
            "--prd", "test.md",
            "--infinite-reviews"
        ])
        self.assertTrue(args.infinite_reviews)

        # Test flag not set
        args = parser.parse_args(["--prd", "test.md"])
        self.assertFalse(args.infinite_reviews)

    def test_support_mode_flag(self) -> None:
        """Verify --support-mode flag parsing."""
        parser = build_parser()

        # Test flag set
        args = parser.parse_args([
            "--prd", "test.md",
            "--support-mode"
        ])
        self.assertTrue(args.support_mode)

        # Test flag not set
        args = parser.parse_args(["--prd", "test.md"])
        self.assertFalse(args.support_mode)

    def test_sync_git_flag(self) -> None:
        """Verify --sync-git flag parsing."""
        parser = build_parser()

        # Test flag set
        args = parser.parse_args([
            "--prd", "test.md",
            "--sync-git"
        ])
        self.assertTrue(args.sync_git)

        # Test flag not set
        args = parser.parse_args(["--prd", "test.md"])
        self.assertFalse(args.sync_git)

    def test_allow_unsafe_execution_flag(self) -> None:
        """Verify --allow-unsafe-execution flag parsing."""
        parser = build_parser()

        # Test flag set
        args = parser.parse_args([
            "--prd", "test.md",
            "--allow-unsafe-execution"
        ])
        self.assertTrue(args.allow_unsafe_execution)

        # Test flag not set
        args = parser.parse_args(["--prd", "test.md"])
        self.assertFalse(args.allow_unsafe_execution)

    def test_dry_run_flag(self) -> None:
        """Verify --dry-run flag parsing."""
        parser = build_parser()

        # Test flag set
        args = parser.parse_args([
            "--prd", "test.md",
            "--dry-run"
        ])
        self.assertTrue(args.dry_run)

        # Test flag not set
        args = parser.parse_args(["--prd", "test.md"])
        self.assertFalse(args.dry_run)

    def test_executor_policy_argument(self) -> None:
        """Verify --executor-policy argument parsing."""
        parser = build_parser()

        # Test valid choices (hardcoded since EXECUTOR_CHOICES is in policy module)
        valid_choices = ["codex-first", "codex-only", "claude-only"]
        for choice in valid_choices:
            args = parser.parse_args([
                "--prd", "test.md",
                "--executor-policy", choice
            ])
            self.assertEqual(args.executor_policy, choice)

        # Test default (None)
        args = parser.parse_args(["--prd", "test.md"])
        self.assertIsNone(args.executor_policy)

    def test_phases_argument(self) -> None:
        """Verify --phases argument parsing."""
        parser = build_parser()

        # Test comma-separated phases
        args = parser.parse_args([
            "--prd", "test.md",
            "--phases", "local,pr,review_fix"
        ])
        self.assertEqual(args.phases, "local,pr,review_fix")

        # Test default (None)
        args = parser.parse_args(["--prd", "test.md"])
        self.assertIsNone(args.phases)

    def test_ralph_mode_flag(self) -> None:
        """Verify --ralph-mode flag parsing."""
        parser = build_parser()

        # Test long form
        args = parser.parse_args([
            "--prd", "test.md",
            "--ralph-mode"
        ])
        self.assertTrue(args.ralph_mode)

        # Test short form
        args = parser.parse_args([
            "--prd", "test.md",
            "--ralph-ready-loop"
        ])
        self.assertTrue(args.ralph_mode)

        # Test flag not set
        args = parser.parse_args(["--prd", "test.md"])
        self.assertFalse(args.ralph_mode)

    def test_ralph_context_rotate_every_argument(self) -> None:
        """Verify --ralph-context-rotate-every argument parsing."""
        parser = build_parser()

        # Test long form
        args = parser.parse_args([
            "--prd", "test.md",
            "--ralph-context-rotate-every", "10"
        ])
        self.assertEqual(args.ralph_context_rotate_every, 10)

        # Test short form
        args = parser.parse_args([
            "--prd", "test.md",
            "--context-rotate-every", "5"
        ])
        self.assertEqual(args.ralph_context_rotate_every, 5)

        # Test default
        args = parser.parse_args(["--prd", "test.md"])
        self.assertEqual(args.ralph_context_rotate_every, 0)

    def test_ralph_max_consecutive_failures_argument(self) -> None:
        """Verify --ralph-max-consecutive-failures argument parsing."""
        parser = build_parser()

        # Test long form
        args = parser.parse_args([
            "--prd", "test.md",
            "--ralph-max-consecutive-failures", "5"
        ])
        self.assertEqual(args.ralph_max_consecutive_failures, 5)

        # Test short form
        args = parser.parse_args([
            "--prd", "test.md",
            "--max-consecutive-failures", "10"
        ])
        self.assertEqual(args.ralph_max_consecutive_failures, 10)

        # Test default
        args = parser.parse_args(["--prd", "test.md"])
        self.assertEqual(args.ralph_max_consecutive_failures, 3)

    def test_ralph_auto_add_signs_flag(self) -> None:
        """Verify --auto-add-signs and --no-auto-add-signs flags."""
        parser = build_parser()

        # Test --auto-add-signs
        args = parser.parse_args([
            "--prd", "test.md",
            "--auto-add-signs"
        ])
        self.assertTrue(args.ralph_auto_add_signs)

        # Test --no-auto-add-signs
        args = parser.parse_args([
            "--prd", "test.md",
            "--no-auto-add-signs"
        ])
        self.assertFalse(args.ralph_auto_add_signs)

        # Test default (True)
        args = parser.parse_args(["--prd", "test.md"])
        self.assertTrue(args.ralph_auto_add_signs)

    def test_ralph_show_progress_log_flag(self) -> None:
        """Verify --show-progress-log and --no-show-progress-log flags."""
        parser = build_parser()

        # Test --show-progress-log
        args = parser.parse_args([
            "--prd", "test.md",
            "--show-progress-log"
        ])
        self.assertTrue(args.ralph_show_progress_log)

        # Test --no-show-progress-log
        args = parser.parse_args([
            "--prd", "test.md",
            "--no-show-progress-log"
        ])
        self.assertFalse(args.ralph_show_progress_log)

        # Test default (False)
        args = parser.parse_args(["--prd", "test.md"])
        self.assertFalse(args.ralph_show_progress_log)

    def test_ralph_show_guardrails_flag(self) -> None:
        """Verify --show-guardrails and --no-show-guardrails flags."""
        parser = build_parser()

        # Test --show-guardrails
        args = parser.parse_args([
            "--prd", "test.md",
            "--show-guardrails"
        ])
        self.assertTrue(args.ralph_show_guardrails)

        # Test --no-show-guardrails
        args = parser.parse_args([
            "--prd", "test.md",
            "--no-show-guardrails"
        ])
        self.assertFalse(args.ralph_show_guardrails)

        # Test default (False)
        args = parser.parse_args(["--prd", "test.md"])
        self.assertFalse(args.ralph_show_guardrails)

    def test_ralph_gutter_output_timeout_sec_argument(self) -> None:
        """Verify --ralph-gutter-output-timeout-sec argument parsing."""
        parser = build_parser()

        # Test long form
        args = parser.parse_args([
            "--prd", "test.md",
            "--ralph-gutter-output-timeout-sec", "120"
        ])
        self.assertEqual(args.ralph_gutter_output_timeout_sec, 120)

        # Test short form
        args = parser.parse_args([
            "--prd", "test.md",
            "--gutter-output-timeout-sec", "60"
        ])
        self.assertEqual(args.ralph_gutter_output_timeout_sec, 60)

        # Test default
        args = parser.parse_args(["--prd", "test.md"])
        self.assertEqual(args.ralph_gutter_output_timeout_sec, 180)

    def test_ralph_gutter_no_progress_iters_argument(self) -> None:
        """Verify --ralph-gutter-no-progress-iters argument parsing."""
        parser = build_parser()

        # Test long form
        args = parser.parse_args([
            "--prd", "test.md",
            "--ralph-gutter-no-progress-iters", "5"
        ])
        self.assertEqual(args.ralph_gutter_no_progress_iters, 5)

        # Test short form
        args = parser.parse_args([
            "--prd", "test.md",
            "--gutter-no-progress-iters", "10"
        ])
        self.assertEqual(args.ralph_gutter_no_progress_iters, 10)

        # Test default
        args = parser.parse_args(["--prd", "test.md"])
        self.assertEqual(args.ralph_gutter_no_progress_iters, 3)

    def test_resume_flag(self) -> None:
        """Verify --resume flag parsing."""
        parser = build_parser()

        # Test flag set
        args = parser.parse_args([
            "--prd", "test.md",
            "--resume"
        ])
        self.assertTrue(args.resume)

        # Test flag not set
        args = parser.parse_args(["--prd", "test.md"])
        self.assertFalse(args.resume)

    def test_resume_session_argument(self) -> None:
        """Verify --resume-session argument parsing."""
        parser = build_parser()

        args = parser.parse_args([
            "--prd", "test.md",
            "--resume-session", "session-id-123"
        ])
        self.assertEqual(args.resume_session, "session-id-123")

    def test_list_sessions_flag(self) -> None:
        """Verify --list-sessions flag parsing."""
        parser = build_parser()

        # Test flag set
        args = parser.parse_args([
            "--prd", "test.md",
            "--list-sessions"
        ])
        self.assertTrue(args.list_sessions)

        # Test flag not set
        args = parser.parse_args(["--prd", "test.md"])
        self.assertFalse(args.list_sessions)

    def test_force_new_flag(self) -> None:
        """Verify --force-new flag parsing."""
        parser = build_parser()

        # Test flag set
        args = parser.parse_args([
            "--prd", "test.md",
            "--force-new"
        ])
        self.assertTrue(args.force_new)

        # Test flag not set
        args = parser.parse_args(["--prd", "test.md"])
        self.assertFalse(args.force_new)


class HandleListSessionsTests(unittest.TestCase):
    """Test handle_list_sessions() function."""

    @patch("auto_prd.cli.list_sessions")
    def test_list_sessions_no_sessions(self, mock_list_sessions: Mock) -> None:
        """Verify behavior when no sessions exist."""
        mock_list_sessions.return_value = []

        with patch("sys.stdout"):  # Suppress print output
            handle_list_sessions()

        mock_list_sessions.assert_called_once_with(limit=50)

    @patch("auto_prd.cli.list_sessions")
    def test_list_sessions_with_sessions(self, mock_list_sessions: Mock) -> None:
        """Verify behavior when sessions exist."""
        mock_list_sessions.return_value = [
            {
                "session_id": "test-session-id-123",
                "status": "in_progress",
                "current_phase": "local",
                "updated_at": "2026-01-19T12:34:56.789Z"
            }
        ]

        with patch("sys.stdout"):  # Suppress print output
            handle_list_sessions()

        mock_list_sessions.assert_called_once_with(limit=50)


class ResolveCheckpointTests(unittest.TestCase):
    """Test resolve_checkpoint() function."""

    @patch("auto_prd.git_ops.git_root")
    def test_resolve_checkpoint_force_new(self, mock_git_root: Mock) -> None:
        """Verify --force-new returns None."""
        mock_args = Mock()
        mock_args.force_new = True
        mock_args.resume_session = None
        mock_args.resume = False

        result = resolve_checkpoint(mock_args)

        self.assertIsNone(result)
        mock_git_root.assert_not_called()

    @patch("auto_prd.cli.load_checkpoint")
    def test_resolve_checkpoint_resume_session(self, mock_load_checkpoint: Mock) -> None:
        """Verify --resume-session loads specific session."""
        mock_checkpoint = {"session_id": "test-session"}
        mock_load_checkpoint.return_value = mock_checkpoint

        mock_args = Mock()
        mock_args.force_new = False
        mock_args.resume_session = "test-session"
        mock_args.resume = False

        with patch("sys.stdout"):  # Suppress print output
            result = resolve_checkpoint(mock_args)

        self.assertEqual(result, mock_checkpoint)
        mock_load_checkpoint.assert_called_once_with("test-session")

    @patch("auto_prd.cli.load_checkpoint")
    def test_resolve_checkpoint_session_not_found(self, mock_load_checkpoint: Mock) -> None:
        """Verify --resume-session with non-existent session raises SystemExit."""
        mock_load_checkpoint.return_value = None

        mock_args = Mock()
        mock_args.force_new = False
        mock_args.resume_session = "nonexistent-session"
        mock_args.resume = False

        with self.assertRaises(SystemExit) as cm:
            resolve_checkpoint(mock_args)

        self.assertIn("Session not found", str(cm.exception))

    @patch("auto_prd.cli.find_resumable_session")
    @patch("auto_prd.git_ops.git_root")
    def test_resolve_checkpoint_resume_no_session(
        self,
        mock_git_root: Mock,
        mock_find_resumable_session: Mock
    ) -> None:
        """Verify --resume with no resumable session returns None."""
        mock_git_root.return_value = Path("/repo")
        mock_find_resumable_session.return_value = None

        mock_args = Mock()
        mock_args.force_new = False
        mock_args.resume_session = None
        mock_args.resume = True
        mock_args.prd = "/path/to/prd.md"
        mock_args.repo = None

        result = resolve_checkpoint(mock_args)

        self.assertIsNone(result)

    @patch("auto_prd.checkpoint.prd_changed_since_checkpoint")
    @patch("auto_prd.cli.find_resumable_session")
    @patch("auto_prd.git_ops.git_root")
    @patch("pathlib.Path.resolve")
    def test_resolve_checkpoint_resume_with_session(
        self,
        mock_resolve: Mock,
        mock_git_root: Mock,
        mock_find_resumable_session: Mock,
        mock_prd_changed: Mock
    ) -> None:
        """Verify --resume returns checkpoint when session exists."""
        # Mock Path.resolve() to return a fixed Path object
        mock_resolve.return_value = Path("/path/to/prd.md")

        mock_git_root.return_value = Path("/repo")
        mock_checkpoint = {
            "session_id": "test-session",
            "current_phase": "local"
        }
        mock_find_resumable_session.return_value = mock_checkpoint
        mock_prd_changed.return_value = False

        mock_args = Mock()
        mock_args.force_new = False
        mock_args.resume_session = None
        mock_args.resume = True
        mock_args.prd = "/path/to/prd.md"
        mock_args.repo = None

        with patch("sys.stdout"):  # Suppress print output
            result = resolve_checkpoint(mock_args)

        self.assertEqual(result, mock_checkpoint)


class MainTests(unittest.TestCase):
    """Test main() entry point."""

    @patch("auto_prd.cli.handle_list_sessions")
    @patch("auto_prd.cli.initialize_output_buffering")
    def test_main_with_list_sessions(
        self,
        mock_init: Mock,
        mock_handle_list: Mock
    ) -> None:
        """Verify main() handles --list-sessions flag."""
        with patch.object(sys, "argv", ["auto_prd", "--prd", "test.md", "--list-sessions"]):
            with self.assertRaises(SystemExit) as cm:
                main()
            self.assertEqual(cm.exception.code, 0)

        mock_handle_list.assert_called_once()

    @patch("auto_prd.cli.run")
    @patch("auto_prd.cli.resolve_checkpoint")
    @patch("auto_prd.cli.initialize_output_buffering")
    def test_main_successful_execution(
        self,
        mock_init: Mock,
        mock_resolve: Mock,
        mock_run: Mock
    ) -> None:
        """Verify main() calls run() with correct arguments."""
        mock_resolve.return_value = None

        with patch.object(sys, "argv", ["auto_prd", "--prd", "test.md"]):
            main()

        mock_run.assert_called_once()

    @patch("auto_prd.cli.run")
    @patch("auto_prd.cli.resolve_checkpoint")
    @patch("auto_prd.cli.initialize_output_buffering")
    def test_main_keyboard_interrupt(
        self,
        mock_init: Mock,
        mock_resolve: Mock,
        mock_run: Mock
    ) -> None:
        """Verify main() handles KeyboardInterrupt gracefully."""
        mock_resolve.return_value = None
        mock_run.side_effect = KeyboardInterrupt()

        with patch.object(sys, "argv", ["auto_prd", "--prd", "test.md"]):
            with self.assertRaises(KeyboardInterrupt):
                main()

    @patch("auto_prd.cli.run")
    @patch("auto_prd.cli.resolve_checkpoint")
    @patch("auto_prd.cli.initialize_output_buffering")
    def test_main_auto_prd_error(
        self,
        mock_init: Mock,
        mock_resolve: Mock,
        mock_run: Mock
    ) -> None:
        """Verify main() handles AutoPrdError with SystemExit."""
        from auto_prd.executor import AutoPrdError

        mock_resolve.return_value = None
        error = AutoPrdError("Test error")
        mock_run.side_effect = error

        with patch.object(sys, "argv", ["auto_prd", "--prd", "test.md"]):
            with self.assertRaises(SystemExit) as cm:
                main()
            self.assertIn("Test error", str(cm.exception))

    @patch("auto_prd.cli.initialize_output_buffering")
    def test_main_missing_required_argument(self, mock_init: Mock) -> None:
        """Verify main() exits with code 2 when --prd is missing."""
        with patch.object(sys, "argv", ["auto_prd"]):
            with self.assertRaises(SystemExit) as cm:
                main()
            self.assertEqual(cm.exception.code, 2)

    @patch("auto_prd.readiness_loop.run_ralph_wiggum_loop")
    @patch("auto_prd.git_ops.git_root")
    @patch("auto_prd.cli.resolve_checkpoint")
    @patch("auto_prd.cli.initialize_output_buffering")
    def test_main_ralph_mode_enabled(
        self,
        mock_init: Mock,
        mock_resolve: Mock,
        mock_git_root: Mock,
        mock_ralph_loop: Mock
    ) -> None:
        """Verify main() uses Ralph loop when --ralph-mode is set."""
        mock_resolve.return_value = None
        mock_git_root.return_value = Path("/repo")

        with patch.object(sys, "argv", ["auto_prd", "--prd", "test.md", "--ralph-mode"]):
            main()

        # Verify Ralph loop was called
        mock_ralph_loop.assert_called_once()

    @patch("auto_prd.cli.initialize_output_buffering")
    def test_main_ralph_mode_with_support_mode_raises_error(
        self,
        mock_init: Mock
    ) -> None:
        """Verify main() raises SystemExit when --ralph-mode and --support-mode are combined."""
        with patch.object(sys, "argv", [
            "auto_prd",
            "--prd", "test.md",
            "--ralph-mode",
            "--support-mode"
        ]):
            with self.assertRaises(SystemExit) as cm:
                main()
            # Check for the exact error message
            self.assertIn("cannot be combined", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
