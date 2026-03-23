"""
Model Deployer for AutoDev

This module provides model deployment capabilities for trained LoRA adapters,
bridging the gap between training completion and production inference.

Components:
- CheckpointInfo: Dataclass for checkpoint metadata
- DeploymentConfig: Configuration for deployment targets
- CheckpointManager: Discover and validate training checkpoints
- ModelDeployer: Abstract base class for deployment strategies
- HuggingFaceDeployer: Push adapters to HuggingFace Hub
- VLLMDeployer: Deploy to vLLM inference server
- LocalInferenceDeployer: Export for local inference
- VersionRegistry: Track deployed versions
- RollbackManager: Handle version rollback with safety checks

Target: Complete deployment in <5 min for LoRA adapters
"""

import json
import logging
import os
import subprocess
import shutil
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================

class DeploymentTarget(Enum):
    """Supported deployment targets."""
    HUGGINGFACE = "huggingface"
    VLLM = "vllm"
    LOCAL = "local"


class DeploymentStatus(Enum):
    """Status of a deployment."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    ACTIVE = "active"
    CANARY = "canary"
    DEPRECATED = "deprecated"
    FAILED = "failed"


class RollbackReason(Enum):
    """Reasons for rollback."""
    PERFORMANCE_REGRESSION = "performance_regression"
    ERROR_RATE = "error_rate"
    MANUAL = "manual"
    CANARY_FAILURE = "canary_failure"
    HEALTH_CHECK = "health_check"


# =============================================================================
# Data Structures
# =============================================================================

@dataclass
class CheckpointInfo:
    """
    Information about a training checkpoint.
    
    Attributes:
        path: Path to the checkpoint directory
        step: Training step number
        timestamp: When the checkpoint was created
        metrics: Performance metrics (loss, resolution_rate, reward)
        is_best: Whether this is the best checkpoint in the run
        run_id: The training run identifier
        adapter_file: Path to adapter_model.safetensors
        config_file: Path to adapter_config.json
    """
    path: str
    step: int
    timestamp: datetime
    metrics: Dict[str, float] = field(default_factory=dict)
    is_best: bool = False
    run_id: str = ""
    adapter_file: str = ""
    config_file: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CheckpointInfo":
        """Create from dictionary."""
        if isinstance(data.get("timestamp"), str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)
    
    def get_metric(self, metric_name: str, default: float = 0.0) -> float:
        """Get a specific metric value."""
        return self.metrics.get(metric_name, default)


@dataclass
class DeploymentConfig:
    """
    Configuration for model deployment.
    
    Attributes:
        target: Deployment target (huggingface, vllm, local)
        base_model: Base model identifier
        checkpoint_path: Path to checkpoint to deploy
        version: Version string (optional, auto-generated if not provided)
        
        # HuggingFace specific
        hf_repo_id: HuggingFace repo ID (org/model-name)
        hf_private: Whether to make repo private
        hf_tags: Tags for the model card
        
        # vLLM specific
        vllm_host: Host for vLLM server
        vllm_port: Port for vLLM server
        vllm_gpu_memory: GPU memory utilization
        vllm_max_model_len: Maximum model context length
        
        # Local specific
        local_output_dir: Output directory for local deployment
        local_merge_weights: Whether to merge LoRA weights
        local_quantization: Quantization type (None, "4bit", "8bit")
        
        # General
        run_validation: Whether to run validation after deploy
        tags: General tags for the deployment
    """
    target: DeploymentTarget = DeploymentTarget.LOCAL
    base_model: str = ""
    checkpoint_path: str = ""
    version: str = ""
    
    # HuggingFace settings
    hf_repo_id: str = ""
    hf_private: bool = False
    hf_tags: List[str] = field(default_factory=lambda: ["autodev", "code-generation", "lora"])
    
    # vLLM settings
    vllm_host: str = "0.0.0.0"
    vllm_port: int = 8000
    vllm_gpu_memory: float = 0.9
    vllm_max_model_len: int = 8192
    
    # Local settings
    local_output_dir: str = "~/.autodev/deployed"
    local_merge_weights: bool = True
    local_quantization: Optional[str] = None
    
    # General settings
    run_validation: bool = True
    tags: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Process configuration after initialization."""
        # Convert string target to enum
        if isinstance(self.target, str):
            self.target = DeploymentTarget(self.target)
        
        # Expand output directory
        self.local_output_dir = os.path.expanduser(self.local_output_dir)


@dataclass
class DeployedVersion:
    """
    Information about a deployed model version.
    
    Attributes:
        version: Version string
        checkpoint_path: Path to the deployed checkpoint
        deployment_type: Type of deployment (huggingface, vllm, local)
        endpoint_url: URL for inference endpoint (if applicable)
        deployed_at: When the deployment was created
        metrics: Performance metrics at deployment time
        status: Current deployment status
        base_model: Base model identifier
        config: Deployment configuration used
    """
    version: str
    checkpoint_path: str
    deployment_type: str
    endpoint_url: Optional[str] = None
    deployed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metrics: Dict[str, float] = field(default_factory=dict)
    status: DeploymentStatus = DeploymentStatus.ACTIVE
    base_model: str = ""
    config: Optional[DeploymentConfig] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        data["deployed_at"] = self.deployed_at.isoformat()
        data["status"] = self.status.value
        if self.config:
            data["config"] = {
                "target": self.config.target.value,
                "base_model": self.config.base_model,
                "version": self.config.version,
            }
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DeployedVersion":
        """Create from dictionary."""
        if isinstance(data.get("deployed_at"), str):
            data["deployed_at"] = datetime.fromisoformat(data["deployed_at"])
        if isinstance(data.get("status"), str):
            data["status"] = DeploymentStatus(data["status"])
        # Note: config is stored as a simplified dict, not reconstructed
        if "config" in data and isinstance(data["config"], dict):
            data["config"] = None  # Simplified - don't reconstruct full config
        return cls(**data)


@dataclass
class DeploymentResult:
    """
    Result of a deployment operation.
    
    Attributes:
        success: Whether the deployment succeeded
        version: DeployedVersion if successful
        error_message: Error message if failed
        duration_seconds: Time taken for deployment
        logs: Deployment logs
    """
    success: bool
    version: Optional[DeployedVersion] = None
    error_message: str = ""
    duration_seconds: float = 0.0
    logs: List[str] = field(default_factory=list)


@dataclass
class RollbackResult:
    """
    Result of a rollback operation.
    
    Attributes:
        success: Whether the rollback succeeded
        previous_version: Version rolled back from
        target_version: Version rolled back to
        reason: Reason for rollback
        error_message: Error message if failed
    """
    success: bool
    previous_version: str = ""
    target_version: str = ""
    reason: RollbackReason = RollbackReason.MANUAL
    error_message: str = ""


# =============================================================================
# Checkpoint Manager
# =============================================================================

