"""Tests for PRD path security validation.

This module tests the PRD path security validation introduced in app.py
to prevent path traversal attacks. The validation ensures PRD files
are within allowed directories (repo root, working directory, or home).
"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from .test_helpers import safe_import

_is_path_within = safe_import("tools.auto_prd.app", "..app", "_is_path_within")


class IsPathWithinTests(unittest.TestCase):
    """Test suite for the _is_path_within helper function."""

    def setUp(self) -> None:
        """Set up test environment with temporary directories."""
        self.temp_dir = tempfile.mkdtemp()
        self.parent_dir = Path(self.temp_dir)

    def tearDown(self) -> None:
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_path_directly_in_parent(self) -> None:
        """Verify that a path directly in the parent directory is accepted."""
        # The path must be resolved before calling _is_path_within
        # (as per function docstring: "path should be resolved/absolute")
        child_path = (self.parent_dir / "file.txt").resolve()
        self.assertTrue(_is_path_within(child_path, self.parent_dir))

    def test_path_in_subdirectory(self) -> None:
        """Verify that a path in a subdirectory is accepted."""
        subdir = self.parent_dir / "subdir" / "nested"
        subdir.mkdir(parents=True, exist_ok=True)
        # The path must be resolved before calling _is_path_within
        child_path = (subdir / "file.txt").resolve()
        self.assertTrue(_is_path_within(child_path, self.parent_dir))

    def test_path_outside_parent(self) -> None:
        """Verify that a path outside the parent directory is rejected."""
        outside_path = Path("/tmp/outside/file.txt")
        self.assertFalse(_is_path_within(outside_path, self.parent_dir))

    def test_path_traversal_attempt(self) -> None:
        """Verify that path traversal attempts are rejected."""
        # Create a path that uses .. to escape
        traversal_path = self.parent_dir / ".." / ".." / "etc" / "passwd"
        self.assertFalse(_is_path_within(traversal_path.resolve(), self.parent_dir))

    def test_parent_equals_path(self) -> None:
        """Verify that a path equal to parent directory is accepted."""
        # A path is considered within itself (both must be resolved)
        self.assertTrue(
            _is_path_within(self.parent_dir.resolve(), self.parent_dir.resolve())
        )

    def test_symlink_in_allowed_directory(self) -> None:
        """Verify that symlinks within allowed directories are handled."""
        # Create a real file and a symlink to it
        real_file = self.parent_dir / "real_file.txt"
        real_file.write_text("content", encoding="utf-8")
        symlink = self.parent_dir / "symlink.txt"
        try:
            symlink.symlink_to(real_file)
            # The resolved symlink should still be within the parent
            self.assertTrue(_is_path_within(symlink.resolve(), self.parent_dir))
        except OSError:
            # Skip on systems that don't support symlinks
            self.skipTest("Symlinks not supported on this system")

    def test_relative_path_resolution(self) -> None:
        """Verify that relative paths are properly handled via resolution."""
        # Create actual files for resolution
        subdir = self.parent_dir / "subdir"
        subdir.mkdir(exist_ok=True)
        file_path = subdir / "file.txt"
        file_path.write_text("test", encoding="utf-8")

        # Test with resolved path
        self.assertTrue(_is_path_within(file_path.resolve(), self.parent_dir))

    def test_exception_handling_returns_false(self) -> None:
        """Verify that exceptions during path checking return False."""
        # Test with a path that might cause resolution issues
        # The function should handle ValueError and OSError gracefully
        with mock.patch.object(
            Path, "is_relative_to", side_effect=ValueError("Test error")
        ):
            result = _is_path_within(Path("/some/path"), Path("/parent"))
            self.assertFalse(result)

        with mock.patch.object(
            Path, "is_relative_to", side_effect=OSError("Test error")
        ):
            result = _is_path_within(Path("/some/path"), Path("/parent"))
            self.assertFalse(result)


class PRDPathValidationIntegrationTests(unittest.TestCase):
    """Integration tests for PRD path validation in the run() function."""

    def setUp(self) -> None:
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.repo_root = Path(self.temp_dir) / "repo"
        self.repo_root.mkdir(parents=True, exist_ok=True)

        # Create a .git directory to make it a git repo
        git_dir = self.repo_root / ".git"
        git_dir.mkdir(exist_ok=True)

    def tearDown(self) -> None:
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_prd_in_repo_root_accepted(self) -> None:
        """Verify that PRD files in the repo root are accepted."""
        # The path must be resolved before calling _is_path_within
        prd_path = (self.repo_root / "feature.md").resolve()
        allowed_dirs = [self.repo_root, Path.cwd(), Path.home()]

        prd_in_allowed = any(
            _is_path_within(prd_path, allowed_dir) for allowed_dir in allowed_dirs
        )
        self.assertTrue(prd_in_allowed)

    def test_prd_in_repo_subdirectory_accepted(self) -> None:
        """Verify that PRD files in repo subdirectories are accepted."""
        docs_dir = self.repo_root / "docs" / "prds"
        docs_dir.mkdir(parents=True, exist_ok=True)
        # The path must be resolved before calling _is_path_within
        prd_path = (docs_dir / "feature.md").resolve()

        allowed_dirs = [self.repo_root, Path.cwd(), Path.home()]
        prd_in_allowed = any(
            _is_path_within(prd_path, allowed_dir) for allowed_dir in allowed_dirs
        )
        self.assertTrue(prd_in_allowed)

    def test_prd_in_home_directory_accepted(self) -> None:
        """Verify that PRD files in home directory are accepted."""
        home = Path.home()
        prd_path = home / "Documents" / "feature.md"

        allowed_dirs = [self.repo_root, Path.cwd(), home]
        prd_in_allowed = any(
            _is_path_within(prd_path, allowed_dir) for allowed_dir in allowed_dirs
        )
        self.assertTrue(prd_in_allowed)

    def test_prd_in_current_working_directory_accepted(self) -> None:
        """Verify that PRD files in the current working directory are accepted."""
        cwd = Path.cwd()
        prd_path = cwd / "feature.md"

        allowed_dirs = [self.repo_root, cwd, Path.home()]
        prd_in_allowed = any(
            _is_path_within(prd_path, allowed_dir) for allowed_dir in allowed_dirs
        )
        self.assertTrue(prd_in_allowed)

    def test_prd_outside_allowed_directories_rejected(self) -> None:
        """Verify that PRD files outside allowed directories are rejected."""
        # Create a path that's outside all allowed directories
        # This simulates a path traversal attack
        malicious_path = Path("/etc/passwd")

        # Mock allowed directories to be very specific
        allowed_dirs = [
            self.repo_root,
            Path(self.temp_dir) / "cwd",
            Path(self.temp_dir) / "home",
        ]

        prd_in_allowed = any(
            _is_path_within(malicious_path, allowed_dir) for allowed_dir in allowed_dirs
        )
        self.assertFalse(prd_in_allowed)

    def test_path_traversal_attack_rejected(self) -> None:
        """Verify that path traversal attacks are rejected."""
        # Simulate an attacker trying to escape the repo
        traversal_path = self.repo_root / ".." / ".." / "etc" / "passwd"
        resolved_path = traversal_path.resolve()

        # The resolved path should NOT be in the repo root directory
        # This tests that path traversal attempts are correctly detected
        self.assertFalse(_is_path_within(resolved_path, self.repo_root))


class PRDValidationEdgeCases(unittest.TestCase):
    """Edge case tests for PRD path validation."""

    def test_empty_path_handling(self) -> None:
        """Verify that empty paths don't cause crashes."""
        # This should not raise an exception
        result = _is_path_within(Path(""), Path("/some/dir"))
        # Empty path is not within /some/dir
        self.assertFalse(result)

    def test_root_path_as_parent(self) -> None:
        """Verify behavior when root path is the parent."""
        root = Path("/")
        child = Path("/usr/local/bin/file")

        # Everything is within root on Unix
        result = _is_path_within(child, root)
        self.assertTrue(result)

    def test_nested_path_with_dots(self) -> None:
        """Verify that paths with . components are handled correctly."""
        parent = Path("/home/user/project")
        # Path with . components that still resolves within parent
        child = Path("/home/user/project/./subdir/../subdir/file.txt")

        result = _is_path_within(child.resolve(), parent)
        self.assertTrue(result)

    def test_case_sensitivity(self) -> None:
        """Test case sensitivity (system-dependent)."""
        # Create temp directories for testing
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir) / "Parent"
            parent.mkdir(exist_ok=True)
            child = parent / "child.txt"
            child.write_text("test", encoding="utf-8")

            # Test that the exact path works (must resolve both paths)
            result = _is_path_within(child.resolve(), parent.resolve())
            self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
