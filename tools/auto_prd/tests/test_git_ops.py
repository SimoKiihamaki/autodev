"""Tests for git_ops.py - Git-related helper functions."""

import subprocess
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from .test_helpers import safe_import

# Import functions under test
git_root = safe_import("tools.auto_prd.git_ops", "auto_prd.git_ops", "git_root")
parse_owner_repo_from_git = safe_import(
    "tools.auto_prd.git_ops", "auto_prd.git_ops", "parse_owner_repo_from_git"
)
ensure_gh_alias = safe_import(
    "tools.auto_prd.git_ops", "auto_prd.git_ops", "ensure_gh_alias"
)
workspace_has_changes = safe_import(
    "tools.auto_prd.git_ops", "auto_prd.git_ops", "workspace_has_changes"
)
git_status_snapshot = safe_import(
    "tools.auto_prd.git_ops", "auto_prd.git_ops", "git_status_snapshot"
)
git_current_branch = safe_import(
    "tools.auto_prd.git_ops", "auto_prd.git_ops", "git_current_branch"
)
git_head_sha = safe_import("tools.auto_prd.git_ops", "auto_prd.git_ops", "git_head_sha")
git_branch_exists = safe_import(
    "tools.auto_prd.git_ops", "auto_prd.git_ops", "git_branch_exists"
)
git_default_branch = safe_import(
    "tools.auto_prd.git_ops", "auto_prd.git_ops", "git_default_branch"
)
git_stash_worktree = safe_import(
    "tools.auto_prd.git_ops", "auto_prd.git_ops", "git_stash_worktree"
)
safe_stash_pop = safe_import(
    "tools.auto_prd.git_ops", "auto_prd.git_ops", "safe_stash_pop"
)
git_stage_all = safe_import(
    "tools.auto_prd.git_ops", "auto_prd.git_ops", "git_stage_all"
)
git_add = safe_import("tools.auto_prd.git_ops", "auto_prd.git_ops", "git_add")
git_has_staged_changes = safe_import(
    "tools.auto_prd.git_ops", "auto_prd.git_ops", "git_has_staged_changes"
)
git_commit = safe_import("tools.auto_prd.git_ops", "auto_prd.git_ops", "git_commit")
git_push_branch = safe_import(
    "tools.auto_prd.git_ops", "auto_prd.git_ops", "git_push_branch"
)
git_fetch_with_retry = safe_import(
    "tools.auto_prd.git_ops", "auto_prd.git_ops", "git_fetch_with_retry"
)
git_pull_with_retry = safe_import(
    "tools.auto_prd.git_ops", "auto_prd.git_ops", "git_pull_with_retry"
)
_GIT_TRANSIENT_ERRORS = safe_import(
    "tools.auto_prd.git_ops", "auto_prd.git_ops", "GIT_TRANSIENT_ERRORS"
)


class GitRootTests(unittest.TestCase):
    """Test git_root() function."""

    @patch("auto_prd.git_ops.run_cmd")
    def test_git_root_returns_path(self, mock_run_cmd: Mock) -> None:
        """Verify git_root returns Path object from git output."""
        mock_run_cmd.return_value = ("/path/to/repo\n", "", 0)

        result = git_root()

        self.assertIsInstance(result, Path)
        self.assertEqual(str(result), "/path/to/repo")
        mock_run_cmd.assert_called_once_with(
            ["git", "rev-parse", "--show-toplevel"]
        )


