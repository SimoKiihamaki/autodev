"""Tests for multi-repository monitoring module."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from support_mode.multi_repo import (
    RepoStatus,
    check_repository,
    check_repositories_parallel,
    format_repo_table,
)


class TestCheckRepository:
    """Tests for check_repository function."""

    def test_returns_repo_status_object(self):
        """Test that check_repository returns a RepoStatus object."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            # Initialize as a git repo
            repo_path.joinpath(".git").mkdir()

            with patch(
                "support_mode.multi_repo.git_current_branch", return_value="main"
            ), patch(
                "support_mode.multi_repo.git_head_sha", return_value="abc123def456"
            ):
                status = check_repository(repo_path)

            assert isinstance(status, RepoStatus)
            assert status.path == str(repo_path)
            assert status.name == repo_path.name
            assert status.branch == "main"
            assert status.sha == "abc123d"

    def test_nonexistent_repo_path(self):
        """Test check_repository with a nonexistent path."""
        nonexistent = Path("/nonexistent/path/that/does/not/exist")
        status = check_repository(nonexistent)

        assert status.path == str(nonexistent)
        assert status.name == nonexistent.name
        assert status.branch == ""
        assert status.sha == ""
        assert status.issues is not None
        assert len(status.issues) == 1
        assert "not found" in status.issues[0].lower()

    def test_git_error_handling(self):
        """Test check_repository when git operations fail."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            repo_path.joinpath(".git").mkdir()

            with patch(
                "support_mode.multi_repo.git_current_branch",
                side_effect=OSError("git not found"),
            ):
                status = check_repository(repo_path)

            assert status.branch == ""
            assert status.sha == ""
            assert status.issues is not None
            assert "Git error" in status.issues[0]

    def test_repo_with_tracker(self):
        """Test check_repository with a valid tracker."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            repo_path.joinpath(".git").mkdir()

            # Create tracker
            aprd_dir = repo_path / ".aprd"
            aprd_dir.mkdir()
            tracker_path = aprd_dir / "tracker.json"
            tracker_data = {
                "version": "2.0.0",
                "metadata": {
                    "prd_source": "test.md",
                    "prd_hash": "sha256:abc123",
                    "created_at": "2025-01-20T00:00:00Z",
                    "created_by": "claude",
                    "project_context": {},
                },
                "features": [
                    {
                        "id": "F001",
                        "name": "Feature 1",
                        "description": "Test",
                        "priority": "high",
                        "status": "pending",
                        "goals": {"primary": "Test", "measurable_outcomes": []},
                        "tasks": [
                            {
                                "id": "T001",
                                "description": "Task 1",
                                "status": "completed",
                            },
                            {
                                "id": "T002",
                                "description": "Task 2",
                                "status": "pending",
                            },
                        ],
                        "acceptance_criteria": [],
                        "testing": {"unit_tests": [], "integration_tests": []},
                        "validation": {"benchmarks": [], "quality_gates": []},
                    }
                ],
                "validation_summary": {
                    "total_features": 1,
                    "total_tasks": 2,
                    "estimated_complexity": "small",
                },
            }
            tracker_path.write_text(json.dumps(tracker_data))

            with patch(
                "support_mode.multi_repo.git_current_branch", return_value="main"
            ), patch(
                "support_mode.multi_repo.git_head_sha", return_value="abc123def456"
            ):
                status = check_repository(repo_path)

            assert status.tracker_valid is True
            assert status.total_tasks == 2
            assert status.tasks_left == 1

    def test_repo_without_tracker(self):
        """Test check_repository without a tracker."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            repo_path.joinpath(".git").mkdir()

            with patch(
                "support_mode.multi_repo.git_current_branch", return_value="main"
            ), patch(
                "support_mode.multi_repo.git_head_sha", return_value="abc123def456"
            ):
                status = check_repository(repo_path)

            assert status.tracker_valid is False
            assert status.total_tasks == 0
            assert status.tasks_left == 0
            assert status.warnings is not None
            assert "No tracker found" in status.warnings

    def test_repo_with_invalid_tracker(self):
        """Test check_repository with an invalid tracker."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            repo_path.joinpath(".git").mkdir()

            # Create invalid tracker (missing required fields)
            aprd_dir = repo_path / ".aprd"
            aprd_dir.mkdir()
            tracker_path = aprd_dir / "tracker.json"
            tracker_path.write_text('{"invalid": "data"}')

            with patch(
                "support_mode.multi_repo.git_current_branch", return_value="main"
            ), patch(
                "support_mode.multi_repo.git_head_sha", return_value="abc123def456"
            ):
                status = check_repository(repo_path)

            assert status.tracker_valid is False
            assert status.issues is not None
            # Should have validation errors
            assert len(status.issues) > 0

    def test_shas_are_truncated(self):
        """Test that SHA is truncated to 7 characters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            repo_path.joinpath(".git").mkdir()

            with patch(
                "support_mode.multi_repo.git_current_branch", return_value="main"
            ), patch(
                "support_mode.multi_repo.git_head_sha",
                return_value="a" * 40,  # Full SHA
            ):
                status = check_repository(repo_path)

            assert status.sha == "aaaaaaa"
            assert len(status.sha) == 7


class TestCheckRepositoriesParallel:
    """Tests for check_repositories_parallel function."""

    def test_single_repository(self):
        """Test checking a single repository."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            repo_path.joinpath(".git").mkdir()

            repos = [{"path": str(repo_path)}]

            with patch(
                "support_mode.multi_repo.git_current_branch", return_value="main"
            ), patch(
                "support_mode.multi_repo.git_head_sha", return_value="abc123def456"
            ):
                statuses = check_repositories_parallel(repos)

            assert len(statuses) == 1
            assert statuses[0].name == repo_path.name

    def test_multiple_repositories(self):
        """Test checking multiple repositories in parallel."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo1 = Path(tmpdir) / "repo1"
            repo2 = Path(tmpdir) / "repo2"
            repo1.mkdir()
            repo2.mkdir()
            repo1.joinpath(".git").mkdir()
            repo2.joinpath(".git").mkdir()

            repos = [{"path": str(repo1)}, {"path": str(repo2)}]

            with patch(
                "support_mode.multi_repo.git_current_branch", return_value="main"
            ), patch(
                "support_mode.multi_repo.git_head_sha", return_value="abc123def456"
            ):
                statuses = check_repositories_parallel(repos)

            assert len(statuses) == 2
            names = {s.name for s in statuses}
            assert "repo1" in names
            assert "repo2" in names

    def test_mixed_success_and_failure(self):
        """Test checking repos where some fail and some succeed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            valid_repo = Path(tmpdir) / "valid"
            valid_repo.mkdir()
            valid_repo.joinpath(".git").mkdir()

            repos = [
                {"path": str(valid_repo)},
                {"path": "/nonexistent/path"},
            ]

            with patch(
                "support_mode.multi_repo.git_current_branch", return_value="main"
            ), patch(
                "support_mode.multi_repo.git_head_sha", return_value="abc123def456"
            ):
                statuses = check_repositories_parallel(repos)

            assert len(statuses) == 2
            # One should have succeeded, one should have issues
            has_success = any(s.branch == "main" for s in statuses)
            has_failure = any(s.issues is not None for s in statuses)
            assert has_success
            assert has_failure

    def test_custom_max_workers(self):
        """Test check_repositories_parallel with custom max_workers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            repo_path.joinpath(".git").mkdir()

            repos = [{"path": str(repo_path)}]

            with patch(
                "support_mode.multi_repo.git_current_branch", return_value="main"
            ), patch(
                "support_mode.multi_repo.git_head_sha", return_value="abc123def456"
            ):
                # Should not raise with custom max_workers
                statuses = check_repositories_parallel(repos, max_workers=2)

            assert len(statuses) == 1


class TestFormatRepoTable:
    """Tests for format_repo_table function."""

    def test_empty_list(self):
        """Test formatting with no repositories."""
        result = format_repo_table([])
        assert result == "No repositories to display."

    def test_single_repository(self):
        """Test formatting a single repository."""
        statuses = [
            RepoStatus(
                path="/path/to/repo",
                name="myrepo",
                branch="main",
                sha="abc123d",
                has_changes=False,
                tracker_valid=True,
                tasks_left=3,
                total_tasks=10,
            )
        ]

        result = format_repo_table(statuses)

        assert "myrepo" in result
        assert "/path/to/repo" in result
        assert "main @ abc123d" in result
        assert "7/10 (70%)" in result  # 10 - 3 = 7 completed

    def test_multiple_repositories(self):
        """Test formatting multiple repositories."""
        statuses = [
            RepoStatus(
                path="/path/to/repo1",
                name="repo1",
                branch="main",
                sha="abc123d",
            ),
            RepoStatus(
                path="/path/to/repo2",
                name="repo2",
                branch="feature",
                sha="def456e",
            ),
        ]

        result = format_repo_table(statuses)

        assert "repo1" in result
        assert "repo2" in result
        assert "main" in result
        assert "feature" in result

    def test_repository_with_issues(self):
        """Test formatting a repository with issues."""
        statuses = [
            RepoStatus(
                path="/path/to/repo",
                name="broken-repo",
                branch="",
                sha="",
                issues=["Git error: command not found", "Tracker validation failed"],
            )
        ]

        result = format_repo_table(statuses)

        assert "broken-repo" in result
        assert "❌ Issues: 2" in result
        assert "Git error: command not found" in result

    def test_issues_are_limited(self):
        """Test that only first 3 issues are shown."""
        statuses = [
            RepoStatus(
                path="/path/to/repo",
                name="repo",
                branch="main",
                sha="abc123d",
                issues=[f"Error {i}" for i in range(10)],
            )
        ]

        result = format_repo_table(statuses)

        # Should show only first 3 issues
        assert "Error 0" in result
        assert "Error 1" in result
        assert "Error 2" in result
        # But not all 10
        assert result.count("Error ") == 3  # Only in the shown issues

    def test_repository_with_warnings(self):
        """Test formatting a repository with warnings."""
        statuses = [
            RepoStatus(
                path="/path/to/repo",
                name="repo",
                branch="main",
                sha="abc123d",
                warnings=["No tracker found", "Out of date"],
            )
        ]

        result = format_repo_table(statuses)

        assert "repo" in result
        assert "⚠️  Warnings: 2" in result
        assert "No tracker found" in result

    def test_warnings_are_limited(self):
        """Test that only first 2 warnings are shown."""
        statuses = [
            RepoStatus(
                path="/path/to/repo",
                name="repo",
                branch="main",
                sha="abc123d",
                warnings=[f"Warning {i}" for i in range(5)],
            )
        ]

        result = format_repo_table(statuses)

        # Should show only first 2 warnings
        assert "Warning 0" in result
        assert "Warning 1" in result
        assert result.count("Warning ") == 2

    def test_task_completion_percentage(self):
        """Test task completion percentage calculation."""
        statuses = [
            RepoStatus(
                path="/path/to/repo",
                name="repo",
                branch="main",
                sha="abc123d",
                tasks_left=0,
                total_tasks=100,
            )
        ]

        result = format_repo_table(statuses)

        assert "100/100 (100%)" in result

    def test_custom_width(self):
        """Test format_repo_table with custom width."""
        statuses = [
            RepoStatus(
                path="/path/to/repo",
                name="repo",
                branch="main",
                sha="abc123d",
            )
        ]

        result = format_repo_table(statuses, width=80)

        # Header should use custom width
        assert "=" * 80 in result

    def test_zero_tasks_shows_no_task_summary(self):
        """Test that repo with zero tasks doesn't show task summary."""
        statuses = [
            RepoStatus(
                path="/path/to/repo",
                name="repo",
                branch="main",
                sha="abc123d",
                tasks_left=0,
                total_tasks=0,
            )
        ]

        result = format_repo_table(statuses)

        # Should not have a "Tasks:" line
        assert "Tasks:" not in result
