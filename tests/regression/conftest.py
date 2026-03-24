"""
Pytest configuration for regression tests.
"""

import pytest


def pytest_configure(config):
    """Configure custom markers for regression tests."""
    config.addinivalue_line(
        "markers", "regression: mark test as a performance regression test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )


def pytest_collection_modifyitems(config, items):
    """Add markers to regression tests."""
    for item in items:
        if "regression" in item.nodeid:
            item.add_marker(pytest.mark.regression)
