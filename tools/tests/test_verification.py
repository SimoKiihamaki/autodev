"""Tests for the Verification Protocol.

This module tests the verification protocol implementation from
tools/auto_prd/verification.py.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from auto_prd.verification import (
    QualityGateResult,
    TestResult,
    VerificationEvidence,
    VerificationProtocol,
    VerificationResult,
    verify_feature,
)


@pytest.fixture
def temp_repo(tmp_path: Path) -> Path:
    """Create a temporary directory for testing."""
    repo = tmp_path / "test_repo"
    repo.mkdir()

    # Create .aprd directory structure
    aprd_dir = repo / ".aprd"
    aprd_dir.mkdir()
    evidence_dir = aprd_dir / "evidence"
    evidence_dir.mkdir()

    return repo


@pytest.fixture
def sample_feature() -> dict:
    """Create a sample feature for testing."""
    return {
        "id": "F001",
        "name": "Test Feature",
        "description": "A test feature for verification",
        "status": "in_progress",
        "goals": {
            "primary": "Test the verification protocol",
            "measurable_outcomes": ["All tests pass"],
        },
        "tasks": [
            {"id": "T001", "description": "Implement feature", "status": "completed"},
            {"id": "T002", "description": "Write tests", "status": "completed"},
        ],
        "acceptance_criteria": [
            {
                "id": "AC001",
                "criterion": "Feature works correctly",
                "verification_method": "unit_test",
                "status": "pending",
            },
            {
                "id": "AC002",
                "criterion": "No type errors",
                "verification_method": "type_check",
                "status": "pending",
            },
        ],
        "testing": {
            "unit_tests": [],
            "integration_tests": [],
            "e2e_tests": [],
        },
        "validation": {
            "benchmarks": [],
            "quality_gates": [
                {"gate": "Type Check", "requirement": "No type errors"},
                {"gate": "Lint Check", "requirement": "No lint errors"},
            ],
        },
    }


class TestTestResult:
    """Tests for TestResult dataclass."""

    def test_test_result_passed(self) -> None:
        """Test successful TestResult."""
        result = TestResult(
            name="test_addition",
            passed=True,
            output="1 passed in 0.1s",
            exit_code=0,
            duration_seconds=0.1,
        )
        assert result.passed
        assert result.exit_code == 0
        assert result.duration_seconds == 0.1

    def test_test_result_failed(self) -> None:
        """Test failed TestResult."""
        result = TestResult(
            name="test_addition",
            passed=False,
            output="1 failed",
            exit_code=1,
            tests_failed=1,
        )
        assert not result.passed
        assert result.exit_code == 1
        assert result.tests_failed == 1


class TestQualityGateResult:
    """Tests for QualityGateResult dataclass."""

    def test_quality_gate_passed(self) -> None:
        """Test passed quality gate."""
        result = QualityGateResult(
            gate="Type Check",
            requirement="No type errors",
            passed=True,
            output="Success",
        )
        assert result.passed
        assert not result.skipped

    def test_quality_gate_skipped(self) -> None:
        """Test skipped quality gate."""
        result = QualityGateResult(
            gate="E2E Tests",
            requirement="All e2e tests pass",
            passed=False,
            output="No e2e tests configured",
            skipped=True,
        )
        assert not result.passed
        assert result.skipped


class TestVerificationResult:
    """Tests for VerificationResult dataclass."""

    def test_all_tests_passing_empty(self) -> None:
        """Test all_tests_passing with no tests."""
        result = VerificationResult(
            feature_id="F001",
            passed=True,
        )
        assert result.all_tests_passing  # True when no tests

    def test_all_tests_passing_with_tests(self) -> None:
        """Test all_tests_passing with passing tests."""
        result = VerificationResult(
            feature_id="F001",
            passed=True,
            unit_tests=[
                TestResult(name="test1", passed=True, output="OK", exit_code=0),
                TestResult(name="test2", passed=True, output="OK", exit_code=0),
            ],
        )
        assert result.all_tests_passing

    def test_all_tests_passing_with_failure(self) -> None:
        """Test all_tests_passing with a failed test."""
        result = VerificationResult(
            feature_id="F001",
            passed=False,
            unit_tests=[
                TestResult(name="test1", passed=True, output="OK", exit_code=0),
                TestResult(name="test2", passed=False, output="FAIL", exit_code=1),
            ],
        )
        assert not result.all_tests_passing

    def test_all_gates_passing(self) -> None:
        """Test all_gates_passing with passing gates."""
        result = VerificationResult(
            feature_id="F001",
            passed=True,
            quality_gates=[
                QualityGateResult(
                    gate="Type", requirement="No errors", passed=True, output="OK"
                ),
                QualityGateResult(
                    gate="Lint", requirement="No errors", passed=True, output="OK"
                ),
            ],
        )
        assert result.all_gates_passing


class TestVerificationProtocol:
    """Tests for VerificationProtocol class."""

    def test_init_protocol(self, temp_repo: Path) -> None:
        """Test VerificationProtocol initialization."""
        protocol = VerificationProtocol(repo_root=temp_repo)
        assert protocol.repo_root == temp_repo
        assert protocol.timeout_seconds == 300
        assert not protocol.dry_run

    def test_dry_run_verification(self, temp_repo: Path, sample_feature: dict) -> None:
        """Test verification in dry run mode."""
        protocol = VerificationProtocol(repo_root=temp_repo, dry_run=True)
        result, _ = protocol.verify_feature(sample_feature)

        assert result.passed
        assert result.feature_id == "F001"
        assert result.evidence.verified_by == "dry_run"

    @patch("auto_prd.verification.run_cmd")
    def test_verify_feature_runs_quality_gates(
        self, mock_run_cmd: MagicMock, temp_repo: Path, sample_feature: dict
    ) -> None:
        """Test that verify_feature runs quality gates."""
        # Mock successful command execution
        mock_run_cmd.return_value = ("Success", "", 0)

        protocol = VerificationProtocol(repo_root=temp_repo, timeout_seconds=10)
        result, _ = protocol.verify_feature(sample_feature)

        # Should have attempted to run quality gates
        assert len(result.quality_gates) > 0

    def test_verify_feature_with_tracker_update(
        self, temp_repo: Path, sample_feature: dict
    ) -> None:
        """Test verification updates tracker when passed."""
        tracker = {
            "version": "2.0.0",
            "features": [sample_feature],
            "validation_summary": {"total_features": 1, "total_tasks": 2},
        }

        protocol = VerificationProtocol(repo_root=temp_repo, dry_run=True)
        result, updated_tracker = protocol.verify_feature(sample_feature, tracker)

        assert result.passed
        assert updated_tracker is not None

    def test_detect_test_command_with_makefile(self, temp_repo: Path) -> None:
        """Test test command detection with Makefile."""
        makefile = temp_repo / "Makefile"
        makefile.write_text("test:\n\techo 'test'\n")

        protocol = VerificationProtocol(repo_root=temp_repo)
        cmd = protocol._detect_test_command("unit")

        assert cmd == ["make", "test"]

    def test_detect_test_command_with_package_json(self, temp_repo: Path) -> None:
        """Test test command detection with package.json."""
        package_json = temp_repo / "package.json"
        package_json.write_text('{"name": "test", "scripts": {"test": "jest"}}')

        protocol = VerificationProtocol(repo_root=temp_repo)
        cmd = protocol._detect_test_command("unit")

        assert cmd == ["npm", "test"]

    def test_build_test_command_for_python_file(self, temp_repo: Path) -> None:
        """Test building test command for Python file."""
        protocol = VerificationProtocol(repo_root=temp_repo)
        cmd = protocol._build_test_command_for_file("tests/test_example.py")

        assert cmd == ["pytest", "tests/test_example.py"]

    def test_build_test_command_for_ts_file(self, temp_repo: Path) -> None:
        """Test building test command for TypeScript file."""
        protocol = VerificationProtocol(repo_root=temp_repo)
        cmd = protocol._build_test_command_for_file("src/__tests__/example.test.ts")

        assert cmd == ["npx", "jest", "src/__tests__/example.test.ts"]

    def test_build_test_command_for_go_file(self, temp_repo: Path) -> None:
        """Test building test command for Go file."""
        protocol = VerificationProtocol(repo_root=temp_repo)
        cmd = protocol._build_test_command_for_file("internal/pkg/example_test.go")

        assert cmd == ["go", "test", "-v", "./internal/pkg"]


class TestVerifyFeatureFunction:
    """Tests for verify_feature convenience function."""

    def test_verify_feature_dry_run(
        self, temp_repo: Path, sample_feature: dict
    ) -> None:
        """Test verify_feature function in dry run mode."""
        result, _ = verify_feature(
            feature=sample_feature,
            repo_root=temp_repo,
            dry_run=True,
        )

        assert result.passed
        assert result.feature_id == "F001"

    def test_verify_feature_with_tracker(
        self, temp_repo: Path, sample_feature: dict
    ) -> None:
        """Test verify_feature function with tracker."""
        tracker = {
            "version": "2.0.0",
            "features": [sample_feature],
            "validation_summary": {"total_features": 1, "total_tasks": 2},
        }

        result, updated = verify_feature(
            feature=sample_feature,
            repo_root=temp_repo,
            tracker=tracker,
            dry_run=True,
        )

        assert result.passed
        assert updated is not None


class TestVerificationEvidence:
    """Tests for VerificationEvidence dataclass."""

    def test_evidence_defaults(self) -> None:
        """Test VerificationEvidence default values."""
        evidence = VerificationEvidence()
        assert evidence.test_output_logs == []
        assert evidence.screenshots == []
        assert evidence.verified_at == ""
        assert evidence.verified_by == ""
        assert evidence.duration_seconds == 0.0

    def test_evidence_with_values(self) -> None:
        """Test VerificationEvidence with values."""
        evidence = VerificationEvidence(
            test_output_logs=["/path/to/log.txt"],
            screenshots=["/path/to/screenshot.png"],
            verified_at="2024-01-01T00:00:00Z",
            verified_by="verification_protocol",
            duration_seconds=5.5,
        )
        assert len(evidence.test_output_logs) == 1
        assert len(evidence.screenshots) == 1
        assert evidence.duration_seconds == 5.5
