"""Tests for the Initializer Agent.

This module tests the initializer agent implementation from
tools/auto_prd/initializer.py.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from auto_prd.initializer import (
    BaselineResult,
    InitializerAgent,
    InitResult,
    run_initializer,
)


@pytest.fixture
def temp_repo(tmp_path: Path) -> Path:
    """Create a temporary git repository for testing."""
    repo = tmp_path / "test_repo"
    repo.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    # Create initial commit
    readme = repo / "README.md"
    readme.write_text("# Test Repo\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    return repo


@pytest.fixture
def sample_prd(temp_repo: Path) -> Path:
    """Create a sample PRD file."""
    prd_path = temp_repo / "test_prd.md"
    prd_path.write_text(
        """# Test Feature PRD

## Overview
Implement a simple test feature.

## Requirements
1. Create a function that adds two numbers
2. Write unit tests for the function

## Acceptance Criteria
- Function returns correct sum
- All tests pass
"""
    )
    return prd_path


class TestInitializerAgent:
    """Tests for InitializerAgent class."""

    def test_init_requires_repo_root(self, temp_repo: Path) -> None:
        """Test that InitializerAgent requires a valid repo root."""
        agent = InitializerAgent(repo_root=temp_repo)
        assert agent.repo_root == temp_repo
        assert agent.executor == "claude"  # default
        assert agent.allow_unsafe_execution is True
        assert agent.dry_run is False

    def test_init_with_custom_executor(self, temp_repo: Path) -> None:
        """Test InitializerAgent with custom executor."""
        agent = InitializerAgent(repo_root=temp_repo, executor="codex")
        assert agent.executor == "codex"

    def test_init_dry_run_mode(self, temp_repo: Path) -> None:
        """Test InitializerAgent in dry run mode."""
        agent = InitializerAgent(repo_root=temp_repo, dry_run=True)
        assert agent.dry_run is True

    @patch("auto_prd.initializer.generate_tracker")
    def test_run_generates_tracker(
        self, mock_generate: MagicMock, temp_repo: Path, sample_prd: Path
    ) -> None:
        """Test that run() generates a tracker."""
        mock_tracker = {
            "version": "2.0.0",
            "metadata": {"prd_source": str(sample_prd)},
            "features": [
                {
                    "id": "F001",
                    "name": "Test Feature",
                    "status": "pending",
                    "tasks": [{"id": "T001", "status": "pending"}],
                }
            ],
            "validation_summary": {"total_features": 1, "total_tasks": 1},
        }
        mock_generate.return_value = mock_tracker

        agent = InitializerAgent(repo_root=temp_repo, dry_run=True)
        result = agent.run(sample_prd)

        assert result.success
        assert result.tracker is not None
        assert result.tracker["version"] == "2.0.0"

    @patch("auto_prd.initializer.generate_tracker")
    def test_run_selects_first_feature(
        self, mock_generate: MagicMock, temp_repo: Path, sample_prd: Path
    ) -> None:
        """Test that run() selects the first available feature."""
        mock_tracker = {
            "version": "2.0.0",
            "metadata": {"prd_source": str(sample_prd)},
            "features": [
                {
                    "id": "F001",
                    "name": "First Feature",
                    "status": "pending",
                    "priority": "high",
                    "tasks": [{"id": "T001", "status": "pending"}],
                    "dependencies": [],
                },
                {
                    "id": "F002",
                    "name": "Second Feature",
                    "status": "pending",
                    "priority": "medium",
                    "tasks": [{"id": "T002", "status": "pending"}],
                    "dependencies": ["F001"],
                },
            ],
            "validation_summary": {"total_features": 2, "total_tasks": 2},
        }
        mock_generate.return_value = mock_tracker

        agent = InitializerAgent(repo_root=temp_repo, dry_run=True)
        result = agent.run(sample_prd)

        assert result.success
        assert result.next_feature is not None
        assert result.next_feature["id"] == "F001"

    @patch("auto_prd.initializer.generate_tracker")
    def test_run_handles_tracker_generation_failure(
        self, mock_generate: MagicMock, temp_repo: Path, sample_prd: Path
    ) -> None:
        """Test that run() handles tracker generation failures."""
        mock_generate.side_effect = ValueError("Failed to generate tracker")

        agent = InitializerAgent(repo_root=temp_repo, dry_run=True)
        result = agent.run(sample_prd)

        assert not result.success
        assert len(result.errors) > 0
        assert "Failed to generate tracker" in result.errors[0]


class TestBaselineResult:
    """Tests for BaselineResult dataclass."""

    def test_baseline_result_success(self) -> None:
        """Test successful BaselineResult."""
        result = BaselineResult(success=True, output="All tests passed", exit_code=0)
        assert result.success
        assert result.exit_code == 0
        assert len(result.errors) == 0

    def test_baseline_result_failure(self) -> None:
        """Test failed BaselineResult."""
        result = BaselineResult(
            success=False,
            output="Test failed",
            exit_code=1,
            errors=["Test assertion failed"],
        )
        assert not result.success
        assert result.exit_code == 1
        assert len(result.errors) == 1


class TestInitResult:
    """Tests for InitResult dataclass."""

    def test_init_result_success_property(self, tmp_path: Path) -> None:
        """Test InitResult.success property."""
        result = InitResult(
            tracker={"version": "2.0.0"},
            tracker_path=tmp_path / "tracker.json",
            baseline_passed=True,
            baseline_output="OK",
            next_feature={"id": "F001"},
            errors=[],
        )
        assert result.success

    def test_init_result_fails_with_errors(self, tmp_path: Path) -> None:
        """Test InitResult.success is False when errors exist."""
        result = InitResult(
            tracker={"version": "2.0.0"},
            tracker_path=tmp_path / "tracker.json",
            baseline_passed=True,
            baseline_output="OK",
            next_feature={"id": "F001"},
            errors=["Something went wrong"],
        )
        assert not result.success

    def test_init_result_fails_with_no_tracker(self, tmp_path: Path) -> None:
        """Test InitResult.success is False when tracker is None."""
        result = InitResult(
            tracker=None,
            tracker_path=tmp_path / "tracker.json",
            baseline_passed=True,
            baseline_output="OK",
            next_feature=None,
            errors=[],
        )
        # success checks for empty tracker dict, not None
        assert not result.success


class TestRunInitializer:
    """Tests for run_initializer convenience function."""

    @patch("auto_prd.initializer.InitializerAgent")
    def test_run_initializer_creates_agent(
        self, mock_agent_class: MagicMock, temp_repo: Path, sample_prd: Path
    ) -> None:
        """Test run_initializer creates and runs an InitializerAgent."""
        mock_agent = MagicMock()
        mock_agent.run.return_value = InitResult(
            tracker={"version": "2.0.0"},
            tracker_path=temp_repo / ".aprd" / "tracker.json",
            baseline_passed=True,
            baseline_output="OK",
            next_feature={"id": "F001"},
            errors=[],
        )
        mock_agent_class.return_value = mock_agent

        result = run_initializer(
            prd_path=sample_prd,
            repo_root=temp_repo,
            executor="claude",
            dry_run=True,
        )

        mock_agent_class.assert_called_once_with(
            repo_root=temp_repo,
            executor="claude",
            allow_unsafe_execution=True,
            dry_run=True,
        )
        mock_agent.run.assert_called_once()
        assert result.tracker is not None
