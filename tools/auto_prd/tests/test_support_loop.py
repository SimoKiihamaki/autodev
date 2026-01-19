"""Tests for support_loop module.

The run_support_mode function is a continuous polling loop that interacts with:
- Git operations (current SHA, branch, status, log)
- Tracker state (loading, validation, aggregation)
- VerificationPersistence (checking for stale runs)
- Guardrails (loading signs)

Testing this function comprehensively requires mocking:
1. All git operations via run_cmd
2. Tracker loading and validation
3. Verification persistence checks
4. Time.sleep for the polling interval
5. KeyboardInterrupt to exit the infinite loop

The minimal test below verifies the module can be imported and
key helper functions work correctly. Full integration testing
would require significant mocking infrastructure.
"""

from __future__ import annotations

from pathlib import Path

from auto_prd.support_loop import (
    MAX_ITEMS,
    STATE_FILENAME,
    _collect_tracker_text,
    _extract_prd_checkboxes,
    _limit,
    _normalize_text,
    load_support_state,
    save_support_state,
)


class TestNormalizeText:
    """Tests for _normalize_text helper."""

    def test_lowercases_text(self) -> None:
        assert _normalize_text("Hello World") == "hello world"

    def test_removes_special_chars(self) -> None:
        assert _normalize_text("Hello@World#Test") == "hello world test"

    def test_collapses_whitespace(self) -> None:
        assert _normalize_text("hello   world") == "hello world"

    def test_trims_whitespace(self) -> None:
        assert _normalize_text("  hello world  ") == "hello world"


class TestExtractPrdCheckboxes:
    """Tests for _extract_prd_checkboxes helper."""

    def test_extracts_checked_items(self) -> None:
        prd = "- [x] Item one\n- [X] Item two\n- [ ] Item three"
        result = _extract_prd_checkboxes(prd)
        assert result == ["Item one", "Item two", "Item three"]

    def test_extracts_unchecked_items(self) -> None:
        prd = "- [ ] Item one\n  - [ ] Item two"
        result = _extract_prd_checkboxes(prd)
        assert result == ["Item one", "Item two"]

    def test_handles_empty_lines(self) -> None:
        prd = "- [x] Item one\n\n- [ ] Item two"
        result = _extract_prd_checkboxes(prd)
        assert result == ["Item one", "Item two"]

    def test_ignores_non_checkbox_lines(self) -> None:
        prd = "# Header\n- [x] Item one\nSome text"
        result = _extract_prd_checkboxes(prd)
        assert result == ["Item one"]

    def test_handles_checkboxes_without_space_after_bracket(self) -> None:
        r"""Test that checkboxes without a space after the closing bracket are extracted.

        This covers the edge case where markdown uses `- [x]item` instead of `- [x] item`.
        The regex pattern uses `\s*` after the closing bracket to make the space optional.
        """
        # Table-driven test cases: (input, expected_output)
        test_cases = [
            # Standard format with space (original behavior)
            ("- [ ] item one", ["item one"]),
            ("- [x] item two", ["item two"]),
            ("- [X] item three", ["item three"]),
            # Edge case: no space after bracket (newly supported)
            ("- [ ]item four", ["item four"]),
            ("- [x]item five", ["item five"]),
            ("- [X]item six", ["item six"]),
            # Mixed content with both formats
            ("- [ ] spaced item\n- [x]unspaced item", ["spaced item", "unspaced item"]),
            # Asterisk bullet with both formats
            (
                "* [ ] spaced asterisk\n* [x]unspaced asterisk",
                ["spaced asterisk", "unspaced asterisk"],
            ),
        ]

        for prd_input, expected in test_cases:
            result = _extract_prd_checkboxes(prd_input)
            assert result == expected, (
                f"Failed for input: {prd_input!r}. Expected {expected}, got {result}"
            )


class TestLimit:
    """Tests for _limit helper."""

    def test_returns_all_when_under_limit(self) -> None:
        items = ["a", "b", "c"]
        result, extra = _limit(items, max_items=5)
        assert result == ["a", "b", "c"]
        assert extra == 0

    def test_limits_when_over(self) -> None:
        items = ["a", "b", "c", "d", "e"]
        result, extra = _limit(items, max_items=3)
        assert result == ["a", "b", "c"]
        assert extra == 2

    def test_returns_empty_list(self) -> None:
        result, extra = _limit([], max_items=3)
        assert result == []
        assert extra == 0


