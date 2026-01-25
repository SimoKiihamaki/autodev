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

# Add project root to allow 'tools.auto_prd' imports
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Also add tools_dir to allow 'auto_prd' imports (alternative import style)
# This supports both import styles used across the codebase
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))


@pytest.fixture(autouse=True)
def allow_unsafe_execution():
    """
    Allow command execution in tests by setting the safety flag.

    This fixture runs automatically for all tests to ensure that
    command execution is allowed during testing. Without this flag,
    the command safety checks would prevent tests from running.

    The flag is restored to its original value after each test.
    """
    original_value = os.environ.get("AUTO_PRD_ALLOW_UNSAFE_EXECUTION")
    os.environ["AUTO_PRD_ALLOW_UNSAFE_EXECUTION"] = "1"
    yield
    # Restore original value after test
    if original_value is None:
        os.environ.pop("AUTO_PRD_ALLOW_UNSAFE_EXECUTION", None)
    else:
        os.environ["AUTO_PRD_ALLOW_UNSAFE_EXECUTION"] = original_value


def pytest_configure(config):
    """
    Configure pytest to handle our custom test structure.

    This ensures that the 'tools' package can be imported correctly,
    which is required for the safe_import helper function to work.
    """
    # Disable pytest's assertion rewriting for modules with dots in names
    # that aren't actual package paths (like 'tools.auto_prd')
    config.option.pythonpath = [str(_project_root)]
