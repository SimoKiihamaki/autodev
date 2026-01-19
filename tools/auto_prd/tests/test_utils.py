import subprocess
import tempfile
import unittest
from pathlib import Path

from .test_helpers import safe_import

CLI_ARG_REPLACEMENTS = safe_import(
    "tools.auto_prd.constants", "auto_prd.constants", "CLI_ARG_REPLACEMENTS"
)
UNSAFE_ARG_CHARS = safe_import(
    "tools.auto_prd.constants", "auto_prd.constants", "UNSAFE_ARG_CHARS"
)
compute_file_hash = safe_import("tools.auto_prd.utils", "auto_prd.utils", "compute_file_hash")
extract_called_process_error_details = safe_import(
    "tools.auto_prd.utils", "auto_prd.utils", "extract_called_process_error_details"
)
extract_http_status = safe_import(
    "tools.auto_prd.utils", "auto_prd.utils", "extract_http_status"
)
get_prd_hash = safe_import("tools.auto_prd.utils", "auto_prd.utils", "get_prd_hash")
is_valid_int = safe_import("tools.auto_prd.utils", "auto_prd.utils", "is_valid_int")
is_valid_numeric = safe_import("tools.auto_prd.utils", "auto_prd.utils", "is_valid_numeric")
parse_tasks_left = safe_import("tools.auto_prd.utils", "auto_prd.utils", "parse_tasks_left")
sanitize_for_cli = safe_import("tools.auto_prd.utils", "auto_prd.utils", "sanitize_for_cli")
scrub_cli_text = safe_import("tools.auto_prd.utils", "auto_prd.utils", "scrub_cli_text")


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


class GetPrdHashTests(unittest.TestCase):
    """Tests for get_prd_hash helper function."""

    def test_returns_hash_when_prd_exists(self) -> None:
        """Verify function returns SHA256 hash when PRD.md exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            prd_path = repo_root / "PRD.md"
            prd_path.write_text("# Test PRD\n\nContent here")

            result = get_prd_hash(repo_root)

            self.assertIsInstance(result, str)
            self.assertEqual(len(result), 64)  # SHA256 hex digest length
            self.assertNotEqual(result, "")

    def test_returns_empty_string_when_prd_missing(self) -> None:
        """Verify function returns empty string when PRD.md doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            # Don't create PRD.md

            result = get_prd_hash(repo_root)

            self.assertEqual(result, "")

    def test_returns_hash_for_empty_prd(self) -> None:
        """Verify function returns valid hash even for empty PRD.md."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            prd_path = repo_root / "PRD.md"
            prd_path.write_text("")

            result = get_prd_hash(repo_root)

            # Empty file still has a hash (SHA256 of empty string)
            self.assertEqual(
                result,
                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            )

    def test_hash_changes_when_content_changes(self) -> None:
        """Verify hash value changes when PRD content changes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            prd_path = repo_root / "PRD.md"

            prd_path.write_text("Version 1")
            hash1 = get_prd_hash(repo_root)

            prd_path.write_text("Version 2")
            hash2 = get_prd_hash(repo_root)

            self.assertNotEqual(hash1, hash2)

    def test_hash_is_stable_for_same_content(self) -> None:
        """Verify hash is stable across multiple calls with same content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            prd_path = repo_root / "PRD.md"
            prd_path.write_text("Stable content")

            hash1 = get_prd_hash(repo_root)
            hash2 = get_prd_hash(repo_root)

            self.assertEqual(hash1, hash2)


class ComputeFileHashTests(unittest.TestCase):
    """Tests for compute_file_hash helper function."""

    def test_returns_sha256_hash(self) -> None:
        """Verify function returns SHA256 hash of file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.txt"
            file_path.write_text("Test content")

            result = compute_file_hash(file_path)

            self.assertIsInstance(result, str)
            self.assertEqual(len(result), 64)  # SHA256 hex digest length

    def test_hash_matches_known_value(self) -> None:
        """Verify hash matches known SHA256 value for test content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.txt"
            content = "Hello, World!"
            file_path.write_text(content)

            result = compute_file_hash(file_path)

            # Known SHA256 hash of "Hello, World!" (UTF-8)
            expected = (
                "dffd6021bb2bd5b0af676290809ec3a53191dd81c7f70a4b28688a362182986f"
            )
            self.assertEqual(result, expected)

    def test_handles_large_files_efficiently(self) -> None:
        """Verify function can handle large files without memory issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "large.txt"
            # Create 10MB file
            large_content = "x" * (10 * 1024 * 1024)
            file_path.write_text(large_content)

            result = compute_file_hash(file_path)

            self.assertEqual(len(result), 64)
            self.assertNotEqual(result, "")

    def test_handles_binary_files(self) -> None:
        """Verify function handles binary files correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "binary.bin"
            binary_content = bytes([0, 1, 2, 3, 255, 254, 253])
            file_path.write_bytes(binary_content)

            result = compute_file_hash(file_path)

            self.assertEqual(len(result), 64)
            # Known SHA256 of these bytes
            expected = (
                "db89824d39a30f48b5c79775d5f01f4859e1b80f6d7acde373cd29d6facb3fe6"
            )
            self.assertEqual(result, expected)


if __name__ == "__main__":
    unittest.main()
