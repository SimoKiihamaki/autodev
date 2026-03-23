"""
Tests for Training Pipeline

Run with: pytest src/training/test_pipeline.py -v
"""

import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from training.pipeline import (
    TrainingPipeline,
    PipelineConfig,
    PipelineStage,
    PipelineResult,
    create_pipeline,
    run_training,
    main,
)
from training.data_collector import (
    ExecutionTrace,
    TraceStep,
    TraceStatus,
    DataCollectionConfig,
    TrainingDataCollector,
)
from training.reward_calculator import (
    RewardCalculator,
    RewardComponents,
    RewardConfig,
)
from training.grpo_trainer import (
    TrainingMetrics,
    TrainingStage,
)
from training.model_registry import (
    ModelRegistry,
    ModelVersion,
    ModelStatus,
    RegistryConfig,
)


class TestPipelineConfig:
    """Tests for PipelineConfig dataclass."""
    
    def test_create_default_config(self):
        """Test creating config with defaults."""
        config = PipelineConfig()
        
        assert config.base_model == "codellama/CodeLlama-7b-hf"
        assert config.num_epochs == 3
        assert config.batch_size == 8
        assert config.use_peft is True
        assert config.auto_register is True
        assert config.auto_promote is False
    
    def test_config_path_expansion(self):
        """Test that paths are expanded."""
        config = PipelineConfig(
            output_dir="~/test_output",
            data_dir="~/test_data",
            registry_dir="~/test_registry",
        )
        
        assert "~" not in config.output_dir
        assert "~" not in config.data_dir
        assert "~" not in config.registry_dir
    
    def test_config_run_name_generation(self):
        """Test that run names are auto-generated."""
        config = PipelineConfig()
        
        assert config.run_name.startswith("run_")
        assert len(config.run_name) > 10
    
    def test_custom_run_name(self):
        """Test custom run name."""
        config = PipelineConfig(run_name="my_custom_run")
        
        assert config.run_name == "my_custom_run"
    
    def test_ref_model_defaults_to_base(self):
        """Test that ref_model defaults to base_model."""
        config = PipelineConfig(base_model="custom/model")
        
        assert config.ref_model == "custom/model"
    
    def test_to_dict(self):
        """Test serialization to dictionary."""
        config = PipelineConfig(
            base_model="test-model",
            num_epochs=5,
        )
        
        data = config.to_dict()
        
        assert data["base_model"] == "test-model"
        assert data["num_epochs"] == 5
    
    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "base_model": "custom-model",
            "num_epochs": 10,
            "batch_size": 16,
        }
        
        config = PipelineConfig.from_dict(data)
        
        assert config.base_model == "custom-model"
        assert config.num_epochs == 10
        assert config.batch_size == 16
    
    def test_to_grpo_config(self):
        """Test conversion to GRPOConfig."""
        config = PipelineConfig(
            learning_rate=2e-5,
            num_epochs=5,
            batch_size=16,
        )
        
        grpo_config = config.to_grpo_config()
        
        assert grpo_config.learning_rate == 2e-5
        assert grpo_config.num_epochs == 5
        assert grpo_config.batch_size == 16
    
    def test_to_data_collection_config(self):
        """Test conversion to DataCollectionConfig."""
        config = PipelineConfig(
            data_dir="~/custom_data",
            max_traces_per_task=20,
        )
        
        dc_config = config.to_data_collection_config()
        
        assert "~" not in dc_config.output_dir  # Expanded
        assert dc_config.max_traces_per_task == 20
    
    def test_invalid_mixed_precision(self):
        """Test that invalid mixed precision is corrected."""
        config = PipelineConfig(mixed_precision="invalid")
        
        assert config.mixed_precision == "fp16"


class TestPipelineResult:
    """Tests for PipelineResult dataclass."""
    
    def test_create_default_result(self):
        """Test creating default result."""
        result = PipelineResult()
        
        assert result.success is False
        assert result.stage == PipelineStage.IDLE
        assert result.traces_collected == 0
        assert result.training_metrics is None
        assert result.eval_metrics is None
    
    def test_result_to_dict(self):
        """Test result serialization."""
        metrics = TrainingMetrics(
            loss=0.5,
            mean_reward=0.8,
        )
        
        result = PipelineResult(
            success=True,
            stage=PipelineStage.COMPLETED,
            run_name="test_run",
            training_metrics=metrics,
        )
        
        data = result.to_dict()
        
        assert data["success"] is True
        assert data["stage"] == "completed"
        assert data["run_name"] == "test_run"
        assert "training_metrics" in data
    
    def test_result_with_error(self):
        """Test result with error."""
        result = PipelineResult(
            success=False,
            stage=PipelineStage.FAILED,
            error="Something went wrong",
        )
        
        data = result.to_dict()
        
        assert data["success"] is False
        assert data["error"] == "Something went wrong"


