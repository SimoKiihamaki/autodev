"""Guardrails and signs system for Ralph-style autonomous iteration.

This module implements the "signs" pattern from Ralph, where mistakes are recorded
as "signs" so they never happen twice. When something breaks, a sign is added. The
next iteration reads signs first to prevent recurring issues.

Key concepts:
- Signs: Learned patterns from mistakes that should be avoided
- Guardrails: Collection of signs for a repository
- Integration: Signs are injected into agent context via system_prompt_suffix

Storage:
- Guardrails are stored under ~/.config/aprd/guardrails/<repo_slug>.md
- Each repository has its own guardrails file
- Signs persist across sessions for continuous learning
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .logging_utils import logger


@dataclass
class Sign:
    """A sign represents a learned pattern from a mistake.

    Signs are created when errors occur during execution. They capture:
    - What triggered the mistake
    - What instruction should prevent it
    - When it was added (iteration number and timestamp)
    - What file/context was involved

    Attributes:
        name: Short identifier for the sign (snake_case)
        trigger: Description of what triggers this mistake
        instruction: What to do to avoid the mistake
        added_iteration: Iteration number when this sign was created
        file_context: Optional file path where issue occurred
        added_at: ISO timestamp when sign was added
        category: Optional category (import, migration, schema, api, etc.)
        phase: Phase where issue was detected (local, pr, review_fix)
    """

    name: str
    trigger: str
    instruction: str
    added_iteration: int
    file_context: str | None = None
    added_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    category: str | None = None
    phase: str | None = None

    def to_markdown(self) -> str:
        """Convert sign to markdown format for guardrails file.

        Returns:
            Markdown formatted sign entry.
        """
        lines = [
            f"## sign: {self.name}",
            f"- **Trigger**: {self.trigger}",
            f"- **Instruction**: {self.instruction}",
            f"- **Added**: Iteration {self.added_iteration}",
        ]
        if self.file_context:
            lines.append(f"- **File**: {self.file_context}")
        if self.category:
            lines.append(f"- **Category**: {self.category}")
        if self.phase:
            lines.append(f"- **Phase**: {self.phase}")
        lines.append(f"- **Timestamp**: {self.added_at}")
        return "\n".join(lines)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Sign:
        """Create Sign from dictionary (loaded from JSON/structured storage).

        Args:
            data: Dictionary with sign attributes.

        Returns:
            Sign instance.
        """
        return cls(
            name=data.get("name", ""),
            trigger=data.get("trigger", ""),
            instruction=data.get("instruction", ""),
            added_iteration=data.get("added_iteration", 1),
            file_context=data.get("file_context"),
            added_at=data.get("added_at", datetime.now(timezone.utc).isoformat()),
            category=data.get("category"),
            phase=data.get("phase"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert Sign to dictionary for JSON serialization.

        Returns:
            Dictionary representation.
        """
        return {
            "name": self.name,
            "trigger": self.trigger,
            "instruction": self.instruction,
            "added_iteration": self.added_iteration,
            "file_context": self.file_context,
            "added_at": self.added_at,
            "category": self.category,
            "phase": self.phase,
        }


def _get_guardrails_dir() -> Path:
    """Get the guardrails directory under XDG config.

    Returns:
        Path to guardrails directory (~/.config/aprd/guardrails).
    """
    xdg_config = os.getenv("XDG_CONFIG_HOME", None)
    if xdg_config and xdg_config.strip():
        base_config = Path(xdg_config).expanduser()
    else:
        base_config = Path.home() / ".config"
    return base_config / "aprd" / "guardrails"


def _get_repo_slug(repo_root: Path) -> str:
    """Generate a slug for the repository from its path.

    Args:
        repo_root: Repository root directory.

    Returns:
        Slug string (e.g., "username_reponame" or "reponame").
    """
    # Try to get owner/repo from git config
    try:
        from .git_ops import parse_owner_repo_from_git

        owner_repo = parse_owner_repo_from_git()
        if owner_repo:
            # owner_repo is "owner/repo" format
            return owner_repo.replace("/", "_").replace("-", "_")
    except Exception:
        pass  # Fall back to directory name

    # Fallback to directory name
    return repo_root.name.replace("-", "_")


def get_guardrails_path(repo_root: Path) -> Path:
    """Get the path to the guardrails file for a repository.

    Note: This function does not create the directory. Callers that need
    to write should use guardrails_dir.mkdir(parents=True, exist_ok=True)
    before writing, or use add_sign() which handles directory creation.

    Args:
        repo_root: Repository root directory.

    Returns:
        Path to guardrails file.
    """
    guardrails_dir = _get_guardrails_dir()
    repo_slug = _get_repo_slug(repo_root)
    return guardrails_dir / f"{repo_slug}.md"


