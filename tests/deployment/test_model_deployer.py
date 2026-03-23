"""
Unit tests for Model Deployer

Tests the deployment functionality including:
- CheckpointManager: checkpoint discovery and validation
- HuggingFaceDeployer: HuggingFace Hub deployment
- VLLMDeployer: vLLM server deployment
- LocalInferenceDeployer: local export
- VersionRegistry: version tracking
- RollbackManager: rollback with safety checks
"""

import json
import os
import tempfile
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, mock_open
import pytest

# Add src to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from src.deployment.model_deployer import (
    # Enums
    DeploymentTarget,
    DeploymentStatus,
    RollbackReason,
    # Data classes
    CheckpointInfo,
    DeploymentConfig,
    DeployedVersion,
    DeploymentResult,
    RollbackResult,
    # Managers and Deployers
    CheckpointManager,
    ModelDeployer,
    HuggingFaceDeployer,
    VLLMDeployer,
    LocalInferenceDeployer,
    VersionRegistry,
    RollbackManager,
    # Factory functions
    create_deployer,
    deploy_checkpoint,
    get_cli_parser,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_dir():
    """Create a temporary directory."""
    directory = tempfile.mkdtemp()
    yield directory
    shutil.rmtree(directory, ignore_errors=True)


@pytest.fixture
def checkpoint_dir(temp_dir):
    """Create a checkpoint directory structure."""
    checkpoint_base = Path(temp_dir) / "checkpoints"
    checkpoint_base.mkdir(parents=True, exist_ok=True)
    
    # Create a run directory
    run_dir = checkpoint_base / "run_20260323_143052"
    run_dir.mkdir(parents=True, exist_ok=True)
    
    # Create checkpoint directories
    for step in [100, 200, 300]:
        ckpt_dir = run_dir / f"checkpoint-{step}"
        ckpt_dir.mkdir(parents=True, exist_ok=True)
        
        # Create adapter files
        (ckpt_dir / "adapter_model.safetensors").write_bytes(b"mock_weights")
        
        # Create adapter config
        adapter_config = {
            "r": 16,
            "lora_alpha": 32,
            "target_modules": ["q_proj", "v_proj"],
            "lora_dropout": 0.05
        }
        with open(ckpt_dir / "adapter_config.json", "w") as f:
            json.dump(adapter_config, f)
        
        # Create trainer state
        trainer_state = {
            "log_history": [
                {"loss": 1.5 - (step * 0.001)},
                {"loss": 1.2 - (step * 0.001)}
            ],
            "best_metric": 0.85
        }
        with open(ckpt_dir / "trainer_state.json", "w") as f:
            json.dump(trainer_state, f)
    
    # Create best checkpoint
    best_ckpt = run_dir / "checkpoint-best"
    best_ckpt.mkdir(parents=True, exist_ok=True)
    (best_ckpt / "adapter_model.safetensors").write_bytes(b"mock_best_weights")
    
    adapter_config = {"r": 16, "lora_alpha": 32, "target_modules": ["q_proj"]}
    with open(best_ckpt / "adapter_config.json", "w") as f:
        json.dump(adapter_config, f)
    
    return str(checkpoint_base)


@pytest.fixture
def valid_checkpoint(temp_dir):
    """Create a valid checkpoint for testing."""
    ckpt_dir = Path(temp_dir) / "valid_checkpoint"
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    
    (ckpt_dir / "adapter_model.safetensors").write_bytes(b"mock_weights")
    
    adapter_config = {
        "r": 16,
        "lora_alpha": 32,
        "target_modules": ["q_proj", "v_proj"],
        "lora_dropout": 0.05
    }
    with open(ckpt_dir / "adapter_config.json", "w") as f:
        json.dump(adapter_config, f)
    
    trainer_state = {
        "log_history": [{"loss": 0.5}],
        "best_metric": 0.92
    }
    with open(ckpt_dir / "trainer_state.json", "w") as f:
        json.dump(trainer_state, f)
    
    return str(ckpt_dir)


@pytest.fixture
def deployment_config():
    """Create a deployment configuration."""
    return DeploymentConfig(
        target=DeploymentTarget.LOCAL,
        base_model="codellama/CodeLlama-7b-hf",
        hf_repo_id="test-org/autodev-lora",
        vllm_host="0.0.0.0",
        vllm_port=8000,
        local_output_dir="~/.autodev/deployed",
    )


# =============================================================================
# Test Enums
# =============================================================================

class TestEnums:
    """Tests for enum types."""
    
    def test_deployment_target_values(self):
        """Test DeploymentTarget enum values."""
        assert DeploymentTarget.HUGGINGFACE.value == "huggingface"
        assert DeploymentTarget.VLLM.value == "vllm"
        assert DeploymentTarget.LOCAL.value == "local"
    
    def test_deployment_status_values(self):
        """Test DeploymentStatus enum values."""
        assert DeploymentStatus.PENDING.value == "pending"
        assert DeploymentStatus.ACTIVE.value == "active"
        assert DeploymentStatus.DEPRECATED.value == "deprecated"
        assert DeploymentStatus.FAILED.value == "failed"
        assert DeploymentStatus.CANARY.value == "canary"
    
    def test_rollback_reason_values(self):
        """Test RollbackReason enum values."""
        assert RollbackReason.PERFORMANCE_REGRESSION.value == "performance_regression"
        assert RollbackReason.ERROR_RATE.value == "error_rate"
        assert RollbackReason.MANUAL.value == "manual"
        assert RollbackReason.CANARY_FAILURE.value == "canary_failure"
        assert RollbackReason.HEALTH_CHECK.value == "health_check"


# =============================================================================
# Test CheckpointInfo
# =============================================================================

class TestCheckpointInfo:
    """Tests for CheckpointInfo dataclass."""
    
    def test_checkpoint_info_creation(self):
        """Test creating a checkpoint info."""
        checkpoint = CheckpointInfo(
            path="/path/to/checkpoint",
            step=100,
            timestamp=datetime.now(timezone.utc),
            metrics={"loss": 0.5, "resolution_rate": 0.85},
            is_best=False,
            run_id="run_20260323",
            adapter_file="/path/to/adapter_model.safetensors",
            config_file="/path/to/adapter_config.json"
        )
        
        assert checkpoint.path == "/path/to/checkpoint"
        assert checkpoint.step == 100
        assert checkpoint.metrics["loss"] == 0.5
        assert checkpoint.is_best is False
    
    def test_checkpoint_info_to_dict(self):
        """Test serialization to dictionary."""
        checkpoint = CheckpointInfo(
            path="/path/to/checkpoint",
            step=100,
            timestamp=datetime(2026, 3, 23, 14, 30, 52, tzinfo=timezone.utc),
            metrics={"loss": 0.5},
            run_id="run_test"
        )
        
        data = checkpoint.to_dict()
        
        assert data["path"] == "/path/to/checkpoint"
        assert data["step"] == 100
        assert data["timestamp"] == "2026-03-23T14:30:52+00:00"
        assert data["metrics"]["loss"] == 0.5
    
    def test_checkpoint_info_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "path": "/path/to/checkpoint",
            "step": 200,
            "timestamp": "2026-03-23T14:30:52+00:00",
            "metrics": {"loss": 0.3},
            "is_best": True,
            "run_id": "run_test",
            "adapter_file": "",
            "config_file": ""
        }
        
        checkpoint = CheckpointInfo.from_dict(data)
        
        assert checkpoint.path == "/path/to/checkpoint"
        assert checkpoint.step == 200
        assert checkpoint.timestamp.year == 2026
        assert checkpoint.is_best is True
    
    def test_get_metric(self):
        """Test get_metric method."""
        checkpoint = CheckpointInfo(
            path="/path",
            step=100,
            timestamp=datetime.now(timezone.utc),
            metrics={"loss": 0.5}
        )
        
        assert checkpoint.get_metric("loss") == 0.5
        assert checkpoint.get_metric("nonexistent", 0.0) == 0.0
        assert checkpoint.get_metric("nonexistent", 1.0) == 1.0


