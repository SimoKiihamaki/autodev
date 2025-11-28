"""Tests for executor resolution in tracker generation.

This module tests that the executor resolution for tracker generation
correctly maps policy strings to executor names.
"""

import unittest
from unittest.mock import patch

from auto_prd.policy import policy_runner


class PolicyRunnerExecutorResolutionTests(unittest.TestCase):
    """Tests for policy_runner executor resolution."""

    def test_codex_first_policy_resolves_to_codex_on_first_iteration(self) -> None:
        """codex-first policy with i=1 should return Codex executor."""
        _, label = policy_runner("codex-first", i=1, phase="implement")
        self.assertEqual(label, "Codex")
        self.assertEqual(label.lower(), "codex")

    def test_codex_first_policy_resolves_to_claude_on_later_iterations(self) -> None:
        """codex-first policy with i>1 should return Claude executor."""
        _, label = policy_runner("codex-first", i=2, phase="implement")
        self.assertEqual(label, "Claude")
        self.assertEqual(label.lower(), "claude")

    def test_codex_only_policy_always_resolves_to_codex(self) -> None:
        """codex-only policy should always return Codex executor."""
        for i in [1, 2, 3, 10]:
            _, label = policy_runner("codex-only", i=i, phase="implement")
            self.assertEqual(label, "Codex")

    def test_claude_only_policy_always_resolves_to_claude(self) -> None:
        """claude-only policy should always return Claude executor."""
        for i in [1, 2, 3, 10]:
            _, label = policy_runner("claude-only", i=i, phase="implement")
            self.assertEqual(label, "Claude")

    def test_pr_phase_uses_claude_regardless_of_policy(self) -> None:
        """PR phase should use Claude regardless of policy."""
        _, label = policy_runner("codex-first", i=1, phase="pr")
        self.assertEqual(label, "Claude")

    def test_review_fix_phase_uses_claude_regardless_of_policy(self) -> None:
        """review_fix phase should use Claude regardless of policy."""
        _, label = policy_runner("codex-first", i=1, phase="review_fix")
        self.assertEqual(label, "Claude")

    def test_executor_label_lowercase_gives_valid_created_by_value(self) -> None:
        """label.lower() should produce valid created_by values for tracker validation."""
        valid_created_by = {"claude", "codex"}

        test_cases = [
            ("codex-first", 1, "implement"),
            ("codex-first", 2, "implement"),
            ("codex-only", 1, "implement"),
            ("claude-only", 1, "implement"),
        ]

        for policy, iteration, phase in test_cases:
            with self.subTest(policy=policy, iteration=iteration, phase=phase):
                _, label = policy_runner(policy, i=iteration, phase=phase)
                executor = label.lower()
                self.assertIn(
                    executor,
                    valid_created_by,
                    f"Policy '{policy}' resolved to invalid executor '{executor}'",
                )


class TrackerExecutorResolutionIntegrationTests(unittest.TestCase):
    """Integration tests to verify the bug fix for codex-first policy."""

    @patch("auto_prd.tracker_generator.codex_exec")
    @patch("auto_prd.tracker_generator.claude_exec")
    def test_generate_tracker_with_codex_executor_sets_correct_created_by(
        self, mock_claude: unittest.mock.MagicMock, mock_codex: unittest.mock.MagicMock
    ) -> None:
        """generate_tracker with executor='codex' should set created_by='codex'."""
        import json
        import tempfile
        from pathlib import Path

        from auto_prd.tracker_generator import generate_tracker, validate_tracker

        # Mock the codex_exec to return a valid tracker JSON
        mock_tracker = {
            "version": "1.0.0",
            "metadata": {
                "prd_source": "test.md",
                "prd_hash": "sha256:1234567890abcdef",
                "created_at": "2024-01-01T00:00:00Z",
                "created_by": "codex",
                "project_context": {},
            },
            "features": [
                {
                    "id": "F001",
                    "name": "Test Feature",
                    "description": "A test feature",
                    "priority": "medium",
                    "complexity": "S",
                    "status": "pending",
                    "dependencies": [],
                    "goals": {
                        "primary": "Test goal",
                        "secondary": [],
                        "measurable_outcomes": ["Test passes"],
                    },
                    "tasks": [
                        {"id": "T001", "description": "Do task", "status": "pending"}
                    ],
                    "acceptance_criteria": [
                        {
                            "id": "AC001",
                            "criterion": "Works",
                            "verification_method": "manual_test",
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
        mock_codex.return_value = (json.dumps(mock_tracker), "")

        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            prd_path = repo_root / "test.md"
            prd_path.write_text("# Test PRD\n\nImplement a test feature.")

            tracker = generate_tracker(
                prd_path=prd_path,
                repo_root=repo_root,
                executor="codex",
                force=True,
                dry_run=False,
                allow_unsafe_execution=True,
            )

            # Verify created_by is set correctly
            self.assertEqual(tracker["metadata"]["created_by"], "codex")

            # Verify tracker is valid
            is_valid, errors = validate_tracker(tracker)
            self.assertTrue(is_valid, f"Tracker validation failed: {errors}")


if __name__ == "__main__":
    unittest.main()
