"""Integration tests for multi_repo CLI module.

This module tests the multi_repo CLI wiring including argument parsing,
config loading precedence, combining config and CLI args, exit codes,
and table printing via the main() entry point.
"""

import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from support_mode.config_file import Config, MultiRepoConfig
from support_mode.multi_repo_cli import build_parser, main


class TestBuildParser:
    """Tests for build_parser function."""

    def test_parser_has_all_arguments(self):
        """Test that parser has all expected arguments."""
        parser = build_parser()

        # Test parsing with all arguments
        args = parser.parse_args(
            [
                "--config",
                "/path/to/config.yaml",
                "--repo",
                "/repo1",
                "--repo",
                "/repo2",
                "--parallel",
                "8",
                "--width",
                "160",
            ]
        )

        assert args.config == Path("/path/to/config.yaml")
        assert args.repo == ["/repo1", "/repo2"]
        assert args.parallel == 8
        assert args.width == 160

    def test_parser_defaults(self):
        """Test that parser has correct default values."""
        parser = build_parser()
        args = parser.parse_args([])

        assert args.config is None
        assert args.repo is None
        assert args.parallel == 4
        assert args.width == 120

    def test_repo_is_append_action(self):
        """Test that --repo can be specified multiple times."""
        parser = build_parser()
        args = parser.parse_args(["--repo", "r1", "--repo", "r2", "--repo", "r3"])

        assert args.repo == ["r1", "r2", "r3"]


class TestMainExitCodes:
    """Tests for main() exit codes."""

    def test_exit_code_zero_on_success(self):
        """Test that main returns 0 on successful execution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            repo_path.joinpath(".git").mkdir()

            with mock.patch(
                "sys.argv", ["multi-repo", "--repo", str(repo_path)]
            ), mock.patch(
                "support_mode.multi_repo.git_current_branch", return_value="main"
            ), mock.patch(
                "support_mode.multi_repo.git_head_sha", return_value="abc123def456"
            ):
                exit_code = main()
                assert exit_code == 0

    def test_exit_code_one_when_no_repos(self):
        """Test that main returns 1 when no repositories are specified."""
        with mock.patch("sys.argv", ["multi-repo"]):
            exit_code = main()
            assert exit_code == 1

    def test_exit_code_zero_with_config_repos(self):
        """Test that main returns 0 when repos are loaded from config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            repo_path.joinpath(".git").mkdir()

            # Create a mock config with repos
            mock_config = Config(
                multi_repo=MultiRepoConfig(
                    enabled=True,
                    repos=[{"path": str(repo_path)}],
                )
            )

            with mock.patch(
                "sys.argv", ["multi-repo", "--config", "/fake/config.yaml"]
            ), mock.patch(
                "support_mode.config_file.Config.load", return_value=mock_config
            ), mock.patch(
                "support_mode.multi_repo.git_current_branch", return_value="main"
            ), mock.patch(
                "support_mode.multi_repo.git_head_sha", return_value="abc123def456"
            ):
                exit_code = main()
                assert exit_code == 0


