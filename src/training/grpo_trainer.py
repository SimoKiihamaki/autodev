"""
GRPO Trainer for AutoDev RL Training

This module provides the AutoDevGRPOTrainer class which wraps TRL's GRPOTrainer
for reinforcement learning training of code generation models using Group Relative
Policy Optimization (GRPO).

GRPO is a variant of PPO that uses group-wise relative advantages, making it
particularly suitable for code generation tasks where relative quality comparisons
are more meaningful than absolute reward values.

Usage:
    from training.grpo_trainer import AutoDevGRPOTrainer, GRPOConfig
    
    config = GRPOConfig(
        learning_rate=1e-5,
        num_epochs=3,
        batch_size=8,
        kl_coef=0.1
    )
    
    trainer = AutoDevGRPOTrainer(
        model=model,
        ref_model=ref_model,
        config=config,
        reward_calculator=reward_calculator
    )
    
    # Train with collected traces
    trainer.train(traces=collected_traces)
    
    # Save the trained model
    trainer.save_model("path/to/output")
"""

import json
import logging
import os
import shutil
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Callable
from enum import Enum
import hashlib

# Optional dependencies
try:
    import torch
    import torch.nn as nn
    from torch.utils.data import Dataset, DataLoader
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None
    nn = None
    # Create a base class for Dataset when torch is not available
    class Dataset:
        """Base class for datasets when torch is not available."""
        def __len__(self) -> int:
            raise NotImplementedError
        def __getitem__(self, idx):
            raise NotImplementedError
    class DataLoader:
        """Placeholder for DataLoader when torch is not available."""
        def __init__(self, *args, **kwargs):
            pass

try:
    from transformers import (
        PreTrainedModel,
        PreTrainedTokenizer,
        AutoModelForCausalLM,
        AutoTokenizer,
        TrainingArguments,
        Trainer,
    )
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    PreTrainedModel = object
    PreTrainedTokenizer = object

try:
    from trl import GRPOTrainer as TRLGRPOTrainer, GRPOConfig as TRLGRPOConfig
    TRL_AVAILABLE = True
except ImportError:
    TRL_AVAILABLE = False
    TRLGRPOTrainer = object
    TRLGRPOConfig = object

from .data_collector import ExecutionTrace, TraceStatus, TrainingDataCollector
from .reward_calculator import RewardCalculator, RewardComponents, RewardConfig

logger = logging.getLogger(__name__)


class TrainingStage(Enum):
    """Stages of the training process."""
    INITIALIZING = "initializing"
    PREPARING_DATA = "preparing_data"
    TRAINING = "training"
    EVALUATING = "evaluating"
    COMPLETED = "completed"
    FAILED = "failed"


class OptimizerType(Enum):
    """Supported optimizer types."""
    ADAMW = "adamw"
    ADAM = "adam"
    SGD = "sgd"


class SchedulerType(Enum):
    """Learning rate scheduler types."""
    LINEAR = "linear"
    COSINE = "cosine"
    CONSTANT = "constant"
    WARMUP_LINEAR = "warmup_linear"
    WARMUP_COSINE = "warmup_cosine"


