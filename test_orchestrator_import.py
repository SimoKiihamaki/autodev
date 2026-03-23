#!/usr/bin/env python3
"""Test script to verify orchestrator module imports."""
import sys
sys.path.insert(0, '/Users/simo/Projects/autodev')

from src.training.orchestrator import (
    TrainingOrchestrator,
    OrchestratorConfig,
    OrchestratorStage,
    ProgressInfo,
    CheckpointState,
    TrainingCycleResult,
    ShutdownReason,
    create_orchestrator,
    run_training,
)

print('All imports successful!')
print(f'TrainingOrchestrator: {TrainingOrchestrator}')
print(f'OrchestratorConfig: {OrchestratorConfig}')
print(f'OrchestratorStage values: {[s.value for s in OrchestratorStage]}')

# Test instantiation
config = OrchestratorConfig()
print(f'Default config checkpoint_dir: {config.checkpoint_dir}')
print(f'Default config model_output_dir: {config.model_output_dir}')
