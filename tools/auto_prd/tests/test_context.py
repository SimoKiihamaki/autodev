"""Tests for context.py module."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from .test_helpers import safe_import

# Import the context module and classes we need to test
context_module = safe_import("tools.auto_prd.context", "..context")
SessionMemory = safe_import("tools.auto_prd.context", "..context", "SessionMemory")
LoadSessionResult = safe_import(
    "tools.auto_prd.context", "..context", "LoadSessionResult"
)
LoadFailureReason = safe_import(
    "tools.auto_prd.context", "..context", "LoadFailureReason"
)
StallDetector = safe_import("tools.auto_prd.context", "..context", "StallDetector")
build_phase_context = safe_import(
    "tools.auto_prd.context", "..context", "build_phase_context"
)
compact_context = safe_import("tools.auto_prd.context", "..context", "compact_context")
save_session_memory = safe_import(
    "tools.auto_prd.context", "..context", "save_session_memory"
)
load_session_memory = safe_import(
    "tools.auto_prd.context", "..context", "load_session_memory"
)

# Import ClaudeHeadlessResponse from agents for update_from_response tests
ClaudeHeadlessResponse = safe_import(
    "tools.auto_prd.agents", "..agents", "ClaudeHeadlessResponse"
)


class SessionMemoryTests(unittest.TestCase):
    """Test suite for SessionMemory dataclass."""

    def test_basic_creation(self):
        """Test basic SessionMemory creation with defaults."""
        memory = SessionMemory(session_id="test-session")
        self.assertEqual(memory.session_id, "test-session")
        self.assertEqual(memory.total_cost_usd, 0.0)
        self.assertEqual(memory.total_duration_ms, 0)
        self.assertEqual(memory.errors, [])
        self.assertIsNotNone(memory.created_at)

    def test_negative_cost_raises_value_error(self):
        """Test that negative total_cost_usd raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            SessionMemory(session_id="test", total_cost_usd=-1.0)
        self.assertIn("non-negative", str(ctx.exception))

    def test_negative_duration_raises_value_error(self):
        """Test that negative total_duration_ms raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            SessionMemory(session_id="test", total_duration_ms=-100)
        self.assertIn("non-negative", str(ctx.exception))

    def test_assignment_validation_cost(self):
        """Test that assigning negative cost after creation raises ValueError."""
        memory = SessionMemory(session_id="test")
        with self.assertRaises(ValueError):
            memory.total_cost_usd = -5.0

    def test_assignment_validation_duration(self):
        """Test that assigning negative duration after creation raises ValueError."""
        memory = SessionMemory(session_id="test")
        with self.assertRaises(ValueError):
            memory.total_duration_ms = -100

    def test_assignment_validation_type_cost(self):
        """Test that assigning non-numeric cost raises TypeError."""
        memory = SessionMemory(session_id="test")
        with self.assertRaises(TypeError):
            memory.total_cost_usd = "not a number"

    def test_assignment_validation_type_duration(self):
        """Test that assigning non-numeric duration raises TypeError."""
        memory = SessionMemory(session_id="test")
        with self.assertRaises(TypeError):
            memory.total_duration_ms = "not a number"

    def test_to_dict(self):
        """Test SessionMemory.to_dict() serialization."""
        memory = SessionMemory(
            session_id="test-session",
            total_cost_usd=0.05,
            total_duration_ms=1000,
            errors=["error1"],
        )
        data = memory.to_dict()
        self.assertEqual(data["session_id"], "test-session")
        self.assertEqual(data["total_cost_usd"], 0.05)
        self.assertEqual(data["total_duration_ms"], 1000)
        self.assertEqual(data["errors"], ["error1"])
        self.assertIn("created_at", data)

    def test_from_dict_valid(self):
        """Test SessionMemory.from_dict() with valid data."""
        data = {
            "session_id": "restored-session",
            "created_at": "2024-01-01T00:00:00Z",
            "total_cost_usd": 0.10,
            "total_duration_ms": 2000,
            "files_touched": ["file1.py", "file2.py"],
            "commits_made": ["abc123"],
            "errors": [],
            "phase_outcomes": {"implement": "success"},
        }
        memory = SessionMemory.from_dict(data)
        self.assertEqual(memory.session_id, "restored-session")
        self.assertEqual(memory.total_cost_usd, 0.10)
        self.assertEqual(memory.total_duration_ms, 2000)
        self.assertEqual(len(memory.files_touched), 2)

    def test_from_dict_null_numeric_fields(self):
        """Test SessionMemory.from_dict() handles null numeric fields."""
        data = {
            "session_id": "test",
            "total_cost_usd": None,
            "total_duration_ms": None,
        }
        # Should not raise, uses defaults
        memory = SessionMemory.from_dict(data)
        self.assertEqual(memory.total_cost_usd, 0.0)
        self.assertEqual(memory.total_duration_ms, 0)

    def test_from_dict_invalid_type_files_touched(self):
        """Test SessionMemory.from_dict() raises TypeError for invalid files_touched."""
        data = {
            "session_id": "test",
            "files_touched": "not a list",
        }
        with self.assertRaises(TypeError) as ctx:
            SessionMemory.from_dict(data)
        self.assertIn("files_touched must be a list", str(ctx.exception))

    def test_from_dict_invalid_type_phase_outcomes(self):
        """Test SessionMemory.from_dict() raises TypeError for invalid phase_outcomes."""
        data = {
            "session_id": "test",
            "phase_outcomes": ["not", "a", "dict"],
        }
        with self.assertRaises(TypeError) as ctx:
            SessionMemory.from_dict(data)
        self.assertIn("phase_outcomes must be a dict", str(ctx.exception))

    def test_from_dict_invalid_cost_type(self):
        """Test SessionMemory.from_dict() raises TypeError for invalid cost type."""
        data = {
            "session_id": "test",
            "total_cost_usd": "not numeric",
        }
        with self.assertRaises(TypeError) as ctx:
            SessionMemory.from_dict(data)
        self.assertIn("total_cost_usd must be numeric", str(ctx.exception))

    def test_update_from_response(self):
        """Test SessionMemory.update_from_response() updates fields correctly."""
        memory = SessionMemory(session_id="")
        mock_response = MagicMock(spec=ClaudeHeadlessResponse)
        mock_response.total_cost_usd = 0.05
        mock_response.duration_ms = 1500
        mock_response.is_error = False
        mock_response.session_id = "new-session-id"

        memory.update_from_response(mock_response, "implement")

        self.assertEqual(memory.total_cost_usd, 0.05)
        self.assertEqual(memory.total_duration_ms, 1500)
        self.assertEqual(memory.session_id, "new-session-id")
        self.assertEqual(len(memory.errors), 0)

    def test_update_from_response_with_error(self):
        """Test SessionMemory.update_from_response() records errors."""
        memory = SessionMemory(session_id="test")
        mock_response = MagicMock(spec=ClaudeHeadlessResponse)
        mock_response.total_cost_usd = 0.02
        mock_response.duration_ms = 500
        mock_response.is_error = True
        mock_response.session_id = ""

        memory.update_from_response(mock_response, "fix")

        self.assertEqual(len(memory.errors), 1)
        self.assertIn("fix", memory.errors[0])


class LoadSessionResultTests(unittest.TestCase):
    """Test suite for LoadSessionResult dataclass."""

    def test_success_state(self):
        """Test LoadSessionResult with successful load."""
        memory = SessionMemory(session_id="test")
        result = LoadSessionResult(memory=memory)
        self.assertTrue(result.is_success)
        self.assertEqual(result.memory, memory)
        self.assertIsNone(result.failure_reason)

    def test_failure_state(self):
        """Test LoadSessionResult with failure."""
        result = LoadSessionResult(
            memory=None,
            failure_reason=LoadFailureReason.NOT_FOUND,
            error_message="File not found",
        )
        self.assertFalse(result.is_success)
        self.assertIsNone(result.memory)
        self.assertEqual(result.failure_reason, LoadFailureReason.NOT_FOUND)

    def test_mutual_exclusivity_both_set(self):
        """Test that setting both memory and failure_reason raises ValueError."""
        memory = SessionMemory(session_id="test")
        with self.assertRaises(ValueError) as ctx:
            LoadSessionResult(
                memory=memory,
                failure_reason=LoadFailureReason.NOT_FOUND,
            )
        self.assertIn("cannot have both", str(ctx.exception))

    def test_mutual_exclusivity_neither_set(self):
        """Test that setting neither memory nor failure_reason raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            LoadSessionResult(memory=None, failure_reason=None)
        self.assertIn("must have either", str(ctx.exception))


