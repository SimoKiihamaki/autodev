"""Tests for verification backends."""

import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from support_mode.verification_backends import (
    CustomBackend,
    ManualBackend,
    PytestBackend,
    TestResult,
    VerificationMonitor,
    VerificationStatus,
    VerificationSummary,
)


def test_verification_status_enum():
    """Test VerificationStatus enum values."""
    assert VerificationStatus.PENDING == "pending"
    assert VerificationStatus.RUNNING == "running"
    assert VerificationStatus.PASSED == "passed"
    assert VerificationStatus.FAILED == "failed"
    assert VerificationStatus.SKIPPED == "skipped"
    assert VerificationStatus.STALE == "stale"


def test_test_result_defaults():
    """Test TestResult default values."""
    result = TestResult(name="test_example")
    assert result.name == "test_example"
    assert result.status == VerificationStatus.PENDING
    assert result.duration == 0.0
    assert result.message == ""


def test_verification_summary_defaults():
    """Test VerificationSummary default values."""
    summary = VerificationSummary(backend="pytest")
    assert summary.backend == "pytest"
    assert summary.status == VerificationStatus.PENDING
    assert summary.total == 0
    assert summary.passed == 0
    assert summary.failed == 0
    assert summary.skipped == 0
    assert summary.duration == 0.0
    assert summary.results == []


class TestPytestBackend:
    """Tests for PytestBackend."""

    def test_name(self):
        """Test backend name property."""
        backend = PytestBackend()
        assert backend.name == "pytest"

    def test_is_available_success(self):
        """Test is_available when pytest exists."""
        with patch("support_mode.verification_backends.run_cmd") as mock_run:
            mock_run.return_value = MagicMock(stdout="pytest 7.4.0")
            backend = PytestBackend()
            assert backend.is_available(Path("/tmp"))

    def test_is_available_failure(self):
        """Test is_available when pytest not found."""
        with patch("support_mode.verification_backends.run_cmd") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            backend = PytestBackend()
            assert not backend.is_available(Path("/tmp"))

    def test_run_success(self):
        """Test successful pytest run."""
        with patch("support_mode.verification_backends.run_cmd") as mock_run:
            # Mock help check (no json-report)
            mock_run.return_value = MagicMock(
                stdout="usage: pytest [options] [file_or_dir]"
            )
            # Then mock actual pytest run
            mock_run.side_effect = [
                MagicMock(stdout="usage: pytest [options]"),  # --help
                (
                    "tests/test_foo.py::test_bar PASSED\n"
                    "tests/test_foo.py::test_baz FAILED\n",
                    "",
                    1,
                ),  # actual run
            ]

            backend = PytestBackend()
            summary = backend.run(Path("/tmp"))

            assert summary.backend == "pytest"
            assert summary.status == VerificationStatus.FAILED
            assert summary.total == 2
            assert summary.passed == 1
            assert summary.failed == 1

    def test_run_command_error(self):
        """Test pytest run with command error."""
        with patch("support_mode.verification_backends.run_cmd") as mock_run:
            mock_run.side_effect = OSError("pytest not found")

            backend = PytestBackend()
            summary = backend.run(Path("/tmp"))

            assert summary.status == VerificationStatus.FAILED
            assert len(summary.results) == 1
            assert summary.results[0].name == "pytest"
            assert summary.results[0].status == VerificationStatus.FAILED

    def test_parse_pytest_output(self):
        """Test pytest output parsing."""
        backend = PytestBackend()
        output = """
tests/test_foo.py::test_bar PASSED
tests/test_foo.py::test_baz FAILED
tests/test_foo.py::test_qux SKIPPED
        """.strip()

        results = backend._parse_pytest_output(output)

        assert len(results) == 3
        assert results[0].name == "tests/test_foo.py::test_bar"
        assert results[0].status == VerificationStatus.PASSED
        assert results[1].name == "tests/test_foo.py::test_baz"
        assert results[1].status == VerificationStatus.FAILED
        assert results[2].name == "tests/test_foo.py::test_qux"
        assert results[2].status == VerificationStatus.SKIPPED


