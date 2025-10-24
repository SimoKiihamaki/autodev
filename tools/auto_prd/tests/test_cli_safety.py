import unittest

from tools.auto_prd.command import validate_command_args
from tools.auto_prd.utils import scrub_cli_text


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
            validate_command_args(["gh", "pr", "create", "--body", "contains `backticks`"])

    def test_accepts_scrubbed_arguments(self) -> None:
        safe_body = scrub_cli_text("contains `backticks`")
        # Should not raise once sanitized.
        validate_command_args(["gh", "pr", "create", "--body", safe_body])


if __name__ == "__main__":
    unittest.main()