@dataclass
class GRPOConfig:
    """
    Configuration for GRPO training.
    
    This configuration wraps and extends TRL's GRPOConfig with AutoDev-specific
    settings for code generation training.
    
    Attributes:
        learning_rate: Learning rate for optimizer
        num_epochs: Number of training epochs
        batch_size: Batch size per GPU
        gradient_accumulation_steps: Steps to accumulate gradients
        kl_coef: KL divergence coefficient for PPO
        clip_range: PPO clip range
        gamma: Discount factor for rewards
        gae_lambda: GAE lambda parameter
        max_grad_norm: Maximum gradient norm for clipping
        warmup_ratio: Ratio of training for warmup
        weight_decay: Weight decay for optimizer
        optimizer: Optimizer type
        scheduler: Learning rate scheduler type
        seed: Random seed for reproducibility
        mixed_precision: Use mixed precision training
        gradient_checkpointing: Use gradient checkpointing to save memory
        use_peft: Use Parameter-Efficient Fine-Tuning (LoRA/QLoRA)
        lora_r: LoRA rank
        lora_alpha: LoRA alpha parameter
        lora_dropout: LoRA dropout
        max_length: Maximum sequence length
        max_prompt_length: Maximum prompt length
        response_length: Expected response length
        temperature: Sampling temperature for generation
        top_p: Top-p sampling parameter
        top_k: Top-k sampling parameter
        num_samples: Number of samples per prompt for GRPO
        reward_normalization: Normalize rewards across batch
        advantage_normalization: Normalize advantages
        use_reward_scaling: Scale rewards by running statistics
        reward_clip_range: Clip rewards to this range
        early_stopping_patience: Epochs without improvement before stopping
        early_stopping_metric: Metric to monitor for early stopping
        save_steps: Save checkpoint every N steps
        eval_steps: Evaluate every N steps
        logging_steps: Log every N steps
        output_dir: Output directory for checkpoints and logs
        run_name: Name for this training run
    """
    # Core training hyperparameters
    learning_rate: float = 1e-5
    num_epochs: int = 3
    batch_size: int = 8
    gradient_accumulation_steps: int = 1
    
    # PPO/GRPO specific parameters
    kl_coef: float = 0.1
    clip_range: float = 0.2
    gamma: float = 1.0
    gae_lambda: float = 0.95
    
    # Optimization
    max_grad_norm: float = 1.0
    warmup_ratio: float = 0.1
    weight_decay: float = 0.01
    optimizer: str = "adamw"
    scheduler: str = "cosine"
    seed: int = 42
    
    # Memory optimization
    mixed_precision: str = "fp16"  # "fp16", "bf16", or "no"
    gradient_checkpointing: bool = True
    
    # PEFT/LoRA settings
    use_peft: bool = False
    lora_r: int = 8
    lora_alpha: int = 16
    lora_dropout: float = 0.05
    
    # Sequence length settings
    max_length: int = 2048
    max_prompt_length: int = 1024
    response_length: int = 512
    
    # Generation parameters
    temperature: float = 1.0
    top_p: float = 0.95
    top_k: int = 50
    num_samples: int = 4  # Number of samples per prompt for GRPO
    
    # Reward settings
    reward_normalization: bool = True
    advantage_normalization: bool = True
    use_reward_scaling: bool = True
    reward_clip_range: float = 10.0
    
    # Early stopping
    early_stopping_patience: int = 3
    early_stopping_metric: str = "reward"
    
    # Checkpointing and logging
    save_steps: int = 500
    eval_steps: int = 500
    logging_steps: int = 10
    output_dir: str = "~/.autodev/training_output"
    run_name: str = ""
    
    def __post_init__(self):
        """Validate and process configuration."""
        self.output_dir = os.path.expanduser(self.output_dir)
        
        if not self.run_name:
            self.run_name = f"grpo_run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        
        # Validate optimizer type
        valid_optimizers = [o.value for o in OptimizerType]
        if self.optimizer not in valid_optimizers:
            logger.warning(f"Unknown optimizer '{self.optimizer}', using 'adamw'")
            self.optimizer = "adamw"
        
        # Validate scheduler type
        valid_schedulers = [s.value for s in SchedulerType]
        if self.scheduler not in valid_schedulers:
            logger.warning(f"Unknown scheduler '{self.scheduler}', using 'cosine'")
            self.scheduler = "cosine"
        
        # Validate mixed precision
        valid_mp = ["fp16", "bf16", "no"]
        if self.mixed_precision not in valid_mp:
            logger.warning(f"Unknown mixed precision '{self.mixed_precision}', using 'fp16'")
            self.mixed_precision = "fp16"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GRPOConfig":
        """Create from dictionary."""
        return cls(**data)
    
    def to_training_arguments(self) -> Dict[str, Any]:
        """
        Convert to HuggingFace TrainingArguments format.
        
        Returns:
            Dictionary of training arguments
        """
        return {
            "learning_rate": self.learning_rate,
            "num_train_epochs": self.num_epochs,
            "per_device_train_batch_size": self.batch_size,
            "gradient_accumulation_steps": self.gradient_accumulation_steps,
            "max_grad_norm": self.max_grad_norm,
            "warmup_ratio": self.warmup_ratio,
            "weight_decay": self.weight_decay,
            "optim": self.optimizer,
            "lr_scheduler_type": self.scheduler,
            "seed": self.seed,
            "fp16": self.mixed_precision == "fp16",
            "bf16": self.mixed_precision == "bf16",
            "gradient_checkpointing": self.gradient_checkpointing,
            "save_steps": self.save_steps,
            "eval_steps": self.eval_steps,
            "logging_steps": self.logging_steps,
            "output_dir": self.output_dir,
            "run_name": self.run_name,
        }


@dataclass
class TrainingMetrics:
    """
    Metrics tracked during training.
    
    Attributes:
        epoch: Current epoch
        step: Current step
        total_steps: Total training steps
        loss: Current loss value
        policy_loss: Policy loss component
        value_loss: Value loss component
        kl_divergence: KL divergence from reference
        entropy: Policy entropy
        mean_reward: Mean reward in batch
        std_reward: Standard deviation of rewards
        learning_rate: Current learning rate
        gradient_norm: Gradient norm before clipping
        elapsed_time: Elapsed training time in seconds
        samples_per_second: Training throughput
    """
    epoch: float = 0.0
    step: int = 0
    total_steps: int = 0
    loss: float = 0.0
    policy_loss: float = 0.0
    value_loss: float = 0.0
    kl_divergence: float = 0.0
    entropy: float = 0.0
    mean_reward: float = 0.0
    std_reward: float = 0.0
    learning_rate: float = 0.0
    gradient_norm: float = 0.0
    elapsed_time: float = 0.0
    samples_per_second: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)


