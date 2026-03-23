"""
Tests for Model Registry

Run with: pytest src/training/test_model_registry.py -v
"""

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
import pytest
import shutil

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from training.model_registry import (
    ModelRegistry,
    ModelVersion,
    ModelStatus,
    RegistryConfig,
    create_registry,
)


class TestModelStatus:
    """Tests for ModelStatus enum."""
    
    def test_status_values(self):
        """Test status enum values."""
        assert ModelStatus.EXPERIMENTAL.value == "experimental"
        assert ModelStatus.STAGING.value == "staging"
        assert ModelStatus.PRODUCTION.value == "production"
        assert ModelStatus.DEPRECATED.value == "deprecated"
        assert ModelStatus.ARCHIVED.value == "archived"


class TestModelVersion:
    """Tests for ModelVersion dataclass."""
    
    def test_create_model_version(self):
        """Test creating a model version."""
        version = ModelVersion(
            version_id="test_model_20260323_120000_abc123",
            model_name="test-model",
            version_number="v1.0.0",
            created_at="2026-03-23T12:00:00",
            model_path="/models/test_model",
            metrics={"accuracy": 0.85, "swe_bench_score": 0.25},
            metadata={"base_model": "codellama-7b"},
            status=ModelStatus.EXPERIMENTAL,
            tags=["baseline", "codellama"]
        )
        
        assert version.version_id == "test_model_20260323_120000_abc123"
        assert version.model_name == "test-model"
        assert version.metrics["accuracy"] == 0.85
        assert version.status == ModelStatus.EXPERIMENTAL
        assert "baseline" in version.tags
    
    def test_version_serialization(self):
        """Test serializing and deserializing a version."""
        version = ModelVersion(
            version_id="test-v1",
            model_name="test",
            version_number="v1.0.0",
            created_at="2026-03-23T12:00:00",
            model_path="/models/test",
            metrics={"score": 0.9},
            status=ModelStatus.PRODUCTION
        )
        
        data = version.to_dict()
        assert data["version_id"] == "test-v1"
        assert data["status"] == "production"
        
        restored = ModelVersion.from_dict(data)
        assert restored.version_id == version.version_id
        assert restored.status == ModelStatus.PRODUCTION
        assert restored.metrics["score"] == 0.9
    
    def test_version_from_dict_string_status(self):
        """Test creating version from dict with string status."""
        data = {
            "version_id": "test-v1",
            "model_name": "test",
            "version_number": "v1.0.0",
            "created_at": "2026-03-23T12:00:00",
            "model_path": "/models/test",
            "status": "staging"
        }
        
        version = ModelVersion.from_dict(data)
        assert version.status == ModelStatus.STAGING
    
    def test_get_metric(self):
        """Test getting metric values."""
        version = ModelVersion(
            version_id="test-v1",
            model_name="test",
            version_number="v1.0.0",
            created_at="2026-03-23T12:00:00",
            model_path="/models/test",
            metrics={"accuracy": 0.85}
        )
        
        assert version.get_metric("accuracy") == 0.85
        assert version.get_metric("nonexistent") == 0.0
        assert version.get_metric("nonexistent", default=-1.0) == -1.0
    
    def test_matches_tags(self):
        """Test tag matching."""
        version = ModelVersion(
            version_id="test-v1",
            model_name="test",
            version_number="v1.0.0",
            created_at="2026-03-23T12:00:00",
            model_path="/models/test",
            tags=["baseline", "codellama", "7b"]
        )
        
        # Any match
        assert version.matches_tags(["baseline"]) == True
        assert version.matches_tags(["baseline", "other"]) == True
        assert version.matches_tags(["other"]) == False
        
        # Require all
        assert version.matches_tags(["baseline", "codellama"], require_all=True) == True
        assert version.matches_tags(["baseline", "other"], require_all=True) == False
    
    def test_is_better_than(self):
        """Test version comparison."""
        v1 = ModelVersion(
            version_id="v1",
            model_name="test",
            version_number="v1.0.0",
            created_at="2026-03-23T12:00:00",
            model_path="/models/v1",
            metrics={"score": 0.8}
        )
        
        v2 = ModelVersion(
            version_id="v2",
            model_name="test",
            version_number="v1.1.0",
            created_at="2026-03-23T13:00:00",
            model_path="/models/v2",
            metrics={"score": 0.9}
        )
        
        # Higher is better
        assert v2.is_better_than(v1, "score", higher_is_better=True) == True
        assert v1.is_better_than(v2, "score", higher_is_better=True) == False
        
        # Lower is better
        assert v1.is_better_than(v2, "score", higher_is_better=False) == True
        assert v2.is_better_than(v1, "score", higher_is_better=False) == False


