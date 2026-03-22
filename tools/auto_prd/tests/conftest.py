"""
Pytest configuration for auto_prd test suite.

This conftest.py file configures pytest to properly handle imports and
test environment setup for the auto_prd package.
"""

import os
import sys
from pathlib import Path

import pytest

# Configure Python path BEFORE any tests are imported
# This must be done at module load time, not in pytest_configure
_tools_dir = Path(__file__).parent.parent
_project_root = _tools_dir.parent

# Only add tools_dir for 'auto_prd' imports
# NOTE: We intentionally do NOT add _project_root to sys.path because having
# both paths causes Python to create two separate module objects for the same
# code (one as 'tools.auto_prd.X' and one as 'auto_prd.X'), which breaks mocking.
# All patches should use 'auto_prd.X' paths.
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

# Set the safety bypass flag globally for the test session
# This allows tests to execute commands without triggering safety checks
# Safety-specific tests will temporarily unset this as needed
os.environ["AUTO_PRD_ALLOW_UNSAFE_EXECUTION"] = "1"


def pytest_configure(config):
    """
    Configure pytest to handle our custom test structure.

    This ensures that the 'tools' package can be imported correctly,
    which is required for the safe_import helper function to work.
    """
    # Disable pytest's assertion rewriting for modules with dots in names
    # that aren't actual package paths (like 'tools.auto_prd')
    config.option.pythonpath = [str(_project_root)]