@dataclass
class CheckpointInfo:
    """
    Information about a saved checkpoint.
    
    Attributes:
        checkpoint_path: Path to checkpoint directory
        step: Training step when checkpoint was saved
        epoch: Training epoch when checkpoint was saved
        metrics: Metrics at checkpoint time
        timestamp: When checkpoint was saved
        model_hash: Hash of model state for verification
    """
    checkpoint_path: str
    step: int
    epoch: float
    metrics: Dict[str, float]
    timestamp: str
    model_hash: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)


class GRPODataset(Dataset):
    """
    Dataset for GRPO training from execution traces.
    
    Converts ExecutionTrace objects into the format expected by GRPO trainer:
    - prompt: The input prompt for code generation
    - completion: The generated code/solution
    - reward: The computed reward signal
    """
    
    def __init__(
        self,
        traces: List[ExecutionTrace],
        reward_calculator: Optional[RewardCalculator] = None,
        tokenizer: Optional[PreTrainedTokenizer] = None,
        max_length: int = 2048,
        max_prompt_length: int = 1024,
    ):
        """
        Initialize the GRPO dataset.
        
        Args:
            traces: List of execution traces
            reward_calculator: Calculator for computing rewards (if not pre-computed)
            tokenizer: Tokenizer for encoding text
            max_length: Maximum total sequence length
            max_prompt_length: Maximum prompt length
        """
        self.traces = traces
        self.reward_calculator = reward_calculator
        self.tokenizer = tokenizer
        self.max_length = max_length
        self.max_prompt_length = max_prompt_length
        
        # Pre-process traces
        self._process_traces()
    
    def _process_traces(self):
        """Process traces into training format."""
        self.processed_data = []
        
        for trace in self.traces:
            # Get formatted prompt and completion
            prompt = trace.get_formatted_prompt()
            completion = trace.get_formatted_completion()
            
            # Compute or retrieve reward
            if trace.reward is None and self.reward_calculator:
                components = self.reward_calculator.compute_reward(trace)
                reward = components.total_reward
            else:
                reward = trace.reward if trace.reward is not None else 0.0
            
            # Tokenize if tokenizer provided
            input_ids = None
            attention_mask = None
            
            if self.tokenizer:
                # Tokenize prompt
                prompt_enc = self.tokenizer(
                    prompt,
                    max_length=self.max_prompt_length,
                    truncation=True,
                    return_tensors=None,
                )
                
                # Tokenize full sequence
                full_text = prompt + completion
                full_enc = self.tokenizer(
                    full_text,
                    max_length=self.max_length,
                    truncation=True,
                    return_tensors=None,
                )
                
                input_ids = full_enc["input_ids"]
                attention_mask = full_enc["attention_mask"]
            
            self.processed_data.append({
                "prompt": prompt,
                "completion": completion,
                "reward": reward,
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "task_id": trace.task_id,
                "trace_id": trace.trace_id,
            })
    
    def __len__(self) -> int:
        """Return number of samples."""
        return len(self.processed_data)
    
    def __getitem__(self, idx: int) -> Dict[str, Any]:
        """Get a sample by index."""
        return self.processed_data[idx]