class TestPipelineStage:
    """Tests for PipelineStage enum."""
    
    def test_all_stages(self):
        """Test all stages exist."""
        stages = [
            PipelineStage.IDLE,
            PipelineStage.COLLECTING,
            PipelineStage.COMPUTING_REWARDS,
            PipelineStage.TRAINING,
            PipelineStage.EVALUATING,
            PipelineStage.REGISTERING,
            PipelineStage.PROMOTING,
            PipelineStage.COMPLETED,
            PipelineStage.FAILED,
        ]
        
        for stage in stages:
            assert stage.value is not None


class TestTrainingPipeline:
    """Tests for TrainingPipeline class."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def config(self, temp_dir):
        """Create a test configuration."""
        return PipelineConfig(
            base_model="test-model",
            output_dir=temp_dir,
            data_dir=temp_dir,
            registry_dir=temp_dir,
            num_epochs=1,
            batch_size=2,
            run_name="test_run",
        )
    
    @pytest.fixture
    def pipeline(self, config):
        """Create a test pipeline."""
        return TrainingPipeline(config)
    
    @pytest.fixture
    def sample_trace(self):
        """Create a sample execution trace."""
        trace = ExecutionTrace(
            trace_id="test_trace_1",
            task_id="test_task_1",
            timestamp=datetime.now(timezone.utc).isoformat(),
            problem_statement="Fix the bug",
            repo_context={"repo": "test/repo"},
            status=TraceStatus.SUCCESS,
            tests_passed=["test_a", "test_b"],
            tests_failed=[],
            reward=0.8,
        )
        trace.prompt = "Fix the bug"
        trace.completion = "Fixed code"
        return trace
    
    def test_pipeline_initialization(self, pipeline, config):
        """Test pipeline initializes correctly."""
        assert pipeline.config.run_name == config.run_name
        assert pipeline.stage == PipelineStage.IDLE
        assert pipeline.data_collector is not None
        assert pipeline.reward_calculator is not None
        assert pipeline.registry is not None
    
    def test_pipeline_with_custom_components(self, temp_dir):
        """Test pipeline with custom components."""
        data_collector = TrainingDataCollector(
            DataCollectionConfig(output_dir=temp_dir)
        )
        reward_calculator = RewardCalculator()
        registry = ModelRegistry(RegistryConfig(base_dir=temp_dir))
        
        config = PipelineConfig(
            output_dir=temp_dir,
            registry_dir=temp_dir,
        )
        
        pipeline = TrainingPipeline(
            config=config,
            data_collector=data_collector,
            reward_calculator=reward_calculator,
            registry=registry,
        )
        
        assert pipeline.data_collector is data_collector
        assert pipeline.reward_calculator is reward_calculator
        assert pipeline.registry is registry
    
    def test_set_stage(self, pipeline):
        """Test stage transitions."""
        pipeline._set_stage(PipelineStage.COLLECTING)
        assert pipeline.stage == PipelineStage.COLLECTING
        
        pipeline._set_stage(PipelineStage.TRAINING)
        assert pipeline.stage == PipelineStage.TRAINING
    
    def test_stage_callback(self, config):
        """Test callbacks are notified on stage change."""
        callback_calls = []
        
        def callback(event, data):
            callback_calls.append((event, data))
        
        pipeline = TrainingPipeline(config, callbacks=[callback])
        pipeline._set_stage(PipelineStage.COLLECTING)
        
        assert len(callback_calls) == 1
        assert callback_calls[0][0] == "stage_change"
        assert callback_calls[0][1]["new_stage"] == "collecting"
    
    def test_split_traces(self, pipeline, sample_trace):
        """Test train/eval split."""
        traces = [sample_trace for _ in range(20)]
        
        train, eval = pipeline.split_traces(traces, eval_ratio=0.2)
        
        assert len(train) == 16
        assert len(eval) == 4
        assert len(pipeline._train_traces) == 16
        assert len(pipeline._eval_traces) == 4
    
    def test_split_traces_empty(self, pipeline):
        """Test split with no traces."""
        train, eval = pipeline.split_traces([])
        
        assert train == []
        assert eval == []
    
    def test_split_traces_min_eval(self, pipeline, sample_trace):
        """Test split respects minimum eval samples."""
        traces = [sample_trace for _ in range(5)]
        
        train, eval = pipeline.split_traces(traces, eval_ratio=0.1)
        
        # Should have at least min_eval_samples
        assert len(eval) >= pipeline.config.min_eval_samples or len(eval) == len(traces)
    
    def test_compute_rewards(self, pipeline, sample_trace):
        """Test reward computation."""
        traces = [sample_trace]
        
        rewards = pipeline.compute_rewards(traces)
        
        assert len(rewards) == 1
        assert isinstance(rewards[0], RewardComponents)
    
    def test_compute_rewards_empty(self, pipeline):
        """Test reward computation with no traces."""
        rewards = pipeline.compute_rewards([])
        
        assert rewards == []
    
    def test_save_and_load_traces(self, pipeline, sample_trace, temp_dir):
        """Test saving and loading traces."""
        traces = [sample_trace]
        
        # Save
        pipeline._save_traces(traces)
        
        # Load
        loaded = pipeline._load_existing_traces()
        
        assert len(loaded) >= 1
        assert loaded[0].trace_id == sample_trace.trace_id
    
    def test_get_statistics(self, pipeline):
        """Test getting pipeline statistics."""
        stats = pipeline.get_statistics()
        
        assert "run_name" in stats
        assert "stage" in stats
        assert "registry_stats" in stats
    
    def test_add_callback(self, pipeline):
        """Test adding callbacks."""
        callback = lambda e, d: None
        
        pipeline.add_callback(callback)
        
        assert callback in pipeline.callbacks
    
    def test_remove_callback(self, pipeline):
        """Test removing callbacks."""
        callback = lambda e, d: None
        
        pipeline.add_callback(callback)
        pipeline.remove_callback(callback)
        
        assert callback not in pipeline.callbacks
    
    def test_load_traces_from_file(self, pipeline, sample_trace, temp_dir):
        """Test loading traces from a file."""
        trace_file = Path(temp_dir) / "traces.json"
        
        with open(trace_file, "w") as f:
            json.dump([sample_trace.to_dict()], f)
        
        traces = pipeline.load_traces(str(trace_file))
        
        assert len(traces) == 1
        assert traces[0].trace_id == sample_trace.trace_id
    
    def test_load_traces_from_directory(self, pipeline, sample_trace, temp_dir):
        """Test loading traces from a directory."""
        traces_dir = Path(temp_dir) / "traces"
        traces_dir.mkdir()
        
        trace_file = traces_dir / "trace1.json"
        with open(trace_file, "w") as f:
            json.dump(sample_trace.to_dict(), f)
        
        traces = pipeline.load_traces(str(traces_dir))
        
        assert len(traces) == 1


class TestTrainingPipelineAsync:
    """Async tests for TrainingPipeline class."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def config(self, temp_dir):
        """Create a test configuration."""
        return PipelineConfig(
            base_model="test-model",
            output_dir=temp_dir,
            data_dir=temp_dir,
            registry_dir=temp_dir,
            num_epochs=1,
            batch_size=2,
            run_name="test_run",
        )
    
    @pytest.fixture
    def pipeline(self, config):
        """Create a test pipeline."""
        return TrainingPipeline(config)
    
    @pytest.mark.asyncio
    async def test_collect_data_default(self, pipeline):
        """Test data collection with default method."""
        traces = await pipeline.collect_data(num_tasks=5)
        
        # Should create synthetic traces
        assert len(traces) > 0
        assert pipeline.stage == PipelineStage.IDLE
    
    @pytest.mark.asyncio
    async def test_collect_data_with_mock_harness(self, pipeline, temp_dir):
        """Test data collection with mock harness."""
        # Create mock trace
        trace = ExecutionTrace(
            trace_id="mock_trace",
            task_id="mock_task",
            timestamp=datetime.now(timezone.utc).isoformat(),
            problem_statement="Test problem",
            status=TraceStatus.SUCCESS,
        )
        
        # Create mock harness
        mock_harness = Mock()
        mock_harness.collect_traces = AsyncMock(return_value=[trace])
        
        traces = await pipeline.collect_data(
            num_tasks=1,
            harness=mock_harness,
        )
        
        assert len(traces) == 1
        assert traces[0].trace_id == "mock_trace"
    
    @pytest.mark.asyncio
    async def test_run_full_pipeline(self, pipeline):
        """Test running the full pipeline."""
        result = await pipeline.run_full_pipeline(
            num_tasks=5,
            save_results=False,
        )
        
        assert result.run_name == pipeline.config.run_name
        assert result.traces_collected > 0
        # Note: Training may fail due to missing model, which is expected
        # in test environment
    
    @pytest.mark.asyncio
    async def test_run_full_pipeline_with_result_save(self, pipeline):
        """Test pipeline saves results."""
        result = await pipeline.run_full_pipeline(
            num_tasks=2,
            save_results=True,
        )
        
        # Check result file was created
        result_file = pipeline.output_path / "pipeline_result.json"
        assert result_file.exists()
        
        with open(result_file) as f:
            saved = json.load(f)
        
        assert saved["run_name"] == result.run_name


