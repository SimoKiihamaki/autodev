"""
Simple verification gates module for Ralph Wiggum Loop testing.

This module provides mock implementations of verification functions
for testing the readiness orchestrator without needing full dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .verification_persistence import (
    VerificationStatus,
    VerifierResult,
    VerifierType,
)


@dataclass
class MockVerificationRun:
    """Mock verification run for testing."""

    run_id: str
    overall_status: VerificationStatus
    verifiers: list[VerifierResult] = field(default_factory=list)
    git_sha: str = "abc123"
    prd_hash: str = "hash123"
    phase: str = "verification"


def run_verification_gates(repo_root: Path, tracker_path: Path) -> MockVerificationRun:
    """
    Run verification gates on tracker and return mock result.

    This is a simplified version for testing that always passes.
    In production, this would integrate with:
    - tools/verification.py to run actual tests
    - Playwright for user journey tests
    - ML evaluation frameworks for model validation
    """
    _ = repo_root, tracker_path  # Currently unused, kept for interface compatibility
    verifiers = [
        VerifierResult(
            name="unit_tests",
            type=VerifierType.TEST,
            status=VerificationStatus.PASSED,
            duration_sec=12.3,
            exit_code=0,
            command="go test ./...",
        ),
        VerifierResult(
            name="lint_checks",
            type=VerifierType.QUALITY_GATE,
            status=VerificationStatus.PASSED,
            duration_sec=8.7,
            exit_code=0,
            command="ruff check .",
        ),
    ]

    return MockVerificationRun(
        run_id="vrf_test_001",
        overall_status=VerificationStatus.PASSED,
        verifiers=verifiers,
        git_sha="abc123",
        prd_hash="hash123",
        phase="verification",
    )


def is_verification_fresh(
    verification_ref: dict[str, Any], current_git_sha: str, current_prd_hash: str
) -> bool:
    """
    Check if verification evidence is still valid (fresh).

    For testing purposes, this always returns True.
    In production, this would check git_sha and prd_hash match.
    """
    _ = verification_ref, current_git_sha, current_prd_hash  # Currently unused
    return True


def create_test_tracker(repo_root: Path) -> dict[str, Any]:
    """
    Create a minimal test tracker for Ralph Wiggum Loop testing.

    Returns a basic tracker structure with a few features.
    """
    _ = repo_root  # Currently unused, kept for interface compatibility
    return {
        "version": "2.0.0",
        "prd_hash": "test_hash_123",
        "metadata": {"created_at": "2025-01-14T19:00:00Z", "prd_source": "TEST_PRD.md"},
        "features": [
            {
                "id": "F001",
                "title": "User authentication",
                "status": "verified",
                "acceptance_criteria": [
                    {
                        "id": "AC001",
                        "type": "unit_test",
                        "description": "User can login with valid credentials",
                        "status": "passed",
                    },
                    {
                        "id": "AC002",
                        "type": "code_review",
                        "description": "Code review passed",
                        "status": "passed",
                    },
                ],
                "verification_evidence": {
                    "run_id": "vrf_test_001",
                    "verified_at": "2025-01-14T19:00:00Z",
                },
            },
            {
                "id": "F002",
                "title": "User dashboard",
                "status": "verified",
                "acceptance_criteria": [
                    {
                        "id": "AC003",
                        "type": "unit_test",
                        "description": "Dashboard displays user data",
                        "status": "passed",
                    }
                ],
                "verification_evidence": {
                    "run_id": "vrf_test_001",
                    "verified_at": "2025-01-14T19:00:00Z",
                },
            },
            {
                "id": "F003",
                "title": "User profile management",
                "status": "completed",
                "acceptance_criteria": [],
            },
        ],
        "validation_summary": {
            "total_features": 3,
            "completed": 2,
            "verified": 2,
            "pending": 1,
        },
    }
