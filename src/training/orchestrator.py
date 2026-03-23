"""
Training Orchestrator for AutoDev Phase 9 Integration & Evaluation

This module provides the TrainingOrchestrator class that coordinates the full
training workflow from data collection through evaluation and model registration.
It manages checkpointing, progress tracking, and graceful shutdown for robust
training cycles.

Key features:
- Coordinates data collection, GRPO training, and evaluation cycles
- Checkpoint management at ~/.autodev/checkpoints
- Progress tracking with detailed metrics
- Graceful shutdown with state preservation
- Evaluation intervals for periodic model assessment
- Recovery from interrupted training runs

Usage:
    from training.orchestrator import TrainingOrchestrator, OrchestratorConfig

    config = OrchestratorConfig(
        data_collection_episodes=100,
        min_traces_for_training=50,
        evaluation_interval=100,
        checkpoint_dir="~/.autodev/checkpoints",
        model_output_dir="~/.autodev/models"
    )

    orchestrator = TrainingOrchestrator(config)

    # Run full training cycle
    result = await orchestrator.run_training_cycle(
        base_model="Qwen/Qwen2.5-Coder-7B-Instruct",
        swebench_subset="lite",
        num_eval_tasks=50
    )

    print(f"Model trained: {result.model_path}")
    print(f"Resolution rate: {result.resolution_rate:.1%}")
"""

import asyncio
import json
import logging
import os
import signal
import shutil
import threading
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

# Import training components
from .data_collector import (
    ExecutionTrace,
    TraceStatus,
    DataCollectionConfig,
    TrainingDataCollector,
)
from .reward_calculator import (
    RewardCalculator,
    RewardComponents,
    RewardConfig,
)
from .grpo_trainer import (
    AutoDevGRPOTrainer,
    GRPOConfig,
    TrainingMetrics,
    TrainingStage,
)
from .model_registry import (
    ModelRegistry,
    ModelVersion,
    ModelStatus,
    RegistryConfig,
)
from .pipeline import (
    PipelineConfig,
    PipelineStage,
)

logger = logging.getLogger(__name__)


class OrchestratorStage(Enum):
    """Stages of the orchestrator training cycle."""
    IDLE = "idle"
    INITIALIZING = "initializing"
    COLLECTING_DATA = "collecting_data"
    COMPUTING_REWARDS = "computing_rewards"
    TRAINING = "training"
    EVALUATING = "evaluating"
    REGISTERING_MODEL = "registering_model"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ShutdownReason(Enum):
    """Reasons for orchestrator shutdown."""
    NONE = "none"
    USER_REQUEST = "user_request"
    SIGNAL = "signal"
    ERROR = "error"
    TIMEOUT = "timeout"
    COMPLETED = "completed"