class TestCustomBackend:
    """Tests for CustomBackend."""

    def test_name(self):
        """Test backend name includes command."""
        backend = CustomBackend(["make", "test"])
        assert backend.name == "custom:make"

    def test_init_empty_command(self):
        """Test initialization with empty command raises ValueError."""
        with pytest.raises(ValueError, match="command must be a non-empty list"):
            CustomBackend([])

    def test_run_success(self):
        """Test successful custom command run."""
        with patch("support_mode.verification_backends.run_cmd") as mock_run:
            mock_run.return_value = ("output", "", 0)

            backend = CustomBackend(["make", "test"])
            summary = backend.run(Path("/tmp"))

            assert summary.backend == "custom:make"
            assert summary.status == VerificationStatus.PASSED
            assert summary.total == 1
            assert summary.passed == 1
            assert summary.failed == 0

    def test_run_failure(self):
        """Test custom command run with failure."""
        with patch("support_mode.verification_backends.run_cmd") as mock_run:
            mock_run.return_value = ("", "error message", 1)

            backend = CustomBackend(["make", "test"])
            summary = backend.run(Path("/tmp"))

            assert summary.status == VerificationStatus.FAILED
            assert summary.total == 1
            assert summary.passed == 0
            assert summary.failed == 1

    def test_run_command_error(self):
        """Test custom command with execution error."""
        with patch("support_mode.verification_backends.run_cmd") as mock_run:
            mock_run.side_effect = OSError("make not found")

            backend = CustomBackend(["make", "test"])
            summary = backend.run(Path("/tmp"))

            assert summary.status == VerificationStatus.FAILED
            assert len(summary.results) == 1
            assert summary.results[0].status == VerificationStatus.FAILED


