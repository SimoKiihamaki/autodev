"""Tracker loading and validation utilities."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

# Optional jsonschema import
try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

logger = logging.getLogger(__name__)

TRACKER_DIR = ".aprd"
TRACKER_FILE = "tracker.json"
MAX_TRACKER_SIZE = 1 * 1024 * 1024  # 1 MB


def compute_prd_hash(prd_path: Path) -> str:
    """Compute SHA-256 hash of PRD content for change detection.

    Args:
        prd_path: Path to PRD file.

    Returns:
        SHA-256 hash prefix (16 hex chars) with "sha256:" prefix.
    """
    content = prd_path.read_bytes()
    return f"sha256:{hashlib.sha256(content).hexdigest()[:16]}"


def get_tracker_path(repo_root: Path) -> Path:
    """Get path to tracker.json.

    Args:
        repo_root: Repository root directory.

    Returns:
        Path to tracker.json file.
    """
    return repo_root / TRACKER_DIR / TRACKER_FILE


def load_tracker(repo_root: Path) -> dict[str, Any] | None:
    """Load existing tracker if present.

    Args:
        repo_root: Repository root directory

    Returns:
        Tracker dictionary or None if not found/invalid/too large
    """
    tracker_path = get_tracker_path(repo_root)
    if not tracker_path.exists():
        return None

    try:
        # Check file size before reading to guard against overly large files
        file_size = tracker_path.stat().st_size
        if file_size > MAX_TRACKER_SIZE:
            logger.warning(
                "Tracker file too large (%d bytes, max %d bytes): %s",
                file_size,
                MAX_TRACKER_SIZE,
                tracker_path,
            )
            return None
        return json.loads(tracker_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load tracker: %s", e)
        return None


def _load_schema() -> dict[str, Any]:
    """Load tracker JSON schema from package data.

    Returns:
        Schema dictionary.
    """
    import importlib.resources as resources

    schema_bytes = resources.files(__package__).joinpath("tracker_schema.json").read_bytes()
    return json.loads(schema_bytes)


def _validate_basic_structure(tracker: dict[str, Any]) -> list[str]:
    """Basic fallback validation when jsonschema is not available.

    Args:
        tracker: Tracker dictionary to validate.

    Returns:
        List of error messages (empty if valid).
    """
    errors: list[str] = []

    # Check required top-level fields
    for field in ["version", "metadata", "features", "validation_summary"]:
        if field not in tracker:
            errors.append(f"Missing required field: {field}")

    # Check metadata fields
    if "metadata" in tracker:
        metadata = tracker["metadata"]
        if not isinstance(metadata, dict):
            errors.append("metadata must be an object")
        else:
            for meta_field in ["prd_source", "prd_hash", "created_at", "created_by", "project_context"]:
                if meta_field not in metadata:
                    errors.append(f"Missing metadata field: {meta_field}")

    # Check features array
    if "features" in tracker:
        if not isinstance(tracker["features"], list):
            errors.append("features must be an array")
        elif len(tracker["features"]) == 0:
            errors.append("features must have at least one item")

    # Check validation_summary
    if "validation_summary" in tracker:
        if not isinstance(tracker["validation_summary"], dict):
            errors.append("validation_summary must be an object")
        else:
            for summary_field in ["total_features", "total_tasks", "estimated_complexity"]:
                if summary_field not in tracker["validation_summary"]:
                    errors.append(f"Missing validation_summary field: {summary_field}")

    return errors


def validate_tracker(tracker: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate tracker structure against JSON schema.

    Args:
        tracker: Tracker dictionary to validate

    Returns:
        Tuple of (is_valid, error_messages)
    """
    errors: list[str] = []

    # JSON Schema validation (if available)
    if HAS_JSONSCHEMA:
        try:
            schema = _load_schema()
            jsonschema.validate(instance=tracker, schema=schema)
        except jsonschema.ValidationError as e:
            errors.append(f"Schema validation failed: {e.message}")
            return False, errors
        except jsonschema.SchemaError as e:
            errors.append(f"Invalid schema: {e.message}")
            return False, errors
    else:
        # Fallback to basic validation
        basic_errors = _validate_basic_structure(tracker)
        if basic_errors:
            errors.extend(basic_errors)
            return False, errors

    # Additional semantic validation
    feature_ids: set[str] = set()
    task_ids: set[str] = set()
    ac_ids: set[str] = set()

    for feature in tracker.get("features", []):
        fid = feature.get("id", "")

        # Check for duplicate feature IDs
        if fid in feature_ids:
            errors.append(f"Duplicate feature id: {fid}")
        else:
            feature_ids.add(fid)

        # Check task IDs within feature
        for task in feature.get("tasks", []):
            tid = task.get("id", "")
            if tid in task_ids:
                errors.append(f"Duplicate task id: {tid} in feature {fid}")
            else:
                task_ids.add(tid)

        # Check acceptance criteria IDs within feature
        for ac in feature.get("acceptance_criteria", []):
            ac_id = ac.get("id", "")
            if ac_id in ac_ids:
                errors.append(f"Duplicate acceptance criterion id: {ac_id} in feature {fid}")
            else:
                ac_ids.add(ac_id)

    # Validate validation_summary counts
    if "validation_summary" in tracker:
        vs = tracker["validation_summary"]
        total_features = vs.get("total_features", 0)
        total_tasks = vs.get("total_tasks", 0)

        if total_features != len(feature_ids):
            errors.append(
                f"validation_summary.total_features ({total_features}) != actual features ({len(feature_ids)})"
            )

        if total_tasks != len(task_ids):
            errors.append(
                f"validation_summary.total_tasks ({total_tasks}) != actual tasks ({len(task_ids)})"
            )

    return len(errors) == 0, errors