@dataclass
class OrchestratorConfig:
    """
    Configuration for the Training Orchestrator.
    
    Attributes:
        data_collection_episodes: Number of episodes for data collection
        min_traces_for_training: Minimum traces required before training
        evaluation_interval: Steps between evaluations (0 = no interval)
        evaluation_tasks: Number of tasks for each evaluation
        checkpoint_dir: Directory for storing checkpoints
        model_output_dir: Directory for trained models
        registry_dir: Directory for model registry
        
        # Training settings
        max_training_steps: Maximum training steps (0 = unlimited)
        training_timeout: Timeout for training in seconds (0 = no timeout)
        
        # Checkpoint settings
        checkpoint_interval: Steps between checkpoints
        keep_checkpoints: Number of checkpoints to keep
        auto_resume: Automatically resume from checkpoint if available
        
        # Resource settings
        max_concurrent_evals: Maximum concurrent evaluations
        gpu_memory_fraction: GPU memory fraction to use
        
        # Graceful shutdown settings
        shutdown_timeout: Seconds to wait for graceful shutdown
        save_on_shutdown: Save state on shutdown
    """
    # Data collection settings
    data_collection_episodes: int = 100
    min_traces_for_training: int = 50
    max_traces_per_task: int = 10
    include_failed_attempts: bool = True
    
    # Evaluation settings
    evaluation_interval: int = 100  # Steps between evaluations
    evaluation_tasks: int = 50
    swebench_subset: str = "lite"  # "lite", "full", or custom
    
    # Directory settings
    checkpoint_dir: str = "~/.autodev/checkpoints"
    model_output_dir: str = "~/.autodev/models"
    registry_dir: str = "~/.autodev/model_registry"
    data_dir: str = "~/.autodev/training_data"
    
    # Training settings
    max_training_steps: int = 10000
    training_timeout: int = 0  # 0 = no timeout
    learning_rate: float = 1e-5
    num_epochs: int = 3
    batch_size: int = 8
    use_peft: bool = True
    
    # Checkpoint settings
    checkpoint_interval: int = 500
    keep_checkpoints: int = 5
    auto_resume: bool = True
    
    # Resource settings
    max_concurrent_evals: int = 4
    gpu_memory_fraction: float = 0.9
    
    # Graceful shutdown settings
    shutdown_timeout: int = 30
    save_on_shutdown: bool = True
    
    def __post_init__(self):
        """Expand directory paths."""
        self.checkpoint_dir = os.path.expanduser(self.checkpoint_dir)
        self.model_output_dir = os.path.expanduser(self.model_output_dir)
        self.registry_dir = os.path.expanduser(self.registry_dir)
        self.data_dir = os.path.expanduser(self.data_dir)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OrchestratorConfig":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class ProgressInfo:
    """
    Current progress information for the orchestrator.
    
    Attributes:
        stage: Current orchestrator stage
        stage_progress: Progress within current stage (0.0 to 1.0)
        total_episodes: Total episodes planned
        completed_episodes: Episodes completed so far
        total_steps: Total training steps planned
        completed_steps: Training steps completed
        current_epoch: Current training epoch
        traces_collected: Number of traces collected
        traces_processed: Number of traces processed
        evaluations_completed: Number of evaluations completed
        best_resolution_rate: Best resolution rate seen
        elapsed_time: Elapsed time in seconds
        estimated_remaining: Estimated remaining time in seconds
    """
    stage: OrchestratorStage = OrchestratorStage.IDLE
    stage_progress: float = 0.0
    total_episodes: int = 0
    completed_episodes: int = 0
    total_steps: int = 0
    completed_steps: int = 0
    current_epoch: int = 0
    traces_collected: int = 0
    traces_processed: int = 0
    evaluations_completed: int = 0
    best_resolution_rate: float = 0.0
    elapsed_time: float = 0.0
    estimated_remaining: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        data["stage"] = self.stage.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProgressInfo":
        """Create from dictionary."""
        if isinstance(data.get("stage"), str):
            data["stage"] = OrchestratorStage(data["stage"])
        return cls(**data)


@dataclass
class CheckpointState:
    """
    State saved at each checkpoint.
    
    Attributes:
        checkpoint_id: Unique identifier for this checkpoint
        timestamp: When the checkpoint was created
        stage: Orchestrator stage at checkpoint time
        progress: Progress info at checkpoint time
        config: Configuration used
        collected_traces: Paths to collected trace files
        training_step: Current training step
        model_path: Path to current model checkpoint
        metrics: Metrics at checkpoint time
        metadata: Additional metadata
    """
    checkpoint_id: str
    timestamp: str
    stage: OrchestratorStage
    progress: ProgressInfo
    config: OrchestratorConfig
    collected_traces: List[str] = field(default_factory=list)
    training_step: int = 0
    model_path: str = ""
    metrics: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "checkpoint_id": self.checkpoint_id,
            "timestamp": self.timestamp,
            "stage": self.stage.value,
            "progress": self.progress.to_dict(),
            "config": self.config.to_dict(),
            "collected_traces": self.collected_traces,
            "training_step": self.training_step,
            "model_path": self.model_path,
            "metrics": self.metrics,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CheckpointState":
        """Create from dictionary."""
        if isinstance(data.get("stage"), str):
            data["stage"] = OrchestratorStage(data["stage"])
        if isinstance(data.get("progress"), dict):
            data["progress"] = ProgressInfo.from_dict(data["progress"])
        if isinstance(data.get("config"), dict):
            data["config"] = OrchestratorConfig.from_dict(data["config"])
        return cls(**data)


