"""
Versioned acceptance criteria with delta-only edits and changelog.

Implements version control for acceptance criteria to enable:
- Delta-only edits (add, modify, remove)
- Rollback support with soft deletes
- Evidence staleness detection on version mismatch
- Full audit trail via changelog
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, List


@dataclass
class CriteriaChange:
    """Represents a change to acceptance criteria."""

    type: str
    feature_id: str
    description: str
    criterion_id: Optional[str] = None
    criterion_type: Optional[str] = None
    reason: str = ""
    new_status: Optional[str] = None


@dataclass
class ChangelogEntry:
    """Single entry in criteria changelog."""

    version: int
    timestamp: str
    reason: str
    changes: List[dict[str, Any]] = field(default_factory=list)
    invalidated_tasks: List[str] = field(default_factory=list)


class VersionedCriteriaManager:
    """
    Manages versioned acceptance criteria with delta edits and changelog.

    Features:
    - Delta-only edits: Prefer additions over rewrites
    - Version bumping: Bump version on modifications
    - Soft deletes: Mark removed criteria as deprecated, don't remove
    - Evidence staleness: Mark evidence stale on version mismatch
    - Changelog audit: Track all changes with timestamps
    """

    def __init__(self, tracker_path: Path):
        self.tracker_path = Path(tracker_path)
        self.tracker: dict[str, Any] = self._load_tracker()
        self._next_id: int = self._find_next_criterion_id()

    def _load_tracker(self) -> dict[str, Any]:
        """Load tracker from file."""
        if self.tracker_path.exists():
            with open(self.tracker_path, "r") as f:
                return json.load(f)
        return {
            "features": [],
            "criteria_changelog": [],
        }

    def _save_tracker(self) -> None:
        """Save tracker to file."""
        with open(self.tracker_path, "w") as f:
            json.dump(self.tracker, f, indent=2)

    def _find_next_criterion_id(self) -> int:
        """Find next available criterion ID."""
        max_id = 0
        for feature in self.tracker.get("features", []):
            for criterion in feature.get("acceptance_criteria", []):
                criterion_id_str = criterion.get("id", "")
                if criterion_id_str.startswith("AC"):
                    try:
                        num = int(criterion_id_str[2:])
                        if num > max_id:
                            max_id = num
                    except ValueError:
                        pass
        return max_id + 1

    def get_feature(self, feature_id: str) -> Optional[dict[str, Any]]:
        """Get feature by ID."""
        for feature in self.tracker.get("features", []):
            if feature.get("id") == feature_id:
                return feature
        return None

    def find_criterion(
        self, feature: dict[str, Any], criterion_id: str
    ) -> Optional[dict[str, Any]]:
        """Find criterion by ID within feature."""
        if not feature:
            return None
        for criterion in feature.get("acceptance_criteria", []):
            if criterion.get("id") == criterion_id:
                return criterion
        return None

    def mark_tasks_needing_reverify(
        self, feature: dict[str, Any], new_version: int
    ) -> None:
        """Mark all tasks in feature as needing reverification."""
        for task in feature.get("tasks", []):
            task["needs_reverify"] = True
            task["criteria_version"] = new_version

    def get_invalidated_tasks(
        self, feature: dict[str, Any], new_version: int
    ) -> List[str]:
        """Get list of task IDs invalidated by criteria change."""
        invalidated = []
        for task in feature.get("tasks", []):
            task_version = task.get("criteria_version", 0)
            if task_version < new_version:
                invalidated.append(task.get("id", ""))
        return invalidated

    def update_acceptance_criteria(
        self, feature_id: str, changes: List[CriteriaChange]
    ) -> None:
        """
        Update acceptance criteria with version control and rollback support.

        Rules:
        1. Prefer delta additions over rewrites
        2. If changing existing criterion, bump version
        3. Mark impacted tasks as needs_reverify
        4. Prior evidence marked stale on version mismatch
        5. Record changelog entry

        Args:
            feature_id: Feature to update
            changes: List of criteria changes to apply
        """
        feature = self.get_feature(feature_id)
        if not feature:
            raise ValueError(f"Feature {feature_id} not found")

        current_version = feature.get("criteria_version", 0)
        new_version = current_version + 1
        feature["criteria_version"] = new_version
        feature["needs_reverify"] = len(changes) > 0

        for change in changes:
            if change.type == "add":
                self._add_criterion(feature, change, new_version)

            elif change.type == "modify":
                self._modify_criterion(feature, change, new_version)

            elif change.type == "remove":
                self._remove_criterion(feature, change, new_version)

        # Mark impacted tasks
        if changes:
            invalidated = self.get_invalidated_tasks(feature, new_version)
            self.mark_tasks_needing_reverify(feature, new_version)

            # Record changelog entry
            changelog_entry = ChangelogEntry(
                version=new_version,
                timestamp=datetime.now().isoformat(),
                reason=changes[0].reason if changes else "",
                changes=[{"type": c.type, **c.__dict__} for c in changes],
                invalidated_tasks=invalidated,
            )
            self.tracker.setdefault("criteria_changelog", []).append(
                changelog_entry.__dict__
            )

        self._save_tracker()

    def _add_criterion(
        self, feature: dict[str, Any], change: CriteriaChange, version: int
    ) -> None:
        """Add new criterion to feature."""
        new_id = f"AC{self._next_id}"
        self._next_id += 1
        # Update change object so changelog captures the actual ID
        change.criterion_id = new_id

        new_criterion = {
            "id": new_id,
            "type": change.criterion_type or "unit_test",
            "description": change.description,
            "status": "pending",
            "version": version,
            "last_updated": datetime.now().isoformat(),
            "added_in_version": version,
        }

        feature.setdefault("acceptance_criteria", []).append(new_criterion)

    def _modify_criterion(
        self, feature: dict[str, Any], change: CriteriaChange, version: int
    ) -> None:
        """Modify existing criterion with version bump."""
        existing = self.find_criterion(feature, change.criterion_id or "")
        if not existing:
            raise ValueError(
                f"Criterion {change.criterion_id} not found for modification"
            )

        existing["version"] = version
        existing["last_updated"] = datetime.now().isoformat()
        existing["status"] = change.new_status or "pending"

        if change.description:
            existing["description"] = change.description
        if change.criterion_type:
            existing["type"] = change.criterion_type

    def _remove_criterion(
        self, feature: dict[str, Any], change: CriteriaChange, version: int
    ) -> None:
        """Soft delete criterion (mark as deprecated)."""
        existing = self.find_criterion(feature, change.criterion_id or "")
        if not existing:
            raise ValueError(f"Criterion {change.criterion_id} not found for removal")

        existing["status"] = "deprecated"
        existing["version"] = version
        existing["last_updated"] = datetime.now().isoformat()
        existing["removed_in_version"] = version
        existing["removal_reason"] = change.description

    def bump_criteria_version(self, feature_id: str) -> int:
        """Bump criteria version without making changes."""
        feature = self.get_feature(feature_id)
        if not feature:
            raise ValueError(f"Feature {feature_id} not found")

        current_version = feature.get("criteria_version", 0)
        new_version = current_version + 1
        feature["criteria_version"] = new_version
        feature["needs_reverify"] = True

        self._save_tracker()
        return new_version

    def is_criteria_fresh(
        self, feature_id: str, task_version: Optional[int] = None
    ) -> bool:
        """
        Check if acceptance criteria is fresh relative to task.

        Criteria is stale if:
        1. Task has criteria_version set and it's < feature.criteria_version
        2. Criteria has been modified since task was last updated

        Args:
            feature_id: Feature to check
            task_version: Optional task's criteria_version to compare

        Returns:
            True if criteria is fresh, False if stale
        """
        feature = self.get_feature(feature_id)
        if not feature:
            return True

        feature_version = feature.get("criteria_version", 0)

        # If no task version, assume fresh
        if task_version is None:
            return True

        # Stale if task version < feature version
        return task_version >= feature_version

    def get_criteria_history(self, feature_id: str) -> List[dict[str, Any]]:
        """Get changelog history for a feature's criteria."""
        history = []
        for entry in self.tracker.get("criteria_changelog", []):
            for change in entry.get("changes", []):
                if change.get("feature_id") == feature_id:
                    history.append(
                        {
                            "version": entry.get("version"),
                            "timestamp": entry.get("timestamp"),
                            "reason": entry.get("reason"),
                            "change": change,
                        }
                    )
        return history

    def rollback_to_version(
        self, feature_id: str, target_version: int
    ) -> dict[str, Any]:
        """
        Rollback acceptance criteria to a specific version.

        Args:
            feature_id: Feature to rollback
            target_version: Version to restore

        Returns:
            Rollback summary with changes reverted
        """
        feature = self.get_feature(feature_id)
        if not feature:
            raise ValueError(f"Feature {feature_id} not found")

        current_version = feature.get("criteria_version", 0)

        if target_version > current_version:
            raise ValueError(
                f"Cannot rollback to version {target_version} from {current_version}"
            )

        # Find changelog entries to revert
        reverted = []
        for entry in reversed(self.tracker.get("criteria_changelog", [])):
            if entry.get("version") > target_version:
                for change in entry.get("changes", []):
                    if change.get("feature_id") == feature_id:
                        self._revert_change(feature, change)
                        reverted.append(change)

        feature["criteria_version"] = target_version
        feature["needs_reverify"] = True

        self._save_tracker()

        return {
            "feature_id": feature_id,
            "from_version": current_version,
            "to_version": target_version,
            "changes_reverted": len(reverted),
            "reverted_changes": reverted,
        }

    def _revert_change(self, feature: dict[str, Any], change: dict[str, Any]) -> None:
        """Revert a single change."""
        change_type = change.get("type")

        if change_type == "add":
            criterion_id = change.get("criterion_id")
            feature["acceptance_criteria"] = [
                c
                for c in feature.get("acceptance_criteria", [])
                if c.get("id") != criterion_id
            ]

        elif change_type == "modify":
            criterion_id = change.get("criterion_id")
            criterion = self.find_criterion(feature, criterion_id)
            if criterion:
                criterion["status"] = "pending"
                # Note: In a real system, we'd need version history
                # This is simplified for demo

        elif change_type == "remove":
            criterion_id = change.get("criterion_id")
            criterion = self.find_criterion(feature, criterion_id)
            if criterion:
                criterion["status"] = "pending"
                del criterion["removed_in_version"]
                del criterion["removal_reason"]
