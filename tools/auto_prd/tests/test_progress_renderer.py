"""Tests for the progress_renderer module."""

import json
import tempfile
from pathlib import Path
from unittest import mock

from auto_prd.progress_renderer import (
    IterationSummary,
    ProgressHistory,
    clear_progress_history,
    format_progress_for_prompt,
    get_progress_path,
    load_progress_history,
    render_progress_txt,
    save_iteration_summary,
)


class TestIterationSummary:
    """Tests for IterationSummary."""

    def test_to_dict(self) -> None:
        """Test IterationSummary to dictionary conversion."""
        summary = IterationSummary(
            iteration=1,
            status="completed",
            files_changed=["src/test.py"],
            learnings=["Pattern: Uses pytest"],
            issues_found=["Type mismatch found"],
            tasks_completed=["T001"],
            tasks_remaining=5,
            phase="local",
            commits_made=2,
        )
        data = summary.to_dict()

        assert data["iteration"] == 1
        assert data["status"] == "completed"
        assert data["files_changed"] == ["src/test.py"]
        assert data["learnings"] == ["Pattern: Uses pytest"]
        assert data["issues_found"] == ["Type mismatch found"]
        assert data["tasks_completed"] == ["T001"]
        assert data["tasks_remaining"] == 5
        assert data["phase"] == "local"
        assert data["commits_made"] == 2

    def test_from_dict(self) -> None:
        """Test IterationSummary from dictionary creation."""
        data = {
            "iteration": 2,
            "status": "completed_with_warnings",
            "files_changed": ["src/main.py"],
            "learnings": ["Uses TypeVar for generics"],
            "issues_found": [],
            "tasks_completed": ["T002"],
            "tasks_remaining": 4,
            "phase": "review_fix",
            "commits_made": 1,
        }
        summary = IterationSummary.from_dict(data)

        assert summary.iteration == 2
        assert summary.status == "completed_with_warnings"
        assert summary.files_changed == ["src/main.py"]
        assert summary.learnings == ["Uses TypeVar for generics"]
        assert summary.issues_found == []
        assert summary.tasks_completed == ["T002"]
        assert summary.tasks_remaining == 4
        assert summary.phase == "review_fix"
        assert summary.commits_made == 1

    def test_to_markdown(self) -> None:
        """Test IterationSummary to markdown conversion."""
        summary = IterationSummary(
            iteration=1,
            status="completed",
            files_changed=["src/test.py"],
            learnings=["Pattern: Uses pytest"],
            issues_found=["Type mismatch found"],
            tasks_completed=["T001"],
            tasks_remaining=5,
            phase="local",
            commits_made=2,
        )
        markdown = summary.to_markdown()

        assert "### Iteration 1" in markdown
        assert "**Status:** completed" in markdown
        assert "**Phase:** local" in markdown
        assert "**Commits:** 2" in markdown
        assert "- src/test.py" in markdown
        assert "- Type mismatch found" in markdown
        assert "- Pattern: Uses pytest" in markdown
        assert "**Tasks Completed:** T001" in markdown
        assert "**Tasks Remaining:** 5" in markdown


