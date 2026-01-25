"""Tests for review round with mocked agent responses.

This module tests the review round functionality using mock fixtures
to simulate various agent response scenarios.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest

from tools.auto_prd.command import CalledProcessError, TimeoutExpired
from tools.auto_prd.review_round import (
    REVIEW_PROMPT,
    ReviewConfig,
    ReviewResult,
    ReviewRound,
)

# Import fixtures
from tools.tests.fixtures.review_responses import (
    GIT_DIFF_EMPTY,
    GIT_DIFF_MEDIUM,
    GIT_DIFF_SMALL,
    REVIEW_EMPTY,
    REVIEW_FAILED,
    REVIEW_MALFORMED_INCOMPLETE,
    REVIEW_MALFORMED_SYNTAX,
    REVIEW_NO_JSON,
    REVIEW_PARTIAL,
    REVIEW_PLAIN_JSON,
    REVIEW_SUCCESSFUL,
    REVIEW_WITH_PREFIX,
    TRACKER_MINIMAL,
    TRACKER_WITH_REVIEW_FIELDS,
    get_git_diff,
    get_review_response,
    get_tracker,
)


# ============================================================================
# ReviewConfig Tests
# ============================================================================


class TestReviewConfig:
    """Tests for ReviewConfig dataclass."""

    def test_default_values(self) -> None:
        """Test ReviewConfig initializes with default values."""
        config = ReviewConfig()
        assert config.enabled is True
        assert config.executor == "claude"
        assert config.model == "claude-sonnet-4-20250514"
        assert config.max_review_time == 300

    def test_custom_values(self) -> None:
        """Test ReviewConfig with custom values."""
        config = ReviewConfig(
            enabled=False,
            executor="codex",
            model="gpt-4",
            max_review_time=600,
        )
        assert config.enabled is False
        assert config.executor == "codex"
        assert config.model == "gpt-4"
        assert config.max_review_time == 600

    def test_codex_executor(self) -> None:
        """Test ReviewConfig with codex executor."""
        config = ReviewConfig(executor="codex")
        assert config.executor == "codex"


# ============================================================================
# ReviewResult Tests
# ============================================================================


class TestReviewResult:
    """Tests for ReviewResult dataclass."""

    def test_minimal_creation(self) -> None:
        """Test ReviewResult with minimal required fields."""
        result = ReviewResult(
            iteration=1,
            reviewer="claude",
            timestamp="2026-01-25T12:00:00Z",
            overall_status="passed",
            tasks_reviewed=2,
        )
        assert result.iteration == 1
        assert result.reviewer == "claude"
        assert result.overall_status == "passed"
        assert result.tasks_reviewed == 2
        assert result.statuses_updated == {}
        assert result.insights == {}
        assert result.next_steps == []
        assert result.git_diff_summary == ""
        assert result.summary == ""

    def test_full_creation(self) -> None:
        """Test ReviewResult with all fields populated."""
        result = ReviewResult(
            iteration=1,
            reviewer="claude",
            timestamp="2026-01-25T12:00:00Z",
            overall_status="partial",
            tasks_reviewed=3,
            statuses_updated={"T001": "completed", "T002": "in_progress"},
            insights={
                "positive": ["Good code"],
                "negative": ["Missing tests"],
                "patterns": ["Clean structure"],
            },
            next_steps=["Add tests", "Fix bugs"],
            git_diff_summary="Small changes",
            summary="Partial review complete",
        )
        assert len(result.statuses_updated) == 2
        assert len(result.insights) == 3
        assert len(result.next_steps) == 2


# ============================================================================
# ReviewRound Initialization Tests
# ============================================================================


class TestReviewRoundInit:
    """Tests for ReviewRound initialization."""

    def test_init_with_defaults(self, tmp_path: Path) -> None:
        """Test ReviewRound initialization with default config."""
        review_round = ReviewRound(tmp_path)
        assert review_round.repo_root == tmp_path
        assert review_round.config.enabled is True
        assert review_round.config.executor == "claude"

    def test_init_with_custom_config(self, tmp_path: Path) -> None:
        """Test ReviewRound initialization with custom config."""
        config = ReviewConfig(executor="codex", max_review_time=600)
        review_round = ReviewRound(tmp_path, config)
        assert review_round.config.executor == "codex"
        assert review_round.config.max_review_time == 600


# ============================================================================
# JSON Extraction Tests
# ============================================================================


class TestJSONExtraction:
    """Tests for JSON extraction from agent responses."""

    def test_extract_json_from_markdown_block(self) -> None:
        """Test extracting JSON from markdown code block."""
        review_round = ReviewRound(Path("/tmp"))
        result = review_round._extract_json(REVIEW_SUCCESSFUL)
        assert result is not None
        # Verify it's valid JSON
        data = json.loads(result)
        assert data["overall_assessment"] == "passed"

    def test_extract_json_from_plain_json(self) -> None:
        """Test extracting JSON from plain JSON response."""
        review_round = ReviewRound(Path("/tmp"))
        result = review_round._extract_json(REVIEW_PLAIN_JSON)
        assert result is not None
        data = json.loads(result)
        assert data["overall_assessment"] == "passed"

    def test_extract_json_with_prefix(self) -> None:
        """Test extracting JSON when preceded by explanatory text."""
        review_round = ReviewRound(Path("/tmp"))
        result = review_round._extract_json(REVIEW_WITH_PREFIX)
        assert result is not None
        data = json.loads(result)
        assert "overall_assessment" in data

    def test_extract_json_malformed_incomplete(self) -> None:
        """Test handling of incomplete JSON (missing closing brace)."""
        review_round = ReviewRound(Path("/tmp"))
        result = review_round._extract_json(REVIEW_MALFORMED_INCOMPLETE)
        # Should return None or the incomplete string
        # Either way, it shouldn't crash
        assert result is None or "{" in result

    def test_extract_json_malformed_syntax(self) -> None:
        """Test handling of JSON with syntax errors."""
        review_round = ReviewRound(Path("/tmp"))
        result = review_round._extract_json(REVIEW_MALFORMED_SYNTAX)
        # Should extract the string but parsing will fail separately
        assert result is not None

    def test_extract_json_no_json(self) -> None:
        """Test handling of response with no JSON at all."""
        review_round = ReviewRound(Path("/tmp"))
        result = review_round._extract_json(REVIEW_NO_JSON)
        assert result is None

    def test_extract_json_empty(self) -> None:
        """Test handling of empty response."""
        review_round = ReviewRound(Path("/tmp"))
        result = review_round._extract_json(REVIEW_EMPTY)
        assert result is None


# ============================================================================
# Review Result Parsing Tests
# ============================================================================


class TestParseReviewResult:
    """Tests for parsing review results from agent output."""

    def test_parse_successful_review(self) -> None:
        """Test parsing a successful review response."""
        review_round = ReviewRound(Path("/tmp"))
        result = review_round._parse_review_result(
            REVIEW_SUCCESSFUL, iteration=1, git_diff=GIT_DIFF_SMALL
        )

        assert result.iteration == 1
        assert result.overall_status == "passed"
        assert result.tasks_reviewed == 2
        assert len(result.statuses_updated) == 0  # No status changes in this response
        assert "positive" in result.insights
        assert len(result.next_steps) > 0

    def test_parse_partial_review(self) -> None:
        """Test parsing a partial review response."""
        review_round = ReviewRound(Path("/tmp"))
        result = review_round._parse_review_result(
            REVIEW_PARTIAL, iteration=1, git_diff=GIT_DIFF_MEDIUM
        )

        assert result.overall_status == "partial"
        assert result.tasks_reviewed == 3
        assert len(result.statuses_updated) == 2  # T002 and T001 changed
        assert "T002" in result.statuses_updated
        assert result.statuses_updated["T002"] == "in_progress"
        assert "negative" in result.insights
        assert len(result.next_steps) > 0

    def test_parse_failed_review(self) -> None:
        """Test parsing a failed review response."""
        review_round = ReviewRound(Path("/tmp"))
        result = review_round._parse_review_result(
            REVIEW_FAILED, iteration=1, git_diff=GIT_DIFF_MEDIUM
        )

        assert result.overall_status == "failed"
        assert result.tasks_reviewed == 2
        assert "T001" in result.statuses_updated
        assert result.statuses_updated["T001"] == "pending"
        assert "T002" in result.statuses_updated
        assert result.statuses_updated["T002"] == "in_progress"

    def test_parse_with_plain_json(self) -> None:
        """Test parsing response without markdown code blocks."""
        review_round = ReviewRound(Path("/tmp"))
        result = review_round._parse_review_result(
            REVIEW_PLAIN_JSON, iteration=1, git_diff=GIT_DIFF_SMALL
        )

        assert result.overall_status == "passed"
        assert result.tasks_reviewed == 1

    def test_parse_with_prefix_text(self) -> None:
        """Test parsing response with explanatory text before JSON."""
        review_round = ReviewRound(Path("/tmp"))
        result = review_round._parse_review_result(
            REVIEW_WITH_PREFIX, iteration=1, git_diff=GIT_DIFF_SMALL
        )

        assert result.overall_status == "passed"
        assert "summary" in result.__dict__

    def test_parse_malformed_json_fails_gracefully(self) -> None:
        """Test that malformed JSON returns a failed result."""
        review_round = ReviewRound(Path("/tmp"))
        result = review_round._parse_review_result(
            REVIEW_MALFORMED_INCOMPLETE,
            iteration=1,
            git_diff=GIT_DIFF_SMALL,
        )

        assert result.overall_status == "failed"
        assert result.tasks_reviewed == 0

    def test_parse_no_json_fails_gracefully(self) -> None:
        """Test that response with no JSON returns a failed result."""
        review_round = ReviewRound(Path("/tmp"))
        result = review_round._parse_review_result(
            REVIEW_NO_JSON, iteration=1, git_diff=GIT_DIFF_SMALL
        )

        assert result.overall_status == "failed"
        assert result.tasks_reviewed == 0

    def test_parse_empty_response_fails_gracefully(self) -> None:
        """Test that empty response returns a failed result."""
        review_round = ReviewRound(Path("/tmp"))
        result = review_round._parse_review_result(
            REVIEW_EMPTY, iteration=1, git_diff=GIT_DIFF_SMALL
        )

        assert result.overall_status == "failed"
        assert result.tasks_reviewed == 0


# ============================================================================
# Review Prompt Building Tests
# ============================================================================


class TestBuildReviewPrompt:
    """Tests for building the review prompt."""

    def test_build_prompt_contains_all_sections(self, tmp_path: Path) -> None:
        """Test that the prompt contains all required sections."""
        review_round = ReviewRound(tmp_path)
        tracker = get_tracker("minimal")

        with patch("tools.auto_prd.review_round.git_head_sha", return_value="abc123"):
            prompt = review_round._build_review_prompt(
                tracker=tracker,
                git_diff=GIT_DIFF_SMALL,
                iteration=1,
                base_branch="main",
            )

        assert "Iteration" in prompt and "1" in prompt
        assert "Base Branch" in prompt and "main" in prompt
        assert "Git SHA" in prompt and "abc123" in prompt
        assert "Tasks/Features to Review" in prompt
        assert "Current Tracker State" in prompt
        assert "Git Diff" in prompt
        assert GIT_DIFF_SMALL in prompt

    def test_build_prompt_includes_tasks(self, tmp_path: Path) -> None:
        """Test that the prompt includes task information."""
        review_round = ReviewRound(tmp_path)
        tracker = get_tracker("with_review")

        with patch("tools.auto_prd.review_round.git_head_sha", return_value="abc123"):
            prompt = review_round._build_review_prompt(
                tracker=tracker,
                git_diff=GIT_DIFF_SMALL,
                iteration=1,
                base_branch="main",
            )

        assert "T001" in prompt
        assert "Test task 1" in prompt
        assert "T002" in prompt
        assert "Test task 2" in prompt

    def test_build_prompt_includes_acceptance_criteria(self, tmp_path: Path) -> None:
        """Test that the prompt includes acceptance criteria."""
        review_round = ReviewRound(tmp_path)
        tracker = get_tracker("all_completed")

        with patch("tools.auto_prd.review_round.git_head_sha", return_value="abc123"):
            prompt = review_round._build_review_prompt(
                tracker=tracker,
                git_diff=GIT_DIFF_SMALL,
                iteration=1,
                base_branch="main",
            )

        assert "AC001" in prompt
        assert "Test criterion" in prompt

    def test_build_prompt_includes_tracker_summary(self, tmp_path: Path) -> None:
        """Test that the prompt includes tracker statistics."""
        review_round = ReviewRound(tmp_path)
        tracker = get_tracker("with_review")

        with patch("tools.auto_prd.review_round.git_head_sha", return_value="abc123"):
            prompt = review_round._build_review_prompt(
                tracker=tracker,
                git_diff=GIT_DIFF_SMALL,
                iteration=1,
                base_branch="main",
            )

        assert "Total tasks: 2" in prompt
        assert "Completed tasks: 1" in prompt
        assert "Tasks remaining: 1" in prompt

    def test_build_prompt_limits_diff_size(self, tmp_path: Path) -> None:
        """Test that large diffs are truncated in the prompt."""
        review_round = ReviewRound(tmp_path)
        tracker = get_tracker("minimal")

        # Create a large diff (> 50000 chars)
        large_diff = GIT_DIFF_MEDIUM * 1000
        assert len(large_diff) > 50000

        with patch("tools.auto_prd.review_round.git_head_sha", return_value="abc123"):
            prompt = review_round._build_review_prompt(
                tracker=tracker,
                git_diff=large_diff,
                iteration=1,
                base_branch="main",
            )

        # Diff in prompt should be truncated
        diff_start = prompt.find("```diff")
        diff_end = prompt.find("```", diff_start + 10)
        actual_diff_in_prompt = prompt[diff_start:diff_end]
        assert len(actual_diff_in_prompt) <= 50000 + 100  # Allow some margin


# ============================================================================
# Git Diff Handling Tests
# ============================================================================


class TestGitDiffHandling:
    """Tests for git diff retrieval and processing."""

    def test_empty_diff_skips_review(self, tmp_path: Path) -> None:
        """Test that empty git diff results in skipped review."""
        review_round = ReviewRound(tmp_path)
        tracker = get_tracker("minimal")

        with patch.object(review_round, "_get_git_diff", return_value=""):
            result = review_round.execute_review(
                iteration=1,
                tracker=tracker,
                base_branch="main",
            )

        assert result.overall_status == "skipped"
        assert result.tasks_reviewed == 0
        assert "No changes detected" in result.git_diff_summary

    def test_whitespace_only_diff_skips_review(self, tmp_path: Path) -> None:
        """Test that whitespace-only diff results in skipped review."""
        review_round = ReviewRound(tmp_path)
        tracker = get_tracker("minimal")

        with patch.object(review_round, "_get_git_diff", return_value="   \n\n  \t  "):
            result = review_round.execute_review(
                iteration=1,
                tracker=tracker,
                base_branch="main",
            )

        assert result.overall_status == "skipped"

    def test_normal_diff_proceeds_with_review(self, tmp_path: Path) -> None:
        """Test that normal diff proceeds to agent call."""
        review_round = ReviewRound(tmp_path)
        tracker = get_tracker("minimal")

        with patch.object(review_round, "_get_git_diff", return_value=GIT_DIFF_SMALL):
            with patch(
                "tools.auto_prd.review_round.git_head_sha", return_value="abc123"
            ):
                with patch.object(
                    review_round, "_call_review_agent", return_value=REVIEW_SUCCESSFUL
                ):
                    result = review_round.execute_review(
                        iteration=1,
                        tracker=tracker,
                        base_branch="main",
                    )

        assert result.overall_status == "passed"
        assert result.tasks_reviewed == 2


# ============================================================================
# Tracker Update Tests
# ============================================================================


class TestTrackerUpdates:
    """Tests for applying review updates to tracker."""

    def test_status_update_applied_to_task(self, tmp_path: Path) -> None:
        """Test that status updates are applied to tasks."""
        review_round = ReviewRound(tmp_path)
        tracker = get_tracker("with_review")

        result = ReviewResult(
            iteration=2,
            reviewer="claude",
            timestamp="2026-01-25T12:00:00Z",
            overall_status="partial",
            tasks_reviewed=1,
            statuses_updated={"T002": "completed"},
        )

        review_round._apply_review_updates(tracker, result)

        # Check task status was updated
        task = tracker["features"][0]["tasks"][1]
        assert task["id"] == "T002"
        assert task["status"] == "completed"
        assert "completed_at" in task

    def test_review_insight_added_to_task(self, tmp_path: Path) -> None:
        """Test that review insights are added to tasks."""
        review_round = ReviewRound(tmp_path)
        tracker = get_tracker("minimal")

        result = ReviewResult(
            iteration=1,
            reviewer="claude",
            timestamp="2026-01-25T12:00:00Z",
            overall_status="passed",
            tasks_reviewed=1,
            statuses_updated={"T001": "completed"},
        )

        review_round._apply_review_updates(tracker, result)

        # Check review insight was added
        task = tracker["features"][0]["tasks"][0]
        assert "review_insights" in task
        assert len(task["review_insights"]) == 1
        assert task["review_insights"][0]["iteration"] == 1
        assert task["review_insights"][0]["reviewer"] == "claude"

    def test_review_history_added_to_feature(self, tmp_path: Path) -> None:
        """Test that review history is added to features."""
        review_round = ReviewRound(tmp_path)
        tracker = get_tracker("minimal")

        result = ReviewResult(
            iteration=1,
            reviewer="claude",
            timestamp="2026-01-25T12:00:00Z",
            overall_status="passed",
            tasks_reviewed=1,
            statuses_updated={"T001": "completed"},
            insights={"negative": ["Some issue"]},
        )

        review_round._apply_review_updates(tracker, result)

        # Check review history was added
        feature = tracker["features"][0]
        assert "review_history" in feature
        assert len(feature["review_history"]) == 1
        assert feature["review_history"][0]["iteration"] == 1

    def test_top_level_insights_updated(self, tmp_path: Path) -> None:
        """Test that top-level review insights are updated."""
        review_round = ReviewRound(tmp_path)
        tracker = get_tracker("minimal")

        result = ReviewResult(
            iteration=1,
            reviewer="claude",
            timestamp="2026-01-25T12:00:00Z",
            overall_status="passed",
            tasks_reviewed=1,
            statuses_updated={"T001": "completed"},
            insights={
                "patterns": ["Clean code"],
                "negative": ["Missing tests"],
            },
        )

        review_round._apply_review_updates(tracker, result)

        # Check top-level insights
        assert "review_insights" in tracker
        assert tracker["review_insights"]["last_review_iteration"] == 1
        assert "Clean code" in tracker["review_insights"]["common_patterns"]
        assert "Missing tests" in tracker["review_insights"]["recurring_issues"]


# ============================================================================
# Agent Failure Handling Tests
# ============================================================================


class TestAgentFailureHandling:
    """Tests for handling agent execution failures."""

    def test_agent_timeout_returns_failed_result(self, tmp_path: Path) -> None:
        """Test that agent timeout returns a failed result."""
        review_round = ReviewRound(tmp_path)
        tracker = get_tracker("minimal")

        with patch.object(review_round, "_get_git_diff", return_value=GIT_DIFF_SMALL):
            with patch(
                "tools.auto_prd.review_round.git_head_sha", return_value="abc123"
            ):
                with patch.object(
                    review_round,
                    "_call_review_agent",
                    side_effect=TimeoutExpired(["claude"], 300),
                ):
                    result = review_round.execute_review(
                        iteration=1,
                        tracker=tracker,
                        base_branch="main",
                    )

        assert result.overall_status == "failed"
        assert (
            "timeout" in result.git_diff_summary.lower()
            or "failed" in result.git_diff_summary.lower()
        )

    def test_agent_process_error_returns_failed_result(self, tmp_path: Path) -> None:
        """Test that agent process error returns a failed result."""
        review_round = ReviewRound(tmp_path)
        tracker = get_tracker("minimal")

        with patch.object(review_round, "_get_git_diff", return_value=GIT_DIFF_SMALL):
            with patch(
                "tools.auto_prd.review_round.git_head_sha", return_value="abc123"
            ):
                with patch.object(
                    review_round,
                    "_call_review_agent",
                    side_effect=CalledProcessError(1, ["claude"]),
                ):
                    result = review_round.execute_review(
                        iteration=1,
                        tracker=tracker,
                        base_branch="main",
                    )

        assert result.overall_status == "failed"
        assert result.tasks_reviewed == 0


# ============================================================================
# Full Integration Tests
# ============================================================================


class TestFullIntegration:
    """Full integration tests with mocked components."""

    def test_successful_review_flow(self, tmp_path: Path) -> None:
        """Test complete successful review flow."""
        review_round = ReviewRound(tmp_path)
        tracker = get_tracker("minimal")

        with patch.object(review_round, "_get_git_diff", return_value=GIT_DIFF_MEDIUM):
            with patch(
                "tools.auto_prd.review_round.git_head_sha", return_value="abc123"
            ):
                with patch.object(
                    review_round, "_call_review_agent", return_value=REVIEW_SUCCESSFUL
                ):
                    with patch.object(review_round, "_apply_review_updates"):
                        result = review_round.execute_review(
                            iteration=1,
                            tracker=tracker,
                            base_branch="main",
                        )

        assert result.overall_status == "passed"
        assert result.tasks_reviewed == 2
        assert len(result.insights.get("positive", [])) > 0

    def test_partial_review_with_reverts(self, tmp_path: Path) -> None:
        """Test review that results in status reverts."""
        review_round = ReviewRound(tmp_path)
        tracker = get_tracker("with_review")

        with patch.object(review_round, "_get_git_diff", return_value=GIT_DIFF_MEDIUM):
            with patch(
                "tools.auto_prd.review_round.git_head_sha", return_value="abc123"
            ):
                with patch.object(
                    review_round, "_call_review_agent", return_value=REVIEW_PARTIAL
                ):
                    result = review_round.execute_review(
                        iteration=2,
                        tracker=tracker,
                        base_branch="main",
                    )

        assert result.overall_status == "partial"
        assert len(result.statuses_updated) > 0
        # Check that at least one task was reverted
        has_revert = any(
            s in ("pending", "in_progress") for s in result.statuses_updated.values()
        )
        assert has_revert

    def test_failed_review_flow(self, tmp_path: Path) -> None:
        """Test complete failed review flow."""
        review_round = ReviewRound(tmp_path)
        tracker = get_tracker("with_review")

        with patch.object(review_round, "_get_git_diff", return_value=GIT_DIFF_MEDIUM):
            with patch(
                "tools.auto_prd.review_round.git_head_sha", return_value="abc123"
            ):
                with patch.object(
                    review_round, "_call_review_agent", return_value=REVIEW_FAILED
                ):
                    result = review_round.execute_review(
                        iteration=1,
                        tracker=tracker,
                        base_branch="main",
                    )

        assert result.overall_status == "failed"
        assert (
            "critical" in result.summary.lower() or "security" in result.summary.lower()
        )

    def test_review_with_various_json_formats(self, tmp_path: Path) -> None:
        """Test review handles various JSON output formats."""
        review_round = ReviewRound(tmp_path)
        tracker = get_tracker("minimal")

        formats = [
            ("markdown", REVIEW_SUCCESSFUL),
            ("plain", REVIEW_PLAIN_JSON),
            ("prefix", REVIEW_WITH_PREFIX),
        ]

        for format_name, response in formats:
            with patch.object(
                review_round, "_get_git_diff", return_value=GIT_DIFF_SMALL
            ):
                with patch(
                    "tools.auto_prd.review_round.git_head_sha", return_value="abc123"
                ):
                    with patch.object(
                        review_round, "_call_review_agent", return_value=response
                    ):
                        result = review_round.execute_review(
                            iteration=1,
                            tracker=tracker,
                            base_branch="main",
                        )

            assert result.overall_status in (
                "passed",
                "partial",
                "failed",
            ), f"Failed for format: {format_name}"


# ============================================================================
# Fixture Helper Function Tests
# ============================================================================


class TestFixtureHelpers:
    """Tests for fixture helper functions."""

    def test_get_review_response_passed(self) -> None:
        """Test getting passed review response."""
        response = get_review_response("passed")
        assert "passed" in response

    def test_get_review_response_partial(self) -> None:
        """Test getting partial review response."""
        response = get_review_response("partial")
        assert "partial" in response

    def test_get_review_response_failed(self) -> None:
        """Test getting failed review response."""
        response = get_review_response("failed")
        assert "failed" in response

    def test_get_review_response_malformed(self) -> None:
        """Test getting malformed review response."""
        response = get_review_response("malformed", "incomplete")
        assert response is not None

    def test_get_git_diff_various_sizes(self) -> None:
        """Test getting git diff of various sizes."""
        sizes = ["empty", "small", "medium", "large", "comments_only"]
        for size in sizes:
            diff = get_git_diff(size)
            assert isinstance(diff, str)

        empty_diff = get_git_diff("empty")
        assert empty_diff == ""

    def test_get_tracker_various_types(self) -> None:
        """Test getting tracker of various types."""
        tracker = get_tracker("minimal")
        assert "version" in tracker
        assert "features" in tracker

        # Verify it's a copy, not the same object
        tracker2 = get_tracker("minimal")
        assert tracker is not tracker2
        tracker["features"][0]["id"] = "MODIFIED"
        assert tracker2["features"][0]["id"] != "MODIFIED"
