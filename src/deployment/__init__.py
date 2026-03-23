"""
AutoDev Model Deployment Module

This module provides model deployment capabilities for trained LoRA adapters,
bridging the gap between training completion and production inference.

Components:
- CheckpointManager: Discover and validate training checkpoints
- ModelDeployer: Abstract base class for deployment strategies
- HuggingFaceDeployer: Push adapters to HuggingFace Hub
- VLLMDeployer: Deploy to vLLM inference server
- LocalInferenceDeployer: Export for local inference
- VersionRegistry: Track deployed model versions

Quick Start:
    from deployment import (
        CheckpointManager,
        HuggingFaceDeployer,
        VLLMDeployer,
        LocalInferenceDeployer,
        deploy_checkpoint,
        create_deployer,
    )
    
    # List checkpoints from a training run
    manager = CheckpointManager()
    checkpoints = manager.list_checkpoints("run_20260323_143052")
    
    # Get the best checkpoint
    best = manager.get_best_checkpoint("run_20260323_143052", metric="loss")
    
    # Deploy to different targets
    result = deploy_checkpoint(
        checkpoint_path=best.path,
        target="vllm",
        base_model="codellama/CodeLlama-7b-hf",
        port=8000
    )
    
    if result.success:
        print(f"Deployed to: {result.version.endpoint_url}")

Target: Complete deployment in <5 min for LoRA adapters
"""

# Core data structures
from .model_deployer import (
    # Dataclasses
    CheckpointInfo,
    DeploymentConfig,
    DeployedVersion,
    DeploymentResult,
    RollbackResult,
    
    # Enums
    DeploymentTarget,
    DeploymentStatus,
    RollbackReason,
    
    # Checkpoint management
    CheckpointManager,
    
    # Deployer classes
    ModelDeployer,
    HuggingFaceDeployer,
    VLLMDeployer,
    LocalInferenceDeployer,
    
    # Version tracking
    VersionRegistry,
    
    # Factory functions
    create_deployer,
    deploy_checkpoint,
    
    # CLI support (optional import)
    get_cli_parser,
)

__all__ = [
    # Data structures
    "CheckpointInfo",
    "DeploymentConfig",
    "DeployedVersion",
    "DeploymentResult",
    "RollbackResult",
    
    # Enums
    "DeploymentTarget",
    "DeploymentStatus",
    "RollbackReason",
    
    # Classes
    "CheckpointManager",
    "ModelDeployer",
    "HuggingFaceDeployer",
    "VLLMDeployer",
    "LocalInferenceDeployer",
    "VersionRegistry",
    
    # Functions
    "create_deployer",
    "deploy_checkpoint",
    "get_cli_parser",
]

__version__ = "1.0.0"