class TestCollectTrackerText:
    """Tests for _collect_tracker_text helper."""

    def test_extracts_feature_name_and_description(self) -> None:
        tracker = {
            "features": [
                {
                    "id": "F001",
                    "name": "Feature One",
                    "description": "A detailed description",
                    "tasks": [],
                }
            ]
        }
        result = _collect_tracker_text(tracker)
        assert "Feature One" in result
        assert "A detailed description" in result

    def test_extracts_task_descriptions(self) -> None:
        tracker = {
            "features": [
                {
                    "id": "F001",
                    "name": "Feature",
                    "description": "Desc",
                    "tasks": [
                        {"id": "T001", "description": "Task one"},
                        {"id": "T002", "description": "Task two"},
                    ],
                }
            ]
        }
        result = _collect_tracker_text(tracker)
        assert "Task one" in result
        assert "Task two" in result

    def test_handles_null_tasks_gracefully(self) -> None:
        """Test that null tasks are handled without crashing."""
        tracker = {
            "features": [
                {
                    "id": "F001",
                    "name": "Feature",
                    "description": "Desc",
                    "tasks": None,  # Malformed entry
                }
            ]
        }
        result = _collect_tracker_text(tracker)
        assert "Feature" in result

    def test_handles_missing_features(self) -> None:
        result = _collect_tracker_text({})
        assert result == []

    def test_ignores_empty_strings(self) -> None:
        tracker = {
            "features": [
                {
                    "id": "F001",
                    "name": "",
                    "description": "   ",
                    "tasks": [],
                }
            ]
        }
        result = _collect_tracker_text(tracker)
        assert result == []

    def test_handles_non_list_features_field(self) -> None:
        """Table-driven test for non-list 'features' field values.

        Covers corrupted tracker data where 'features' is not a list.
        """
        test_cases = [
            # (features_value, expected_result_count, description)
            (None, 0, "null features"),
            (42, 0, "int features"),
            ("corrupted", 0, "string features"),
            ({}, 0, "dict features"),
            ([], 0, "empty list features"),
            (
                [
                    {
                        "id": "F001",
                        "name": "Valid Feature",
                        "description": "Valid description",
                        "tasks": [],
                    }
                ],
                2,
                "valid list with one feature",
            ),
        ]

        for features_val, expected_count, desc in test_cases:
            tracker = {"features": features_val}
            result = _collect_tracker_text(tracker)
            assert len(result) == expected_count, (
                f"Failed for {desc}: expected {expected_count} items, got {len(result)}"
            )

    def test_handles_non_list_tasks_field(self) -> None:
        """Table-driven test for non-list 'tasks' field values within features.

        Covers corrupted tracker data where a feature's 'tasks' is not a list.
        """
        test_cases = [
            # (tasks_value, expected_result_count, description)
            # Feature name + description = 2 items when tasks is malformed/empty
            (None, 2, "null tasks"),
            (99, 2, "int tasks"),
            ("broken", 2, "string tasks"),
            ({}, 2, "dict tasks"),
            ([], 2, "empty list tasks"),
            (
                [{"id": "T001", "description": "Valid task"}],
                3,
                "valid list with one task (name + desc + task)",
            ),
        ]

        for tasks_val, expected_count, desc in test_cases:
            tracker = {
                "features": [
                    {
                        "id": "F001",
                        "name": "Feature Name",
                        "description": "Feature description",
                        "tasks": tasks_val,
                    }
                ]
            }
            result = _collect_tracker_text(tracker)
            assert len(result) == expected_count, (
                f"Failed for {desc}: expected {expected_count} items, got {len(result)}"
            )


class TestSupportStatePersistence:
    """Tests for support state persistence."""

    def test_load_state_returns_default_when_missing(self, tmp_path: Path) -> None:
        """Default state should be returned when no state file exists."""
        # Use a non-existent path
        state = load_support_state(tmp_path)
        assert state.iteration == 1
        assert state.last_reviewed_sha == ""
        assert state.last_reviewed_prd_hash == ""

    def test_save_and_load_state(self, tmp_path: Path) -> None:
        """State should persist across save/load cycles."""
        from auto_prd.support_loop import SupportState

        original = SupportState(
            iteration=5,
            last_reviewed_sha="abc123",
            last_reviewed_prd_hash="hash456",
            last_reviewed_at="2024-01-01T00:00:00Z",
        )
        save_support_state(tmp_path, original)

        loaded = load_support_state(tmp_path)
        assert loaded.iteration == 5
        assert loaded.last_reviewed_sha == "abc123"
        assert loaded.last_reviewed_prd_hash == "hash456"
        assert loaded.last_reviewed_at == "2024-01-01T00:00:00Z"


class TestRunSupportModeCoverage:
    """
    Coverage notes for run_support_mode.

    The run_support_mode function is an infinite loop with the following
    code paths that require testing:

    1. State persistence: loading/saving iteration counter and reviewed SHA
       - Covered by TestSupportStatePersistence

    2. Git operations: current SHA, branch, status, recent commits
       - Requires mocking run_cmd for git commands

    3. Tracker validation short-circuit: when validation fails, don't
       aggregate task counts to avoid TypeError from malformed data
       - Requires mocking load_tracker and validate_tracker

    4. PRD checkbox comparison: matching PRD items against tracker tasks
       - Covered indirectly by TestCollectTrackerText with
         _normalize_text integration

    5. VerificationPersistence: checking for stale runs
       - Requires mocking VerificationPersistence

    6. Guardrails loading: counting signs on record
       - Requires mocking load_guardrails

    7. KeyboardInterrupt handling: clean exit on Ctrl+C
       - Requires simulating keyboard interrupt in loop

    8. Exception handling: continue polling after crash
       - Requires triggering exception in loop body

    Full coverage would require significant refactoring to make the
    loop testable, or extensive use of unittest.mock.patch.
    """

    def test_module_constants_defined(self) -> None:
        """Verify module constants are properly defined."""
        assert STATE_FILENAME == "support_state.json"
        assert isinstance(MAX_ITEMS, int)
        assert MAX_ITEMS > 0