class TestManualBackend:
    """Tests for ManualBackend."""

    def test_name(self):
        """Test backend name property."""
        backend = ManualBackend()
        assert backend.name == "manual"

    def test_run_no_tracker(self):
        """Test manual backend with no tracker file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = ManualBackend()
            summary = backend.run(Path(tmpdir))

            assert summary.backend == "manual"
            assert summary.status == VerificationStatus.PENDING
            assert summary.total == 0
            assert len(summary.results) == 1
            assert summary.results[0].name == "tracker"
            assert summary.results[0].message == "No tracker found"

    def test_run_with_passed_criteria(self):
        """Test manual backend with passed acceptance criteria."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            aprd_dir = repo_root / ".aprd"
            aprd_dir.mkdir()
            tracker_path = aprd_dir / "tracker.json"

            tracker_data = {
                "version": "2.0.0",
                "metadata": {
                    "prd_source": "test.md",
                    "prd_hash": "sha256:abc123",
                    "created_at": "2025-01-20T00:00:00Z",
                    "created_by": "claude",
                    "project_context": {},
                },
                "features": [
                    {
                        "id": "F001",
                        "name": "Feature 1",
                        "description": "Test",
                        "priority": "high",
                        "status": "pending",
                        "goals": {"primary": "Test", "measurable_outcomes": []},
                        "tasks": [
                            {
                                "id": "T001",
                                "description": "Task 1",
                                "status": "completed",
                            }
                        ],
                        "acceptance_criteria": [
                            {
                                "id": "AC001",
                                "criterion": "Criteria 1",
                                "verification_method": "manual_test",
                                "status": "passed",
                            },
                            {
                                "id": "AC002",
                                "criterion": "Criteria 2",
                                "verification_method": "manual_test",
                                "status": "passed",
                            },
                        ],
                        "testing": {"unit_tests": [], "integration_tests": []},
                        "validation": {"benchmarks": [], "quality_gates": []},
                    }
                ],
                "validation_summary": {
                    "total_features": 1,
                    "total_tasks": 1,
                    "estimated_complexity": "small",
                },
            }
            tracker_path.write_text(json.dumps(tracker_data))

            backend = ManualBackend()
            summary = backend.run(repo_root)

            assert summary.backend == "manual"
            assert summary.status == VerificationStatus.PASSED
            assert summary.total == 2
            assert summary.passed == 2
            assert summary.failed == 0

    def test_run_with_mixed_criteria(self):
        """Test manual backend with mixed pass/fail/pending criteria."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            aprd_dir = repo_root / ".aprd"
            aprd_dir.mkdir()
            tracker_path = aprd_dir / "tracker.json"

            tracker_data = {
                "version": "2.0.0",
                "metadata": {
                    "prd_source": "test.md",
                    "prd_hash": "sha256:abc123",
                    "created_at": "2025-01-20T00:00:00Z",
                    "created_by": "claude",
                    "project_context": {},
                },
                "features": [
                    {
                        "id": "F001",
                        "name": "Feature 1",
                        "description": "Test",
                        "priority": "high",
                        "status": "pending",
                        "goals": {"primary": "Test", "measurable_outcomes": []},
                        "tasks": [
                            {"id": "T001", "description": "Task 1", "status": "pending"}
                        ],
                        "acceptance_criteria": [
                            {
                                "id": "AC001",
                                "criterion": "Criteria 1",
                                "verification_method": "manual_test",
                                "status": "passed",
                            },
                            {
                                "id": "AC002",
                                "criterion": "Criteria 2",
                                "verification_method": "manual_test",
                                "status": "failed",
                            },
                            {
                                "id": "AC003",
                                "criterion": "Criteria 3",
                                "verification_method": "manual_test",
                                "status": "pending",
                            },
                        ],
                        "testing": {"unit_tests": [], "integration_tests": []},
                        "validation": {"benchmarks": [], "quality_gates": []},
                    }
                ],
                "validation_summary": {
                    "total_features": 1,
                    "total_tasks": 1,
                    "estimated_complexity": "small",
                },
            }
            tracker_path.write_text(json.dumps(tracker_data))

            backend = ManualBackend()
            summary = backend.run(repo_root)

            assert summary.status == VerificationStatus.FAILED  # Has failed criteria
            assert summary.total == 3
            assert summary.passed == 1
            assert summary.failed == 1

    def test_run_with_default_pending_status(self):
        """Test manual backend with missing status defaults to pending."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            aprd_dir = repo_root / ".aprd"
            aprd_dir.mkdir()
            tracker_path = aprd_dir / "tracker.json"

            # Missing status field should default to pending
            tracker_data = {
                "version": "2.0.0",
                "metadata": {
                    "prd_source": "test.md",
                    "prd_hash": "sha256:abc123",
                    "created_at": "2025-01-20T00:00:00Z",
                    "created_by": "claude",
                    "project_context": {},
                },
                "features": [
                    {
                        "id": "F001",
                        "name": "Feature 1",
                        "description": "Test",
                        "priority": "high",
                        "status": "pending",
                        "goals": {"primary": "Test", "measurable_outcomes": []},
                        "tasks": [
                            {"id": "T001", "description": "Task 1", "status": "pending"}
                        ],
                        "acceptance_criteria": [
                            {
                                "id": "AC001",
                                "criterion": "Criteria 1",
                                "verification_method": "manual_test",
                                # status field missing - should default to pending
                            },
                        ],
                        "testing": {"unit_tests": [], "integration_tests": []},
                        "validation": {"benchmarks": [], "quality_gates": []},
                    }
                ],
                "validation_summary": {
                    "total_features": 1,
                    "total_tasks": 1,
                    "estimated_complexity": "small",
                },
            }
            tracker_path.write_text(json.dumps(tracker_data))

            backend = ManualBackend()
            summary = backend.run(repo_root)

            # With no passed criteria and pending items, status should be PENDING
            assert summary.status == VerificationStatus.PENDING
            assert summary.total == 1
            assert summary.passed == 0
            assert summary.failed == 0