class TestTrainingPipelineTraining:
    """Tests for training-related pipeline methods."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def config(self, temp_dir):
        """Create a test configuration."""
        return PipelineConfig(
            base_model="test-model",
            output_dir=temp_dir,
            data_dir=temp_dir,
            registry_dir=temp_dir,
            num_epochs=1,
            batch_size=2,
            run_name="test_run",
        )
    
    @pytest.fixture
    def sample_trace(self):
        """Create a sample execution trace."""
        trace = ExecutionTrace(
            trace_id="test_trace",
            task_id="test_task",
            timestamp=datetime.now(timezone.utc).isoformat(),
            problem_statement="Fix bug",
            status=TraceStatus.SUCCESS,
            tests_passed=["test_a"],
            tests_failed=[],
            reward=0.8,
        )
        trace.prompt = "Fix bug"
        trace.completion = "Fixed"
        return trace
    
    def test_train_no_traces_raises(self, config):
        """Test training without traces raises error."""
        pipeline = TrainingPipeline(config)
        
        with pytest.raises(ValueError, match="No training traces"):
            pipeline.train()
    
    def test_evaluate_no_traces_raises(self, config):
        """Test evaluating without traces raises error."""
        pipeline = TrainingPipeline(config)
        
        with pytest.raises(ValueError, match="No evaluation traces"):
            pipeline.evaluate()
    
    def test_evaluate_no_trainer_raises(self, config):
        """Test evaluating without initialized trainer raises error."""
        pipeline = TrainingPipeline(config)
        
        with pytest.raises(ValueError, match="Trainer not initialized"):
            pipeline.evaluate(traces=[])
    
    @patch('training.pipeline.AutoDevGRPOTrainer')
    def test_register_model(self, mock_trainer_class, config, sample_trace, temp_dir):
        """Test model registration."""
        pipeline = TrainingPipeline(config)
        pipeline._collected_traces = [sample_trace]
        
        # Create a mock model path
        model_path = Path(temp_dir) / "test_model"
        model_path.mkdir()
        (model_path / "config.json").write_text("{}")
        
        version = pipeline.register_model(
            model_path=str(model_path),
            metrics={"accuracy": 0.9},
            tags=["test"],
        )
        
        assert version is not None
        assert version.model_name == config.model_name
        assert "test" in version.tags
        assert pipeline._current_version == version
    
    def test_register_model_no_path_no_trainer(self, config):
        """Test registration fails without model path or trainer."""
        pipeline = TrainingPipeline(config)
        
        with pytest.raises(ValueError, match="No model available"):
            pipeline.register_model()
    
    def test_promote_model_no_version(self, config):
        """Test promotion fails without version."""
        pipeline = TrainingPipeline(config)
        
        with pytest.raises(ValueError, match="No version to promote"):
            pipeline.promote_model()
    
    def test_promote_model_not_found(self, config):
        """Test promotion fails if version not found."""
        pipeline = TrainingPipeline(config)
        
        with pytest.raises(ValueError, match="Version not found"):
            pipeline.promote_model(version_id="nonexistent")
    
    def test_promote_model_threshold_check(self, config, temp_dir):
        """Test promotion respects thresholds."""
        pipeline = TrainingPipeline(config)
        
        # Register a model with low metrics
        model_path = Path(temp_dir) / "low_score_model"
        model_path.mkdir()
        
        version = pipeline.registry.register_model(
            model_path=str(model_path),
            metrics={"swe_bench_score": 0.1, "final_reward": 0.3},
            model_name=config.model_name,
        )
        
        # Try to promote with threshold check
        result = pipeline.promote_model(
            version_id=version.version_id,
            require_threshold=True,
        )
        
        # Should be rejected due to low scores
        assert result is None
    
    def test_promote_model_success(self, config, temp_dir):
        """Test successful promotion."""
        pipeline = TrainingPipeline(config)
        
        # Register a model with high metrics
        model_path = Path(temp_dir) / "high_score_model"
        model_path.mkdir()
        
        version = pipeline.registry.register_model(
            model_path=str(model_path),
            metrics={"swe_bench_score": 0.3, "final_reward": 0.8},
            model_name=config.model_name,
        )
        
        # Promote without threshold check
        result = pipeline.promote_model(
            version_id=version.version_id,
            require_threshold=False,
        )
        
        assert result is not None
        assert result.status == ModelStatus.STAGING
    
    def test_get_best_model(self, config, temp_dir):
        """Test getting best model from registry."""
        pipeline = TrainingPipeline(config)
        
        # Register multiple models
        for i, score in enumerate([0.5, 0.9, 0.7]):
            model_path = Path(temp_dir) / f"model_{i}"
            model_path.mkdir()
            
            pipeline.registry.register_model(
                model_path=str(model_path),
                metrics={"final_reward": score},
                model_name=config.model_name,
            )
        
        best = pipeline.get_best_model(metric="final_reward")
        
        assert best is not None
        assert best.get_metric("final_reward") == 0.9
    
    def test_compare_with_baseline(self, config, temp_dir):
        """Test comparing with baseline."""
        pipeline = TrainingPipeline(config)
        
        # Register two models
        paths = []
        for i, score in enumerate([0.5, 0.8]):
            model_path = Path(temp_dir) / f"compare_model_{i}"
            model_path.mkdir()
            paths.append(model_path)
        
        v1 = pipeline.registry.register_model(
            model_path=str(paths[0]),
            metrics={"accuracy": 0.5},
            model_name=config.model_name,
        )
        
        v2 = pipeline.registry.register_model(
            model_path=str(paths[1]),
            metrics={"accuracy": 0.8},
            model_name=config.model_name,
        )
        
        comparison = pipeline.compare_with_baseline(
            version_id=v2.version_id,
            baseline_id=v1.version_id,
        )
        
        assert "metrics" in comparison
        assert "differences" in comparison


class TestConvenienceFunctions:
    """Tests for convenience functions."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    def test_create_pipeline(self, temp_dir):
        """Test create_pipeline function."""
        pipeline = create_pipeline(
            base_model="test-model",
            output_dir=temp_dir,
            num_epochs=5,
        )
        
        assert isinstance(pipeline, TrainingPipeline)
        assert pipeline.config.base_model == "test-model"
        assert pipeline.config.num_epochs == 5
    
    @pytest.mark.asyncio
    async def test_run_training(self, temp_dir):
        """Test run_training function."""
        result = await run_training(
            base_model="test-model",
            num_tasks=2,
            output_dir=temp_dir,
            num_epochs=1,
        )
        
        assert isinstance(result, PipelineResult)
        assert result.run_name is not None


