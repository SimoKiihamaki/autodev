"""PRD Tracker Generator - Creates detailed JSON tracker from PRD analysis.

This module is the foundational component of the AutoDev agent harness.
It generates a structured implementation tracker from a PRD that serves
as the contract between all subsequent agent invocations.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# jsonschema is optional - we implement fallback validation if not available
try:
    import jsonschema

    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

from .agents import claude_exec, codex_exec
from .logging_utils import logger

TRACKER_VERSION = "2.0.0"
TRACKER_DIR = ".aprd"
TRACKER_FILE = "tracker.json"
MAX_TRACKER_SIZE = 1 * 1024 * 1024  # 1 MB maximum tracker file size

# Retry constants for tracker generation
MAX_TRACKER_GEN_ATTEMPTS = 3
TRACKER_GEN_RETRY_BACKOFF_BASE = 10  # seconds

# Load schema at module level for validation
_SCHEMA_PATH = Path(__file__).parent / "tracker_schema.json"
_TRACKER_SCHEMA: dict[str, Any] | None = None


def _load_schema() -> dict[str, Any]:
    """Load the tracker JSON schema."""
    global _TRACKER_SCHEMA
    if _TRACKER_SCHEMA is None:
        _TRACKER_SCHEMA = json.loads(_SCHEMA_PATH.read_text())
    return _TRACKER_SCHEMA


ANALYSIS_PROMPT = """# PRD Analysis Task

You are an expert software architect analyzing a Product Requirements Document (PRD).
Your task is to create a comprehensive implementation tracker in JSON format.

## Requirements

1. **Feature Extraction**: Break down ALL requirements into discrete features
   - Each feature should be implementable in 1-4 hours
   - Complex requirements should be split into multiple features
   - Identify dependencies between features

2. **Task Breakdown**: For each feature, define specific tasks
   - Tasks should be atomic (completable in 15-60 minutes)
   - Include both implementation and testing tasks

3. **Acceptance Criteria**: Define clear, testable criteria
   - Each criterion must be verifiable
   - Specify the verification method (unit_test, e2e_test, etc.)

4. **Testing Requirements**: Specify required tests
   - Unit tests for individual components
   - Integration tests for component interactions
   - E2E tests for user-facing features

5. **Validation Benchmarks**: Define measurable quality targets
   - Performance targets where applicable
   - Quality gates (type safety, accessibility, coverage)

6. **File Mapping**: Predict files to create/modify
   - Use project conventions from context provided

## Project Context

Language: {language}
Framework: {framework}
Test Framework: {test_framework}
Build System: {build_system}

Existing Structure:
{file_structure}

## PRD Content

{prd_content}

## Output Format

Return ONLY valid JSON matching this structure (no markdown, no explanation):