class AutoDevGRPOTrainer:
    """
    GRPO Trainer for AutoDev code generation models.
    
    This class wraps TRL's GRPOTrainer and integrates with AutoDev's
    data collection and reward calculation systems.
    
    Key features:
    - Seamless integration with TrainingDataCollector and RewardCalculator
    - Support for LoRA/QLoRA fine-tuning
    - Automatic checkpoint management
    - Progress tracking and logging
    - Early stopping based on reward improvement
    
    Example:
        # Initialize with model and config
        trainer = AutoDevGRPOTrainer(
            model="codellama/CodeLlama-7b-hf",
            config=GRPOConfig(learning_rate=1e-5),
            reward_calculator=RewardCalculator()
        )
        
        # Load training data
        collector = TrainingDataCollector()
        traces = collector.load_traces("path/to/traces")
        
        # Train the model
        trainer.train(traces=traces)
        
        # Save and evaluate
        trainer.save_model("path/to/output")
        metrics = trainer.evaluate(test_traces)
    """
    
    def __init__(
        self,
        model: Union[str, PreTrainedModel, None] = None,
        ref_model: Union[str, PreTrainedModel, None] = None,
        config: Optional[GRPOConfig] = None,
        reward_calculator: Optional[RewardCalculator] = None,
        tokenizer: Optional[PreTrainedTokenizer] = None,
        data_collector: Optional[TrainingDataCollector] = None,
        callbacks: Optional[List[Callable]] = None,
    ):
        """
        Initialize the GRPO trainer.
        
        Args:
            model: Model to train (path, name, or PreTrainedModel)
            ref_model: Reference model for KL computation
            config: Training configuration
            reward_calculator: Reward calculator for computing rewards
            tokenizer: Tokenizer for the model
            data_collector: Data collector for loading traces
            callbacks: Optional callbacks for training events
        """
        self.config = config or GRPOConfig()
        self.reward_calculator = reward_calculator or RewardCalculator()
        self.data_collector = data_collector
        self.callbacks = callbacks or []
        
        # Initialize models and tokenizer
        self.model = None
        self.ref_model = None
        self.tokenizer = tokenizer
        self._trl_trainer = None
        
        # Training state
        self._stage = TrainingStage.INITIALIZING
        self._current_epoch = 0
        self._current_step = 0
        self._metrics_history: List[TrainingMetrics] = []
        self._checkpoints: List[CheckpointInfo] = []
        self._start_time: Optional[float] = None
        self._best_reward = float("-inf")
        self._patience_counter = 0
        
        # Load models if paths provided
        if model is not None:
            self._load_model(model)
        if ref_model is not None:
            self._load_ref_model(ref_model)
        
        # Create output directory
        self.output_path = Path(self.config.output_dir)
        self.output_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"AutoDevGRPOTrainer initialized with config: {self.config.to_dict()}")
    
    def _load_model(self, model: Union[str, PreTrainedModel]):
        """Load the model to train."""
        if not TRANSFORMERS_AVAILABLE:
            raise ImportError("transformers is required for model loading")
        
        if isinstance(model, str):
            logger.info(f"Loading model from {model}")
            self.model = AutoModelForCausalLM.from_pretrained(
                model,
                torch_dtype=torch.float16 if self.config.mixed_precision == "fp16" else torch.bfloat16 if self.config.mixed_precision == "bf16" else torch.float32,
                device_map="auto" if TORCH_AVAILABLE else None,
            )
            
            # Load tokenizer if not provided
            if self.tokenizer is None:
                self.tokenizer = AutoTokenizer.from_pretrained(model)
                if self.tokenizer.pad_token is None:
                    self.tokenizer.pad_token = self.tokenizer.eos_token
        else:
            self.model = model
        
        # Apply LoRA if configured
        if self.config.use_peft:
            self._apply_peft()
    
    def _load_ref_model(self, model: Union[str, PreTrainedModel]):
        """Load the reference model for KL computation."""
        if not TRANSFORMERS_AVAILABLE:
            raise ImportError("transformers is required for model loading")
        
        if isinstance(model, str):
            logger.info(f"Loading reference model from {model}")
            self.ref_model = AutoModelForCausalLM.from_pretrained(
                model,
                torch_dtype=torch.float16 if self.config.mixed_precision == "fp16" else torch.bfloat16 if self.config.mixed_precision == "bf16" else torch.float32,
                device_map="auto" if TORCH_AVAILABLE else None,
            )
        else:
            self.ref_model = model
    
    def _apply_peft(self):
        """Apply Parameter-Efficient Fine-Tuning (LoRA)."""
        try:
            from peft import LoraConfig, get_peft_model, TaskType
            
            peft_config = LoraConfig(
                task_type=TaskType.CAUSAL_LM,
                r=self.config.lora_r,
                lora_alpha=self.config.lora_alpha,
                lora_dropout=self.config.lora_dropout,
                target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
            )
            
            self.model = get_peft_model(self.model, peft_config)
            self.model.print_trainable_parameters()
            logger.info("Applied LoRA configuration")
            
        except ImportError:
            logger.warning("PEFT not available, skipping LoRA application")
    
    def _create_trl_trainer(self, train_dataset: GRPODataset, eval_dataset: Optional[GRPODataset] = None):
        """Create the underlying TRL GRPO trainer."""
        if not TRL_AVAILABLE:
            logger.warning("TRL not available, using fallback implementation")
            return None
        
        # Convert our config to TRL format
        training_args = TrainingArguments(
            **self.config.to_training_arguments()
        )
        
        # Create TRL GRPO trainer
        self._trl_trainer = TRLGRPOTrainer(
            model=self.model,
            ref_model=self.ref_model,
            args=training_args,
            train_dataset=train_dataset,
            eval_dataset=eval_dataset,
            tokenizer=self.tokenizer,
        )
        
        return self._trl_trainer
    
    def prepare_dataset(
        self,
        traces: List[ExecutionTrace],
        compute_rewards: bool = True
    ) -> GRPODataset:
        """
        Prepare execution traces for training.
        
        Args:
            traces: List of execution traces
            compute_rewards: Whether to compute rewards if not present
            
        Returns:
            GRPODataset ready for training
        """
        self._stage = TrainingStage.PREPARING_DATA
        
        # Compute rewards if needed
        if compute_rewards:
            for trace in traces:
                if trace.reward is None:
                    components = self.reward_calculator.compute_reward(trace)
                    trace.reward = components.total_reward
        
        # Filter invalid traces
        valid_traces = [
            t for t in traces
            if t.prompt or t.problem_statement
        ]
        
        logger.info(f"Prepared {len(valid_traces)}/{len(traces)} valid traces for training")
        
        # Create dataset
        dataset = GRPODataset(
            traces=valid_traces,
            reward_calculator=self.reward_calculator if compute_rewards else None,
            tokenizer=self.tokenizer,
            max_length=self.config.max_length,
            max_prompt_length=self.config.max_prompt_length,
        )
        
        return dataset
    
    def train(
        self,
        traces: Optional[List[ExecutionTrace]] = None,
        train_dataset: Optional[GRPODataset] = None,
        eval_traces: Optional[List[ExecutionTrace]] = None,
        eval_dataset: Optional[GRPODataset] = None,
        resume_from_checkpoint: Optional[str] = None,
    ) -> TrainingMetrics:
        """
        Train the model using GRPO.
        
        Args:
            traces: Training execution traces (will create dataset if not provided)
            train_dataset: Pre-prepared training dataset
            eval_traces: Evaluation execution traces
            eval_dataset: Pre-prepared evaluation dataset
            resume_from_checkpoint: Path to checkpoint to resume from
            
        Returns:
            Final training metrics
        """
        if not TORCH_AVAILABLE:
            raise ImportError("torch is required for training")
        
        if self.model is None:
            raise ValueError("No model loaded. Call _load_model() first or provide model in constructor.")
        
        self._stage = TrainingStage.TRAINING
        self._start_time = time.time()
        
        # Prepare datasets
        if train_dataset is None:
            if traces is None:
                raise ValueError("Either traces or train_dataset must be provided")
            train_dataset = self.prepare_dataset(traces)
        
        if eval_dataset is not None and eval_traces is not None:
            eval_dataset = self.prepare_dataset(eval_traces, compute_rewards=True)
        
        # Calculate training steps
        num_samples = len(train_dataset)
        steps_per_epoch = num_samples // (self.config.batch_size * self.config.gradient_accumulation_steps)
        total_steps = steps_per_epoch * self.config.num_epochs
        
        logger.info(
            f"Starting GRPO training: {num_samples} samples, "
            f"{steps_per_epoch} steps/epoch, {total_steps} total steps"
        )
        
        # Try to use TRL trainer if available
        if TRL_AVAILABLE and self._trl_trainer is None:
            self._create_trl_trainer(train_dataset, eval_dataset)
        
        # Run training
        if self._trl_trainer is not None:
            final_metrics = self._train_with_trl(
                train_dataset=train_dataset,
                eval_dataset=eval_dataset,
                resume_from_checkpoint=resume_from_checkpoint,
            )
        else:
            # Fallback training loop
            final_metrics = self._train_fallback(
                train_dataset=train_dataset,
                eval_dataset=eval_dataset,
            )
        
        self._stage = TrainingStage.COMPLETED
        logger.info(f"Training completed with final reward: {final_metrics.mean_reward:.4f}")
        
        return final_metrics
    
    def _train_with_trl(
        self,
        train_dataset: GRPODataset,
        eval_dataset: Optional[GRPODataset],
        resume_from_checkpoint: Optional[str],
    ) -> TrainingMetrics:
        """Train using TRL's GRPO trainer."""
        # Train with TRL
        train_result = self._trl_trainer.train(
            resume_from_checkpoint=resume_from_checkpoint
        )
        
        # Extract metrics
        metrics = TrainingMetrics(
            epoch=self.config.num_epochs,
            step=self._trl_trainer.state.global_step,
            total_steps=self._trl_trainer.state.max_steps,
            loss=train_result.training_loss,
            mean_reward=train_result.metrics.get("mean_reward", 0.0),
            elapsed_time=time.time() - self._start_time if self._start_time else 0.0,
        )
        
        self._metrics_history.append(metrics)
        
        return metrics
    
    def _train_fallback(
        self,
        train_dataset: GRPODataset,
        eval_dataset: Optional[GRPODataset],
    ) -> TrainingMetrics:
        """
        Fallback training loop when TRL is not available.
        
        This provides a simplified PPO-style training loop that can work
        without the full TRL library.
        """
        logger.info("Using fallback training loop (TRL not available)")
        
        # Create data loader
        train_loader = DataLoader(
            train_dataset,
            batch_size=self.config.batch_size,
            shuffle=True,
        )
        
        # Setup optimizer
        optimizer = self._create_optimizer()
        scheduler = self._create_scheduler(optimizer, len(train_loader))
        
        # Training loop
        self.model.train()
        global_step = 0
        total_loss = 0.0
        total_reward = 0.0
        
        for epoch in range(self.config.num_epochs):
            self._current_epoch = epoch
            epoch_loss = 0.0
            epoch_reward = 0.0
            
            for batch_idx, batch in enumerate(train_loader):
                # Get batch data
                prompts = batch["prompt"]
                rewards = batch["reward"]
                
                # Tokenize if needed
                if self.tokenizer and batch["input_ids"][0] is None:
                    encodings = self.tokenizer(
                        prompts,
                        padding=True,
                        truncation=True,
                        max_length=self.config.max_length,
                        return_tensors="pt",
                    )
                    input_ids = encodings["input_ids"].to(self.model.device)
                    attention_mask = encodings["attention_mask"].to(self.model.device)
                else:
                    input_ids = torch.stack(batch["input_ids"]).to(self.model.device) if batch["input_ids"][0] is not None else None
                    attention_mask = torch.stack(batch["attention_mask"]).to(self.model.device) if batch["attention_mask"][0] is not None else None
                
                if input_ids is None:
                    continue
                
                # Forward pass
                outputs = self.model(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    labels=input_ids,
                )
                
                loss = outputs.loss
                
                # Scale loss by reward (simplified GRPO)
                reward_tensor = torch.tensor(rewards, dtype=torch.float32, device=self.model.device)
                scaled_loss = loss * (1.0 - reward_tensor.mean() * 0.5)
                
                # Backward pass
                scaled_loss.backward()
                
                # Gradient clipping
                torch.nn.utils.clip_grad_norm_(
                    self.model.parameters(),
                    self.config.max_grad_norm
                )
                
                # Optimizer step
                optimizer.step()
                scheduler.step()
                optimizer.zero_grad()
                
                # Update metrics
                global_step += 1
                self._current_step = global_step
                epoch_loss += loss.item()
                epoch_reward += reward_tensor.mean().item()
                
                # Log progress
                if global_step % self.config.logging_steps == 0:
                    avg_loss = epoch_loss / (batch_idx + 1)
                    avg_reward = epoch_reward / (batch_idx + 1)
                    
                    metrics = TrainingMetrics(
                        epoch=epoch + batch_idx / len(train_loader),
                        step=global_step,
                        total_steps=len(train_loader) * self.config.num_epochs,
                        loss=avg_loss,
                        mean_reward=avg_reward,
                        learning_rate=scheduler.get_last_lr()[0],
                        elapsed_time=time.time() - self._start_time if self._start_time else 0.0,
                    )
                    self._metrics_history.append(metrics)
                    
                    logger.info(
                        f"Epoch {epoch+1}/{self.config.num_epochs}, "
                        f"Step {global_step}, Loss: {avg_loss:.4f}, Reward: {avg_reward:.4f}"
                    )
                    
                    # Check for checkpoint
                    if global_step % self.config.save_steps == 0:
                        self._save_checkpoint(global_step, epoch, metrics)
                
                # Check for early stopping
                if self._check_early_stopping(epoch_reward / (batch_idx + 1)):
                    logger.info(f"Early stopping triggered at epoch {epoch+1}")
                    break
            
            # End of epoch
            avg_epoch_loss = epoch_loss / len(train_loader)
            avg_epoch_reward = epoch_reward / len(train_loader)
            
            logger.info(
                f"Epoch {epoch+1} completed - Loss: {avg_epoch_loss:.4f}, Reward: {avg_epoch_reward:.4f}"
            )
            
            # Run evaluation
            if eval_dataset is not None:
                eval_metrics = self.evaluate(eval_dataset)
                logger.info(f"Evaluation metrics: {eval_metrics.to_dict()}")
        
        # Final metrics
        final_metrics = TrainingMetrics(
            epoch=self.config.num_epochs,
            step=global_step,
            total_steps=global_step,
            loss=total_loss / max(global_step, 1),
            mean_reward=total_reward / max(global_step, 1),
            elapsed_time=time.time() - self._start_time if self._start_time else 0.0,
        )
        
        return final_metrics
    
    def _create_optimizer(self):
        """Create optimizer based on configuration."""
        # Get trainable parameters
        param_optimizer = list(self.model.named_parameters())
        no_decay = ["bias", "LayerNorm.weight"]
        
        optimizer_grouped_parameters = [
            {
                "params": [p for n, p in param_optimizer if not any(nd in n for nd in no_decay)],
                "weight_decay": self.config.weight_decay,
            },
            {
                "params": [p for n, p in param_optimizer if any(nd in n for nd in no_decay)],
                "weight_decay": 0.0,
            },
        ]
        
        if self.config.optimizer == "adamw":
            optimizer = torch.optim.AdamW(
                optimizer_grouped_parameters,
                lr=self.config.learning_rate,
            )
        elif self.config.optimizer == "adam":
            optimizer = torch.optim.Adam(
                optimizer_grouped_parameters,
                lr=self.config.learning_rate,
            )
        else:
            optimizer = torch.optim.SGD(
                optimizer_grouped_parameters,
                lr=self.config.learning_rate,
            )
        
        return optimizer
    
    def _create_scheduler(self, optimizer, num_training_steps: int):
        """Create learning rate scheduler."""
        from torch.optim.lr_scheduler import (
            LinearLR,
            CosineAnnealingLR,
            ConstantLR,
            SequentialLR,
        )
        
        warmup_steps = int(num_training_steps * self.config.warmup_ratio)
        
        if warmup_steps > 0:
            warmup_scheduler = LinearLR(
                optimizer,
                start_factor=0.1,
                end_factor=1.0,
                total_iters=warmup_steps,
            )
            
            if self.config.scheduler == "linear":
                main_scheduler = LinearLR(
                    optimizer,
                    start_factor=1.0,
                    end_factor=0.0,
                    total_iters=num_training_steps - warmup_steps,
                )
            elif self.config.scheduler == "cosine":
                main_scheduler = CosineAnnealingLR(
                    optimizer,
                    T_max=num_training_steps - warmup_steps,
                )
            else:
                main_scheduler = ConstantLR(optimizer, factor=1.0)
            
            scheduler = SequentialLR(
                optimizer,
                schedulers=[warmup_scheduler, main_scheduler],
                milestones=[warmup_steps],
            )
        else:
            if self.config.scheduler == "cosine":
                scheduler = CosineAnnealingLR(optimizer, T_max=num_training_steps)
            elif self.config.scheduler == "linear":
                scheduler = LinearLR(
                    optimizer,
                    start_factor=1.0,
                    end_factor=0.0,
                    total_iters=num_training_steps,
                )
            else:
                scheduler = ConstantLR(optimizer, factor=1.0)
        
        return scheduler
    
    def _check_early_stopping(self, current_reward: float) -> bool:
        """Check if early stopping should be triggered."""
        if current_reward > self._best_reward:
            self._best_reward = current_reward
            self._patience_counter = 0
            return False
        
        self._patience_counter += 1
        return self._patience_counter >= self.config.early_stopping_patience
    
    def _save_checkpoint(
        self,
        step: int,
        epoch: float,
        metrics: TrainingMetrics,
        checkpoint_name: Optional[str] = None
    ) -> CheckpointInfo:
        """Save a training checkpoint."""
        if checkpoint_name is None:
            checkpoint_name = f"checkpoint-{step}"
        
        checkpoint_path = self.output_path / checkpoint_name
        checkpoint_path.mkdir(parents=True, exist_ok=True)
        
        # Save model
        if self.model is not None:
            self.model.save_pretrained(checkpoint_path)
        
        # Save tokenizer
        if self.tokenizer is not None:
            self.tokenizer.save_pretrained(checkpoint_path)
        
        # Save training state
        state = {
            "step": step,
            "epoch": epoch,
            "metrics": metrics.to_dict(),
            "config": self.config.to_dict(),
            "best_reward": self._best_reward,
        }
        
        with open(checkpoint_path / "training_state.json", "w") as f:
            json.dump(state, f, indent=2)
        
        # Create checkpoint info
        checkpoint_info = CheckpointInfo(
            checkpoint_path=str(checkpoint_path),
            step=step,
            epoch=epoch,
            metrics=metrics.to_dict(),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        
        self._checkpoints.append(checkpoint_info)
        
        logger.info(f"Saved checkpoint to {checkpoint_path}")
        
        return checkpoint_info
    
    def save_model(self, output_path: str) -> str:
        """
        Save the trained model.
        
        Args:
            output_path: Directory to save the model to
            
        Returns:
            Path to saved model
        """
        output_path = Path(output_path)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Save model
        if self.model is not None:
            if self.config.use_peft:
                # Save LoRA adapters
                self.model.save_pretrained(output_path)
            else:
                self.model.save_pretrained(output_path)
        
        # Save tokenizer
        if self.tokenizer is not None:
            self.tokenizer.save_pretrained(output_path)
        
        # Save config
        with open(output_path / "grpo_config.json", "w") as f:
            json.dump(self.config.to_dict(), f, indent=2)
        
        # Save metrics history
        metrics_file = output_path / "training_metrics.json"
        with open(metrics_file, "w") as f:
            json.dump(
                [m.to_dict() for m in self._metrics_history],
                f,
                indent=2
            )
        
        logger.info(f"Model saved to {output_path}")
        
        return str(output_path)
    
    def load_model(self, model_path: str) -> None:
        """
        Load a trained model from checkpoint.
        
        Args:
            model_path: Path to the model checkpoint
        """
        if not TRANSFORMERS_AVAILABLE:
            raise ImportError("transformers is required for model loading")
        
        model_path = Path(model_path)
        
        # Load model
        self.model = AutoModelForCausalLM.from_pretrained(model_path)
        
        # Load tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        
        # Load config if available
        config_path = model_path / "grpo_config.json"
        if config_path.exists():
            with open(config_path) as f:
                config_dict = json.load(f)
            self.config = GRPOConfig.from_dict(config_dict)
        
        logger.info(f"Model loaded from {model_path}")
    
    def evaluate(
        self,
        traces: Optional[List[ExecutionTrace]] = None,
        dataset: Optional[GRPODataset] = None,
    ) -> TrainingMetrics:
        """
        Evaluate the model on test data.
        
        Args:
            traces: Test execution traces
            dataset: Pre-prepared test dataset
            
        Returns:
            Evaluation metrics
        """
        self._stage = TrainingStage.EVALUATING
        
        # Prepare dataset
        if dataset is None:
            if traces is None:
                raise ValueError("Either traces or dataset must be provided")
            dataset = self.prepare_dataset(traces)
        
        # Create data loader
        eval_loader = DataLoader(
            dataset,
            batch_size=self.config.batch_size,
            shuffle=False,
        )
        
        # Evaluate
        self.model.eval()
        total_loss = 0.0
        total_reward = 0.0
        num_batches = 0
        
        with torch.no_grad():
            for batch in eval_loader:
                prompts = batch["prompt"]
                rewards = batch["reward"]
                
                # Tokenize if needed
                if self.tokenizer and batch["input_ids"][0] is None:
                    encodings = self.tokenizer(
                        prompts,
                        padding=True,
                        truncation=True,
                        max_length=self.config.max_length,
                        return_tensors="pt",
                    )
                    input_ids = encodings["input_ids"].to(self.model.device)
                    attention_mask = encodings["attention_mask"].to(self.model.device)
                else:
                    input_ids = torch.stack(batch["input_ids"]).to(self.model.device) if batch["input_ids"][0] is not None else None
                    attention_mask = torch.stack(batch["attention_mask"]).to(self.model.device) if batch["attention_mask"][0] is not None else None
                
                if input_ids is None:
                    continue
                
                # Forward pass
                outputs = self.model(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    labels=input_ids,
                )
                
                total_loss += outputs.loss.item()
                total_reward += sum(rewards) / len(rewards)
                num_batches += 1
        
        # Calculate metrics
        metrics = TrainingMetrics(
            loss=total_loss / max(num_batches, 1),
            mean_reward=total_reward / max(num_batches, 1),
        )
        
        self._stage = TrainingStage.COMPLETED
        
        return metrics
    
    def generate(
        self,
        prompt: str,
        max_new_tokens: int = 512,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
        num_return_sequences: int = 1,
    ) -> List[str]:
        """
        Generate code completions from a prompt.
        
        Args:
            prompt: Input prompt
            max_new_tokens: Maximum tokens to generate
            temperature: Sampling temperature (uses config if not provided)
            top_p: Top-p sampling (uses config if not provided)
            top_k: Top-k sampling (uses config if not provided)
            num_return_sequences: Number of sequences to generate
            
        Returns:
            List of generated completions
        """
        if self.model is None or self.tokenizer is None:
            raise ValueError("Model and tokenizer must be loaded for generation")
        
        self.model.eval()
        
        # Use config defaults if not specified
        temperature = temperature if temperature is not None else self.config.temperature
        top_p = top_p if top_p is not None else self.config.top_p
        top_k = top_k if top_k is not None else self.config.top_k
        
        # Tokenize
        inputs = self.tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=self.config.max_prompt_length,
        ).to(self.model.device)
        
        # Generate
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                temperature=temperature if temperature > 0 else 1.0,
                top_p=top_p,
                top_k=top_k,
                num_return_sequences=num_return_sequences,
                do_sample=temperature > 0,
                pad_token_id=self.tokenizer.pad_token_id,
            )
        
        # Decode
        completions = []
        for output in outputs:
            # Remove prompt from output
            generated = output[inputs["input_ids"].shape[1]:]
            completion = self.tokenizer.decode(generated, skip_special_tokens=True)
            completions.append(completion)
        
        return completions
    
    def get_training_metrics(self) -> List[TrainingMetrics]:
        """Get the history of training metrics."""
        return self._metrics_history.copy()
    
    def get_checkpoints(self) -> List[CheckpointInfo]:
        """Get information about saved checkpoints."""
        return self._checkpoints.copy()
    
    @property
    def stage(self) -> TrainingStage:
        """Get current training stage."""
        return self._stage
    
    def add_callback(self, callback: Callable) -> None:
        """Add a callback for training events."""
        self.callbacks.append(callback)
    
    def remove_callback(self, callback: Callable) -> None:
        """Remove a callback."""
        if callback in self.callbacks:
            self.callbacks.remove(callback)


