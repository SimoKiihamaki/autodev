#!/usr/bin/env python3
"""Simple verification that the integration test file is syntactically correct."""

import sys
from pathlib import Path

# Verify file can be parsed
test_file = Path(__file__).parent / "test_hermes_delegation_integration.py"
with open(test_file) as f:
    code = f.read()

try:
    compile(code, 'test_hermes_delegation_integration.py', 'exec')
    print("✓ File syntax is valid")
except SyntaxError as e:
    print(f"✗ Syntax error: {e}")
    sys.exit(1)

# Try importing the basic test utilities
try:
    from dataclasses import dataclass
    from typing import List, Dict, Any, Optional
    from unittest.mock import Mock, MagicMock, AsyncMock, patch
    import asyncio
    print("✓ All test dependencies available")
except ImportError as e:
    print(f"✗ Missing dependency: {e}")
    sys.exit(1)

# Try importing from AutoDev
try:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from src.agents.base import TaskSpec, TaskResult, SubTask, AgentRole, BaseAgent
    from src.hierarchical.hierarchical_executor import HierarchicalExecutor
    print("✓ AutoDev imports available")
except ImportError as e:
    print(f"⚠ AutoDev imports not available (some tests will be skipped): {e}")

print("\n✓ Test file verification complete")