class TestCLI:
    """Tests for CLI entry point."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    def test_cli_dry_run(self, temp_dir, capsys):
        """Test CLI dry run mode."""
        with patch('sys.argv', [
            'pipeline.py',
            '--base-model', 'test-model',
            '--output-dir', temp_dir,
            '--dry-run',
        ]):
            result = main()
            
            assert result == 0
            
            captured = capsys.readouterr()
            assert "Configuration" in captured.out
            assert "test-model" in captured.out
    
    def test_cli_custom_args(self, temp_dir):
        """Test CLI with custom arguments."""
        with patch('sys.argv', [
            'pipeline.py',
            '--base-model', 'custom-model',
            '--output-dir', temp_dir,
            '--registry-dir', temp_dir,
            '--num-epochs', '5',
            '--batch-size', '16',
            '--learning-rate', '0.0001',
            '--no-peft',
            '--no-register',
            '--dry-run',
        ]):
            result = main()
            
            assert result == 0
    
    def test_cli_verbose(self, temp_dir):
        """Test CLI verbose mode."""
        with patch('sys.argv', [
            'pipeline.py',
            '--output-dir', temp_dir,
            '--verbose',
            '--dry-run',
        ]):
            result = main()
            
            assert result == 0


class TestIntegration:
    """Integration tests for the full pipeline."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def config(self, temp_dir):
        """Create a test configuration."""
        return PipelineConfig(
            base_model="test-model",
            output_dir=temp_dir,
            data_dir=temp_dir,
            registry_dir=temp_dir,
            num_epochs=1,
            batch_size=2,
            run_name="integration_test",
            auto_register=True,
            auto_promote=False,
        )
    
    @pytest.mark.asyncio
    async def test_end_to_end_workflow(self, config):
        """Test complete workflow from data to registration."""
        pipeline = TrainingPipeline(config)
        
        # 1. Collect data
        traces = await pipeline.collect_data(num_tasks=3)
        assert len(traces) > 0
        assert pipeline.stage == PipelineStage.IDLE
        
        # 2. Compute rewards
        rewards = pipeline.compute_rewards(traces)
        assert len(rewards) == len(traces)
        
        # 3. Split traces
        train, eval = pipeline.split_traces(traces)
        assert len(train) + len(eval) == len(traces)
        
        # 4. Check statistics
        stats = pipeline.get_statistics()
        assert stats["collected_traces"] == len(traces)
    
    def test_pipeline_persistence(self, config):
        """Test pipeline state persistence."""
        pipeline1 = TrainingPipeline(config)
        
        # Create and save traces
        trace = ExecutionTrace(
            trace_id="persist_test",
            task_id="persist_task",
            timestamp=datetime.now(timezone.utc).isoformat(),
            problem_statement="Test persistence",
            status=TraceStatus.SUCCESS,
        )
        pipeline1._collected_traces = [trace]
        pipeline1._save_traces([trace])
        
        # Create new pipeline and load
        pipeline2 = TrainingPipeline(config)
        loaded = pipeline2._load_existing_traces()
        
        assert len(loaded) >= 1


