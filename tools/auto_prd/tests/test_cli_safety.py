import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from .test_helpers import safe_import


def get_expected_repo_root() -> Path:
    """Get the expected repository root directory for test purposes.

    Returns:
        Path to the repository root directory (3 levels up from the test file)
    """
    return Path(__file__).resolve().parents[3]


CLAUDE_DEBUG_LOG_NAME = safe_import(
    "tools.auto_prd.command", "..command", "CLAUDE_DEBUG_LOG_NAME"
)
ensure_claude_debug_dir = safe_import(
    "tools.auto_prd.command", "..command", "ensure_claude_debug_dir"
)
run_cmd = safe_import("tools.auto_prd.command", "..command", "run_cmd")
validate_command_args = safe_import(
    "tools.auto_prd.command", "..command", "validate_command_args"
)
register_safe_cwd = safe_import(
    "tools.auto_prd.command", "..command", "register_safe_cwd"
)
scrub_cli_text = safe_import("tools.auto_prd.utils", "..utils", "scrub_cli_text")
open_or_get_pr = safe_import("tools.auto_prd.pr_flow", "..pr_flow", "open_or_get_pr")


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
            validate_command_args(["gh", "pr", "create", "--body", "contains | pipe"])

    def test_allows_backticks(self) -> None:
        try:
            validate_command_args(
                ["gh", "pr", "create", "--body", "contains `backticks`"]
            )
        except ValueError as exc:  # pragma: no cover - defensive path
            self.fail(f"validate_command_args unexpectedly rejected backticks: {exc}")

    def test_accepts_scrubbed_arguments(self) -> None:
        safe_body = scrub_cli_text("contains `backticks`")
        # Should not raise once sanitized.
        validate_command_args(["gh", "pr", "create", "--body", safe_body])


class EnsureClaudeDebugDirTests(unittest.TestCase):
    def setUp(self) -> None:
        register_safe_cwd(Path(__file__).parent)

    def test_converts_directory_env_value_into_log_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict(os.environ, {"CLAUDE_CODE_DEBUG_LOGS_DIR": tmpdir}):
                path = ensure_claude_debug_dir()
                expected = (get_expected_repo_root() / ".claude-debug").resolve()
                self.assertTrue(
                    path.is_file(), msg="expected Claude debug path to become a file"
                )
                self.assertEqual(path.resolve(), expected)
                self.assertEqual(
                    Path(os.environ["CLAUDE_CODE_DEBUG_LOGS_DIR"]).resolve(), expected
                )

    def test_creates_repo_local_file_when_variable_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = Path.cwd()
            try:
                os.chdir(tmpdir)
                with mock.patch.dict(os.environ, clear=True):
                    path = ensure_claude_debug_dir()
                    self.assertTrue(path.exists())
                    expected = (get_expected_repo_root() / ".claude-debug").resolve()
                    self.assertEqual(path.resolve(), expected)
            finally:
                os.chdir(original_cwd)


class RequireCmdClaudeTests(unittest.TestCase):
    def test_require_cmd_invokes_debug_dir_setup(self) -> None:
        with mock.patch.dict(os.environ, clear=True):
            with mock.patch(
                "tools.auto_prd.command_checks.shutil.which",
                return_value="/usr/bin/claude",
            ), mock.patch(
                "tools.auto_prd.command_checks.run_cmd", return_value=("", "", 0)
            ):
                from ..command_checks import require_cmd

                require_cmd("claude")

            expected = (get_expected_repo_root() / ".claude-debug").resolve()
            self.assertEqual(
                Path(os.environ["CLAUDE_CODE_DEBUG_LOGS_DIR"]).resolve(), expected
            )


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
