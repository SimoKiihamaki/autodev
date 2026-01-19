"""Tests for versioned acceptance criteria module."""

import tempfile
from pathlib import Path

from auto_prd.versioned_criteria import (
    CriteriaChange,
    VersionedCriteriaManager,
)


def test_create_manager_with_empty_tracker():
    """Test manager creation with non-existent tracker."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tracker_path = Path(tmpdir) / "tracker.json"
        manager = VersionedCriteriaManager(tracker_path)

        assert manager.tracker == {"features": [], "criteria_changelog": []}
        assert manager._next_id == 1


def test_add_criterion():
    """Test adding new criterion."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tracker_path = Path(tmpdir) / "tracker.json"
        manager = VersionedCriteriaManager(tracker_path)

        # Add feature first
        manager.tracker["features"].append(
            {"id": "F001", "status": "in_progress", "acceptance_criteria": []}
        )

        # Add criterion
        changes = [
            CriteriaChange(
                type="add",
                feature_id="F001",
                criterion_type="unit_test",
                description="User can create account with valid email/password",
            )
        ]

        manager.update_acceptance_criteria("F001", changes)

        # Verify
        feature = manager.get_feature("F001")
        assert feature is not None
        assert feature["criteria_version"] == 1
        assert len(feature["acceptance_criteria"]) == 1
        assert feature["needs_reverify"] is True

        criterion = feature["acceptance_criteria"][0]
        assert criterion["id"] == "AC1"
        assert criterion["version"] == 1


def test_modify_criterion():
    """Test modifying existing criterion."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tracker_path = Path(tmpdir) / "tracker.json"
        manager = VersionedCriteriaManager(tracker_path)

        # Add feature with initial criterion
        manager.tracker["features"].append(
            {
                "id": "F001",
                "status": "in_progress",
                "acceptance_criteria": [
                    {
                        "id": "AC1",
                        "type": "unit_test",
                        "description": "Initial description",
                        "status": "pending",
                        "version": 1,
                    }
                ],
                "criteria_version": 1,
            }
        )

        # Modify criterion
        changes = [
            CriteriaChange(
                type="modify",
                feature_id="F001",
                criterion_id="AC1",
                description="Updated: User can create account with email validation",
                new_status="pending",
            )
        ]

        manager.update_acceptance_criteria("F001", changes)

        # Verify
        feature = manager.get_feature("F001")
        assert feature["criteria_version"] == 2

        criterion = manager.find_criterion("F001", "AC1")
        assert criterion is not None
        assert criterion["version"] == 2
        assert criterion["status"] == "pending"


def test_remove_criterion():
    """Test removing criterion (soft delete)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tracker_path = Path(tmpdir) / "tracker.json"
        manager = VersionedCriteriaManager(tracker_path)

        # Add feature with criteria
        manager.tracker["features"].append(
            {
                "id": "F001",
                "status": "in_progress",
                "acceptance_criteria": [
                    {
                        "id": "AC1",
                        "type": "unit_test",
                        "description": "To be removed",
                        "status": "pending",
                        "version": 1,
                    }
                ],
                "criteria_version": 1,
            }
        )

        # Remove criterion
        changes = [
            CriteriaChange(
                type="remove",
                feature_id="F001",
                criterion_id="AC1",
                description="No longer needed",
            )
        ]

        manager.update_acceptance_criteria("F001", changes)

        # Verify soft delete (deprecated, not removed)
        feature = manager.get_feature("F001")
        assert feature["criteria_version"] == 2

        criterion = manager.find_criterion("F001", "AC1")
        assert criterion is not None
        assert criterion["status"] == "deprecated"
        assert "removed_in_version" in criterion
        assert criterion["removal_reason"] == "No longer needed"


def test_changelog_tracking():
    """Test changelog entries."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tracker_path = Path(tmpdir) / "tracker.json"
        manager = VersionedCriteriaManager(tracker_path)

        # Add feature
        manager.tracker["features"].append(
            {"id": "F001", "status": "in_progress", "acceptance_criteria": []}
        )

        # Add criterion
        changes = [
            CriteriaChange(
                type="add",
                feature_id="F001",
                criterion_type="unit_test",
                description="Test criterion",
            )
        ]

        manager.update_acceptance_criteria("F001", changes)

        # Verify changelog
        assert len(manager.tracker["criteria_changelog"]) == 1
        entry = manager.tracker["criteria_changelog"][0]
        assert entry["version"] == 1
        assert entry["reason"] == ""
        assert len(entry["changes"]) == 1
        assert entry["changes"][0]["type"] == "add"


def test_task_invalidation():
    """Test that tasks are marked needs_reverify on criteria changes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tracker_path = Path(tmpdir) / "tracker.json"
        manager = VersionedCriteriaManager(tracker_path)

        # Add feature with tasks
        manager.tracker["features"].append(
            {
                "id": "F001",
                "status": "in_progress",
                "acceptance_criteria": [],
                "tasks": [
                    {"id": "T001", "status": "pending", "criteria_version": 0},
                    {"id": "T002", "status": "pending", "criteria_version": 0},
                ],
            }
        )

        # Update criteria version
        manager.bump_criteria_version("F001")

        # Verify tasks marked needs_reverify
        feature = manager.get_feature("F001")
        assert all(t.get("needs_reverify") for t in feature.get("tasks", []))


def test_criteria_freshness():
    """Test criteria freshness detection."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tracker_path = Path(tmpdir) / "tracker.json"
        manager = VersionedCriteriaManager(tracker_path)

        # Add feature with criteria
        manager.tracker["features"].append(
            {
                "id": "F001",
                "status": "in_progress",
                "acceptance_criteria": [],
                "tasks": [
                    {"id": "T001", "status": "pending", "criteria_version": 1},
                ],
                "criteria_version": 2,
            }
        )

        # Test stale detection (task version < feature version)
        is_fresh = manager.is_criteria_fresh("F001", task_version=1)
        assert is_fresh is False

        # Test fresh (no task version)
        is_fresh = manager.is_criteria_fresh("F001", task_version=None)
        assert is_fresh is True


def test_criteria_history():
    """Test retrieving changelog history."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tracker_path = Path(tmpdir) / "tracker.json"
        manager = VersionedCriteriaManager(tracker_path)

        # Add feature and update twice
        manager.tracker["features"].append(
            {"id": "F001", "status": "in_progress", "acceptance_criteria": []}
        )

        changes1 = [
            CriteriaChange(
                type="add",
                feature_id="F001",
                criterion_type="unit_test",
                description="First criterion",
            )
        ]

        manager.update_acceptance_criteria("F001", changes1)

        changes2 = [
            CriteriaChange(
                type="modify",
                feature_id="F001",
                criterion_id="AC1",
                description="Updated criterion",
                new_status="pending",
            )
        ]

        manager.update_acceptance_criteria("F001", changes2)

        # Get history
        history = manager.get_criteria_history("F001")
        assert len(history) == 2
        assert history[0]["version"] == 1
        assert history[1]["version"] == 2
        assert history[0]["change"]["type"] == "add"
        assert history[1]["change"]["type"] == "modify"