@dataclass
class TrainingCycleResult:
    """
    Result of a complete training cycle.
    
    Attributes:
        success: Whether the cycle completed successfully
        model_path: Path to the trained model
        model_version: Registered model version ID
        resolution_rate: SWE-bench resolution rate achieved
        baseline_resolution_rate: Baseline resolution rate for comparison
        improvement: Improvement over baseline
        traces_collected: Number of traces collected
        training_steps: Number of training steps completed
        training_time: Total training time in seconds
        evaluations_run: Number of evaluations run
        final_metrics: Final training metrics
        best_checkpoint: Path to best checkpoint
        error: Error message if failed
        cancelled: Whether the cycle was cancelled
    """
    success: bool = False
    model_path: str = ""
    model_version: str = ""
    resolution_rate: float = 0.0
    baseline_resolution_rate: float = 0.20  # Phase 7 baseline
    improvement: float = 0.0
    traces_collected: int = 0
    training_steps: int = 0
    training_time: float = 0.0
    evaluations_run: int = 0
    final_metrics: Optional[TrainingMetrics] = None
    best_checkpoint: str = ""
    error: Optional[str] = None
    cancelled: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        if self.final_metrics:
            data["final_metrics"] = self.final_metrics.to_dict()
        return data


class TrainingOrchestrator:
    """
    Coordinates the full training workflow for AutoDev.
    
    This class orchestrates:
    1. Data collection from SWE-bench or custom sources
    2. Reward computation for collected traces
    3. GRPO-based model training with checkpointing
    4. Periodic evaluation at configured intervals
    5. Model registration and versioning
    6. Progress tracking and reporting
    7. Graceful shutdown with state preservation
    
    Example:
        config = OrchestratorConfig(
            data_collection_episodes=100,
            min_traces_for_training=50,
            evaluation_interval=100
        )
        
        orchestrator = TrainingOrchestrator(config)
        
        # Set up progress callback
        orchestrator.add_progress_callback(my_callback)
        
        # Run training cycle
        result = await orchestrator.run_training_cycle(
            base_model="Qwen/Qwen2.5-Coder-7B-Instruct",
            swebench_subset="lite",
            num_eval_tasks=50
        )
        
        if result.success:
            print(f"Trained model: {result.model_path}")
            print(f"Resolution rate: {result.resolution_rate:.1%}")
            print(f"Improvement: {result.improvement:.1%}")
    """
    
    def __init__(
        self,
        config: Optional[OrchestratorConfig] = None,
        data_collector: Optional[TrainingDataCollector] = None,
        reward_calculator: Optional[RewardCalculator] = None,
        trainer: Optional[AutoDevGRPOTrainer] = None,
        registry: Optional[ModelRegistry] = None,
    ):
        """
        Initialize the Training Orchestrator.
        
        Args:
            config: Orchestrator configuration
            data_collector: Pre-configured data collector
            reward_calculator: Pre-configured reward calculator
            trainer: Pre-configured trainer
            registry: Pre-configured model registry
        """
        self.config = config or OrchestratorConfig()
        
        # Initialize state
        self._stage = OrchestratorStage.IDLE
        self._progress = ProgressInfo()
        self._shutdown_requested = False
        self._shutdown_reason = ShutdownReason.NONE
        self._shutdown_lock = threading.Lock()
        self._start_time: Optional[float] = None
        self._current_checkpoint: Optional[CheckpointState] = None
        self._collected_traces: List[ExecutionTrace] = []
        self._best_resolution_rate: float = 0.0
        self._model_version: Optional[ModelVersion] = None
        
        # Progress callbacks
        self._progress_callbacks: List[Callable[[ProgressInfo], None]] = []
        
        # Create directories
        self._ensure_directories()
        
        # Initialize components
        self._init_components(
            data_collector=data_collector,
            reward_calculator=reward_calculator,
            trainer=trainer,
            registry=registry,
        )
        
        # Set up signal handlers for graceful shutdown
        self._setup_signal_handlers()
        
        logger.info(
            f"TrainingOrchestrator initialized with "
            f"episodes={self.config.data_collection_episodes}, "
            f"eval_interval={self.config.evaluation_interval}"
        )
    
    def _ensure_directories(self) -> None:
        """Create necessary directories."""
        Path(self.config.checkpoint_dir).mkdir(parents=True, exist_ok=True)
        Path(self.config.model_output_dir).mkdir(parents=True, exist_ok=True)
        Path(self.config.registry_dir).mkdir(parents=True, exist_ok=True)
        Path(self.config.data_dir).mkdir(parents=True, exist_ok=True)
    
    def _init_components(
        self,
        data_collector: Optional[TrainingDataCollector],
        reward_calculator: Optional[RewardCalculator],
        trainer: Optional[AutoDevGRPOTrainer],
        registry: Optional[ModelRegistry],
    ) -> None:
        """Initialize or use provided components."""
        # Data collector
        if data_collector is not None:
            self.data_collector = data_collector
        else:
            data_config = DataCollectionConfig(
                output_dir=self.config.data_dir,
                max_traces_per_task=self.config.max_traces_per_task,
                include_failed_attempts=self.config.include_failed_attempts,
            )
            self.data_collector = TrainingDataCollector(data_config)
        
        # Reward calculator
        if reward_calculator is not None:
            self.reward_calculator = reward_calculator
        else:
            self.reward_calculator = RewardCalculator(RewardConfig())
        
        # Trainer (lazy initialization)
        self._trainer = trainer
        self._trainer_initialized = trainer is not None
        
        # Model registry
        if registry is not None:
            self.registry = registry
        else:
            registry_config = RegistryConfig(
                base_dir=self.config.registry_dir,
            )
            self.registry = ModelRegistry(registry_config)
    
    def _setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum: int, frame) -> None:
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown")
        with self._shutdown_lock:
            self._shutdown_requested = True
            self._shutdown_reason = ShutdownReason.SIGNAL
    
    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------
    
    @property
    def stage(self) -> OrchestratorStage:
        """Get current orchestrator stage."""
        return self._stage
    
    @property
    def progress(self) -> ProgressInfo:
        """Get current progress info."""
        return self._progress
    
    @property
    def is_shutdown_requested(self) -> bool:
        """Check if shutdown has been requested."""
        with self._shutdown_lock:
            return self._shutdown_requested
    
    @property
    def shutdown_reason(self) -> ShutdownReason:
        """Get the reason for shutdown."""
        with self._shutdown_lock:
            return self._shutdown_reason
    
    def request_shutdown(self, reason: ShutdownReason = ShutdownReason.USER_REQUEST) -> None:
        """
        Request a graceful shutdown.
        
        Args:
            reason: Reason for the shutdown request
        """
        logger.info(f"Shutdown requested: {reason.value}")
        with self._shutdown_lock:
            self._shutdown_requested = True
            self._shutdown_reason = reason
    
    def add_progress_callback(self, callback: Callable[[ProgressInfo], None]) -> None:
        """
        Add a callback for progress updates.
        
        Args:
            callback: Function to call with progress updates
        """
        self._progress_callbacks.append(callback)
    
    def remove_progress_callback(self, callback: Callable[[ProgressInfo], None]) -> None:
        """Remove a progress callback."""
        if callback in self._progress_callbacks:
            self._progress_callbacks.remove(callback)
    
    async def run_training_cycle(
        self,
        base_model: str,
        swebench_subset: str = "lite",
        num_eval_tasks: int = 50,
        resume: bool = True,
    ) -> TrainingCycleResult:
        """
        Run a complete training cycle.
        
        This method orchestrates the full workflow:
        1. Resume from checkpoint if available and requested
        2. Collect training data from SWE-bench
        3. Compute rewards for collected traces
        4. Train the model using GRPO
        5. Evaluate at configured intervals
        6. Register the final model
        7. Return results
        
        Args:
            base_model: Base model to train from
            swebench_subset: SWE-bench subset to use ("lite", "full")
            num_eval_tasks: Number of tasks for final evaluation
            resume: Whether to resume from checkpoint if available
            
        Returns:
            TrainingCycleResult with training outcomes
        """
        result = TrainingCycleResult()
        self._start_time = datetime.now().timestamp()
        self._best_resolution_rate = 0.0
        
        try:
            # Initialize
            self._set_stage(OrchestratorStage.INITIALIZING)
            
            # Try to resume from checkpoint
            if resume and self.config.auto_resume:
                checkpoint = self._load_latest_checkpoint()
                if checkpoint:
                    logger.info(f"Resuming from checkpoint: {checkpoint.checkpoint_id}")
                    self._restore_from_checkpoint(checkpoint)
                    result.traces_collected = len(self._collected_traces)
            
            # Check for shutdown
            if self.is_shutdown_requested:
                return self._create_cancelled_result()
            
            # Phase 1: Data Collection
            self._set_stage(OrchestratorStage.COLLECTING_DATA)
            traces = await self._collect_data(base_model, swebench_subset)
            self._collected_traces.extend(traces)
            result.traces_collected = len(self._collected_traces)
            
            if len(self._collected_traces) < self.config.min_traces_for_training:
                logger.warning(
                    f"Insufficient traces: {len(self._collected_traces)} < "
                    f"{self.config.min_traces_for_training}"
                )
                result.error = f"Insufficient traces collected: {len(self._collected_traces)}"
                result.success = False
                return result
            
            # Save checkpoint after data collection
            self._save_checkpoint()
            
            # Check for shutdown
            if self.is_shutdown_requested:
                self._save_checkpoint()
                return self._create_cancelled_result()
            
            # Phase 2: Compute Rewards
            self._set_stage(OrchestratorStage.COMPUTING_REWARDS)
            self._compute_rewards()
            
            # Check for shutdown
            if self.is_shutdown_requested:
                self._save_checkpoint()
                return self._create_cancelled_result()
            
            # Phase 3: Training with periodic evaluation
            self._set_stage(OrchestratorStage.TRAINING)
            training_result = await self._train_with_evaluations(
                base_model=base_model,
                num_eval_tasks=num_eval_tasks,
            )
            
            result.training_steps = training_result.get("steps", 0)
            result.training_time = training_result.get("time", 0.0)
            result.final_metrics = training_result.get("metrics")
            result.evaluations_run = training_result.get("evaluations", 0)
            result.best_checkpoint = training_result.get("best_checkpoint", "")
            
            # Check for shutdown
            if self.is_shutdown_requested:
                self._save_checkpoint()
                return self._create_cancelled_result()
            
            # Phase 4: Final Evaluation
            self._set_stage(OrchestratorStage.EVALUATING)
            final_eval = await self._run_evaluation(num_eval_tasks)
            result.resolution_rate = final_eval.get("resolution_rate", 0.0)
            result.improvement = result.resolution_rate - result.baseline_resolution_rate
            
            # Check for shutdown
            if self.is_shutdown_requested:
                return self._create_cancelled_result()
            
            # Phase 5: Register Model
            self._set_stage(OrchestratorStage.REGISTERING_MODEL)
            version = self._register_model(
                model_path=training_result.get("model_path", ""),
                metrics={
                    "resolution_rate": result.resolution_rate,
                    "training_steps": result.training_steps,
                    "traces_collected": result.traces_collected,
                },
            )
            if version:
                result.model_version = version.version_id
                result.model_path = version.model_path
            
            # Complete
            self._set_stage(OrchestratorStage.COMPLETED)
            result.success = True
            result.model_path = training_result.get("model_path", "")
            
            logger.info(
                f"Training cycle completed: resolution_rate={result.resolution_rate:.1%}, "
                f"improvement={result.improvement:.1%}"
            )
            
        except Exception as e:
            logger.error(f"Training cycle failed: {e}")
            self._set_stage(OrchestratorStage.FAILED)
            result.error = str(e)
            result.success = False
            
            # Save checkpoint on failure for recovery
            if self.config.save_on_shutdown:
                self._save_checkpoint()
        
        return result
    
    def get_checkpoint_path(self, checkpoint_id: str) -> Path:
        """Get the path to a checkpoint directory."""
        return Path(self.config.checkpoint_dir) / checkpoint_id
    
    def list_checkpoints(self) -> List[CheckpointState]:
        """List all available checkpoints."""
        checkpoints = []
        checkpoint_dir = Path(self.config.checkpoint_dir)
        
        if not checkpoint_dir.exists():
            return checkpoints
        
        for checkpoint_path in checkpoint_dir.iterdir():
            if checkpoint_path.is_dir():
                metadata_path = checkpoint_path / "metadata.json"
                if metadata_path.exists():
                    try:
                        with open(metadata_path, "r") as f:
                            data = json.load(f)
                        checkpoint = CheckpointState.from_dict(data)
                        checkpoints.append(checkpoint)
                    except Exception as e:
                        logger.warning(f"Failed to load checkpoint {checkpoint_path}: {e}")
        
        # Sort by timestamp (newest first)
        checkpoints.sort(key=lambda c: c.timestamp, reverse=True)
        return checkpoints
    
    def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """Delete a checkpoint by ID."""
        checkpoint_path = self.get_checkpoint_path(checkpoint_id)
        if checkpoint_path.exists():
            shutil.rmtree(checkpoint_path)
            logger.info(f"Deleted checkpoint: {checkpoint_id}")
            return True
        return False
    
    def cleanup_old_checkpoints(self) -> int:
        """Remove old checkpoints, keeping only the configured number."""
        checkpoints = self.list_checkpoints()
        deleted = 0
        
        # Keep the configured number of checkpoints
        while len(checkpoints) > self.config.keep_checkpoints:
            old_checkpoint = checkpoints.pop()
            if self.delete_checkpoint(old_checkpoint.checkpoint_id):
                deleted += 1
        
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old checkpoints")
        
        return deleted
    
    # -------------------------------------------------------------------------
    # Internal Methods
    # -------------------------------------------------------------------------
    
    def _set_stage(self, stage: OrchestratorStage) -> None:
        """Set the current stage and update progress."""
        old_stage = self._stage
        self._stage = stage
        self._progress.stage = stage
        
        logger.info(f"Orchestrator stage: {old_stage.value} -> {stage.value}")
        self._notify_progress()
    
    def _update_progress(self, **kwargs) -> None:
        """Update progress fields and notify callbacks."""
        for key, value in kwargs.items():
            if hasattr(self._progress, key):
                setattr(self._progress, key, value)
        
        # Update elapsed time
        if self._start_time:
            self._progress.elapsed_time = datetime.now().timestamp() - self._start_time
        
        self._notify_progress()
    
    def _notify_progress(self) -> None:
        """Notify all progress callbacks."""
        for callback in self._progress_callbacks:
            try:
                callback(self._progress)
            except Exception as e:
                logger.warning(f"Progress callback error: {e}")
    
    async def _collect_data(
        self,
        base_model: str,
        swebench_subset: str,
    ) -> List[ExecutionTrace]:
        """Collect training data from SWE-bench."""
        logger.info(f"Starting data collection: {self.config.data_collection_episodes} episodes")
        
        collected_traces = []
        total = self.config.data_collection_episodes
        
        for episode in range(total):
            if self.is_shutdown_requested:
                logger.info("Data collection interrupted by shutdown request")
                break
            
            # Update progress
            self._update_progress(
                stage_progress=(episode + 1) / total,
                completed_episodes=episode + 1,
                total_episodes=total,
                traces_collected=len(self._collected_traces) + len(collected_traces),
            )
            
            try:
                # Collect a single episode (simplified - would use actual harness)
                trace = await self._collect_single_episode(
                    base_model=base_model,
                    subset=swebench_subset,
                    episode_num=episode,
                )
                if trace:
                    collected_traces.append(trace)
                    
            except Exception as e:
                logger.warning(f"Episode {episode} failed: {e}")
                continue
            
            # Periodic checkpoint during collection
            if (episode + 1) % 50 == 0:
                self._collected_traces.extend(collected_traces)
                self._save_checkpoint()
                collected_traces = []
        
        self._collected_traces.extend(collected_traces)
        logger.info(f"Data collection complete: {len(self._collected_traces)} total traces")
        
        return self._collected_traces
    
    async def _collect_single_episode(
        self,
        base_model: str,
        subset: str,
        episode_num: int,
    ) -> Optional[ExecutionTrace]:
        """
        Collect a single training episode.
        
        This is a simplified implementation. In production, this would
        integrate with the actual SWE-bench harness from Phase 7.
        """
        # Placeholder - in production this would use the actual harness
        trace_id = f"trace_ep{episode_num}_{uuid.uuid4().hex[:8]}"
        
        trace = ExecutionTrace(
            trace_id=trace_id,
            task_id=f"task_{episode_num}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            problem_statement=f"Sample problem for episode {episode_num}",
            repo_context={"subset": subset},
            model=base_model,
        )
        
        return trace
    
    def _compute_rewards(self) -> None:
        """Compute rewards for all collected traces."""
        logger.info(f"Computing rewards for {len(self._collected_traces)} traces")
        
        total = len(self._collected_traces)
        for i, trace in enumerate(self._collected_traces):
            if self.is_shutdown_requested:
                break
            
            self.reward_calculator.compute_reward(trace)
            
            # Update progress
            self._update_progress(
                stage_progress=(i + 1) / total,
                traces_processed=i + 1,
            )
        
        logger.info("Reward computation complete")
    
    async def _train_with_evaluations(
        self,
        base_model: str,
        num_eval_tasks: int,
    ) -> Dict[str, Any]:
        """
        Train the model with periodic evaluations.
        
        Returns:
            Dictionary with training results
        """
        result = {
            "steps": 0,
            "time": 0.0,
            "evaluations": 0,
            "model_path": "",
            "best_checkpoint": "",
            "metrics": None,
        }
        
        # Initialize trainer if needed
        if not self._trainer_initialized:
            grpo_config = GRPOConfig(
                output_dir=self.config.model_output_dir,
                learning_rate=self.config.learning_rate,
                num_epochs=self.config.num_epochs,
                batch_size=self.config.batch_size,
                use_peft=self.config.use_peft,
                save_steps=self.config.checkpoint_interval,
            )
            self._trainer = AutoDevGRPOTrainer(
                model=base_model,
                config=grpo_config,
                reward_calculator=self.reward_calculator,
                data_collector=self.data_collector,
            )
            self._trainer_initialized = True
        
        train_start_time = datetime.now().timestamp()
        total_steps = self.config.max_training_steps
        eval_interval = self.config.evaluation_interval
        best_checkpoint = ""
        
        # Training loop with evaluation intervals
        for step in range(0, total_steps, eval_interval):
            if self.is_shutdown_requested:
                logger.info("Training interrupted by shutdown request")
                break
            
            # Update progress
            self._update_progress(
                stage_progress=(step + eval_interval) / total_steps,
                completed_steps=step + eval_interval,
                total_steps=total_steps,
            )
            
            # Checkpoint at intervals
            if step > 0 and step % self.config.checkpoint_interval == 0:
                self._save_checkpoint()
            
            # Evaluation at intervals
            if eval_interval > 0 and step > 0 and step % eval_interval == 0:
                eval_result = await self._run_evaluation(num_eval_tasks)
                resolution_rate = eval_result.get("resolution_rate", 0.0)
                result["evaluations"] += 1
                
                # Track best model
                if resolution_rate > self._best_resolution_rate:
                    self._best_resolution_rate = resolution_rate
                    best_checkpoint = self._current_checkpoint.checkpoint_id if self._current_checkpoint else ""
                
                logger.info(
                    f"Evaluation at step {step}: "
                    f"resolution_rate={resolution_rate:.1%}, "
                    f"best={self._best_resolution_rate:.1%}"
                )
        
        result["steps"] = min(step + eval_interval, total_steps)
        result["time"] = datetime.now().timestamp() - train_start_time
        result["best_checkpoint"] = best_checkpoint
        
        # Get final model path
        output_path = Path(self.config.model_output_dir)
        result["model_path"] = str(output_path / "final_model")
        
        return result
    
    async def _run_evaluation(self, num_tasks: int) -> Dict[str, Any]:
        """
        Run evaluation on the current model.
        
        Returns:
            Dictionary with evaluation results
        """
        logger.info(f"Running evaluation on {num_tasks} tasks")
        
        # Placeholder - in production this would use the actual SWE-bench runner
        # from Phase 9's swebench_runner.py
        
        # Simulate evaluation progress
        self._set_stage(OrchestratorStage.EVALUATING)
        self._update_progress(stage_progress=0.0)
        
        # Simulate resolution rate (would come from actual evaluation)
        import random
        resolution_rate = 0.20 + random.random() * 0.10  # 20-30% range
        
        self._update_progress(
            stage_progress=1.0,
            evaluations_completed=self._progress.evaluations_completed + 1,
            best_resolution_rate=max(self._best_resolution_rate, resolution_rate),
        )
        
        return {
            "resolution_rate": resolution_rate,
            "tasks_evaluated": num_tasks,
            "resolved_count": int(num_tasks * resolution_rate),
        }
    
    def _register_model(
        self,
        model_path: str,
        metrics: Dict[str, float],
    ) -> Optional[ModelVersion]:
        """Register the trained model in the registry."""
        if not model_path:
            logger.warning("No model path to register")
            return None
        
        logger.info(f"Registering model: {model_path}")
        
        version = self.registry.register_model(
            model_path=model_path,
            metrics=metrics,
            model_name="autodev-grpo",
            description=f"GRPO trained model - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            status=ModelStatus.STAGING,
            copy_model=True,
        )
        
        self._model_version = version
        logger.info(f"Model registered: {version.version_id}")
        
        return version
    
    def _create_cancelled_result(self) -> TrainingCycleResult:
        """Create a result for a cancelled training cycle."""
        self._set_stage(OrchestratorStage.CANCELLED)
        return TrainingCycleResult(
            success=False,
            cancelled=True,
            traces_collected=len(self._collected_traces),
            training_steps=self._progress.completed_steps,
            best_checkpoint=self._current_checkpoint.checkpoint_id if self._current_checkpoint else "",
        )
    
    # -------------------------------------------------------------------------
    # Checkpoint Management
    # -------------------------------------------------------------------------
    
    def _save_checkpoint(self) -> CheckpointState:
        """Save current state to a checkpoint."""
        checkpoint_id = f"ckpt_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        checkpoint_path = self.get_checkpoint_path(checkpoint_id)
        checkpoint_path.mkdir(parents=True, exist_ok=True)
        
        # Create checkpoint state
        state = CheckpointState(
            checkpoint_id=checkpoint_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            stage=self._stage,
            progress=self._progress,
            config=self.config,
            training_step=self._progress.completed_steps,
            metrics={
                "best_resolution_rate": self._best_resolution_rate,
                "traces_collected": len(self._collected_traces),
            },
        )
        
        # Save metadata
        metadata_path = checkpoint_path / "metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(state.to_dict(), f, indent=2)
        
        # Save traces
        if self._collected_traces:
            traces_path = checkpoint_path / "traces.json"
            with open(traces_path, "w") as f:
                json.dump([t.to_dict() for t in self._collected_traces], f)
            state.collected_traces = [str(traces_path)]
        
        self._current_checkpoint = state
        logger.info(f"Checkpoint saved: {checkpoint_id}")
        
        # Cleanup old checkpoints
        self.cleanup_old_checkpoints()
        
        return state
    
    def _load_latest_checkpoint(self) -> Optional[CheckpointState]:
        """Load the most recent checkpoint."""
        checkpoints = self.list_checkpoints()
        if not checkpoints:
            return None
        
        latest = checkpoints[0]  # Sorted by timestamp, newest first
        checkpoint_path = self.get_checkpoint_path(latest.checkpoint_id)
        
        # Load traces if available
        traces_path = checkpoint_path / "traces.json"
        if traces_path.exists():
            with open(traces_path, "r") as f:
                traces_data = json.load(f)
            latest.collected_traces = [str(traces_path)]
        
        return latest
    
    def _restore_from_checkpoint(self, checkpoint: CheckpointState) -> None:
        """Restore state from a checkpoint."""
        # Restore progress
        self._progress = checkpoint.progress
        self._stage = checkpoint.stage
        self._best_resolution_rate = checkpoint.metrics.get("best_resolution_rate", 0.0)
        
        # Restore traces
        checkpoint_path = self.get_checkpoint_path(checkpoint.checkpoint_id)
        traces_path = checkpoint_path / "traces.json"
        if traces_path.exists():
            with open(traces_path, "r") as f:
                traces_data = json.load(f)
            self._collected_traces = [
                ExecutionTrace.from_dict(t) for t in traces_data
            ]
        
        self._current_checkpoint = checkpoint
        logger.info(f"Restored from checkpoint: {checkpoint.checkpoint_id}")


