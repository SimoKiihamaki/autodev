#!/usr/bin/env python3
"""Quick test to see what's crashing."""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

print("Step 1: Import data_collector...")
try:
    from training.data_collector import ExecutionTrace, TraceStatus
    print("  OK")
except Exception as e:
    print(f"  FAILED: {e}")
    sys.exit(1)

print("Step 2: Import reward_calculator...")
try:
    from training.reward_calculator import RewardCalculator, RewardComponents
    print("  OK")
except Exception as e:
    print(f"  FAILED: {e}")
    sys.exit(1)

print("Step 3: Import model_registry...")
try:
    from training.model_registry import ModelRegistry, ModelVersion, ModelStatus
    print("  OK")
except Exception as e:
    print(f"  FAILED: {e}")
    sys.exit(1)

print("Step 4: Import grpo_trainer (may trigger torch import)...")
try:
    from training.grpo_trainer import GRPOConfig, TrainingMetrics
    print("  OK")
except Exception as e:
    print(f"  FAILED: {e}")
    sys.exit(1)

print("\nAll imports successful!")
