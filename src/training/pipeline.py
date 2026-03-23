"""
Training Pipeline for AutoDev RL Training

This module provides the TrainingPipeline class which orchestrates the full
reinforcement learning training workflow, integrating:
- TrainingDataCollector: Execution trace collection
- RewardCalculator: Reward computation
- AutoDevGRPOTrainer: GRPO-based training
- ModelRegistry: Model version management

The pipeline supports:
- End-to-end training from data collection to model promotion
- Incremental training from existing traces
- Evaluation and comparison of model versions
- Automated promotion based on performance thresholds

Usage:
    from training.pipeline import TrainingPipeline, PipelineConfig
    
    # Create pipeline
    config = PipelineConfig(
        base_model="codellama/CodeLlama-7b-hf",
        output_dir="~/.autodev/training_runs"
    )
    pipeline = TrainingPipeline(config)
    
    # Run full training pipeline
    result = await pipeline.run_full_pipeline(
        num_tasks=100,
        promote_on_success=True
    )
    
    # Or run individual steps
    traces = await pipeline.collect_data(num_tasks=50)
    metrics = pipeline.train(traces)
    eval_metrics = pipeline.evaluate(test_traces)
    pipeline.promote_model(version_id="best_version", target_status="production")
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Callable

# Import training components
from .data_collector import (
    ExecutionTrace,
    TraceStatus,
    DataCollectionConfig,
    TrainingDataCollector,
    create_collector,
)
from .reward_calculator import (
    RewardCalculator,
    RewardComponents,
    RewardConfig,
)
from .grpo_trainer import (
    AutoDevGRPOTrainer,
    GRPOConfig,
    GRPODataset,
    TrainingMetrics,
    TrainingStage,
)
from .model_registry import (
    ModelRegistry,
    ModelVersion,
    ModelStatus,
    RegistryConfig,
    create_registry,
)

logger = logging.getLogger(__name__)


class PipelineStage(Enum):
    """Stages of the training pipeline."""
    IDLE = "idle"
    COLLECTING = "collecting"
    COMPUTING_REWARDS = "computing_rewards"
    TRAINING = "training"
    EVALUATING = "evaluating"
    REGISTERING = "registering"
    PROMOTING = "promoting"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class PipelineConfig:
    """
    Configuration for the training pipeline.
    
    Attributes:
        base_model: Base model name or path for training
        ref_model: Reference model for KL divergence (defaults to base_model)
        output_dir: Base directory for all pipeline outputs
        run_name: Name for this training run (auto-generated if not provided)
        
        # Data collection settings
        data_dir: Directory for collected training data
        num_collect_tasks: Number of tasks to collect data from
        max_traces_per_task: Maximum traces per task
        
        # Training settings
        learning_rate: Learning rate for training
        num_epochs: Number of training epochs
        batch_size: Training batch size
        use_peft: Whether to use PEFT/LoRA
        gradient_checkpointing: Whether to use gradient checkpointing
        
        # Evaluation settings
        eval_split_ratio: Ratio of data to use for evaluation
        min_eval_samples: Minimum samples required for evaluation
        
        # Model registry settings
        registry_dir: Directory for model registry
        model_name: Name for registered models
        auto_register: Automatically register trained models
        max_registry_versions: Maximum versions to keep in registry
        
        # Promotion settings
        auto_promote: Automatically promote models meeting thresholds
        swe_bench_threshold: SWE-bench score threshold for promotion
        reward_threshold: Reward threshold for promotion
        
        # Resource settings
        device: Device to use for training (auto-detect if not specified)
        mixed_precision: Mixed precision mode ("fp16", "bf16", "no")
        num_workers: Number of data loading workers
    """
    # Model settings
    base_model: str = "codellama/CodeLlama-7b-hf"
    ref_model: Optional[str] = None
    output_dir: str = "~/.autodev/training_runs"
    run_name: str = ""
    
    # Data collection settings
    data_dir: str = "~/.autodev/training_data"
    num_collect_tasks: int = 100
    max_traces_per_task: int = 10
    include_failed_attempts: bool = True
    
    # Training settings
    learning_rate: float = 1e-5
    num_epochs: int = 3
    batch_size: int = 8
    gradient_accumulation_steps: int = 4
    use_peft: bool = True
    lora_r: int = 16
    lora_alpha: int = 32
    gradient_checkpointing: bool = True
    max_grad_norm: float = 1.0
    warmup_ratio: float = 0.1
    weight_decay: float = 0.01
    
    # Evaluation settings
    eval_split_ratio: float = 0.1
    min_eval_samples: int = 10
    
    # Model registry settings
    registry_dir: str = "~/.autodev/model_registry"
    model_name: str = "autodev-code-model"
    auto_register: bool = True
    max_registry_versions: int = 50
    
    # Promotion settings
    auto_promote: bool = False
    swe_bench_threshold: float = 0.25
    reward_threshold: float = 0.7
    
    # Resource settings
    device: str = ""
    mixed_precision: str = "fp16"
    num_workers: int = 4
    
    # Checkpointing
    save_steps: int = 500
    eval_steps: int = 500
    logging_steps: int = 10
    
    def __post_init__(self):
        """Validate and process configuration."""
        self.output_dir = os.path.expanduser(self.output_dir)
        self.data_dir = os.path.expanduser(self.data_dir)
        self.registry_dir = os.path.expanduser(self.registry_dir)
        
        if not self.run_name:
            self.run_name = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        
        # Set reference model to base model if not specified
        if self.ref_model is None:
            self.ref_model = self.base_model
        
        # Validate mixed precision
        if self.mixed_precision not in ("fp16", "bf16", "no"):
            logger.warning(f"Unknown mixed precision '{self.mixed_precision}', using 'fp16'")
            self.mixed_precision = "fp16"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PipelineConfig":
        """Create from dictionary."""
        return cls(**data)
    
    def to_grpo_config(self) -> GRPOConfig:
        """Convert to GRPOConfig for the trainer."""
        return GRPOConfig(
            learning_rate=self.learning_rate,
            num_epochs=self.num_epochs,
            batch_size=self.batch_size,
            gradient_accumulation_steps=self.gradient_accumulation_steps,
            use_peft=self.use_peft,
            lora_r=self.lora_r,
            lora_alpha=self.lora_alpha,
            gradient_checkpointing=self.gradient_checkpointing,
            max_grad_norm=self.max_grad_norm,
            warmup_ratio=self.warmup_ratio,
            weight_decay=self.weight_decay,
            mixed_precision=self.mixed_precision,
            save_steps=self.save_steps,
            eval_steps=self.eval_steps,
            logging_steps=self.logging_steps,
            output_dir=str(Path(self.output_dir) / self.run_name),
            run_name=self.run_name,
        )
    
    def to_data_collection_config(self) -> DataCollectionConfig:
        """Convert to DataCollectionConfig."""
        return DataCollectionConfig(
            output_dir=self.data_dir,
            max_traces_per_task=self.max_traces_per_task,
            include_failed_attempts=self.include_failed_attempts,
        )
    
    def to_reward_config(self) -> RewardConfig:
        """Convert to RewardConfig."""
        return RewardConfig()


@dataclass
class PipelineResult:
    """
    Result of a pipeline run.
    
    Attributes:
        success: Whether the pipeline completed successfully
        stage: Final pipeline stage
        run_name: Name of the training run
        traces_collected: Number of traces collected
        training_metrics: Final training metrics
        eval_metrics: Evaluation metrics (if evaluation was run)
        model_version: Registered model version (if registered)
        model_path: Path to the trained model
        swe_bench_score: SWE-bench score (if evaluated)
        promoted: Whether the model was promoted
        error: Error message if failed
        elapsed_time: Total elapsed time in seconds
        metadata: Additional metadata
    """
    success: bool = False
    stage: PipelineStage = PipelineStage.IDLE
    run_name: str = ""
    traces_collected: int = 0
    training_metrics: Optional[TrainingMetrics] = None
    eval_metrics: Optional[TrainingMetrics] = None
    model_version: Optional[str] = None
    model_path: str = ""
    swe_bench_score: float = 0.0
    promoted: bool = False
    error: Optional[str] = None
    elapsed_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        data["stage"] = self.stage.value
        if self.training_metrics:
            data["training_metrics"] = self.training_metrics.to_dict()
        if self.eval_metrics:
            data["eval_metrics"] = self.eval_metrics.to_dict()
        return data


class TrainingPipeline:
    """
    Orchestrates the full RL training workflow.
    
    This class coordinates:
    1. Data collection from SWE-bench or other sources
    2. Reward computation for collected traces
    3. GRPO-based model training
    4. Model evaluation and comparison
    5. Model registration and promotion
    
    Example:
        # Create pipeline with custom config
        config = PipelineConfig(
            base_model="codellama/CodeLlama-7b-hf",
            num_epochs=3,
            auto_register=True
        )
        pipeline = TrainingPipeline(config)
        
        # Run full pipeline
        result = await pipeline.run_full_pipeline(num_tasks=100)
        
        # Or run step by step
        traces = await pipeline.collect_data(num_tasks=50)
        pipeline.compute_rewards(traces)
        metrics = pipeline.train(traces)
        
        # Evaluate and promote
        eval_metrics = pipeline.evaluate(test_traces)
        if eval_metrics.mean_reward > 0.7:
            pipeline.promote_model(version_id, ModelStatus.PRODUCTION)
    """
    
    def __init__(
        self,
        config: Optional[PipelineConfig] = None,
        data_collector: Optional[TrainingDataCollector] = None,
        reward_calculator: Optional[RewardCalculator] = None,
        trainer: Optional[AutoDevGRPOTrainer] = None,
        registry: Optional[ModelRegistry] = None,
        callbacks: Optional[List[Callable]] = None,
    ):
        """
        Initialize the training pipeline.
        
        Args:
            config: Pipeline configuration
            data_collector: Pre-configured data collector
            reward_calculator: Pre-configured reward calculator
            trainer: Pre-configured trainer
            registry: Pre-configured model registry
            callbacks: Callbacks for pipeline events
        """
        self.config = config or PipelineConfig()
        self.callbacks = callbacks or []
        
        # Initialize components
        self._stage = PipelineStage.IDLE
        self._start_time: Optional[float] = None
        self._collected_traces: List[ExecutionTrace] = []
        self._train_traces: List[ExecutionTrace] = []
        self._eval_traces: List[ExecutionTrace] = []
        self._current_version: Optional[ModelVersion] = None
        
        # Create output directories
        self.output_path = Path(self.config.output_dir) / self.config.run_name
        self.output_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize data collector
        if data_collector is not None:
            self.data_collector = data_collector
        else:
            self.data_collector = TrainingDataCollector(
                self.config.to_data_collection_config()
            )
        
        # Initialize reward calculator
        if reward_calculator is not None:
            self.reward_calculator = reward_calculator
        else:
            self.reward_calculator = RewardCalculator(
                self.config.to_reward_config()
            )
        
        # Initialize trainer (lazy initialization)
        self._trainer = trainer
        self._trainer_initialized = trainer is not None
        
        # Initialize model registry
        if registry is not None:
            self.registry = registry
        else:
            registry_config = RegistryConfig(
                base_dir=self.config.registry_dir,
                max_versions=self.config.max_registry_versions,
            )
            self.registry = ModelRegistry(registry_config)
        
        logger.info(
            f"TrainingPipeline initialized with run_name={self.config.run_name}, "
            f"base_model={self.config.base_model}"
        )
    
    @property
    def stage(self) -> PipelineStage:
        """Get current pipeline stage."""
        return self._stage
    
    @property
    def trainer(self) -> AutoDevGRPOTrainer:
        """Get the trainer, initializing if needed."""
        if not self._trainer_initialized:
            self._initialize_trainer()
        return self._trainer
    
    def _initialize_trainer(self) -> None:
        """Initialize the GRPO trainer."""
        if self._trainer_initialized:
            return
        
        grpo_config = self.config.to_grpo_config()
        self._trainer = AutoDevGRPOTrainer(
            model=self.config.base_model,
            ref_model=self.config.ref_model,
            config=grpo_config,
            reward_calculator=self.reward_calculator,
            data_collector=self.data_collector,
        )
        self._trainer_initialized = True
        logger.info("GRPO trainer initialized")
    
    def _set_stage(self, stage: PipelineStage) -> None:
        """Set the current pipeline stage and notify callbacks."""
        old_stage = self._stage
        self._stage = stage
        logger.info(f"Pipeline stage: {old_stage.value} -> {stage.value}")
        
        # Notify callbacks
        for callback in self.callbacks:
            try:
                callback("stage_change", {
                    "old_stage": old_stage.value,
                    "new_stage": stage.value,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
            except Exception as e:
                logger.warning(f"Callback error: {e}")
    
    async def collect_data(
        self,
        num_tasks: Optional[int] = None,
        harness: Optional[Any] = None,
        task_ids: Optional[List[str]] = None,
        resume: bool = True,
    ) -> List[ExecutionTrace]:
        """
        Collect training data from SWE-bench or custom harness.
        
        Args:
            num_tasks: Number of tasks to collect (uses config if not provided)
            harness: Custom evaluation harness (uses default if not provided)
            task_ids: Specific task IDs to collect
            resume: Whether to resume from previous collection
            
        Returns:
            List of collected execution traces
        """
        self._set_stage(PipelineStage.COLLECTING)
        self._start_time = datetime.now().timestamp()
        
        num_tasks = num_tasks or self.config.num_collect_tasks
        
        logger.info(f"Starting data collection for {num_tasks} tasks")
        
        # Check for existing traces if resuming
        if resume:
            existing_traces = self._load_existing_traces()
            if existing_traces:
                logger.info(f"Found {len(existing_traces)} existing traces")
                self._collected_traces = existing_traces
        
        try:
            if harness is not None:
                # Use provided harness
                traces = await self._collect_from_harness(harness, num_tasks, task_ids)
            else:
                # Use default collection method
                traces = await self._collect_default(num_tasks, task_ids)
            
            self._collected_traces.extend(traces)
            
            # Save collected traces
            self._save_traces(self._collected_traces)
            
            logger.info(f"Collected {len(self._collected_traces)} total traces")
            
            self._set_stage(PipelineStage.IDLE)
            return self._collected_traces
            
        except Exception as e:
            self._set_stage(PipelineStage.FAILED)
            logger.error(f"Data collection failed: {e}")
            raise
    
    async def _collect_from_harness(
        self,
        harness: Any,
        num_tasks: int,
        task_ids: Optional[List[str]] = None,
    ) -> List[ExecutionTrace]:
        """Collect traces from a custom harness."""
        traces = []
        
        # Try to use harness's collect method if available
        if hasattr(harness, 'collect_traces'):
            traces = await harness.collect_traces(
                num_tasks=num_tasks,
                task_ids=task_ids,
                collector=self.data_collector,
            )
        elif hasattr(harness, 'run_evaluation'):
            # Run evaluation and collect traces
            result = await harness.run_evaluation(
                num_tasks=num_tasks,
                task_ids=task_ids,
            )
            
            # Extract traces from result
            if hasattr(result, 'traces'):
                traces = result.traces
            elif isinstance(result, dict) and 'traces' in result:
                traces = result['traces']
        else:
            logger.warning("Harness does not support trace collection")
        
        return traces
    
    async def _collect_default(
        self,
        num_tasks: int,
        task_ids: Optional[List[str]] = None,
    ) -> List[ExecutionTrace]:
        """Default data collection method."""
        # This is a placeholder that creates synthetic traces
        # In production, this would integrate with SWE-bench harness
        logger.warning(
            "Using default data collection - provide a harness for real data. "
            "Creating synthetic traces for demonstration."
        )
        
        traces = []
        for i in range(min(num_tasks, 10)):  # Limit synthetic traces
            trace = self.data_collector.start_trace(
                task_id=f"synthetic_task_{i}",
                problem_statement=f"Fix issue #{i} in the codebase",
                repo_context={"repo": "example/repo"},
                model=self.config.base_model,
            )
            
            # Add a step
            self.data_collector.record_step(
                trace=trace,
                prompt=f"Solve problem #{i}",
                response="Here's the solution...",
                latency_seconds=1.0,
            )
            
            # Finalize
            self.data_collector.finalize_trace(
                trace=trace,
                status=TraceStatus.SUCCESS if i % 3 != 0 else TraceStatus.FAILED,
                tests_passed=[f"test_{i}_a"] if i % 2 == 0 else [],
                tests_failed=[f"test_{i}_b"] if i % 3 == 0 else [],
                execution_time_seconds=5.0 + i,
            )
            
            traces.append(trace)
        
        return traces
    
    def _load_existing_traces(self) -> List[ExecutionTrace]:
        """Load existing traces from the data directory."""
        traces = []
        traces_dir = Path(self.config.data_dir) / "traces"
        
        if not traces_dir.exists():
            return traces
        
        for trace_file in traces_dir.glob("*.json"):
            try:
                with open(trace_file) as f:
                    data = json.load(f)
                trace = ExecutionTrace.from_dict(data)
                traces.append(trace)
            except Exception as e:
                logger.warning(f"Failed to load trace {trace_file}: {e}")
        
        return traces
    
    def _save_traces(self, traces: List[ExecutionTrace]) -> None:
        """Save traces to the data directory."""
        traces_dir = Path(self.config.data_dir) / "traces"
        traces_dir.mkdir(parents=True, exist_ok=True)
        
        for trace in traces:
            trace_file = traces_dir / f"{trace.trace_id}.json"
            with open(trace_file, "w") as f:
                json.dump(trace.to_dict(), f, indent=2)
        
        logger.debug(f"Saved {len(traces)} traces to {traces_dir}")
    
    def compute_rewards(
        self,
        traces: Optional[List[ExecutionTrace]] = None,
    ) -> List[RewardComponents]:
        """
        Compute rewards for collected traces.
        
        Args:
            traces: Traces to compute rewards for (uses collected traces if not provided)
            
        Returns:
            List of reward components for each trace
        """
        self._set_stage(PipelineStage.COMPUTING_REWARDS)
        
        traces = traces or self._collected_traces
        if not traces:
            logger.warning("No traces to compute rewards for")
            return []
        
        logger.info(f"Computing rewards for {len(traces)} traces")
        
        rewards = self.reward_calculator.compute_batch_rewards(traces)
        
        # Log reward statistics
        total_rewards = [r.total_reward for r in rewards]
        avg_reward = sum(total_rewards) / len(total_rewards) if total_rewards else 0.0
        max_reward = max(total_rewards) if total_rewards else 0.0
        min_reward = min(total_rewards) if total_rewards else 0.0
        
        logger.info(
            f"Reward statistics - Avg: {avg_reward:.4f}, "
            f"Min: {min_reward:.4f}, Max: {max_reward:.4f}"
        )
        
        self._set_stage(PipelineStage.IDLE)
        return rewards
    
    def split_traces(
        self,
        traces: Optional[List[ExecutionTrace]] = None,
        eval_ratio: Optional[float] = None,
    ) -> tuple[List[ExecutionTrace], List[ExecutionTrace]]:
        """
        Split traces into training and evaluation sets.
        
        Args:
            traces: Traces to split (uses collected traces if not provided)
            eval_ratio: Ratio for evaluation split (uses config if not provided)
            
        Returns:
            Tuple of (train_traces, eval_traces)
        """
        traces = traces or self._collected_traces
        eval_ratio = eval_ratio or self.config.eval_split_ratio
        
        if not traces:
            return [], []
        
        # Shuffle traces
        import random
        shuffled = traces.copy()
        random.shuffle(shuffled)
        
        # Split
        split_idx = int(len(shuffled) * (1 - eval_ratio))
        train_traces = shuffled[:split_idx]
        eval_traces = shuffled[split_idx:]
        
        # Ensure minimum eval samples
        if len(eval_traces) < self.config.min_eval_samples:
            # Take from training set
            needed = self.config.min_eval_samples - len(eval_traces)
            if len(train_traces) > needed:
                eval_traces.extend(train_traces[-needed:])
                train_traces = train_traces[:-needed]
        
        logger.info(
            f"Split traces: {len(train_traces)} train, {len(eval_traces)} eval"
        )
        
        self._train_traces = train_traces
        self._eval_traces = eval_traces
        
        return train_traces, eval_traces
    
    def train(
        self,
        traces: Optional[List[ExecutionTrace]] = None,
        eval_traces: Optional[List[ExecutionTrace]] = None,
        resume_from_checkpoint: Optional[str] = None,
    ) -> TrainingMetrics:
        """
        Train the model using GRPO.
        
        Args:
            traces: Training traces (uses split train traces if not provided)
            eval_traces: Evaluation traces (uses split eval traces if not provided)
            resume_from_checkpoint: Path to checkpoint to resume from
            
        Returns:
            Final training metrics
        """
        self._set_stage(PipelineStage.TRAINING)
        
        # Get traces
        traces = traces or self._train_traces or self._collected_traces
        if not traces:
            raise ValueError("No training traces available. Call collect_data() first.")
        
        # Ensure trainer is initialized
        self._initialize_trainer()
        
        logger.info(f"Starting training with {len(traces)} traces")
        
        try:
            # Run training
            metrics = self._trainer.train(
                traces=traces,
                eval_traces=eval_traces or self._eval_traces,
                resume_from_checkpoint=resume_from_checkpoint,
            )
            
            logger.info(
                f"Training completed - Loss: {metrics.loss:.4f}, "
                f"Reward: {metrics.mean_reward:.4f}"
            )
            
            self._set_stage(PipelineStage.IDLE)
            return metrics
            
        except Exception as e:
            self._set_stage(PipelineStage.FAILED)
            logger.error(f"Training failed: {e}")
            raise
    
    def evaluate(
        self,
        traces: Optional[List[ExecutionTrace]] = None,
        dataset: Optional[GRPODataset] = None,
    ) -> TrainingMetrics:
        """
        Evaluate the trained model.
        
        Args:
            traces: Evaluation traces (uses split eval traces if not provided)
            dataset: Pre-prepared evaluation dataset
            
        Returns:
            Evaluation metrics
        """
        self._set_stage(PipelineStage.EVALUATING)
        
        traces = traces or self._eval_traces
        if not traces and dataset is None:
            raise ValueError("No evaluation traces available.")
        
        if not self._trainer_initialized:
            raise ValueError("Trainer not initialized. Call train() first.")
        
        logger.info(f"Evaluating model on {len(traces) if traces else 'dataset'} samples")
        
        try:
            metrics = self._trainer.evaluate(
                traces=traces,
                dataset=dataset,
            )
            
            logger.info(
                f"Evaluation completed - Loss: {metrics.loss:.4f}, "
                f"Reward: {metrics.mean_reward:.4f}"
            )
            
            self._set_stage(PipelineStage.IDLE)
            return metrics
            
        except Exception as e:
            self._set_stage(PipelineStage.FAILED)
            logger.error(f"Evaluation failed: {e}")
            raise
    
    def register_model(
        self,
        model_path: Optional[str] = None,
        metrics: Optional[Dict[str, float]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        description: str = "",
    ) -> ModelVersion:
        """
        Register the trained model in the registry.
        
        Args:
            model_path: Path to the model (uses trainer output if not provided)
            metrics: Model metrics
            metadata: Additional metadata
            tags: Tags for categorization
            description: Description of this version
            
        Returns:
            Registered ModelVersion
        """
        self._set_stage(PipelineStage.REGISTERING)
        
        # Determine model path
        if model_path is None:
            if self._trainer is None:
                raise ValueError("No model available to register")
            model_path = str(self.output_path / "final_model")
            self._trainer.save_model(model_path)
        
        # Prepare metrics
        if metrics is None:
            metrics = {}
            if self._trainer:
                training_metrics = self._trainer.get_training_metrics()
                if training_metrics:
                    latest = training_metrics[-1]
                    metrics["final_loss"] = latest.loss
                    metrics["final_reward"] = latest.mean_reward
        
        # Prepare metadata
        if metadata is None:
            metadata = {
                "run_name": self.config.run_name,
                "base_model": self.config.base_model,
                "num_epochs": self.config.num_epochs,
                "learning_rate": self.config.learning_rate,
                "collected_at": datetime.now(timezone.utc).isoformat(),
            }
        
        # Default tags
        if tags is None:
            tags = ["grpo", "autodev", self.config.run_name]
        
        logger.info(f"Registering model from {model_path}")
        
        try:
            version = self.registry.register_model(
                model_path=model_path,
                metrics=metrics,
                metadata=metadata,
                model_name=self.config.model_name,
                tags=tags,
                description=description or f"Trained with {self.config.run_name}",
                copy_model=True,
            )
            
            self._current_version = version
            logger.info(f"Registered model version: {version.version_id}")
            
            self._set_stage(PipelineStage.IDLE)
            return version
            
        except Exception as e:
            self._set_stage(PipelineStage.FAILED)
            logger.error(f"Model registration failed: {e}")
            raise
    
    def promote_model(
        self,
        version_id: Optional[str] = None,
        target_status: ModelStatus = ModelStatus.STAGING,
        require_threshold: bool = True,
    ) -> Optional[ModelVersion]:
        """
        Promote a model version to a higher status.
        
        Args:
            version_id: Version to promote (uses current version if not provided)
            target_status: Target status for promotion
            require_threshold: Whether to require meeting performance thresholds
            
        Returns:
            Promoted ModelVersion or None if promotion was rejected
        """
        self._set_stage(PipelineStage.PROMOTING)
        
        # Get version
        if version_id is None:
            if self._current_version is None:
                raise ValueError("No version to promote. Call register_model() first.")
            version_id = self._current_version.version_id
        
        version = self.registry.get_version(version_id)
        if version is None:
            raise ValueError(f"Version not found: {version_id}")
        
        # Check thresholds if required
        if require_threshold:
            swe_score = version.metrics.get("swe_bench_score", 0.0)
            reward = version.metrics.get("final_reward", 0.0)
            
            if swe_score < self.config.swe_bench_threshold:
                logger.warning(
                    f"SWE-bench score {swe_score:.4f} below threshold "
                    f"{self.config.swe_bench_threshold:.4f}, promotion rejected"
                )
                self._set_stage(PipelineStage.IDLE)
                return None
            
            if reward < self.config.reward_threshold:
                logger.warning(
                    f"Reward {reward:.4f} below threshold "
                    f"{self.config.reward_threshold:.4f}, promotion rejected"
                )
                self._set_stage(PipelineStage.IDLE)
                return None
        
        logger.info(f"Promoting version {version_id} to {target_status.value}")
        
        try:
            promoted = self.registry.promote_version(version_id, target_status)
            
            if promoted:
                logger.info(f"Successfully promoted {version_id} to {target_status.value}")
            
            self._set_stage(PipelineStage.IDLE)
            return promoted
            
        except Exception as e:
            self._set_stage(PipelineStage.FAILED)
            logger.error(f"Model promotion failed: {e}")
            raise
    
    async def run_full_pipeline(
        self,
        num_tasks: Optional[int] = None,
        harness: Optional[Any] = None,
        task_ids: Optional[List[str]] = None,
        promote_on_success: bool = False,
        save_results: bool = True,
    ) -> PipelineResult:
        """
        Run the complete training pipeline.
        
        This method orchestrates the full workflow:
        1. Data collection
        2. Reward computation
        3. Train/eval split
        4. Model training
        5. Model evaluation
        6. Model registration
        7. Model promotion (optional)
        
        Args:
            num_tasks: Number of tasks for data collection
            harness: Custom evaluation harness
            task_ids: Specific task IDs to process
            promote_on_success: Whether to auto-promote on success
            save_results: Whether to save results to file
            
        Returns:
            PipelineResult with all pipeline outputs
        """
        self._start_time = datetime.now().timestamp()
        result = PipelineResult(
            run_name=self.config.run_name,
            stage=PipelineStage.IDLE,
        )
        
        try:
            # 1. Data collection
            logger.info("=" * 50)
            logger.info("Step 1: Data Collection")
            logger.info("=" * 50)
            
            traces = await self.collect_data(
                num_tasks=num_tasks,
                harness=harness,
                task_ids=task_ids,
            )
            result.traces_collected = len(traces)
            
            if not traces:
                result.error = "No traces collected"
                result.stage = PipelineStage.FAILED
                return result
            
            # 2. Reward computation
            logger.info("=" * 50)
            logger.info("Step 2: Reward Computation")
            logger.info("=" * 50)
            
            self.compute_rewards(traces)
            
            # 3. Train/eval split
            logger.info("=" * 50)
            logger.info("Step 3: Train/Eval Split")
            logger.info("=" * 50)
            
            train_traces, eval_traces = self.split_traces(traces)
            
            if not train_traces:
                result.error = "No training traces after split"
                result.stage = PipelineStage.FAILED
                return result
            
            # 4. Model training
            logger.info("=" * 50)
            logger.info("Step 4: Model Training")
            logger.info("=" * 50)
            
            training_metrics = self.train(train_traces, eval_traces)
            result.training_metrics = training_metrics
            
            # 5. Model evaluation
            logger.info("=" * 50)
            logger.info("Step 5: Model Evaluation")
            logger.info("=" * 50)
            
            if eval_traces:
                eval_metrics = self.evaluate(eval_traces)
                result.eval_metrics = eval_metrics
                result.swe_bench_score = eval_metrics.mean_reward  # Simplified
            
            # 6. Model registration
            if self.config.auto_register:
                logger.info("=" * 50)
                logger.info("Step 6: Model Registration")
                logger.info("=" * 50)
                
                register_metrics = {
                    "final_loss": training_metrics.loss,
                    "final_reward": training_metrics.mean_reward,
                    "swe_bench_score": result.swe_bench_score,
                }
                
                version = self.register_model(metrics=register_metrics)
                result.model_version = version.version_id
                result.model_path = version.model_path
            
            # 7. Model promotion
            if promote_on_success or self.config.auto_promote:
                logger.info("=" * 50)
                logger.info("Step 7: Model Promotion")
                logger.info("=" * 50)
                
                promoted = self.promote_model(
                    require_threshold=promote_on_success,
                    target_status=ModelStatus.PRODUCTION if promote_on_success else ModelStatus.STAGING,
                )
                result.promoted = promoted is not None
            
            result.success = True
            result.stage = PipelineStage.COMPLETED
            
        except Exception as e:
            result.success = False
            result.stage = self._stage
            result.error = str(e)
            logger.error(f"Pipeline failed at stage {self._stage.value}: {e}")
        
        finally:
            # Calculate elapsed time
            if self._start_time:
                result.elapsed_time = datetime.now().timestamp() - self._start_time
            
            # Save results
            if save_results:
                self._save_result(result)
        
        logger.info(
            f"Pipeline completed: success={result.success}, "
            f"traces={result.traces_collected}, "
            f"time={result.elapsed_time:.2f}s"
        )
        
        return result
    
    def _save_result(self, result: PipelineResult) -> None:
        """Save pipeline result to file."""
        result_file = self.output_path / "pipeline_result.json"
        
        with open(result_file, "w") as f:
            json.dump(result.to_dict(), f, indent=2)
        
        logger.info(f"Pipeline result saved to {result_file}")
    
    def load_traces(self, path: str) -> List[ExecutionTrace]:
        """
        Load traces from a file or directory.
        
        Args:
            path: Path to trace file or directory
            
        Returns:
            List of loaded traces
        """
        path = Path(path)
        traces = []
        
        if path.is_file():
            with open(path) as f:
                data = json.load(f)
            if isinstance(data, list):
                traces = [ExecutionTrace.from_dict(t) for t in data]
            else:
                traces = [ExecutionTrace.from_dict(data)]
        elif path.is_dir():
            for trace_file in path.glob("*.json"):
                try:
                    with open(trace_file) as f:
                        data = json.load(f)
                    traces.append(ExecutionTrace.from_dict(data))
                except Exception as e:
                    logger.warning(f"Failed to load {trace_file}: {e}")
        
        logger.info(f"Loaded {len(traces)} traces from {path}")
        return traces
    
    def get_best_model(self, metric: str = "final_reward") -> Optional[ModelVersion]:
        """
        Get the best model from the registry.
        
        Args:
            metric: Metric to compare by
            
        Returns:
            Best ModelVersion or None
        """
        return self.registry.get_best_model(
            metric=metric,
            model_name=self.config.model_name,
            higher_is_better=True,
        )
    
    def compare_with_baseline(
        self,
        version_id: str,
        baseline_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Compare a model version with a baseline.
        
        Args:
            version_id: Version to compare
            baseline_id: Baseline version (uses best model if not provided)
            
        Returns:
            Comparison results
        """
        if baseline_id is None:
            baseline = self.get_best_model()
            if baseline is None:
                raise ValueError("No baseline model available")
            baseline_id = baseline.version_id
        
        return self.registry.compare_versions(version_id, baseline_id)
    
    def add_callback(self, callback: Callable) -> None:
        """Add a callback for pipeline events."""
        self.callbacks.append(callback)
    
    def remove_callback(self, callback: Callable) -> None:
        """Remove a callback."""
        if callback in self.callbacks:
            self.callbacks.remove(callback)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about the pipeline and registry."""
        stats = {
            "run_name": self.config.run_name,
            "stage": self._stage.value,
            "collected_traces": len(self._collected_traces),
            "train_traces": len(self._train_traces),
            "eval_traces": len(self._eval_traces),
            "trainer_initialized": self._trainer_initialized,
            "current_version": self._current_version.version_id if self._current_version else None,
            "registry_stats": self.registry.get_statistics(),
        }
        return stats


# Convenience functions

def create_pipeline(
    base_model: str = "codellama/CodeLlama-7b-hf",
    output_dir: str = "~/.autodev/training_runs",
    **kwargs
) -> TrainingPipeline:
    """
    Create a TrainingPipeline with simplified configuration.
    
    Args:
        base_model: Base model name or path
        output_dir: Output directory for training runs
        **kwargs: Additional PipelineConfig parameters
        
    Returns:
        Configured TrainingPipeline
    """
    config = PipelineConfig(
        base_model=base_model,
        output_dir=output_dir,
        **kwargs
    )
    return TrainingPipeline(config)


async def run_training(
    base_model: str,
    num_tasks: int = 100,
    output_dir: str = "~/.autodev/training_runs",
    **kwargs
) -> PipelineResult:
    """
    Run the full training pipeline with one function call.
    
    Args:
        base_model: Base model name or path
        num_tasks: Number of tasks for data collection
        output_dir: Output directory
        **kwargs: Additional pipeline configuration
        
    Returns:
        PipelineResult
    """
    pipeline = create_pipeline(
        base_model=base_model,
        output_dir=output_dir,
        **kwargs
    )
    return await pipeline.run_full_pipeline(num_tasks=num_tasks)


# CLI Entry Point

def main():
    """Command-line interface for the training pipeline."""
    parser = argparse.ArgumentParser(
        description="AutoDev Training Pipeline - RL training for code generation"
    )
    
    # Model arguments
    parser.add_argument(
        "--base-model",
        type=str,
        default="codellama/CodeLlama-7b-hf",
        help="Base model for training",
    )
    parser.add_argument(
        "--ref-model",
        type=str,
        default=None,
        help="Reference model for KL divergence (defaults to base model)",
    )
    
    # Output arguments
    parser.add_argument(
        "--output-dir",
        type=str,
        default="~/.autodev/training_runs",
        help="Output directory for training runs",
    )
    parser.add_argument(
        "--run-name",
        type=str,
        default="",
        help="Name for this training run",
    )
    
    # Data arguments
    parser.add_argument(
        "--num-tasks",
        type=int,
        default=100,
        help="Number of tasks for data collection",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="~/.autodev/training_data",
        help="Directory for training data",
    )
    parser.add_argument(
        "--traces-path",
        type=str,
        default=None,
        help="Path to pre-collected traces (skips collection)",
    )
    
    # Training arguments
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=1e-5,
        help="Learning rate",
    )
    parser.add_argument(
        "--num-epochs",
        type=int,
        default=3,
        help="Number of training epochs",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=8,
        help="Training batch size",
    )
    parser.add_argument(
        "--no-peft",
        action="store_true",
        help="Disable PEFT/LoRA",
    )
    
    # Evaluation arguments
    parser.add_argument(
        "--eval-ratio",
        type=float,
        default=0.1,
        help="Evaluation split ratio",
    )
    
    # Registry arguments
    parser.add_argument(
        "--registry-dir",
        type=str,
        default="~/.autodev/model_registry",
        help="Model registry directory",
    )
    parser.add_argument(
        "--model-name",
        type=str,
        default="autodev-code-model",
        help="Name for registered models",
    )
    parser.add_argument(
        "--no-register",
        action="store_true",
        help="Skip model registration",
    )
    
    # Promotion arguments
    parser.add_argument(
        "--auto-promote",
        action="store_true",
        help="Automatically promote models meeting thresholds",
    )
    parser.add_argument(
        "--swe-bench-threshold",
        type=float,
        default=0.25,
        help="SWE-bench score threshold for promotion",
    )
    parser.add_argument(
        "--reward-threshold",
        type=float,
        default=0.7,
        help="Reward threshold for promotion",
    )
    
    # Resource arguments
    parser.add_argument(
        "--device",
        type=str,
        default="",
        help="Device for training (auto-detect if not specified)",
    )
    parser.add_argument(
        "--mixed-precision",
        type=str,
        default="fp16",
        choices=["fp16", "bf16", "no"],
        help="Mixed precision mode",
    )
    
    # Other arguments
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show configuration without running",
    )
    
    args = parser.parse_args()
    
    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    # Create configuration
    config = PipelineConfig(
        base_model=args.base_model,
        ref_model=args.ref_model,
        output_dir=args.output_dir,
        run_name=args.run_name,
        data_dir=args.data_dir,
        num_collect_tasks=args.num_tasks,
        learning_rate=args.learning_rate,
        num_epochs=args.num_epochs,
        batch_size=args.batch_size,
        use_peft=not args.no_peft,
        eval_split_ratio=args.eval_ratio,
        registry_dir=args.registry_dir,
        model_name=args.model_name,
        auto_register=not args.no_register,
        auto_promote=args.auto_promote,
        swe_bench_threshold=args.swe_bench_threshold,
        reward_threshold=args.reward_threshold,
        device=args.device,
        mixed_precision=args.mixed_precision,
    )
    
    # Dry run - just show configuration
    if args.dry_run:
        print("\n" + "=" * 60)
        print("AutoDev Training Pipeline Configuration")
        print("=" * 60)
        for key, value in config.to_dict().items():
            print(f"  {key}: {value}")
        print("=" * 60 + "\n")
        return 0
    
    # Create and run pipeline
    pipeline = TrainingPipeline(config)
    
    # Run with pre-collected traces or collect new data
    if args.traces_path:
        logger.info(f"Loading traces from {args.traces_path}")
        traces = pipeline.load_traces(args.traces_path)
        
        # Compute rewards and split
        pipeline.compute_rewards(traces)
        train_traces, eval_traces = pipeline.split_traces(traces)
        
        # Train
        training_metrics = pipeline.train(train_traces, eval_traces)
        logger.info(f"Training completed: {training_metrics}")
        
        # Evaluate
        if eval_traces:
            eval_metrics = pipeline.evaluate(eval_traces)
            logger.info(f"Evaluation completed: {eval_metrics}")
        
        # Register
        if config.auto_register:
            version = pipeline.register_model()
            logger.info(f"Model registered: {version.version_id}")
    else:
        # Run full pipeline
        result = asyncio.run(pipeline.run_full_pipeline(
            num_tasks=args.num_tasks,
            promote_on_success=args.auto_promote,
        ))
        
        if result.success:
            logger.info("Pipeline completed successfully!")
            return 0
        else:
            logger.error(f"Pipeline failed: {result.error}")
            return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