class ParseOwnerRepoFromGitTests(unittest.TestCase):
    """Test parse_owner_repo_from_git() function."""

    @patch("auto_prd.git_ops.run_cmd")
    def test_https_url(self, mock_run_cmd: Mock) -> None:
        """Verify parsing of HTTPS URLs."""
        mock_run_cmd.return_value = ("https://github.com/owner/repo.git\n", "", 0)

        result = parse_owner_repo_from_git()

        self.assertEqual(result, "owner/repo")
        mock_run_cmd.assert_called_once_with(["git", "remote", "get-url", "origin"])

    @patch("auto_prd.git_ops.run_cmd")
    def test_https_url_without_git_extension(self, mock_run_cmd: Mock) -> None:
        """Verify parsing of HTTPS URLs without .git extension."""
        mock_run_cmd.return_value = ("https://github.com/owner/repo\n", "", 0)

        result = parse_owner_repo_from_git()

        self.assertEqual(result, "owner/repo")

    @patch("auto_prd.git_ops.run_cmd")
    def test_ssh_url(self, mock_run_cmd: Mock) -> None:
        """Verify parsing of SSH URLs."""
        mock_run_cmd.return_value = ("git@github.com:owner/repo.git\n", "", 0)

        result = parse_owner_repo_from_git()

        self.assertEqual(result, "owner/repo")

    @patch("auto_prd.git_ops.run_cmd")
    def test_ssh_url_with_port(self, mock_run_cmd: Mock) -> None:
        """Verify parsing of SSH URLs with port numbers."""
        mock_run_cmd.return_value = (
            "git@github.com:2222:owner/repo.git\n",
            "",
            0,
        )

        result = parse_owner_repo_from_git()

        self.assertEqual(result, "owner/repo")

    @patch("auto_prd.git_ops.run_cmd")
    def test_url_with_extra_path_segments(self, mock_run_cmd: Mock) -> None:
        """Verify parsing of URLs with extra path segments."""
        mock_run_cmd.return_value = (
            "https://github.com/extra/segments/owner/repo.git\n",
            "",
            0,
        )

        result = parse_owner_repo_from_git()

        # Should use last two segments
        self.assertEqual(result, "owner/repo")

    @patch("auto_prd.git_ops.run_cmd")
    def test_invalid_url_raises_error(self, mock_run_cmd: Mock) -> None:
        """Verify invalid URLs raise RuntimeError."""
        mock_run_cmd.return_value = ("https://github.com/invalid\n", "", 0)

        with self.assertRaises(RuntimeError) as ctx:
            parse_owner_repo_from_git()

        self.assertIn("Cannot parse owner/repo", str(ctx.exception))

    @patch("auto_prd.git_ops.run_cmd")
    def test_empty_owner_or_repo_raises_error(self, mock_run_cmd: Mock) -> None:
        """Verify URLs with empty owner or repo raise RuntimeError."""
        mock_run_cmd.return_value = ("https://github.com//repo.git\n", "", 0)

        with self.assertRaises(RuntimeError):
            parse_owner_repo_from_git()


class EnsureGhAliasTests(unittest.TestCase):
    """Test ensure_gh_alias() function."""

    @patch("auto_prd.git_ops.run_cmd")
    @patch("auto_prd.git_ops.logger")
    def test_alias_already_exists(
        self, mock_logger: Mock, mock_run_cmd: Mock
    ) -> None:
        """Verify no action taken when alias already exists."""
        mock_run_cmd.return_value = ("save-me-copilot: some command\n", "", 0)

        ensure_gh_alias()

        # Should only call list, not set
        self.assertEqual(mock_run_cmd.call_count, 1)
        mock_run_cmd.assert_called_once_with(["gh", "alias", "list"])

    @patch("auto_prd.git_ops.run_cmd")
    @patch("auto_prd.git_ops.logger")
    def test_alias_created_when_missing(
        self, mock_logger: Mock, mock_run_cmd: Mock
    ) -> None:
        """Verify alias is created when it doesn't exist."""
        # First call returns empty list, second succeeds
        mock_run_cmd.side_effect = [
            ("other: alias\n", "", 0),
            ("", "", 0),
        ]

        ensure_gh_alias()

        self.assertEqual(mock_run_cmd.call_count, 2)
        mock_run_cmd.assert_any_call(["gh", "alias", "list"])
        mock_run_cmd.assert_any_call(
            [
                "gh",
                "alias",
                "set",
                "save-me-copilot",
                (
                    'api --method POST /repos/$1/pulls/$2/requested_reviewers '
                    '-f "reviewers[]=copilot-pull-request-reviewer[bot]"'
                ),
            ]
        )

    @patch("auto_prd.git_ops.run_cmd")
    @patch("auto_prd.git_ops.logger")
    def test_gh_not_available_gracefully_skips(
        self, mock_logger: Mock, mock_run_cmd: Mock
    ) -> None:
        """Verify function handles missing gh CLI gracefully."""
        mock_run_cmd.side_effect = FileNotFoundError("gh not found")

        # Should not raise
        ensure_gh_alias()

        mock_logger.debug.assert_called()


