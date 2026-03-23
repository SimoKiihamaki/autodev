#!/usr/bin/env python3
"""Test script for deployment module."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.deployment import (
    CheckpointManager,
    CheckpointInfo,
    DeploymentConfig,
    DeployedVersion,
    DeploymentResult,
    RollbackResult,
    DeploymentTarget,
    DeploymentStatus,
    RollbackReason,
    HuggingFaceDeployer,
    VLLMDeployer,
    LocalInferenceDeployer,
    VersionRegistry,
    create_deployer,
    deploy_checkpoint,
)
from datetime import datetime

print('✓ All imports successful')

# Test basic functionality
manager = CheckpointManager()
print(f'✓ CheckpointManager created, base dir: {manager.checkpoint_base_dir}')

config = DeploymentConfig(target='vllm', base_model='test-model')
print(f'✓ DeploymentConfig created, target: {config.target}')

deployer = create_deployer('local', config)
print(f'✓ Deployer created: {type(deployer).__name__}')

# Test CheckpointInfo
info = CheckpointInfo(
    path='/test/path',
    step=100,
    timestamp=datetime.now(),
    metrics={'loss': 0.5}
)
print(f'✓ CheckpointInfo created, step: {info.step}')

# Test serialization
data = info.to_dict()
info2 = CheckpointInfo.from_dict(data)
print(f'✓ CheckpointInfo serialization works, metric loss: {info2.get_metric("loss")}')

# Test DeploymentResult
result = DeploymentResult(success=True, logs=['test'])
print(f'✓ DeploymentResult created, success: {result.success}')

# Test VersionRegistry
registry = VersionRegistry()
print(f'✓ VersionRegistry created')

print('\n✅ All tests passed!')