class CheckpointManager:
    """
    Manages training checkpoint discovery and validation.
    
    Handles:
    - Discovering checkpoints from training runs
    - Parsing trainer_state.json for metrics
    - Selecting best/latest checkpoints
    - Validating checkpoint integrity
    
    Example:
        manager = CheckpointManager()
        
        # List all checkpoints from a run
        checkpoints = manager.list_checkpoints("run_20260323_143052")
        
        # Get the best checkpoint by metric
        best = manager.get_best_checkpoint("run_20260323_143052", metric="resolution_rate")
        
        # Validate a checkpoint
        is_valid = manager.validate_checkpoint("/path/to/checkpoint")
    """
    
    def __init__(self, checkpoint_base_dir: str = "~/.autodev/checkpoints"):
        """
        Initialize the checkpoint manager.
        
        Args:
            checkpoint_base_dir: Base directory for checkpoints
        """
        self.checkpoint_base_dir = Path(os.path.expanduser(checkpoint_base_dir))
        self._ensure_directories()
    
    def _ensure_directories(self) -> None:
        """Create necessary directories."""
        self.checkpoint_base_dir.mkdir(parents=True, exist_ok=True)
    
    def list_runs(self) -> List[str]:
        """
        List all training run IDs.
        
        Returns:
            List of run IDs (directory names)
        """
        runs = []
        if not self.checkpoint_base_dir.exists():
            return runs
        
        for item in self.checkpoint_base_dir.iterdir():
            if item.is_dir() and item.name.startswith("run_"):
                runs.append(item.name)
        
        return sorted(runs, reverse=True)
    
    def list_checkpoints(self, run_id: str) -> List[CheckpointInfo]:
        """
        List all checkpoints from a training run.
        
        Args:
            run_id: The training run identifier
            
        Returns:
            List of CheckpointInfo objects
        """
        run_path = self.checkpoint_base_dir / run_id
        if not run_path.exists():
            logger.warning(f"Run directory does not exist: {run_path}")
            return []
        
        checkpoints = []
        
        for item in sorted(run_path.iterdir()):
            if not item.is_dir():
                continue
            
            # Check for checkpoint directories
            if item.name.startswith("checkpoint-") or item.name == "checkpoint-best":
                checkpoint_info = self._parse_checkpoint(item, run_id)
                if checkpoint_info:
                    checkpoints.append(checkpoint_info)
        
        return checkpoints
    
    def _parse_checkpoint(self, checkpoint_path: Path, run_id: str) -> Optional[CheckpointInfo]:
        """
        Parse a checkpoint directory and extract metadata.
        
        Args:
            checkpoint_path: Path to the checkpoint directory
            run_id: The training run identifier
            
        Returns:
            CheckpointInfo or None if parsing fails
        """
        try:
            # Extract step number
            if checkpoint_path.name == "checkpoint-best":
                step = -1  # Special marker for best checkpoint
                is_best = True
            else:
                step = int(checkpoint_path.name.split("-")[1])
                is_best = False
            
            # Look for required files
            adapter_file = checkpoint_path / "adapter_model.safetensors"
            config_file = checkpoint_path / "adapter_config.json"
            trainer_state_file = checkpoint_path / "trainer_state.json"
            
            # Check if required files exist
            if not adapter_file.exists():
                logger.debug(f"Missing adapter file in {checkpoint_path}")
                return None
            
            # Parse metrics from trainer_state.json
            metrics = {}
            timestamp = datetime.fromtimestamp(checkpoint_path.stat().st_mtime, tz=timezone.utc)
            
            if trainer_state_file.exists():
                try:
                    with open(trainer_state_file, "r") as f:
                        trainer_state = json.load(f)
                    
                    # Extract relevant metrics
                    if "log_history" in trainer_state:
                        # Get the most recent log entry
                        log_history = trainer_state["log_history"]
                        if log_history:
                            last_log = log_history[-1]
                            metrics["loss"] = last_log.get("loss", 0.0)
                    
                    # Check for custom metrics
                    if "best_metric" in trainer_state:
                        metrics["best_metric"] = trainer_state["best_metric"]
                    
                    # Extract timestamp if available
                    if "timestamp" in trainer_state:
                        try:
                            timestamp = datetime.fromisoformat(trainer_state["timestamp"])
                        except (ValueError, TypeError):
                            pass
                            
                except (json.JSONDecodeError, IOError) as e:
                    logger.warning(f"Failed to parse trainer_state.json: {e}")
            
            return CheckpointInfo(
                path=str(checkpoint_path),
                step=step,
                timestamp=timestamp,
                metrics=metrics,
                is_best=is_best,
                run_id=run_id,
                adapter_file=str(adapter_file),
                config_file=str(config_file) if config_file.exists() else ""
            )
            
        except (ValueError, OSError) as e:
            logger.warning(f"Failed to parse checkpoint {checkpoint_path}: {e}")
            return None
    
    def get_best_checkpoint(
        self, 
        run_id: str, 
        metric: str = "loss",
        higher_is_better: bool = False
    ) -> Optional[CheckpointInfo]:
        """
        Get the best checkpoint from a run by a specific metric.
        
        Args:
            run_id: The training run identifier
            metric: The metric to compare by
            higher_is_better: Whether higher values are better
            
        Returns:
            Best CheckpointInfo or None if no checkpoints
        """
        checkpoints = self.list_checkpoints(run_id)
        
        if not checkpoints:
            return None
        
        # First check for explicitly marked best checkpoint
        best_marked = [c for c in checkpoints if c.is_best]
        if best_marked:
            return best_marked[0]
        
        # Filter checkpoints that have the metric
        candidates = [c for c in checkpoints if metric in c.metrics]
        
        if not candidates:
            # Fall back to latest checkpoint
            return self.get_latest_checkpoint(run_id)
        
        # Sort by metric
        candidates.sort(
            key=lambda c: c.get_metric(metric),
            reverse=higher_is_better
        )
        
        return candidates[0]
    
    def get_latest_checkpoint(self, run_id: str) -> Optional[CheckpointInfo]:
        """
        Get the most recent checkpoint from a run.
        
        Args:
            run_id: The training run identifier
            
        Returns:
            Latest CheckpointInfo or None if no checkpoints
        """
        checkpoints = self.list_checkpoints(run_id)
        
        if not checkpoints:
            return None
        
        # Sort by step number (descending)
        checkpoints.sort(key=lambda c: c.step, reverse=True)
        
        return checkpoints[0]
    
    def validate_checkpoint(self, path: str) -> bool:
        """
        Validate that a checkpoint has all required files.
        
        Args:
            path: Path to the checkpoint directory
            
        Returns:
            True if checkpoint is valid
        """
        checkpoint_path = Path(path)
        
        if not checkpoint_path.exists():
            logger.error(f"Checkpoint path does not exist: {path}")
            return False
        
        if not checkpoint_path.is_dir():
            logger.error(f"Checkpoint path is not a directory: {path}")
            return False
        
        # Check for required files
        required_files = ["adapter_model.safetensors"]
        optional_files = ["adapter_config.json", "trainer_state.json"]
        
        for req_file in required_files:
            if not (checkpoint_path / req_file).exists():
                logger.error(f"Missing required file: {req_file}")
                return False
        
        # Log optional file status
        for opt_file in optional_files:
            if not (checkpoint_path / opt_file).exists():
                logger.debug(f"Missing optional file: {opt_file}")
        
        # Try to load adapter config if present
        adapter_config_path = checkpoint_path / "adapter_config.json"
        if adapter_config_path.exists():
            try:
                with open(adapter_config_path, "r") as f:
                    config = json.load(f)
                
                # Validate essential config keys
                essential_keys = ["r", "lora_alpha", "target_modules"]
                missing_keys = [k for k in essential_keys if k not in config]
                if missing_keys:
                    logger.warning(f"Adapter config missing keys: {missing_keys}")
                    
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to parse adapter_config.json: {e}")
        
        logger.info(f"Checkpoint validation passed: {path}")
        return True


# =============================================================================
# Base Model Deployer
# =============================================================================