def load_guardrails(repo_root: Path) -> list[Sign]:
    """Load all signs for a repository.

    Args:
        repo_root: Repository root directory.

    Returns:
        List of Sign objects (empty list if file doesn't exist).
    """
    guardrails_path = get_guardrails_path(repo_root)
    if not guardrails_path.exists():
        return []

    signs = []
    try:
        content = guardrails_path.read_text(encoding="utf-8")
        # Parse markdown format
        # Expected format:
        # ## sign: name
        # - **Trigger**: ...
        # - **Instruction**: ...
        # ...
        current_sign: dict[str, Any] = {}
        current_trigger = ""
        current_instruction = ""

        for line in content.split("\n"):
            line = line.rstrip()
            if line.startswith("## sign: "):
                # Save previous sign if exists
                if current_sign:
                    signs.append(
                        Sign(
                            name=current_sign.get("name", "unknown"),
                            trigger=current_sign.get("trigger", ""),
                            instruction=current_sign.get("instruction", ""),
                            added_iteration=current_sign.get("added_iteration", 1),
                            file_context=current_sign.get("file_context"),
                            added_at=current_sign.get(
                                "added_at",
                                datetime.now(timezone.utc).isoformat(),
                            ),
                            category=current_sign.get("category"),
                            phase=current_sign.get("phase"),
                        )
                    )
                # Start new sign
                sign_name = line[len("## sign: ") :].strip()
                current_sign = {"name": sign_name}
            elif "- **Trigger**:" in line or "- **Trigger** :" in line:
                current_trigger = line.split(":", 1)[1].strip() if ":" in line else ""
                current_sign["trigger"] = current_trigger
            elif "- **Instruction**:" in line or "- **Instruction** :" in line:
                current_instruction = (
                    line.split(":", 1)[1].strip() if ":" in line else ""
                )
                current_sign["instruction"] = current_instruction
            elif "- **Added**:" in line or "- **Added** :" in line:
                # Parse "Iteration N"
                added = line.split(":", 1)[1].strip() if ":" in line else ""
                # Extract iteration number from patterns like "Iteration 2" or just a number
                match = re.search(r"Iteration\s+(\d+)|^\s*(\d+)", added, re.IGNORECASE)
                current_sign["added_iteration"] = (
                    int(match.group(1) or match.group(2)) if match else 1
                )
            elif "- **File**:" in line or "- **File** :" in line:
                file_ctx = line.split(":", 1)[1].strip() if ":" in line else ""
                current_sign["file_context"] = file_ctx
            elif "- **Category**:" in line or "- **Category** :" in line:
                category = line.split(":", 1)[1].strip() if ":" in line else ""
                current_sign["category"] = category
            elif "- **Phase**:" in line or "- **Phase** :" in line:
                phase = line.split(":", 1)[1].strip() if ":" in line else ""
                current_sign["phase"] = phase
            elif "- **Timestamp**:" in line or "- **Timestamp** :" in line:
                timestamp = line.split(":", 1)[1].strip() if ":" in line else ""
                current_sign["added_at"] = timestamp

        # Save last sign
        if current_sign:
            signs.append(
                Sign(
                    name=current_sign.get("name", "unknown"),
                    trigger=current_sign.get("trigger", ""),
                    instruction=current_sign.get("instruction", ""),
                    added_iteration=current_sign.get("added_iteration", 1),
                    file_context=current_sign.get("file_context"),
                    added_at=current_sign.get(
                        "added_at", datetime.now(timezone.utc).isoformat()
                    ),
                    category=current_sign.get("category"),
                    phase=current_sign.get("phase"),
                )
            )

    except OSError as e:
        logger.warning("Failed to load guardrails from %s: %s", guardrails_path, e)

    return signs


def add_sign(
    name: str,
    trigger: str,
    instruction: str,
    iteration: int,
    repo_root: Path,
    file_context: str | None = None,
    category: str | None = None,
    phase: str | None = None,
) -> Sign:
    """Add a new sign to guardrails after detecting a mistake pattern.

    Args:
        name: Short identifier for the sign (snake_case recommended).
        trigger: Description of what triggers this mistake.
        instruction: What to do to avoid the mistake.
        iteration: Current iteration number.
        repo_root: Repository root directory.
        file_context: Optional file path where issue occurred.
        category: Optional category for grouping related signs.
        phase: Phase where issue was detected.

    Returns:
        The created Sign object.
    """
    sign = Sign(
        name=name,
        trigger=trigger,
        instruction=instruction,
        added_iteration=iteration,
        file_context=file_context,
        category=category,
        phase=phase,
    )

    guardrails_path = get_guardrails_path(repo_root)
    guardrails_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Read existing content
        existing_content = ""
        if guardrails_path.exists():
            existing_content = guardrails_path.read_text(encoding="utf-8")

        # Append new sign
        new_content = existing_content
        if new_content and not new_content.endswith("\n"):
            new_content += "\n"
        new_content += sign.to_markdown() + "\n"

        guardrails_path.write_text(new_content, encoding="utf-8")
        logger.info("Added guardrail sign '%s' to %s", name, guardrails_path)
    except OSError as e:
        logger.warning("Failed to write guardrails to %s: %s", guardrails_path, e)

    return sign


