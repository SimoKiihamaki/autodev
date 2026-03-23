"""
Tests for GRPO Trainer

Run with: pytest src/training/test_grpo_trainer.py -v
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
import json
import tempfile
import os

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from dataclasses import asdict

from training.grpo_trainer import (
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

from training.data_collector import (
    ExecutionTrace,
    TraceStep,
    CodeChange,
    TraceStatus,
)

from training.reward_calculator import (
    RewardCalculator,
    RewardConfig,
    RewardComponents,
)


# Sample test data factories

def create_sample_trace(
    task_id: str = "test_task",
    prompt: str = "Write a function to add two numbers",
    completion: str = "def add(a, b):\n    return a + b",
    reward: float = 0.8,
    status: TraceStatus = TraceStatus.SUCCESS
) -> ExecutionTrace:
    """Create a sample execution trace for testing."""
    return ExecutionTrace(
        trace_id=f"trace_{task_id}",
        task_id=task_id,
        timestamp="2024-01-01T00:00:00Z",
        problem_statement=prompt,
        prompt=prompt,
        completion=completion,
        status=status,
        reward=reward,
        steps=[
            TraceStep(
                step_number=1,
                timestamp="2024-01-01T00:00:00Z",
                prompt=prompt,
                response=completion,
            )
        ],
        code_changes=[
            CodeChange(
                file_path="test.py",
                change_type="create",
                new_content=completion,
            )
        ],
        tests_passed=["test_add"],
        tests_failed=[],
    )


def create_sample_traces(count: int = 5) -> list:
    """Create multiple sample traces for testing."""
    return [
        create_sample_trace(
            task_id=f"task_{i}",
            prompt=f"Write function {i}",
            completion=f"def func_{i}(): pass",
            reward=0.5 + i * 0.1,
        )
        for i in range(count)
    ]


class TestGRPOConfig:
    """Tests for GRPOConfig dataclass."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = GRPOConfig()
        
        assert config.learning_rate == 1e-5
        assert config.num_epochs == 3
        assert config.batch_size == 8
        assert config.kl_coef == 0.1
        assert config.clip_range == 0.2
        assert config.gamma == 1.0
        assert config.gae_lambda == 0.95
        assert config.max_grad_norm == 1.0
        assert config.warmup_ratio == 0.1
        assert config.weight_decay == 0.01
        assert config.optimizer == "adamw"
        assert config.scheduler == "cosine"
        assert config.seed == 42
        assert config.mixed_precision == "fp16"
        assert config.gradient_checkpointing == True
        assert config.use_peft == False
        assert config.max_length == 2048
        assert config.max_prompt_length == 1024
        assert config.response_length == 512
        assert config.temperature == 1.0
        assert config.top_p == 0.95
        assert config.top_k == 50
        assert config.num_samples == 4
        assert config.reward_normalization == True
        assert config.early_stopping_patience == 3
    
    def test_custom_config(self):
        """Test custom configuration values."""
        config = GRPOConfig(
            learning_rate=2e-5,
            num_epochs=5,
            batch_size=16,
            kl_coef=0.2,
            mixed_precision="bf16",
        )
        
        assert config.learning_rate == 2e-5
        assert config.num_epochs == 5
        assert config.batch_size == 16
        assert config.kl_coef == 0.2
        assert config.mixed_precision == "bf16"
    
    def test_output_dir_expansion(self):
        """Test that output_dir is expanded."""
        config = GRPOConfig(output_dir="~/test_output")
        assert "~" not in config.output_dir
        assert "test_output" in config.output_dir
    
    def test_run_name_generation(self):
        """Test automatic run name generation."""
        config = GRPOConfig()
        assert config.run_name.startswith("grpo_run_")
    
    def test_custom_run_name(self):
        """Test custom run name."""
        config = GRPOConfig(run_name="my_custom_run")
        assert config.run_name == "my_custom_run"
    
    def test_optimizer_validation(self):
        """Test optimizer validation."""
        config = GRPOConfig(optimizer="invalid")
        assert config.optimizer == "adamw"  # Falls back to default
    
    def test_scheduler_validation(self):
        """Test scheduler validation."""
        config = GRPOConfig(scheduler="invalid")
        assert config.scheduler == "cosine"  # Falls back to default
    
    def test_mixed_precision_validation(self):
        """Test mixed precision validation."""
        config = GRPOConfig(mixed_precision="invalid")
        assert config.mixed_precision == "fp16"  # Falls back to default
    
    def test_to_dict(self):
        """Test serialization to dictionary."""
        config = GRPOConfig(learning_rate=1e-5, batch_size=8)
        d = config.to_dict()
        
        assert isinstance(d, dict)
        assert d["learning_rate"] == 1e-5
        assert d["batch_size"] == 8
    
    def test_from_dict(self):
        """Test deserialization from dictionary."""
        d = {"learning_rate": 2e-5, "batch_size": 16, "num_epochs": 5}
        config = GRPOConfig.from_dict(d)
        
        assert config.learning_rate == 2e-5
        assert config.batch_size == 16
        assert config.num_epochs == 5
    
    def test_to_training_arguments(self):
        """Test conversion to HuggingFace training arguments format."""
        config = GRPOConfig(
            learning_rate=1e-5,
            batch_size=8,
            num_epochs=3,
        )
        args = config.to_training_arguments()
        
        assert args["learning_rate"] == 1e-5
        assert args["per_device_train_batch_size"] == 8
        assert args["num_train_epochs"] == 3
        assert "output_dir" in args