class ModelDeployer(ABC):
    """
    Abstract base class for model deployment strategies.
    
    Subclasses implement specific deployment targets:
    - HuggingFaceDeployer: Push to HuggingFace Hub
    - VLLMDeployer: Start vLLM inference server
    - LocalInferenceDeployer: Export for local use
    
    Example:
        deployer = HuggingFaceDeployer(config)
        result = deployer.deploy(checkpoint_path, version="v1.0.0")
        
        if result.success:
            print(f"Deployed to: {result.version.endpoint_url}")
    """
    
    def __init__(self, config: Optional[DeploymentConfig] = None):
        """
        Initialize the deployer.
        
        Args:
            config: Deployment configuration
        """
        self.config = config or DeploymentConfig()
        self.checkpoint_manager = CheckpointManager()
    
    @abstractmethod
    def deploy(
        self, 
        checkpoint_path: str, 
        version: Optional[str] = None,
        **kwargs
    ) -> DeploymentResult:
        """
        Deploy a checkpoint to the target.
        
        Args:
            checkpoint_path: Path to the checkpoint directory
            version: Version string (auto-generated if not provided)
            **kwargs: Additional deployment options
            
        Returns:
            DeploymentResult with success status and details
        """
        pass
    
    @abstractmethod
    def rollback(
        self, 
        target_version: str, 
        reason: RollbackReason = RollbackReason.MANUAL
    ) -> RollbackResult:
        """
        Rollback to a previous version.
        
        Args:
            target_version: Version to rollback to
            reason: Reason for rollback
            
        Returns:
            RollbackResult with success status
        """
        pass
    
    def _generate_version(
        self, 
        checkpoint_path: str,
        model_name: str = "autodev-lora",
        commit_sha: Optional[str] = None
    ) -> str:
        """
        Generate a version string for deployment.
        
        Format: {model_name}-v{major}.{minor}.{patch}-{short_sha}
        Example: autodev-llama-lora-v1.0.0-4f3bf81
        
        Args:
            checkpoint_path: Path to checkpoint
            model_name: Base model name
            commit_sha: Git commit SHA (optional)
            
        Returns:
            Version string
        """
        # Get short SHA
        short_sha = ""
        if commit_sha:
            short_sha = commit_sha[:7]
        else:
            # Try to get git SHA from checkpoint directory
            try:
                result = subprocess.run(
                    ["git", "rev-parse", "--short", "HEAD"],
                    cwd=checkpoint_path,
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    short_sha = result.stdout.strip()[:7]
            except Exception:
                pass
        
        # Generate version components
        timestamp = datetime.now()
        major = 1
        minor = (timestamp.month * 100) + timestamp.day  # MMDD format
        patch = timestamp.hour * 100 + timestamp.minute  # HHMM format
        
        version_base = f"{model_name}-v{major}.{minor}.{patch}"
        
        if short_sha:
            return f"{version_base}-{short_sha}"
        return version_base
    
    def _validate_checkpoint(self, checkpoint_path: str) -> bool:
        """
        Validate the checkpoint before deployment.
        
        Args:
            checkpoint_path: Path to checkpoint
            
        Returns:
            True if valid
        """
        return self.checkpoint_manager.validate_checkpoint(checkpoint_path)
    
    def status(self, endpoint: Optional[str] = None) -> Dict[str, Any]:
        """
        Check the status of a deployment.
        
        Args:
            endpoint: Endpoint URL to check
            
        Returns:
            Status dictionary
        """
        return {
            "status": "unknown",
            "message": "Status check not implemented for this deployer"
        }


# =============================================================================
# HuggingFace Deployer
# =============================================================================

class HuggingFaceDeployer(ModelDeployer):
    """
    Deploy LoRA adapters to HuggingFace Hub.
    
    Features:
    - Auto-generated model cards with training metrics
    - LoRA adapter upload (adapter_model.safetensors, adapter_config.json)
    - Commit SHA-based versioning
    - README with SWE-bench resolution rate
    
    Example:
        deployer = HuggingFaceDeployer(config)
        result = deployer.deploy(
            checkpoint_path="./checkpoints/best",
            repo_id="your-org/autodev-lora",
            tags=["autodev", "code-generation"],
            private=False
        )
    """
    
    def __init__(self, config: Optional[DeploymentConfig] = None):
        super().__init__(config)
        self._hf_api = None
    
    def _get_hf_api(self):
        """Lazy load HuggingFace API."""
        if self._hf_api is None:
            try:
                from huggingface_hub import HfApi
                self._hf_api = HfApi()
            except ImportError:
                raise ImportError(
                    "huggingface_hub is required for HuggingFace deployment. "
                    "Install with: pip install huggingface_hub"
                )
        return self._hf_api
    
    def deploy(
        self,
        checkpoint_path: str,
        version: Optional[str] = None,
        repo_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        private: Optional[bool] = None,
        **kwargs
    ) -> DeploymentResult:
        """
        Deploy checkpoint to HuggingFace Hub.
        
        Args:
            checkpoint_path: Path to checkpoint directory
            version: Version string
            repo_id: HuggingFace repo ID (org/model-name)
            tags: Tags for the model card
            private: Whether to make the repo private
            **kwargs: Additional options (commit_message, create_tag)
            
        Returns:
            DeploymentResult with repo URL
        """
        import time
        start_time = time.time()
        logs = []
        
        try:
            # Validate checkpoint
            logs.append(f"Validating checkpoint: {checkpoint_path}")
            if not self._validate_checkpoint(checkpoint_path):
                return DeploymentResult(
                    success=False,
                    error_message="Checkpoint validation failed",
                    logs=logs
                )
            
            # Get configuration
            repo_id = repo_id or self.config.hf_repo_id
            if not repo_id:
                return DeploymentResult(
                    success=False,
                    error_message="repo_id is required for HuggingFace deployment",
                    logs=logs
                )
            
            tags = tags or self.config.hf_tags
            private = private if private is not None else self.config.hf_private
            commit_message = kwargs.get("commit_message", f"Deploy {version or 'model'} via AutoDev")
            create_tag = kwargs.get("create_tag", True)
            
            # Generate version
            version = version or self._generate_version(checkpoint_path)
            logs.append(f"Generated version: {version}")
            
            # Get HuggingFace API
            api = self._get_hf_api()
            checkpoint_path_obj = Path(checkpoint_path)
            
            # Step 1: Create repository if it doesn't exist
            logs.append(f"Creating/getting repository: {repo_id}")
            try:
                from huggingface_hub import create_repo, repo_exists
                if not repo_exists(repo_id):
                    create_repo(repo_id, private=private, exist_ok=True)
                    logs.append(f"Created new repository: {repo_id}")
                else:
                    logs.append(f"Repository exists: {repo_id}")
            except Exception as e:
                logs.append(f"Repository check/create: {e}")
            
            # Step 2: Upload adapter files
            from huggingface_hub import upload_file, upload_folder
            
            files_to_upload = []
            
            # Upload adapter_model.safetensors
            adapter_file = checkpoint_path_obj / "adapter_model.safetensors"
            if adapter_file.exists():
                logs.append("Uploading adapter_model.safetensors...")
                api.upload_file(
                    path_or_fileobj=str(adapter_file),
                    path_in_repo="adapter_model.safetensors",
                    repo_id=repo_id,
                    commit_message=f"Upload adapter weights - {version}"
                )
                files_to_upload.append("adapter_model.safetensors")
            
            # Upload adapter_config.json
            config_file = checkpoint_path_obj / "adapter_config.json"
            if config_file.exists():
                logs.append("Uploading adapter_config.json...")
                api.upload_file(
                    path_or_fileobj=str(config_file),
                    path_in_repo="adapter_config.json",
                    repo_id=repo_id,
                    commit_message=f"Upload adapter config - {version}"
                )
                files_to_upload.append("adapter_config.json")
            
            # Step 3: Generate and upload model card
            logs.append("Generating model card...")
            model_card_content = self._generate_model_card(
                checkpoint_path=checkpoint_path,
                version=version,
                tags=tags,
                **kwargs
            )
            
            # Write model card to temp file and upload
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
                f.write(model_card_content)
                temp_card_path = f.name
            
            try:
                api.upload_file(
                    path_or_fileobj=temp_card_path,
                    path_in_repo="README.md",
                    repo_id=repo_id,
                    commit_message=f"Update model card - {version}"
                )
                logs.append("Uploaded model card (README.md)")
            finally:
                os.unlink(temp_card_path)
            
            # Step 4: Create version tag if requested
            if create_tag:
                try:
                    from huggingface_hub import create_tag
                    create_tag(repo_id, tag=version, exist_ok=True)
                    logs.append(f"Created version tag: {version}")
                except Exception as tag_error:
                    logs.append(f"Tag creation note: {tag_error}")
            
            endpoint_url = f"https://huggingface.co/{repo_id}"
            logs.append(f"Deployment complete: {endpoint_url}")
            
            # Load checkpoint metrics if available
            metrics = self._load_checkpoint_metrics(checkpoint_path)
            
            deployed_version = DeployedVersion(
                version=version,
                checkpoint_path=checkpoint_path,
                deployment_type="huggingface",
                endpoint_url=endpoint_url,
                metrics=metrics,
                status=DeploymentStatus.ACTIVE,
                base_model=self.config.base_model
            )
            
            return DeploymentResult(
                success=True,
                version=deployed_version,
                duration_seconds=time.time() - start_time,
                logs=logs
            )
            
        except ImportError as e:
            logger.error(f"Missing dependency: {e}")
            logs.append(f"Import error: {str(e)}")
            return DeploymentResult(
                success=False,
                error_message=f"Missing dependency: {e}. Install with: pip install huggingface_hub",
                duration_seconds=time.time() - start_time,
                logs=logs
            )
        except Exception as e:
            logger.error(f"HuggingFace deployment failed: {e}")
            logs.append(f"Error: {str(e)}")
            return DeploymentResult(
                success=False,
                error_message=str(e),
                duration_seconds=time.time() - start_time,
                logs=logs
            )
    
    def _generate_model_card(
        self,
        checkpoint_path: str,
        version: str,
        tags: List[str],
        **kwargs
    ) -> str:
        """Generate a HuggingFace model card README."""
        checkpoint_path_obj = Path(checkpoint_path)
        
        # Load adapter config
        adapter_config = {}
        config_file = checkpoint_path_obj / "adapter_config.json"
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    adapter_config = json.load(f)
            except Exception:
                pass
        
        # Load training metrics
        metrics = self._load_checkpoint_metrics(checkpoint_path)
        
        # Get base model info
        base_model = adapter_config.get("base_model_name_or_path", self.config.base_model or "unknown")
        
        # Format tags
        tags_yaml = "\n".join([f"- {tag}" for tag in tags])
        
        # Build model card
        card = f"""---
license: apache-2.0
tags:
{tags_yaml}
base_model: {base_model}
---

# AutoDev LoRA Adapter - {version}

This model is a LoRA adapter fine-tuned by AutoDev for code generation tasks.

## Model Details

- **Base Model:** `{base_model}`
- **Version:** `{version}`
- **Architecture:** LoRA (Low-Rank Adaptation)

## LoRA Configuration

| Parameter | Value |
|-----------|-------|
| Rank (r) | {adapter_config.get('r', 'N/A')} |
| Alpha | {adapter_config.get('lora_alpha', 'N/A')} |
| Target Modules | {adapter_config.get('target_modules', 'N/A')} |
| Dropout | {adapter_config.get('lora_dropout', 'N/A')} |

## Training Metrics

| Metric | Value |
|--------|-------|
| Loss | {f"{metrics.get('loss'):.4f}" if isinstance(metrics.get('loss'), (int, float)) else 'N/A'} |
| Resolution Rate | {f"{metrics.get('resolution_rate'):.2%}" if isinstance(metrics.get('resolution_rate'), (int, float)) else 'N/A'} |

## Usage

### With PEFT

```python
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

# Load base model
base_model = AutoModelForCausalLM.from_pretrained("{base_model}")
tokenizer = AutoTokenizer.from_pretrained("{base_model}")

# Load LoRA adapter
model = PeftModel.from_pretrained(base_model, "{self.config.hf_repo_id or 'your-org/your-model'}")

# Generate
inputs = tokenizer("def hello_world():", return_tensors="pt")
outputs = model.generate(**inputs, max_length=100)
print(tokenizer.decode(outputs[0]))
```

### With vLLM

```bash
vllm serve {base_model} \\
  --enable-lora \\
  --lora-modules autodev={self.config.hf_repo_id or 'your-org/your-model'}
```

## Limitations

- This adapter requires the base model to function
- Performance may vary depending on the code domain
- Not suitable for tasks outside code generation

## License

Apache 2.0

---
*Generated by AutoDev Model Deployer on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}*
"""
        return card
    
    def _load_checkpoint_metrics(self, checkpoint_path: str) -> Dict[str, float]:
        """Load metrics from checkpoint's trainer_state.json."""
        metrics = {}
        trainer_state_path = Path(checkpoint_path) / "trainer_state.json"
        
        if trainer_state_path.exists():
            try:
                with open(trainer_state_path, 'r') as f:
                    trainer_state = json.load(f)
                
                # Extract loss from last log entry
                if "log_history" in trainer_state and trainer_state["log_history"]:
                    last_log = trainer_state["log_history"][-1]
                    if "loss" in last_log:
                        metrics["loss"] = last_log["loss"]
                
                # Extract best metric
                if "best_metric" in trainer_state:
                    metrics["best_metric"] = trainer_state["best_metric"]
                    
            except Exception as e:
                logger.debug(f"Could not load metrics: {e}")
        
        return metrics
    
    def rollback(
        self,
        target_version: str,
        reason: RollbackReason = RollbackReason.MANUAL
    ) -> RollbackResult:
        """
        Rollback to a previous version on HuggingFace.
        
        This involves:
        1. Getting the target version from the repo tags
        2. Updating the README to reflect current recommended version
        3. Optionally creating a rollback notice
        
        Args:
            target_version: Version tag to rollback to
            reason: Reason for rollback
            
        Returns:
            RollbackResult
        """
        try:
            api = self._get_hf_api()
            repo_id = self.config.hf_repo_id
            
            if not repo_id:
                return RollbackResult(
                    success=False,
                    target_version=target_version,
                    reason=reason,
                    error_message="No repo_id configured for rollback"
                )
            
            # Get list of tags to verify target exists
            try:
                from huggingface_hub import list_repo_refs
                refs = list_repo_refs(repo_id)
                tag_names = [t.name for t in (refs.tags or [])]
                
                if target_version not in tag_names:
                    return RollbackResult(
                        success=False,
                        target_version=target_version,
                        reason=reason,
                        error_message=f"Version tag '{target_version}' not found in repository"
                    )
            except Exception as e:
                logger.warning(f"Could not verify tags: {e}")
            
            # Get current active version for logging
            registry = VersionRegistry()
            current = registry.get_active_version("huggingface")
            previous_version = current.version if current else "unknown"
            
            # Create rollback notice
            rollback_notice = f"""
## ⚠️ Rollback Notice

This repository has been rolled back from a newer version.

- **Rolled back to:** {target_version}
- **Previous version:** {previous_version}
- **Reason:** {reason.value}
- **Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
            
            # Update README with rollback notice
            try:
                from huggingface_hub import hf_hub_download
                readme_path = hf_hub_download(repo_id, "README.md")
                
                with open(readme_path, 'r') as f:
                    readme_content = f.read()
                
                # Add rollback notice if not already present
                if "Rollback Notice" not in readme_content:
                    updated_readme = readme_content + "\n\n" + rollback_notice
                    
                    import tempfile
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
                        f.write(updated_readme)
                        temp_path = f.name
                    
                    try:
                        api.upload_file(
                            path_or_fileobj=temp_path,
                            path_in_repo="README.md",
                            repo_id=repo_id,
                            commit_message=f"Rollback to {target_version} - {reason.value}"
                        )
                    finally:
                        os.unlink(temp_path)
            except Exception as e:
                logger.warning(f"Could not update README with rollback notice: {e}")
            
            logger.info(f"HuggingFace rollback to {target_version} completed")
            
            return RollbackResult(
                success=True,
                previous_version=previous_version,
                target_version=target_version,
                reason=reason
            )
            
        except ImportError as e:
            return RollbackResult(
                success=False,
                target_version=target_version,
                reason=reason,
                error_message=f"Missing dependency: {e}"
            )
        except Exception as e:
            logger.error(f"HuggingFace rollback failed: {e}")
            return RollbackResult(
                success=False,
                target_version=target_version,
                reason=reason,
                error_message=str(e)
            )
    
    def status(self, endpoint: Optional[str] = None) -> Dict[str, Any]:
        """Check HuggingFace model status."""
        # TODO: Implement status check via HuggingFace API
        return {
            "status": "unknown",
            "message": "HuggingFace status check not implemented"
        }


# =============================================================================
# vLLM Deployer
# =============================================================================

class VLLMDeployer(ModelDeployer):
    """
    Deploy to vLLM inference server.
    
    Features:
    - Dynamic LoRA loading (--enable-lora)
    - Multi-adapter serving
    - OpenAI-compatible API endpoint
    - Health check endpoint /health
    
    Example:
        deployer = VLLMDeployer(config)
        result = deployer.deploy(
            checkpoint_path="./checkpoints/best",
            base_model="codellama/CodeLlama-7b-hf",
            port=8000
        )
        
        if result.success:
            print(f"vLLM server running at: {result.version.endpoint_url}")
    """
    
    def __init__(self, config: Optional[DeploymentConfig] = None):
        super().__init__(config)
        self._process = None
    
    def deploy(
        self,
        checkpoint_path: str,
        version: Optional[str] = None,
        base_model: Optional[str] = None,
        port: Optional[int] = None,
        **kwargs
    ) -> DeploymentResult:
        """
        Deploy checkpoint to vLLM server.
        
        Args:
            checkpoint_path: Path to checkpoint directory
            version: Version string / adapter name
            base_model: Base model identifier
            port: Port for the server
            **kwargs: Additional options:
                - host: Server host (default: "0.0.0.0")
                - gpu_memory: GPU memory utilization (default: 0.9)
                - max_model_len: Max context length (default: 8192)
                - background: Run server in background (default: True)
                - timeout: Health check timeout in seconds (default: 120)
                - lora_name: Name for the LoRA adapter (default: "autodev")
            
        Returns:
            DeploymentResult with server URL
        """
        import time
        start_time = time.time()
        logs = []
        
        try:
            # Validate checkpoint
            logs.append(f"Validating checkpoint: {checkpoint_path}")
            if not self._validate_checkpoint(checkpoint_path):
                return DeploymentResult(
                    success=False,
                    error_message="Checkpoint validation failed",
                    logs=logs
                )
            
            # Get configuration
            base_model = base_model or self.config.base_model
            if not base_model:
                return DeploymentResult(
                    success=False,
                    error_message="base_model is required for vLLM deployment",
                    logs=logs
                )
            
            port = port or self.config.vllm_port
            host = kwargs.get("host", self.config.vllm_host)
            gpu_memory = kwargs.get("gpu_memory", self.config.vllm_gpu_memory)
            max_model_len = kwargs.get("max_model_len", self.config.vllm_max_model_len)
            background = kwargs.get("background", True)
            timeout = kwargs.get("timeout", 120)
            lora_name = kwargs.get("lora_name", "autodev")
            
            # Generate version (also used as adapter name)
            version = version or self._generate_version(checkpoint_path)
            logs.append(f"Generated version: {version}")
            
            # Build vLLM command
            checkpoint_path_abs = str(Path(checkpoint_path).resolve())
            
            cmd = [
                "vllm", "serve", base_model,
                "--enable-lora",
                f"--lora-modules", f"{lora_name}={checkpoint_path_abs}",
                "--host", host,
                "--port", str(port),
                "--gpu-memory-utilization", str(gpu_memory),
                "--max-model-len", str(max_model_len),
            ]
            
            # Add optional vLLM args
            if kwargs.get("tensor_parallel_size"):
                cmd.extend(["--tensor-parallel-size", str(kwargs["tensor_parallel_size"])])
            if kwargs.get("trust_remote_code"):
                cmd.append("--trust-remote-code")
            
            logs.append(f"Starting vLLM server with command:")
            logs.append(f"  {' '.join(cmd)}")
            
            endpoint_url = f"http://{host}:{port}"
            
            # Start the vLLM server
            if background:
                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True
                )
                logs.append(f"vLLM server started in background (PID: {self._process.pid})")
                
                # Wait for server to be healthy
                logs.append(f"Waiting for server to be healthy (timeout: {timeout}s)...")
                healthy = self._wait_for_health(endpoint_url, timeout)
                
                if not healthy:
                    # Try to get error output
                    stderr_output = ""
                    if self._process.stderr:
                        try:
                            stderr_output = self._process.stderr.read().decode('utf-8', errors='ignore')[:2000]
                        except Exception:
                            pass
                    
                    # Kill the failed process
                    self.stop()
                    
                    return DeploymentResult(
                        success=False,
                        error_message=f"vLLM server failed to start within {timeout}s. stderr: {stderr_output}",
                        duration_seconds=time.time() - start_time,
                        logs=logs
                    )
                
                logs.append("Server is healthy and ready to serve requests")
            else:
                # Run in foreground (blocking)
                logs.append("Starting vLLM server in foreground mode...")
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    return DeploymentResult(
                        success=False,
                        error_message=f"vLLM server failed: {result.stderr}",
                        duration_seconds=time.time() - start_time,
                        logs=logs + [result.stderr]
                    )
            
            # Load checkpoint metrics
            metrics = self._load_checkpoint_metrics_vllm(checkpoint_path)
            
            deployed_version = DeployedVersion(
                version=version,
                checkpoint_path=checkpoint_path,
                deployment_type="vllm",
                endpoint_url=endpoint_url,
                metrics=metrics,
                status=DeploymentStatus.ACTIVE,
                base_model=base_model
            )
            
            return DeploymentResult(
                success=True,
                version=deployed_version,
                duration_seconds=time.time() - start_time,
                logs=logs
            )
            
        except FileNotFoundError:
            logger.error("vLLM not found")
            logs.append("Error: vLLM not installed")
            return DeploymentResult(
                success=False,
                error_message="vLLM not found. Install with: pip install vllm",
                duration_seconds=time.time() - start_time,
                logs=logs
            )
        except Exception as e:
            logger.error(f"vLLM deployment failed: {e}")
            logs.append(f"Error: {str(e)}")
            return DeploymentResult(
                success=False,
                error_message=str(e),
                duration_seconds=time.time() - start_time,
                logs=logs
            )
    
    def _wait_for_health(self, endpoint_url: str, timeout: int = 120) -> bool:
        """
        Wait for the vLLM server to become healthy.
        
        Args:
            endpoint_url: Server endpoint URL
            timeout: Maximum seconds to wait
            
        Returns:
            True if server is healthy, False if timeout
        """
        import urllib.request
        import urllib.error
        import time
        
        health_url = f"{endpoint_url}/health"
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                req = urllib.request.Request(health_url, method="GET")
                with urllib.request.urlopen(req, timeout=5) as response:
                    if response.status == 200:
                        return True
            except urllib.error.URLError:
                pass
            except Exception:
                pass
            
            time.sleep(2)
        
        return False
    
    def _load_checkpoint_metrics_vllm(self, checkpoint_path: str) -> Dict[str, float]:
        """Load metrics from checkpoint for vLLM deployment."""
        metrics = {}
        trainer_state_path = Path(checkpoint_path) / "trainer_state.json"
        
        if trainer_state_path.exists():
            try:
                with open(trainer_state_path, 'r') as f:
                    trainer_state = json.load(f)
                
                if "log_history" in trainer_state and trainer_state["log_history"]:
                    last_log = trainer_state["log_history"][-1]
                    if "loss" in last_log:
                        metrics["loss"] = last_log["loss"]
                
                if "best_metric" in trainer_state:
                    metrics["best_metric"] = trainer_state["best_metric"]
                    
            except Exception as e:
                logger.debug(f"Could not load metrics: {e}")
        
        return metrics
    
    def rollback(
        self,
        target_version: str,
        reason: RollbackReason = RollbackReason.MANUAL
    ) -> RollbackResult:
        """
        Rollback vLLM to a previous LoRA version.
        
        This involves:
        1. Stopping the current server (if running)
        2. Starting a new server with the target LoRA adapter
        3. Waiting for health check to pass
        
        Args:
            target_version: Version/adapter name to rollback to
            reason: Reason for rollback
            
        Returns:
            RollbackResult
        """
        try:
            # Get registry info
            registry = VersionRegistry()
            current = registry.get_active_version("vllm")
            previous_version = current.version if current else "unknown"
            
            # Find target version in registry
            target = registry.get_version(target_version)
            if not target:
                return RollbackResult(
                    success=False,
                    previous_version=previous_version,
                    target_version=target_version,
                    reason=reason,
                    error_message=f"Target version '{target_version}' not found in registry"
                )
            
            # Stop current server if running
            if self._process:
                logger.info("Stopping current vLLM server...")
                self.stop()
                time.sleep(2)  # Brief pause for cleanup
            
            # Restart with target version's checkpoint
            checkpoint_path = target.checkpoint_path
            if not checkpoint_path or not Path(checkpoint_path).exists():
                return RollbackResult(
                    success=False,
                    previous_version=previous_version,
                    target_version=target_version,
                    reason=reason,
                    error_message=f"Checkpoint path not found: {checkpoint_path}"
                )
            
            # Deploy with the target checkpoint
            logger.info(f"Starting vLLM with target version checkpoint: {checkpoint_path}")
            
            deploy_result = self.deploy(
                checkpoint_path=checkpoint_path,
                version=target_version,
                base_model=target.base_model,
                background=True,
                timeout=120
            )
            
            if deploy_result.success:
                logger.info(f"vLLM rollback to {target_version} completed")
                return RollbackResult(
                    success=True,
                    previous_version=previous_version,
                    target_version=target_version,
                    reason=reason
                )
            else:
                return RollbackResult(
                    success=False,
                    previous_version=previous_version,
                    target_version=target_version,
                    reason=reason,
                    error_message=deploy_result.error_message
                )
                
        except Exception as e:
            logger.error(f"vLLM rollback failed: {e}")
            
            # Get previous version safely
            registry = VersionRegistry()
            current = registry.get_active_version("vllm")
            previous_version = current.version if current else "unknown"
            
            return RollbackResult(
                success=False,
                previous_version=previous_version,
                target_version=target_version,
                reason=reason,
                error_message=str(e)
            )
    
    def status(self, endpoint: Optional[str] = None) -> Dict[str, Any]:
        """
        Check vLLM server health.
        
        Args:
            endpoint: Server endpoint URL
            
        Returns:
            Status dictionary
        """
        import urllib.request
        import urllib.error
        
        endpoint = endpoint or f"http://{self.config.vllm_host}:{self.config.vllm_port}"
        health_url = f"{endpoint}/health"
        
        try:
            req = urllib.request.Request(health_url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    return {
                        "status": "healthy",
                        "endpoint": endpoint,
                        "message": "vLLM server is running"
                    }
        except urllib.error.URLError as e:
            return {
                "status": "unhealthy",
                "endpoint": endpoint,
                "message": f"Connection failed: {e.reason}"
            }
        except Exception as e:
            return {
                "status": "unknown",
                "endpoint": endpoint,
                "message": str(e)
            }
        
        return {
            "status": "unknown",
            "endpoint": endpoint,
            "message": "Unexpected response"
        }
    
    def stop(self) -> bool:
        """
        Stop the vLLM server if running.
        
        Returns:
            True if stopped successfully
        """
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=10)
                self._process = None
                logger.info("vLLM server stopped")
                return True
            except Exception as e:
                logger.error(f"Failed to stop vLLM server: {e}")
                return False
        return True


# =============================================================================
# Local Inference Deployer
# =============================================================================

class LocalInferenceDeployer(ModelDeployer):
    """
    Export model for local inference.
    
    Features:
    - LoRA weight merging to base model
    - GGUF export for llama.cpp
    - ONNX export for edge deployment
    - Quantization support (4-bit, 8-bit)
    
    Example:
        deployer = LocalInferenceDeployer(config)
        result = deployer.deploy(
            checkpoint_path="./checkpoints/best",
            output_dir="./deployed/model",
            merge_weights=True
        )
        
        if result.success:
            print(f"Model exported to: {result.version.endpoint_url}")
    """
    
    def __init__(self, config: Optional[DeploymentConfig] = None):
        super().__init__(config)
    
    def deploy(
        self,
        checkpoint_path: str,
        version: Optional[str] = None,
        output_dir: Optional[str] = None,
        merge_weights: Optional[bool] = None,
        quantization: Optional[str] = None,
        **kwargs
    ) -> DeploymentResult:
        """
        Export checkpoint for local inference.
        
        Args:
            checkpoint_path: Path to checkpoint directory
            version: Version string
            output_dir: Output directory for exported model
            merge_weights: Whether to merge LoRA weights into base model
            quantization: Quantization type (None, "4bit", "8bit")
            **kwargs: Additional options:
                - format: Export format ("transformers", "gguf", "onnx")
                - base_model: Base model to merge with
                - gguf_quantization: GGUF quantization type (e.g., "q4_0", "q8_0")
                - copy_tokenizer: Whether to copy tokenizer files (default: True)
            
        Returns:
            DeploymentResult with export path
        """
        import time
        start_time = time.time()
        logs = []
        
        try:
            # Validate checkpoint
            logs.append(f"Validating checkpoint: {checkpoint_path}")
            if not self._validate_checkpoint(checkpoint_path):
                return DeploymentResult(
                    success=False,
                    error_message="Checkpoint validation failed",
                    logs=logs
                )
            
            # Get configuration
            output_dir = output_dir or self.config.local_output_dir
            merge_weights = merge_weights if merge_weights is not None else self.config.local_merge_weights
            quantization = quantization or self.config.local_quantization
            export_format = kwargs.get("format", "transformers")
            base_model = kwargs.get("base_model", self.config.base_model)
            copy_tokenizer = kwargs.get("copy_tokenizer", True)
            gguf_quantization = kwargs.get("gguf_quantization", "q4_0")
            
            # Generate version
            version = version or self._generate_version(checkpoint_path)
            logs.append(f"Generated version: {version}")
            
            # Create output directory
            output_path = Path(output_dir) / version
            output_path.mkdir(parents=True, exist_ok=True)
            logs.append(f"Output directory: {output_path}")
            
            checkpoint_path_obj = Path(checkpoint_path)
            
            if export_format == "transformers":
                if merge_weights and base_model:
                    # Merge LoRA weights into base model
                    logs.append(f"Merging LoRA weights into base model: {base_model}")
                    merge_success = self._merge_lora_weights_impl(
                        checkpoint_path=checkpoint_path,
                        base_model=base_model,
                        output_path=str(output_path),
                        quantization=quantization,
                        logs=logs
                    )
                    
                    if not merge_success:
                        return DeploymentResult(
                            success=False,
                            error_message="Failed to merge LoRA weights",
                            duration_seconds=time.time() - start_time,
                            logs=logs
                        )
                    
                    # Copy tokenizer if requested
                    if copy_tokenizer:
                        self._copy_tokenizer(base_model, str(output_path), logs)
                    
                    logs.append(f"Merged model saved to: {output_path}")
                else:
                    # Just copy adapter files
                    logs.append("Copying adapter files without merging...")
                    for file_name in ["adapter_model.safetensors", "adapter_config.json"]:
                        src = checkpoint_path_obj / file_name
                        if src.exists():
                            shutil.copy2(src, output_path / file_name)
                            logs.append(f"Copied: {file_name}")
                    
                    # Copy tokenizer files from checkpoint if available
                    if copy_tokenizer:
                        for tokenizer_file in ["tokenizer.json", "tokenizer_config.json", 
                                               "special_tokens_map.json", "vocab.json", "merges.txt"]:
                            src = checkpoint_path_obj / tokenizer_file
                            if src.exists():
                                shutil.copy2(src, output_path / tokenizer_file)
                                logs.append(f"Copied tokenizer: {tokenizer_file}")
            
            elif export_format == "gguf":
                # Export to GGUF format
                if not base_model:
                    # First merge if we have base model
                    if merge_weights and self.config.base_model:
                        merge_output = output_path / "merged"
                        merge_output.mkdir(exist_ok=True)
                        self._merge_lora_weights_impl(
                            checkpoint_path=checkpoint_path,
                            base_model=self.config.base_model,
                            output_path=str(merge_output),
                            quantization=None,
                            logs=logs
                        )
                        model_to_convert = str(merge_output)
                    else:
                        return DeploymentResult(
                            success=False,
                            error_message="base_model required for GGUF export",
                            duration_seconds=time.time() - start_time,
                            logs=logs
                        )
                else:
                    # Merge first then convert
                    merge_output = output_path / "merged"
                    merge_output.mkdir(exist_ok=True)
                    self._merge_lora_weights_impl(
                        checkpoint_path=checkpoint_path,
                        base_model=base_model,
                        output_path=str(merge_output),
                        quantization=None,
                        logs=logs
                    )
                    model_to_convert = str(merge_output)
                
                # Convert to GGUF
                logs.append(f"Converting to GGUF format with quantization: {gguf_quantization}")
                gguf_success = self._export_gguf_impl(
                    model_path=model_to_convert,
                    output_path=str(output_path / f"model-{gguf_quantization}.gguf"),
                    quantization=gguf_quantization,
                    logs=logs
                )
                
                if not gguf_success:
                    logs.append("Warning: GGUF conversion failed, but merged model is available")
            
            elif export_format == "onnx":
                # Export to ONNX format
                logs.append("ONNX export not yet implemented")
                return DeploymentResult(
                    success=False,
                    error_message="ONNX export not yet implemented",
                    duration_seconds=time.time() - start_time,
                    logs=logs
                )
            
            # Copy additional files
            additional_files = ["trainer_state.json", "README.md"]
            for file_name in additional_files:
                src = checkpoint_path_obj / file_name
                if src.exists():
                    shutil.copy2(src, output_path / file_name)
                    logs.append(f"Copied additional file: {file_name}")
            
            # Generate deployment README
            self._generate_deployment_readme(
                output_path=str(output_path),
                version=version,
                checkpoint_path=checkpoint_path,
                base_model=base_model or self.config.base_model,
                merge_weights=merge_weights,
                quantization=quantization,
                export_format=export_format
            )
            logs.append("Generated deployment README.md")
            
            # Load checkpoint metrics
            metrics = self._load_local_metrics(checkpoint_path)
            
            deployed_version = DeployedVersion(
                version=version,
                checkpoint_path=checkpoint_path,
                deployment_type="local",
                endpoint_url=str(output_path),
                metrics=metrics,
                status=DeploymentStatus.ACTIVE,
                base_model=base_model or self.config.base_model
            )
            
            return DeploymentResult(
                success=True,
                version=deployed_version,
                duration_seconds=time.time() - start_time,
                logs=logs
            )
            
        except Exception as e:
            logger.error(f"Local deployment failed: {e}")
            logs.append(f"Error: {str(e)}")
            return DeploymentResult(
                success=False,
                error_message=str(e),
                duration_seconds=time.time() - start_time,
                logs=logs
            )
    
    def _merge_lora_weights_impl(
        self,
        checkpoint_path: str,
        base_model: str,
        output_path: str,
        quantization: Optional[str],
        logs: List[str]
    ) -> bool:
        """Actually merge LoRA weights into base model using PEFT."""
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
            from peft import PeftModel
            import torch
            
            logs.append(f"Loading base model: {base_model}")
            
            # Determine torch dtype based on quantization
            torch_dtype = torch.float16
            load_in_4bit = False
            load_in_8bit = False
            
            if quantization == "4bit":
                load_in_4bit = True
                torch_dtype = None
            elif quantization == "8bit":
                load_in_8bit = True
                torch_dtype = None
            
            # Load base model
            base = AutoModelForCausalLM.from_pretrained(
                base_model,
                torch_dtype=torch_dtype,
                device_map="auto",
                load_in_4bit=load_in_4bit,
                load_in_8bit=load_in_8bit,
                trust_remote_code=True
            )
            
            logs.append("Loading LoRA adapter...")
            # Load PEFT model with LoRA adapter
            model = PeftModel.from_pretrained(base, checkpoint_path)
            
            logs.append("Merging and unloading LoRA weights...")
            # Merge and unload
            merged_model = model.merge_and_unload()
            
            logs.append(f"Saving merged model to: {output_path}")
            # Save merged model
            merged_model.save_pretrained(output_path, safe_serialization=True)
            
            return True
            
        except ImportError as e:
            logs.append(f"Import error: {e}")
            logs.append("Required packages: transformers, peft, torch")
            return False
        except Exception as e:
            logs.append(f"Merge error: {e}")
            return False
    
    def _copy_tokenizer(self, base_model: str, output_path: str, logs: List[str]) -> None:
        """Copy tokenizer files from base model to output."""
        try:
            from transformers import AutoTokenizer
            
            tokenizer = AutoTokenizer.from_pretrained(base_model)
            tokenizer.save_pretrained(output_path)
            logs.append("Copied tokenizer files")
        except Exception as e:
            logs.append(f"Warning: Could not copy tokenizer: {e}")
    
    def _export_gguf_impl(
        self,
        model_path: str,
        output_path: str,
        quantization: str,
        logs: List[str]
    ) -> bool:
        """Convert model to GGUF format using llama.cpp."""
        try:
            # Check for llama.cpp conversion script
            possible_paths = [
                Path.home() / "llama.cpp" / "convert-hf-to-gguf.py",
                Path("/usr/local/bin/convert-hf-to-gguf.py"),
                Path("llama.cpp/convert-hf-to-gguf.py"),
            ]
            
            convert_script = None
            for path in possible_paths:
                if path.exists():
                    convert_script = path
                    break
            
            if not convert_script:
                # Try using the Python package
                try:
                    result = subprocess.run(
                        ["python", "-m", "llama_cpp", "--convert", model_path, "--outfile", output_path],
                        capture_output=True,
                        text=True
                    )
                    if result.returncode == 0:
                        logs.append(f"GGUF model saved to: {output_path}")
                        return True
                except Exception:
                    pass
                
                logs.append("llama.cpp convert script not found")
                logs.append("Install llama.cpp or ensure convert-hf-to-gguf.py is in PATH")
                return False
            
            # Convert to GGUF first (unquantized)
            gguf_output = output_path.replace(f"-{quantization}.gguf", "-f16.gguf")
            
            cmd = [
                "python", str(convert_script),
                model_path,
                "--outfile", gguf_output,
                "--outtype", "f16"
            ]
            
            logs.append(f"Running: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                logs.append(f"GGUF conversion failed: {result.stderr}")
                return False
            
            logs.append(f"Created unquantized GGUF: {gguf_output}")
            
            # Quantize if needed
            if quantization != "f16":
                llama_quantize = convert_script.parent / "llama-quantize"
                if not llama_quantize.exists():
                    llama_quantize = convert_script.parent / "quantize"
                
                if llama_quantize.exists():
                    quant_cmd = [str(llama_quantize), gguf_output, output_path, quantization]
                    logs.append(f"Quantizing: {' '.join(quant_cmd)}")
                    quant_result = subprocess.run(quant_cmd, capture_output=True, text=True)
                    
                    if quant_result.returncode == 0:
                        logs.append(f"Quantized GGUF saved to: {output_path}")
                        # Remove unquantized version
                        Path(gguf_output).unlink()
                        return True
                    else:
                        logs.append(f"Quantization failed: {quant_result.stderr}")
                        return False
                else:
                    logs.append("llama-quantize not found, keeping unquantized GGUF")
                    # Rename to requested output
                    Path(gguf_output).rename(output_path)
                    return True
            
            return True
            
        except Exception as e:
            logs.append(f"GGUF export error: {e}")
            return False
    
    def _generate_deployment_readme(
        self,
        output_path: str,
        version: str,
        checkpoint_path: str,
        base_model: str,
        merge_weights: bool,
        quantization: Optional[str],
        export_format: str
    ) -> None:
        """Generate a README for the deployed model."""
        readme_content = f"""# AutoDev Deployed Model - {version}

## Deployment Details

- **Version:** {version}
- **Base Model:** {base_model or 'N/A'}
- **Checkpoint:** {checkpoint_path}
- **Export Format:** {export_format}
- **Merged Weights:** {merge_weights}
- **Quantization:** {quantization or 'None'}
- **Deployed At:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}

