"""Tests for tracker_generator module edge cases."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from auto_prd.tracker_generator import (
    TRACKER_VERSION,
    _extract_json_from_response,
    generate_tracker,
)


class TestExtractJsonFromResponse:
    """Tests for _extract_json_from_response function."""

    def test_empty_response_raises_value_error(self):
        """Empty string should raise ValueError."""
        with pytest.raises(ValueError, match="Empty response"):
            _extract_json_from_response("")

    def test_whitespace_only_raises_value_error(self):
        """Whitespace-only string should raise ValueError."""
        with pytest.raises(ValueError, match="Empty response"):
            _extract_json_from_response("   \n\t  ")

    def test_no_json_object_raises_value_error(self):
        """Response without JSON object should raise ValueError."""
        with pytest.raises(ValueError, match="No JSON object"):
            _extract_json_from_response("Error: rate limit exceeded")

    def test_unbalanced_braces_raises_value_error(self):
        """Truncated JSON should raise ValueError."""
        with pytest.raises(ValueError, match="Unbalanced braces"):
            _extract_json_from_response('{"version": "2.0.0", "features": [')

    def test_valid_json_extracted(self):
        """Valid JSON should be extracted correctly."""
        response = '{"version": "2.0.0"}'
        result = _extract_json_from_response(response)
        assert result == '{"version": "2.0.0"}'

    def test_json_in_markdown_code_block(self):
        """JSON in markdown code block should be extracted."""
        response = """Here is the tracker:
```json
{"version": "2.0.0"}
```
"""
        result = _extract_json_from_response(response)
        assert result == '{"version": "2.0.0"}'

    def test_json_with_surrounding_text(self):
        """JSON with surrounding text should be extracted."""
        response = 'Here is the output: {"version": "2.0.0"} End of output.'
        result = _extract_json_from_response(response)
        assert result == '{"version": "2.0.0"}'

    def test_nested_json_extracted_correctly(self):
        """Nested JSON objects should be extracted correctly."""
        response = '{"outer": {"inner": "value"}}'
        result = _extract_json_from_response(response)
        assert result == '{"outer": {"inner": "value"}}'

    def test_json_with_array_in_object(self):
        """JSON with arrays should be extracted correctly."""
        response = '{"items": [1, 2, 3]}'
        result = _extract_json_from_response(response)
        assert result == '{"items": [1, 2, 3]}'

    def test_json_in_generic_code_block(self):
        """JSON in generic code block (without json marker) should be extracted."""
        response = """Here is the tracker:
