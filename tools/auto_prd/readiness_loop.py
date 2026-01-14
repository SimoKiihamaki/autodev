"""
Readiness orchestrator for Ralph Wiggum Loop.

Implements outer loop that wraps existing phases (local → pr → review_fix)
with scope review, adaptive guardrails, and termination convergence logic.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from enum import Enum

from .utils import get_prd_hash
from .scope_reviewer import ScopeReviewer, TriggerType, ScopeReviewResult, ScopeChange
from .verification_persistence import (
    VerificationPersistence,
    VerificationRun,
    VerificationStatus,
    create_verification_run,
)
from .context import StallDetector
from .verification import run_verification_gates


class ReadinessState(str, Enum):
    INITIALIZING = "initializing"
    SCOPE_REVIEW = "scope_review"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    EVALUATING = "evaluating"
    READY = "ready"
    STALLED = "stalled"
    FAILED = "failed"


@dataclass
class ReadinessConfig:
    """Configuration for Ralph Wiggum Loop."""

    enabled: bool = True
    max_iterations: int = 100
    scope_review_interval: int = 5
    failure_to_sign_threshold: int = 2
    base_branch: str = "main"
    create_issue_on_stall: bool = False


@dataclass
class ReadinessStats:
    """Statistics collected during readiness loop execution."""

    iteration: int = 0
    scope_reviews: int = 0
    verification_runs: int = 0
    guardrail_signs_added: int = 0
    features_verified: int = 0
    features_total: int = 0


class ReadinessOrchestrator:
    """
    Orchestrates Ralph Wiggum Loop - outer loop that keeps iterating until ready.

    Wraps existing phases (local → pr → review_fix) and adds:
    - Scope review with trigger signals
    - Comprehensive verification with freshness checking
    - Adaptive guardrail evolution
    - Termination based on convergence of multiple signals
    """

    def __init__(
        self,
        repo_root: Path,
        config: Optional[ReadinessConfig] = None,
        state_dir: Optional[Path] = None,
    ):
        self.repo_root = Path(repo_root)
        self.config = config or ReadinessConfig()
        self.state_dir = Path(state_dir) if state_dir else self.repo_root / ".aprd"
        self.state_dir.mkdir(parents=True, exist_ok=True)

        self.state = ReadinessState.INITIALIZING
        self.stats = ReadinessStats()

        self.scope_reviewer = ScopeReviewer(self.repo_root, self.state_dir)
        self.verification_persistence = VerificationPersistence(self.repo_root)
        self.stall_detector = StallDetector()

    def run(self, tracker: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run Ralph Wiggum Loop until ready or max iterations.

        Args:
            tracker: Current tracker dictionary

        Returns:
            Final state with execution statistics
        """
        while (
            self.stats.iteration < self.config.max_iterations
            and self.state != ReadinessState.READY
        ):
            self.state = ReadinessState.SCOPE_REVIEW
            self._handle_scope_review(tracker)

            self.state = ReadinessState.EXECUTING
            self._handle_execution(tracker)

            self.state = ReadinessState.VERIFYING
            verification_result = self._handle_verification()

            self.state = ReadinessState.EVALUATING
            self._handle_evaluation(verification_result, tracker)

            self.stats.iteration += 1

        if self.state == ReadinessState.READY:
            return {
                "status": "ready",
                "stats": self.stats.__dict__,
                "message": "Ralph Wiggum Loop converged to ready state",
            }
        else:
            return {
                "status": "not_ready",
                "stats": self.stats.__dict__,
                "message": self._get_stall_message(),
            }

    def _handle_scope_review(self, tracker: Dict[str, Any]) -> None:
        """Handle scope review phase."""
        is_stalled, _ = self.stall_detector.check_stall()
        should_review, trigger_type = self.scope_reviewer.should_review_scope(
            iteration=self.stats.iteration,
            current_prd_hash=get_prd_hash(self.repo_root),
            stall_detected=is_stalled,
            verification_failed=self._last_verification_failed(tracker),
            tracker_done_verification_failed=self._tracker_done_but_verification_failed(
                tracker
            ),
        )

        if should_review:
            import json

            prd_content = (
                (self.repo_root / "PRD.md").read_text()
                if (self.repo_root / "PRD.md").exists()
                else None
            )
            review_result = self.scope_reviewer.review_scope(
                iteration=self.stats.iteration,
                trigger_type=trigger_type or TriggerType.PERIODIC,
                tracker=tracker,
                prd_content=prd_content,
            )

            self.stats.scope_reviews += 1

            if review_result.has_changes():
                self._apply_scope_changes(review_result, tracker)
                trigger_display = trigger_type.value if trigger_type else "unknown"
                print(
                    f"\n📋 Scope Review ({trigger_display}): {len(review_result.changes)} changes"
                )

                if review_result.needs_full_rescoping:
                    print("⚠️  Full rescopning may be required")

    def _handle_execution(self, tracker: Dict[str, Any]) -> None:
        """Handle execution phase (local → pr → review_fix)."""
        import subprocess
        from . import cli

        print(f"\n🚀 Execution Phase: Iteration {self.stats.iteration}")
        print(f"   Features: {self._count_features(tracker)}")
        print(
            f"   Completed: {tracker.get('validation_summary', {}).get('features_verified', 0)}"
        )

        try:
            subprocess.run(
                ["python3", "-m", "tools.auto_prd.cli"], check=True, cwd=self.repo_root
            )
        except subprocess.CalledProcessError as e:
            print(f"\n❌ Execution phase failed: {e}")
            if self.stats.iteration >= 3:
                self.state = ReadinessState.STALLED
                raise

    def _handle_verification(self) -> VerificationRun:
        """Handle verification phase."""
        print(f"\n🧪 Verification Phase: Iteration {self.stats.iteration}")

        verification_results = run_verification_gates(
            repo_root=self.repo_root,
            tracker_path=self.repo_root / ".aprd" / "tracker.json",
        )

        run = create_verification_run(
            repo_root=self.repo_root,
            verifiers=verification_results,
            phase="verification",
            base_branch=self.config.base_branch,
        )

        self.verification_persistence.save_run(run)
        self.stats.verification_runs += 1
        self.stats.features_verified = sum(
            1
            for f in self._load_tracker().get("features", [])
            if f.get("status") == "verified"
        )
        self.stats.features_total = len(self._load_tracker().get("features", []))

        print(f"   Verifiers: {len(run.verifiers)}")
        print(f"   Status: {run.overall_status.value}")

        return run

    def _handle_evaluation(
        self, verification_result: VerificationRun, tracker: Dict[str, Any]
    ) -> None:
        """Handle evaluation phase - check termination conditions."""
        print(f"\n📊 Evaluation Phase: Iteration {self.stats.iteration}")

        is_ready, missing_reasons = self._is_ready(verification_result, tracker)

        if is_ready:
            self.state = ReadinessState.READY
            print("✅ Ready: All convergence conditions met")
            print(
                f"   Features verified: {self.stats.features_verified}/{self.stats.features_total}"
            )
            print(f"   Scope reviews: {self.stats.scope_reviews}")
            print(f"   Verification runs: {self.stats.verification_runs}")
            print(f"   Guardrail signs added: {self.stats.guardrail_signs_added}")
        else:
            self.state = ReadinessState.EVALUATING
            self._evaluate_guardrail_evolution(tracker)

            is_stalled, stall_reason = self.stall_detector.check_stall()
            if is_stalled:
                self.state = ReadinessState.STALLED
                print(f"🛑 Stalled: {stall_reason}")
                if self.config.create_issue_on_stall:
                    self._create_stall_issue(missing_reasons)
            else:
                print(f"\n⏳  Not yet ready ({len(missing_reasons)} reasons):")
                for reason in missing_reasons:
                    print(f"   - {reason}")

    def _is_ready(
        self, verification_result: VerificationRun, tracker: Dict[str, Any]
    ) -> tuple[bool, List[str]]:
        """
        Check if all readiness conditions are met via convergence of multiple signals.

        Ready = all 7 signals converge:
        1. All features verified
        2. Evidence fresh (git/prd match)
        3. No CodeRabbit findings
        4. Scope review clean
        5. System not stalled
        6. All quality gates passed
        7. No active guardrail signs
        """
        from .guardrails import load_guardrails

        reasons = []

        features = tracker.get("features", [])

        # Signal 1: All features verified
        all_verified = all(f.get("status") == "verified" for f in features)
        if not all_verified:
            unverified = [f["id"] for f in features if f.get("status") != "verified"]
            reasons.append(f"Features not verified: {', '.join(unverified)}")

        # Signal 2: Evidence fresh
        stale_features = 0
        for feature in features:
            evidence = feature.get("verification_evidence", {})
            if not self.verification_persistence.is_verification_fresh(
                evidence, verification_result.git_sha, verification_result.prd_hash
            ):
                reasons.append(
                    f"Feature {feature['id']}: Evidence stale (git/prd mismatch)"
                )
                stale_features += 1

        # Signal 3: No CodeRabbit findings
        review_feedback = self._get_review_feedback()
        if review_feedback:
            reasons.append(f"Unresolved review feedback: {len(review_feedback)} items")

        # Signal 4: Scope review clean
        scope_needs_review = self._scope_needs_review()
        if scope_needs_review:
            reasons.append("Scope review identifies missing requirements")

        # Signal 5: System not stalled (checked externally, not part of convergence)

        # Signal 6: All quality gates passed
        if verification_result.overall_status != VerificationStatus.PASSED:
            failed_verifiers = [
                v.name
                for v in verification_result.verifiers
                if v.status == VerificationStatus.FAILED
            ]
            reasons.append(f"Verification gates failed: {', '.join(failed_verifiers)}")

        # Signal 7: No active guardrail signs
        active_signs = load_guardrails(self.repo_root)
        if active_signs:
            reasons.append(f"Active guardrail signs: {len(active_signs)}")

        # Ready if all 7 signals converge (no reasons)
        is_ready = len(reasons) == 0
        return (is_ready, reasons)

    def _evaluate_guardrail_evolution(self, tracker: Dict[str, Any]) -> None:
        """Check if guardrails should evolve from failures."""
        signs_created = self.scope_reviewer.evolve_guardrails_from_failures(
            threshold=self.config.failure_to_sign_threshold,
            iteration=self.stats.iteration,
        )
        self.stats.guardrail_signs_added += len(signs_created)

    def _apply_scope_changes(
        self, review_result: ScopeReviewResult, tracker: Dict[str, Any]
    ) -> None:
        """Apply scope changes to tracker."""
        import json

        tracker_path = self.repo_root / ".aprd" / "tracker.json"

        for change in review_result.changes:
            if change.type == "add_criteria":
                self._add_acceptance_criterion(tracker, change)
            elif change.type == "invalidate_tasks":
                self._invalidate_feature_tasks(tracker, change)
            elif change.type == "needs_reverify":
                self._mark_needs_reverify(tracker, change)
            elif change.type == "warning":
                print(f"⚠️  {change.description}")

        with open(tracker_path, "w") as f:
            json.dump(tracker, f, indent=2)

    def _add_acceptance_criterion(
        self, tracker: Dict[str, Any], change: ScopeChange
    ) -> None:
        """Add new acceptance criterion to feature."""
        for feature in tracker.get("features", []):
            if feature["id"] == change.feature_id:
                if not feature.get("acceptance_criteria"):
                    feature["acceptance_criteria"] = []
                feature["acceptance_criteria"].append(
                    {
                        "id": f"AC{len(feature['acceptance_criteria']) + 1}",
                        "type": "unit_test",
                        "description": change.description,
                        "status": "pending",
                        "version": 1,
                    }
                )
                break

    def _invalidate_feature_tasks(
        self, tracker: Dict[str, Any], change: ScopeChange
    ) -> None:
        """Mark feature tasks as needing reverification."""
        for feature in tracker.get("features", []):
            if feature["id"] == change.feature_id:
                feature["status"] = "in_progress"
                for task in feature.get("tasks", []):
                    task["status"] = "pending"

    def _mark_needs_reverify(
        self, tracker: Dict[str, Any], change: ScopeChange
    ) -> None:
        """Mark feature as needing reverification."""
        for feature in tracker.get("features", []):
            if feature["id"] == change.feature_id:
                feature["needs_reverify"] = True
                for criterion in feature.get("acceptance_criteria", []):
                    criterion["status"] = "pending"

    def _load_tracker(self) -> Dict[str, Any]:
        """Load tracker from file."""
        tracker_path = self.repo_root / ".aprd" / "tracker.json"
        with open(tracker_path, "r") as f:
            import json

            return json.load(f)

    def _last_verification_failed(self, tracker: Dict[str, Any]) -> bool:
        """Check if last verification failed."""
        last_run = self.verification_persistence.get_latest_run()
        if not last_run:
            return False
        return last_run.overall_status == VerificationStatus.FAILED

    def _tracker_done_but_verification_failed(self, tracker: Dict[str, Any]) -> bool:
        """Check if tracker shows done but verification fails."""
        all_complete = all(
            f.get("status") in ["completed", "verified"]
            for f in tracker.get("features", [])
        )
        last_run = self.verification_persistence.get_latest_run()
        if not last_run:
            return False
        return all_complete and last_run.overall_status == VerificationStatus.FAILED

    def _get_review_feedback(self) -> List[str]:
        """Get unresolved review feedback from CodeRabbit."""
        last_run = self.verification_persistence.get_latest_run()
        if not last_run:
            return []

        unresolved = []
        for verifier in last_run.verifiers:
            if (
                verifier.type == "code_review"
                and verifier.status == VerificationStatus.FAILED
            ):
                findings = verifier.findings
                unresolved.extend(findings)

        return unresolved

    def _scope_needs_review(self) -> bool:
        """Check if scope review should run."""
        last_review = self.scope_reviewer.state.get("last_scope_review_iteration", 0)
        current_review = self.stats.iteration
        return (current_review - last_review) >= self.config.scope_review_interval

    def _count_features(self, tracker: Dict[str, Any]) -> Dict[str, int]:
        """Count features by status."""
        features = tracker.get("features", [])
        counts = {"pending": 0, "in_progress": 0, "completed": 0, "verified": 0}

        for feature in features:
            status = feature.get("status", "pending")
            if status in counts:
                counts[status] += 1

        return counts

    def _get_stall_message(self) -> str:
        """Get detailed stall message."""
        is_stalled, stall_reason = self.stall_detector.check_stall()
        stall_text = f"{stall_reason}" if is_stalled else ""
        stats_summary = (
            f"Iterations: {self.stats.iteration}, "
            f"Scope reviews: {self.stats.scope_reviews}, "
            f"Verification runs: {self.stats.verification_runs}, "
            f"Guardrail signs: {self.stats.guardrail_signs_added}"
        )
        return f"{stall_text}\n\n{stats_summary}"

    def _create_stall_issue(self, missing_reasons: List[str]) -> None:
        """Create GitHub issue for stall escalation."""
        try:
            import subprocess

            stall_result = self.stall_detector.check_stall()
            is_stalled, stall_reason = stall_result
            stall_text = f"{stall_reason}" if is_stalled else ""

            body = [
                "## Ralph Wiggum Loop Stalled",
                "",
                f"The Ralph Wiggum Loop has stalled after {self.stats.iteration} iterations.",
                "",
                "### Stall Reason",
                "",
                stall_text,
                "",
                "### Statistics",
                f"- Iterations: {self.stats.iteration}",
                f"- Scope reviews: {self.stats.scope_reviews}",
                f"- Verification runs: {self.stats.verification_runs}",
                f"- Guardrail signs: {self.stats.guardrail_signs_added}",
                "",
                "### Missing Conditions",
                "",
            ]

            if missing_reasons:
                body.append("### Missing Conditions")
                body.append("")
                for reason in missing_reasons:
                    body.append(f"- {reason}")
                body.append("")

            body.extend(
                [
                    "### Next Steps",
                    "1. Review stall state: `~/.config/aprd/stall_state.json`",
                    "2. Fix blockers or adjust scope",
                    "3. Resume with: `aprd --resume`",
                    "",
                    "### Execution Stats",
                    "```",
                    json.dumps(self.stats.__dict__, indent=2),
                    "```",
                ]
            )

            subprocess.run(
                [
                    "gh",
                    "issue",
                    "create",
                    "--title",
                    f"[RALPH] Stalled after {self.stats.iteration} iterations",
                    "--body",
                    "\n".join(body),
                ],
                check=True,
                cwd=self.repo_root,
            )
        except FileNotFoundError:
            print("⚠️  gh CLI not available - skipping issue creation")


