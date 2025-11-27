"""Tests for the verification module.

This module tests the VerificationProtocol and related functionality.
"""

import tempfile
import unittest
from pathlib import Path

from auto_prd.verification import (
    QualityGateResult,
    TestResult,
    VerificationEvidence,
    VerificationProtocol,
    VerificationResult,
    _sanitize_filename,
)


class SanitizeFilenameTests(unittest.TestCase):
    """Tests for _sanitize_filename function."""

    def test_removes_unsafe_characters(self) -> None:
        """Should replace unsafe characters with underscores."""
        result = _sanitize_filename("test<file>name.txt")
        self.assertNotIn("<", result)
        self.assertNotIn(">", result)

    def test_strips_path_separators(self) -> None:
        """Should strip path components."""
        result = _sanitize_filename("/path/to/file.txt")
        self.assertEqual(result, "file.txt")

    def test_truncates_long_names(self) -> None:
        """Should truncate names longer than max_length."""
        long_name = "a" * 100
        result = _sanitize_filename(long_name, max_length=50)
        self.assertEqual(len(result), 50)

    def test_returns_unknown_for_empty(self) -> None:
        """Should return 'unknown' for empty strings."""
        result = _sanitize_filename("")
        self.assertEqual(result, "unknown")

    def test_collapses_multiple_underscores(self) -> None:
        """Should collapse multiple consecutive underscores."""
        result = _sanitize_filename("test___file___name")
        self.assertNotIn("___", result)


class TestResultTests(unittest.TestCase):
    """Tests for TestResult dataclass."""

    def test_passed_test_result(self) -> None:
        """TestResult should represent a passing test."""
        result = TestResult(
            name="unit_tests",
            passed=True,
            output="All tests passed",
            exit_code=0,
            tests_run=10,
            tests_failed=0,
        )
        self.assertTrue(result.passed)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.tests_run, 10)
        self.assertEqual(result.tests_failed, 0)

    def test_failed_test_result(self) -> None:
        """TestResult should represent a failing test."""
        result = TestResult(
            name="unit_tests",
            passed=False,
            output="2 tests failed",
            exit_code=1,
            tests_run=10,
            tests_failed=2,
        )
        self.assertFalse(result.passed)
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.tests_failed, 2)


class QualityGateResultTests(unittest.TestCase):
    """Tests for QualityGateResult dataclass."""

    def test_passing_gate(self) -> None:
        """QualityGateResult should represent a passing gate."""
        result = QualityGateResult(
            gate="type_check",
            requirement="All types must be valid",
            passed=True,
            output="Type check passed",
        )
        self.assertTrue(result.passed)
        self.assertFalse(result.skipped)

    def test_failing_gate(self) -> None:
        """QualityGateResult should represent a failing gate."""
        result = QualityGateResult(
            gate="lint",
            requirement="No lint errors",
            passed=False,
            output="3 lint errors found",
            details="Line 10: Missing semicolon",
        )
        self.assertFalse(result.passed)
        self.assertEqual(result.details, "Line 10: Missing semicolon")

    def test_skipped_gate(self) -> None:
        """QualityGateResult should represent a skipped gate."""
        result = QualityGateResult(
            gate="e2e_test",
            requirement="E2E tests pass",
            passed=True,
            output="Skipped",
            skipped=True,
        )
        self.assertTrue(result.skipped)