# Convenience functions

def create_trainer(
    model: str,
    learning_rate: float = 1e-5,
    num_epochs: int = 3,
    batch_size: int = 8,
    output_dir: str = "~/.autodev/training_output",
    **kwargs
) -> AutoDevGRPOTrainer:
    """
    Create an AutoDevGRPOTrainer with simplified configuration.
    
    Args:
        model: Model name or path
        learning_rate: Learning rate
        num_epochs: Number of training epochs
        batch_size: Batch size
        output_dir: Output directory
        **kwargs: Additional GRPOConfig parameters
        
    Returns:
        Configured AutoDevGRPOTrainer
    """
    config = GRPOConfig(
        learning_rate=learning_rate,
        num_epochs=num_epochs,
        batch_size=batch_size,
        output_dir=output_dir,
        **kwargs
    )
    
    return AutoDevGRPOTrainer(model=model, config=config)


def train_model(
    model: str,
    traces: List[ExecutionTrace],
    output_dir: str = "~/.autodev/training_output",
    **kwargs
) -> AutoDevGRPOTrainer:
    """
    Train a model on execution traces with one function call.
    
    Args:
        model: Model name or path
        traces: Training execution traces
        output_dir: Output directory for checkpoints
        **kwargs: Additional training configuration
        
    Returns:
        Trained AutoDevGRPOTrainer
    """
    trainer = create_trainer(model=model, output_dir=output_dir, **kwargs)
    trainer.train(traces=traces)
    trainer.save_model(output_dir)
    return trainer


def load_trainer(checkpoint_path: str) -> AutoDevGRPOTrainer:
    """
    Load a trainer from a checkpoint.
    
    Args:
        checkpoint_path: Path to checkpoint directory
        
    Returns:
        Loaded AutoDevGRPOTrainer
    """
    trainer = AutoDevGRPOTrainer()
    trainer.load_model(checkpoint_path)
    return trainer