class TestProgressHistory:
    """Tests for ProgressHistory."""

    def test_add_iteration(self) -> None:
        """Test adding iteration to history."""
        history = ProgressHistory(session_id="test-session")

        summary1 = IterationSummary(
            iteration=1,
            learnings=["Pattern: Uses pytest fixtures"],
            commits_made=2,
        )
        history.add_iteration(summary1)

        assert len(history.iterations) == 1
        assert history.total_iterations == 1
        assert history.total_commits == 2
        assert "Pattern: Uses pytest fixtures" in history.codebase_patterns

        summary2 = IterationSummary(
            iteration=2,
            learnings=["Pattern: Uses TypeVar"],
            commits_made=1,
        )
        history.add_iteration(summary2)

        assert len(history.iterations) == 2
        assert history.total_iterations == 2
        assert history.total_commits == 3
        assert "Pattern: Uses TypeVar" in history.codebase_patterns

    def test_get_latest_iteration(self) -> None:
        """Test getting latest iteration."""
        history = ProgressHistory(session_id="test-session")

        assert history.get_latest_iteration() is None

        summary1 = IterationSummary(iteration=1)
        history.add_iteration(summary1)

        assert history.get_latest_iteration().iteration == 1

        summary2 = IterationSummary(iteration=2)
        history.add_iteration(summary2)

        assert history.get_latest_iteration().iteration == 2

    def test_to_markdown(self) -> None:
        """Test converting history to markdown."""
        history = ProgressHistory(session_id="test-session")
        history.codebase_patterns = ["Uses pytest", "TypeVar for generics"]

        summary = IterationSummary(
            iteration=1,
            status="completed",
            files_changed=["src/test.py"],
            learnings=["Discovered: Uses pytest fixtures"],
            tasks_completed=["T001"],
            tasks_remaining=5,
        )
        history.add_iteration(summary)

        markdown = history.to_markdown()

        assert "# Ralph Progress Log" in markdown
        assert "test-session" in markdown
        assert "## Codebase Patterns (Discovered)" in markdown
        assert "- Uses pytest" in markdown
        assert "- TypeVar for generics" in markdown
        assert "## Iteration History" in markdown
        assert "### Iteration 1" in markdown
        assert "- src/test.py" in markdown

    def test_to_dict(self) -> None:
        """Test converting history to dictionary."""
        history = ProgressHistory(session_id="test-session")
        summary = IterationSummary(iteration=1)
        history.add_iteration(summary)

        data = history.to_dict()

        assert data["session_id"] == "test-session"
        assert data["total_iterations"] == 1
        assert len(data["iterations"]) == 1

    def test_from_dict(self) -> None:
        """Test creating history from dictionary."""
        data = {
            "session_id": "test-session",
            "started_at": "2025-01-12T10:00:00Z",
            "codebase_patterns": ["Pattern 1"],
            "iterations": [
                {
                    "iteration": 1,
                    "status": "completed",
                    "files_changed": [],
                    "learnings": [],
                    "issues_found": [],
                    "tasks_completed": [],
                    "tasks_remaining": 0,
                    "phase": "local",
                    "commits_made": 0,
                }
            ],
            "total_commits": 1,
            "total_iterations": 1,
        }
        history = ProgressHistory.from_dict(data)

        assert history.session_id == "test-session"
        assert len(history.iterations) == 1
        assert history.codebase_patterns == ["Pattern 1"]


class TestGetProgressPath:
    """Tests for get_progress_path."""

    def test_returns_correct_path(self) -> None:
        """Test that path is correctly constructed."""
        path = get_progress_path("test-session")
        assert "test-session.jsonl" in str(path)
        assert "aprd/progress" in str(path)

    def test_uses_xdg_config_home(self) -> None:
        """Test that XDG_CONFIG_HOME is respected."""
        with mock.patch.dict("os.environ", {"XDG_CONFIG_HOME": "/custom/config"}):
            path = get_progress_path("test-session")
            assert str(path).startswith("/custom/config/aprd/progress")


class TestLoadProgressHistory:
    """Tests for load_progress_history."""

    def test_load_nonexistent_returns_empty_history(self) -> None:
        """Test loading nonexistent session returns empty history."""
        # Use a session ID that won't exist
        history = load_progress_history("nonexistent-session-xyz123")

        assert history.session_id == "nonexistent-session-xyz123"
        assert len(history.iterations) == 0

    def test_load_existing_session(self) -> None:
        """Test loading existing session history."""
        with tempfile.TemporaryDirectory() as tmpdir:
            progress_path = Path(tmpdir) / "test-session.jsonl"
            progress_path.parent.mkdir(parents=True, exist_ok=True)

            # Write test data
            data1 = {
                "iteration": 1,
                "status": "completed",
                "files_changed": ["src/test.py"],
                "learnings": ["Pattern: Uses pytest"],
                "issues_found": [],
                "tasks_completed": ["T001"],
                "tasks_remaining": 5,
                "phase": "local",
                "commits_made": 2,
            }
            data2 = {
                "iteration": 2,
                "status": "completed",
                "files_changed": [],
                "learnings": [],
                "issues_found": [],
                "tasks_completed": ["T002"],
                "tasks_remaining": 4,
                "phase": "local",
                "commits_made": 1,
            }

            with open(progress_path, "w") as f:
                f.write(json.dumps(data1) + "\n")
                f.write(json.dumps(data2) + "\n")

            # Mock get_progress_path to return our temp file
            with mock.patch(
                "auto_prd.progress_renderer.get_progress_path",
                return_value=progress_path,
            ):
                history = load_progress_history("test-session")

                assert len(history.iterations) == 2
                assert history.iterations[0].iteration == 1
                assert history.iterations[1].iteration == 2
                assert history.total_commits == 3