class WorkspaceHasChangesTests(unittest.TestCase):
    """Test workspace_has_changes() function."""

    @patch("auto_prd.git_ops.run_cmd")
    def test_workspace_with_changes(self, mock_run_cmd: Mock) -> None:
        """Verify returns True when workspace has changes."""
        mock_result = MagicMock()
        mock_result.stdout = "M file.txt\nA new.txt\n"
        mock_run_cmd.return_value = mock_result

        result = workspace_has_changes(Path("/repo"))

        self.assertTrue(result)
        mock_run_cmd.assert_called_once_with(
            ["git", "status", "--porcelain"], cwd=Path("/repo")
        )

    @patch("auto_prd.git_ops.run_cmd")
    def test_workspace_clean(self, mock_run_cmd: Mock) -> None:
        """Verify returns False when workspace is clean."""
        mock_result = MagicMock()
        mock_result.stdout = "\n"
        mock_run_cmd.return_value = mock_result

        result = workspace_has_changes(Path("/repo"))

        self.assertFalse(result)


class GitStatusSnapshotTests(unittest.TestCase):
    """Test git_status_snapshot() function."""

    @patch("auto_prd.git_ops.run_cmd")
    def test_status_snapshot_returns_sorted_tuple(
        self, mock_run_cmd: Mock
    ) -> None:
        """Verify status snapshot returns sorted tuple of lines."""
        mock_result = MagicMock()
        mock_result.stdout = "M file.txt\nA new.txt\nD old.txt\n"
        mock_run_cmd.return_value = mock_result

        result = git_status_snapshot(Path("/repo"))

        self.assertIsInstance(result, tuple)
        # Should be sorted alphabetically
        self.assertEqual(
            result, ("A new.txt", "D old.txt", "M file.txt")
        )
        mock_run_cmd.assert_called_once_with(
            ["git", "status", "--porcelain"], cwd=Path("/repo")
        )


class GitCurrentBranchTests(unittest.TestCase):
    """Test git_current_branch() function."""

    @patch("auto_prd.git_ops.run_cmd")
    def test_returns_branch_name(self, mock_run_cmd: Mock) -> None:
        """Verify returns current branch name."""
        mock_result = MagicMock()
        mock_result.stdout = "feature-branch\n"
        mock_run_cmd.return_value = mock_result

        result = git_current_branch(Path("/repo"))

        self.assertEqual(result, "feature-branch")
        mock_run_cmd.assert_called_once_with(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=Path("/repo")
        )


class GitHeadShaTests(unittest.TestCase):
    """Test git_head_sha() function."""

    @patch("auto_prd.git_ops.run_cmd")
    def test_returns_commit_sha(self, mock_run_cmd: Mock) -> None:
        """Verify returns HEAD commit SHA."""
        mock_result = MagicMock()
        mock_result.stdout = "abc123def456\n"
        mock_run_cmd.return_value = mock_result

        result = git_head_sha(Path("/repo"))

        self.assertEqual(result, "abc123def456")
        mock_run_cmd.assert_called_once_with(
            ["git", "rev-parse", "HEAD"], cwd=Path("/repo")
        )


class GitBranchExistsTests(unittest.TestCase):
    """Test git_branch_exists() function."""

    @patch("auto_prd.git_ops.run_cmd")
    def test_local_branch_exists(self, mock_run_cmd: Mock) -> None:
        """Verify returns True when local branch exists."""
        mock_run_cmd.return_value = ("", "", 0)  # Exit code 0 = exists

        result = git_branch_exists(Path("/repo"), "main")

        self.assertTrue(result)
        mock_run_cmd.assert_called_once_with(
            ["git", "show-ref", "--verify", "--quiet", "refs/heads/main"],
            cwd=Path("/repo"),
            check=False,
        )

    @patch("auto_prd.git_ops.run_cmd")
    def test_remote_branch_exists(self, mock_run_cmd: Mock) -> None:
        """Verify returns True when remote branch exists."""
        # Local doesn't exist (rc=1), remote does (rc=0)
        mock_run_cmd.side_effect = [
            ("", "", 1),
            ("", "", 0),
        ]

        result = git_branch_exists(Path("/repo"), "origin/main")

        self.assertTrue(result)

    @patch("auto_prd.git_ops.run_cmd")
    def test_branch_does_not_exist(self, mock_run_cmd: Mock) -> None:
        """Verify returns False when branch doesn't exist."""
        mock_run_cmd.return_value = ("", "", 1)

        result = git_branch_exists(Path("/repo"), "nonexistent")

        self.assertFalse(result)

    @patch("auto_prd.git_ops.run_cmd")
    def test_empty_branch_returns_false(self, mock_run_cmd: Mock) -> None:
        """Verify empty branch name returns False."""
        result = git_branch_exists(Path("/repo"), "")

        self.assertFalse(result)
        mock_run_cmd.assert_not_called()

    @patch("auto_prd.git_ops.run_cmd")
    def test_whitespace_branch_returns_false(self, mock_run_cmd: Mock) -> None:
        """Verify whitespace-only branch name returns False."""
        result = git_branch_exists(Path("/repo"), "   ")

        self.assertFalse(result)
        mock_run_cmd.assert_not_called()


