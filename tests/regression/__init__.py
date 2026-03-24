"""
Performance Regression Tests

This package contains performance regression tests for the AutoDev hierarchical executor.
"""

# Mark all tests in this directory as regression tests
import pytest

def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line(
        "markers", "regression: mark test as a performance regression test"
    )