def run_ralph_wiggum_loop(
    repo_root: Path, config: Optional[ReadinessConfig] = None
) -> Dict[str, Any]:
    """
    Entry point for Ralph Wiggum Loop.

    Args:
        repo_root: Repository root directory
        config: Optional configuration overrides

    Returns:
        Final execution state with statistics
    """
    orchestrator = ReadinessOrchestrator(repo_root, config)
    tracker = orchestrator._load_tracker()

    print("\n" + "=" * 70)
    print("🔄 RALPH WIGGUM LOOP STARTED")
    print("=" * 70)
    print(f"Max iterations: {orchestrator.config.max_iterations}")
    print(
        f"Scope review interval: Every {orchestrator.config.scope_review_interval} iterations"
    )
    print(f"Failure-to-sign threshold: {orchestrator.config.failure_to_sign_threshold}")
    print("=" * 70)

    result = orchestrator.run(tracker)

    print("\n" + "=" * 70)
    print("RALPH WIGGUM LOOP FINISHED")
    print("=" * 70)
    print(f"Final status: {result['status']}")
    print(f"Total iterations: {result['stats']['iteration']}")
    print(f"Scope reviews: {result['stats']['scope_reviews']}")
    print(f"Verification runs: {result['stats']['verification_runs']}")
    print(f"Guardrail signs added: {result['stats']['guardrail_signs_added']}")
    print("=" * 70)

    return result