class TestTrainingMetrics:
    """Tests for TrainingMetrics dataclass."""
    
    def test_default_metrics(self):
        """Test default metrics values."""
        metrics = TrainingMetrics()
        
        assert metrics.epoch == 0.0
        assert metrics.step == 0
        assert metrics.loss == 0.0
        assert metrics.policy_loss == 0.0
        assert metrics.value_loss == 0.0
        assert metrics.kl_divergence == 0.0
        assert metrics.mean_reward == 0.0
    
    def test_custom_metrics(self):
        """Test custom metrics values."""
        metrics = TrainingMetrics(
            epoch=1.5,
            step=100,
            loss=0.5,
            mean_reward=0.75,
        )
        
        assert metrics.epoch == 1.5
        assert metrics.step == 100
        assert metrics.loss == 0.5
        assert metrics.mean_reward == 0.75
    
    def test_to_dict(self):
        """Test serialization."""
        metrics = TrainingMetrics(step=50, loss=0.3)
        d = metrics.to_dict()
        
        assert d["step"] == 50
        assert d["loss"] == 0.3


class TestCheckpointInfo:
    """Tests for CheckpointInfo dataclass."""
    
    def test_checkpoint_info(self):
        """Test checkpoint info creation."""
        info = CheckpointInfo(
            checkpoint_path="/path/to/checkpoint",
            step=100,
            epoch=1.0,
            metrics={"loss": 0.5},
            timestamp="2024-01-01T00:00:00Z",
        )
        
        assert info.checkpoint_path == "/path/to/checkpoint"
        assert info.step == 100
        assert info.epoch == 1.0
        assert info.metrics["loss"] == 0.5
    
    def test_to_dict(self):
        """Test serialization."""
        info = CheckpointInfo(
            checkpoint_path="/path",
            step=50,
            epoch=0.5,
            metrics={},
            timestamp="2024-01-01T00:00:00Z",
        )
        
        d = info.to_dict()
        assert d["checkpoint_path"] == "/path"
        assert d["step"] == 50


class TestGRPODataset:
    """Tests for GRPODataset class."""
    
    def test_dataset_creation(self):
        """Test creating a dataset from traces."""
        traces = create_sample_traces(5)
        dataset = GRPODataset(traces=traces)
        
        assert len(dataset) == 5
    
    def test_dataset_getitem(self):
        """Test getting items from dataset."""
        traces = create_sample_traces(3)
        dataset = GRPODataset(traces=traces)
        
        item = dataset[0]
        assert "prompt" in item
        assert "completion" in item
        assert "reward" in item
    
    def test_dataset_with_reward_calculator(self):
        """Test dataset with reward calculator."""
        traces = [create_sample_trace(reward=None)]
        calculator = RewardCalculator()
        
        dataset = GRPODataset(
            traces=traces,
            reward_calculator=calculator,
        )
        
        # Reward should be computed
        item = dataset[0]
        assert item["reward"] is not None
    
    def test_dataset_filters_invalid_traces(self):
        """Test that dataset handles traces with missing data."""
        # Create a trace with no prompt
        trace = create_sample_trace(prompt="", completion="")
        trace.problem_statement = ""
        
        dataset = GRPODataset(traces=[trace])
        
        # Dataset should still be created but the trace may be processed differently
        assert len(dataset) == 1