class SaveLoadSessionMemoryTests(unittest.TestCase):
    """Test suite for save_session_memory and load_session_memory functions."""

    def setUp(self):
        """Set up temporary directory for tests."""
        self.temp_dir = tempfile.mkdtemp()
        self.repo_root = Path(self.temp_dir)

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_save_and_load_roundtrip(self):
        """Test saving and loading session memory roundtrip."""
        memory = SessionMemory(
            session_id="roundtrip-test",
            total_cost_usd=0.15,
            total_duration_ms=3000,
        )

        filepath = save_session_memory(memory, self.repo_root)
        self.assertIsNotNone(filepath)
        self.assertTrue(filepath.exists())

        result = load_session_memory(filepath)
        self.assertTrue(result.is_success)
        self.assertEqual(result.memory.session_id, "roundtrip-test")
        self.assertEqual(result.memory.total_cost_usd, 0.15)
        self.assertEqual(result.memory.total_duration_ms, 3000)

    def test_save_creates_directory(self):
        """Test that save_session_memory creates .aprd/memory directory."""
        memory = SessionMemory(session_id="dir-test")
        filepath = save_session_memory(memory, self.repo_root)
        self.assertIsNotNone(filepath)
        self.assertTrue((self.repo_root / ".aprd" / "memory").exists())

    def test_load_nonexistent_file(self):
        """Test load_session_memory with nonexistent file."""
        result = load_session_memory(self.repo_root / "nonexistent.json")
        self.assertFalse(result.is_success)
        self.assertEqual(result.failure_reason, LoadFailureReason.NOT_FOUND)

    def test_load_corrupted_json(self):
        """Test load_session_memory with corrupted JSON."""
        bad_file = self.repo_root / "corrupted.json"
        bad_file.write_text("not valid json {{{")

        result = load_session_memory(bad_file)
        self.assertFalse(result.is_success)
        self.assertEqual(result.failure_reason, LoadFailureReason.CORRUPTED_JSON)

    def test_load_invalid_format(self):
        """Test load_session_memory with invalid data format."""
        bad_file = self.repo_root / "invalid.json"
        bad_file.write_text(
            json.dumps({"session_id": "test", "files_touched": "not a list"})
        )

        result = load_session_memory(bad_file)
        self.assertFalse(result.is_success)
        self.assertEqual(result.failure_reason, LoadFailureReason.INVALID_FORMAT)

    def test_save_failure_returns_none(self):
        """Test save_session_memory returns None on failure (default behavior)."""
        memory = SessionMemory(session_id="test")
        # Use a path that can't be written to
        with patch("builtins.open", side_effect=OSError("Permission denied")):
            # Create directory first so mkdir succeeds
            (self.repo_root / ".aprd" / "memory").mkdir(parents=True, exist_ok=True)
            result = save_session_memory(memory, self.repo_root, raise_on_failure=False)
            self.assertIsNone(result)

    def test_save_failure_raises_when_requested(self):
        """Test save_session_memory raises OSError when raise_on_failure=True."""
        memory = SessionMemory(session_id="test")
        with patch("builtins.open", side_effect=OSError("Permission denied")):
            (self.repo_root / ".aprd" / "memory").mkdir(parents=True, exist_ok=True)
            with self.assertRaises(OSError):
                save_session_memory(memory, self.repo_root, raise_on_failure=True)