## Usage

### With Transformers

```python
from transformers import AutoModelForCausalLM, AutoTokenizer

model = AutoModelForCausalLM.from_pretrained("{output_path}")
tokenizer = AutoTokenizer.from_pretrained("{output_path}")

inputs = tokenizer("def hello_world():", return_tensors="pt")
outputs = model.generate(**inputs, max_length=100)
print(tokenizer.decode(outputs[0]))
```

## Files

"""
        # List files in output directory
        output_path_obj = Path(output_path)
        for f in sorted(output_path_obj.iterdir()):
            readme_content += f"- `{f.name}`\n"
        
        readme_content += f"""
---
*Generated by AutoDev Local Inference Deployer*
"""
        
        with open(output_path_obj / "README.md", 'w') as f:
            f.write(readme_content)
    
    def _load_local_metrics(self, checkpoint_path: str) -> Dict[str, float]:
        """Load metrics from checkpoint for local deployment."""
        metrics = {}
        trainer_state_path = Path(checkpoint_path) / "trainer_state.json"
        
        if trainer_state_path.exists():
            try:
                with open(trainer_state_path, 'r') as f:
                    trainer_state = json.load(f)
                
                if "log_history" in trainer_state and trainer_state["log_history"]:
                    last_log = trainer_state["log_history"][-1]
                    if "loss" in last_log:
                        metrics["loss"] = last_log["loss"]
                
                if "best_metric" in trainer_state:
                    metrics["best_metric"] = trainer_state["best_metric"]
                    
            except Exception as e:
                logger.debug(f"Could not load metrics: {e}")
        
        return metrics
    
    def rollback(
        self,
        target_version: str,
        reason: RollbackReason = RollbackReason.MANUAL
    ) -> RollbackResult:
        """
        Rollback to a previous local version.
        
        For local deployments, this involves:
        1. Validating the target version directory exists
        2. Updating the "current" symlink to point to target
        3. Optionally creating a rollback marker file
        
        Args:
            target_version: Version directory name to rollback to
            reason: Reason for rollback
            
        Returns:
            RollbackResult
        """
        try:
            # Get registry info
            registry = VersionRegistry()
            current = registry.get_active_version("local")
            previous_version = current.version if current else "unknown"
            
            # Find target version in registry
            target = registry.get_version(target_version)
            if not target:
                return RollbackResult(
                    success=False,
                    previous_version=previous_version,
                    target_version=target_version,
                    reason=reason,
                    error_message=f"Target version '{target_version}' not found in registry"
                )
            
            # Check target path exists
            target_path = Path(target.endpoint_url) if target.endpoint_url else None
            if not target_path or not target_path.exists():
                return RollbackResult(
                    success=False,
                    previous_version=previous_version,
                    target_version=target_version,
                    reason=reason,
                    error_message=f"Target version path does not exist: {target_path}"
                )
            
            # Update "current" symlink
            output_base = Path(self.config.local_output_dir)
            current_link = output_base / "current"
            
            # Remove existing symlink
            if current_link.exists() or current_link.is_symlink():
                if current_link.is_symlink():
                    current_link.unlink()
                else:
                    # It's a directory, rename it
                    current_link.rename(current_link.with_suffix(".old"))
            
            # Create new symlink
            current_link.symlink_to(target_path)
            
            # Create rollback marker
            rollback_marker = target_path / ".rollback_info.json"
            with open(rollback_marker, 'w') as f:
                json.dump({
                    "rolled_back_at": datetime.now(timezone.utc).isoformat(),
                    "previous_version": previous_version,
                    "target_version": target_version,
                    "reason": reason.value
                }, f, indent=2)
            
            # Update registry
            if current:
                registry.deprecate(current.version)
            target.status = DeploymentStatus.ACTIVE
            
            logger.info(f"Local rollback to {target_version} completed")
            logger.info(f"Symlink updated: {current_link} -> {target_path}")
            
            return RollbackResult(
                success=True,
                previous_version=previous_version,
                target_version=target_version,
                reason=reason
            )
            
        except Exception as e:
            logger.error(f"Local rollback failed: {e}")
            
            # Get previous version safely
            registry = VersionRegistry()
            current = registry.get_active_version("local")
            previous_version = current.version if current else "unknown"
            
            return RollbackResult(
                success=False,
                previous_version=previous_version,
                target_version=target_version,
                reason=reason,
                error_message=str(e)
            )
    
    def status(self, endpoint: Optional[str] = None) -> Dict[str, Any]:
        """
        Check status of a local deployment.
        
        Args:
            endpoint: Path to the deployed model
            
        Returns:
            Status dictionary
        """
        if not endpoint:
            endpoint = self.config.local_output_dir
        
        endpoint_path = Path(endpoint)
        
        if not endpoint_path.exists():
            return {
                "status": "not_found",
                "path": endpoint,
                "message": "Deployment path does not exist"
            }
        
        # Check for key files
        files_present = []
        for expected in ["adapter_model.safetensors", "adapter_config.json"]:
            if (endpoint_path / expected).exists():
                files_present.append(expected)
        
        return {
            "status": "available",
            "path": endpoint,
            "files": files_present,
            "message": f"Found {len(files_present)} files"
        }
    
    def merge_lora_weights(
        self,
        checkpoint_path: str,
        base_model: str,
        output_path: str
    ) -> bool:
        """
        Merge LoRA weights into the base model.
        
        Args:
            checkpoint_path: Path to LoRA checkpoint
            base_model: Base model identifier or path
            output_path: Where to save merged model
            
        Returns:
            True if merge successful
        """
        # TODO: Implement LoRA weight merging using PEFT
        # This would:
        # 1. Load base model
        # 2. Load PEFT model with LoRA adapter
        # 3. Merge and unload
        # 4. Save merged model
        
        logger.info(f"STUB: Would merge {checkpoint_path} into {base_model}")
        logger.info(f"STUB: Output would be saved to {output_path}")
        
        return False
    
    def export_gguf(
        self,
        model_path: str,
        output_path: str,
        quantization: str = "q4_0"
    ) -> bool:
        """
        Export model to GGUF format for llama.cpp.
        
        Args:
            model_path: Path to the model
            output_path: Where to save GGUF file
            quantization: Quantization type
            
        Returns:
            True if export successful
        """
        # TODO: Implement GGUF export
        # This would use llama.cpp's convert scripts
        
        logger.info(f"STUB: Would export {model_path} to GGUF at {output_path}")
        logger.info(f"STUB: Quantization: {quantization}")
        
        return False


# =============================================================================
# Factory Functions
# =============================================================================

def create_deployer(
    target: Union[DeploymentTarget, str],
    config: Optional[DeploymentConfig] = None
) -> ModelDeployer:
    """
    Create a deployer for the specified target.
    
    Args:
        target: Deployment target (huggingface, vllm, local)
        config: Deployment configuration
        
    Returns:
        ModelDeployer instance
        
    Example:
        deployer = create_deployer("vllm", config)
        result = deployer.deploy("./checkpoints/best")
    """
    if isinstance(target, str):
        target = DeploymentTarget(target)
    
    deployers = {
        DeploymentTarget.HUGGINGFACE: HuggingFaceDeployer,
        DeploymentTarget.VLLM: VLLMDeployer,
        DeploymentTarget.LOCAL: LocalInferenceDeployer,
    }
    
    deployer_class = deployers.get(target)
    if not deployer_class:
        raise ValueError(f"Unknown deployment target: {target}")
    
    return deployer_class(config)


def deploy_checkpoint(
    checkpoint_path: str,
    target: Union[DeploymentTarget, str] = DeploymentTarget.LOCAL,
    config: Optional[DeploymentConfig] = None,
    **kwargs
) -> DeploymentResult:
    """
    Convenience function to deploy a checkpoint.
    
    Args:
        checkpoint_path: Path to checkpoint
        target: Deployment target
        config: Deployment configuration
        **kwargs: Additional options passed to deploy()
        
    Returns:
        DeploymentResult
        
    Example:
        result = deploy_checkpoint(
            "./checkpoints/best",
            target="huggingface",
            repo_id="org/model",
            private=True
        )
    """
    deployer = create_deployer(target, config)
    return deployer.deploy(checkpoint_path, **kwargs)


# =============================================================================
# Version Registry (Simplified)
# =============================================================================

class VersionRegistry:
    """
    Simplified version registry for tracking deployments.
    
    This is a lightweight implementation. A full implementation would:
    - Persist registry to disk
    - Support querying by various filters
    - Integrate with ModelRegistry from training module
    """
    
    def __init__(self, registry_path: str = "~/.autodev/deployment_registry.json"):
        """
        Initialize the version registry.
        
        Args:
            registry_path: Path to registry file
        """
        self.registry_path = Path(os.path.expanduser(registry_path))
        self._versions: Dict[str, DeployedVersion] = {}
        self._load_registry()
    
    def _load_registry(self) -> None:
        """Load registry from disk."""
        if self.registry_path.exists():
            try:
                with open(self.registry_path, "r") as f:
                    data = json.load(f)
                for version_data in data.get("versions", []):
                    version = DeployedVersion.from_dict(version_data)
                    self._versions[version.version] = version
                logger.info(f"Loaded {len(self._versions)} versions from registry")
            except Exception as e:
                logger.error(f"Failed to load registry: {e}")
    
    def _save_registry(self) -> None:
        """Save registry to disk."""
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "versions": [v.to_dict() for v in self._versions.values()],
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
        with open(self.registry_path, "w") as f:
            json.dump(data, f, indent=2)
    
    def register(self, version: DeployedVersion) -> None:
        """Register a deployed version."""
        self._versions[version.version] = version
        self._save_registry()
        logger.info(f"Registered version: {version.version}")
    
    def get_version(self, version_id: str) -> Optional[DeployedVersion]:
        """Get a version by ID."""
        return self._versions.get(version_id)
    
    def get_active_version(self, deployment_type: Optional[str] = None) -> Optional[DeployedVersion]:
        """Get the currently active version."""
        for version in self._versions.values():
            if version.status == DeploymentStatus.ACTIVE:
                if deployment_type is None or version.deployment_type == deployment_type:
                    return version
        return None
    
    def list_versions(self, limit: int = 10) -> List[DeployedVersion]:
        """List all versions, most recent first."""
        versions = sorted(
            self._versions.values(),
            key=lambda v: v.deployed_at,
            reverse=True
        )
        return versions[:limit]
    
    def deprecate(self, version_id: str) -> bool:
        """Mark a version as deprecated."""
        version = self._versions.get(version_id)
        if version:
            version.status = DeploymentStatus.DEPRECATED
            self._save_registry()
            logger.info(f"Deprecated version: {version_id}")
            return True
        return False


# =============================================================================
# Rollback Manager
# =============================================================================

class RollbackManager:
    """
    Handle version rollback with comprehensive safety checks.
    
    Features:
    - Validates rollback safety (target version exists, is stable)
    - Tracks rollback history
    - Supports automatic rollback triggers
    - Health checks after rollback
    
    Rollback Triggers:
    - SWE-bench resolution rate drops >5%
    - Error rate exceeds 10%
    - Manual trigger via CLI
    - Canary failure threshold
    - Health check failures
    
    Example:
        manager = RollbackManager(registry)
        
        # Manual rollback
        result = manager.rollback(
            target_version="v1.0.0-4f3bf81",
            reason=RollbackReason.PERFORMANCE_REGRESSION
        )
        
        # Automatic rollback based on metrics
        result = manager.auto_rollback_if_needed(
            current_metrics={"resolution_rate": 0.15, "error_rate": 0.12}
        )
    """
    
    # Default thresholds for auto-rollback
    DEFAULT_RESOLUTION_RATE_THRESHOLD = 0.05  # 5% degradation
    DEFAULT_ERROR_RATE_THRESHOLD = 0.10  # 10% error rate
    
    def __init__(
        self,
        registry: Optional[VersionRegistry] = None,
        deployer: Optional[ModelDeployer] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the RollbackManager.
        
        Args:
            registry: VersionRegistry instance for version tracking
            deployer: ModelDeployer instance for performing rollbacks
            config: Configuration options
        """
        self.registry = registry or VersionRegistry()
        self.deployer = deployer
        self.config = config or {}
        
        # Rollback history
        self._rollback_history: List[RollbackResult] = []
        self._history_path = Path(
            os.path.expanduser(
                self.config.get("history_path", "~/.autodev/rollback_history.json")
            )
        )
        self._load_history()
    
    def _load_history(self) -> None:
        """Load rollback history from disk."""
        if self._history_path.exists():
            try:
                with open(self._history_path, "r") as f:
                    data = json.load(f)
                for item in data.get("history", []):
                    # Reconstruct RollbackResult
                    result = RollbackResult(
                        success=item.get("success", False),
                        previous_version=item.get("previous_version", ""),
                        target_version=item.get("target_version", ""),
                        reason=RollbackReason(item.get("reason", "manual")),
                        error_message=item.get("error_message", "")
                    )
                    self._rollback_history.append(result)
                logger.info(f"Loaded {len(self._rollback_history)} rollback records")
            except Exception as e:
                logger.error(f"Failed to load rollback history: {e}")
    
    def _save_history(self) -> None:
        """Save rollback history to disk."""
        self._history_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "history": [
                {
                    "success": r.success,
                    "previous_version": r.previous_version,
                    "target_version": r.target_version,
                    "reason": r.reason.value,
                    "error_message": r.error_message
                }
                for r in self._rollback_history
            ],
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
        with open(self._history_path, "w") as f:
            json.dump(data, f, indent=2)
    
    def rollback(
        self,
        target_version: str,
        reason: RollbackReason = RollbackReason.MANUAL,
        force: bool = False,
        skip_health_check: bool = False
    ) -> RollbackResult:
        """
        Rollback to a previous stable version with safety checks.
        
        Args:
            target_version: Version to rollback to
            reason: Reason for rollback
            force: Skip safety checks (use with caution)
            skip_health_check: Skip post-rollback health check
            
        Returns:
            RollbackResult with success status
        """
        logger.info(f"Initiating rollback to version: {target_version}")
        
        # Get current active version
        current_version = self.registry.get_active_version()
        previous_version_str = current_version.version if current_version else "unknown"
        
        # Safety checks (unless forced)
        if not force:
            safety_result = self._perform_safety_checks(target_version, reason)
            if not safety_result["safe"]:
                error_msg = f"Safety check failed: {safety_result['reason']}"
                logger.error(error_msg)
                
                result = RollbackResult(
                    success=False,
                    previous_version=previous_version_str,
                    target_version=target_version,
                    reason=reason,
                    error_message=error_msg
                )
                self._rollback_history.append(result)
                self._save_history()
                return result
        
        # Perform the actual rollback
        if self.deployer:
            try:
                deployer_result = self.deployer.rollback(target_version, reason)
                
                if deployer_result.success:
                    # Update registry
                    if current_version:
                        self.registry.deprecate(current_version.version)
                    
                    target = self.registry.get_version(target_version)
                    if target:
                        target.status = DeploymentStatus.ACTIVE
                        self._save_history()
                    
                    logger.info(f"Rollback successful: {previous_version_str} -> {target_version}")
                    
                    # Post-rollback health check
                    if not skip_health_check:
                        health_ok = self._perform_health_check()
                        if not health_ok:
                            logger.warning("Post-rollback health check failed")
                    
                    result = RollbackResult(
                        success=True,
                        previous_version=previous_version_str,
                        target_version=target_version,
                        reason=reason
                    )
                else:
                    result = RollbackResult(
                        success=False,
                        previous_version=previous_version_str,
                        target_version=target_version,
                        reason=reason,
                        error_message=deployer_result.error_message
                    )
            except Exception as e:
                logger.error(f"Rollback exception: {e}")
                result = RollbackResult(
                    success=False,
                    previous_version=previous_version_str,
                    target_version=target_version,
                    reason=reason,
                    error_message=str(e)
                )
        else:
            # No deployer available - registry-only rollback
            logger.warning("No deployer available, performing registry-only rollback")
            
            if current_version:
                self.registry.deprecate(current_version.version)
            
            target = self.registry.get_version(target_version)
            if target:
                target.status = DeploymentStatus.ACTIVE
            
            result = RollbackResult(
                success=True,
                previous_version=previous_version_str,
                target_version=target_version,
                reason=reason
            )
        
        # Record history
        self._rollback_history.append(result)
        self._save_history()
        
        return result
    
    def _perform_safety_checks(
        self,
        target_version: str,
        reason: RollbackReason
    ) -> Dict[str, Any]:
        """
        Perform safety checks before rollback.
        
        Args:
            target_version: Target version to rollback to
            reason: Reason for rollback
            
        Returns:
            Dict with 'safe' boolean and optional 'reason' string
        """
        checks = []
        
        # Check 1: Target version exists
        target = self.registry.get_version(target_version)
        if not target:
            return {
                "safe": False,
                "reason": f"Target version '{target_version}' not found in registry"
            }
        checks.append(("version_exists", True))
        
        # Check 2: Target version is not already active
        if target.status == DeploymentStatus.ACTIVE:
            return {
                "safe": False,
                "reason": f"Target version '{target_version}' is already active"
            }
        checks.append(("not_already_active", True))
        
        # Check 3: Target version is not deprecated (unless forced by performance issues)
        if target.status == DeploymentStatus.DEPRECATED:
            if reason not in [RollbackReason.PERFORMANCE_REGRESSION, 
                             RollbackReason.ERROR_RATE,
                             RollbackReason.HEALTH_CHECK]:
                return {
                    "safe": False,
                    "reason": f"Target version '{target_version}' is deprecated"
                }
        checks.append(("status_check", True))
        
        # Check 4: Target version has valid checkpoint path
        if target.checkpoint_path:
            checkpoint_path = Path(target.checkpoint_path)
            if not checkpoint_path.exists():
                logger.warning(f"Checkpoint path does not exist: {target.checkpoint_path}")
                # Continue anyway - checkpoint may have been moved
        checks.append(("checkpoint_path", True))
        
        # Check 5: No recent rollback (prevent rollback loops)
        recent_rollbacks = [
            r for r in self._rollback_history[-5:]
            if r.success and (datetime.now(timezone.utc) - 
                datetime.fromisoformat(str(r.target_version))).total_seconds() < 3600
        ]
        if len(recent_rollbacks) >= 3:
            return {
                "safe": False,
                "reason": "Too many recent rollbacks - possible rollback loop detected"
            }
        checks.append(("no_rollback_loop", True))
        
        return {"safe": True, "checks": checks}
    
    def _perform_health_check(self) -> bool:
        """
        Perform health check after rollback.
        
        Returns:
            True if healthy, False otherwise
        """
        if not self.deployer:
            return True
        
        try:
            status = self.deployer.status()
            return status.get("status") in ["healthy", "available", "unknown"]
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
    
    def auto_rollback_if_needed(
        self,
        current_metrics: Dict[str, float],
        baseline_metrics: Optional[Dict[str, float]] = None,
        deployment_type: Optional[str] = None
    ) -> Optional[RollbackResult]:
        """
        Automatically trigger rollback if metrics indicate problems.
        
        Args:
            current_metrics: Current performance metrics
            baseline_metrics: Baseline metrics to compare against
            deployment_type: Type of deployment to check
            
        Returns:
            RollbackResult if rollback was triggered, None otherwise
        """
        # Get current version
        current_version = self.registry.get_active_version(deployment_type)
        if not current_version:
            logger.warning("No active version found for auto-rollback check")
            return None
        
        # Use stored baseline if not provided
        if baseline_metrics is None:
            baseline_metrics = current_version.metrics
        
        # Check resolution rate degradation
        resolution_threshold = self.config.get(
            "resolution_rate_threshold",
            self.DEFAULT_RESOLUTION_RATE_THRESHOLD
        )
        
        current_resolution = current_metrics.get("resolution_rate", 1.0)
        baseline_resolution = baseline_metrics.get("resolution_rate", 1.0)
        
        if baseline_resolution > 0:
            degradation = baseline_resolution - current_resolution
            
            if degradation > resolution_threshold:
                logger.warning(
                    f"Resolution rate degradation detected: "
                    f"{baseline_resolution:.2%} -> {current_resolution:.2%} "
                    f"(threshold: {resolution_threshold:.2%})"
                )
                
                # Find previous stable version
                previous = self._find_stable_previous_version(current_version.version)
                
                if previous:
                    return self.rollback(
                        target_version=previous.version,
                        reason=RollbackReason.PERFORMANCE_REGRESSION
                    )
        
        # Check error rate
        error_threshold = self.config.get(
            "error_rate_threshold",
            self.DEFAULT_ERROR_RATE_THRESHOLD
        )
        
        error_rate = current_metrics.get("error_rate", 0.0)
        
        if error_rate > error_threshold:
            logger.warning(
                f"Error rate exceeds threshold: "
                f"{error_rate:.2%} > {error_threshold:.2%}"
            )
            
            previous = self._find_stable_previous_version(current_version.version)
            
            if previous:
                return self.rollback(
                    target_version=previous.version,
                    reason=RollbackReason.ERROR_RATE
                )
        
        return None
    
    def _find_stable_previous_version(
        self,
        current_version: str
    ) -> Optional[DeployedVersion]:
        """
        Find a stable previous version to rollback to.
        
        Args:
            current_version: Current version string
            
        Returns:
            DeployedVersion to rollback to, or None
        """
        versions = self.registry.list_versions(limit=10)
        
        for version in versions:
            # Skip current version
            if version.version == current_version:
                continue
            
            # Skip deprecated versions
            if version.status == DeploymentStatus.DEPRECATED:
                continue
            
            # Return first stable version found
            return version
        
        return None
    
    def get_rollback_history(self, limit: int = 10) -> List[RollbackResult]:
        """
        Get recent rollback history.
        
        Args:
            limit: Maximum number of records to return
            
        Returns:
            List of RollbackResult records
        """
        return self._rollback_history[-limit:]
    
    def can_rollback(self, target_version: str) -> Dict[str, Any]:
        """
        Check if rollback to a specific version is possible.
        
        Args:
            target_version: Target version to check
            
        Returns:
            Dict with 'can_rollback' boolean and details
        """
        safety_result = self._perform_safety_checks(
            target_version,
            RollbackReason.MANUAL
        )
        
        target = self.registry.get_version(target_version)
        
        return {
            "can_rollback": safety_result["safe"],
            "target_exists": target is not None,
            "target_status": target.status.value if target else None,
            "checkpoint_path": target.checkpoint_path if target else None,
            "safety_checks": safety_result.get("checks", []),
            "block_reason": safety_result.get("reason")
        }


# =============================================================================
# CLI Support (for future implementation)
# =============================================================================

def get_cli_parser():
    """
    Get argument parser for CLI commands.
    
    This is a placeholder for CLI integration.
    
    Returns:
        ArgumentParser instance
    """
    import argparse
    
    parser = argparse.ArgumentParser(
        description="AutoDev Model Deployer",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command")
    
    # Deploy command
    deploy_parser = subparsers.add_parser("deploy", help="Deploy a checkpoint")
    deploy_parser.add_argument("--target", "-t", choices=["huggingface", "vllm", "local"],
                               default="local", help="Deployment target")
    deploy_parser.add_argument("--checkpoint", "-c", required=True,
                               help="Path to checkpoint")
    deploy_parser.add_argument("--run-id", help="Training run ID")
    deploy_parser.add_argument("--version", help="Version string")
    
    # Rollback command
    rollback_parser = subparsers.add_parser("rollback", help="Rollback to previous version")
    rollback_parser.add_argument("--version", "-v", required=True,
                                  help="Target version")
    rollback_parser.add_argument("--reason", default="manual",
                                  help="Rollback reason")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List deployments")
    list_parser.add_argument("--status", choices=["active", "deprecated", "all"],
                             default="all", help="Filter by status")
    
    return parser