class TestRegistryConfig:
    """Tests for RegistryConfig."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = RegistryConfig()
        
        assert config.max_versions == 50
        assert config.auto_archive == True
        assert config.compress_models == False
        assert config.metadata_file == "registry_metadata.json"
    
    def test_path_expansion(self):
        """Test that base_dir path is expanded."""
        config = RegistryConfig(base_dir="~/test_registry")
        
        assert "~" not in config.base_dir
        assert config.base_dir.endswith("test_registry")


class TestModelRegistry:
    """Tests for ModelRegistry."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def registry(self, temp_dir):
        """Create a registry with temp directory."""
        config = RegistryConfig(
            base_dir=temp_dir,
            max_versions=10
        )
        return ModelRegistry(config)
    
    @pytest.fixture
    def sample_model_path(self, temp_dir):
        """Create a sample model directory for testing."""
        model_path = Path(temp_dir) / "sample_model"
        model_path.mkdir()
        
        # Create some mock model files
        (model_path / "config.json").write_text('{"model_type": "test"}')
        (model_path / "model.safetensors").write_text("mock weights")
        (model_path / "tokenizer.json").write_text("{}")
        
        return str(model_path)
    
    def test_registry_initialization(self, registry, temp_dir):
        """Test registry initialization."""
        assert registry.base_path == Path(temp_dir)
        assert registry.models_path.exists()
        assert registry.archived_path.exists()
    
    def test_register_model(self, registry, sample_model_path):
        """Test registering a model."""
        version = registry.register_model(
            model_path=sample_model_path,
            metrics={"accuracy": 0.85, "swe_bench_score": 0.25},
            metadata={"base_model": "codellama-7b"},
            model_name="autodev-v1",
            tags=["baseline"],
            description="Initial model"
        )
        
        assert version.version_id.startswith("autodev-v1_")
        assert version.model_name == "autodev-v1"
        assert version.metrics["accuracy"] == 0.85
        assert version.status == ModelStatus.EXPERIMENTAL
        assert "baseline" in version.tags
        assert version.description == "Initial model"
    
    def test_register_model_auto_version(self, registry, sample_model_path):
        """Test automatic version number generation."""
        v1 = registry.register_model(
            model_path=sample_model_path,
            model_name="test-model",
            version_number="v1.0.0"
        )
        
        v2 = registry.register_model(
            model_path=sample_model_path,
            model_name="test-model"
        )
        
        assert v1.version_number == "v1.0.0"
        assert v2.version_number == "v1.1.0"
    
    def test_register_model_without_copy(self, temp_dir, sample_model_path):
        """Test registering without copying model."""
        config = RegistryConfig(base_dir=temp_dir)
        registry = ModelRegistry(config)
        
        version = registry.register_model(
            model_path=sample_model_path,
            model_name="test",
            copy_model=False
        )
        
        # Model path should point to original
        assert version.model_path == sample_model_path
    
    def test_get_version(self, registry, sample_model_path):
        """Test getting a version by ID."""
        registered = registry.register_model(
            model_path=sample_model_path,
            model_name="test-model"
        )
        
        retrieved = registry.get_version(registered.version_id)
        
        assert retrieved is not None
        assert retrieved.version_id == registered.version_id
    
    def test_get_version_not_found(self, registry):
        """Test getting a non-existent version."""
        result = registry.get_version("nonexistent")
        assert result is None
    
    def test_list_versions(self, registry, sample_model_path):
        """Test listing versions."""
        # Register multiple versions
        for i in range(3):
            registry.register_model(
                model_path=sample_model_path,
                model_name=f"model-{i % 2}",  # model-0, model-1, model-0
                metrics={"score": 0.5 + i * 0.1}
            )
        
        # List all
        all_versions = registry.list_versions()
        assert len(all_versions) == 3
        
        # List by model name
        model_0 = registry.list_versions(model_name="model-0")
        assert len(model_0) == 2
        
        model_1 = registry.list_versions(model_name="model-1")
        assert len(model_1) == 1
    
    def test_list_versions_with_filters(self, registry, sample_model_path):
        """Test listing versions with filters."""
        # Register versions with different statuses and tags
        registry.register_model(
            model_path=sample_model_path,
            model_name="test",
            metrics={"score": 0.9},
            tags=["production", "stable"],
            status=ModelStatus.PRODUCTION
        )
        
        registry.register_model(
            model_path=sample_model_path,
            model_name="test",
            metrics={"score": 0.7},
            tags=["experimental"],
            status=ModelStatus.EXPERIMENTAL
        )
        
        # Filter by status
        prod_versions = registry.list_versions(status=ModelStatus.PRODUCTION)
        assert len(prod_versions) == 1
        
        # Filter by tags
        tagged = registry.list_versions(tags=["stable"])
        assert len(tagged) == 1
        
        # Filter by min metric
        high_score = registry.list_versions(min_metric={"score": 0.8})
        assert len(high_score) == 1
    
    def test_get_best_model(self, registry, sample_model_path):
        """Test getting the best model by metric."""
        # Register models with different scores
        registry.register_model(
            model_path=sample_model_path,
            model_name="test",
            metrics={"swe_bench_score": 0.20}
        )
        
        registry.register_model(
            model_path=sample_model_path,
            model_name="test",
            metrics={"swe_bench_score": 0.28}
        )
        
        registry.register_model(
            model_path=sample_model_path,
            model_name="test",
            metrics={"swe_bench_score": 0.15}
        )
        
        # Get best by swe_bench_score
        best = registry.get_best_model("swe_bench_score", model_name="test")
        
        assert best is not None
        assert best.get_metric("swe_bench_score") == 0.28
    
    def test_get_best_model_lower_is_better(self, registry, sample_model_path):
        """Test getting best model when lower is better."""
        registry.register_model(
            model_path=sample_model_path,
            model_name="test",
            metrics={"loss": 0.5}
        )
        
        registry.register_model(
            model_path=sample_model_path,
            model_name="test",
            metrics={"loss": 0.2}
        )
        
        best = registry.get_best_model("loss", higher_is_better=False)
        
        assert best.get_metric("loss") == 0.2
    
    def test_get_best_model_no_candidates(self, registry):
        """Test getting best model when no candidates match."""
        best = registry.get_best_model("nonexistent_metric")
        assert best is None
    
    def test_load_model(self, registry, sample_model_path):
        """Test loading a model checkpoint."""
        version = registry.register_model(
            model_path=sample_model_path,
            model_name="test"
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            loaded_path = registry.load_model(
                version.version_id,
                os.path.join(tmpdir, "loaded_model")
            )
            
            assert loaded_path.exists()
            assert (loaded_path / "config.json").exists()
            assert (loaded_path / "model.safetensors").exists()
    
    def test_load_model_overwrite(self, registry, sample_model_path):
        """Test loading model with overwrite."""
        version = registry.register_model(
            model_path=sample_model_path,
            model_name="test"
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, "loaded_model")
            
            # First load
            registry.load_model(version.version_id, target)
            
            # Second load should fail without overwrite
            with pytest.raises(FileExistsError):
                registry.load_model(version.version_id, target, overwrite=False)
            
            # Should succeed with overwrite
            registry.load_model(version.version_id, target, overwrite=True)
    
    def test_load_model_not_found(self, registry):
        """Test loading a non-existent version."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError):
                registry.load_model("nonexistent", os.path.join(tmpdir, "model"))
    
    def test_update_metrics(self, registry, sample_model_path):
        """Test updating metrics."""
        version = registry.register_model(
            model_path=sample_model_path,
            model_name="test",
            metrics={"accuracy": 0.8}
        )
        
        # Update with merge
        updated = registry.update_metrics(
            version.version_id,
            {"accuracy": 0.9, "new_metric": 0.5}
        )
        
        assert updated.metrics["accuracy"] == 0.9
        assert updated.metrics["new_metric"] == 0.5
    
    def test_update_metrics_replace(self, registry, sample_model_path):
        """Test updating metrics without merge."""
        version = registry.register_model(
            model_path=sample_model_path,
            model_name="test",
            metrics={"accuracy": 0.8, "old_metric": 0.5}
        )
        
        # Update without merge
        updated = registry.update_metrics(
            version.version_id,
            {"new_metric": 0.9},
            merge=False
        )
        
        assert "old_metric" not in updated.metrics
        assert updated.metrics["new_metric"] == 0.9
    
    def test_update_status(self, registry, sample_model_path):
        """Test updating version status."""
        version = registry.register_model(
            model_path=sample_model_path,
            model_name="test"
        )
        
        assert version.status == ModelStatus.EXPERIMENTAL
        
        updated = registry.update_status(
            version.version_id,
            ModelStatus.PRODUCTION
        )
        
        assert updated.status == ModelStatus.PRODUCTION
    
    def test_promote_version(self, registry, sample_model_path):
        """Test promoting a version."""
        version = registry.register_model(
            model_path=sample_model_path,
            model_name="test"
        )
        
        promoted = registry.promote_version(
            version.version_id,
            ModelStatus.STAGING
        )
        
        assert promoted.status == ModelStatus.STAGING
    
    def test_archive_version(self, registry, sample_model_path):
        """Test archiving a version."""
        version = registry.register_model(
            model_path=sample_model_path,
            model_name="test"
        )
        
        result = registry.archive_version(version.version_id)
        
        assert result == True
        
        archived = registry.get_version(version.version_id)
        assert archived.status == ModelStatus.ARCHIVED
        assert "archived" in archived.model_path
    
    def test_delete_version(self, registry, sample_model_path):
        """Test deleting a version."""
        version = registry.register_model(
            model_path=sample_model_path,
            model_name="test"
        )
        
        result = registry.delete_version(version.version_id)
        
        assert result == True
        assert registry.get_version(version.version_id) is None
    
    def test_compare_versions(self, registry, sample_model_path):
        """Test comparing two versions."""
        v1 = registry.register_model(
            model_path=sample_model_path,
            model_name="test",
            metrics={"accuracy": 0.8, "loss": 0.3}
        )
        
        v2 = registry.register_model(
            model_path=sample_model_path,
            model_name="test",
            metrics={"accuracy": 0.9, "loss": 0.2}
        )
        
        comparison = registry.compare_versions(v1.version_id, v2.version_id)
        
        assert comparison["version_1"] == v1.version_id
        assert comparison["version_2"] == v2.version_id
        
        # Check metrics comparison
        assert comparison["metrics"]["accuracy"]["version_1"] == 0.8
        assert comparison["metrics"]["accuracy"]["version_2"] == 0.9
        
        # Check differences
        assert comparison["differences"]["accuracy"] == 0.1
        assert comparison["differences"]["loss"] == -0.1
        
        # Check winner
        assert comparison["winner"]["accuracy"] == v2.version_id
    
    def test_compare_versions_not_found(self, registry, sample_model_path):
        """Test comparing with non-existent version."""
        v1 = registry.register_model(
            model_path=sample_model_path,
            model_name="test"
        )
        
        with pytest.raises(ValueError):
            registry.compare_versions(v1.version_id, "nonexistent")
    
    def test_get_lineage(self, registry, sample_model_path):
        """Test getting model lineage."""
        # Create a lineage: grandparent -> parent -> child
        grandparent = registry.register_model(
            model_path=sample_model_path,
            model_name="test"
        )
        
        parent = registry.register_model(
            model_path=sample_model_path,
            model_name="test",
            parent_version=grandparent.version_id
        )
        
        child = registry.register_model(
            model_path=sample_model_path,
            model_name="test",
            parent_version=parent.version_id
        )
        
        lineage = registry.get_lineage(child.version_id)
        
        assert len(lineage) == 3
        assert lineage[0].version_id == grandparent.version_id
        assert lineage[1].version_id == parent.version_id
        assert lineage[2].version_id == child.version_id
    
    def test_get_statistics(self, registry, sample_model_path):
        """Test getting registry statistics."""
        # Register some models
        registry.register_model(
            model_path=sample_model_path,
            model_name="model-a",
            metrics={"accuracy": 0.8, "score": 0.5},
            status=ModelStatus.PRODUCTION
        )
        
        registry.register_model(
            model_path=sample_model_path,
            model_name="model-a",
            metrics={"accuracy": 0.9, "score": 0.6},
            status=ModelStatus.EXPERIMENTAL
        )
        
        registry.register_model(
            model_path=sample_model_path,
            model_name="model-b",
            metrics={"accuracy": 0.7},
            status=ModelStatus.EXPERIMENTAL
        )
        
        stats = registry.get_statistics()
        
        assert stats["total_versions"] == 3
        assert "model-a" in stats["model_names"]
        assert "model-b" in stats["model_names"]
        assert stats["versions_per_model"]["model-a"] == 2
        assert stats["versions_per_model"]["model-b"] == 1
        assert stats["status_counts"]["production"] == 1
        assert stats["status_counts"]["experimental"] == 2
    
    def test_version_limit(self, sample_model_path):
        """Test version limit enforcement."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = RegistryConfig(
                base_dir=tmpdir,
                max_versions=3,
                auto_archive=False
            )
            registry = ModelRegistry(config)
            
            # Register 5 versions
            for i in range(5):
                registry.register_model(
                    model_path=sample_model_path,
                    model_name="test"
                )
            
            # Should only have 3 versions
            versions = registry.list_versions(model_name="test")
            assert len(versions) == 3
    
    def test_metadata_persistence(self, temp_dir, sample_model_path):
        """Test that metadata persists across registry instances."""
        config = RegistryConfig(base_dir=temp_dir)
        
        # Create registry and register model
        registry1 = ModelRegistry(config)
        version = registry1.register_model(
            model_path=sample_model_path,
            model_name="test",
            metrics={"score": 0.9}
        )
        
        # Create new registry instance
        registry2 = ModelRegistry(config)
        
        # Should load the version
        loaded = registry2.get_version(version.version_id)
        assert loaded is not None
        assert loaded.metrics["score"] == 0.9
    
    def test_list_versions_limit(self, registry, sample_model_path):
        """Test limit parameter in list_versions."""
        for i in range(10):
            registry.register_model(
                model_path=sample_model_path,
                model_name="test"
            )
        
        # List with limit
        versions = registry.list_versions(limit=5)
        assert len(versions) == 5


