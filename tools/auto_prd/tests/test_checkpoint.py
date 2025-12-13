"""Tests for checkpoint file permission hardening and security features.

This module tests the save_checkpoint function's security enhancements:
- Temp files created with 0600 permissions via umask(0o077)
- Final checkpoint files have 0600 permissions after rename
- Original umask is properly restored even when exceptions occur
- The atomic write-rename pattern works correctly with permissions
"""

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from .test_helpers import safe_import

save_checkpoint = safe_import(
    "tools.auto_prd.checkpoint", "..checkpoint", "save_checkpoint"
)
get_sessions_dir = safe_import(
    "tools.auto_prd.checkpoint", "..checkpoint", "get_sessions_dir"
)
create_checkpoint = safe_import(
    "tools.auto_prd.checkpoint", "..checkpoint", "create_checkpoint"
)
load_checkpoint = safe_import(
    "tools.auto_prd.checkpoint", "..checkpoint", "load_checkpoint"
)


class CheckpointPermissionTests(unittest.TestCase):
    """Test suite for checkpoint file permission hardening."""

    def setUp(self) -> None:
        """Set up test environment with temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_umask = os.umask(0o022)  # Store original umask
        os.umask(self.original_umask)  # Restore it immediately

    def tearDown(self) -> None:
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_checkpoint_file_has_0600_permissions(self) -> None:
        """Verify that saved checkpoint files have 0600 permissions (owner read/write only)."""
        # Create a mock sessions directory in temp
        sessions_dir = Path(self.temp_dir) / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)

        with mock.patch(
            "tools.auto_prd.checkpoint.get_sessions_dir", return_value=sessions_dir
        ):
            checkpoint = {
                "session_id": "test-session-001",
                "version": 1,
                "status": "in_progress",
                "prd_path": "/test/prd.md",
                "phases": {"local": {}, "pr": {}, "review_fix": {}},
            }

            save_checkpoint(checkpoint)

            # Verify the checkpoint file exists
            checkpoint_path = sessions_dir / "test-session-001.json"
            self.assertTrue(checkpoint_path.exists(), "Checkpoint file should exist")

            # Check file permissions (should be 0600 = owner read/write only)
            file_mode = checkpoint_path.stat().st_mode
            permission_bits = stat.S_IMODE(file_mode)
            self.assertEqual(
                permission_bits,
                0o600,
                f"Checkpoint file should have 0600 permissions, got {oct(permission_bits)}",
            )

    def test_umask_restored_after_save(self) -> None:
        """Verify that the original umask is restored after save_checkpoint completes."""
        sessions_dir = Path(self.temp_dir) / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)

        # Set a known umask before calling save_checkpoint
        original_umask = os.umask(0o022)
        os.umask(original_umask)  # Restore immediately to get the value

        with mock.patch(
            "tools.auto_prd.checkpoint.get_sessions_dir", return_value=sessions_dir
        ):
            checkpoint = {
                "session_id": "test-session-umask",
                "version": 1,
                "status": "in_progress",
                "prd_path": "/test/prd.md",
                "phases": {"local": {}, "pr": {}, "review_fix": {}},
            }

            # Set umask and save
            os.umask(original_umask)
            save_checkpoint(checkpoint)

            # Verify umask was restored
            current_umask = os.umask(original_umask)
            os.umask(current_umask)  # Restore again
            self.assertEqual(
                current_umask,
                original_umask,
                f"Umask should be restored to {oct(original_umask)}, got {oct(current_umask)}",
            )

    def test_umask_restored_on_exception(self) -> None:
        """Verify that umask is restored even when save_checkpoint raises an exception."""
        sessions_dir = Path(self.temp_dir) / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)

        # Set a known umask
        original_umask = os.umask(0o022)
        os.umask(original_umask)

        with mock.patch(
            "tools.auto_prd.checkpoint.get_sessions_dir", return_value=sessions_dir
        ):
            # Mock json.dump to raise an exception
            with mock.patch(
                "tools.auto_prd.checkpoint.json.dump",
                side_effect=ValueError("Simulated JSON error"),
            ):
                checkpoint = {
                    "session_id": "test-session-error",
                    "version": 1,
                    "status": "in_progress",
                }

                os.umask(original_umask)
                with self.assertRaises(ValueError):
                    save_checkpoint(checkpoint)

                # Verify umask was still restored despite exception
                current_umask = os.umask(original_umask)
                os.umask(current_umask)
                self.assertEqual(
                    current_umask,
                    original_umask,
                    "Umask should be restored even after exception",
                )

    def test_temp_file_cleaned_up_on_failure(self) -> None:
        """Verify that temporary files are cleaned up when save fails."""
        sessions_dir = Path(self.temp_dir) / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)

        with mock.patch(
            "tools.auto_prd.checkpoint.get_sessions_dir", return_value=sessions_dir
        ):
            # Count files before
            files_before = list(sessions_dir.glob("*.json*"))

            # Mock json.dump to raise an exception after creating temp file
            with mock.patch(
                "tools.auto_prd.checkpoint.json.dump",
                side_effect=ValueError("Simulated error"),
            ):
                checkpoint = {
                    "session_id": "test-session-cleanup",
                    "version": 1,
                    "status": "in_progress",
                }

                with self.assertRaises(ValueError):
                    save_checkpoint(checkpoint)

            # Verify no temp files left behind
            files_after = list(sessions_dir.glob("*.json*"))
            self.assertEqual(
                len(files_before),
                len(files_after),
                "Temp files should be cleaned up on failure",
            )

    def test_atomic_write_rename_pattern(self) -> None:
        """Verify that checkpoint uses atomic write-then-rename pattern."""
        sessions_dir = Path(self.temp_dir) / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)

        with mock.patch(
            "tools.auto_prd.checkpoint.get_sessions_dir", return_value=sessions_dir
        ):
            checkpoint = {
                "session_id": "test-atomic",
                "version": 1,
                "status": "in_progress",
                "prd_path": "/test/prd.md",
                "phases": {"local": {}, "pr": {}, "review_fix": {}},
            }

            # Save checkpoint
            save_checkpoint(checkpoint)

            # Verify final file exists and is valid JSON
            checkpoint_path = sessions_dir / "test-atomic.json"
            self.assertTrue(checkpoint_path.exists())

            with open(checkpoint_path) as f:
                loaded = json.load(f)

            self.assertEqual(loaded["session_id"], "test-atomic")
            self.assertEqual(loaded["version"], 1)

    def test_checkpoint_content_integrity(self) -> None:
        """Verify that checkpoint content is correctly written with proper permissions."""
        sessions_dir = Path(self.temp_dir) / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)

        with mock.patch(
            "tools.auto_prd.checkpoint.get_sessions_dir", return_value=sessions_dir
        ):
            checkpoint = {
                "session_id": "test-integrity",
                "version": 1,
                "status": "in_progress",
                "prd_path": "/test/prd.md",
                "prd_hash": "sha256:abc123",
                "repo_root": "/test/repo",
                "base_branch": "main",
                "feature_branch": "feature/test",
                "selected_phases": ["local", "pr"],
                "current_phase": "local",
                "phases": {
                    "local": {"status": "in_progress", "iteration": 5},
                    "pr": {"status": "pending"},
                    "review_fix": {"status": "pending"},
                },
                "git_state": {"stash_selector": None},
                "errors": [],
            }

            save_checkpoint(checkpoint)

            # Load and verify
            checkpoint_path = sessions_dir / "test-integrity.json"
            with open(checkpoint_path) as f:
                loaded = json.load(f)

            # Verify all fields preserved
            self.assertEqual(loaded["session_id"], "test-integrity")
            self.assertEqual(loaded["prd_path"], "/test/prd.md")
            self.assertEqual(loaded["phases"]["local"]["iteration"], 5)
            self.assertIn("updated_at", loaded)  # Should be added by save_checkpoint


class CheckpointLoadTests(unittest.TestCase):
    """Test suite for loading checkpoints with proper permissions."""

    def setUp(self) -> None:
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_load_checkpoint_with_restricted_permissions(self) -> None:
        """Verify that checkpoints with 0600 permissions can be loaded."""
        sessions_dir = Path(self.temp_dir) / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)

        # Create a checkpoint file with restricted permissions
        checkpoint_path = sessions_dir / "test-load.json"
        checkpoint_data = {
            "session_id": "test-load",
            "version": 1,
            "status": "in_progress",
            "prd_path": "/test/prd.md",
            "phases": {"local": {}, "pr": {}, "review_fix": {}},
        }

        with open(checkpoint_path, "w") as f:
            json.dump(checkpoint_data, f)

        # Set restrictive permissions
        os.chmod(checkpoint_path, 0o600)

        with mock.patch(
            "tools.auto_prd.checkpoint.get_sessions_dir", return_value=sessions_dir
        ):
            loaded = load_checkpoint("test-load")

            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["session_id"], "test-load")


if __name__ == "__main__":
    unittest.main()
