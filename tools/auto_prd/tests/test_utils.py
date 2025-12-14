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
is_valid_int = safe_import("tools.auto_prd.utils", "..utils", "is_valid_int")
is_valid_numeric = safe_import("tools.auto_prd.utils", "..utils", "is_valid_numeric")
parse_tasks_left = safe_import("tools.auto_prd.utils", "..utils", "parse_tasks_left")
sanitize_for_cli = safe_import("tools.auto_prd.utils", "..utils", "sanitize_for_cli")
scrub_cli_text = safe_import("tools.auto_prd.utils", "..utils", "scrub_cli_text")


class ExtractCalledProcessErrorDetailsTests(unittest.TestCase):
    def test_uses_stderr_only_not_stdout(self) -> None:
        """Verify function uses stderr only, ignoring stdout for security reasons.

        This test ensures that only stderr is used in error details and stdout is
        ignored to prevent sensitive model output (secrets, PII, tokens) from
        appearing in error messages.

        The test data uses realistic secret patterns to demonstrate the security
        vulnerability being prevented. If stdout were included in error details,
        these secrets would leak into logs, error messages, and exception traces.

        For migration notes on this behavior change, see CHANGELOG.md.
        """
        # Use realistic secret patterns that could appear in LLM output
        # These demonstrate what would leak if stdout were included in error details
        stdout_with_secrets = (
            b"Here's the code you requested:\n"
            b"API_KEY=sk-1234567890abcdef1234567890abcdef\n"
            b"GITHUB_TOKEN=ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ012345678\n"
            b"DATABASE_URL=postgres://user:password123@localhost/db\n"
            b"Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xxx\n"
        )
        exc = subprocess.CalledProcessError(
            1,
            ["coderabbit", "--prompt-only"],
            output=stdout_with_secrets,
            stderr=None,
        )
        details = extract_called_process_error_details(exc)
        self.assertIsInstance(details, str)
        # Should NOT contain ANY stdout content (security: stdout may have sensitive data)
        self.assertNotIn("sk-", details)
        self.assertNotIn("ghp_", details)
        self.assertNotIn("password", details)
        self.assertNotIn("Bearer", details)
        self.assertNotIn("API_KEY", details)
        # Should fall back to exit code when stderr is empty (new behavior)
        self.assertEqual(details, "exit code 1")

    def test_returns_stderr_when_available(self) -> None:
        """Verify function returns stderr content when available."""
        exc = subprocess.CalledProcessError(
            1,
            ["cmd"],
            output=b"stdout content to ignore",
            stderr=b"actual error message from stderr",
        )
        details = extract_called_process_error_details(exc)
        self.assertEqual(details, "actual error message from stderr")
        self.assertNotIn("stdout", details)

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


class IsValidIntTests(unittest.TestCase):
    """Tests for is_valid_int helper function."""

    def test_returns_true_for_integer(self) -> None:
        """Verify function returns True for regular integers."""
        self.assertTrue(is_valid_int(42))
        self.assertTrue(is_valid_int(0))
        self.assertTrue(is_valid_int(-1))

    def test_returns_false_for_boolean(self) -> None:
        """Verify function excludes booleans (which are subclass of int in Python)."""
        self.assertFalse(is_valid_int(True))
        self.assertFalse(is_valid_int(False))

    def test_returns_false_for_float(self) -> None:
        """Verify function returns False for floats."""
        self.assertFalse(is_valid_int(3.14))
        self.assertFalse(is_valid_int(0.0))

    def test_returns_false_for_string(self) -> None:
        """Verify function returns False for strings."""
        self.assertFalse(is_valid_int("42"))
        self.assertFalse(is_valid_int(""))

    def test_returns_false_for_none(self) -> None:
        """Verify function returns False for None."""
        self.assertFalse(is_valid_int(None))


class IsValidNumericTests(unittest.TestCase):
    """Tests for is_valid_numeric helper function."""

    def test_returns_true_for_integer(self) -> None:
        """Verify function returns True for integers."""
        self.assertTrue(is_valid_numeric(42))
        self.assertTrue(is_valid_numeric(0))
        self.assertTrue(is_valid_numeric(-1))

    def test_returns_true_for_float(self) -> None:
        """Verify function returns True for floats."""
        self.assertTrue(is_valid_numeric(3.14))
        self.assertTrue(is_valid_numeric(0.0))
        self.assertTrue(is_valid_numeric(-1.5))

    def test_returns_false_for_boolean(self) -> None:
        """Verify function excludes booleans (which are subclass of int in Python)."""
        self.assertFalse(is_valid_numeric(True))
        self.assertFalse(is_valid_numeric(False))

    def test_returns_false_for_string(self) -> None:
        """Verify function returns False for strings."""
        self.assertFalse(is_valid_numeric("3.14"))
        self.assertFalse(is_valid_numeric(""))

    def test_returns_false_for_none(self) -> None:
        """Verify function returns False for None."""
        self.assertFalse(is_valid_numeric(None))


class SanitizeForCliTests(unittest.TestCase):
    """Tests for sanitize_for_cli helper function."""

    def test_replaces_unsafe_characters(self) -> None:
        """Verify function replaces unsafe CLI characters."""
        text = "`command|arg;stuff<data>`"
        sanitized = sanitize_for_cli(text)
        self.assertNotIn("`", sanitized)
        self.assertNotIn("|", sanitized)
        self.assertNotIn(";", sanitized)
        self.assertNotIn("<", sanitized)
        self.assertNotIn(">", sanitized)

    def test_preserves_safe_characters(self) -> None:
        """Verify function preserves safe characters."""
        text = "safe text with spaces and numbers 123"
        self.assertEqual(sanitize_for_cli(text), text)

    def test_handles_empty_string(self) -> None:
        """Verify function handles empty string."""
        self.assertEqual(sanitize_for_cli(""), "")

    def test_replacement_values_match_cli_arg_replacements(self) -> None:
        """Verify replacements match CLI_ARG_REPLACEMENTS mapping."""
        for unsafe, safe in CLI_ARG_REPLACEMENTS.items():
            text = f"prefix{unsafe}suffix"
            sanitized = sanitize_for_cli(text)
            self.assertEqual(sanitized, f"prefix{safe}suffix")


if __name__ == "__main__":
    unittest.main()
