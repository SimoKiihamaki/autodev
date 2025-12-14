"""Tests for constants.py module."""

import unittest

from .test_helpers import safe_import

# Import the constants module and functions we need to test
get_tool_allowlist = safe_import(
    "tools.auto_prd.constants", "..constants", "get_tool_allowlist"
)
HEADLESS_TOOL_ALLOWLISTS = safe_import(
    "tools.auto_prd.constants", "..constants", "HEADLESS_TOOL_ALLOWLISTS"
)


class GetToolAllowlistTests(unittest.TestCase):
    """Test suite for get_tool_allowlist function."""

    def test_implement_phase_returns_correct_tools(self):
        """Test get_tool_allowlist returns correct tools for 'implement' phase."""
        tools = get_tool_allowlist("implement")
        self.assertIsInstance(tools, list)
        self.assertIn("Read", tools)
        self.assertIn("Edit", tools)
        self.assertIn("Write", tools)
        self.assertIn("Glob", tools)
        self.assertIn("Grep", tools)
        # Should have bash with build commands
        bash_tool = [t for t in tools if t.startswith("Bash(")]
        self.assertEqual(len(bash_tool), 1)
        self.assertIn("git:", bash_tool[0])
        self.assertIn("make:", bash_tool[0])

    def test_fix_phase_returns_correct_tools(self):
        """Test get_tool_allowlist returns correct tools for 'fix' phase."""
        tools = get_tool_allowlist("fix")
        self.assertIsInstance(tools, list)
        self.assertIn("Read", tools)
        self.assertIn("Edit", tools)
        # Fix phase should NOT have Write (limited to editing existing files)
        self.assertNotIn("Write", tools)
        self.assertNotIn("Glob", tools)
        self.assertNotIn("Grep", tools)

    def test_pr_phase_returns_correct_tools(self):
        """Test get_tool_allowlist returns correct tools for 'pr' phase."""
        tools = get_tool_allowlist("pr")
        self.assertIsInstance(tools, list)
        self.assertIn("Read", tools)
        # PR phase should be git + gh only
        bash_tool = [t for t in tools if t.startswith("Bash(")]
        self.assertEqual(len(bash_tool), 1)
        self.assertIn("git:", bash_tool[0])
        self.assertIn("gh:", bash_tool[0])
        # Should NOT have edit/write capabilities
        self.assertNotIn("Edit", tools)
        self.assertNotIn("Write", tools)

    def test_review_fix_phase_returns_correct_tools(self):
        """Test get_tool_allowlist returns correct tools for 'review_fix' phase."""
        tools = get_tool_allowlist("review_fix")
        self.assertIsInstance(tools, list)
        self.assertIn("Read", tools)
        self.assertIn("Edit", tools)
        self.assertIn("Write", tools)
        # Should have bash with git/gh for PR updates
        bash_tool = [t for t in tools if t.startswith("Bash(")]
        self.assertEqual(len(bash_tool), 1)
        self.assertIn("git:", bash_tool[0])
        self.assertIn("gh:", bash_tool[0])

    def test_invalid_phase_raises_value_error(self):
        """Test get_tool_allowlist raises ValueError for invalid phase names."""
        with self.assertRaises(ValueError) as ctx:
            get_tool_allowlist("invalid_phase")
        error_msg = str(ctx.exception)
        self.assertIn("Invalid phase 'invalid_phase'", error_msg)
        # Error message should include list of valid phases
        self.assertIn("valid phases are:", error_msg)

    def test_invalid_phase_error_includes_valid_phases_list(self):
        """Test that the error message includes all valid phase names."""
        with self.assertRaises(ValueError) as ctx:
            get_tool_allowlist("nonexistent")
        error_msg = str(ctx.exception)
        # Check that valid phases are mentioned in the error
        self.assertIn("implement", error_msg)
        self.assertIn("fix", error_msg)
        self.assertIn("pr", error_msg)
        self.assertIn("review_fix", error_msg)

    def test_cli_phase_local_raises_value_error(self):
        """Test that 'local' (CLI phase name) raises ValueError - must use 'implement'."""
        # 'local' is the CLI phase name, but internal tool allowlist uses 'implement'
        with self.assertRaises(ValueError) as ctx:
            get_tool_allowlist("local")
        self.assertIn("Invalid phase 'local'", str(ctx.exception))

    def test_returns_new_list_each_call(self):
        """Test get_tool_allowlist returns a new list (not reference to internal state)."""
        tools1 = get_tool_allowlist("implement")
        tools2 = get_tool_allowlist("implement")
        # Should be equal but not the same object
        self.assertEqual(tools1, tools2)
        self.assertIsNot(tools1, tools2)
        # Modifying returned list should not affect subsequent calls
        tools1.append("Malicious")
        tools3 = get_tool_allowlist("implement")
        self.assertNotIn("Malicious", tools3)

    def test_all_defined_phases_are_valid(self):
        """Test that all phases in HEADLESS_TOOL_ALLOWLISTS are accessible."""
        for phase in HEADLESS_TOOL_ALLOWLISTS:
            tools = get_tool_allowlist(phase)
            self.assertIsInstance(tools, list)
            self.assertGreater(len(tools), 0, f"Phase {phase} has no tools")

    def test_empty_string_phase_raises_value_error(self):
        """Test that empty string raises ValueError."""
        with self.assertRaises(ValueError):
            get_tool_allowlist("")

    def test_whitespace_phase_raises_value_error(self):
        """Test that whitespace-only string raises ValueError."""
        with self.assertRaises(ValueError):
            get_tool_allowlist("   ")

    def test_case_sensitive_phase_names(self):
        """Test that phase names are case-sensitive."""
        # Uppercase should fail
        with self.assertRaises(ValueError):
            get_tool_allowlist("IMPLEMENT")

        with self.assertRaises(ValueError):
            get_tool_allowlist("Implement")


if __name__ == "__main__":
    unittest.main()