class TestMainConfigLoading:
    """Tests for config loading precedence in main()."""

    def test_config_loaded_when_specified(self):
        """Test that config file is loaded when --config is provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo1 = Path(tmpdir) / "repo1"
            repo1.mkdir()
            repo1.joinpath(".git").mkdir()

            # Create a mock config with repos
            mock_config = Config(
                multi_repo=MultiRepoConfig(
                    enabled=True,
                    repos=[{"path": str(repo1)}],
                )
            )

            with mock.patch(
                "sys.argv", ["multi-repo", "--config", "/fake/config.yaml"]
            ), mock.patch(
                "support_mode.config_file.Config.load", return_value=mock_config
            ), mock.patch(
                "support_mode.multi_repo.git_current_branch", return_value="main"
            ), mock.patch(
                "support_mode.multi_repo.git_head_sha", return_value="abc123def456"
            ), mock.patch(
                "support_mode.multi_repo_cli.format_repo_table"
            ) as mock_format:
                mock_format.return_value = "Mock Table"
                main()
                # Should have checked exactly one repo from config
                mock_format.assert_called_once()

    def test_config_not_loaded_when_disabled(self):
        """Test that repos are not loaded from config when multi_repo.enabled=false."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            repo_path.joinpath(".git").mkdir()

            # Config with disabled multi_repo
            mock_config = Config(
                multi_repo=MultiRepoConfig(
                    enabled=False,
                    repos=[{"path": "/some/other/path"}],
                )
            )

            with mock.patch(
                "sys.argv",
                [
                    "multi-repo",
                    "--config",
                    "/fake/config.yaml",
                    "--repo",
                    str(repo_path),
                ],
            ), mock.patch(
                "support_mode.config_file.Config.load", return_value=mock_config
            ), mock.patch(
                "support_mode.multi_repo.git_current_branch", return_value="main"
            ), mock.patch(
                "support_mode.multi_repo.git_head_sha", return_value="abc123def456"
            ), mock.patch(
                "support_mode.multi_repo_cli.format_repo_table"
            ) as mock_format:
                mock_format.return_value = "Mock Table"
                main()
                # Should use CLI repo, not config repo (since config disabled)
                call_args = mock_format.call_args
                statuses = call_args[0][0]
                assert len(statuses) == 1
                assert statuses[0].path == str(repo_path)

    def test_cli_repos_added_to_config_repos(self):
        """Test that --repo arguments are added to repos from config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo1 = Path(tmpdir) / "repo1"
            repo1.mkdir()
            repo1.joinpath(".git").mkdir()

            repo2 = Path(tmpdir) / "repo2"
            repo2.mkdir()
            repo2.joinpath(".git").mkdir()

            # Config with one repo
            mock_config = Config(
                multi_repo=MultiRepoConfig(
                    enabled=True,
                    repos=[{"path": str(repo1)}],
                )
            )

            with mock.patch(
                "sys.argv",
                ["multi-repo", "--config", "/fake/config.yaml", "--repo", str(repo2)],
            ), mock.patch(
                "support_mode.config_file.Config.load", return_value=mock_config
            ), mock.patch(
                "support_mode.multi_repo.git_current_branch", return_value="main"
            ), mock.patch(
                "support_mode.multi_repo.git_head_sha", return_value="abc123def456"
            ), mock.patch(
                "support_mode.multi_repo_cli.format_repo_table"
            ) as mock_format:
                mock_format.return_value = "Mock Table"
                main()
                # Should have checked 2 repos (1 from config + 1 from CLI)
                call_args = mock_format.call_args
                statuses = call_args[0][0]
                assert len(statuses) == 2
                repo_names = {s.name for s in statuses}
                assert "repo1" in repo_names
                assert "repo2" in repo_names

    def test_config_file_missing_repos_uses_cli_only(self):
        """Test that when config has no repos, only CLI repos are used."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            repo_path.joinpath(".git").mkdir()

            # Config with enabled but empty repos list
            mock_config = Config(
                multi_repo=MultiRepoConfig(
                    enabled=True,
                    repos=[],
                )
            )

            with mock.patch(
                "sys.argv",
                [
                    "multi-repo",
                    "--config",
                    "/fake/config.yaml",
                    "--repo",
                    str(repo_path),
                ],
            ), mock.patch(
                "support_mode.config_file.Config.load", return_value=mock_config
            ), mock.patch(
                "support_mode.multi_repo.git_current_branch", return_value="main"
            ), mock.patch(
                "support_mode.multi_repo.git_head_sha", return_value="abc123def456"
            ):
                exit_code = main()
                # Should succeed with CLI-provided repo
                assert exit_code == 0