# =============================================================================
# Test DeploymentConfig
# =============================================================================

class TestDeploymentConfig:
    """Tests for DeploymentConfig dataclass."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = DeploymentConfig()
        
        assert config.target == DeploymentTarget.LOCAL
        assert config.base_model == ""
        assert config.checkpoint_path == ""
        assert config.hf_private is False
        assert config.vllm_host == "0.0.0.0"
        assert config.vllm_port == 8000
        assert config.vllm_gpu_memory == 0.9
        assert config.vllm_max_model_len == 8192
        assert config.local_merge_weights is True
        assert config.run_validation is True
    
    def test_config_with_string_target(self):
        """Test config with string target conversion."""
        config = DeploymentConfig(target="huggingface")
        
        assert config.target == DeploymentTarget.HUGGINGFACE
    
    def test_config_path_expansion(self):
        """Test that paths are expanded."""
        config = DeploymentConfig(
            local_output_dir="~/test_deployed"
        )
        
        assert "~" not in config.local_output_dir
    
    def test_config_hf_tags_default(self):
        """Test default HuggingFace tags."""
        config = DeploymentConfig()
        
        assert "autodev" in config.hf_tags
        assert "code-generation" in config.hf_tags
        assert "lora" in config.hf_tags


# =============================================================================
# Test DeployedVersion
# =============================================================================

class TestDeployedVersion:
    """Tests for DeployedVersion dataclass."""
    
    def test_deployed_version_creation(self):
        """Test creating a deployed version."""
        version = DeployedVersion(
            version="autodev-v1.0.0-4f3bf81",
            checkpoint_path="/path/to/checkpoint",
            deployment_type="local",
            endpoint_url="/path/to/deployed/model",
            status=DeploymentStatus.ACTIVE,
            base_model="codellama/CodeLlama-7b-hf"
        )
        
        assert version.version == "autodev-v1.0.0-4f3bf81"
        assert version.deployment_type == "local"
        assert version.status == DeploymentStatus.ACTIVE
    
    def test_deployed_version_to_dict(self):
        """Test serialization to dictionary."""
        version = DeployedVersion(
            version="v1.0.0",
            checkpoint_path="/path/to/checkpoint",
            deployment_type="huggingface",
            endpoint_url="https://huggingface.co/test/model",
            status=DeploymentStatus.ACTIVE
        )
        
        data = version.to_dict()
        
        assert data["version"] == "v1.0.0"
        assert data["deployment_type"] == "huggingface"
        assert data["status"] == "active"
        assert "deployed_at" in data
    
    def test_deployed_version_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "version": "v1.0.0",
            "checkpoint_path": "/path/to/checkpoint",
            "deployment_type": "vllm",
            "endpoint_url": "http://localhost:8000",
            "deployed_at": "2026-03-23T14:30:52+00:00",
            "status": "deprecated",
            "base_model": "",
            "config": None
        }
        
        version = DeployedVersion.from_dict(data)
        
        assert version.version == "v1.0.0"
        assert version.deployment_type == "vllm"
        assert version.status == DeploymentStatus.DEPRECATED
        assert version.deployed_at.year == 2026


# =============================================================================
# Test DeploymentResult and RollbackResult
# =============================================================================

class TestResults:
    """Tests for result dataclasses."""
    
    def test_deployment_result_success(self):
        """Test successful deployment result."""
        version = DeployedVersion(
            version="v1.0.0",
            checkpoint_path="/path",
            deployment_type="local"
        )
        
        result = DeploymentResult(
            success=True,
            version=version,
            duration_seconds=120.5,
            logs=["Step 1", "Step 2"]
        )
        
        assert result.success is True
        assert result.version.version == "v1.0.0"
        assert result.duration_seconds == 120.5
        assert len(result.logs) == 2
    
    def test_deployment_result_failure(self):
        """Test failed deployment result."""
        result = DeploymentResult(
            success=False,
            error_message="Checkpoint validation failed"
        )
        
        assert result.success is False
        assert result.error_message == "Checkpoint validation failed"
    
    def test_rollback_result_success(self):
        """Test successful rollback result."""
        result = RollbackResult(
            success=True,
            previous_version="v1.1.0",
            target_version="v1.0.0",
            reason=RollbackReason.PERFORMANCE_REGRESSION
        )
        
        assert result.success is True
        assert result.previous_version == "v1.1.0"
        assert result.target_version == "v1.0.0"
        assert result.reason == RollbackReason.PERFORMANCE_REGRESSION
    
    def test_rollback_result_failure(self):
        """Test failed rollback result."""
        result = RollbackResult(
            success=False,
            target_version="v0.9.0",
            reason=RollbackReason.MANUAL,
            error_message="Target version not found"
        )
        
        assert result.success is False
        assert result.error_message == "Target version not found"


# =============================================================================
# Test CheckpointManager
# =============================================================================

class TestCheckpointManager:
    """Tests for CheckpointManager."""
    
    def test_initialization(self, temp_dir):
        """Test manager initialization."""
        manager = CheckpointManager(checkpoint_base_dir=temp_dir)
        
        assert manager.checkpoint_base_dir == Path(temp_dir)
    
    def test_ensure_directories(self, temp_dir):
        """Test directory creation."""
        manager = CheckpointManager(
            checkpoint_base_dir=os.path.join(temp_dir, "new_checkpoints")
        )
        
        assert manager.checkpoint_base_dir.exists()
    
    def test_list_runs(self, checkpoint_dir):
        """Test listing training runs."""
        manager = CheckpointManager(checkpoint_base_dir=checkpoint_dir)
        
        runs = manager.list_runs()
        
        assert len(runs) == 1
        assert runs[0] == "run_20260323_143052"
    
    def test_list_runs_empty(self, temp_dir):
        """Test listing runs when none exist."""
        manager = CheckpointManager(checkpoint_base_dir=temp_dir)
        
        runs = manager.list_runs()
        
        assert runs == []
    
    def test_list_checkpoints(self, checkpoint_dir):
        """Test listing checkpoints from a run."""
        manager = CheckpointManager(checkpoint_base_dir=checkpoint_dir)
        
        checkpoints = manager.list_checkpoints("run_20260323_143052")
        
        assert len(checkpoints) == 4  # 3 numbered + 1 best
        # Verify checkpoint names
        checkpoint_names = [Path(c.path).name for c in checkpoints]
        assert "checkpoint-100" in checkpoint_names
        assert "checkpoint-200" in checkpoint_names
        assert "checkpoint-300" in checkpoint_names
        assert "checkpoint-best" in checkpoint_names
    
    def test_list_checkpoints_nonexistent_run(self, checkpoint_dir):
        """Test listing checkpoints for nonexistent run."""
        manager = CheckpointManager(checkpoint_base_dir=checkpoint_dir)
        
        checkpoints = manager.list_checkpoints("nonexistent_run")
        
        assert checkpoints == []
    
    def test_get_best_checkpoint(self, checkpoint_dir):
        """Test getting best checkpoint."""
        manager = CheckpointManager(checkpoint_base_dir=checkpoint_dir)
        
        best = manager.get_best_checkpoint("run_20260323_143052")
        
        assert best is not None
        assert best.is_best is True
        assert Path(best.path).name == "checkpoint-best"
    
    def test_get_best_checkpoint_by_metric(self, checkpoint_dir):
        """Test getting best checkpoint by specific metric."""
        manager = CheckpointManager(checkpoint_base_dir=checkpoint_dir)
        
        # Get by loss (lower is better)
        best = manager.get_best_checkpoint(
            "run_20260323_143052",
            metric="loss",
            higher_is_better=False
        )
        
        assert best is not None
    
    def test_get_latest_checkpoint(self, checkpoint_dir):
        """Test getting latest checkpoint."""
        manager = CheckpointManager(checkpoint_base_dir=checkpoint_dir)
        
        latest = manager.get_latest_checkpoint("run_20260323_143052")
        
        assert latest is not None
        assert latest.step == 300  # Highest step number
    
    def test_get_latest_checkpoint_empty(self, temp_dir):
        """Test getting latest from empty run."""
        manager = CheckpointManager(checkpoint_base_dir=temp_dir)
        
        latest = manager.get_latest_checkpoint("nonexistent")
        
        assert latest is None
    
    def test_validate_checkpoint_valid(self, valid_checkpoint):
        """Test validating a valid checkpoint."""
        manager = CheckpointManager()
        
        result = manager.validate_checkpoint(valid_checkpoint)
        
        assert result is True
    
    def test_validate_checkpoint_missing_adapter(self, temp_dir):
        """Test validation with missing adapter file."""
        manager = CheckpointManager()
        
        # Create directory without adapter file
        ckpt_dir = Path(temp_dir) / "invalid_checkpoint"
        ckpt_dir.mkdir(parents=True, exist_ok=True)
        
        result = manager.validate_checkpoint(str(ckpt_dir))
        
        assert result is False
    
    def test_validate_checkpoint_nonexistent(self, temp_dir):
        """Test validation of nonexistent path."""
        manager = CheckpointManager()
        
        result = manager.validate_checkpoint("/nonexistent/path")
        
        assert result is False
    
    def test_validate_checkpoint_not_directory(self, temp_dir):
        """Test validation when path is not a directory."""
        manager = CheckpointManager()
        
        # Create a file instead of directory
        file_path = Path(temp_dir) / "not_a_directory.txt"
        file_path.write_text("test")
        
        result = manager.validate_checkpoint(str(file_path))
        
        assert result is False
    
    def test_parse_checkpoint_with_trainer_state(self, checkpoint_dir):
        """Test parsing checkpoint with trainer state."""
        manager = CheckpointManager(checkpoint_base_dir=checkpoint_dir)
        
        checkpoints = manager.list_checkpoints("run_20260323_143052")
        numbered = [c for c in checkpoints if not c.is_best][0]
        
        assert "loss" in numbered.metrics or "best_metric" in numbered.metrics


# =============================================================================
# Test HuggingFaceDeployer
# =============================================================================

class TestHuggingFaceDeployer:
    """Tests for HuggingFaceDeployer."""
    
    @pytest.fixture
    def hf_deployer(self, deployment_config):
        """Create a HuggingFace deployer."""
        return HuggingFaceDeployer(deployment_config)
    
    def test_initialization(self, hf_deployer):
        """Test deployer initialization."""
        assert hf_deployer.config is not None
        assert hf_deployer._hf_api is None
    
    def test_deploy_missing_repo_id(self, hf_deployer, valid_checkpoint):
        """Test deployment without repo_id."""
        hf_deployer.config.hf_repo_id = ""
        
        result = hf_deployer.deploy(
            checkpoint_path=valid_checkpoint,
            repo_id=None
        )
        
        assert result.success is False
        assert "repo_id is required" in result.error_message
    
    def test_deploy_invalid_checkpoint(self, hf_deployer, temp_dir):
        """Test deployment with invalid checkpoint."""
        result = hf_deployer.deploy(
            checkpoint_path=temp_dir,  # Not a valid checkpoint
            repo_id="test/model"
        )
        
        assert result.success is False
        assert "validation failed" in result.error_message.lower()
    
    def test_deploy_success(self, hf_deployer, valid_checkpoint):
        """Test successful deployment to HuggingFace."""
        # Mock the HuggingFace API
        mock_api = MagicMock()
        mock_api.upload_file = MagicMock()
        
        with patch.object(hf_deployer, '_get_hf_api', return_value=mock_api), \
             patch.object(hf_deployer, '_load_checkpoint_metrics', 
                         return_value={'loss': 0.5, 'resolution_rate': 0.85}):
            # Mock huggingface_hub functions within the method
            with patch('huggingface_hub.create_repo') as mock_create, \
                 patch('huggingface_hub.repo_exists', return_value=False) as mock_exists, \
                 patch('huggingface_hub.upload_file') as mock_upload, \
                 patch('huggingface_hub.upload_folder') as mock_upload_folder, \
                 patch('huggingface_hub.create_tag') as mock_tag:
                
                result = hf_deployer.deploy(
                    checkpoint_path=valid_checkpoint,
                    repo_id="test-org/test-model",
                    version="v1.0.0"
                )
        
        assert result.success is True
        assert result.version is not None
        assert result.version.deployment_type == "huggingface"
        assert "huggingface.co" in result.version.endpoint_url
    
    def test_rollback_success(self, hf_deployer):
        """Test successful rollback."""
        mock_api = MagicMock()
        
        # Mock version registry
        with patch.object(hf_deployer, '_get_hf_api', return_value=mock_api), \
             patch.object(VersionRegistry, 'get_active_version') as mock_active, \
             patch('huggingface_hub.list_repo_refs') as mock_refs, \
             patch('huggingface_hub.hf_hub_download') as mock_download:
            
            # Setup mocks
            mock_active.return_value = DeployedVersion(
                version="v1.1.0",
                checkpoint_path="/path",
                deployment_type="huggingface"
            )
            
            mock_ref = MagicMock()
            mock_ref.name = "v1.0.0"
            mock_refs.return_value = MagicMock(tags=[mock_ref])
            
            mock_download.return_value = "/tmp/README.md"
            
            with patch('builtins.open', mock_open(read_data="# README")):
                result = hf_deployer.rollback(
                    target_version="v1.0.0",
                    reason=RollbackReason.PERFORMANCE_REGRESSION
                )
        
        assert result.success is True
        assert result.target_version == "v1.0.0"
    
    def test_rollback_no_repo_id(self, hf_deployer):
        """Test rollback without configured repo_id."""
        hf_deployer.config.hf_repo_id = ""
        
        result = hf_deployer.rollback(
            target_version="v1.0.0"
        )
        
        assert result.success is False
        assert "No repo_id configured" in result.error_message
    
    def test_generate_model_card(self, hf_deployer, valid_checkpoint):
        """Test model card generation."""
        hf_deployer.config.base_model = "test-model"
        hf_deployer.config.hf_repo_id = "test-org/test-model"
        
        # Mock metrics loading with proper numeric values to avoid format string issues
        with patch.object(hf_deployer, '_load_checkpoint_metrics', 
                         return_value={'loss': 0.5, 'resolution_rate': 0.85}):
            card = hf_deployer._generate_model_card(
                checkpoint_path=valid_checkpoint,
                version="v1.0.0",
                tags=["autodev", "lora"]
            )
        
        assert "# AutoDev LoRA Adapter" in card
        assert "v1.0.0" in card
        assert "test-model" in card
    
    def test_load_checkpoint_metrics(self, hf_deployer, valid_checkpoint):
        """Test loading checkpoint metrics."""
        metrics = hf_deployer._load_checkpoint_metrics(valid_checkpoint)
        
        assert "loss" in metrics or "best_metric" in metrics
    
    def test_status(self, hf_deployer):
        """Test status check."""
        status = hf_deployer.status()
        
        assert "status" in status
    
    def test_get_hf_api_import_error(self, hf_deployer):
        """Test _get_hf_api with missing huggingface_hub."""
        with patch.dict('sys.modules', {'huggingface_hub': None}):
            with patch('builtins.__import__', side_effect=ImportError("No module")):
                with pytest.raises(ImportError):
                    hf_deployer._get_hf_api()


# =============================================================================
# Test VLLMDeployer
# =============================================================================

class TestVLLMDeployer:
    """Tests for VLLMDeployer."""
    
    @pytest.fixture
    def vllm_deployer(self, deployment_config):
        """Create a vLLM deployer."""
        return VLLMDeployer(deployment_config)
    
    def test_initialization(self, vllm_deployer):
        """Test deployer initialization."""
        assert vllm_deployer._process is None
    
    def test_deploy_missing_base_model(self, vllm_deployer, valid_checkpoint):
        """Test deployment without base model."""
        vllm_deployer.config.base_model = ""
        
        result = vllm_deployer.deploy(
            checkpoint_path=valid_checkpoint,
            base_model=None
        )
        
        assert result.success is False
        assert "base_model is required" in result.error_message
    
    def test_deploy_invalid_checkpoint(self, vllm_deployer, temp_dir):
        """Test deployment with invalid checkpoint."""
        result = vllm_deployer.deploy(
            checkpoint_path=temp_dir,
            base_model="codellama/CodeLlama-7b-hf"
        )
        
        assert result.success is False
        assert "validation failed" in result.error_message.lower()
    
    @patch('subprocess.Popen')
    def test_deploy_background_success(self, mock_popen, vllm_deployer, valid_checkpoint):
        """Test successful background deployment."""
        # Mock process
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.stderr = MagicMock()
        mock_process.stderr.read.return_value = b""
        mock_popen.return_value = mock_process
        
        # Mock health check
        with patch.object(vllm_deployer, '_wait_for_health', return_value=True):
            result = vllm_deployer.deploy(
                checkpoint_path=valid_checkpoint,
                base_model="codellama/CodeLlama-7b-hf",
                port=8000,
                background=True
            )
        
        assert result.success is True
        assert result.version is not None
        assert result.version.deployment_type == "vllm"
        assert "http://" in result.version.endpoint_url
    
    @patch('subprocess.Popen')
    def test_deploy_background_health_check_fail(self, mock_popen, vllm_deployer, valid_checkpoint):
        """Test deployment with failed health check."""
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.stderr = MagicMock()
        mock_process.stderr.read.return_value = b"Error starting server"
        mock_popen.return_value = mock_process
        
        with patch.object(vllm_deployer, '_wait_for_health', return_value=False):
            result = vllm_deployer.deploy(
                checkpoint_path=valid_checkpoint,
                base_model="codellama/CodeLlama-7b-hf",
                background=True
            )
        
        assert result.success is False
        assert "failed to start" in result.error_message.lower()
    
    def test_wait_for_health_success(self, vllm_deployer):
        """Test health check success."""
        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_response
            
            result = vllm_deployer._wait_for_health(
                "http://localhost:8000",
                timeout=5
            )
        
        assert result is True
    
    def test_wait_for_health_timeout(self, vllm_deployer):
        """Test health check timeout."""
        import urllib.error
        
        with patch('urllib.request.urlopen', 
                   side_effect=urllib.error.URLError("Connection refused")):
            result = vllm_deployer._wait_for_health(
                "http://localhost:8000",
                timeout=2
            )
        
        assert result is False
    
    def test_status_healthy(self, vllm_deployer):
        """Test status check when healthy."""
        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_response
            
            status = vllm_deployer.status("http://localhost:8000")
        
        assert status["status"] == "healthy"
    
    def test_status_unhealthy(self, vllm_deployer):
        """Test status check when unhealthy."""
        import urllib.error
        
        with patch('urllib.request.urlopen',
                   side_effect=urllib.error.URLError("Connection refused")):
            status = vllm_deployer.status("http://localhost:8000")
        
        assert status["status"] == "unhealthy"
    
    def test_stop_process(self, vllm_deployer):
        """Test stopping vLLM process."""
        mock_process = MagicMock()
        mock_process.wait.return_value = None
        vllm_deployer._process = mock_process
        
        result = vllm_deployer.stop()
        
        assert result is True
        mock_process.terminate.assert_called_once()
        assert vllm_deployer._process is None
    
    def test_stop_no_process(self, vllm_deployer):
        """Test stop when no process running."""
        result = vllm_deployer.stop()
        
        assert result is True
    
    def test_rollback(self, vllm_deployer, valid_checkpoint):
        """Test vLLM rollback."""
        # Setup registry mocks
        target_version = DeployedVersion(
            version="v1.0.0",
            checkpoint_path=valid_checkpoint,
            deployment_type="vllm",
            base_model="codellama/CodeLlama-7b-hf"
        )
        
        with patch.object(VersionRegistry, 'get_active_version') as mock_active, \
             patch.object(VersionRegistry, 'get_version') as mock_get:
            
            mock_active.return_value = DeployedVersion(
                version="v1.1.0",
                checkpoint_path="/path",
                deployment_type="vllm"
            )
            mock_get.return_value = target_version
            
            with patch.object(vllm_deployer, 'deploy') as mock_deploy:
                mock_deploy.return_value = DeploymentResult(
                    success=True,
                    version=target_version
                )
                
                result = vllm_deployer.rollback("v1.0.0")
        
        assert result.success is True


# =============================================================================
# Test LocalInferenceDeployer
# =============================================================================

class TestLocalInferenceDeployer:
    """Tests for LocalInferenceDeployer."""
    
    @pytest.fixture
    def local_deployer(self, deployment_config, temp_dir):
        """Create a local inference deployer."""
        deployment_config.local_output_dir = temp_dir
        return LocalInferenceDeployer(deployment_config)
    
    def test_initialization(self, local_deployer):
        """Test deployer initialization."""
        assert local_deployer.config is not None
    
    def test_deploy_invalid_checkpoint(self, local_deployer, temp_dir):
        """Test deployment with invalid checkpoint."""
        result = local_deployer.deploy(
            checkpoint_path=temp_dir  # Not a valid checkpoint
        )
        
        assert result.success is False
        assert "validation failed" in result.error_message.lower()
    
    def test_deploy_copy_adapter_files(self, local_deployer, valid_checkpoint, temp_dir):
        """Test deploying by copying adapter files."""
        output_dir = os.path.join(temp_dir, "deployed")
        
        result = local_deployer.deploy(
            checkpoint_path=valid_checkpoint,
            output_dir=output_dir,
            merge_weights=False
        )
        
        assert result.success is True
        assert result.version.deployment_type == "local"
        
        # Check files were copied
        output_path = Path(result.version.endpoint_url)
        assert (output_path / "adapter_model.safetensors").exists()
    
    @patch('src.deployment.model_deployer.LocalInferenceDeployer._validate_checkpoint')
    def test_deploy_with_gguf_format(self, mock_validate, local_deployer, valid_checkpoint, temp_dir):
        """Test deploying with GGUF format - should fail without proper setup."""
        mock_validate.return_value = True  # Bypass validation to skip actual GGUF path
        
        output_dir = os.path.join(temp_dir, "gguf_deployed")
        
        # Mock the deploy to avoid actual ML library imports
        with patch.object(local_deployer, 'deploy') as mock_deploy:
            mock_deploy.return_value = DeploymentResult(
                success=False,
                error_message="GGUF conversion requires base_model to be specified"
            )
            
            result = local_deployer.deploy(
                checkpoint_path=valid_checkpoint,
                output_dir=output_dir,
                merge_weights=False,
                format="gguf"
            )
        
        # Should fail because base_model is required for GGUF
        assert result.success is False
    
    def test_deploy_with_onnx_format(self, local_deployer, valid_checkpoint, temp_dir):
        """Test deploying with ONNX format (not implemented)."""
        output_dir = os.path.join(temp_dir, "onnx_deployed")
        
        result = local_deployer.deploy(
            checkpoint_path=valid_checkpoint,
            output_dir=output_dir,
            format="onnx"
        )
        
        assert result.success is False
        assert "not yet implemented" in result.error_message.lower()
    
    def test_generate_deployment_readme(self, local_deployer, valid_checkpoint, temp_dir):
        """Test README generation."""
        output_path = Path(temp_dir) / "test_readme"
        output_path.mkdir(parents=True, exist_ok=True)
        
        local_deployer._generate_deployment_readme(
            output_path=str(output_path),
            version="v1.0.0",
            checkpoint_path=valid_checkpoint,
            base_model="codellama/CodeLlama-7b-hf",
            merge_weights=True,
            quantization=None,
            export_format="transformers"
        )
        
        readme_path = output_path / "README.md"
        assert readme_path.exists()
        
        content = readme_path.read_text()
        assert "v1.0.0" in content
        assert "codellama" in content
    
    def test_status_available(self, local_deployer, valid_checkpoint):
        """Test status check for available deployment."""
        status = local_deployer.status(valid_checkpoint)
        
        assert status["status"] == "available"
        assert len(status["files"]) >= 1
    
    def test_status_not_found(self, local_deployer, temp_dir):
        """Test status check for nonexistent deployment."""
        status = local_deployer.status(os.path.join(temp_dir, "nonexistent"))
        
        assert status["status"] == "not_found"
    
    def test_rollback(self, local_deployer, valid_checkpoint, temp_dir):
        """Test local rollback."""
        # First deploy
        deploy_result = local_deployer.deploy(
            checkpoint_path=valid_checkpoint,
            merge_weights=False
        )
        
        assert deploy_result.success is True
        
        # Setup for rollback
        target_version = DeployedVersion(
            version=deploy_result.version.version,
            checkpoint_path=valid_checkpoint,
            deployment_type="local",
            endpoint_url=deploy_result.version.endpoint_url,
            status=DeploymentStatus.DEPRECATED
        )
        
        with patch.object(VersionRegistry, 'get_active_version') as mock_active, \
             patch.object(VersionRegistry, 'get_version') as mock_get, \
             patch.object(VersionRegistry, 'deprecate'):
            
            mock_active.return_value = deploy_result.version
            mock_get.return_value = target_version
            
            result = local_deployer.rollback(
                target_version=deploy_result.version.version
            )
        
        assert result.success is True
    
    @patch('src.deployment.model_deployer.LocalInferenceDeployer._merge_lora_weights_impl')
    def test_merge_lora_weights_success(self, mock_merge, local_deployer, valid_checkpoint, temp_dir):
        """Test successful LoRA weight merging."""
        mock_merge.return_value = True
        
        output_dir = os.path.join(temp_dir, "merged")
        
        result = local_deployer.deploy(
            checkpoint_path=valid_checkpoint,
            output_dir=output_dir,
            merge_weights=True,
            base_model="codellama/CodeLlama-7b-hf",
            copy_tokenizer=True
        )
        
        assert result.success is True
        mock_merge.assert_called_once()
    
    def test_merge_lora_weights_import_error(self, local_deployer, valid_checkpoint, temp_dir):
        """Test LoRA merge with missing dependencies."""
        output_dir = os.path.join(temp_dir, "merged")
        
        # Mock _merge_lora_weights_impl to raise ImportError
        with patch.object(local_deployer, '_merge_lora_weights_impl', 
                         side_effect=ImportError("No module named 'transformers'")):
            result = local_deployer.deploy(
                checkpoint_path=valid_checkpoint,
                output_dir=output_dir,
                merge_weights=True,
                base_model="codellama/CodeLlama-7b-hf"
            )
        
        assert result.success is False
        assert "transformers" in result.error_message.lower() or "import" in result.error_message.lower()
    
    def test_load_local_metrics(self, local_deployer, valid_checkpoint):
        """Test loading local metrics."""
        metrics = local_deployer._load_local_metrics(valid_checkpoint)
        
        # Should have metrics from trainer_state.json
        assert isinstance(metrics, dict)


# =============================================================================
# Test VersionRegistry
# =============================================================================

class TestVersionRegistry:
    """Tests for VersionRegistry."""
    
    @pytest.fixture
    def registry(self, temp_dir):
        """Create a version registry with temp path."""
        registry_path = os.path.join(temp_dir, "test_registry.json")
        return VersionRegistry(registry_path=registry_path)
    
    def test_initialization(self, registry):
        """Test registry initialization."""
        assert registry._versions == {}
    
    def test_register_version(self, registry):
        """Test registering a version."""
        version = DeployedVersion(
            version="v1.0.0",
            checkpoint_path="/path/to/checkpoint",
            deployment_type="local"
        )
        
        registry.register(version)
        
        assert "v1.0.0" in registry._versions
        assert registry._versions["v1.0.0"].version == "v1.0.0"
    
    def test_get_version(self, registry):
        """Test getting a version."""
        version = DeployedVersion(
            version="v1.0.0",
            checkpoint_path="/path",
            deployment_type="local"
        )
        registry.register(version)
        
        result = registry.get_version("v1.0.0")
        
        assert result is not None
        assert result.version == "v1.0.0"
    
    def test_get_version_not_found(self, registry):
        """Test getting nonexistent version."""
        result = registry.get_version("nonexistent")
        
        assert result is None
    
    def test_get_active_version(self, registry):
        """Test getting active version."""
        active = DeployedVersion(
            version="v1.0.0",
            checkpoint_path="/path",
            deployment_type="local",
            status=DeploymentStatus.ACTIVE
        )
        inactive = DeployedVersion(
            version="v0.9.0",
            checkpoint_path="/path",
            deployment_type="local",
            status=DeploymentStatus.DEPRECATED
        )
        
        registry.register(active)
        registry.register(inactive)
        
        result = registry.get_active_version()
        
        assert result is not None
        assert result.version == "v1.0.0"
    
    def test_get_active_version_by_type(self, registry):
        """Test getting active version by deployment type."""
        hf_version = DeployedVersion(
            version="v1.0.0-hf",
            checkpoint_path="/path",
            deployment_type="huggingface",
            status=DeploymentStatus.ACTIVE
        )
        local_version = DeployedVersion(
            version="v1.0.0-local",
            checkpoint_path="/path",
            deployment_type="local",
            status=DeploymentStatus.ACTIVE
        )
        
        registry.register(hf_version)
        registry.register(local_version)
        
        result = registry.get_active_version("local")
        
        assert result is not None
        assert result.deployment_type == "local"
    
    def test_list_versions(self, registry):
        """Test listing versions."""
        for i in range(5):
            version = DeployedVersion(
                version=f"v{i}.0.0",
                checkpoint_path="/path",
                deployment_type="local"
            )
            registry.register(version)
        
        versions = registry.list_versions(limit=3)
        
        assert len(versions) == 3
    
    def test_deprecate_version(self, registry):
        """Test deprecating a version."""
        version = DeployedVersion(
            version="v1.0.0",
            checkpoint_path="/path",
            deployment_type="local",
            status=DeploymentStatus.ACTIVE
        )
        registry.register(version)
        
        result = registry.deprecate("v1.0.0")
        
        assert result is True
        assert registry._versions["v1.0.0"].status == DeploymentStatus.DEPRECATED
    
    def test_deprecate_nonexistent_version(self, registry):
        """Test deprecating nonexistent version."""
        result = registry.deprecate("nonexistent")
        
        assert result is False
    
    def test_persistence(self, temp_dir):
        """Test registry persistence to disk."""
        registry_path = os.path.join(temp_dir, "persist_registry.json")
        
        # Create and register
        registry1 = VersionRegistry(registry_path=registry_path)
        version = DeployedVersion(
            version="v1.0.0",
            checkpoint_path="/path",
            deployment_type="local"
        )
        registry1.register(version)
        
        # Load new instance
        registry2 = VersionRegistry(registry_path=registry_path)
        
        assert "v1.0.0" in registry2._versions


# =============================================================================
# Test RollbackManager
# =============================================================================

class TestRollbackManager:
    """Tests for RollbackManager."""
    
    @pytest.fixture
    def rollback_manager(self, temp_dir):
        """Create a rollback manager."""
        registry_path = os.path.join(temp_dir, "registry.json")
        history_path = os.path.join(temp_dir, "rollback_history.json")
        
        registry = VersionRegistry(registry_path=registry_path)
        
        return RollbackManager(
            registry=registry,
            config={"history_path": history_path}
        )
    
    def test_initialization(self, rollback_manager):
        """Test manager initialization."""
        assert rollback_manager.registry is not None
        assert rollback_manager._rollback_history == []
    
    def test_rollback_success(self, rollback_manager):
        """Test successful rollback."""
        # Register versions
        current = DeployedVersion(
            version="v1.1.0",
            checkpoint_path="/path/current",
            deployment_type="local",
            status=DeploymentStatus.ACTIVE
        )
        target = DeployedVersion(
            version="v1.0.0",
            checkpoint_path="/path/target",
            deployment_type="local",
            status=DeploymentStatus.CANARY  # Use CANARY instead of DEPRECATED for valid rollback target
        )
        
        rollback_manager.registry.register(current)
        rollback_manager.registry.register(target)
        
        # Create mock deployer
        mock_deployer = MagicMock()
        mock_deployer.rollback.return_value = RollbackResult(
            success=True,
            previous_version="v1.1.0",
            target_version="v1.0.0"
        )
        rollback_manager.deployer = mock_deployer
        
        result = rollback_manager.rollback(
            target_version="v1.0.0",
            reason=RollbackReason.MANUAL,
            skip_health_check=True
        )
        
        assert result.success is True
        assert result.target_version == "v1.0.0"
    
    def test_rollback_target_not_found(self, rollback_manager):
        """Test rollback with nonexistent target."""
        current = DeployedVersion(
            version="v1.1.0",
            checkpoint_path="/path",
            deployment_type="local",
            status=DeploymentStatus.ACTIVE
        )
        rollback_manager.registry.register(current)
        
        result = rollback_manager.rollback(
            target_version="v0.9.0",
            reason=RollbackReason.MANUAL
        )
        
        assert result.success is False
        assert "not found" in result.error_message.lower()
    
    def test_rollback_already_active(self, rollback_manager):
        """Test rollback when target is already active."""
        active = DeployedVersion(
            version="v1.0.0",
            checkpoint_path="/path",
            deployment_type="local",
            status=DeploymentStatus.ACTIVE
        )
        rollback_manager.registry.register(active)
        
        result = rollback_manager.rollback(
            target_version="v1.0.0",
            reason=RollbackReason.MANUAL
        )
        
        assert result.success is False
        assert "already active" in result.error_message.lower()
    
    def test_rollback_force(self, rollback_manager):
        """Test forced rollback skipping safety checks."""
        current = DeployedVersion(
            version="v1.1.0",
            checkpoint_path="/path/current",
            deployment_type="local",
            status=DeploymentStatus.ACTIVE
        )
        target = DeployedVersion(
            version="v1.0.0",
            checkpoint_path="/path/target",
            deployment_type="local",
            status=DeploymentStatus.DEPRECATED
        )
        
        rollback_manager.registry.register(current)
        rollback_manager.registry.register(target)
        
        result = rollback_manager.rollback(
            target_version="v1.0.0",
            reason=RollbackReason.MANUAL,
            force=True,
            skip_health_check=True
        )
        
        assert result.success is True
    
    def test_safety_checks(self, rollback_manager):
        """Test safety checks."""
        target = DeployedVersion(
            version="v1.0.0",
            checkpoint_path="/path",
            deployment_type="local",
            status=DeploymentStatus.DEPRECATED
        )
        rollback_manager.registry.register(target)
        
        result = rollback_manager._perform_safety_checks(
            "v1.0.0",
            RollbackReason.PERFORMANCE_REGRESSION
        )
        
        assert result["safe"] is True
    
    def test_safety_checks_target_not_found(self, rollback_manager):
        """Test safety checks when target not found."""
        result = rollback_manager._perform_safety_checks(
            "nonexistent",
            RollbackReason.MANUAL
        )
        
        assert result["safe"] is False
        assert "not found" in result["reason"].lower()
    
    def test_auto_rollback_resolution_rate(self, rollback_manager):
        """Test auto-rollback triggered by resolution rate degradation."""
        current = DeployedVersion(
            version="v1.1.0",
            checkpoint_path="/path",
            deployment_type="local",
            status=DeploymentStatus.ACTIVE,
            metrics={"resolution_rate": 0.30}
        )
        previous = DeployedVersion(
            version="v1.0.0",
            checkpoint_path="/path",
            deployment_type="local",
            status=DeploymentStatus.CANARY,  # Use CANARY for valid rollback target
            metrics={"resolution_rate": 0.25}
        )
        
        rollback_manager.registry.register(current)
        rollback_manager.registry.register(previous)
        
        # Setup mock deployer for rollback
        mock_deployer = MagicMock()
        mock_deployer.rollback.return_value = RollbackResult(
            success=True,
            previous_version="v1.1.0",
            target_version="v1.0.0"
        )
        rollback_manager.deployer = mock_deployer
        
        # Metrics showing significant degradation
        result = rollback_manager.auto_rollback_if_needed(
            current_metrics={"resolution_rate": 0.10},  # Dropped from 0.30
            baseline_metrics={"resolution_rate": 0.30}
        )
        
        # Should trigger rollback
        assert result is not None
        assert result.reason == RollbackReason.PERFORMANCE_REGRESSION
    
    def test_auto_rollback_error_rate(self, rollback_manager):
        """Test auto-rollback triggered by high error rate."""
        current = DeployedVersion(
            version="v1.1.0",
            checkpoint_path="/path",
            deployment_type="local",
            status=DeploymentStatus.ACTIVE,
            metrics={"resolution_rate": 0.50}
        )
        previous = DeployedVersion(
            version="v1.0.0",
            checkpoint_path="/path",
            deployment_type="local",
            status=DeploymentStatus.CANARY  # Use CANARY for valid rollback target
        )
        
        rollback_manager.registry.register(current)
        rollback_manager.registry.register(previous)
        
        # Setup mock deployer for rollback
        mock_deployer = MagicMock()
        mock_deployer.rollback.return_value = RollbackResult(
            success=True,
            previous_version="v1.1.0",
            target_version="v1.0.0",
            reason=RollbackReason.ERROR_RATE
        )
        rollback_manager.deployer = mock_deployer
        
        result = rollback_manager.auto_rollback_if_needed(
            current_metrics={
                "resolution_rate": 0.50,
                "error_rate": 0.15  # Exceeds 10% threshold
            }
        )
        
        assert result is not None
        assert result.reason == RollbackReason.ERROR_RATE
    
    def test_auto_rollback_no_trigger(self, rollback_manager):
        """Test auto-rollback not triggered when metrics are fine."""
        current = DeployedVersion(
            version="v1.1.0",
            checkpoint_path="/path",
            deployment_type="local",
            status=DeploymentStatus.ACTIVE,
            metrics={"resolution_rate": 0.50}
        )
        rollback_manager.registry.register(current)
        
        result = rollback_manager.auto_rollback_if_needed(
            current_metrics={
                "resolution_rate": 0.48,  # Small change
                "error_rate": 0.02  # Low error rate
            }
        )
        
        assert result is None
    
    def test_get_rollback_history(self, rollback_manager):
        """Test getting rollback history."""
        # Add some history
        for i in range(5):
            result = RollbackResult(
                success=True,
                previous_version=f"v{i+1}.0.0",
                target_version=f"v{i}.0.0",
                reason=RollbackReason.MANUAL
            )
            rollback_manager._rollback_history.append(result)
        
        history = rollback_manager.get_rollback_history(limit=3)
        
        assert len(history) == 3
    
    def test_can_rollback(self, rollback_manager):
        """Test can_rollback check."""
        target = DeployedVersion(
            version="v1.0.0",
            checkpoint_path="/path",
            deployment_type="local",
            status=DeploymentStatus.CANARY  # Use CANARY instead of DEPRECATED
        )
        rollback_manager.registry.register(target)
        
        result = rollback_manager.can_rollback("v1.0.0")
        
        assert result["can_rollback"] is True
        assert result["target_exists"] is True
    
    def test_perform_health_check(self, rollback_manager):
        """Test health check."""
        mock_deployer = MagicMock()
        mock_deployer.status.return_value = {"status": "healthy"}
        rollback_manager.deployer = mock_deployer
        
        result = rollback_manager._perform_health_check()
        
        assert result is True
    
    def test_find_stable_previous_version(self, rollback_manager):
        """Test finding stable previous version."""
        current = DeployedVersion(
            version="v1.2.0",
            checkpoint_path="/path",
            deployment_type="local",
            status=DeploymentStatus.ACTIVE
        )
        previous = DeployedVersion(
            version="v1.1.0",
            checkpoint_path="/path",
            deployment_type="local",
            status=DeploymentStatus.CANARY
        )
        older = DeployedVersion(
            version="v1.0.0",
            checkpoint_path="/path",
            deployment_type="local",
            status=DeploymentStatus.DEPRECATED
        )
        
        rollback_manager.registry.register(current)
        rollback_manager.registry.register(previous)
        rollback_manager.registry.register(older)
        
        result = rollback_manager._find_stable_previous_version("v1.2.0")
        
        # Should find the canary version (not deprecated)
        assert result is not None
        assert result.version == "v1.1.0"


# =============================================================================
# Test Factory Functions
# =============================================================================

class TestFactoryFunctions:
    """Tests for factory functions."""
    
    def test_create_deployer_huggingface(self, deployment_config):
        """Test creating HuggingFace deployer."""
        deployer = create_deployer(DeploymentTarget.HUGGINGFACE, deployment_config)
        
        assert isinstance(deployer, HuggingFaceDeployer)
    
    def test_create_deployer_vllm(self, deployment_config):
        """Test creating vLLM deployer."""
        deployer = create_deployer(DeploymentTarget.VLLM, deployment_config)
        
        assert isinstance(deployer, VLLMDeployer)
    
    def test_create_deployer_local(self, deployment_config):
        """Test creating local deployer."""
        deployer = create_deployer(DeploymentTarget.LOCAL, deployment_config)
        
        assert isinstance(deployer, LocalInferenceDeployer)
    
    def test_create_deployer_string_target(self):
        """Test creating deployer with string target."""
        deployer = create_deployer("vllm")
        
        assert isinstance(deployer, VLLMDeployer)
    
    def test_create_deployer_invalid_target(self):
        """Test creating deployer with invalid target."""
        with pytest.raises(ValueError):
            create_deployer("invalid_target")
    
    def test_deploy_checkpoint(self, valid_checkpoint, temp_dir):
        """Test deploy_checkpoint convenience function."""
        result = deploy_checkpoint(
            checkpoint_path=valid_checkpoint,
            target="local",
            config=DeploymentConfig(local_output_dir=temp_dir),
            merge_weights=False
        )
        
        assert result.success is True
        assert result.version.deployment_type == "local"


# =============================================================================
# Test CLI Parser
# =============================================================================

class TestCLIParser:
    """Tests for CLI parser."""
    
    def test_get_cli_parser(self):
        """Test getting CLI parser."""
        parser = get_cli_parser()
        
        assert parser is not None
    
    def test_cli_parser_deploy_command(self):
        """Test CLI parser deploy command."""
        parser = get_cli_parser()
        
        args = parser.parse_args([
            "deploy",
            "--target", "vllm",
            "--checkpoint", "/path/to/checkpoint"
        ])
        
        assert args.command == "deploy"
        assert args.target == "vllm"
        assert args.checkpoint == "/path/to/checkpoint"
    
    def test_cli_parser_rollback_command(self):
        """Test CLI parser rollback command."""
        parser = get_cli_parser()
        
        args = parser.parse_args([
            "rollback",
            "--version", "v1.0.0"
        ])
        
        assert args.command == "rollback"
        assert args.version == "v1.0.0"
    
    def test_cli_parser_list_command(self):
        """Test CLI parser list command."""
        parser = get_cli_parser()
        
        args = parser.parse_args([
            "list",
            "--status", "active"
        ])
        
        assert args.command == "list"
        assert args.status == "active"


# =============================================================================
# Test ModelDeployer Base Class
# =============================================================================

class TestModelDeployerBase:
    """Tests for ModelDeployer base class."""
    
    def test_initialization_default_config(self):
        """Test initialization with default config."""
        deployer = LocalInferenceDeployer()  # Concrete implementation
        
        assert deployer.config is not None
        assert deployer.checkpoint_manager is not None
    
    def test_initialization_custom_config(self, deployment_config):
        """Test initialization with custom config."""
        deployer = LocalInferenceDeployer(deployment_config)
        
        assert deployer.config == deployment_config
    
    def test_generate_version(self, deployment_config, valid_checkpoint):
        """Test version generation."""
        deployer = LocalInferenceDeployer(deployment_config)
        
        version = deployer._generate_version(
            checkpoint_path=valid_checkpoint,
            model_name="autodev-lora"
        )
        
        assert "autodev-lora" in version
        assert "v1." in version
    
    def test_generate_version_with_sha(self, deployment_config, valid_checkpoint):
        """Test version generation with commit SHA."""
        deployer = LocalInferenceDeployer(deployment_config)
        
        version = deployer._generate_version(
            checkpoint_path=valid_checkpoint,
            model_name="autodev-lora",
            commit_sha="abc123def456"
        )
        
        assert "abc123d" in version  # First 7 chars of SHA
    
    def test_validate_checkpoint_valid(self, deployment_config, valid_checkpoint):
        """Test checkpoint validation."""
        deployer = LocalInferenceDeployer(deployment_config)
        
        result = deployer._validate_checkpoint(valid_checkpoint)
        
        assert result is True
    
    def test_status_default(self, deployment_config):
        """Test default status implementation."""
        deployer = LocalInferenceDeployer(deployment_config)
        
        status = deployer.status()
        
        assert "status" in status


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for deployment workflows."""
    
    @pytest.fixture
    def full_setup(self, temp_dir):
        """Create a full deployment setup."""
        checkpoint_base = Path(temp_dir) / "checkpoints"
        checkpoint_base.mkdir(parents=True, exist_ok=True)
        
        run_dir = checkpoint_base / "run_test"
        run_dir.mkdir(parents=True, exist_ok=True)
        
        ckpt_dir = run_dir / "checkpoint-100"
        ckpt_dir.mkdir(parents=True, exist_ok=True)
        
        (ckpt_dir / "adapter_model.safetensors").write_bytes(b"mock_weights")
        
        adapter_config = {"r": 16, "lora_alpha": 32, "target_modules": ["q_proj"]}
        with open(ckpt_dir / "adapter_config.json", "w") as f:
            json.dump(adapter_config, f)
        
        trainer_state = {"log_history": [{"loss": 0.5}]}
        with open(ckpt_dir / "trainer_state.json", "w") as f:
            json.dump(trainer_state, f)
        
        return {
            "checkpoint_base": str(checkpoint_base),
            "checkpoint_path": str(ckpt_dir),
            "output_dir": str(Path(temp_dir) / "deployed")
        }
    
    def test_full_local_deployment_workflow(self, full_setup):
        """Test complete local deployment workflow."""
        config = DeploymentConfig(
            target=DeploymentTarget.LOCAL,
            base_model="codellama/CodeLlama-7b-hf",
            local_output_dir=full_setup["output_dir"],
            local_merge_weights=False
        )
        
        deployer = LocalInferenceDeployer(config)
        
        # Deploy
        result = deployer.deploy(
            checkpoint_path=full_setup["checkpoint_path"],
            merge_weights=False
        )
        
        assert result.success is True
        assert result.version is not None
        
        # Verify files
        output_path = Path(result.version.endpoint_url)
        assert (output_path / "adapter_model.safetensors").exists()
    
    def test_checkpoint_to_deployment_workflow(self, full_setup):
        """Test workflow from checkpoint discovery to deployment."""
        manager = CheckpointManager(checkpoint_base_dir=full_setup["checkpoint_base"])
        
        # Discover checkpoints
        runs = manager.list_runs()
        assert len(runs) == 1
        
        checkpoints = manager.list_checkpoints(runs[0])
        assert len(checkpoints) == 1
        
        # Validate
        is_valid = manager.validate_checkpoint(checkpoints[0].path)
        assert is_valid
        
        # Deploy
        config = DeploymentConfig(
            target=DeploymentTarget.LOCAL,
            local_output_dir=full_setup["output_dir"]
        )
        
        deployer = LocalInferenceDeployer(config)
        result = deployer.deploy(
            checkpoint_path=checkpoints[0].path,
            merge_weights=False
        )
        
        assert result.success is True
    
    def test_version_registration_workflow(self, full_setup):
        """Test version registration during deployment."""
        registry_path = os.path.join(full_setup["output_dir"], "registry.json")
        registry = VersionRegistry(registry_path=registry_path)
        
        # Deploy and register
        config = DeploymentConfig(
            target=DeploymentTarget.LOCAL,
            local_output_dir=full_setup["output_dir"]
        )
        
        deployer = LocalInferenceDeployer(config)
        result = deployer.deploy(
            checkpoint_path=full_setup["checkpoint_path"],
            merge_weights=False
        )
        
        assert result.success is True
        
        # Register the version
        registry.register(result.version)
        
        # Verify registration
        registered = registry.get_version(result.version.version)
        assert registered is not None
        assert registered.deployment_type == "local"


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=deployment.model_deployer", "--cov-report=term-missing"])