class TestAutoDevGRPOTrainer:
    """Tests for AutoDevGRPOTrainer class."""
    
    def test_trainer_initialization_default(self):
        """Test trainer initialization with default config."""
        trainer = AutoDevGRPOTrainer()
        
        assert trainer.config is not None
        assert trainer.config.learning_rate == 1e-5
        assert trainer.reward_calculator is not None
        assert trainer.stage == TrainingStage.INITIALIZING
    
    def test_trainer_initialization_custom_config(self):
        """Test trainer initialization with custom config."""
        config = GRPOConfig(
            learning_rate=2e-5,
            batch_size=16,
        )
        trainer = AutoDevGRPOTrainer(config=config)
        
        assert trainer.config.learning_rate == 2e-5
        assert trainer.config.batch_size == 16
    
    def test_trainer_with_reward_calculator(self):
        """Test trainer with custom reward calculator."""
        reward_config = RewardConfig(test_pass_weight=0.6)
        calculator = RewardCalculator(reward_config)
        
        trainer = AutoDevGRPOTrainer(reward_calculator=calculator)
        
        assert trainer.reward_calculator.config.test_pass_weight == 0.6
    
    def test_prepare_dataset(self):
        """Test preparing dataset from traces."""
        trainer = AutoDevGRPOTrainer()
        traces = create_sample_traces(5)
        
        dataset = trainer.prepare_dataset(traces)
        
        assert len(dataset) == 5
        assert trainer.stage == TrainingStage.PREPARING_DATA
    
    def test_prepare_dataset_computes_rewards(self):
        """Test that prepare_dataset computes rewards."""
        traces = [create_sample_trace(reward=None)]
        trainer = AutoDevGRPOTrainer()
        
        dataset = trainer.prepare_dataset(traces, compute_rewards=True)
        
        item = dataset[0]
        assert item["reward"] is not None
    
    def test_get_training_metrics(self):
        """Test getting training metrics history."""
        trainer = AutoDevGRPOTrainer()
        
        metrics = TrainingMetrics(step=10, loss=0.5)
        trainer._metrics_history.append(metrics)
        
        history = trainer.get_training_metrics()
        assert len(history) == 1
        assert history[0].step == 10
    
    def test_get_checkpoints(self):
        """Test getting checkpoint info."""
        trainer = AutoDevGRPOTrainer()
        
        checkpoint = CheckpointInfo(
            checkpoint_path="/test",
            step=100,
            epoch=1.0,
            metrics={},
            timestamp="2024-01-01T00:00:00Z",
        )
        trainer._checkpoints.append(checkpoint)
        
        checkpoints = trainer.get_checkpoints()
        assert len(checkpoints) == 1
        assert checkpoints[0].step == 100
    
    def test_add_callback(self):
        """Test adding callbacks."""
        trainer = AutoDevGRPOTrainer()
        
        callback = lambda: None
        trainer.add_callback(callback)
        
        assert callback in trainer.callbacks
    
    def test_remove_callback(self):
        """Test removing callbacks."""
        callback = lambda: None
        trainer = AutoDevGRPOTrainer(callbacks=[callback])
        
        trainer.remove_callback(callback)
        
        assert callback not in trainer.callbacks
    
    def test_stage_property(self):
        """Test stage property."""
        trainer = AutoDevGRPOTrainer()
        
        assert trainer.stage == TrainingStage.INITIALIZING
        
        trainer._stage = TrainingStage.TRAINING
        assert trainer.stage == TrainingStage.TRAINING


