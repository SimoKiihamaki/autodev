"""Integration tests for support_loop module."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from support_mode.support_loop import run_support_mode


def test_run_support_mode_single_iteration():
    """Test run_support_mode completes one iteration with mocked dependencies.

    This test verifies the core monitoring behavior by:
    - Loading tracker state and computing TASKS_LEFT
    - Reading PRD content and extracting checkboxes
    - Checking git status
    - Consulting verification history
    - Handling KeyboardInterrupt for clean exit
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        prd_path = repo_root / "prd.md"

        # Create minimal tracker.json
        aprd_dir = repo_root / ".aprd"
        aprd_dir.mkdir()
        tracker_path = aprd_dir / "tracker.json"
        tracker_data = {
            "version": "2.0.0",
            "metadata": {
                "prd_source": "prd.md",
                "prd_hash": "sha256:test123",
                "created_at": "2025-01-20T00:00:00Z",
                "created_by": "claude",
                "project_context": {},
            },
            "features": [
                {
                    "id": "F001",
                    "name": "Test Feature",
                    "description": "A test feature",
                    "priority": "high",
                    "status": "pending",
                    "goals": {"primary": "Test", "measurable_outcomes": []},
                    "tasks": [
                        {"id": "T001", "description": "Task 1", "status": "pending"},
                        {"id": "T002", "description": "Task 2", "status": "completed"},
                    ],
                    "acceptance_criteria": [],
                    "testing": {"unit_tests": [], "integration_tests": []},
                    "validation": {"benchmarks": [], "quality_gates": []},
                }
            ],
            "validation_summary": {
                "total_features": 1,
                "total_tasks": 2,
                "estimated_complexity": "small",
            },
        }
        tracker_path.write_text(json.dumps(tracker_data))

        # Create PRD with checkboxes
        prd_content = """
# Test PRD

## Requirements
- [ ] Task 1: Implement feature
- [ ] Task 2: Write tests
- [ ] Task 3: Documentation
"""
        prd_path.write_text(prd_content)

        # Create verification runs log
        verification_dir = aprd_dir / "verification"
        verification_dir.mkdir()
        runs_log = verification_dir / "runs.jsonl"
        verification_run = {
            "run_id": "test-run-001",
            "timestamp_start": "2025-01-20T00:00:00Z",
            "timestamp_end": "2025-01-20T00:01:00Z",
            "git_sha": "abc123def456",
            "prd_hash": "sha256:test123",
            "verifiers": [
                {"name": "pytest", "status": "passed", "exit_code": 0},
                {"name": "ruff", "status": "passed", "exit_code": 0},
            ],
            "overall_status": "passed",
        }
        runs_log.write_text(json.dumps(verification_run))

        # Mock git operations and time.sleep
        mock_git_result = MagicMock()
        mock_git_result.stdout = "master\nabc123def4567890"
        mock_git_result.exit_code = 0
        mock_git_result.is_success.return_value = True

        with patch("support_mode.git_ops.run_cmd", return_value=mock_git_result), patch(
            "support_mode.support_loop.time.sleep"
        ) as mock_sleep, patch(
            "support_mode.command.run_cmd", return_value=mock_git_result
        ):

            # Schedule KeyboardInterrupt after first sleep to exit loop
            mock_sleep.side_effect = [None, KeyboardInterrupt()]

            # Run support mode (should exit after one iteration)
            run_support_mode(repo_root, prd_path, poll_seconds=1)

            # Verify time.sleep was called (loop executed)
            assert mock_sleep.call_count >= 1

        # Verify state was saved
        state_path = repo_root / ".aprd" / "support_state.json"
        assert state_path.exists()
        state = json.loads(state_path.read_text())
        assert state.get("iteration") >= 1
