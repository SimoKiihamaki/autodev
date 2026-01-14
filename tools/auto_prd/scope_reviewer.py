"""
Scope review mechanism for Ralph Wiggum Loop.

Detects missing requirements, validates acceptance criteria completeness,
and tracks PRD changes for selective invalidation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from enum import Enum
import re

from .utils import get_git_sha, get_prd_hash, compute_file_hash
from .guardrails import add_sign


class TriggerType(str, Enum):
    PERIODIC = "periodic"
    FAILURE_BASED = "failure_based"
    PROGRESS_BASED = "progress_based"
    CHANGE_BASED = "change_based"
    STALL_BASED = "stall_based"


@dataclass
class ScopeChange:
    """Represents a change to apply to tracker/criteria."""

    type: str
    feature_id: Optional[str] = None
    criterion_id: Optional[str] = None
    description: Optional[str] = None
    reason: Optional[str] = None
    severity: str = "info"


@dataclass
class ScopeReviewResult:
    """Result of scope review operation."""

    triggered_at: str
    iteration: int
    trigger_type: TriggerType
    prd_hash: str
    changes: List[ScopeChange] = field(default_factory=list)
    needs_full_rescoping: bool = False

    def has_changes(self) -> bool:
        """Check if review identified any changes."""
        return len(self.changes) > 0

    def get_severity_summary(self) -> Dict[str, int]:
        """Get summary of changes by severity."""
        summary = {"info": 0, "warning": 0, "error": 0}
        for change in self.changes:
            if change.severity in summary:
                summary[change.severity] += 1
        return summary


@dataclass
class FailureFingerprint:
    """Fingerprint of a failure for pattern detection."""

    phase: str
    gate_name: str
    error_type: str
    normalized_error: str
    stack_frame: Optional[str] = None
    count: int = 1
    first_seen: str = ""
    last_seen: str = ""

    def to_key(self) -> str:
        """Generate unique key for deduplication."""
        return f"{self.phase}:{self.gate_name}:{self.error_type}:{hash(self.normalized_error)}"

    def should_become_sign(self, threshold: int = 2) -> bool:
        """Check if repeated enough to become a guardrail sign."""
        return self.count >= threshold


class ScopeReviewer:
    """
    Orchestrates scope review based on multiple trigger signals.
    """

    REVIEW_INTERVAL = 5
    FAILURE_THRESHOLD = 2

    def __init__(self, repo_root: Path, state_dir: Optional[Path] = None):
        self.repo_root = Path(repo_root)
        self.state_dir = Path(state_dir) if state_dir else self.repo_root / ".aprd"
        self.state_dir.mkdir(parents=True, exist_ok=True)

        self.last_review_file = self.state_dir / "last_scope_review.json"
        self.fingerprint_history_file = self.state_dir / "failure_fingerprints.jsonl"

        self.state: Dict[str, Any] = self._load_state()
        self.failure_fingerprints: Dict[str, FailureFingerprint] = (
            self._load_fingerprints()
        )

    def _load_state(self) -> Dict[str, Any]:
        """Load persistent state for scope review."""
        if self.last_review_file.exists():
            import json

            with open(self.last_review_file, "r") as f:
                return json.load(f)
        return {
            "last_scope_review_iteration": 0,
            "last_prd_hash_scoped": "",
            "stall_count": 0,
        }

    def _load_fingerprints(self) -> Dict[str, FailureFingerprint]:
        """Load failure fingerprint history."""
        import json

        fingerprints = {}
        if self.fingerprint_history_file.exists():
            with open(self.fingerprint_history_file, "r") as f:
                for line in f:
                    try:
                        fp_dict = json.loads(line)
                        fp = FailureFingerprint(**fp_dict)
                        fingerprints[fp.to_key()] = fp
                    except (json.JSONDecodeError, TypeError):
                        continue
        return fingerprints

    def _save_state(self) -> None:
        """Save persistent state."""
        import json

        with open(self.last_review_file, "w") as f:
            json.dump(self.state, f, indent=2)

    def _save_fingerprints(self) -> None:
        """Save failure fingerprint history."""
        import json

        with open(self.fingerprint_history_file, "w") as f:
            for fp in self.failure_fingerprints.values():
                f.write(json.dumps(fp.__dict__) + "\n")

    def should_review_scope(
        self,
        iteration: int,
        current_prd_hash: str,
        stall_detected: bool = False,
        verification_failed: bool = False,
        tracker_done_verification_failed: bool = False,
    ) -> tuple[bool, Optional[TriggerType]]:
        """
        Determine if scope review should run.

        Args:
            iteration: Current iteration number
            current_prd_hash: Hash of current PRD
            stall_detected: StallDetector reported stall
            verification_failed: Latest verification failed
            tracker_done_verification_failed: Tracker says done but verification fails

        Returns:
            (should_review, trigger_type)
        """
        last_iteration = self.state.get("last_scope_review_iteration", 0)
        last_prd_hash = self.state.get("last_prd_hash_scoped", "")

        if iteration - last_iteration >= self.REVIEW_INTERVAL:
            return True, TriggerType.PERIODIC

        if last_prd_hash != current_prd_hash:
            return True, TriggerType.CHANGE_BASED

        if stall_detected:
            return True, TriggerType.STALL_BASED

        if tracker_done_verification_failed:
            return True, TriggerType.PROGRESS_BASED

        if verification_failed:
            failure_count = self.state.get("recent_verification_failures", 0)
            if failure_count >= self.FAILURE_THRESHOLD:
                return True, TriggerType.FAILURE_BASED

        return False, None

    def review_scope(
        self,
        iteration: int,
        trigger_type: TriggerType,
        tracker: Dict[str, Any],
        prd_content: Optional[str] = None,
    ) -> ScopeReviewResult:
        """
        Perform scope review and identify changes.

        Args:
            iteration: Current iteration number
            trigger_type: What triggered this review
            tracker: Tracker dictionary
            prd_content: Full PRD content (optional for deep analysis)

        Returns:
            ScopeReviewResult with changes to apply
        """
        result = ScopeReviewResult(
            triggered_at=datetime.now().isoformat(),
            iteration=iteration,
            trigger_type=trigger_type,
            prd_hash=get_prd_hash(self.repo_root),
            changes=[],
        )

        last_prd_hash = self.state.get("last_prd_hash_scoped", "")
        current_prd_hash = get_prd_hash(self.repo_root)

        if last_prd_hash != current_prd_hash:
            prd_changes = self._detect_prd_changes(last_prd_hash, prd_content)
            if prd_changes:
                result.changes.extend(prd_changes)
                result.needs_full_rescoping = True

        criteria_issues = self._validate_acceptance_criteria(tracker)
        result.changes.extend(criteria_issues)

        conflicts = self._detect_criteria_conflicts(tracker)
        if conflicts:
            result.changes.extend(conflicts)

        if prd_content:
            checkbox_stats = self._get_prd_checkbox_stats(prd_content)
            tracker_completion = self._get_tracker_completion_rate(tracker)

            if (
                abs(tracker_completion - checkbox_stats.get("completion_rate", 0))
                > 0.15
            ):
                result.changes.append(
                    ScopeChange(
                        type="warning",
                        description=(
                            f"Tracker completion ({tracker_completion:.1%}) "
                            f"differs from PRD checkbox heuristic "
                            f"({checkbox_stats.get('completion_rate', 0):.1%})"
                        ),
                        reason="potential scope mismatch",
                        severity="warning",
                    )
                )

        self.state["last_scope_review_iteration"] = iteration
        self.state["last_prd_hash_scoped"] = current_prd_hash
        if result.needs_full_rescoping:
            self.state["stall_count"] = self.state.get("stall_count", 0) + 1
        self._save_state()

        return result

    def _detect_prd_changes(
        self, old_prd_hash: str, prd_content: Optional[str]
    ) -> List[ScopeChange]:
        """Detect changes in PRD since last review."""
        changes = []

        if not prd_content:
            return changes

        lines = prd_content.split("\n")
        sections = self._extract_sections(lines)

        for section in sections:
            section_hash = compute_file_hash(section["content"])

            if len(section["content"]) > 100:
                changes.append(
                    ScopeChange(
                        type="invalidate_tasks",
                        description=f"PRD section '{section['title']}' may have changed",
                        reason="PRD hash changed",
                        severity="warning",
                    )
                )

        return changes

    def _extract_sections(self, lines: List[str]) -> List[Dict[str, Any]]:
        """Extract markdown sections from PRD content."""
        sections = []
        current_section = None

        for line in lines:
            if line.startswith("## "):
                if current_section:
                    sections.append(current_section)
                current_section = {"title": line[3:], "content": ""}
            elif current_section:
                current_section["content"] += line + "\n"

        if current_section:
            sections.append(current_section)

        return sections

    def _validate_acceptance_criteria(
        self, tracker: Dict[str, Any]
    ) -> List[ScopeChange]:
        """Check that all features have verifiable acceptance criteria."""
        issues = []

        for feature in tracker.get("features", []):
            feature_id = feature.get("id")
            criteria = feature.get("acceptance_criteria", [])

            if not criteria:
                issues.append(
                    ScopeChange(
                        type="add_criteria",
                        feature_id=feature_id,
                        description=(
                            f"Feature '{feature_id}' has no acceptance criteria. "
                            f"Add at least one verifiable criterion (unit_test, integration_test, "
                            f"user_journey, etc.)"
                        ),
                        reason="missing acceptance criteria",
                        severity="error",
                    )
                )
                continue

            verifiable_types = [
                "unit_test",
                "integration_test",
                "e2e_test",
                "user_journey",
                "ml_evaluation",
                "code_review",
            ]
            has_verifiable = any(c.get("type") in verifiable_types for c in criteria)

            if not has_verifiable:
                issues.append(
                    ScopeChange(
                        type="add_criteria",
                        feature_id=feature_id,
                        description=(
                            f"Feature '{feature_id}' has no verifiable criteria. "
                            f"Add at least one criterion with type in: "
                            f"{', '.join(verifiable_types)}"
                        ),
                        reason="no verifiable acceptance criteria",
                        severity="warning",
                    )
                )

        return issues

    def _detect_criteria_conflicts(self, tracker: Dict[str, Any]) -> List[ScopeChange]:
        """Detect duplicate or conflicting acceptance criteria."""
        conflicts = []
        seen_criteria = set()

        for feature in tracker.get("features", []):
            feature_id = feature.get("id")
            for criterion in feature.get("acceptance_criteria", []):
                criterion_id = criterion.get("id")
                key = f"{feature_id}:{criterion.get('type')}:{criterion.get('description')}"

                if key in seen_criteria:
                    conflicts.append(
                        ScopeChange(
                            type="warning",
                            feature_id=feature_id,
                            criterion_id=criterion_id,
                            description=(
                                f"Duplicate acceptance criterion detected: "
                                f"'{criterion.get('description')}'"
                            ),
                            reason="duplicate acceptance criteria",
                            severity="warning",
                        )
                    )
                else:
                    seen_criteria.add(key)

        return conflicts

    def _get_prd_checkbox_stats(self, prd_content: str) -> Dict[str, float]:
        """Extract checkbox statistics from PRD."""
        total_checkboxes = prd_content.count("- [ ]") + prd_content.count("- [x]")
        checked_checkboxes = prd_content.count("- [x]")

        if total_checkboxes == 0:
            return {"total": 0, "completed": 0, "completion_rate": 100.0}

        completion_rate = (checked_checkboxes / total_checkboxes) * 100
        return {
            "total": total_checkboxes,
            "completed": checked_checkboxes,
            "completion_rate": completion_rate,
        }

    def _get_tracker_completion_rate(self, tracker: Dict[str, Any]) -> float:
        """Calculate overall feature completion rate from tracker."""
        features = tracker.get("features", [])
        if not features:
            return 100.0

        completed = sum(1 for f in features if f.get("status") == "verified")
        return (completed / len(features)) * 100

    def record_failure(
        self,
        phase: str,
        gate_name: str,
        error_type: str,
        error_message: str,
        stack_frame: Optional[str] = None,
    ) -> None:
        """Record a failure for pattern detection."""
        path_normalized = re.sub(r"[/\\][\w\-\.]+\d*:?\d*", "<path>", error_message)
        timestamp_normalized = re.sub(
            r"\d{4}-\d{2}-\d{2}", "<timestamp>", path_normalized
        )
        number_normalized = re.sub(r"\b\d+\b", "<n>", timestamp_normalized)
        whitespace_normalized = " ".join(number_normalized.split())
        normalized_error = whitespace_normalized.lower()

        key = f"{phase}:{gate_name}:{error_type}:{hash(normalized_error)}"

        now = datetime.now().isoformat()

        if key in self.failure_fingerprints:
            fp = self.failure_fingerprints[key]
            fp.count += 1
            fp.last_seen = now
        else:
            fp = FailureFingerprint(
                phase=phase,
                gate_name=gate_name,
                error_type=error_type,
                normalized_error=normalized_error,
                stack_frame=stack_frame,
                count=1,
                first_seen=now,
                last_seen=now,
            )
            self.failure_fingerprints[key] = fp

        self._save_fingerprints()

        recent_failures = self.state.get("recent_verification_failures", 0)
        if gate_name.startswith("verification"):
            self.state["recent_verification_failures"] = recent_failures + 1
            self._save_state()

    def get_repeated_failures(self, threshold: int = 2) -> List[FailureFingerprint]:
        """Get failures that repeated enough to become guardrail signs."""
        return [
            fp
            for fp in self.failure_fingerprints.values()
            if fp.should_become_sign(threshold)
        ]

    def evolve_guardrails_from_failures(
        self, threshold: int = 2, iteration: int = 0
    ) -> List[str]:
        """
        Analyze repeated failures and create guardrail signs.

        Args:
            threshold: Minimum repetition count to become a sign (default: 2)
            iteration: Current iteration number for sign tracking (default: 0)

        Returns:
            List of trigger descriptions for signs that were created
        """
        repeated_failures = self.get_repeated_failures(threshold)
        signs_created = []

        for fp in repeated_failures:
            sign_name = f"repeated_{fp.gate_name}_{fp.error_type}".replace(" ", "_")
            trigger = f"When running verifier '{fp.gate_name}' (phase: {fp.phase})"
            instruction = (
                f"Before re-running:\n"
                f"1. Check if error is transient (network timeouts, rate limits)\n"
                f"2. Verify dependencies are installed\n"
                f"3. Review stack trace: {fp.stack_frame or 'N/A'}\n"
                f"4. Pattern: Failed {fp.count} times with '{fp.normalized_error}'"
            )

            add_sign(
                name=sign_name,
                trigger=trigger,
                instruction=instruction,
                iteration=iteration,
                repo_root=self.repo_root,
                category=fp.error_type,
                phase=fp.phase,
            )
            signs_created.append(trigger)

        if signs_created:
            print(
                f"🛡️  Evolved {len(signs_created)} guardrails from {len(repeated_failures)} repeated failures"
            )

        return signs_created
