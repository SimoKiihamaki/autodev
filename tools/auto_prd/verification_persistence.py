"""
Verification persistence system for Ralph Wiggum Loop.

Implements immutable verification run records stored in JSONL format
with git_sha + prd_hash for reproducibility and freshness checking.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from .git_ops import git_head_sha
from .utils import get_prd_hash


class VerificationStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    STALE = "stale"


class VerifierType(str, Enum):
    TEST = "test"
    PLAYWRIGHT = "playwright"
    ML_EVALUATION = "ml_evaluation"
    QUALITY_GATE = "quality_gate"
    CODE_REVIEW = "code_review"
    BENCHMARK = "benchmark"


@dataclass
class VerifierResult:
    """Result of running a single verifier."""

    name: str
    type: VerifierType
    command: str | None = None
    exit_code: int | None = None
    status: VerificationStatus = VerificationStatus.PENDING
    duration_sec: float = 0.0
    error: str | None = None
    stderr: str | None = None
    screenshots: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    metrics: dict[str, Any] | None = None
    quality_gates: list[dict[str, Any]] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = asdict(self)
        # Convert enums to strings
        result["type"] = self.type.value if isinstance(self.type, Enum) else self.type
        result["status"] = (
            self.status.value if isinstance(self.status, Enum) else self.status
        )
        return result


@dataclass
class VerificationRun:
    """Complete verification run result."""

    run_id: str
    timestamp_start: str
    timestamp_end: str
    git_sha: str
    base_branch: str
    prd_hash: str
    phase: str = "verification"  # Can be "local", "pr", "review_fix"
    verifiers: list[VerifierResult] = field(default_factory=list)
    overall_status: VerificationStatus = VerificationStatus.PENDING
    artifact_paths: list[str] = field(default_factory=list)
    tool_versions: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = asdict(self)
        # Convert enums
        result["overall_status"] = (
            self.overall_status.value
            if isinstance(self.overall_status, Enum)
            else self.overall_status
        )
        # Convert verifier enums
        result["verifiers"] = [v.to_dict() for v in self.verifiers]
        return result


class VerificationPersistence:
    """
    Manages persistence of verification runs in JSONL format.

    Each line in the JSONL file is a complete, immutable verification run record.
    """

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)
        self.runs_dir = self.repo_root / ".aprd" / "verification"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.runs_log = self.runs_dir / "runs.jsonl"

    def save_run(self, run: VerificationRun) -> None:
        """
        Append a verification run to the JSONL log.

        Args:
            run: VerificationRun to persist
        """
        # Ensure status is set
        if run.overall_status == VerificationStatus.PENDING and run.verifiers:
            # Determine overall status from verifiers
            all_passed = all(
                v.status == VerificationStatus.PASSED for v in run.verifiers
            )
            run.overall_status = (
                VerificationStatus.PASSED if all_passed else VerificationStatus.FAILED
            )

        # Append to JSONL
        with open(self.runs_log, "a") as f:
            f.write(json.dumps(run.to_dict()) + "\n")

    def load_runs(
        self,
        limit: int | None = None,
        since_hours: int | None = None,
        git_sha: str | None = None,
        prd_hash: str | None = None,
    ) -> list[VerificationRun]:
        """
        Load verification runs from JSONL log.

        Args:
            limit: Maximum number of runs to load (most recent first)
            since_hours: Only load runs from last N hours
            git_sha: Only load runs matching this git_sha
            prd_hash: Only load runs matching this prd_hash

        Returns:
            List of VerificationRun objects (most recent first)
        """
        if not self.runs_log.exists():
            return []

        runs = []
        with open(self.runs_log) as f:
            for line in f:
                try:
                    run_dict = json.loads(line)
                    run = self._dict_to_run(run_dict)
                    runs.append(run)
                except (json.JSONDecodeError, KeyError, ValueError):
                    # Skip malformed lines
                    continue

        # Filter by criteria
        filtered_runs = runs
        if git_sha:
            filtered_runs = [r for r in filtered_runs if r.git_sha == git_sha]
        if prd_hash:
            filtered_runs = [r for r in filtered_runs if r.prd_hash == prd_hash]
        if since_hours:
            from datetime import timedelta

            cutoff = datetime.now() - timedelta(hours=since_hours)
            filtered_runs = [
                r
                for r in filtered_runs
                if datetime.fromisoformat(r.timestamp_start) >= cutoff
            ]

        # Sort by timestamp (most recent first)
        filtered_runs.sort(key=lambda r: r.timestamp_start, reverse=True)

        # Apply limit
        if limit:
            filtered_runs = filtered_runs[:limit]

        return filtered_runs

    def get_latest_run(
        self, git_sha: str | None = None, prd_hash: str | None = None
    ) -> VerificationRun | None:
        """
        Get the most recent verification run.

        Args:
            git_sha: Only consider runs matching this git_sha
            prd_hash: Only consider runs matching this prd_hash

        Returns:
            Most recent VerificationRun or None
        """
        runs = self.load_runs(limit=1, git_sha=git_sha, prd_hash=prd_hash)
        return runs[0] if runs else None

    def is_verification_fresh(
        self,
        verification_ref: dict[str, Any],
        current_git_sha: str,
        current_prd_hash: str,
    ) -> bool:
        """
        Check if verification evidence is still valid (fresh).

        Evidence is fresh if:
        1. git_sha matches current HEAD
        2. prd_hash matches current PRD

        Args:
            verification_ref: Dictionary with 'git_sha' and 'prd_hash' keys
            current_git_sha: Current git commit SHA
            current_prd_hash: Current PRD hash

        Returns:
            True if evidence is fresh, False otherwise
        """
        return (
            verification_ref.get("git_sha") == current_git_sha
            and verification_ref.get("prd_hash") == current_prd_hash
        )

    def is_run_fresh(
        self, run: VerificationRun, current_prd_hash: str | None = None
    ) -> bool:
        """
        Check if a verification run is still fresh for current state.

        Args:
            run: VerificationRun to check
            current_prd_hash: Optional PRD hash for support mode where PRD path may differ.
                If not provided, falls back to default PRD.md hash.

        Returns:
            True if run is fresh, False otherwise
        """
        current_git_sha = git_head_sha(self.repo_root)
        if current_prd_hash is None:
            current_prd_hash = get_prd_hash(self.repo_root)

        return self.is_verification_fresh(
            run.to_dict(), current_git_sha, current_prd_hash
        )

    def _dict_to_run(self, run_dict: dict) -> VerificationRun:
        """
        Convert dictionary to VerificationRun object.

        Handles enum conversion and nested verifiers.

        Args:
            run_dict: Dictionary from JSON

        Returns:
            VerificationRun object
        """
        # Convert verifier dicts to objects
        verifiers = []
        for v_dict in run_dict.get("verifiers", []):
            verifier = VerifierResult(
                name=v_dict["name"],
                type=VerifierType(v_dict["type"]),
                command=v_dict.get("command"),
                exit_code=v_dict.get("exit_code"),
                status=VerificationStatus(v_dict["status"]),
                duration_sec=v_dict.get("duration_sec", 0.0),
                error=v_dict.get("error"),
                stderr=v_dict.get("stderr"),
                screenshots=v_dict.get("screenshots", []),
                acceptance_criteria=v_dict.get("acceptance_criteria", []),
                metrics=v_dict.get("metrics"),
                quality_gates=v_dict.get("quality_gates", []),
                findings=v_dict.get("findings", []),
                artifacts=v_dict.get("artifacts", []),
            )
            verifiers.append(verifier)

        return VerificationRun(
            run_id=run_dict["run_id"],
            timestamp_start=run_dict["timestamp_start"],
            timestamp_end=run_dict["timestamp_end"],
            git_sha=run_dict["git_sha"],
            base_branch=run_dict["base_branch"],
            prd_hash=run_dict["prd_hash"],
            phase=run_dict.get("phase", "verification"),
            verifiers=verifiers,
            overall_status=VerificationStatus(run_dict["overall_status"]),
            artifact_paths=run_dict.get("artifact_paths", []),
            tool_versions=run_dict.get("tool_versions", {}),
        )


def generate_run_id() -> str:
    """Generate a unique run ID based on timestamp."""
    return f"vrf_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def create_verification_run(
    repo_root: Path,
    verifiers: list[VerifierResult],
    phase: str = "verification",
    base_branch: str = "main",
) -> VerificationRun:
    """
    Create a VerificationRun object with current git_sha and prd_hash.

    Args:
        repo_root: Repository root directory
        verifiers: List of VerifierResult objects
        phase: Phase that triggered verification
        base_branch: Base branch for comparison

    Returns:
        VerificationRun object ready to persist
    """
    git_sha = git_head_sha(repo_root)
    prd_hash = get_prd_hash(repo_root)

    run_id = generate_run_id()
    now = datetime.now().isoformat()

    return VerificationRun(
        run_id=run_id,
        timestamp_start=now,
        timestamp_end=now,  # Will be updated after verifiers complete
        git_sha=git_sha,
        base_branch=base_branch,
        prd_hash=prd_hash,
        phase=phase,
        verifiers=verifiers,
        overall_status=VerificationStatus.PENDING,
    )
