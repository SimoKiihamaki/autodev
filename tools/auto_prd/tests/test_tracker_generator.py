"""Tests for the tracker_generator module.

This module tests the PRD analysis and tracker generation functionality.
"""

import tempfile
import unittest
from pathlib import Path

from auto_prd.tracker_generator import (
    TRACKER_VERSION,
    compute_prd_hash,
    get_next_feature,
    get_tracker_path,
    load_tracker,
    save_tracker,
    update_feature_status,
    validate_tracker,
)


class ComputePrdHashTests(unittest.TestCase):
    """Tests for compute_prd_hash function."""

    def test_returns_sha256_prefixed_hash(self) -> None:
        """Hash should be prefixed with 'sha256:'."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Test PRD\n\nSome content here.")
            f.flush()
            temp_path = Path(f.name)

        try:
            result = compute_prd_hash(temp_path)
            self.assertTrue(result.startswith("sha256:"))
            # Hash should be 16 chars after prefix
            hash_value = result.split(":")[1]
            self.assertEqual(len(hash_value), 16)
        finally:
            temp_path.unlink()

    def test_same_content_produces_same_hash(self) -> None:
        """Identical content should produce identical hash."""
        content = "# Test PRD\n\nIdentical content"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f1:
            f1.write(content)
            f1.flush()
            path1 = Path(f1.name)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f2:
            f2.write(content)
            f2.flush()
            path2 = Path(f2.name)

        try:
            hash1 = compute_prd_hash(path1)
            hash2 = compute_prd_hash(path2)
            self.assertEqual(hash1, hash2)
        finally:
            path1.unlink()
            path2.unlink()

    def test_different_content_produces_different_hash(self) -> None:
        """Different content should produce different hash."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f1:
            f1.write("Content A")
            f1.flush()
            path1 = Path(f1.name)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f2:
            f2.write("Content B")
            f2.flush()
            path2 = Path(f2.name)

        try:
            hash1 = compute_prd_hash(path1)
            hash2 = compute_prd_hash(path2)
            self.assertNotEqual(hash1, hash2)
        finally:
            path1.unlink()
            path2.unlink()

    def test_nonexistent_file_raises_error(self) -> None:
        """Nonexistent file should raise FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            compute_prd_hash(Path("/nonexistent/path/file.md"))


class GetTrackerPathTests(unittest.TestCase):
    """Tests for get_tracker_path function."""

    def test_returns_path_in_aprd_directory(self) -> None:
        """Tracker path should be in .aprd directory."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = get_tracker_path(Path(tmp_dir))
            self.assertTrue(str(result).endswith(".aprd/tracker.json"))
            self.assertTrue(str(result).startswith(tmp_dir))