class StallDetectorTests(unittest.TestCase):
    """Test suite for StallDetector class."""

    def test_basic_creation(self):
        """Test StallDetector creation with default thresholds."""
        detector = StallDetector()
        self.assertEqual(detector.no_output_threshold_seconds, 120.0)
        self.assertEqual(detector.no_progress_threshold_iterations, 3)

    def test_custom_thresholds(self):
        """Test StallDetector creation with custom thresholds."""
        detector = StallDetector(
            no_output_threshold_seconds=60.0,
            no_progress_threshold_iterations=5,
        )
        self.assertEqual(detector.no_output_threshold_seconds, 60.0)
        self.assertEqual(detector.no_progress_threshold_iterations, 5)

    def test_invalid_output_threshold_raises(self):
        """Test that non-positive output threshold raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            StallDetector(no_output_threshold_seconds=0)
        self.assertIn("positive", str(ctx.exception))

        with self.assertRaises(ValueError):
            StallDetector(no_output_threshold_seconds=-10.0)

    def test_invalid_progress_threshold_raises(self):
        """Test that threshold < 1 raises ValueError with correct message."""
        with self.assertRaises(ValueError) as ctx:
            StallDetector(no_progress_threshold_iterations=0)
        self.assertIn("at least 1", str(ctx.exception))

    def test_record_output_resets_timer(self):
        """Test that record_output resets the output timer."""
        detector = StallDetector(no_output_threshold_seconds=10.0)

        with patch("tools.auto_prd.context.time.monotonic") as mock_time:
            mock_time.return_value = 100.0
            detector.record_output()
            self.assertAlmostEqual(detector.seconds_since_output, 0.0, delta=0.1)

    def test_record_iteration_with_progress(self):
        """Test record_iteration detects progress (decreasing task count)."""
        detector = StallDetector()

        detector.record_iteration(tasks_left=10)
        self.assertEqual(detector.no_progress_streak, 0)

        detector.record_iteration(tasks_left=8)  # Progress!
        self.assertEqual(detector.no_progress_streak, 0)

        detector.record_iteration(tasks_left=8)  # No progress
        self.assertEqual(detector.no_progress_streak, 1)

        detector.record_iteration(tasks_left=5)  # Progress again!
        self.assertEqual(detector.no_progress_streak, 0)

    def test_record_iteration_no_progress(self):
        """Test record_iteration tracks no-progress streak."""
        detector = StallDetector()

        detector.record_iteration(tasks_left=5)
        detector.record_iteration(tasks_left=5)  # No progress
        detector.record_iteration(tasks_left=6)  # Worse, still no progress

        self.assertEqual(detector.no_progress_streak, 2)

    def test_check_stall_output_timeout(self):
        """Test check_stall detects output timeout."""
        detector = StallDetector(no_output_threshold_seconds=10.0)

        with patch("tools.auto_prd.context.time.monotonic") as mock_time:
            # Initial time
            mock_time.return_value = 0.0
            detector.record_output()

            # Simulate 15 seconds elapsed
            mock_time.return_value = 15.0
            is_stalled, reason = detector.check_stall()

            self.assertTrue(is_stalled)
            self.assertIn("No output", reason)
            self.assertIn("15.0", reason)

    def test_check_stall_no_progress(self):
        """Test check_stall detects no-progress stall."""
        detector = StallDetector(no_progress_threshold_iterations=2)

        # Record iterations without progress
        detector.record_iteration(tasks_left=5)
        detector.record_iteration(tasks_left=5)
        detector.record_iteration(tasks_left=5)

        is_stalled, reason = detector.check_stall()
        self.assertTrue(is_stalled)
        self.assertIn("No task progress", reason)

    def test_check_stall_not_stalled(self):
        """Test check_stall returns False when not stalled."""
        detector = StallDetector()
        detector.record_output()  # Fresh output
        detector.record_iteration(tasks_left=5)
        detector.record_iteration(tasks_left=3)  # Progress

        is_stalled, reason = detector.check_stall()
        self.assertFalse(is_stalled)
        self.assertEqual(reason, "")

    def test_reset(self):
        """Test reset clears all tracking state."""
        detector = StallDetector()

        # Build up some state
        detector.record_iteration(tasks_left=5)
        detector.record_iteration(tasks_left=5)
        detector.record_iteration(tasks_left=5)

        self.assertEqual(detector.iteration_count, 3)
        self.assertEqual(detector.no_progress_streak, 2)

        # Reset
        detector.reset()

        self.assertEqual(detector.iteration_count, 0)
        self.assertEqual(detector.no_progress_streak, 0)


class BuildPhaseContextTests(unittest.TestCase):
    """Test suite for build_phase_context function."""

    def test_basic_context(self):
        """Test build_phase_context generates basic context string."""
        context = build_phase_context(
            phase="implement",
            prd_path=Path("/path/to/prd.md"),
            repo_root=Path("/repo"),
        )
        self.assertIn("<phase_context>", context)
        self.assertIn("Phase: implement", context)
        self.assertIn("Iteration: 1", context)
        self.assertIn("PRD location:", context)
        self.assertIn("</phase_context>", context)

    def test_with_iteration(self):
        """Test build_phase_context includes iteration number."""
        context = build_phase_context(
            phase="fix",
            prd_path=Path("/prd.md"),
            repo_root=Path("/repo"),
            iteration=3,
        )
        self.assertIn("Iteration: 3", context)

    def test_with_previous_summary(self):
        """Test build_phase_context includes previous summary."""
        context = build_phase_context(
            phase="review_fix",
            prd_path=Path("/prd.md"),
            repo_root=Path("/repo"),
            previous_summary="Fixed 3 issues in previous iteration",
        )
        self.assertIn("Previous iteration summary:", context)
        self.assertIn("Fixed 3 issues", context)

    def test_with_additional_context(self):
        """Test build_phase_context includes additional context."""
        context = build_phase_context(
            phase="pr",
            prd_path=Path("/prd.md"),
            repo_root=Path("/repo"),
            additional_context={"pr_number": "123", "branch": "feature/test"},
        )
        self.assertIn("Additional context:", context)
        self.assertIn("pr_number: 123", context)
        self.assertIn("branch: feature/test", context)


class CompactContextTests(unittest.TestCase):
    """Test suite for compact_context function."""

    def test_basic_compact(self):
        """Test compact_context creates summary."""
        mock_response = MagicMock(spec=ClaudeHeadlessResponse)
        mock_response.duration_ms = 2000
        mock_response.total_cost_usd = 0.05
        mock_response.num_turns = 5
        mock_response.is_error = False
        mock_response.result = "Successfully committed changes"

        summary = compact_context(mock_response, "implement")

        self.assertIn("Phase 'implement' completed", summary)
        self.assertIn("Duration: 2000ms", summary)
        self.assertIn("Cost: $0.0500", summary)
        self.assertIn("Turns: 5", summary)
        self.assertIn("committed changes", summary)

    def test_compact_with_error(self):
        """Test compact_context includes error status."""
        mock_response = MagicMock(spec=ClaudeHeadlessResponse)
        mock_response.duration_ms = 1000
        mock_response.total_cost_usd = 0.01
        mock_response.num_turns = 2
        mock_response.is_error = True
        mock_response.result = ""

        summary = compact_context(mock_response, "fix")

        self.assertIn("Status: ERROR", summary)

    def test_compact_truncation(self):
        """Test compact_context truncates long summaries."""
        mock_response = MagicMock(spec=ClaudeHeadlessResponse)
        mock_response.duration_ms = 1000
        mock_response.total_cost_usd = 0.01
        mock_response.num_turns = 1
        mock_response.is_error = False
        # Make result trigger action detection (commit, push, fix, test)
        # to generate a longer summary that will need truncation
        mock_response.result = (
            "commit push fixed test " * 50
        )  # Long result with actions

        summary = compact_context(mock_response, "test", max_length=100)

        # The summary should be truncated to max_length
        self.assertLessEqual(len(summary), 100)
        self.assertIn("truncated", summary)


if __name__ == "__main__":
    unittest.main()
