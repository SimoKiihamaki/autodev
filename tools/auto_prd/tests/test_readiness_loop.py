"""Tests for Ralph Wiggum Loop readiness orchestrator."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _make_mock_history(iterations_data):
    """Create a mock ProgressHistory with specified iterations.

    Args:
        iterations_data: List of (session_id, iteration_num, review_round_dict) tuples

    Returns:
        MagicMock ProgressHistory
    """
    from auto_prd.progress_renderer import IterationSummary

    history = MagicMock()
    iterations = []

    for session_id, iter_num, review_round in iterations_data:
        summary = MagicMock(spec=IterationSummary)
        summary.iteration = iter_num
        summary.review_round = review_round
        iterations.append(summary)

    history.iterations = iterations
    return history


@pytest.fixture
def temp_repo(tmp_path: Path) -> Path:
    """Create a temporary repository structure."""
    aprd_dir = tmp_path / ".aprd"
    aprd_dir.mkdir(parents=True, exist_ok=True)

    # Create .git to make it a valid repo
    (tmp_path / ".git").mkdir(parents=True, exist_ok=True)

    tracker_content = {
        "version": "2.0.0",
        "prd_hash": "test_hash_123",
        "features": [
            {
                "id": "F001",
                "title": "Test Feature",
                "status": "verified",
                "acceptance_criteria": [],
            }
        ],
    }
    (aprd_dir / "tracker.json").write_text(json.dumps(tracker_content, indent=2))

    return tmp_path


def test_readiness_config() -> None:
    """Test ReadinessConfig has sensible defaults."""
    # Import here to avoid issues with circular imports
    from auto_prd.readiness_loop import ReadinessConfig

    config = ReadinessConfig()
    assert config.enabled is True
    assert config.max_iterations == 100
    assert config.scope_review_interval == 5
    assert config.failure_to_sign_threshold == 2
    assert config.base_branch == "main"
    assert config.create_issue_on_stall is False


def test_readiness_orchestrator_init(temp_repo: Path) -> None:
    """Test ReadinessOrchestrator initialization."""
    from auto_prd.readiness_loop import ReadinessConfig, ReadinessOrchestrator

    config = ReadinessConfig(max_iterations=1)
    orchestrator = ReadinessOrchestrator(temp_repo, config)

    assert orchestrator.repo_root == temp_repo
    assert orchestrator.config.max_iterations == 1
    assert orchestrator.state_dir == temp_repo / ".aprd"


def test_readiness_orchestrator_load_tracker(temp_repo: Path) -> None:
    """Test tracker loading functionality."""
    from auto_prd.readiness_loop import ReadinessOrchestrator

    orchestrator = ReadinessOrchestrator(temp_repo)
    tracker = orchestrator._load_tracker()

    assert tracker is not None
    assert tracker["version"] == "2.0.0"
    assert len(tracker["features"]) == 1
    assert tracker["features"][0]["id"] == "F001"


def test_readiness_orchestrator_count_features(temp_repo: Path) -> None:
    """Test feature counting by status."""
    from auto_prd.readiness_loop import ReadinessOrchestrator

    orchestrator = ReadinessOrchestrator(temp_repo)
    tracker = orchestrator._load_tracker()
    counts = orchestrator._count_features(tracker)

    assert counts["verified"] == 1
    assert counts["pending"] == 0
    assert counts["in_progress"] == 0
    assert counts["completed"] == 0


# Table-driven tests for _collect_review_statistics
# Each test case provides a scenario with mocked inputs and expected state changes
COLLECT_REVIEW_STATS_CASES = [
    # Case 1: Empty progress history - no changes to stats
    {
        "name": "empty_progress_history",
        "progress_files": [],
        "history_return": None,  # Will create empty ProgressHistory
        "expected_total": 0,
        "expected_passed": 0,
        "expected_failed": 0,
        "expected_seen": set(),
        "raises": None,
    },
    # Case 2: Single passed review
    {
        "name": "single_passed_review",
        "progress_files": ["session_123.jsonl"],
        "history_return": _make_mock_history(
            [("session_123", 1, {"overall_status": "passed"})]
        ),
        "expected_total": 1,
        "expected_passed": 1,
        "expected_failed": 0,
        "expected_seen": {("session_123", 1, "passed")},
        "raises": None,
    },
    # Case 3: Single failed review
    {
        "name": "single_failed_review",
        "progress_files": ["session_abc.jsonl"],
        "history_return": _make_mock_history(
            [("session_abc", 2, {"overall_status": "failed"})]
        ),
        "expected_total": 1,
        "expected_passed": 0,
        "expected_failed": 1,
        "expected_seen": {("session_abc", 2, "failed")},
        "raises": None,
    },
    # Case 4: Partial review (neither passed nor failed)
    {
        "name": "partial_review",
        "progress_files": ["session_xyz.jsonl"],
        "history_return": _make_mock_history(
            [("session_xyz", 1, {"overall_status": "partial"})]
        ),
        "expected_total": 1,
        "expected_passed": 0,
        "expected_failed": 0,
        "expected_seen": {("session_xyz", 1, "partial")},
        "raises": None,
    },
    # Case 5: Multiple reviews across sessions
    {
        "name": "multiple_reviews_mixed",
        "progress_files": ["s1.jsonl", "s2.jsonl"],
        "history_return": _make_mock_history(
            [
                ("s1", 1, {"overall_status": "passed"}),
                ("s1", 2, {"overall_status": "passed"}),
                ("s2", 1, {"overall_status": "failed"}),
            ]
        ),
        # Note: Since mock returns same history for both s1.jsonl and s2.jsonl,
        # we get 2 * 3 = 6 total reviews (each file contributes the full history)
        "expected_total": 6,
        "expected_passed": 4,  # 2 passed per file * 2 files
        "expected_failed": 2,  # 1 failed per file * 2 files
        # All unique review keys from both files
        "expected_seen": {
            # From s1.jsonl: ("s1", iter, status) for each history entry
            ("s1", 1, "passed"),
            ("s1", 2, "passed"),
            ("s1", 1, "failed"),  # third history entry has status=failed
            # From s2.jsonl: ("s2", iter, status) for each history entry
            ("s2", 1, "passed"),
            ("s2", 2, "passed"),
            ("s2", 1, "failed"),  # third history entry has status=failed
        },
        "raises": None,
    },
    # Case 6: Deduplication - same review seen twice
    {
        "name": "deduplication_same_review",
        "progress_files": ["s1.jsonl"],
        # First call adds to seen_reviews, second call should skip
        "history_return": _make_mock_history([("s1", 1, {"overall_status": "passed"})]),
        "expected_total": 0,  # Skipped due to pre-populate_seen
        "expected_passed": 0,
        "expected_failed": 0,
        "expected_seen": {("s1", 1, "passed")},  # Already in seen, not added again
        "raises": None,
        "pre_populate_seen": {("s1", 1, "passed")},
    },
    # Case 7: JSONDecodeError handling
    {
        "name": "json_decode_error_handling",
        "progress_files": ["bad.jsonl"],
        "history_return": _make_mock_history([]),  # Error occurs during load
        "expected_total": 0,
        "expected_passed": 0,
        "expected_failed": 0,
        "expected_seen": set(),
        "raises": json.JSONDecodeError("Invalid JSON", "", 0),
    },
    # Case 8: OSError handling (missing file)
    {
        "name": "os_error_handling",
        "progress_files": ["missing.jsonl"],
        "history_return": _make_mock_history([]),
        "expected_total": 0,
        "expected_passed": 0,
        "expected_failed": 0,
        "expected_seen": set(),
        "raises": OSError("File not found"),
    },
    # Case 9: ValueError handling (invalid session_id)
    {
        "name": "value_error_handling",
        "progress_files": ["../escape.jsonl"],
        "history_return": _make_mock_history([]),
        "expected_total": 0,
        "expected_passed": 0,
        "expected_failed": 0,
        "expected_seen": set(),
        "raises": ValueError("Invalid session_id"),
    },
]


@pytest.mark.parametrize("case", COLLECT_REVIEW_STATS_CASES)
@patch("auto_prd.readiness_loop.load_progress_history")
def test_collect_review_statistics(mock_load_progress, case, temp_repo):
    """Test _collect_review_statistics with various scenarios.

    This is a table-driven test that covers:
    - Aggregation of passed/failed/partial review outcomes across iterations
    - Deduplication behavior when processing the same review multiple times
    - File I/O error handling (OSError, JSONDecodeError, ValueError)
    - Edge cases: empty progress history, missing files, malformed JSON
    """
    from auto_prd.progress_renderer import ProgressHistory
    from auto_prd.readiness_loop import ReadinessOrchestrator

    orchestrator = ReadinessOrchestrator(temp_repo)

    # Pre-populate seen_reviews if test case requires it
    if case.get("pre_populate_seen"):
        orchestrator._seen_reviews = case["pre_populate_seen"].copy()

    # Create progress directory in temp repo
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        progress_dir = Path(tmpdir) / "aprd" / "progress"
        progress_dir.mkdir(parents=True, exist_ok=True)

        # Create actual progress files for the test
        for fname in case["progress_files"]:
            progress_file = progress_dir / fname
            progress_file.write_text('{"iteration": 1, "review_round": {}}')

        # Set environment to use our temp directory
        import os

        original_xdg = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = tmpdir

        try:
            # Configure mock return value or exception for load_progress_history
            # The mock should only return history for the specific session_id being requested
            if case["raises"]:
                mock_load_progress.side_effect = case["raises"]
            else:
                # Make the mock return the same history for any session_id
                # This simulates each progress file having its own independent history
                mock_load_progress.return_value = case["history_return"]

            # Call the method
            orchestrator._collect_review_statistics()
        finally:
            # Restore environment
            if original_xdg is None:
                os.environ.pop("XDG_CONFIG_HOME", None)
            else:
                os.environ["XDG_CONFIG_HOME"] = original_xdg

    # For cases with multiple progress files, each file contributes its own history
    # The test expectations account for this: multiple files with same history
    # will result in multiplying the counts by the number of files
    assert orchestrator.stats.review_round_total == case["expected_total"], (
        f"Case '{case['name']}': expected total {case['expected_total']}, "
        f"got {orchestrator.stats.review_round_total}"
    )
    assert orchestrator.stats.review_round_passed == case["expected_passed"], (
        f"Case '{case['name']}': expected passed {case['expected_passed']}, "
        f"got {orchestrator.stats.review_round_passed}"
    )
    assert orchestrator.stats.review_round_failed == case["expected_failed"], (
        f"Case '{case['name']}': expected failed {case['expected_failed']}, "
        f"got {orchestrator.stats.review_round_failed}"
    )
    assert orchestrator._seen_reviews == case["expected_seen"], (
        f"Case '{case['name']}': expected seen_reviews {case['expected_seen']}, "
        f"got {orchestrator._seen_reviews}"
    )


def test_collect_review_statistics_deduplication_multiple_calls(temp_repo):
    """Test that _collect_review_statistics properly deduplicates across multiple calls.

    This test verifies the instance-level _seen_reviews set persists across
    multiple iterations of the readiness loop to prevent double-counting.
    """
    import os
    import tempfile
    from unittest.mock import patch

    from auto_prd.readiness_loop import ReadinessOrchestrator

    orchestrator = ReadinessOrchestrator(temp_repo)

    with tempfile.TemporaryDirectory() as tmpdir:
        progress_dir = Path(tmpdir) / "aprd" / "progress"
        progress_dir.mkdir(parents=True, exist_ok=True)
        (progress_dir / "session_123.jsonl").write_text("{}")

        mock_history = _make_mock_history(
            [("session_123", 1, {"overall_status": "passed"})]
        )

        with patch.dict(os.environ, {"XDG_CONFIG_HOME": tmpdir}):
            with patch(
                "auto_prd.readiness_loop.load_progress_history",
                return_value=mock_history,
            ):
                # First call should count the review
                orchestrator._collect_review_statistics()
                assert orchestrator.stats.review_round_total == 1
                assert orchestrator.stats.review_round_passed == 1

                # Second call should NOT re-count the same review
                orchestrator._collect_review_statistics()
                assert orchestrator.stats.review_round_total == 1  # Still 1, not 2
                assert orchestrator.stats.review_round_passed == 1
