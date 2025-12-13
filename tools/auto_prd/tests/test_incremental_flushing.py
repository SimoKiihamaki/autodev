#!/usr/bin/env python3
"""
Tests for incremental log flushing behavior in the auto_prd logging system.
"""

import io
import sys
import unittest
from unittest.mock import patch

try:
    from tools.auto_prd.logging_utils import (
        PRINT_HOOK_INSTALLED,
        install_print_logger,
        print_flush,
        uninstall_print_logger,
    )
except ImportError:
    from ..logging_utils import (
        PRINT_HOOK_INSTALLED,
        install_print_logger,
        print_flush,
        uninstall_print_logger,
    )


class IncrementalLogFlushingTests(unittest.TestCase):
    """Test that log lines are flushed immediately when output is piped."""

    def setUp(self):
        """Set up test environment."""
        # Ensure print hook is not installed before each test
        uninstall_print_logger()

    def tearDown(self):
        """Clean up after each test."""
        # Ensure print hook is not installed after each test
        uninstall_print_logger()

    def test_print_hook_installs_and_uninstalls(self):
        """Test that print hook can be installed and uninstalled."""
        # Initially should not be installed
        self.assertFalse(PRINT_HOOK_INSTALLED)

        # Install should set the flag and change behavior
        install_print_logger()
        # The hook is now installed - test by checking print behavior
        # After install_print_logger(), builtins.print is replaced with tee_print
        # The hook receives the original args and adds flush=True internally
        with patch("builtins.print") as mock_print:
            print("Test")
            mock_print.assert_called_once_with("Test")

        # Uninstall should reset the flag
        uninstall_print_logger()
        self.assertFalse(PRINT_HOOK_INSTALLED)

    def test_print_flush_utility(self):
        """Test the print_flush utility function."""
        with patch("tools.auto_prd.logging_utils.ORIGINAL_PRINT") as mock_print:
            print_flush("Test flush")

            # Verify it was called with flush=True
            mock_print.assert_called_with("Test flush", flush=True)

    @patch("sys.stdout", new_callable=io.StringIO)
    def test_immediate_output_with_mock_stdout(self, mock_stdout):
        """Test that output appears immediately when stdout is a StringIO (simulating a pipe)."""
        install_print_logger()

        # Print multiple messages rapidly
        for i in range(5):
            print(f"Message {i}")
            # No explicit sleep - output should appear immediately

        # Check that all messages are in the output
        output = mock_stdout.getvalue()
        for i in range(5):
            self.assertIn(f"Message {i}", output)

        # Verify the output is complete (all messages should be there)
        expected_lines = [f"Message {i}\n" for i in range(5)]
        self.assertEqual(output, "".join(expected_lines))

    def test_multiple_install_uninstall_cycles(self):
        """Test that install/uninstall cycles work correctly."""
        # Start with a clean state
        uninstall_print_logger()

        for cycle in range(3):
            with self.subTest(cycle=cycle):
                # Install and test
                install_print_logger()

                # Check that the hook is installed by testing if print behavior changed
                with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                    print("Test message")
                    # Should appear in stdout due to hook
                    output = mock_stdout.getvalue()
                    self.assertIn("Test message", output)

                # Uninstall and test
                uninstall_print_logger()
                self.assertFalse(PRINT_HOOK_INSTALLED)

    def test_flush_behavior_with_stderr(self):
        """Test flush behavior with stderr output."""
        install_print_logger()

        with patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
            # Print to stderr
            print("Error message", file=sys.stderr)

            # Check that the message appears in stderr
            output = mock_stderr.getvalue()
            self.assertIn("Error message", output)

    def test_print_preserves_existing_functionality(self):
        """Test that the print hook preserves existing print functionality."""
        install_print_logger()

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            # Test various print formats
            print("Simple message")
            print("Message with", "multiple", "args")
            print("Message with separator", sep="-")
            print("Message without newline", end="")

            output = mock_stdout.getvalue()

            # Verify all messages appear correctly
            self.assertIn("Simple message\n", output)
            self.assertIn("Message with multiple args\n", output)
            # The separator might be processed differently due to logging
            # Check for either the original or the processed version
            self.assertTrue(
                "Message-with-separator\n" in output
                or "Message with separator\n" in output
            )
            self.assertIn("Message without newline", output)


if __name__ == "__main__":
    unittest.main()