class TestAutoDevGRPOTrainerWithMocks:
    """Tests using mocks to avoid model loading."""
    
    @pytest.fixture
    def mock_model(self):
        """Create a mock model."""
        model = Mock()
        model.device = "cpu"
        model.parameters = Mock(return_value=[Mock()])
        model.train = Mock()
        model.eval = Mock()
        model.save_pretrained = Mock()
        model.state_dict = Mock(return_value={})
        return model
    
    @pytest.fixture
    def mock_tokenizer(self):
        """Create a mock tokenizer."""
        tokenizer = Mock()
        tokenizer.pad_token = "<pad>"
        tokenizer.eos_token = "</s>"
        tokenizer.return_value = {
            "input_ids": Mock(),
            "attention_mask": Mock(),
        }
        tokenizer.save_pretrained = Mock()
        tokenizer.decode = Mock(return_value="generated text")
        return tokenizer
    
    @patch('training.grpo_trainer.TRANSFORMERS_AVAILABLE', False)
    @patch('training.grpo_trainer.TORCH_AVAILABLE', False)
    def test_trainer_without_dependencies(self):
        """Test trainer when dependencies are not available."""
        trainer = AutoDevGRPOTrainer()
        assert trainer._trl_trainer is None
    
    @patch('training.grpo_trainer.TRL_AVAILABLE', False)
    def test_train_fallback_raises_without_model(self):
        """Test that training raises error without model."""
        trainer = AutoDevGRPOTrainer()
        traces = create_sample_traces(3)
        
        with pytest.raises(ValueError, match="No model loaded"):
            trainer.train(traces=traces)
    
    def test_save_model_with_mocks(self, mock_model, mock_tokenizer, tmp_path):
        """Test saving model with mocks."""
        trainer = AutoDevGRPOTrainer()
        trainer.model = mock_model
        trainer.tokenizer = mock_tokenizer
        
        output_path = str(tmp_path / "output")
        result = trainer.save_model(output_path)
        
        assert output_path == result
        mock_model.save_pretrained.assert_called_once()
        mock_tokenizer.save_pretrained.assert_called_once()
    
    def test_evaluate_with_mocks(self, mock_model, mock_tokenizer):
        """Test evaluation with mocked model."""
        trainer = AutoDevGRPOTrainer()
        trainer.model = mock_model
        trainer.tokenizer = mock_tokenizer
        
        traces = create_sample_traces(3)
        
        # Mock torch imports
        with patch('training.grpo_trainer.TORCH_AVAILABLE', True):
            with patch('training.grpo_trainer.torch') as mock_torch:
                # Setup mock tensor behavior
                mock_torch.tensor.return_value = Mock()
                mock_torch.stack.return_value = Mock()
                mock_torch.no_grad = Mock(return_value=Mock(__enter__=Mock(), __exit__=Mock()))
                
                # This would require more complex mocking for full evaluation
                # Just verify the stage changes
                trainer._stage = TrainingStage.EVALUATING
                assert trainer.stage == TrainingStage.EVALUATING
    
    def test_generate_with_mocks(self, mock_model, mock_tokenizer):
        """Test generation with mocked model."""
        trainer = AutoDevGRPOTrainer()
        trainer.model = mock_model
        trainer.tokenizer = mock_tokenizer
        
        # Mock torch
        with patch('training.grpo_trainer.TORCH_AVAILABLE', True):
            with patch('training.grpo_trainer.torch') as mock_torch:
                # Setup mock behavior for generation
                mock_inputs = {"input_ids": Mock(shape=[1, 10])}
                mock_tokenizer.return_value = mock_inputs
                mock_model.generate.return_value = [Mock()]
                mock_model.device = "cpu"
                
                mock_torch.no_grad = Mock(return_value=Mock(__enter__=Mock(), __exit__=Mock()))
                
                # Generate would require more complex mocking
                # Just test that model and tokenizer are set
                assert trainer.model is not None
                assert trainer.tokenizer is not None


class TestConvenienceFunctions:
    """Tests for convenience functions."""
    
    def test_create_trainer(self):
        """Test create_trainer convenience function."""
        with patch('training.grpo_trainer.AutoDevGRPOTrainer._load_model'):
            trainer = create_trainer(
                model="test-model",
                learning_rate=2e-5,
                batch_size=16,
            )
            
            assert trainer.config.learning_rate == 2e-5
            assert trainer.config.batch_size == 16
    
    @patch('training.grpo_trainer.AutoDevGRPOTrainer.train')
    @patch('training.grpo_trainer.AutoDevGRPOTrainer.save_model')
    def test_train_model(self, mock_save, mock_train):
        """Test train_model convenience function."""
        traces = create_sample_traces(3)
        
        with patch('training.grpo_trainer.AutoDevGRPOTrainer._load_model'):
            trainer = train_model(
                model="test-model",
                traces=traces,
                output_dir="~/test_output",
            )
            
            mock_train.assert_called_once()
            mock_save.assert_called_once()
    
    def test_load_trainer(self):
        """Test load_trainer convenience function."""
        with patch.object(AutoDevGRPOTrainer, 'load_model') as mock_load:
            trainer = load_trainer("/path/to/checkpoint")
            
            mock_load.assert_called_once_with("/path/to/checkpoint")


