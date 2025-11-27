"""Tests for the initializer module.

This module tests the InitializerAgent and related functionality.
"""

import json
import tempfile
import unittest
from pathlib import Path

from auto_prd.initializer import BaselineResult, InitializerAgent, InitResult
from auto_prd.tracker_generator import TRACKER_VERSION


class InitResultTests(unittest.TestCase):
    """Tests for InitResult dataclass."""

    def test_success_property_true_when_no_errors(self) -> None:
        """success should be True when tracker exists and no errors."""
        result = InitResult(
            tracker={"version": TRACKER_VERSION},
            tracker_path=Path("/tmp/tracker.json"),
            baseline_passed=True,
            baseline_output="",
            next_feature=None,
            errors=[],
        )
        self.assertTrue(result.success)

    def test_success_property_false_when_errors_present(self) -> None:
        """success should be False when errors list is non-empty."""
        result = InitResult(
            tracker={"version": TRACKER_VERSION},
            tracker_path=Path("/tmp/tracker.json"),
            baseline_passed=True,
            baseline_output="",
            next_feature=None,
            errors=["Some error occurred"],
        )
        self.assertFalse(result.success)

    def test_success_property_false_when_tracker_is_none(self) -> None:
        """success should be False when tracker is None."""
        result = InitResult(
            tracker=None,  # type: ignore
            tracker_path=Path("/tmp/tracker.json"),
            baseline_passed=True,
            baseline_output="",
            next_feature=None,
            errors=[],
        )
        self.assertFalse(result.success)


class BaselineResultTests(unittest.TestCase):
    """Tests for BaselineResult dataclass."""

    def test_baseline_result_with_success(self) -> None:
        """BaselineResult should correctly represent successful tests."""
        result = BaselineResult(
            success=True, output="All tests passed", exit_code=0, errors=[]
        )
        self.assertTrue(result.success)
        self.assertEqual(result.exit_code, 0)

    def test_baseline_result_with_failure(self) -> None:
        """BaselineResult should correctly represent failed tests."""
        result = BaselineResult(
            success=False, output="Test failed", exit_code=1, errors=["Test failure"]
        )
        self.assertFalse(result.success)
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(len(result.errors), 1)


class InitializerAgentTests(unittest.TestCase):
    """Tests for InitializerAgent class."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.repo_root = Path(self.temp_dir)
        # Create minimal git repo structure
        (self.repo_root / ".git").mkdir()

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir)

    def test_agent_initialization(self) -> None:
        """Agent should be created with correct parameters."""
        agent = InitializerAgent(
            repo_root=self.repo_root,
            executor="claude",
            allow_unsafe_execution=True,
            dry_run=True,
        )
        self.assertEqual(agent.repo_root, self.repo_root)
        self.assertEqual(agent.executor, "claude")
        self.assertTrue(agent.allow_unsafe_execution)
        self.assertTrue(agent.dry_run)

    def test_agent_dry_run_generates_mock_tracker(self) -> None:
        """In dry run mode, agent should generate a valid mock tracker."""
        # Create a simple PRD file
        prd_path = self.repo_root / "test.md"
        prd_path.write_text("# Test PRD\n\nThis is a test PRD.")

        agent = InitializerAgent(
            repo_root=self.repo_root,
            executor="claude",
            allow_unsafe_execution=True,
            dry_run=True,
        )
        result = agent.run(prd_path)

        # In dry run mode, we expect a mock tracker
        self.assertTrue(result.success)
        self.assertIsNotNone(result.tracker)
        self.assertEqual(result.tracker.get("version"), TRACKER_VERSION)

    def test_command_exists_returns_false_for_nonexistent(self) -> None:
        """_command_exists should return False for nonexistent commands."""
        agent = InitializerAgent(
            repo_root=self.repo_root, executor="claude", dry_run=True
        )
        # Test with a command that definitely doesn't exist
        result = agent._command_exists("nonexistent_command_xyz123")
        self.assertFalse(result)


class InitializerWithExistingTrackerTests(unittest.TestCase):
    """Tests for InitializerAgent with an existing tracker."""

    def setUp(self) -> None:
        """Set up test fixtures with existing tracker."""
        self.temp_dir = tempfile.mkdtemp()
        self.repo_root = Path(self.temp_dir)
        (self.repo_root / ".git").mkdir()

        # Create .aprd directory with a tracker
        aprd_dir = self.repo_root / ".aprd"
        aprd_dir.mkdir()

        self.tracker = {
            "version": TRACKER_VERSION,
            "metadata": {
                "prd_source": "test.md",
                "prd_hash": "sha256:1234567890123456",
                "created_at": "2024-01-01T00:00:00Z",
                "created_by": "claude",
                "project_context": {},
            },
            "features": [
                {
                    "id": "F001",
                    "name": "Test Feature",
                    "description": "Test description",
                    "priority": "high",
                    "complexity": "M",
                    "status": "pending",
                    "dependencies": [],
                    "goals": {
                        "primary": "Test goal",
                        "secondary": [],
                        "measurable_outcomes": ["Outcome 1"],
                    },
                    "tasks": [
                        {"id": "T001", "description": "Test task", "status": "pending"}
                    ],
                    "acceptance_criteria": [
                        {
                            "id": "AC001",
                            "criterion": "Test criterion",
                            "verification_method": "unit_test",
                            "status": "pending",
                        }
                    ],
                    "testing": {"unit_tests": [], "integration_tests": []},
                    "validation": {"benchmarks": [], "quality_gates": []},
                    "files": {"to_create": [], "to_modify": []},
                    "commits": [],
                    "verification_evidence": {},
                }
            ],
            "validation_summary": {
                "total_features": 1,
                "total_tasks": 1,
                "estimated_complexity": "small",
                "critical_path": ["F001"],
            },
        }
        (aprd_dir / "tracker.json").write_text(json.dumps(self.tracker))

        # Create PRD file
        self.prd_path = self.repo_root / "test.md"
        self.prd_path.write_text("# Test PRD\n\nThis is a test PRD.")

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir)

    def test_uses_existing_tracker_when_present(self) -> None:
        """Agent should use existing tracker instead of regenerating."""
        agent = InitializerAgent(
            repo_root=self.repo_root,
            executor="claude",
            allow_unsafe_execution=True,
            dry_run=True,
        )
        result = agent.run(self.prd_path)

        self.assertTrue(result.success)
        self.assertEqual(result.tracker["features"][0]["id"], "F001")

    def test_selects_next_feature(self) -> None:
        """Agent should select the next pending feature."""
        agent = InitializerAgent(
            repo_root=self.repo_root,
            executor="claude",
            allow_unsafe_execution=True,
            dry_run=True,
        )
        result = agent.run(self.prd_path)

        self.assertIsNotNone(result.next_feature)
        self.assertEqual(result.next_feature["id"], "F001")


if __name__ == "__main__":
    unittest.main()