{{
  "version": "2.0.0",
  "metadata": {{
    "prd_source": "<path>",
    "prd_hash": "<will be filled>",
    "created_at": "<will be filled>",
    "created_by": "<will be filled>",
    "project_context": {{
      "language": "{language}",
      "framework": "{framework}",
      "test_framework": "{test_framework}",
      "build_system": "{build_system}"
    }}
  }},
  "features": [
    {{
      "id": "F001",
      "name": "<short name>",
      "description": "<detailed description>",
      "priority": "critical|high|medium|low",
      "complexity": "S|M|L|XL",
      "status": "pending",
      "dependencies": [],
      "goals": {{
        "primary": "<single sentence goal>",
        "secondary": ["<optional secondary goals>"],
        "measurable_outcomes": ["<specific outcomes>"]
      }},
      "tasks": [
        {{
          "id": "T001",
          "description": "<what to do>",
          "status": "pending"
        }}
      ],
      "acceptance_criteria": [
        {{
          "id": "AC001",
          "criterion": "<testable criterion>",
          "verification_method": "unit_test|integration_test|e2e_test|manual_test|code_review|type_check|lint_check",
          "status": "pending"
        }}
      ],
      "testing": {{
        "unit_tests": [
          {{
            "description": "<what test verifies>",
            "file_path": "<test file path>",
            "status": "pending"
          }}
        ],
        "integration_tests": [
          {{
            "description": "<what test verifies>",
            "components_tested": ["<component1>", "<component2>"],
            "status": "pending"
          }}
        ],
        "e2e_tests": []
      }},
      "validation": {{
        "benchmarks": [
          {{
            "metric": "<what to measure>",
            "target": "<target value>",
            "measurement_method": "<how to measure>"
          }}
        ],
        "quality_gates": [
          {{
            "gate": "<gate name>",
            "requirement": "<what must pass>"
          }}
        ]
      }},
      "files": {{
        "to_create": ["<file paths>"],
        "to_modify": ["<file paths>"]
      }},
      "commits": [],
      "verification_evidence": {{}}
    }}
  ],
  "validation_summary": {{
    "total_features": <count>,
    "total_tasks": <count>,
    "estimated_complexity": "small|medium|large|xlarge",
    "critical_path": ["F001", "F002"]
  }}
}}
"""


def compute_prd_hash(prd_path: Path) -> str:
    """Compute SHA-256 hash of PRD content for change detection."""
    content = prd_path.read_bytes()
    return f"sha256:{hashlib.sha256(content).hexdigest()[:16]}"


def get_tracker_path(repo_root: Path) -> Path:
    """Get path to tracker.json."""
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


def should_regenerate_tracker(
    existing: dict[str, Any] | None, prd_path: Path
) -> tuple[bool, str]:
    """Check if tracker needs regeneration.

    Args:
        existing: Existing tracker dictionary or None
        prd_path: Path to the PRD file

    Returns:
        Tuple of (should_regenerate, reason)
    """
    if existing is None:
        return True, "no_existing_tracker"

    current_hash = compute_prd_hash(prd_path)
    stored_hash = existing.get("metadata", {}).get("prd_hash", "")

    if current_hash != stored_hash:
        return True, "prd_content_changed"

    return False, "tracker_current"


def detect_project_context(repo_root: Path) -> dict[str, str]:
    """Detect project language, framework, etc.

    Args:
        repo_root: Repository root directory

    Returns:
        Dictionary with language, framework, test_framework, build_system
    """
    context = {
        "language": "unknown",
        "framework": "unknown",
        "test_framework": "unknown",
        "build_system": "unknown",
    }

    # Check for package.json (Node/JS/TS)
    pkg_json = repo_root / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text())
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

            context["language"] = "TypeScript" if "typescript" in deps else "JavaScript"

            if "next" in deps:
                context["framework"] = f"Next.js {deps.get('next', '')}"
            elif "react" in deps:
                context["framework"] = f"React {deps.get('react', '')}"
            elif "express" in deps:
                context["framework"] = "Express"
            elif "fastify" in deps:
                context["framework"] = "Fastify"

            if "jest" in deps:
                context["test_framework"] = "Jest"
            if "playwright" in deps or "@playwright/test" in deps:
                if context["test_framework"] != "unknown":
                    context["test_framework"] += " + Playwright"
                else:
                    context["test_framework"] = "Playwright"
            if "vitest" in deps:
                context["test_framework"] = "Vitest"

            if (repo_root / "pnpm-lock.yaml").exists():
                context["build_system"] = "pnpm"
            elif (repo_root / "yarn.lock").exists():
                context["build_system"] = "yarn"
            else:
                context["build_system"] = "npm"
        except (json.JSONDecodeError, OSError):
            pass

    # Check for pyproject.toml (Python)
    pyproject = repo_root / "pyproject.toml"
    if pyproject.exists():
        context["language"] = "Python"
        context["test_framework"] = "pytest"
        if (repo_root / "uv.lock").exists():
            context["build_system"] = "uv"
        elif (repo_root / "poetry.lock").exists():
            context["build_system"] = "poetry"
        else:
            context["build_system"] = "pip"

    # Check for go.mod (Go)
    if (repo_root / "go.mod").exists():
        context["language"] = "Go"
        context["test_framework"] = "go test"
        context["build_system"] = "go"

    # Check for Cargo.toml (Rust)
    if (repo_root / "Cargo.toml").exists():
        context["language"] = "Rust"
        context["test_framework"] = "cargo test"
        context["build_system"] = "cargo"

    return context


def get_file_structure(repo_root: Path, max_depth: int = 3) -> str:
    """Get simplified file structure for context.

    Args:
        repo_root: Repository root directory
        max_depth: Maximum depth to traverse

    Returns:
        Tree-like string representation of file structure
    """
    lines: list[str] = []

    # Directories to skip
    skip_dirs = {
        ".git",
        "node_modules",
        "__pycache__",
        ".next",
        "dist",
        "build",
        ".aprd",
        ".venv",
        "venv",
        ".tox",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "target",  # Rust
        "bin",  # Go
        "pkg",  # Go
    }

    def walk(path: Path, prefix: str = "", depth: int = 0) -> None:
        if depth > max_depth:
            return

        try:
            items = sorted(path.iterdir(), key=lambda x: (x.is_file(), x.name))
        except PermissionError:
            return

        # Filter out non-essential directories
        items = [i for i in items if i.name not in skip_dirs]

        # Slice items first, then compute is_last against the sliced list
        displayed_items = items[:20]
        for i, item in enumerate(displayed_items):  # Limit items per directory
            is_last = i == len(displayed_items) - 1
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{item.name}")

            if item.is_dir() and depth < max_depth:
                extension = "    " if is_last else "│   "
                walk(item, prefix + extension, depth + 1)

    walk(repo_root)
    return "\n".join(lines[:100])  # Limit total lines


def _validate_basic_structure(tracker: dict[str, Any]) -> list[str]:
    """Perform basic structural validation without jsonschema.

    Args:
        tracker: Tracker dictionary to validate

    Returns:
        List of error messages (empty if valid)
    """
    errors: list[str] = []

    # Check version
    if tracker.get("version") != TRACKER_VERSION:
        errors.append(
            f"Invalid version: expected {TRACKER_VERSION}, got {tracker.get('version')}"
        )

    # Check metadata
    metadata = tracker.get("metadata")
    if not isinstance(metadata, dict):
        errors.append("Missing or invalid metadata")
    else:
        for field in ["prd_source", "prd_hash", "created_at", "created_by"]:
            if not metadata.get(field):
                errors.append(f"Missing metadata.{field}")
        # Validate prd_hash format
        prd_hash = metadata.get("prd_hash", "")
        if prd_hash and not re.match(r"^sha256:[a-f0-9]{16,64}$", prd_hash):
            errors.append(f"Invalid prd_hash format: {prd_hash}")
        # Validate created_by
        if metadata.get("created_by") not in ("claude", "codex"):
            errors.append(f"Invalid created_by: {metadata.get('created_by')}")

    # Check features
    features = tracker.get("features")
    if not isinstance(features, list) or len(features) == 0:
        errors.append("features must be a non-empty list")
    else:
        for i, feature in enumerate(features):
            if not isinstance(feature, dict):
                errors.append(f"Feature {i} is not a dictionary")
                continue
            # Check required fields
            for field in [
                "id",
                "name",
                "status",
                "goals",
                "tasks",
                "acceptance_criteria",
            ]:
                if not feature.get(field):
                    errors.append(f"Feature {feature.get('id', i)} missing {field}")
            # Check ID format
            fid = feature.get("id", "")
            if fid and not re.match(r"^F[0-9]{3}$", fid):
                errors.append(f"Invalid feature ID format: {fid}")
            # Check status
            if feature.get("status") not in (
                "pending",
                "in_progress",
                "blocked",
                "completed",
                "verified",
                "failed",
            ):
                errors.append(
                    f"Invalid status for feature {fid}: {feature.get('status')}"
                )

    # Check validation_summary
    summary = tracker.get("validation_summary")
    if not isinstance(summary, dict):
        errors.append("Missing or invalid validation_summary")
    else:
        for field in ["total_features", "total_tasks", "estimated_complexity"]:
            if summary.get(field) is None:
                errors.append(f"Missing validation_summary.{field}")

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

        # Check acceptance criteria IDs
        for criterion in feature.get("acceptance_criteria", []):
            acid = criterion.get("id", "")
            if acid in ac_ids:
                errors.append(
                    f"Duplicate acceptance criterion id: {acid} in feature {fid}"
                )
            else:
                ac_ids.add(acid)

        # Check dependencies reference valid features
        for dep in feature.get("dependencies", []):
            if dep not in feature_ids and dep != fid:
                # Dependency might be to a later feature - check at end
                pass

    # Validate dependencies exist
    for feature in tracker.get("features", []):
        for dep in feature.get("dependencies", []):
            if dep not in feature_ids:
                errors.append(
                    f"Feature {feature.get('id')} depends on non-existent feature {dep}"
                )

    # Validate summary counts
    summary = tracker.get("validation_summary", {})
    actual_features = len(tracker.get("features", []))
    actual_tasks = sum(len(f.get("tasks", [])) for f in tracker.get("features", []))

    if summary.get("total_features") != actual_features:
        errors.append(
            f"validation_summary.total_features ({summary.get('total_features')}) "
            f"doesn't match actual feature count ({actual_features})"
        )

    if summary.get("total_tasks") != actual_tasks:
        errors.append(
            f"validation_summary.total_tasks ({summary.get('total_tasks')}) "
            f"doesn't match actual task count ({actual_tasks})"
        )

    return len(errors) == 0, errors


def _extract_json_from_response(response: str) -> str:
    """Extract JSON from agent response, handling markdown code blocks.

    Args:
        response: Raw response from agent

    Returns:
        Extracted JSON string

    Raises:
        ValueError: If response is empty or contains no JSON
    """
    text = response.strip()

    # Validate input - empty response is a clear error
    if not text:
        raise ValueError("Empty response from agent - cannot extract JSON")

    # Try to find JSON in markdown code block
    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        if end > start:
            text = text[start:end].strip()
    elif "```" in text:
        start = text.find("```") + 3
        end = text.find("```", start)
        if end > start:
            text = text[start:end].strip()

    # Find the actual JSON object
    brace_start = text.find("{")
    if brace_start < 0:
        # Log preview of what we received for debugging
        preview = text[:200] + "..." if len(text) > 200 else text
        raise ValueError(
            f"No JSON object found in response. Response preview: {preview}"
        )

    # Find matching closing brace
    depth = 0
    for i, char in enumerate(text[brace_start:], start=brace_start):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[brace_start : i + 1]

    # Unbalanced braces - incomplete output
    raise ValueError("Unbalanced braces in JSON response - incomplete output")


def generate_tracker(
    prd_path: Path,
    repo_root: Path,
    executor: str = "claude",
    force: bool = False,
    dry_run: bool = False,
    allow_unsafe_execution: bool = True,
) -> dict[str, Any]:
    """Generate tracker from PRD using Claude/Codex.

    Args:
        prd_path: Path to the PRD markdown file
        repo_root: Repository root directory
        executor: Which agent to use ("claude" or "codex")
        force: Regenerate even if current tracker exists
        dry_run: If True, skip actual agent execution
        allow_unsafe_execution: Allow unsafe execution mode

    Returns:
        The generated/loaded tracker dictionary

    Raises:
        ValueError: If tracker generation or validation fails
        FileNotFoundError: If PRD file doesn't exist
    """
    if not prd_path.exists():
        raise FileNotFoundError(f"PRD file not found: {prd_path}")

    # Check for existing tracker
    existing = load_tracker(repo_root)
    should_regen, reason = should_regenerate_tracker(existing, prd_path)

    if not should_regen and not force:
        logger.info("Using existing tracker (reason: %s)", reason)
        return existing  # type: ignore[return-value]

    logger.info("Generating tracker (reason: %s)", reason)

    # Gather context
    prd_content = prd_path.read_text()
    context = detect_project_context(repo_root)
    file_structure = get_file_structure(repo_root)

    # Build prompt
    prompt = ANALYSIS_PROMPT.format(
        language=context["language"],
        framework=context["framework"],
        test_framework=context["test_framework"],
        build_system=context["build_system"],
        file_structure=file_structure,
        prd_content=prd_content,
    )

    if dry_run:
        logger.info("Dry run enabled; returning mock tracker")
        # Return a minimal valid tracker for dry run
        tracker: dict[str, Any] = {
            "version": TRACKER_VERSION,
            "metadata": {
                "prd_source": str(prd_path),
                "prd_hash": compute_prd_hash(prd_path),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "created_by": executor,
                "project_context": context,
            },
            "features": [
                {
                    "id": "F001",
                    "name": "Dry Run Feature",
                    "description": "Placeholder feature for dry run",
                    "priority": "medium",
                    "complexity": "S",
                    "status": "pending",
                    "dependencies": [],
                    "goals": {
                        "primary": "Demonstrate dry run functionality",
                        "secondary": [],
                        "measurable_outcomes": ["Tracker validates successfully"],
                    },
                    "tasks": [
                        {
                            "id": "T001",
                            "description": "Implement the feature",
                            "status": "pending",
                        }
                    ],
                    "acceptance_criteria": [
                        {
                            "id": "AC001",
                            "criterion": "Feature works as expected",
                            "verification_method": "manual_test",
                            "status": "pending",
                        }
                    ],
                    "testing": {
                        "unit_tests": [],
                        "integration_tests": [],
                    },
                    "validation": {
                        "benchmarks": [],
                        "quality_gates": [],
                    },
                    "files": {
                        "to_create": [],
                        "to_modify": [],
                    },
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
        return tracker

    # Call agent with retry logic
    logger.info("Sending PRD to %s for analysis...", executor)

    # Initialize result variables before retry loop to avoid UnboundLocalError
    # if an unexpected exception type bypasses the normal assignment path
    result = ""
    stderr = ""
    for attempt in range(MAX_TRACKER_GEN_ATTEMPTS):
        try:
            if executor == "codex":
                result, stderr = codex_exec(
                    prompt=prompt,
                    repo_root=repo_root,
                    allow_unsafe_execution=allow_unsafe_execution,
                )
            else:
                result, stderr = claude_exec(
                    prompt=prompt,
                    repo_root=repo_root,
                    allow_unsafe_execution=allow_unsafe_execution,
                )

            # Validate response before proceeding
            if not result or not result.strip():
                raise ValueError(f"Empty response from {executor}")

            # If we get here, we have a non-empty response - break retry loop
            break

        except (
            ValueError,
            RuntimeError,
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
        ) as e:
            if attempt < MAX_TRACKER_GEN_ATTEMPTS - 1:
                wait_time = TRACKER_GEN_RETRY_BACKOFF_BASE * (2**attempt)
                logger.warning(
                    "Tracker generation attempt %d/%d failed: %s. Retrying in %ds...",
                    attempt + 1,
                    MAX_TRACKER_GEN_ATTEMPTS,
                    e,
                    wait_time,
                )
                time.sleep(wait_time)
            else:
                logger.error(
                    "Tracker generation failed after %d attempts: %s",
                    MAX_TRACKER_GEN_ATTEMPTS,
                    e,
                )
                raise

    # Extract and parse JSON from response
    try:
        json_str = _extract_json_from_response(result)
    except ValueError:
        # Log stderr preview when JSON extraction fails on non-empty output
        # (helps diagnose cases where agent wrote an error message instead of JSON)
        if stderr.strip():
            logger.warning(
                "JSON extraction failed. Stderr preview: %s",
                stderr[:500] if len(stderr) > 500 else stderr,
            )
        raise

    try:
        tracker = json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse tracker JSON: %s", e)
        logger.debug("Raw response: %s", result[:1000])
        raise ValueError(f"Agent returned invalid JSON: {e}") from e

    # Inject/update metadata
    tracker["version"] = TRACKER_VERSION
    if "metadata" not in tracker:
        tracker["metadata"] = {}
    tracker["metadata"]["prd_source"] = str(prd_path)
    tracker["metadata"]["prd_hash"] = compute_prd_hash(prd_path)
    tracker["metadata"]["created_at"] = datetime.now(timezone.utc).isoformat()
    tracker["metadata"]["created_by"] = executor
    if "project_context" not in tracker["metadata"]:
        tracker["metadata"]["project_context"] = context

    # Validate
    valid, errors = validate_tracker(tracker)
    if not valid:
        logger.error("Tracker validation failed: %s", errors)
        raise ValueError(f"Tracker validation failed: {errors}")

    # Save tracker
    tracker_path = get_tracker_path(repo_root)
    tracker_path.parent.mkdir(parents=True, exist_ok=True)
    tracker_path.write_text(json.dumps(tracker, indent=2))

    logger.info(
        "Tracker generated: %d features, %d total tasks",
        tracker["validation_summary"]["total_features"],
        tracker["validation_summary"]["total_tasks"],
    )

    return tracker


def save_tracker(tracker: dict[str, Any], repo_root: Path) -> None:
    """Save tracker to disk.

    Args:
        tracker: Tracker dictionary to save
        repo_root: Repository root directory
    """
    tracker_path = get_tracker_path(repo_root)
    tracker_path.parent.mkdir(parents=True, exist_ok=True)
    tracker_path.write_text(json.dumps(tracker, indent=2))
    logger.debug("Tracker saved to %s", tracker_path)


def get_next_feature(tracker: dict[str, Any]) -> dict[str, Any] | None:
    """Get the next feature to implement based on dependencies and priority.

    Args:
        tracker: Tracker dictionary

    Returns:
        Next feature to implement, or None if all complete
    """
    features = tracker.get("features", [])

    # Get set of completed/verified feature IDs
    completed = {
        f["id"] for f in features if f.get("status") in ("completed", "verified")
    }

    # Find features with all dependencies met
    available = []
    for feature in features:
        if feature.get("status") in ("pending", "blocked"):
            deps = set(feature.get("dependencies", []))
            if deps.issubset(completed):
                available.append(feature)

    if not available:
        # Check if there's an in-progress feature
        for feature in features:
            if feature.get("status") == "in_progress":
                return feature
        return None

    # Sort by priority (critical > high > medium > low)
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    available.sort(key=lambda f: priority_order.get(f.get("priority", "low"), 3))

    return available[0]


def update_feature_status(
    tracker: dict[str, Any],
    feature_id: str,
    status: str,
    repo_root: Path,
) -> None:
    """Update a feature's status and save the tracker.

    Args:
        tracker: Tracker dictionary
        feature_id: ID of feature to update
        status: New status value
        repo_root: Repository root directory
    """
    for feature in tracker.get("features", []):
        if feature.get("id") == feature_id:
            feature["status"] = status
            save_tracker(tracker, repo_root)
            logger.info("Updated feature %s status to %s", feature_id, status)
            return

    logger.warning("Feature %s not found in tracker", feature_id)


def update_task_status(
    tracker: dict[str, Any],
    feature_id: str,
    task_id: str,
    status: str,
    repo_root: Path,
) -> None:
    """Update a task's status and save the tracker.

    Args:
        tracker: Tracker dictionary
        feature_id: ID of parent feature
        task_id: ID of task to update
        status: New status value
        repo_root: Repository root directory
    """
    for feature in tracker.get("features", []):
        if feature.get("id") == feature_id:
            for task in feature.get("tasks", []):
                if task.get("id") == task_id:
                    task["status"] = status
                    if status == "completed":
                        task["completed_at"] = datetime.now(timezone.utc).isoformat()
                    save_tracker(tracker, repo_root)
                    logger.info(
                        "Updated task %s/%s status to %s", feature_id, task_id, status
                    )
                    return
            logger.warning("Task %s not found in feature %s", task_id, feature_id)
            return

    logger.warning("Feature %s not found in tracker", feature_id)
