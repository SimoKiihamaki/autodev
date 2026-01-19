"""Tests for task completion detection module."""


from tools.auto_prd.task_completion_detector import (
    MAX_REASONABLE_TASK_DECREASE,
    MIN_COMPLETION_CONFIDENCE,
    detect_completed_task_from_changes,
    validate_tasks_left_progression,
)


class TestDetectCompletedTaskFromChanges:
    """Tests for detect_completed_task_from_changes function."""

    def test_no_changes_no_completion(self) -> None:
        """Test that no git changes results in low confidence and no completion."""
        tracker = {
            "features": [
                {
                    "id": "F001",
                    "tasks": [{"id": "T001", "status": "pending"}],
                }
            ]
        }

        result = detect_completed_task_from_changes(
            tracker=tracker,
            repo_root=None,  # type: ignore[arg-type]
            assigned_task_id="T001",
            assigned_feature_id="F001",
            before_status=(),
            after_status=(),
            before_head="abc123",
            after_head="abc123",
        )

        assert result["completed"] is False
        assert result["confidence"] < MIN_COMPLETION_CONFIDENCE
        assert result["actual_task_id"] is None

    def test_git_changes_increases_confidence(self) -> None:
        """Test that git changes increase confidence."""
        tracker = {"features": []}

        result = detect_completed_task_from_changes(
            tracker=tracker,
            repo_root=None,  # type: ignore[arg-type]
            assigned_task_id="T001",
            assigned_feature_id="F001",
            before_status=(),
            after_status=("M  file.txt",),
            before_head="abc123",
            after_head="def456",
        )

        assert result["confidence"] >= 0.3  # Git changes detected
        assert "Git changes detected" in result["evidence"]

    def test_tracker_marked_completed_increases_confidence(self) -> None:
        """Test that tracker already marked completed increases confidence."""
        tracker = {
            "features": [
                {
                    "id": "F001",
                    "tasks": [{"id": "T001", "status": "completed"}],
                }
            ]
        }

        result = detect_completed_task_from_changes(
            tracker=tracker,
            repo_root=None,  # type: ignore[arg-type]
            assigned_task_id="T001",
            assigned_feature_id="F001",
            before_status=(),
            after_status=(),
            before_head="abc123",
            after_head="abc123",
        )

        assert result["confidence"] >= 0.5  # Tracker marked completed
        assert result["completed"] is True
        assert "T001" in result["evidence"][0]

    def test_relevant_file_changes_increases_confidence(self) -> None:
        """Test that changes to task-relevant files increase confidence."""
        tracker = {
            "features": [
                {
                    "id": "F001",
                    "files": {
                        "to_create": ["new_file.py"],
                        "to_modify": ["existing.py"],
                    },
                }
            ]
        }

        result = detect_completed_task_from_changes(
            tracker=tracker,
            repo_root=None,  # type: ignore[arg-type]
            assigned_task_id="T001",
            assigned_feature_id="F001",
            before_status=(),
            after_status=("M  existing.py",),
            before_head="abc123",
            after_head="def456",
        )

        assert result["confidence"] >= 0.5  # Git changes + relevant files
        assert result["completed"] is True


class TestValidateTasksLeftProgression:
    """Tests for validate_tasks_left_progression function."""

    def test_no_previous_value_is_valid(self) -> None:
        """Test that missing previous value is valid."""
        is_valid, error = validate_tasks_left_progression(
            previous_tasks_left=None,
            current_tasks_left=10,
            iteration=1,
        )

        assert is_valid is True
        assert error == ""

    def test_no_current_value_is_valid(self) -> None:
        """Test that missing current value is valid."""
        is_valid, error = validate_tasks_left_progression(
            previous_tasks_left=10,
            current_tasks_left=None,
            iteration=2,
        )

        assert is_valid is True
        assert error == ""

    def test_tasks_left_should_not_increase(self) -> None:
        """Test that TASKS_LEFT increasing is invalid."""
        is_valid, error = validate_tasks_left_progression(
            previous_tasks_left=5,
            current_tasks_left=10,
            iteration=2,
        )

        assert is_valid is False
        assert "increased from 5 to 10" in error

    def test_tasks_left_should_not_decrease_too_much(self) -> None:
        """Test that large TASKS_LEFT decreases are invalid."""
        is_valid, error = validate_tasks_left_progression(
            previous_tasks_left=50,
            current_tasks_left=5,
            iteration=2,
        )

        assert is_valid is False
        assert "decreased by 45" in error
        assert "Large decreases" in error

    def test_exactly_at_threshold_is_valid(self) -> None:
        """Test that decrease exactly at threshold is valid."""
        is_valid, error = validate_tasks_left_progression(
            previous_tasks_left=20,
            current_tasks_left=10,
            iteration=2,
        )

        assert is_valid is True
        assert error == ""

    def test_one_over_threshold_is_invalid(self) -> None:
        """Test that decrease over threshold is invalid."""
        is_valid, error = validate_tasks_left_progression(
            previous_tasks_left=20,
            current_tasks_left=9,
            iteration=2,
        )

        assert is_valid is False
        assert "decreased by 11" in error

    def test_negative_tasks_left_is_invalid(self) -> None:
        """Test that negative TASKS_LEFT is invalid."""
        is_valid, error = validate_tasks_left_progression(
            previous_tasks_left=5,
            current_tasks_left=-1,
            iteration=2,
        )

        assert is_valid is False
        assert "negative" in error

    def test_normal_decrease_is_valid(self) -> None:
        """Test that normal decrease is valid."""
        is_valid, error = validate_tasks_left_progression(
            previous_tasks_left=10,
            current_tasks_left=8,
            iteration=2,
        )

        assert is_valid is True
        assert error == ""

    def test_no_change_is_valid(self) -> None:
        """Test that no change is valid."""
        is_valid, error = validate_tasks_left_progression(
            previous_tasks_left=10,
            current_tasks_left=10,
            iteration=2,
        )

        assert is_valid is True
        assert error == ""


class TestModuleConstants:
    """Tests for module-level constants."""

    def test_min_completion_confidence_is_defined(self) -> None:
        """Test that MIN_COMPLETION_CONFIDENCE is defined correctly."""
        assert MIN_COMPLETION_CONFIDENCE == 0.5

    def test_max_reasonable_task_decrease_is_defined(self) -> None:
        """Test that MAX_REASONABLE_TASK_DECREASE is defined correctly."""
        assert MAX_REASONABLE_TASK_DECREASE == 10
