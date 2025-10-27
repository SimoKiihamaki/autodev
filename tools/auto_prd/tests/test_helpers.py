"""
Test utilities and helper functions for the auto_prd test suite.
This module consolidates common patterns used across test files to maintain DRY principles.
"""

import sys
from pathlib import Path


def safe_import(relative_module_path, fallback_module_path, item_names=None):
    """
    Safely import from relative module with fallback to absolute import.

    Args:
        relative_module_path: Module path when running as script (e.g., 'tools.auto_prd.module')
        fallback_module_path: Module path when running as module (e.g., '..module')
        item_names: List of specific items to import (None imports all)

    Returns:
        Imported module or items

    Example:
        # Import single module
        logging_utils = safe_import(
            'tools.auto_prd.logging_utils',
            '..logging_utils'
        )

        # Import specific items
        run_cmd, safe_popen = safe_import(
            'tools.auto_prd.command',
            '..command',
            ['run_cmd', 'safe_popen']
        )
    """
    try:
        if item_names:
            # Import specific items
            module = __import__(relative_module_path, fromlist=item_names)
            return tuple(getattr(module, name) for name in item_names)
        else:
            # Import entire module
            return __import__(relative_module_path)
    except ImportError:
        if item_names:
            # Import specific items from fallback
            module = __import__(fallback_module_path, fromlist=item_names)
            return tuple(getattr(module, name) for name in item_names)
        else:
            # Import entire fallback module
            return __import__(fallback_module_path)


def try_send_with_timeout(queue_func, item, timeout=0.1):
    """
    Helper function to safely send to a queue with timeout.

    Args:
        queue_func: Queue put function (e.g., queue.put)
        item: Item to put in the queue
        timeout: Timeout in seconds

    Returns:
        bool: True if item was sent successfully, False on timeout
    """
    try:
        queue_func(item, timeout=timeout)
        return True
    except Exception:
        # Handle queue full or timeout
        return False


def assert_threads_cleanly_terminated(
    threads, timeout_msg="Reader threads did not finish cleanly"
):
    """
    Assert that threads have terminated cleanly.

    Args:
        threads: List of thread objects to check
        timeout_msg: Message to use if threads are still alive

    Raises:
        AssertionError: If any threads are still alive
    """
    alive_threads = [t for t in threads if t.is_alive()]
    if alive_threads:
        alive_status = ", ".join(f"{t.name or 'unnamed'} alive" for t in alive_threads)
        assert False, f"{timeout_msg}: {alive_status}"
