#!/usr/bin/env python
"""Test imports for Phase 10 hierarchical module."""
import sys
import os

print('Python:', sys.executable)

# Add current directory to path (so 'src' package can be found)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
print('Path:', sys.path[:3])

# Test imports from src package (proper way)
try:
    from src.agents.base import BaseAgent, AgentRole
    print('✅ src.agents.base imports work')
except Exception as e:
    print(f'❌ src.agents.base: {e}')

try:
    from src.training.reward_calculator import RewardCalculator
    print('✅ src.training.reward_calculator imports work')
except Exception as e:
    print(f'❌ src.training.reward_calculator: {e}')

# Test hierarchical module imports
try:
    from src.hierarchical.agent_training_bridge import AgentTrainingBridge, BridgeConfig
    print('✅ src.hierarchical.agent_training_bridge imports work')
    print(f'   BridgeConfig: {BridgeConfig}')
except Exception as e:
    print(f'❌ src.hierarchical.agent_training_bridge: {e}')

try:
    from src.hierarchical.hierarchical_executor import HierarchicalExecutor
    print('✅ src.hierarchical.hierarchical_executor imports work')
except Exception as e:
    print(f'❌ src.hierarchical.hierarchical_executor: {e}')

try:
    from src.hierarchical.agent_pipeline import AgentPipeline
    print('✅ src.hierarchical.agent_pipeline imports work')
except Exception as e:
    print(f'❌ src.hierarchical.agent_pipeline: {e}')
