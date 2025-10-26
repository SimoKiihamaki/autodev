import subprocess
import unittest

from tools.auto_prd.utils import (
    extract_called_process_error_details,
    parse_tasks_left,
    scrub_cli_text,
)


class ExtractCalledProcessErrorDetailsTests(unittest.TestCase):
    def test_decodes_byte_outputs(self) -> None:
        exc = subprocess.CalledProcessError(
            1,
            ["coderabbit", "--prompt-only"],
            output=b"try again after 1 minutes and 5 seconds",
            stderr=None,
        )
        details = extract_called_process_error_details(exc)
        self.assertIsInstance(details, str)
        self.assertIn("try again after 1 minutes", details)

    def test_falls_back_to_exit_code(self) -> None:
        exc = subprocess.CalledProcessError(2, ["cmd"])
        self.assertEqual(extract_called_process_error_details(exc), "exit code 2")


class ParseTasksLeftTests(unittest.TestCase):
    def test_parses_value_when_present(self) -> None:
        self.assertEqual(parse_tasks_left("TASKS_LEFT=3"), 3)

    def test_returns_none_when_missing(self) -> None:
        self.assertIsNone(parse_tasks_left("no counter here"))


class ScrubCliTextTests(unittest.TestCase):
    def test_replaces_unsafe_characters(self) -> None:
        sanitized = scrub_cli_text("`hello|world<foo>`")
        self.assertNotIn("`", sanitized)
        self.assertNotIn("|", sanitized)
        self.assertNotIn("<", sanitized)
        self.assertIn("'", sanitized)
        self.assertIn("/", sanitized)
        self.assertIn("(", sanitized)

    def test_returns_original_when_safe(self) -> None:
        text = "Implement: sample.md"
        self.assertEqual(scrub_cli_text(text), text)


if __name__ == "__main__":
    unittest.main()