class TestVerificationMonitor:
    """Tests for VerificationMonitor."""

    def test_init_empty(self):
        """Test initialization with no backends."""
        monitor = VerificationMonitor()
        assert monitor.backends == []
        assert monitor.get_status() == VerificationStatus.PENDING

    def test_init_with_backends(self):
        """Test initialization with backends."""
        backend1 = MagicMock()
        backend1.name = "pytest"
        backend2 = MagicMock()
        backend2.name = "custom:make"

        monitor = VerificationMonitor(backends=[backend1, backend2])
        assert len(monitor.backends) == 2

    def test_add_backend(self):
        """Test adding a backend."""
        monitor = VerificationMonitor()
        backend = MagicMock()
        backend.name = "pytest"

        monitor.add_backend(backend)
        assert len(monitor.backends) == 1

    def test_run_all_success(self):
        """Test running all backends successfully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)

            # Create a valid tracker
            aprd_dir = repo_root / ".aprd"
            aprd_dir.mkdir()
            tracker_path = aprd_dir / "tracker.json"
            tracker_data = {
                "version": "2.0.0",
                "metadata": {
                    "prd_source": "test.md",
                    "prd_hash": "sha256:abc123",
                    "created_at": "2025-01-20T00:00:00Z",
                    "created_by": "claude",
                    "project_context": {},
                },
                "features": [
                    {
                        "id": "F001",
                        "name": "Feature 1",
                        "description": "Test",
                        "priority": "high",
                        "status": "pending",
                        "goals": {"primary": "Test", "measurable_outcomes": []},
                        "tasks": [
                            {"id": "T001", "description": "Task 1", "status": "pending"}
                        ],
                        "acceptance_criteria": [
                            {
                                "id": "AC001",
                                "criterion": "Criteria 1",
                                "verification_method": "manual_test",
                                "status": "passed",
                            },
                        ],
                        "testing": {"unit_tests": [], "integration_tests": []},
                        "validation": {"benchmarks": [], "quality_gates": []},
                    }
                ],
                "validation_summary": {
                    "total_features": 1,
                    "total_tasks": 1,
                    "estimated_complexity": "small",
                },
            }
            tracker_path.write_text(json.dumps(tracker_data))

            monitor = VerificationMonitor()
            monitor.add_backend(ManualBackend())

            results = monitor.run_all(repo_root)

            assert "manual" in results
            assert results["manual"].status == VerificationStatus.PASSED
            assert monitor.get_status() == VerificationStatus.PASSED

    def test_run_all_backend_failure(self):
        """Test running backends when one fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)

            # Create a valid tracker
            aprd_dir = repo_root / ".aprd"
            aprd_dir.mkdir()
            tracker_path = aprd_dir / "tracker.json"
            tracker_data = {
                "version": "2.0.0",
                "metadata": {
                    "prd_source": "test.md",
                    "prd_hash": "sha256:abc123",
                    "created_at": "2025-01-20T00:00:00Z",
                    "created_by": "claude",
                    "project_context": {},
                },
                "features": [],
                "validation_summary": {
                    "total_features": 0,
                    "total_tasks": 0,
                    "estimated_complexity": "small",
                },
            }
            tracker_path.write_text(json.dumps(tracker_data))

            failing_backend = MagicMock()
            failing_backend.name = "failing"
            failing_backend.is_available.return_value = True
            failing_backend.run.side_effect = RuntimeError("Backend error")

            monitor = VerificationMonitor()
            monitor.add_backend(failing_backend)

            results = monitor.run_all(repo_root)

            assert "failing" in results
            assert results["failing"].status == VerificationStatus.FAILED
            assert monitor.get_status() == VerificationStatus.FAILED

    def test_run_all_backend_not_available(self):
        """Test that unavailable backends are skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)

            unavailable_backend = MagicMock()
            unavailable_backend.name = "unavailable"
            unavailable_backend.is_available.return_value = False

            monitor = VerificationMonitor()
            monitor.add_backend(unavailable_backend)

            results = monitor.run_all(repo_root)

            assert "unavailable" not in results
            assert len(results) == 0

    def test_get_status_no_results(self):
        """Test get_status when no backends have run."""
        monitor = VerificationMonitor()
        assert monitor.get_status() == VerificationStatus.PENDING

    def test_get_status_all_passed(self):
        """Test get_status when all backends passed."""
        monitor = VerificationMonitor()
        monitor._results = {
            "backend1": VerificationSummary(
                backend="backend1",
                status=VerificationStatus.PASSED,
            ),
            "backend2": VerificationSummary(
                backend="backend2",
                status=VerificationStatus.PASSED,
            ),
        }
        assert monitor.get_status() == VerificationStatus.PASSED

    def test_get_status_one_failed(self):
        """Test get_status when one backend failed."""
        monitor = VerificationMonitor()
        monitor._results = {
            "backend1": VerificationSummary(
                backend="backend1",
                status=VerificationStatus.PASSED,
            ),
            "backend2": VerificationSummary(
                backend="backend2",
                status=VerificationStatus.FAILED,
            ),
        }
        assert monitor.get_status() == VerificationStatus.FAILED

    def test_load_tracker_format_aprd(self):
        """Test loading aprd format tracker."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            aprd_dir = repo_root / ".aprd"
            aprd_dir.mkdir()
            tracker_path = aprd_dir / "tracker.json"

            tracker_data = {
                "version": "2.0.0",
                "metadata": {
                    "prd_source": "test.md",
                    "prd_hash": "sha256:abc123",
                    "created_at": "2025-01-20T00:00:00Z",
                    "created_by": "claude",
                    "project_context": {},
                },
                "features": [],
                "validation_summary": {
                    "total_features": 0,
                    "total_tasks": 0,
                    "estimated_complexity": "small",
                },
            }
            tracker_path.write_text(json.dumps(tracker_data))

            monitor = VerificationMonitor()
            tracker = monitor._load_tracker_format(repo_root, "aprd")

            assert tracker is not None
            assert tracker["version"] == "2.0.0"

    def test_load_tracker_format_taskmaster(self):
        """Test loading taskmaster format tracker."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            taskmaster_dir = repo_root / ".taskmaster"
            taskmaster_dir.mkdir()
            tracker_path = taskmaster_dir / "tracker.json"

            tracker_data = {"tasks": []}
            tracker_path.write_text(json.dumps(tracker_data))

            monitor = VerificationMonitor()
            tracker = monitor._load_tracker_format(repo_root, "taskmaster")

            assert tracker is not None
            assert "tasks" in tracker

    def test_load_tracker_format_simple(self):
        """Test loading simple tasks.json format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            tracker_path = repo_root / "tasks.json"

            tracker_data = {"tasks": []}
            tracker_path.write_text(json.dumps(tracker_data))

            monitor = VerificationMonitor()
            tracker = monitor._load_tracker_format(repo_root, "tasks")

            assert tracker is not None
            assert "tasks" in tracker

    def test_load_tracker_format_unknown(self):
        """Test loading unknown format returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)

            monitor = VerificationMonitor()
            tracker = monitor._load_tracker_format(repo_root, "unknown")

            assert tracker is None

    def test_load_tracker_invalid_json(self):
        """Test loading tracker with invalid JSON returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            taskmaster_dir = repo_root / ".taskmaster"
            taskmaster_dir.mkdir()
            tracker_path = taskmaster_dir / "tracker.json"

            tracker_path.write_text("invalid json")

            monitor = VerificationMonitor()
            tracker = monitor._load_tracker_format(repo_root, "taskmaster")

            assert tracker is None