class GitDefaultBranchTests(unittest.TestCase):
    """Test git_default_branch() function."""

    @patch("auto_prd.git_ops.run_cmd")
    def test_gets_from_origin_head(self, mock_run_cmd: Mock) -> None:
        """Verify gets default branch from origin/HEAD."""
        mock_run_cmd.return_value = ("refs/remotes/origin/main\n", "", 0)

        result = git_default_branch(Path("/repo"))

        self.assertEqual(result, "main")
        mock_run_cmd.assert_called_once_with(
            ["git", "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"],
            cwd=Path("/repo"),
            check=False,
        )

    @patch("auto_prd.git_ops.run_cmd")
    def test_falls_back_to_config(self, mock_run_cmd: Mock) -> None:
        """Verify falls back to init.defaultBranch config."""
        # First call (origin/HEAD) fails, second (config) succeeds
        mock_run_cmd.side_effect = [
            ("", "", 1),
            ("master\n", "", 0),
        ]

        result = git_default_branch(Path("/repo"))

        self.assertEqual(result, "master")

    @patch("auto_prd.git_ops.run_cmd")
    def test_returns_none_when_not_found(self, mock_run_cmd: Mock) -> None:
        """Verify returns None when default branch cannot be determined."""
        mock_run_cmd.side_effect = [
            ("", "", 1),  # origin/HEAD fails
            ("", "", 1),  # config fails
        ]

        result = git_default_branch(Path("/repo"))

        self.assertIsNone(result)


class GitStashWorktreeTests(unittest.TestCase):
    """Test git_stash_worktree() function."""

    @patch("auto_prd.git_ops.run_cmd")
    def test_stash_with_changes(self, mock_run_cmd: Mock) -> None:
        """Verify stash creates entry when there are changes."""
        # status: has changes, stash push succeeds, list succeeds
        mock_run_cmd.side_effect = [
            ("M file.txt\n", "", 0),  # git status
            ("", "", 0),  # git stash push
            ("stash@{0}\n", "", 0),  # git stash list
        ]

        result = git_stash_worktree(Path("/repo"), "test message")

        self.assertEqual(result, "stash@{0}")
        self.assertEqual(mock_run_cmd.call_count, 3)

    @patch("auto_prd.git_ops.run_cmd")
    def test_stash_with_no_changes(self, mock_run_cmd: Mock) -> None:
        """Verify stash returns None when there are no changes."""
        # status: no changes
        mock_run_cmd.return_value = ("", "", 0)

        result = git_stash_worktree(Path("/repo"), "test message")

        self.assertIsNone(result)
        mock_run_cmd.assert_called_once()


class SafeStashPopTests(unittest.TestCase):
    """Test safe_stash_pop() function."""

    @patch("auto_prd.git_ops.git_stash_pop")
    def test_successful_pop(self, mock_git_stash_pop: Mock) -> None:
        """Verify successful stash pop."""
        # git_stash_pop succeeds (no exception)
        mock_git_stash_pop.return_value = None

        # Should not raise
        safe_stash_pop(Path("/repo"), "stash@{0}")

        mock_git_stash_pop.assert_called_once_with(Path("/repo"), "stash@{0}")

    @patch("auto_prd.git_ops.git_stash_pop")
    @patch("auto_prd.git_ops.run_cmd")
    def test_pop_with_conflict_raises_error(
        self, mock_run_cmd: Mock, mock_git_stash_pop: Mock
    ) -> None:
        """Verify pop with conflict raises StashConflictError."""
        from auto_prd.git_ops import StashConflictError

        # git_stash_pop raises CalledProcessError with conflict message
        mock_git_stash_pop.side_effect = subprocess.CalledProcessError(
            1, "git", stderr=b"CONFLICT: Merge conflict in file.txt"
        )
        # git status returns conflicted files
        mock_run_cmd.return_value = ("UU file.txt\n", "", 0)

        with self.assertRaises(StashConflictError):
            safe_stash_pop(Path("/repo"), "stash@{0}")


