"""Support state persistence."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class SupportState:
    """State persisted between support mode iterations.

    Attributes:
        iteration: Current iteration number (starts at 1, increments each loop)
        last_reviewed_sha: Git SHA of last reviewed commit
        last_reviewed_prd_hash: Hash of PRD content at last review
        last_reviewed_at: ISO timestamp of last review
    """
    iteration: int = 1
    last_reviewed_sha: str = ""
    last_reviewed_prd_hash: str = ""
    last_reviewed_at: str = ""


def _state_path(repo_root: Path) -> Path:
    """Get path to support_state.json file.

    Args:
        repo_root: Repository root directory.

    Returns:
        Path to .aprd/support_state.json
    """
    return repo_root / ".aprd" / "support_state.json"


def load_support_state(repo_root: Path) -> SupportState:
    """Load support state from disk.

    Args:
        repo_root: Repository root directory.

    Returns:
        SupportState object (default if file doesn't exist or is invalid)
    """
    path = _state_path(repo_root)
    if not path.exists():
        return SupportState()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return SupportState()

    try:
        iteration = int(data.get("iteration", 1) or 1)
    except (TypeError, ValueError):
        iteration = 1

    return SupportState(
        iteration=iteration,
        last_reviewed_sha=str(data.get("last_reviewed_sha", "") or ""),
        last_reviewed_prd_hash=str(data.get("last_reviewed_prd_hash", "") or ""),
        last_reviewed_at=str(data.get("last_reviewed_at", "") or ""),
    )


def save_support_state(repo_root: Path, state: SupportState) -> None:
    """Save support state to disk.

    Args:
        repo_root: Repository root directory.
        state: SupportState object to persist.
    """
    path = _state_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(state)
    path.write_text(json.dumps(payload, indent=2))
