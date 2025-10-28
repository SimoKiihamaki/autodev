import os
import unittest
from unittest.mock import patch

from .test_helpers import safe_import

# Import the agents module and functions we need to test
agents = safe_import("tools.auto_prd.agents", "..agents")
_timeout_from_env = safe_import(
    "tools.auto_prd.agents", "..agents", "_timeout_from_env"
)
get_codex_exec_timeout = safe_import(
    "tools.auto_prd.agents", "..agents", "get_codex_exec_timeout"
)
get_claude_exec_timeout = safe_import(
    "tools.auto_prd.agents", "..agents", "get_claude_exec_timeout"
)


class TimeoutConfigurationTests(unittest.TestCase):
    """Test suite for timeout configuration functions."""

    def setUp(self):
        """Set up test environment by clearing relevant environment variables."""
        # Clear any existing timeout environment variables
        env_vars_to_clear = [
            "AUTO_PRD_CODEX_TIMEOUT_SECONDS",
            "AUTO_PRD_CLAUDE_TIMEOUT_SECONDS",
        ]
        for env_var in env_vars_to_clear:
            if env_var in os.environ:
                del os.environ[env_var]

    def test_timeout_from_env_unset_returns_default(self):
        """Test that unset environment variable returns the default value."""
        result = _timeout_from_env("AUTO_PRD_TEST_TIMEOUT", 300)
        self.assertEqual(result, 300)

    def test_timeout_from_env_none_default(self):
        """Test that unset environment variable returns None when default is None."""
        result = _timeout_from_env("AUTO_PRD_TEST_TIMEOUT", None)
        self.assertIsNone(result)

    def test_timeout_from_env_empty_string_returns_none(self):
        """Test that empty string returns None."""
        with patch.dict(os.environ, {"AUTO_PRD_TEST_TIMEOUT": ""}):
            result = _timeout_from_env("AUTO_PRD_TEST_TIMEOUT", 300)
            self.assertIsNone(result)

    def test_timeout_from_env_whitespace_only_returns_none(self):
        """Test that whitespace-only string returns None."""
        with patch.dict(os.environ, {"AUTO_PRD_TEST_TIMEOUT": "   "}):
            result = _timeout_from_env("AUTO_PRD_TEST_TIMEOUT", 300)
            self.assertIsNone(result)

    def test_timeout_from_env_disabled_keywords_return_none(self):
        """Test that various disabled keywords return None."""
        disabled_keywords = ["none", "no", "off", "disable", "disabled"]

        for keyword in disabled_keywords:
            with self.subTest(keyword=keyword):
                with patch.dict(os.environ, {"AUTO_PRD_TEST_TIMEOUT": keyword}):
                    result = _timeout_from_env("AUTO_PRD_TEST_TIMEOUT", 300)
                    self.assertIsNone(result)

    def test_timeout_from_env_disabled_keywords_case_insensitive(self):
        """Test that disabled keywords are case insensitive."""
        disabled_variations = ["NONE", "No", "OFF", "Disable", "DISABLED"]

        for variation in disabled_variations:
            with self.subTest(variation=variation):
                with patch.dict(os.environ, {"AUTO_PRD_TEST_TIMEOUT": variation}):
                    result = _timeout_from_env("AUTO_PRD_TEST_TIMEOUT", 300)
                    self.assertIsNone(result)

    def test_timeout_from_env_disabled_keywords_with_whitespace(self):
        """Test that disabled keywords with whitespace return None."""
        with patch.dict(os.environ, {"AUTO_PRD_TEST_TIMEOUT": "  none  "}):
            result = _timeout_from_env("AUTO_PRD_TEST_TIMEOUT", 300)
            self.assertIsNone(result)

    def test_timeout_from_env_valid_integer_returns_parsed_value(self):
        """Test that valid integer string returns the parsed value."""
        with patch.dict(os.environ, {"AUTO_PRD_TEST_TIMEOUT": "500"}):
            result = _timeout_from_env("AUTO_PRD_TEST_TIMEOUT", 300)
            self.assertEqual(result, 500)

    def test_timeout_from_env_valid_integer_with_whitespace_returns_parsed_value(self):
        """Test that valid integer with whitespace returns the parsed value."""
        with patch.dict(os.environ, {"AUTO_PRD_TEST_TIMEOUT": "  500  "}):
            result = _timeout_from_env("AUTO_PRD_TEST_TIMEOUT", 300)
            self.assertEqual(result, 500)

    def test_timeout_from_env_invalid_format_returns_default(self):
        """Test that invalid format returns the default value."""
        with patch.dict(os.environ, {"AUTO_PRD_TEST_TIMEOUT": "invalid"}):
            result = _timeout_from_env("AUTO_PRD_TEST_TIMEOUT", 300)
            self.assertEqual(result, 300)

    def test_timeout_from_env_non_numeric_string_returns_default(self):
        """Test that non-numeric string returns the default value."""
        invalid_values = ["abc", "12.5", "1e3", "inf", "-inf", "nan"]

        for invalid_value in invalid_values:
            with self.subTest(invalid_value=invalid_value):
                with patch.dict(os.environ, {"AUTO_PRD_TEST_TIMEOUT": invalid_value}):
                    result = _timeout_from_env("AUTO_PRD_TEST_TIMEOUT", 300)
                    self.assertEqual(result, 300)

    def test_timeout_from_env_zero_returns_none(self):
        """Test that zero value returns None."""
        with patch.dict(os.environ, {"AUTO_PRD_TEST_TIMEOUT": "0"}):
            result = _timeout_from_env("AUTO_PRD_TEST_TIMEOUT", 300)
            self.assertIsNone(result)

    def test_timeout_from_env_negative_returns_none(self):
        """Test that negative value returns None."""
        with patch.dict(os.environ, {"AUTO_PRD_TEST_TIMEOUT": "-10"}):
            result = _timeout_from_env("AUTO_PRD_TEST_TIMEOUT", 300)
            self.assertIsNone(result)

    def test_get_codex_exec_timeout_default(self):
        """Test get_codex_exec_timeout with no environment variable set."""
        result = get_codex_exec_timeout()
        self.assertIsNone(result)  # Default is None for codex

    def test_get_claude_exec_timeout_default(self):
        """Test get_claude_exec_timeout with no environment variable set."""
        result = get_claude_exec_timeout()
        self.assertIsNone(result)  # Default is None for claude

    def test_get_codex_exec_timeout_from_env(self):
        """Test get_codex_exec_timeout reads from environment variable."""
        with patch.dict(os.environ, {"AUTO_PRD_CODEX_TIMEOUT_SECONDS": "600"}):
            result = get_codex_exec_timeout()
            self.assertEqual(result, 600)

    def test_get_claude_exec_timeout_from_env(self):
        """Test get_claude_exec_timeout reads from environment variable."""
        with patch.dict(os.environ, {"AUTO_PRD_CLAUDE_TIMEOUT_SECONDS": "400"}):
            result = get_claude_exec_timeout()
            self.assertEqual(result, 400)

    def test_get_codex_exec_timeout_disabled(self):
        """Test get_codex_exec_timeout with disabled value."""
        with patch.dict(os.environ, {"AUTO_PRD_CODEX_TIMEOUT_SECONDS": "disabled"}):
            result = get_codex_exec_timeout()
            self.assertIsNone(result)

    def test_get_claude_exec_timeout_disabled(self):
        """Test get_claude_exec_timeout with disabled value."""
        with patch.dict(os.environ, {"AUTO_PRD_CLAUDE_TIMEOUT_SECONDS": "off"}):
            result = get_claude_exec_timeout()
            self.assertIsNone(result)

    def test_get_codex_exec_timeout_invalid(self):
        """Test get_codex_exec_timeout with invalid value falls back to default."""
        with patch.dict(os.environ, {"AUTO_PRD_CODEX_TIMEOUT_SECONDS": "invalid"}):
            result = get_codex_exec_timeout()
            self.assertIsNone(result)  # Falls back to default (None)

    def test_get_claude_exec_timeout_invalid(self):
        """Test get_claude_exec_timeout with invalid value falls back to default."""
        with patch.dict(os.environ, {"AUTO_PRD_CLAUDE_TIMEOUT_SECONDS": "invalid"}):
            result = get_claude_exec_timeout()
            self.assertIsNone(result)  # Falls back to default (None)

    def test_timeout_functions_isolated(self):
        """Test that codex and claude timeout functions are independent."""
        with patch.dict(
            os.environ,
            {
                "AUTO_PRD_CODEX_TIMEOUT_SECONDS": "500",
                "AUTO_PRD_CLAUDE_TIMEOUT_SECONDS": "300",
            },
        ):
            codex_result = get_codex_exec_timeout()
            claude_result = get_claude_exec_timeout()

            self.assertEqual(codex_result, 500)
            self.assertEqual(claude_result, 300)

    def test_timeout_functions_runtime_evaluation(self):
        """Test that timeout functions evaluate at runtime, not import time."""
        # Initially no environment variables
        self.assertIsNone(get_codex_exec_timeout())
        self.assertIsNone(get_claude_exec_timeout())

        # Set environment variables after import
        with patch.dict(
            os.environ,
            {
                "AUTO_PRD_CODEX_TIMEOUT_SECONDS": "700",
                "AUTO_PRD_CLAUDE_TIMEOUT_SECONDS": "900",
            },
        ):
            # Functions should pick up the new values
            self.assertEqual(get_codex_exec_timeout(), 700)
            self.assertEqual(get_claude_exec_timeout(), 900)


if __name__ == "__main__":
    unittest.main()
