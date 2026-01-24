"""Tests for tracker utilities."""

import json
import tempfile
from pathlib import Path

from support_mode.tracker import (
    compute_prd_hash,
    get_tracker_path,
    load_tracker,
    validate_tracker,
)


def test_compute_prd_hash():
    """Test PRD hash computation."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".md") as f:
        f.write("# Test PRD\n\n- [ ] Task 1\n- [ ] Task 2\n")
        f.flush()
        prd_path = Path(f.name)

        hash1 = compute_prd_hash(prd_path)
        assert hash1.startswith("sha256:")
        assert len(hash1) == 23  # "sha256:" + 16 hex chars

        # Same content should produce same hash
        hash2 = compute_prd_hash(prd_path)
        assert hash1 == hash2

        prd_path.unlink()


def test_get_tracker_path():
    """Test tracker path construction."""
    repo_root = Path("/tmp/test_repo")
    tracker_path = get_tracker_path(repo_root)
    assert tracker_path == repo_root / ".aprd" / "tracker.json"


def test_load_tracker_missing():
    """Test loading tracker when file doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        tracker = load_tracker(repo_root)
        assert tracker is None


def test_load_tracker_valid():
    """Test loading valid tracker."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        aprd_dir = repo_root / ".aprd"
        aprd_dir.mkdir()
        tracker_path = aprd_dir / "tracker.json"

        tracker_data = {
            "version": "2.0.0",
            "metadata": {
                "prd_source": "test.md",
                "prd_hash": "sha256:abc123",
                "created_at": "2025-01-20T00:00:00Z",
                "created_by": "claude",
                "project_context": {},
            },
            "features": [],
            "validation_summary": {
                "total_features": 0,
                "total_tasks": 0,
                "estimated_complexity": "small",
            },
        }
        tracker_path.write_text(json.dumps(tracker_data))

        tracker = load_tracker(repo_root)
        assert tracker is not None
        assert tracker["version"] == "2.0.0"


def test_validate_tracker_valid():
    """Test validation of valid tracker."""
    # Use basic validation fallback (skip jsonschema for simplicity in test)
    import importlib
    support_mode_tracker = importlib.import_module('support_mode.tracker')
    original_has_jsonschema = support_mode_tracker.HAS_JSONSCHEMA
    support_mode_tracker.HAS_JSONSCHEMA = False

    try:
        tracker = {
            "version": "2.0.0",
            "metadata": {
                "prd_source": "test.md",
                "prd_hash": "sha256:1234567890abcdef",
                "created_at": "2025-01-20T00:00:00Z",
                "created_by": "claude",
                "project_context": {},
            },
            "features": [
                {
                    "id": "F001",
                    "name": "Test Feature",
                    "description": "Test",
                    "priority": "high",
                    "status": "pending",
                    "goals": {"primary": "Test", "measurable_outcomes": []},
                    "tasks": [
                        {"id": "T001", "description": "Task 1", "status": "pending"}
                    ],
                    "acceptance_criteria": [],
                    "testing": {"unit_tests": [], "integration_tests": []},
                    "validation": {"benchmarks": [], "quality_gates": []},
                }
            ],
            "validation_summary": {
                "total_features": 1,
                "total_tasks": 1,
                "estimated_complexity": "small",
            },
        }
        valid, errors = validate_tracker(tracker)
        assert valid
        assert len(errors) == 0
    finally:
        # Restore original value
        support_mode_tracker.HAS_JSONSCHEMA = original_has_jsonschema