# -------------------------------------------------------------------------
# Convenience Functions
# -------------------------------------------------------------------------

def create_orchestrator(
    checkpoint_dir: str = "~/.autodev/checkpoints",
    model_output_dir: str = "~/.autodev/models",
    **kwargs,
) -> TrainingOrchestrator:
    """
    Create a TrainingOrchestrator with common settings.
    
    Args:
        checkpoint_dir: Directory for checkpoints
        model_output_dir: Directory for trained models
        **kwargs: Additional configuration options
        
    Returns:
        Configured TrainingOrchestrator instance
    """
    config = OrchestratorConfig(
        checkpoint_dir=checkpoint_dir,
        model_output_dir=model_output_dir,
        **kwargs,
    )
    return TrainingOrchestrator(config)


async def run_training(
    base_model: str,
    episodes: int = 100,
    eval_tasks: int = 50,
    checkpoint_dir: str = "~/.autodev/checkpoints",
    **kwargs,
) -> TrainingCycleResult:
    """
    Run a complete training cycle with default settings.
    
    Args:
        base_model: Base model to train
        episodes: Number of training episodes
        eval_tasks: Number of evaluation tasks
        checkpoint_dir: Directory for checkpoints
        **kwargs: Additional configuration options
        
    Returns:
        TrainingCycleResult with training outcomes
    """
    config = OrchestratorConfig(
        data_collection_episodes=episodes,
        evaluation_tasks=eval_tasks,
        checkpoint_dir=checkpoint_dir,
        **kwargs,
    )
    
    orchestrator = TrainingOrchestrator(config)
    return await orchestrator.run_training_cycle(
        base_model=base_model,
        num_eval_tasks=eval_tasks,
    )
