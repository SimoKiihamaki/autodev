"""Guardrails and signs system for support-mode."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Sign:
    """A sign represents a learned pattern from a mistake.

    Attributes:
        name: Short identifier for the sign
        trigger: Description of what triggers this mistake
        instruction: What to do to avoid the mistake
    """

    name: str
    trigger: str
    instruction: str


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
    # Fallback to directory name
    return repo_root.name.replace("-", "_").replace("/", "_")


def load_guardrails(repo_root: Path) -> list[Sign]:
    """Load all signs for a repository.

    Args:
        repo_root: Repository root directory.

    Returns:
        List of Sign objects (empty if file doesn't exist).
    """
    guardrails_dir = _get_guardrails_dir()
    repo_slug = _get_repo_slug(repo_root)
    guardrails_path = guardrails_dir / f"{repo_slug}.md"

    if not guardrails_path.exists():
        return []

    signs = []
    try:
        content = guardrails_path.read_text()

        # Parse markdown format with "## sign:" headers
        pattern = re.compile(r"^##\s+sign:\s*(.+)$", re.MULTILINE)
        sections = pattern.split(content)[1:]  # Skip first empty match

        for i in range(0, len(sections) - 1, 2):
            if i + 1 < len(sections):
                name = sections[i].strip()
                section = sections[i + 1]

                # Extract trigger and instruction from bullet points
                trigger_match = re.search(r"-?\s*\*\*Trigger\*\*:\s*(.+)", section)
                instruction_match = re.search(
                    r"-?\s*\*\*Instruction\*\*:\s*(.+)", section
                )

                if trigger_match and instruction_match:
                    signs.append(
                        Sign(
                            name=name,
                            trigger=trigger_match.group(1).strip(),
                            instruction=instruction_match.group(1).strip(),
                        )
                    )
    except (OSError, UnicodeDecodeError):
        pass

    return signs
