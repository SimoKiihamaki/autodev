"""Pytest configuration for tools/tests.

When tests run from the tools/ directory, we need to ensure the parent
directory is on sys.path so that auto_prd is importable.
"""

import sys
from pathlib import Path

# Add tools/ to sys.path so auto_prd is importable when running pytest from tools/
_tools_dir = Path(__file__).parent.parent
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))