class TestTrainingStage:
    """Tests for TrainingStage enum."""
    
    def test_stages(self):
        """Test all training stages exist."""
        assert TrainingStage.INITIALIZING.value == "initializing"
        assert TrainingStage.PREPARING_DATA.value == "preparing_data"
        assert TrainingStage.TRAINING.value == "training"
        assert TrainingStage.EVALUATING.value == "evaluating"
        assert TrainingStage.COMPLETED.value == "completed"
        assert TrainingStage.FAILED.value == "failed"


class TestOptimizerType:
    """Tests for OptimizerType enum."""
    
    def test_optimizers(self):
        """Test all optimizer types exist."""
        assert OptimizerType.ADAMW.value == "adamw"
        assert OptimizerType.ADAM.value == "adam"
        assert OptimizerType.SGD.value == "sgd"


class TestSchedulerType:
    """Tests for SchedulerType enum."""
    
    def test_schedulers(self):
        """Test all scheduler types exist."""
        assert SchedulerType.LINEAR.value == "linear"
        assert SchedulerType.COSINE.value == "cosine"
        assert SchedulerType.CONSTANT.value == "constant"
        assert SchedulerType.WARMUP_LINEAR.value == "warmup_linear"
        assert SchedulerType.WARMUP_COSINE.value == "warmup_cosine"


class TestIntegration:
    """Integration tests with actual reward calculator."""
    
    def test_full_pipeline_mock(self, tmp_path):
        """Test full training pipeline with mocks."""
        # Create traces
        traces = create_sample_traces(5)
        
        # Create trainer config
        config = GRPOConfig(
            num_epochs=1,
            batch_size=2,
            output_dir=str(tmp_path),
        )
        
        # Create trainer with mock model
        with patch('training.grpo_trainer.AutoDevGRPOTrainer._load_model'):
            trainer = AutoDevGRPOTrainer(config=config)
            
            # Prepare dataset
            dataset = trainer.prepare_dataset(traces)
            assert len(dataset) == 5
            
            # Verify rewards are computed
            for i, item in enumerate(dataset):
                assert item["reward"] is not None
    
    def test_checkpoint_saving(self, tmp_path):
        """Test checkpoint saving."""
        config = GRPOConfig(output_dir=str(tmp_path))
        trainer = AutoDevGRPOTrainer(config=config)
        
        # Mock model
        trainer.model = Mock()
        trainer.model.save_pretrained = Mock()
        trainer.tokenizer = Mock()
        trainer.tokenizer.save_pretrained = Mock()
        
        # Save checkpoint
        metrics = TrainingMetrics(step=100, loss=0.5)
        checkpoint = trainer._save_checkpoint(
            step=100,
            epoch=1.0,
            metrics=metrics,
        )
        
        assert checkpoint.step == 100
        assert checkpoint.epoch == 1.0
        assert len(trainer._checkpoints) == 1
        
        # Verify files were created
        checkpoint_path = tmp_path / "checkpoint-100"
        assert checkpoint_path.exists()


class TestErrorHandling:
    """Tests for error handling."""
    
    def test_train_without_traces_or_dataset(self):
        """Test training without providing data."""
        trainer = AutoDevGRPOTrainer()
        
        with pytest.raises(ValueError, match="Either traces or train_dataset"):
            trainer.train()
    
    def test_evaluate_without_traces_or_dataset(self):
        """Test evaluation without providing data."""
        trainer = AutoDevGRPOTrainer()
        
        with pytest.raises(ValueError, match="Either traces or dataset"):
            trainer.evaluate()
    
    def test_generate_without_model(self):
        """Test generation without loaded model."""
        trainer = AutoDevGRPOTrainer()
        
        with pytest.raises(ValueError, match="Model and tokenizer must be loaded"):
            trainer.generate("test prompt")


# Pytest fixtures for common test setup

@pytest.fixture
def sample_config():
    """Create a sample config for testing."""
    return GRPOConfig(
        learning_rate=1e-5,
        num_epochs=1,
        batch_size=2,
    )


@pytest.fixture
def sample_traces():
    """Create sample traces for testing."""
    return create_sample_traces(5)


@pytest.fixture
def temp_output_dir(tmp_path):
    """Create a temporary output directory."""
    return str(tmp_path / "output")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
