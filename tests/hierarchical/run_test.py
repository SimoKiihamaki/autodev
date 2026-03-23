#!/usr/bin/env python3
"""Run the integration tests."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Run the tests
import pytest
sys.exit(pytest.main([
    str(Path(__file__).parent / "test_hermes_delegation_integration.py"),
    "-v",
    "--tb=short",
    "-x",  # Stop on first failure
]))