class TestSaveIterationSummary:
    """Tests for save_iteration_summary."""

    def test_save_creates_file(self) -> None:
        """Test saving creates file with correct content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            progress_path = Path(tmpdir) / "test-session.jsonl"

            summary = IterationSummary(
                iteration=1,
                status="completed",
                commits_made=2,
            )

            with mock.patch(
                "auto_prd.progress_renderer.get_progress_path",
                return_value=progress_path,
            ):
                save_iteration_summary("test-session", summary)

                assert progress_path.exists()

                content = progress_path.read_text()
                data = json.loads(content.strip())
                assert data["iteration"] == 1
                assert data["commits_made"] == 2

    def test_save_appends_to_existing_file(self) -> None:
        """Test saving appends to existing file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            progress_path = Path(tmpdir) / "test-session.jsonl"
            progress_path.parent.mkdir(parents=True, exist_ok=True)

            # Write initial content
            summary1 = IterationSummary(iteration=1, commits_made=1)

            with mock.patch(
                "auto_prd.progress_renderer.get_progress_path",
                return_value=progress_path,
            ):
                save_iteration_summary("test-session", summary1)

                # Save another
                summary2 = IterationSummary(iteration=2, commits_made=2)
                save_iteration_summary("test-session", summary2)

                # Check both are in file
                lines = progress_path.read_text().strip().split("\n")
                assert len(lines) == 2

                data1 = json.loads(lines[0])
                data2 = json.loads(lines[1])
                assert data1["iteration"] == 1
                assert data2["iteration"] == 2


class TestFormatProgressForPrompt:
    """Tests for format_progress_for_prompt."""

    def test_empty_history_returns_empty_string(self) -> None:
        """Test formatting empty history returns empty string."""
        history = ProgressHistory(session_id="test")
        result = format_progress_for_prompt(history)
        assert result == ""

    def test_formats_recent_iterations(self) -> None:
        """Test formatting includes recent iterations."""
        history = ProgressHistory(session_id="test-session")
        history.add_iteration(
            IterationSummary(iteration=1, learnings=["Learning 1"], phase="local")
        )
        history.add_iteration(
            IterationSummary(iteration=2, learnings=["Learning 2"], phase="pr")
        )

        result = format_progress_for_prompt(history, max_iterations=2)

        assert "[recent_progress]" in result
        assert "test-session" in result
        assert "Iteration 1 (local)" in result
        assert "Iteration 2 (pr)" in result
        assert "Learning 1" in result
        assert "Learning 2" in result
        assert "[/recent_progress]" in result

    def test_limits_iterations(self) -> None:
        """Test max_iterations limits iterations included."""
        history = ProgressHistory(session_id="test")
        for i in range(5):
            history.add_iteration(IterationSummary(iteration=i + 1))

        result = format_progress_for_prompt(history, max_iterations=2)

        # Should only include last 2
        assert "Iteration 4" in result
        assert "Iteration 5" in result
        assert "Iteration 1" not in result
        assert "Iteration 2" not in result


class TestRenderProgressTxt:
    """Tests for render_progress_txt."""

    def test_render_nonexistent_returns_none(self) -> None:
        """Test rendering nonexistent session returns None."""
        # Use session that won't exist
        result = render_progress_txt("nonexistent-session-xyz123")
        assert result is None

    def test_render_returns_markdown(self) -> None:
        """Test rendering returns markdown content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            progress_path = Path(tmpdir) / "test-session.jsonl"
            progress_path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "iteration": 1,
                "status": "completed",
                "files_changed": ["src/test.py"],
                "learnings": ["Pattern: Uses pytest"],
                "issues_found": [],
                "tasks_completed": ["T001"],
                "tasks_remaining": 5,
                "phase": "local",
                "commits_made": 2,
            }

            with open(progress_path, "w") as f:
                f.write(json.dumps(data) + "\n")

            with mock.patch(
                "auto_prd.progress_renderer.get_progress_path",
                return_value=progress_path,
            ):
                result = render_progress_txt("test-session")

                assert result is not None
                assert "# Ralph Progress Log" in result
                assert "test-session" in result
                assert "## Iteration History" in result
                assert "### Iteration 1" in result


class TestClearProgressHistory:
    """Tests for clear_progress_history."""

    def test_clear_deletes_file(self) -> None:
        """Test clearing deletes the progress file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            progress_path = Path(tmpdir) / "test-session.jsonl"
            progress_path.parent.mkdir(parents=True, exist_ok=True)

            # Create file
            progress_path.write_text("test content")

            with mock.patch(
                "auto_prd.progress_renderer.get_progress_path",
                return_value=progress_path,
            ):
                clear_progress_history("test-session")
                assert not progress_path.exists()

    def test_clear_nonexistent_is_safe(self) -> None:
        """Test clearing nonexistent file is safe."""
        with tempfile.TemporaryDirectory() as tmpdir:
            progress_path = Path(tmpdir) / "nonexistent-session.jsonl"

            with mock.patch(
                "auto_prd.progress_renderer.get_progress_path",
                return_value=progress_path,
            ):
                # Should not raise
                clear_progress_history("nonexistent-session")