def format_signs_for_prompt(signs: list[Sign]) -> str:
    """Format signs as structured text for agent system prompt.

    This format is designed to be injected via --append-system-prompt.
    It uses bracket-style tags (not XML-style) to avoid conflicts with
    CLI argument validation.

    Args:
        signs: List of Sign objects to format.

    Returns:
        Formatted text for system prompt injection.
    """
    if not signs:
        return ""

    lines = [
        "\n[guardrails]",
        "Important: Follow these signs from previous iterations to avoid recurring issues:",
        "",
    ]

    for sign in signs:
        lines.append(f"SIGN [{sign.name}]")
        lines.append(f"  When: {sign.trigger}")
        lines.append(f"  Do: {sign.instruction}")
        if sign.file_context:
            lines.append(f"  Context: {sign.file_context}")
        lines.append("")

    lines.append("[/guardrails]")
    return "\n".join(lines)


def suggest_sign_from_error(
    error_message: str,
    iteration: int,
    _repo_root: Path,  # Reserved for future use
    phase: str | None = None,
    file_context: str | None = None,
) -> Sign | None:
    """Suggest a sign based on an error message using pattern matching.

    This function analyzes error messages and automatically suggests
    appropriate signs for common error patterns.

    Args:
        error_message: The error message to analyze.
        iteration: Current iteration number.
        _repo_root: Repository root directory. Callers should pass the actual
            repository root; this parameter is kept for interface consistency
            and may be used for repository-specific patterns in the future.
        phase: Phase where error occurred.
        file_context: Optional file context.

    Returns:
        Suggested Sign if pattern matches, None otherwise.
    """
    error_lower = error_message.lower()

    # Common error patterns and their corresponding signs
    patterns = [
        # Import errors
        {
            "patterns": ["no module named", "import error", "module not found"],
            "name": "check_imports_before_using",
            "trigger": "Adding a new import statement",
            "instruction": "Check if import already exists and verify the module is available",
            "category": "import",
        },
        # Migration errors
        {
            "patterns": [
                "migration failed",
                "duplicate column",
                "column already exists",
            ],
            "name": "use_if_not_exists_migrations",
            "trigger": "Creating database schema changes",
            "instruction": "Always use IF NOT EXISTS for idempotency in migrations",
            "category": "migration",
        },
        # Type errors
        {
            "patterns": ["type mismatch", "type error", "cannot convert"],
            "name": "check_types_before_operation",
            "trigger": "Working with typed values",
            "instruction": "Verify types match before operations, especially for IDs (string vs int)",
            "category": "types",
        },
        # Git errors
        {
            "patterns": ["merge conflict", "unmerged files", "your branch is behind"],
            "name": "sync_git_before_changes",
            "trigger": "Making changes to repository",
            "instruction": "Ensure git is synced with remote before making changes",
            "category": "git",
        },
        # Test failures
        {
            "patterns": ["test failed", "assertion", "test error"],
            "name": "run_tests_frequently",
            "trigger": "After making code changes",
            "instruction": "Run relevant tests after changes and fix failures before committing",
            "category": "testing",
        },
        # Linting errors
        {
            "patterns": ["lint", "formatting", "style"],
            "name": "run_linter_before_commit",
            "trigger": "Before committing changes",
            "instruction": "Run linter and formatter, fix all issues before commit",
            "category": "quality",
        },
        # Read-only errors
        {
            "patterns": ["permission denied", "read only", "readonly"],
            "name": "check_file_permissions",
            "trigger": "Writing to files",
            "instruction": "Ensure file permissions allow writing and check disk space",
            "category": "filesystem",
        },
    ]

    for pattern_dict in patterns:
        if any(p in error_lower for p in pattern_dict["patterns"]):
            return Sign(
                name=pattern_dict["name"],
                trigger=pattern_dict["trigger"],
                instruction=pattern_dict["instruction"],
                added_iteration=iteration,
                file_context=file_context,
                category=pattern_dict.get("category"),
                phase=phase,
            )

    return None


def clear_guardrails(repo_root: Path) -> None:
    """Clear all guardrails for a repository.

    Args:
        repo_root: Repository root directory.
    """
    guardrails_path = get_guardrails_path(repo_root)
    if guardrails_path.exists():
        try:
            guardrails_path.unlink()
            logger.info("Cleared guardrails for %s", repo_root)
        except OSError as e:
            logger.warning("Failed to clear guardrails: %s", e)


def get_sign_count(repo_root: Path) -> int:
    """Get the number of signs for a repository.

    Args:
        repo_root: Repository root directory.

    Returns:
        Number of signs (0 if file doesn't exist).
    """
    signs = load_guardrails(repo_root)
    return len(signs)
