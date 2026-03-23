"""
Model Registry for AutoDev RL Training

This module provides model version management for reinforcement learning training.
It handles:
- Model checkpoint saving and loading
- Version tracking with metadata
- Model comparison by metrics
- Best model selection

Usage:
    from training.model_registry import ModelRegistry, ModelVersion
    
    registry = ModelRegistry(base_dir="~/.autodev/models")
    
    # Register a new model version
    version = registry.register_model(
        model_path="./checkpoints/model_v1",
        metrics={"accuracy": 0.85, "swe_bench_score": 0.25},
        metadata={"training_steps": 10000, "base_model": "codellama-7b"}
    )
    
    # Get the best model by a metric
    best = registry.get_best_model(metric="swe_bench_score")
    
    # Load a model checkpoint
    registry.load_model(version.version_id, target_path="./loaded_model")
"""

import json
import logging
import os
import shutil
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from enum import Enum

logger = logging.getLogger(__name__)


class ModelStatus(Enum):
    """Status of a model version."""
    EXPERIMENTAL = "experimental"  # Work in progress
    STAGING = "staging"  # Ready for testing
    PRODUCTION = "production"  # Deployed to production
    DEPRECATED = "deprecated"  # No longer recommended
    ARCHIVED = "archived"  # Archived for reference


@dataclass
class ModelVersion:
    """
    Represents a versioned model with metadata.
    
    Attributes:
        version_id: Unique identifier for this version
        model_name: Base model name
        version_number: Semantic version or iteration number
        created_at: ISO timestamp of creation
        model_path: Path to the model checkpoint
        metrics: Performance metrics (accuracy, swe_bench_score, etc.)
        metadata: Additional metadata (training config, base model, etc.)
        status: Current status of the model
        tags: Tags for categorization
        parent_version: ID of the parent model (for incremental training)
        description: Human-readable description
    """
    version_id: str
    model_name: str
    version_number: str
    created_at: str
    model_path: str
    metrics: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: ModelStatus = ModelStatus.EXPERIMENTAL
    tags: List[str] = field(default_factory=list)
    parent_version: Optional[str] = None
    description: str = ""
    
    def __post_init__(self):
        """Convert status string to enum if needed."""
        if isinstance(self.status, str):
            self.status = ModelStatus(self.status)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        data["status"] = self.status.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelVersion":
        """Create from dictionary."""
        if isinstance(data.get("status"), str):
            data["status"] = ModelStatus(data["status"])
        return cls(**data)
    
    def get_metric(self, metric_name: str, default: float = 0.0) -> float:
        """Get a specific metric value."""
        return self.metrics.get(metric_name, default)
    
    def matches_tags(self, tags: List[str], require_all: bool = False) -> bool:
        """Check if this version matches the given tags."""
        if not tags:
            return True
        if require_all:
            return all(tag in self.tags for tag in tags)
        return any(tag in self.tags for tag in tags)
    
    def is_better_than(self, other: "ModelVersion", metric: str, higher_is_better: bool = True) -> bool:
        """Compare this version with another based on a metric."""
        self_value = self.get_metric(metric)
        other_value = other.get_metric(metric)
        
        if higher_is_better:
            return self_value > other_value
        return self_value < other_value


@dataclass
class RegistryConfig:
    """
    Configuration for the model registry.
    
    Attributes:
        base_dir: Base directory for storing model versions
        max_versions: Maximum number of versions to keep (0 = unlimited)
        auto_archive: Automatically archive old versions
        compress_models: Whether to compress model checkpoints
        metadata_file: Name of the metadata file
    """
    base_dir: str = "~/.autodev/model_registry"
    max_versions: int = 50
    auto_archive: bool = True
    compress_models: bool = False
    metadata_file: str = "registry_metadata.json"
    
    def __post_init__(self):
        """Expand base directory path."""
        self.base_dir = os.path.expanduser(self.base_dir)