class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def config(self, temp_dir):
        """Create a test configuration."""
        return PipelineConfig(
            base_model="test-model",
            output_dir=temp_dir,
            data_dir=temp_dir,
            registry_dir=temp_dir,
            run_name="edge_test",
        )
    
    def test_empty_traces_operations(self, config):
        """Test operations with empty traces."""
        pipeline = TrainingPipeline(config)
        
        # These should not raise
        rewards = pipeline.compute_rewards([])
        assert rewards == []
        
        train, eval = pipeline.split_traces([])
        assert train == []
        assert eval == []
    
    def test_callback_exception_handling(self, config):
        """Test that callback exceptions don't break pipeline."""
        def bad_callback(event, data):
            raise RuntimeError("Callback error")
        
        pipeline = TrainingPipeline(config, callbacks=[bad_callback])
        
        # Should not raise
        pipeline._set_stage(PipelineStage.TRAINING)
        assert pipeline.stage == PipelineStage.TRAINING
    
    def test_load_invalid_trace_file(self, config, temp_dir):
        """Test loading invalid trace file."""
        pipeline = TrainingPipeline(config)
        
        # Create invalid JSON file
        invalid_file = Path(temp_dir) / "traces" / "invalid.json"
        invalid_file.parent.mkdir(exist_ok=True)
        invalid_file.write_text("not valid json")
        
        # Should not raise, just log warning
        traces = pipeline._load_existing_traces()
        assert isinstance(traces, list)
    
    @pytest.mark.asyncio
    async def test_collect_data_exception(self, config):
        """Test data collection exception handling."""
        pipeline = TrainingPipeline(config)
        
        # Create mock harness that raises
        mock_harness = Mock()
        mock_harness.collect_traces = AsyncMock(side_effect=RuntimeError("Harness error"))
        
        with pytest.raises(RuntimeError, match="Harness error"):
            await pipeline.collect_data(harness=mock_harness)
        
        assert pipeline.stage == PipelineStage.FAILED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