```
{"version": "2.0.0"}
```
"""
        result = _extract_json_from_response(response)
        assert result == '{"version": "2.0.0"}'


class TestGenerateTrackerRetry:
    """Tests for generate_tracker retry behavior."""

    @patch("auto_prd.tracker_generator.codex_exec")
    @patch("auto_prd.tracker_generator.time.sleep")
    def test_retries_on_empty_response(
        self,
        mock_sleep: MagicMock,
        mock_codex: MagicMock,
        tmp_path: Path,
    ):
        """Should retry when agent returns empty response."""
        prd_path = tmp_path / "test.md"
        prd_path.write_text("# Test PRD\n\n- [ ] Task 1")

        # First two calls return empty, third succeeds
        valid_tracker = {
            "version": TRACKER_VERSION,
            "metadata": {
                "prd_source": str(prd_path),
                "prd_hash": "sha256:abc123def456",
                "created_at": "2024-01-01T00:00:00Z",
                "created_by": "codex",
            },
            "features": [
                {
                    "id": "F001",
                    "name": "Test",
                    "description": "Test feature",
                    "priority": "medium",
                    "complexity": "S",
                    "status": "pending",
                    "dependencies": [],
                    "goals": {
                        "primary": "Test",
                        "secondary": [],
                        "measurable_outcomes": [],
                    },
                    "tasks": [
                        {"id": "T001", "description": "Test", "status": "pending"}
                    ],
                    "acceptance_criteria": [
                        {
                            "id": "AC001",
                            "criterion": "Test passes",
                            "verification_method": "unit_test",
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

        mock_codex.side_effect = ["", "", json.dumps(valid_tracker)]

        result = generate_tracker(
            prd_path=prd_path,
            repo_root=tmp_path,
            executor="codex",
            allow_unsafe_execution=True,
        )

        assert mock_codex.call_count == 3
        assert result["version"] == TRACKER_VERSION
        # Verify backoff sleep was called twice (after attempts 1 and 2)
        assert mock_sleep.call_count == 2

    @patch("auto_prd.tracker_generator.codex_exec")
    @patch("auto_prd.tracker_generator.time.sleep")
    def test_fails_after_max_retries(
        self,
        mock_sleep: MagicMock,
        mock_codex: MagicMock,
        tmp_path: Path,
    ):
        """Should fail after exhausting retries."""
        prd_path = tmp_path / "test.md"
        prd_path.write_text("# Test PRD")

        mock_codex.return_value = ""  # Always empty

        with pytest.raises(ValueError, match="[Ee]mpty response"):
            generate_tracker(
                prd_path=prd_path,
                repo_root=tmp_path,
                executor="codex",
                allow_unsafe_execution=True,
            )

        assert mock_codex.call_count == 3  # MAX_TRACKER_GEN_ATTEMPTS

    @patch("auto_prd.tracker_generator.claude_exec")
    @patch("auto_prd.tracker_generator.time.sleep")
    def test_retries_with_claude_executor(
        self,
        mock_sleep: MagicMock,
        mock_claude: MagicMock,
        tmp_path: Path,
    ):
        """Should retry with claude executor the same way as codex."""
        prd_path = tmp_path / "test.md"
        prd_path.write_text("# Test PRD\n\n- [ ] Task 1")

        valid_tracker = {
            "version": TRACKER_VERSION,
            "metadata": {
                "prd_source": str(prd_path),
                "prd_hash": "sha256:abc123def456",
                "created_at": "2024-01-01T00:00:00Z",
                "created_by": "claude",
            },
            "features": [
                {
                    "id": "F001",
                    "name": "Test",
                    "description": "Test feature",
                    "priority": "medium",
                    "complexity": "S",
                    "status": "pending",
                    "dependencies": [],
                    "goals": {
                        "primary": "Test",
                        "secondary": [],
                        "measurable_outcomes": [],
                    },
                    "tasks": [
                        {"id": "T001", "description": "Test", "status": "pending"}
                    ],
                    "acceptance_criteria": [
                        {
                            "id": "AC001",
                            "criterion": "Test passes",
                            "verification_method": "unit_test",
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

        # First call empty, second succeeds
        mock_claude.side_effect = ["", json.dumps(valid_tracker)]

        result = generate_tracker(
            prd_path=prd_path,
            repo_root=tmp_path,
            executor="claude",
            allow_unsafe_execution=True,
        )

        assert mock_claude.call_count == 2
        assert result["version"] == TRACKER_VERSION

    @patch("auto_prd.tracker_generator.codex_exec")
    @patch("auto_prd.tracker_generator.time.sleep")
    def test_exponential_backoff_timing(
        self,
        mock_sleep: MagicMock,
        mock_codex: MagicMock,
        tmp_path: Path,
    ):
        """Should use exponential backoff with base of 10 seconds."""
        prd_path = tmp_path / "test.md"
        prd_path.write_text("# Test PRD")

        mock_codex.return_value = ""  # Always empty

        with pytest.raises(ValueError):
            generate_tracker(
                prd_path=prd_path,
                repo_root=tmp_path,
                executor="codex",
                allow_unsafe_execution=True,
            )

        # Check backoff values: 10 * 2^0 = 10, 10 * 2^1 = 20
        sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
        assert sleep_calls == [10, 20]


class TestGenerateTrackerDryRun:
    """Tests for generate_tracker dry run behavior."""

    def test_dry_run_returns_valid_tracker(self, tmp_path: Path):
        """Dry run should return a minimal valid tracker."""
        prd_path = tmp_path / "test.md"
        prd_path.write_text("# Test PRD")

        result = generate_tracker(
            prd_path=prd_path,
            repo_root=tmp_path,
            executor="codex",
            dry_run=True,
            allow_unsafe_execution=True,
        )

        assert result["version"] == TRACKER_VERSION
        assert len(result["features"]) == 1
        assert result["features"][0]["id"] == "F001"
        assert result["validation_summary"]["total_features"] == 1

    def test_dry_run_does_not_call_agent(self, tmp_path: Path):
        """Dry run should not call agent executors."""
        prd_path = tmp_path / "test.md"
        prd_path.write_text("# Test PRD")

        with patch("auto_prd.tracker_generator.codex_exec") as mock_codex:
            with patch("auto_prd.tracker_generator.claude_exec") as mock_claude:
                generate_tracker(
                    prd_path=prd_path,
                    repo_root=tmp_path,
                    executor="codex",
                    dry_run=True,
                    allow_unsafe_execution=True,
                )

                mock_codex.assert_not_called()
                mock_claude.assert_not_called()


class TestGenerateTrackerJsonParsing:
    """Tests for JSON parsing in generate_tracker."""

    @patch("auto_prd.tracker_generator.codex_exec")
    @patch("auto_prd.tracker_generator.time.sleep")
    def test_retries_on_invalid_json(
        self,
        mock_sleep: MagicMock,
        mock_codex: MagicMock,
        tmp_path: Path,
    ):
        """Should not retry on invalid JSON (only empty response triggers retry)."""
        prd_path = tmp_path / "test.md"
        prd_path.write_text("# Test PRD")

        # Return text that has JSON but is malformed
        mock_codex.return_value = '{"version": "2.0.0"'  # Missing closing brace

        with pytest.raises(ValueError, match="Unbalanced braces"):
            generate_tracker(
                prd_path=prd_path,
                repo_root=tmp_path,
                executor="codex",
                allow_unsafe_execution=True,
            )

        # Should only be called once since invalid JSON is not the same as empty response
        assert mock_codex.call_count == 1