class ModelRegistry:
    """
    Registry for managing model versions.
    
    Provides:
    - Model version registration and tracking
    - Checkpoint saving and loading
    - Best model selection by metric
    - Version comparison and promotion
    
    Example:
        registry = ModelRegistry(RegistryConfig(
            base_dir="~/.autodev/models",
            max_versions=20
        ))
        
        # Register a trained model
        version = registry.register_model(
            model_path="./output/checkpoint-1000",
            metrics={"swe_bench_score": 0.28, "pass_rate": 0.85},
            metadata={"base_model": "codellama-7b", "lr": 1e-5}
        )
        
        # Get the best model
        best = registry.get_best_model("swe_bench_score")
        print(f"Best model: {best.version_id} with score {best.get_metric('swe_bench_score')}")
        
        # Load the best model
        registry.load_model(best.version_id, "./production_model")
    """
    
    def __init__(self, config: Optional[RegistryConfig] = None):
        """
        Initialize the model registry.
        
        Args:
            config: Registry configuration. Uses defaults if not provided.
        """
        self.config = config or RegistryConfig()
        self._versions: Dict[str, ModelVersion] = {}
        
        # Ensure directory structure exists
        self.base_path = Path(self.config.base_dir)
        self.models_path = self.base_path / "models"
        self.archived_path = self.base_path / "archived"
        
        self._ensure_directories()
        self._load_metadata()
        
        logger.info(f"ModelRegistry initialized with {len(self._versions)} versions")
    
    def _ensure_directories(self) -> None:
        """Create necessary directories."""
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.models_path.mkdir(parents=True, exist_ok=True)
        self.archived_path.mkdir(parents=True, exist_ok=True)
    
    def _load_metadata(self) -> None:
        """Load registry metadata from disk."""
        metadata_path = self.base_path / self.config.metadata_file
        
        if metadata_path.exists():
            try:
                with open(metadata_path, "r") as f:
                    data = json.load(f)
                
                for version_data in data.get("versions", []):
                    try:
                        version = ModelVersion.from_dict(version_data)
                        self._versions[version.version_id] = version
                    except Exception as e:
                        logger.warning(f"Failed to load version: {e}")
                
                logger.info(f"Loaded {len(self._versions)} model versions from metadata")
            except Exception as e:
                logger.error(f"Failed to load registry metadata: {e}")
    
    def _save_metadata(self) -> None:
        """Save registry metadata to disk."""
        metadata_path = self.base_path / self.config.metadata_file
        
        data = {
            "versions": [v.to_dict() for v in self._versions.values()],
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "total_versions": len(self._versions)
        }
        
        with open(metadata_path, "w") as f:
            json.dump(data, f, indent=2)
    
    def register_model(
        self,
        model_path: str,
        metrics: Optional[Dict[str, float]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        model_name: str = "autodev-model",
        version_number: Optional[str] = None,
        tags: Optional[List[str]] = None,
        parent_version: Optional[str] = None,
        description: str = "",
        status: ModelStatus = ModelStatus.EXPERIMENTAL,
        copy_model: bool = True
    ) -> ModelVersion:
        """
        Register a new model version.
        
        Args:
            model_path: Path to the model checkpoint
            metrics: Performance metrics for this version
            metadata: Additional metadata
            model_name: Base model name
            version_number: Version number (auto-generated if not provided)
            tags: Tags for categorization
            parent_version: ID of the parent model
            description: Human-readable description
            status: Initial status
            copy_model: Whether to copy the model to registry storage
            
        Returns:
            The registered ModelVersion
        """
        # Generate version ID and number
        version_id = self._generate_version_id(model_name)
        if version_number is None:
            version_number = self._generate_version_number(model_name)
        
        # Determine storage path
        storage_path = self.models_path / version_id
        
        # Copy or reference model
        final_model_path = model_path
        if copy_model:
            final_model_path = str(storage_path)
            self._copy_model(model_path, storage_path)
        
        # Create version record
        version = ModelVersion(
            version_id=version_id,
            model_name=model_name,
            version_number=version_number,
            created_at=datetime.now(timezone.utc).isoformat(),
            model_path=final_model_path,
            metrics=metrics or {},
            metadata=metadata or {},
            status=status,
            tags=tags or [],
            parent_version=parent_version,
            description=description
        )
        
        # Store version
        self._versions[version_id] = version
        self._save_metadata()
        
        # Check version limit
        self._enforce_version_limit(model_name)
        
        logger.info(f"Registered model version: {version_id}")
        return version
    
    def _generate_version_id(self, model_name: str) -> str:
        """Generate a unique version ID."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = uuid.uuid4().hex[:8]
        return f"{model_name}_{timestamp}_{unique_id}"
    
    def _generate_version_number(self, model_name: str) -> str:
        """Generate the next version number for a model."""
        model_versions = [
            v for v in self._versions.values()
            if v.model_name == model_name
        ]
        
        if not model_versions:
            return "v1.0.0"
        
        # Find highest version number
        highest = 0
        for v in model_versions:
            try:
                # Extract number from version string like "v1.0.0"
                parts = v.version_number.lstrip("v").split(".")
                num = int(parts[0]) * 100 + int(parts[1]) * 10 + int(parts[2])
                highest = max(highest, num)
            except (ValueError, IndexError):
                continue
        
        # Increment minor version
        major = highest // 100
        minor = (highest % 100) // 10 + 1
        
        return f"v{major}.{minor}.0"
    
    def _copy_model(self, source_path: str, dest_path: Path) -> None:
        """Copy model checkpoint to registry storage."""
        source = Path(source_path)
        
        if source.is_file():
            # Single file checkpoint
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest_path)
        elif source.is_dir():
            # Directory checkpoint
            shutil.copytree(source, dest_path)
        else:
            raise ValueError(f"Model path does not exist: {source_path}")
        
        logger.debug(f"Copied model from {source_path} to {dest_path}")
    
    def _enforce_version_limit(self, model_name: str) -> None:
        """Enforce maximum version limit for a model."""
        if self.config.max_versions <= 0:
            return
        
        model_versions = [
            v for v in self._versions.values()
            if v.model_name == model_name
        ]
        
        # Sort by creation date
        model_versions.sort(key=lambda v: v.created_at, reverse=True)
        
        # Archive old versions
        while len(model_versions) > self.config.max_versions:
            old_version = model_versions.pop()
            
            if self.config.auto_archive:
                self.archive_version(old_version.version_id)
            else:
                self.delete_version(old_version.version_id)
    
    def get_version(self, version_id: str) -> Optional[ModelVersion]:
        """
        Get a model version by ID.
        
        Args:
            version_id: The version identifier
            
        Returns:
            ModelVersion if found, None otherwise
        """
        return self._versions.get(version_id)
    
    def list_versions(
        self,
        model_name: Optional[str] = None,
        status: Optional[ModelStatus] = None,
        tags: Optional[List[str]] = None,
        require_all_tags: bool = False,
        min_metric: Optional[Dict[str, float]] = None,
        limit: int = 100
    ) -> List[ModelVersion]:
        """
        List available model versions with optional filtering.
        
        Args:
            model_name: Filter by model name
            status: Filter by status
            tags: Filter by tags (any match unless require_all_tags=True)
            require_all_tags: Require all tags to match
            min_metric: Minimum metric thresholds (e.g., {"accuracy": 0.8})
            limit: Maximum number of versions to return
            
        Returns:
            List of matching ModelVersion objects
        """
        results = []
        
        for version in self._versions.values():
            # Filter by model name
            if model_name and version.model_name != model_name:
                continue
            
            # Filter by status
            if status and version.status != status:
                continue
            
            # Filter by tags
            if tags and not version.matches_tags(tags, require_all_tags):
                continue
            
            # Filter by minimum metrics
            if min_metric:
                meets_threshold = all(
                    version.get_metric(m) >= v
                    for m, v in min_metric.items()
                )
                if not meets_threshold:
                    continue
            
            results.append(version)
        
        # Sort by creation date (newest first)
        results.sort(key=lambda v: v.created_at, reverse=True)
        
        return results[:limit]
    
    def get_best_model(
        self,
        metric: str,
        model_name: Optional[str] = None,
        status: Optional[ModelStatus] = None,
        tags: Optional[List[str]] = None,
        higher_is_better: bool = True
    ) -> Optional[ModelVersion]:
        """
        Get the best model version by a specific metric.
        
        Args:
            metric: The metric to compare by
            model_name: Filter by model name
            status: Filter by status
            tags: Filter by tags
            higher_is_better: Whether higher values are better
            
        Returns:
            Best ModelVersion or None if no versions match
        """
        candidates = self.list_versions(
            model_name=model_name,
            status=status,
            tags=tags
        )
        
        # Filter to versions that have the metric
        candidates = [v for v in candidates if metric in v.metrics]
        
        if not candidates:
            return None
        
        # Sort by metric
        candidates.sort(
            key=lambda v: v.get_metric(metric),
            reverse=higher_is_better
        )
        
        return candidates[0]
    
    def load_model(
        self,
        version_id: str,
        target_path: str,
        overwrite: bool = False
    ) -> Path:
        """
        Load a model checkpoint to a target location.
        
        Args:
            version_id: The version to load
            target_path: Where to load the model
            overwrite: Whether to overwrite existing target
            
        Returns:
            Path to the loaded model
        """
        version = self.get_version(version_id)
        if not version:
            raise ValueError(f"Version not found: {version_id}")
        
        target = Path(target_path)
        
        if target.exists():
            if overwrite:
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            else:
                raise FileExistsError(f"Target path already exists: {target_path}")
        
        source = Path(version.model_path)
        
        if source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        elif source.is_dir():
            shutil.copytree(source, target)
        else:
            raise FileNotFoundError(f"Model files not found at: {source}")
        
        logger.info(f"Loaded model {version_id} to {target_path}")
        return target
    
    def update_metrics(
        self,
        version_id: str,
        metrics: Dict[str, float],
        merge: bool = True
    ) -> Optional[ModelVersion]:
        """
        Update metrics for a model version.
        
        Args:
            version_id: The version to update
            metrics: New metric values
            merge: If True, merge with existing; if False, replace
            
        Returns:
            Updated ModelVersion or None if not found
        """
        version = self.get_version(version_id)
        if not version:
            return None
        
        if merge:
            version.metrics.update(metrics)
        else:
            version.metrics = metrics
        
        self._save_metadata()
        logger.info(f"Updated metrics for {version_id}")
        return version
    
    def update_status(
        self,
        version_id: str,
        status: ModelStatus
    ) -> Optional[ModelVersion]:
        """
        Update the status of a model version.
        
        Args:
            version_id: The version to update
            status: New status
            
        Returns:
            Updated ModelVersion or None if not found
        """
        version = self.get_version(version_id)
        if not version:
            return None
        
        version.status = status
        self._save_metadata()
        logger.info(f"Updated status for {version_id} to {status.value}")
        return version
    
    def promote_version(
        self,
        version_id: str,
        new_status: ModelStatus = ModelStatus.PRODUCTION
    ) -> Optional[ModelVersion]:
        """
        Promote a version to a higher status.
        
        Args:
            version_id: The version to promote
            new_status: Target status
            
        Returns:
            Updated ModelVersion or None if not found
        """
        return self.update_status(version_id, new_status)
    
    def archive_version(self, version_id: str) -> bool:
        """
        Archive a model version.
        
        Args:
            version_id: The version to archive
            
        Returns:
            True if archived successfully
        """
        version = self.get_version(version_id)
        if not version:
            return False
        
        # Move model files to archive
        source = Path(version.model_path)
        if source.exists():
            archive_dest = self.archived_path / version_id
            shutil.move(str(source), str(archive_dest))
            version.model_path = str(archive_dest)
        
        version.status = ModelStatus.ARCHIVED
        self._save_metadata()
        
        logger.info(f"Archived version {version_id}")
        return True
    
    def delete_version(self, version_id: str) -> bool:
        """
        Delete a model version permanently.
        
        Args:
            version_id: The version to delete
            
        Returns:
            True if deleted successfully
        """
        version = self._versions.pop(version_id, None)
        if not version:
            return False
        
        # Delete model files
        source = Path(version.model_path)
        if source.exists():
            if source.is_dir():
                shutil.rmtree(source)
            else:
                source.unlink()
        
        self._save_metadata()
        logger.info(f"Deleted version {version_id}")
        return True
    
    def compare_versions(
        self,
        version_id_1: str,
        version_id_2: str,
        metrics: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Compare two model versions.
        
        Args:
            version_id_1: First version ID
            version_id_2: Second version ID
            metrics: Specific metrics to compare (all if None)
            
        Returns:
            Comparison results dictionary
        """
        v1 = self.get_version(version_id_1)
        v2 = self.get_version(version_id_2)
        
        if not v1 or not v2:
            raise ValueError("One or both versions not found")
        
        # Get all metrics to compare
        all_metrics = set(v1.metrics.keys()) | set(v2.metrics.keys())
        if metrics:
            all_metrics = all_metrics.intersection(metrics)
        
        comparison = {
            "version_1": version_id_1,
            "version_2": version_id_2,
            "metrics": {},
            "differences": {},
            "winner": {}
        }
        
        for metric in all_metrics:
            val1 = v1.get_metric(metric)
            val2 = v2.get_metric(metric)
            diff = val2 - val1
            
            comparison["metrics"][metric] = {
                "version_1": val1,
                "version_2": val2
            }
            comparison["differences"][metric] = diff
            comparison["winner"][metric] = version_id_1 if val1 > val2 else version_id_2 if val2 > val1 else "tie"
        
        return comparison
    
    def get_lineage(self, version_id: str) -> List[ModelVersion]:
        """
        Get the lineage (ancestry) of a model version.
        
        Args:
            version_id: The version to trace
            
        Returns:
            List of versions from root to this version
        """
        lineage = []
        current = self.get_version(version_id)
        
        while current:
            lineage.append(current)
            if current.parent_version:
                current = self.get_version(current.parent_version)
            else:
                current = None
        
        # Reverse to get root first
        lineage.reverse()
        return lineage
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about the registry.
        
        Returns:
            Dictionary with statistics
        """
        versions = list(self._versions.values())
        
        # Count by status
        status_counts = {}
        for status in ModelStatus:
            status_counts[status.value] = sum(
                1 for v in versions if v.status == status
            )
        
        # Count by model name
        model_counts = {}
        for v in versions:
            model_counts[v.model_name] = model_counts.get(v.model_name, 0) + 1
        
        # Get metric statistics
        all_metrics = set()
        for v in versions:
            all_metrics.update(v.metrics.keys())
        
        metric_stats = {}
        for metric in all_metrics:
            values = [v.get_metric(metric) for v in versions if metric in v.metrics]
            if values:
                metric_stats[metric] = {
                    "count": len(values),
                    "min": min(values),
                    "max": max(values),
                    "mean": sum(values) / len(values)
                }
        
        return {
            "total_versions": len(versions),
            "model_names": list(model_counts.keys()),
            "versions_per_model": model_counts,
            "status_counts": status_counts,
            "metrics_available": list(all_metrics),
            "metric_statistics": metric_stats,
            "registry_path": str(self.base_path)
        }


def create_registry(
    base_dir: str = "~/.autodev/model_registry",
    max_versions: int = 50
) -> ModelRegistry:
    """
    Factory function to create a ModelRegistry.
    
    Args:
        base_dir: Base directory for registry storage
        max_versions: Maximum versions to keep per model
        
    Returns:
        Configured ModelRegistry instance
    """
    config = RegistryConfig(
        base_dir=base_dir,
        max_versions=max_versions
    )
    return ModelRegistry(config)