class LoadSaveTrackerTests(unittest.TestCase):
    """Tests for load_tracker and save_tracker functions."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.repo_root = Path(self.temp_dir)
        self.aprd_dir = self.repo_root / ".aprd"
        self.aprd_dir.mkdir()

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir)

    def test_save_and_load_roundtrip(self) -> None:
        """Saved tracker should be loadable."""
        tracker = {
            "version": TRACKER_VERSION,
            "metadata": {
                "prd_source": "test.md",
                "prd_hash": "sha256:abc123",
                "created_at": "2024-01-01T00:00:00Z",
                "created_by": "test",
                "project_context": {},
            },
            "features": [],
            "validation_summary": {
                "total_features": 0,
                "total_tasks": 0,
                "estimated_complexity": "small",
            },
        }

        save_tracker(tracker, self.repo_root)

        loaded = load_tracker(self.repo_root)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["version"], TRACKER_VERSION)
        self.assertEqual(loaded["metadata"]["prd_source"], "test.md")

    def test_load_returns_none_when_missing(self) -> None:
        """Loading nonexistent tracker should return None."""
        result = load_tracker(self.repo_root)
        self.assertIsNone(result)


class GetNextFeatureTests(unittest.TestCase):
    """Tests for get_next_feature function."""

    def test_returns_highest_priority_pending_feature(self) -> None:
        """Should return the highest priority pending feature."""
        tracker = {
            "features": [
                {"id": "F001", "name": "Low", "priority": "low", "status": "pending"},
                {
                    "id": "F002",
                    "name": "Critical",
                    "priority": "critical",
                    "status": "pending",
                },
                {"id": "F003", "name": "High", "priority": "high", "status": "pending"},
            ]
        }

        result = get_next_feature(tracker)
        self.assertEqual(result["id"], "F002")

    def test_skips_completed_features(self) -> None:
        """Should skip completed features."""
        tracker = {
            "features": [
                {
                    "id": "F001",
                    "name": "Done",
                    "priority": "critical",
                    "status": "completed",
                },
                {"id": "F002", "name": "Next", "priority": "high", "status": "pending"},
            ]
        }

        result = get_next_feature(tracker)
        self.assertEqual(result["id"], "F002")

    def test_returns_none_when_all_completed(self) -> None:
        """Should return None when all features are completed."""
        tracker = {
            "features": [
                {
                    "id": "F001",
                    "name": "Done1",
                    "priority": "high",
                    "status": "completed",
                },
                {
                    "id": "F002",
                    "name": "Done2",
                    "priority": "high",
                    "status": "verified",
                },
            ]
        }

        result = get_next_feature(tracker)
        self.assertIsNone(result)

    def test_respects_dependencies(self) -> None:
        """Should not return feature with unmet dependencies."""
        tracker = {
            "features": [
                {
                    "id": "F001",
                    "name": "Base",
                    "priority": "low",
                    "status": "pending",
                    "dependencies": [],
                },
                {
                    "id": "F002",
                    "name": "Dependent",
                    "priority": "critical",
                    "status": "pending",
                    "dependencies": ["F001"],
                },
            ]
        }

        result = get_next_feature(tracker)
        # Should return F001 because F002 depends on it
        self.assertEqual(result["id"], "F001")


class UpdateFeatureStatusTests(unittest.TestCase):
    """Tests for update_feature_status function."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.repo_root = Path(self.temp_dir)
        self.aprd_dir = self.repo_root / ".aprd"
        self.aprd_dir.mkdir()

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir)

    def test_updates_status_successfully(self) -> None:
        """Should update feature status in tracker and save to disk."""
        tracker = {
            "version": TRACKER_VERSION,
            "metadata": {},
            "features": [
                {"id": "F001", "name": "Test", "status": "pending"},
            ],
            "validation_summary": {},
        }

        # Update status (mutates tracker in place and saves)
        update_feature_status(tracker, "F001", "in_progress", self.repo_root)
        self.assertEqual(tracker["features"][0]["status"], "in_progress")

        # Verify saved to disk
        loaded = load_tracker(self.repo_root)
        self.assertEqual(loaded["features"][0]["status"], "in_progress")

    def test_unknown_feature_logs_warning(self) -> None:
        """Should not crash for unknown feature ID."""
        tracker = {
            "version": TRACKER_VERSION,
            "metadata": {},
            "features": [{"id": "F001", "name": "Test", "status": "pending"}],
            "validation_summary": {},
        }

        # Should not raise exception for unknown feature
        update_feature_status(tracker, "F999", "in_progress", self.repo_root)
        # Original tracker unchanged
        self.assertEqual(tracker["features"][0]["status"], "pending")


class ValidateTrackerTests(unittest.TestCase):
    """Tests for validate_tracker function."""

    def test_valid_tracker_passes(self) -> None:
        """Valid tracker should pass validation."""
        tracker = {
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
                    "status": "pending",
                    "goals": {
                        "primary": "Test goal",
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
                        }
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

        is_valid, errors = validate_tracker(tracker)
        self.assertTrue(is_valid, f"Validation errors: {errors}")

    def test_missing_required_field_fails(self) -> None:
        """Tracker missing required field should fail."""
        tracker = {
            "version": TRACKER_VERSION,
            # Missing 'metadata', 'features', 'validation_summary'
        }

        is_valid, errors = validate_tracker(tracker)
        self.assertFalse(is_valid)
        self.assertTrue(len(errors) > 0)

    def test_invalid_feature_id_format_fails(self) -> None:
        """Feature with invalid ID format should fail."""
        tracker = {
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
                    "id": "INVALID",  # Should be F001 format
                    "name": "Test",
                    "description": "Test",
                    "priority": "high",
                    "status": "pending",
                    "goals": {
                        "primary": "Test",
                        "measurable_outcomes": ["Outcome"],
                    },
                    "tasks": [
                        {"id": "T001", "description": "Test", "status": "pending"}
                    ],
                    "acceptance_criteria": [
                        {
                            "id": "AC001",
                            "criterion": "Test",
                            "verification_method": "unit_test",
                        }
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

        is_valid, errors = validate_tracker(tracker)
        self.assertFalse(is_valid)


if __name__ == "__main__":
    unittest.main()
