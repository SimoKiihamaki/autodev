"""Verification status checking for support-mode."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .git_ops import git_head_sha


class VerificationStatus(str, Enum):
    """Verification status values."""

    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    STALE = "stale"


@dataclass
class VerifierResult:
    """Result of running a single verifier."""

    name: str
    status: VerificationStatus = VerificationStatus.PENDING
    exit_code: int | None = None


@dataclass
class VerificationRun:
    """Complete verification run result."""

    run_id: str
    timestamp_start: str
    timestamp_end: str
    git_sha: str
    prd_hash: str
    verifiers: list[VerifierResult]
    overall_status: VerificationStatus = VerificationStatus.PENDING


class VerificationPersistence:
    """Manages persistence of verification runs in JSONL format."""

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)
        self.runs_dir = self.repo_root / ".aprd" / "verification"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.runs_log = self.runs_dir / "runs.jsonl"

    def get_latest_run(self) -> VerificationRun | None:
        """Get the most recent verification run.

        Returns:
            Most recent VerificationRun or None
        """
        if not self.runs_log.exists():
            return None

        try:
            with open(self.runs_log) as f:
                lines = f.readlines()
                if not lines:
                    return None
                # Last line is most recent
                run_dict = json.loads(lines[-1])
                return self._dict_to_run(run_dict)
        except (OSError, json.JSONDecodeError, KeyError):
            return None

    def is_run_fresh(self, run: VerificationRun, current_prd_hash: str) -> bool:
        """Check if a verification run is still fresh for current state.

        Args:
            run: VerificationRun to check
            current_prd_hash: Current PRD hash

        Returns:
            True if run is fresh, False otherwise
        """
        current_git_sha = git_head_sha(self.repo_root)
        return run.git_sha == current_git_sha and run.prd_hash == current_prd_hash

    def _dict_to_run(self, data: dict) -> VerificationRun:
        """Convert dictionary to VerificationRun.

        Args:
            data: Dictionary with verification run data

        Returns:
            VerificationRun instance
        """
        verifiers = [
            VerifierResult(
                name=v.get("name", "unknown"),
                status=VerificationStatus(v.get("status", "pending")),
                exit_code=v.get("exit_code"),
            )
            for v in data.get("verifiers", [])
        ]

        return VerificationRun(
            run_id=data.get("run_id", ""),
            timestamp_start=data.get("timestamp_start", ""),
            timestamp_end=data.get("timestamp_end", ""),
            git_sha=data.get("git_sha", ""),
            prd_hash=data.get("prd_hash", ""),
            verifiers=verifiers,
            overall_status=VerificationStatus(data.get("overall_status", "pending")),
        )