class TestMainErrorPaths:
    """Tests for error handling in main()."""

    def test_no_repositories_error_message(self):
        """Test error message when no repositories are specified."""
        with mock.patch("sys.argv", ["multi-repo"]), mock.patch(
            "sys.stderr", new_callable=StringIO
        ) as mock_stderr:
            exit_code = main()
            assert exit_code == 1
            error_output = mock_stderr.getvalue()
            assert "No repositories specified" in error_output
            assert "--config" in error_output
            assert "--repo" in error_output

    def test_config_file_not_found_is_ok(self):
        """Test that a missing config file doesn't crash, just uses CLI repos."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            repo_path.joinpath(".git").mkdir()

            # Config.load returns default (empty) config when file not found
            with mock.patch(
                "sys.argv",
                [
                    "multi-repo",
                    "--config",
                    "/nonexistent.yaml",
                    "--repo",
                    str(repo_path),
                ],
            ), mock.patch(
                "support_mode.config_file.Config.load", return_value=Config()
            ), mock.patch(
                "support_mode.multi_repo.git_current_branch", return_value="main"
            ), mock.patch(
                "support_mode.multi_repo.git_head_sha", return_value="abc123def456"
            ):
                # Should succeed with CLI-provided repo, config silently ignored
                exit_code = main()
                assert exit_code == 0


class TestMainOutput:
    """Tests for table output from main()."""

    def test_table_is_printed(self):
        """Test that formatted table is printed to stdout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            repo_path.joinpath(".git").mkdir()

            with mock.patch(
                "sys.argv", ["multi-repo", "--repo", str(repo_path)]
            ), mock.patch(
                "support_mode.multi_repo.git_current_branch", return_value="main"
            ), mock.patch(
                "support_mode.multi_repo.git_head_sha", return_value="abc123def456"
            ), mock.patch(
                "sys.stdout", new_callable=StringIO
            ) as mock_stdout:
                exit_code = main()
                assert exit_code == 0

                output = mock_stdout.getvalue()
                # Should contain table headers
                assert "Repository" in output or repo_path.name in output

    def test_custom_width_is_used(self):
        """Test that custom --width affects table output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            repo_path.joinpath(".git").mkdir()

            with mock.patch(
                "sys.argv", ["multi-repo", "--repo", str(repo_path), "--width", "80"]
            ), mock.patch(
                "support_mode.multi_repo.git_current_branch", return_value="main"
            ), mock.patch(
                "support_mode.multi_repo.git_head_sha", return_value="abc123def456"
            ), mock.patch(
                "support_mode.multi_repo_cli.format_repo_table"
            ) as mock_format:
                mock_format.return_value = "Table\n"
                main()

                # Check that width was passed correctly
                call_kwargs = mock_format.call_args[1]
                assert call_kwargs.get("width") == 80

    def test_custom_parallel_is_used(self):
        """Test that custom --parallel affects worker count."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            repo_path.joinpath(".git").mkdir()

            with mock.patch(
                "sys.argv", ["multi-repo", "--repo", str(repo_path), "--parallel", "2"]
            ), mock.patch(
                "support_mode.multi_repo.git_current_branch", return_value="main"
            ), mock.patch(
                "support_mode.multi_repo.git_head_sha", return_value="abc123def456"
            ), mock.patch(
                "support_mode.multi_repo_cli.check_repositories_parallel"
            ) as mock_check:
                mock_check.return_value = []
                main()

                # Check that parallel was passed correctly
                call_kwargs = mock_check.call_args[1]
                assert call_kwargs.get("max_workers") == 2


class TestMainArgumentCombinations:
    """Tests for various argument combinations."""

    def test_multiple_cli_repos(self):
        """Test main with multiple --repo arguments."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo1 = Path(tmpdir) / "repo1"
            repo1.mkdir()
            repo1.joinpath(".git").mkdir()

            repo2 = Path(tmpdir) / "repo2"
            repo2.mkdir()
            repo2.joinpath(".git").mkdir()

            with mock.patch(
                "sys.argv", ["multi-repo", "--repo", str(repo1), "--repo", str(repo2)]
            ), mock.patch(
                "support_mode.multi_repo.git_current_branch", return_value="main"
            ), mock.patch(
                "support_mode.multi_repo.git_head_sha", return_value="abc123def456"
            ), mock.patch(
                "support_mode.multi_repo_cli.format_repo_table"
            ) as mock_format:
                mock_format.return_value = "Table\n"
                main()

                call_args = mock_format.call_args
                statuses = call_args[0][0]
                assert len(statuses) == 2

    def test_config_and_cli_repos_combined(self):
        """Test that config and CLI repos are properly combined."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_repo = Path(tmpdir) / "config_repo"
            config_repo.mkdir()
            config_repo.joinpath(".git").mkdir()

            cli_repo = Path(tmpdir) / "cli_repo"
            cli_repo.mkdir()
            cli_repo.joinpath(".git").mkdir()

            # Config with one repo
            mock_config = Config(
                multi_repo=MultiRepoConfig(
                    enabled=True,
                    repos=[{"path": str(config_repo)}],
                )
            )

            with mock.patch(
                "sys.argv",
                [
                    "multi-repo",
                    "--config",
                    "/fake/config.yaml",
                    "--repo",
                    str(cli_repo),
                ],
            ), mock.patch(
                "support_mode.config_file.Config.load", return_value=mock_config
            ), mock.patch(
                "support_mode.multi_repo.git_current_branch", return_value="main"
            ), mock.patch(
                "support_mode.multi_repo.git_head_sha", return_value="abc123def456"
            ), mock.patch(
                "support_mode.multi_repo_cli.format_repo_table"
            ) as mock_format:
                mock_format.return_value = "Table\n"
                main()

                call_args = mock_format.call_args
                statuses = call_args[0][0]
                assert len(statuses) == 2
                repo_names = {s.name for s in statuses}
                assert "config_repo" in repo_names
                assert "cli_repo" in repo_names