class VerificationResultTests(unittest.TestCase):
    """Tests for VerificationResult dataclass."""

    def test_all_tests_passing_with_passing_tests(self) -> None:
        """all_tests_passing should be True when all tests pass."""
        result = VerificationResult(
            feature_id="F001",
            passed=True,
            unit_tests=[
                TestResult(
                    name="unit", passed=True, output="", exit_code=0, tests_run=5
                )
            ],
            integration_tests=[
                TestResult(
                    name="integration", passed=True, output="", exit_code=0, tests_run=3
                )
            ],
        )
        self.assertTrue(result.all_tests_passing)

    def test_all_tests_passing_with_failing_tests(self) -> None:
        """all_tests_passing should be False when any test fails."""
        result = VerificationResult(
            feature_id="F001",
            passed=False,
            unit_tests=[
                TestResult(
                    name="unit", passed=True, output="", exit_code=0, tests_run=5
                )
            ],
            integration_tests=[
                TestResult(
                    name="integration",
                    passed=False,
                    output="Failed",
                    exit_code=1,
                    tests_run=3,
                )
            ],
        )
        self.assertFalse(result.all_tests_passing)

    def test_all_tests_passing_with_empty_tests(self) -> None:
        """all_tests_passing should be True when no tests defined."""
        result = VerificationResult(feature_id="F001", passed=True)
        self.assertTrue(result.all_tests_passing)

    def test_all_gates_passing_with_passing_gates(self) -> None:
        """all_gates_passing should be True when all gates pass."""
        result = VerificationResult(
            feature_id="F001",
            passed=True,
            quality_gates=[
                QualityGateResult(gate="lint", requirement="", passed=True, output=""),
                QualityGateResult(
                    gate="type_check", requirement="", passed=True, output=""
                ),
            ],
        )
        self.assertTrue(result.all_gates_passing)

    def test_all_gates_passing_with_failing_gate(self) -> None:
        """all_gates_passing should be False when any gate fails."""
        result = VerificationResult(
            feature_id="F001",
            passed=False,
            quality_gates=[
                QualityGateResult(gate="lint", requirement="", passed=True, output=""),
                QualityGateResult(
                    gate="type_check", requirement="", passed=False, output="Failed"
                ),
            ],
        )
        self.assertFalse(result.all_gates_passing)


class VerificationProtocolTests(unittest.TestCase):
    """Tests for VerificationProtocol class."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.repo_root = Path(self.temp_dir)

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir)

    def test_protocol_initialization(self) -> None:
        """Protocol should be created with correct parameters."""
        protocol = VerificationProtocol(
            repo_root=self.repo_root, timeout_seconds=600, dry_run=True
        )
        self.assertEqual(protocol.repo_root, self.repo_root)
        self.assertEqual(protocol.timeout_seconds, 600)
        self.assertTrue(protocol.dry_run)

    def test_dry_run_skips_verification(self) -> None:
        """In dry run mode, verification should return success without running tests."""
        protocol = VerificationProtocol(
            repo_root=self.repo_root, timeout_seconds=300, dry_run=True
        )
        feature = {
            "id": "F001",
            "name": "Test Feature",
            "status": "in_progress",
            "testing": {"unit_tests": [], "integration_tests": []},
            "validation": {"quality_gates": []},
        }

        result, _ = protocol.verify_feature(feature)

        self.assertTrue(result.passed)
        self.assertEqual(result.evidence.verified_by, "dry_run")

    def test_dry_run_preserves_tracker(self) -> None:
        """In dry run mode, tracker should be returned unchanged."""
        protocol = VerificationProtocol(
            repo_root=self.repo_root, timeout_seconds=300, dry_run=True
        )
        feature = {"id": "F001", "name": "Test Feature", "status": "in_progress"}
        tracker = {
            "version": "2.0.0",
            "features": [feature],
        }

        _, updated_tracker = protocol.verify_feature(feature, tracker)

        self.assertIsNotNone(updated_tracker)
        self.assertEqual(updated_tracker, tracker)


class VerificationEvidenceTests(unittest.TestCase):
    """Tests for VerificationEvidence dataclass."""

    def test_empty_evidence(self) -> None:
        """Empty evidence should have empty lists."""
        evidence = VerificationEvidence()
        self.assertEqual(evidence.test_output_logs, [])
        self.assertEqual(evidence.screenshots, [])
        self.assertEqual(evidence.verified_at, "")
        self.assertEqual(evidence.verified_by, "")

    def test_evidence_with_data(self) -> None:
        """Evidence should store provided data."""
        evidence = VerificationEvidence(
            test_output_logs=["log1.txt", "log2.txt"],
            screenshots=["screenshot1.png"],
            verified_at="2024-01-01T00:00:00Z",
            verified_by="claude",
            duration_seconds=10.5,
        )
        self.assertEqual(len(evidence.test_output_logs), 2)
        self.assertEqual(len(evidence.screenshots), 1)
        self.assertEqual(evidence.duration_seconds, 10.5)


if __name__ == "__main__":
    unittest.main()
