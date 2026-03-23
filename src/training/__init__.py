"""
AutoDev Phase 8: RL Training Integration with GRPO Pipeline

This module provides reinforcement learning training components for improving
AutoDev's code generation capabilities using Group Relative Policy Optimization (GRPO).

Components:
- TrainingDataCollector: Execution trace collection from SWE-bench runs
- RewardCalculator: Multi-component reward computation
- AutoDevGRPOTrainer: TRL GRPO trainer integration
- ModelRegistry: Model version management
- TrainingPipeline: Training orchestration

Target: 25%+ SWE-bench resolution rate (5% improvement over Phase 7)
"""

# Import available modules using relative imports for better compatibility
from .data_collector import (
    ExecutionTrace,
    TraceStep,
    CodeChange,
    TraceStatus,
    TrainingDataCollector,
    DataCollectionConfig,
    create_collector,
)

# Placeholder imports for modules not yet implemented
# These will be replaced when the corresponding modules are created
try:
    from .reward_calculator import (
        RewardCalculator,
        RewardComponents,
    )
except ImportError:
    RewardCalculator = None
    RewardComponents = None

try:
    from .grpo_trainer import (
        AutoDevGRPOTrainer,
        GRPOConfig,
        GRPODataset,
        TrainingMetrics,
        CheckpointInfo,
        TrainingStage,
        OptimizerType,
        SchedulerType,
        create_trainer,
        train_model,
        load_trainer,
    )
except ImportError:
    AutoDevGRPOTrainer = None
    GRPOConfig = None
    GRPODataset = None
    TrainingMetrics = None
    CheckpointInfo = None
    TrainingStage = None
    OptimizerType = None
    SchedulerType = None
    create_trainer = None
    train_model = None
    load_trainer = None

try:
    from .model_registry import (
        ModelRegistry,
        ModelVersion,
    )
except ImportError:
    ModelRegistry = None
    ModelVersion = None

try:
    from .pipeline import (
        TrainingPipeline,
        TrainingConfig,
    )
except ImportError:
    TrainingPipeline = None
    TrainingConfig = None

__all__ = [
    # Data collection
    "ExecutionTrace",
    "TraceStep",
    "CodeChange",
    "TraceStatus",
    "TrainingDataCollector",
    "DataCollectionConfig",
    "create_collector",
    # Reward calculation
    "RewardCalculator",
    "RewardComponents",
    # GRPO training
    "AutoDevGRPOTrainer",
    "GRPOConfig",
    "GRPODataset",
    "TrainingMetrics",
    "CheckpointInfo",
    "TrainingStage",
    "OptimizerType",
    "SchedulerType",
    "create_trainer",
    "train_model",
    "load_trainer",
    # Model management
    "ModelRegistry",
    "ModelVersion",
    # Pipeline
    "TrainingPipeline",
    "TrainingConfig",
]

__version__ = "8.0.0"