class GitStageAllTests(unittest.TestCase):
    """Test git_stage_all() function."""

    @patch("auto_prd.git_ops.run_cmd")
    def test_stage_all(self, mock_run_cmd: Mock) -> None:
        """Verify git add -A is called."""
        git_stage_all(Path("/repo"))

        mock_run_cmd.assert_called_once_with(
            ["git", "add", "-A"], cwd=Path("/repo")
        )


class GitAddTests(unittest.TestCase):
    """Test git_add() function."""

    @patch("auto_prd.git_ops.run_cmd")
    def test_add_single_file(self, mock_run_cmd: Mock) -> None:
        """Verify git add for single file."""
        git_add(Path("/repo"), Path("file.txt"))

        mock_run_cmd.assert_called_once_with(
            ["git", "add", "--", "file.txt"], cwd=Path("/repo")
        )


class GitHasStagedChangesTests(unittest.TestCase):
    """Test git_has_staged_changes() function."""

    @patch("auto_prd.git_ops.run_cmd")
    def test_has_staged_changes(self, mock_run_cmd: Mock) -> None:
        """Verify returns True when there are staged changes."""
        # rc != 0 means there are staged changes
        mock_run_cmd.return_value = ("", "", 1)

        result = git_has_staged_changes(Path("/repo"))

        self.assertTrue(result)
        mock_run_cmd.assert_called_once_with(
            ["git", "diff", "--cached", "--quiet"], cwd=Path("/repo"), check=False
        )

    @patch("auto_prd.git_ops.run_cmd")
    def test_no_staged_changes(self, mock_run_cmd: Mock) -> None:
        """Verify returns False when no staged changes."""
        # rc = 0 means no staged changes
        mock_run_cmd.return_value = ("", "", 0)

        result = git_has_staged_changes(Path("/repo"))

        self.assertFalse(result)


class GitCommitTests(unittest.TestCase):
    """Test git_commit() function."""

    @patch("auto_prd.git_ops.run_cmd")
    def test_commit(self, mock_run_cmd: Mock) -> None:
        """Verify git commit is called."""
        git_commit(Path("/repo"), "test message")

        mock_run_cmd.assert_called_once_with(
            ["git", "commit", "-m", "test message"], cwd=Path("/repo")
        )


class GitPushBranchTests(unittest.TestCase):
    """Test git_push_branch() function."""

    @patch("auto_prd.git_ops.run_cmd")
    def test_successful_push(self, mock_run_cmd: Mock) -> None:
        """Verify successful push."""
        mock_run_cmd.return_value = ("", "", 0)

        git_push_branch(Path("/repo"), "feature")

        mock_run_cmd.assert_called_once_with(
            ["git", "push", "-u", "origin", "feature"],
            cwd=Path("/repo"),
            retries=3,
            retry_on_codes={128},
            retry_on_stderr=_GIT_TRANSIENT_ERRORS,
            backoff_base=2.0,
        )

    @patch("auto_prd.git_ops.run_cmd")
    @patch("auto_prd.git_ops.logger")
    def test_push_with_custom_retries(
        self, mock_logger: Mock, mock_run_cmd: Mock
    ) -> None:
        """Verify push retries with custom retry count."""
        # Just verify the retry parameters are passed correctly
        # Actual retry logic is tested in command.py tests
        mock_run_cmd.return_value = ("", "", 0)

        git_push_branch(Path("/repo"), "feature", retries=5)

        mock_run_cmd.assert_called_once_with(
            ["git", "push", "-u", "origin", "feature"],
            cwd=Path("/repo"),
            retries=5,
            retry_on_codes={128},
            retry_on_stderr=_GIT_TRANSIENT_ERRORS,
            backoff_base=2.0,
        )


class GitTransientErrorsTests(unittest.TestCase):
    """Test GIT_TRANSIENT_ERRORS constant."""

    def test_transient_errors_list(self) -> None:
        """Verify transient errors list contains expected patterns."""
        self.assertIn("Connection reset by peer", _GIT_TRANSIENT_ERRORS)
        self.assertIn("Could not resolve host", _GIT_TRANSIENT_ERRORS)
        self.assertIn("Connection timed out", _GIT_TRANSIENT_ERRORS)
        self.assertIn("RPC failed", _GIT_TRANSIENT_ERRORS)


if __name__ == "__main__":
    unittest.main()
