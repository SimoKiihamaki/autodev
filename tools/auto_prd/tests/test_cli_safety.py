import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ..command import (
    CLAUDE_DEBUG_LOG_NAME,
    ensure_claude_debug_dir,
    run_cmd,
    validate_command_args,
    register_safe_cwd,
)
from ..utils import scrub_cli_text
from ..pr_flow import open_or_get_pr


class ScrubCliTextTests(unittest.TestCase):
    def test_replaces_disallowed_characters(self) -> None:
        original = "Use `/tmp/foo|bar;baz<qux>`"
        cleaned = scrub_cli_text(original)
        self.assertEqual(cleaned, "Use '/tmp/foo/bar,baz(qux)'")

    def test_is_idempotent_for_safe_strings(self) -> None:
        text = "Plain text without shell meta"
        self.assertIs(scrub_cli_text(text), text)


class ValidateCommandArgsTests(unittest.TestCase):
    def test_rejects_unsafe_arguments(self) -> None:
        with self.assertRaises(ValueError):
            validate_command_args(
                ["gh", "pr", "create", "--body", "contains `backticks`"]
            )

    def test_accepts_scrubbed_arguments(self) -> None:
        safe_body = scrub_cli_text("contains `backticks`")
        # Should not raise once sanitized.
        validate_command_args(["gh", "pr", "create", "--body", safe_body])


class EnsureClaudeDebugDirTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = os.environ.copy()
        register_safe_cwd(Path(__file__).parent)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._env_backup)

    def test_converts_directory_env_value_into_log_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["CLAUDE_CODE_DEBUG_LOGS_DIR"] = tmpdir
            path = ensure_claude_debug_dir()
            self.assertTrue(
                path.is_file(), msg="expected Claude debug path to become a file"
            )
            self.assertTrue(path.name.endswith(CLAUDE_DEBUG_LOG_NAME))
            self.assertEqual(Path(os.environ["CLAUDE_CODE_DEBUG_LOGS_DIR"]), path)

    def test_creates_repo_local_file_when_variable_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = Path.cwd()
            try:
                os.chdir(tmpdir)
                os.environ.pop("CLAUDE_CODE_DEBUG_LOGS_DIR", None)
                path = ensure_claude_debug_dir()
                self.assertTrue(path.exists())
                self.assertEqual(path.parent.resolve(), Path(tmpdir).resolve())
            finally:
                os.chdir(original_cwd)


class RequireCmdClaudeTests(unittest.TestCase):
    def test_require_cmd_invokes_debug_dir_setup(self) -> None:
        with mock.patch(
            "tools.auto_prd.command_checks.shutil.which", return_value="/usr/bin/claude"
        ), mock.patch(
            "tools.auto_prd.command_checks.run_cmd", return_value=("", "", 0)
        ), mock.patch(
            "tools.auto_prd.command_checks.ensure_claude_debug_dir"
        ) as ensure_mock:
            from ..command_checks import require_cmd

            require_cmd("claude")
            ensure_mock.assert_called_once()


class RunCmdTests(unittest.TestCase):
    def setUp(self):
        register_safe_cwd(Path(__file__).parent)

    @mock.patch("tools.auto_prd.command.subprocess.run")
    @mock.patch("tools.auto_prd.command.env_with_zsh", return_value={})
    @mock.patch("tools.auto_prd.command.shutil.which", return_value="/usr/bin/gh")
    def test_auto_sanitizes_arguments(
        self, _mock_which, _mock_env_with_zsh, mock_run
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["gh"],
            returncode=0,
            stdout=b"",
            stderr=b"",
        )

        stdout, stderr, code = run_cmd(
            ["gh", "pr", "create", "--body", "contains `code`"]
        )

        self.assertEqual(stdout, "")
        self.assertEqual(stderr, "")
        self.assertEqual(code, 0)
        executed_cmd = mock_run.call_args[0][0]
        body_index = executed_cmd.index("--body") + 1
        self.assertEqual(executed_cmd[body_index], "contains 'code'")
        self.assertNotIn("`", executed_cmd[body_index])


class OpenOrGetPrTests(unittest.TestCase):
    def setUp(self):
        register_safe_cwd(Path(__file__).parent)

    def test_pr_arguments_passed_to_gh_are_sanitized(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            prd_path = repo_root / "AGENTS.md"
            prd_path.write_text("placeholder", encoding="utf-8")

            call_sequence: list[list[str]] = []

            def fake_run_cmd(cmd, **kwargs):
                call_sequence.append(cmd)
                if cmd[:3] == ["git", "rev-list", "--count"]:
                    return ("1\n", "", 0)
                if cmd[:2] == ["gh", "pr"]:
                    body_index = cmd.index("--body") + 1
                    title_index = cmd.index("--title") + 1
                    self.assertNotIn("`", cmd[body_index])
                    self.assertNotIn("`", cmd[title_index])
                    return ("101", "", 0)
                return ("", "", 0)

            pr_lookup_calls = {"count": 0}

            def fake_get_pr_number(*_args, **_kwargs):
                pr_lookup_calls["count"] += 1
                if pr_lookup_calls["count"] == 1:
                    return None
                return 101

            with mock.patch(
                "tools.auto_prd.pr_flow.run_cmd", side_effect=fake_run_cmd
            ), mock.patch(
                "tools.auto_prd.pr_flow.get_pr_number_for_head",
                side_effect=fake_get_pr_number,
            ), mock.patch(
                "tools.auto_prd.pr_flow.git_push_branch"
            ):
                pr_number = open_or_get_pr(
                    new_branch="feature/test",
                    base_branch="main",
                    repo_root=repo_root,
                    prd_path=prd_path,
                    codex_model="gpt",
                    allow_unsafe_execution=False,
                    dry_run=False,
                    skip_runner=True,
                    already_pushed=True,
                )

            self.assertEqual(pr_number, 101)
            self.assertTrue(any(cmd[:2] == ["gh", "pr"] for cmd in call_sequence))


if __name__ == "__main__":
    unittest.main()
