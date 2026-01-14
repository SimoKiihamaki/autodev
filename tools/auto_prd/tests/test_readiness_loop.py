"""Tests for Ralph Wiggum Loop readiness orchestrator."""

import json
from pathlib import Path

import pytest


@pytest.fixture
def temp_repo(tmp_path: Path) -> Path:
    """Create a temporary repository structure."""
    aprd_dir = tmp_path / ".aprd"
    aprd_dir.mkdir(parents=True, exist_ok=True)

    # Create .git to make it a valid repo
    (tmp_path / ".git").mkdir(parents=True, exist_ok=True)

    tracker_content = {
        "version": "2.0.0",
        "prd_hash": "test_hash_123",
        "features": [
            {
                "id": "F001",
                "title": "Test Feature",
                "status": "verified",
                "acceptance_criteria": [],
            }
        ],
    }
    (aprd_dir / "tracker.json").write_text(json.dumps(tracker_content, indent=2))

    return tmp_path


def test_readiness_config() -> None:
    """Test ReadinessConfig has sensible defaults."""
    # Import here to avoid issues with circular imports
    from tools.auto_prd.readiness_loop import ReadinessConfig

    config = ReadinessConfig()
    assert config.enabled is True
    assert config.max_iterations == 100
    assert config.scope_review_interval == 5
    assert config.failure_to_sign_threshold == 2
    assert config.base_branch == "main"
    assert config.create_issue_on_stall is False


def test_readiness_orchestrator_init(temp_repo: Path) -> None:
    """Test ReadinessOrchestrator initialization."""
    from tools.auto_prd.readiness_loop import ReadinessConfig, ReadinessOrchestrator

    config = ReadinessConfig(max_iterations=1)
    orchestrator = ReadinessOrchestrator(temp_repo, config)

    assert orchestrator.repo_root == temp_repo
    assert orchestrator.config.max_iterations == 1
    assert orchestrator.state_dir == temp_repo / ".aprd"


def test_readiness_orchestrator_load_tracker(temp_repo: Path) -> None:
    """Test tracker loading functionality."""
    from tools.auto_prd.readiness_loop import ReadinessOrchestrator

    orchestrator = ReadinessOrchestrator(temp_repo)
    tracker = orchestrator._load_tracker()

    assert tracker is not None
    assert tracker["version"] == "2.0.0"
    assert len(tracker["features"]) == 1
    assert tracker["features"][0]["id"] == "F001"


def test_readiness_orchestrator_count_features(temp_repo: Path) -> None:
    """Test feature counting by status."""
    from tools.auto_prd.readiness_loop import ReadinessOrchestrator

    orchestrator = ReadinessOrchestrator(temp_repo)
    tracker = orchestrator._load_tracker()
    counts = orchestrator._count_features(tracker)

    assert counts["verified"] == 1
    assert counts["pending"] == 0
    assert counts["in_progress"] == 0
    assert counts["completed"] == 0
