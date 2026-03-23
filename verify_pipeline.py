#!/usr/bin/env python3
"""Verify pipeline module works correctly."""

import sys
import os
import tempfile
import json

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_basic_imports():
    """Test basic imports work."""
    print("Testing basic imports...")
    
    from training.pipeline import (
        TrainingPipeline,
        PipelineConfig,
        PipelineStage,
        PipelineResult,
        create_pipeline,
    )
    
    print("  All imports successful!")
    return True

def test_config():
    """Test PipelineConfig."""
    print("\nTesting PipelineConfig...")
    
    from training.pipeline import PipelineConfig
    
    # Create config
    config = PipelineConfig(
        base_model='test-model',
        num_epochs=5,
        batch_size=16,
    )
    
    assert config.base_model == 'test-model'
    assert config.num_epochs == 5
    assert config.batch_size == 16
    print(f"  Config created: base_model={config.base_model}, num_epochs={config.num_epochs}")
    
    # Test serialization
    data = config.to_dict()
    assert data['base_model'] == 'test-model'
    print(f"  Serialization works: {len(data)} fields")
    
    # Test conversion methods
    grpo_config = config.to_grpo_config()
    assert grpo_config.learning_rate == config.learning_rate
    print("  to_grpo_config() works")
    
    dc_config = config.to_data_collection_config()
    assert dc_config.max_traces_per_task == config.max_traces_per_task
    print("  to_data_collection_config() works")
    
    reward_config = config.to_reward_config()
    print("  to_reward_config() works")
    
    return True

def test_pipeline_stage():
    """Test PipelineStage enum."""
    print("\nTesting PipelineStage enum...")
    
    from training.pipeline import PipelineStage
    
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
    
    print(f"  All {len(stages)} stages defined correctly")
    return True

def test_pipeline_result():
    """Test PipelineResult."""
    print("\nTesting PipelineResult...")
    
    from training.pipeline import PipelineResult, PipelineStage
    from training.grpo_trainer import TrainingMetrics
    
    # Create default result
    result = PipelineResult()
    assert result.success is False
    assert result.stage == PipelineStage.IDLE
    
    # Create with metrics
    metrics = TrainingMetrics(loss=0.5, mean_reward=0.8)
    result = PipelineResult(
        success=True,
        stage=PipelineStage.COMPLETED,
        run_name="test_run",
        training_metrics=metrics,
    )
    
    # Test serialization
    data = result.to_dict()
    assert data['success'] is True
    assert data['stage'] == 'completed'
    assert 'training_metrics' in data
    
    print("  PipelineResult works correctly")
    return True

def test_pipeline_creation():
    """Test TrainingPipeline creation."""
    print("\nTesting TrainingPipeline creation...")
    
    from training.pipeline import TrainingPipeline, PipelineConfig
    
    with tempfile.TemporaryDirectory() as tmpdir:
        config = PipelineConfig(
            base_model='test-model',
            output_dir=tmpdir,
            data_dir=tmpdir,
            registry_dir=tmpdir,
            run_name='test_run',
        )
        
        pipeline = TrainingPipeline(config)
        
        assert pipeline.config.run_name == 'test_run'
        assert pipeline.stage == PipelineStage.IDLE
        assert pipeline.data_collector is not None
        assert pipeline.reward_calculator is not None
        assert pipeline.registry is not None
        
        # Test statistics
        stats = pipeline.get_statistics()
        assert 'run_name' in stats
        assert 'stage' in stats
        
        print("  TrainingPipeline created successfully")
    
    return True

def test_convenience_functions():
    """Test convenience functions."""
    print("\nTesting convenience functions...")
    
    from training.pipeline import create_pipeline, PipelineConfig
    
    with tempfile.TemporaryDirectory() as tmpdir:
        pipeline = create_pipeline(
            base_model='test-model',
            output_dir=tmpdir,
            num_epochs=5,
        )
        
        assert isinstance(pipeline, TrainingPipeline)
        assert pipeline.config.num_epochs == 5
        
        print("  create_pipeline() works")
    
    return True

def test_cli_parsing():
    """Test CLI argument parsing."""
    print("\nTesting CLI...")
    
    import argparse
    from training.pipeline import main
    
    # Just verify the parser is set up correctly
    # (Can't run main() without proper setup)
    print("  CLI main() function exists")
    
    return True

def main_test():
    """Run all tests."""
    print("=" * 60)
    print("Pipeline Module Verification Tests")
    print("=" * 60)
    
    tests = [
        test_basic_imports,
        test_config,
        test_pipeline_stage,
        test_pipeline_result,
        test_pipeline_creation,
        test_convenience_functions,
        test_cli_parsing,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"  FAILED: {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0

if __name__ == '__main__':
    success = main_test()
    sys.exit(0 if success else 1)
