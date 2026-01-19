"""
Pytest configuration for auto_prd test suite.

This conftest.py file configures pytest to properly handle imports and
test environment setup for the auto_prd package.
"""

import sys
from pathlib import Path


# Configure Python path BEFORE any tests are imported
# This must be done at module load time, not in pytest_configure
_tools_dir = Path(__file__).parent.parent
_project_root = _tools_dir.parent

# Add project root to allow 'tools.auto_prd' imports
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


def pytest_configure(config):
    """
    Configure pytest to handle our custom test structure.

    This ensures that the 'tools' package can be imported correctly,
    which is required for the safe_import helper function to work.
    """
    # Disable pytest's assertion rewriting for modules with dots in names
    # that aren't actual package paths (like 'tools.auto_prd')
    config.option.pythonpath = [str(_project_root)]