class TestCreateRegistry:
    """Tests for the factory function."""
    
    def test_create_registry(self):
        """Test creating registry with factory function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = create_registry(base_dir=tmpdir, max_versions=20)
            
            assert registry.config.max_versions == 20
            assert registry.base_path == Path(tmpdir)


class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def registry(self, temp_dir):
        """Create a registry with temp directory."""
        config = RegistryConfig(base_dir=temp_dir)
        return ModelRegistry(config)
    
    def test_register_nonexistent_model(self, registry):
        """Test registering a model that doesn't exist."""
        with pytest.raises(ValueError):
            registry.register_model(
                model_path="/nonexistent/path",
                model_name="test"
            )
    
    def test_update_nonexistent_version(self, registry):
        """Test updating a non-existent version."""
        result = registry.update_metrics("nonexistent", {"score": 0.5})
        assert result is None
        
        result = registry.update_status("nonexistent", ModelStatus.PRODUCTION)
        assert result is None
    
    def test_archive_nonexistent_version(self, registry):
        """Test archiving a non-existent version."""
        result = registry.archive_version("nonexistent")
        assert result == False
    
    def test_delete_nonexistent_version(self, registry):
        """Test deleting a non-existent version."""
        result = registry.delete_version("nonexistent")
        assert result == False
    
    def test_empty_tags_filter(self, registry, temp_dir):
        """Test listing with empty tags filter."""
        # Create sample model
        model_path = Path(temp_dir) / "model"
        model_path.mkdir()
        (model_path / "config.json").write_text("{}")
        
        registry.register_model(
            model_path=str(model_path),
            model_name="test",
            tags=["tag1"]
        )
        
        # Empty tags should match all
        versions = registry.list_versions(tags=[])
        assert len(versions) == 1
    
    def test_version_with_missing_metric_comparison(self, registry, temp_dir):
        """Test comparing versions when one is missing a metric."""
        model_path = Path(temp_dir) / "model"
        model_path.mkdir()
        (model_path / "config.json").write_text("{}")
        
        v1 = registry.register_model(
            model_path=str(model_path),
            model_name="test",
            metrics={"accuracy": 0.8}
        )
        
        v2 = registry.register_model(
            model_path=str(model_path),
            model_name="test",
            metrics={"accuracy": 0.9, "extra_metric": 0.5}
        )
        
        comparison = registry.compare_versions(v1.version_id, v2.version_id)
        
        # v1 should have 0.0 for extra_metric
        assert comparison["metrics"]["extra_metric"]["version_1"] == 0.0
        assert comparison["metrics"]["extra_metric"]["version_2"] == 0.5
    
    def test_get_best_model_with_tie(self, registry, temp_dir):
        """Test getting best model when there's a tie."""
        model_path = Path(temp_dir) / "model"
        model_path.mkdir()
        (model_path / "config.json").write_text("{}")
        
        registry.register_model(
            model_path=str(model_path),
            model_name="test",
            metrics={"score": 0.9}
        )
        
        registry.register_model(
            model_path=str(model_path),
            model_name="test",
            metrics={"score": 0.9}
        )
        
        # Should return one of them (newest)
        best = registry.get_best_model("score")
        assert best.get_metric("score") == 0.9
