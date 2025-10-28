import subprocess
import unittest

from .test_helpers import safe_import

CLI_ARG_REPLACEMENTS = safe_import(
    "tools.auto_prd.constants", "..constants", "CLI_ARG_REPLACEMENTS"
)
UNSAFE_ARG_CHARS = safe_import(
    "tools.auto_prd.constants", "..constants", "UNSAFE_ARG_CHARS"
)
extract_called_process_error_details = safe_import(
    "tools.auto_prd.utils", "..utils", "extract_called_process_error_details"
)
extract_http_status = safe_import(
    "tools.auto_prd.utils", "..utils", "extract_http_status"
)
parse_tasks_left = safe_import("tools.auto_prd.utils", "..utils", "parse_tasks_left")
scrub_cli_text = safe_import("tools.auto_prd.utils", "..utils", "scrub_cli_text")


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


class ExtractHttpStatusTests(unittest.TestCase):
    def test_handles_mixed_byte_streams(self) -> None:
        exc = subprocess.CalledProcessError(
            1,
            ["gh", "api"],
            output=b"HTTP 404: not found",
            stderr="failure details",
        )
        self.assertEqual(extract_http_status(exc), "404")

    def test_handles_empty_streams_without_type_error(self) -> None:
        exc = subprocess.CalledProcessError(
            1,
            ["gh", "api"],
            output="",
            stderr=b"",
        )
        self.assertIsNone(extract_http_status(exc))


class ParseTasksLeftTests(unittest.TestCase):
    def test_parses_value_when_present(self) -> None:
        self.assertEqual(parse_tasks_left("TASKS_LEFT=3"), 3)

    def test_returns_none_when_missing(self) -> None:
        self.assertIsNone(parse_tasks_left("no counter here"))


class ScrubCliTextTests(unittest.TestCase):
    def test_replaces_unsafe_characters(self) -> None:
        sanitized = scrub_cli_text("`hello|world<foo;bar>`")
        self.assertNotIn("`", sanitized)
        self.assertNotIn("|", sanitized)
        self.assertNotIn("<", sanitized)
        self.assertNotIn(";", sanitized)
        self.assertIn("'", sanitized)
        self.assertIn("/", sanitized)
        self.assertIn("(", sanitized)
        self.assertIn(",", sanitized)

    def test_returns_original_when_safe(self) -> None:
        text = "Implement: sample.md"
        self.assertEqual(scrub_cli_text(text), text)

    def test_replaces_each_unsafe_character_with_expected_mapping(self) -> None:
        for char in UNSAFE_ARG_CHARS:
            original = f"prefix{char}suffix"
            sanitized = scrub_cli_text(original)
            self.assertTrue(
                sanitized.startswith("prefix"), msg=f"prefix lost for {char!r}"
            )
            replacement = CLI_ARG_REPLACEMENTS.get(char, " ")
            self.assertNotIn(char, sanitized)
            self.assertIn(replacement, sanitized)

    def test_handles_mixed_unsafe_sequence(self) -> None:
        original = "a>b;c"
        sanitized = scrub_cli_text(original)
        self.assertEqual(sanitized, "a)b,c")


if __name__ == "__main__":
    unittest.main()
