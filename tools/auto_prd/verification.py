"""Verification Protocol - Requires explicit verification before marking features complete.

This module implements the verification protocol from Anthropic's
"Effective Harnesses for Long-Running Agents". Key principle:
- NEVER mark a feature complete without end-to-end verification

Verification includes:
1. Unit tests for individual components
2. Integration tests for component interactions
3. E2E tests for user-facing features
4. Quality gates (type checks, linting, etc.)
5. Collecting evidence (test outputs, screenshots)
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .command import run_cmd
from .logging_utils import logger


@dataclass
class TestResult:
    """Result of running a test suite."""

    name: str
    passed: bool
    output: str
    exit_code: int
    duration_seconds: float = 0.0
    tests_run: int = 0
    tests_failed: int = 0


@dataclass
class QualityGateResult:
    """Result of a quality gate check."""

    gate: str
    requirement: str
    passed: bool
    output: str
    details: str = ""
    skipped: bool = False


@dataclass
class VerificationEvidence:
    """Evidence collected during verification."""

    test_output_logs: list[str] = field(default_factory=list)
    screenshots: list[str] = field(default_factory=list)
    verified_at: str = ""
    verified_by: str = ""
    duration_seconds: float = 0.0


@dataclass
class VerificationResult:
    """Complete verification result for a feature."""

    feature_id: str
    passed: bool
    unit_tests: list[TestResult] = field(default_factory=list)
    integration_tests: list[TestResult] = field(default_factory=list)
    e2e_tests: list[TestResult] = field(default_factory=list)
    quality_gates: list[QualityGateResult] = field(default_factory=list)
    evidence: VerificationEvidence = field(default_factory=VerificationEvidence)
    errors: list[str] = field(default_factory=list)

    @property
    def all_tests_passing(self) -> bool:
        """Check if all tests are passing."""
        all_tests = self.unit_tests + self.integration_tests + self.e2e_tests
        return all(t.passed for t in all_tests) if all_tests else True

    @property
    def all_gates_passing(self) -> bool:
        """Check if all quality gates are passing."""
        return all(g.passed for g in self.quality_gates) if self.quality_gates else True


class VerificationProtocol:
    """Verification required before marking feature complete.

    This protocol ensures features are properly validated before
    being marked as complete. It runs:
    1. Unit tests
    2. Integration tests
    3. E2E tests (if applicable)
    4. Quality gates

    And collects evidence for audit purposes.

    Usage:
        verifier = VerificationProtocol(repo_root)
        result = verifier.verify_feature(feature)
        if result.passed:
            feature["status"] = "verified"
            feature["verification_evidence"] = result.evidence
    """

    def __init__(
        self,
        repo_root: Path,
        timeout_seconds: int = 300,
        dry_run: bool = False,
    ):
        """Initialize the verification protocol.

        Args:
            repo_root: Repository root directory
            timeout_seconds: Timeout for test commands
            dry_run: If True, skip actual verification
        """
        self.repo_root = repo_root
        self.timeout_seconds = timeout_seconds
        self.dry_run = dry_run
        self._evidence_dir = repo_root / ".aprd" / "evidence"

    def verify_feature(
        self,
        feature: dict[str, Any],
        tracker: dict[str, Any] | None = None,
    ) -> VerificationResult:
        """Verify a feature meets all acceptance criteria.

        Args:
            feature: Feature dictionary from tracker
            tracker: Optional tracker to update with results

        Returns:
            VerificationResult with all test and gate results
        """
        import time

        start_time = time.time()
        feature_id = feature.get("id", "unknown")

        logger.info("Starting verification for feature %s", feature_id)

        if self.dry_run:
            logger.info("Dry run: skipping actual verification")
            return VerificationResult(
                feature_id=feature_id,
                passed=True,
                evidence=VerificationEvidence(
                    verified_at=datetime.now(timezone.utc).isoformat(),
                    verified_by="dry_run",
                ),
            )

        # Run unit tests
        unit_results = self._run_unit_tests(feature)

        # Run integration tests
        integration_results = self._run_integration_tests(feature)

        # Run e2e tests (if defined)
        e2e_results = self._run_e2e_tests(feature)

        # Run quality gates
        gate_results = self._run_quality_gates(feature)

        # Collect evidence
        duration = time.time() - start_time
        evidence = self._collect_evidence(
            feature_id, unit_results, integration_results, e2e_results, duration
        )

        # Determine overall pass/fail
        all_unit_pass = all(r.passed for r in unit_results)
        all_integration_pass = all(r.passed for r in integration_results)
        all_e2e_pass = all(r.passed for r in e2e_results)
        all_gates_pass = all(g.passed for g in gate_results)

        passed = (
            all_unit_pass and all_integration_pass and all_e2e_pass and all_gates_pass
        )

        result = VerificationResult(
            feature_id=feature_id,
            passed=passed,
            unit_tests=unit_results,
            integration_tests=integration_results,
            e2e_tests=e2e_results,
            quality_gates=gate_results,
            evidence=evidence,
        )

        # Update tracker if provided
        if tracker and passed:
            self._update_tracker_with_results(tracker, feature_id, result)

        logger.info(
            "Verification %s for feature %s (%.1fs)",
            "PASSED" if passed else "FAILED",
            feature_id,
            duration,
        )

        return result

    def _run_unit_tests(self, feature: dict[str, Any]) -> list[TestResult]:
        """Run unit tests for a feature.

        Args:
            feature: Feature dictionary

        Returns:
            List of TestResult objects
        """
        results: list[TestResult] = []
        testing = feature.get("testing", {})
        unit_tests = testing.get("unit_tests", [])

        if not unit_tests:
            # Run general test suite
            result = self._run_test_command(
                "unit_tests",
                self._detect_test_command("unit"),
            )
            if result:
                results.append(result)
            return results

        # Run specific test files if defined
        for test in unit_tests:
            file_path = test.get("file_path")
            if not file_path:
                logger.warning("Unit test entry missing file_path, skipping")
                test["status"] = "skipped"
                continue
            if not Path(file_path).exists():
                logger.warning(f"Unit test file not found: {file_path}, skipping")
                test["status"] = "skipped"
                continue
            cmd = self._build_test_command_for_file(file_path)
            if not cmd:
                logger.warning(f"Could not build test command for: {file_path}")
                test["status"] = "skipped"
                continue
            result = self._run_test_command(test.get("description", file_path), cmd)
            if result:
                results.append(result)
                # Update test status in tracker
                test["status"] = "passing" if result.passed else "failing"

        return results

    def _run_integration_tests(self, feature: dict[str, Any]) -> list[TestResult]:
        """Run integration tests for a feature.

        Args:
            feature: Feature dictionary

        Returns:
            List of TestResult objects
        """
        results: list[TestResult] = []
        testing = feature.get("testing", {})
        integration_tests = testing.get("integration_tests", [])

        if not integration_tests:
            return results

        for test in integration_tests:
            file_path = test.get("file_path")
            if not file_path:
                logger.warning("Integration test entry missing file_path, skipping")
                test["status"] = "skipped"
                continue
            if not Path(file_path).exists():
                logger.warning(
                    f"Integration test file not found: {file_path}, skipping"
                )
                test["status"] = "skipped"
                continue
            cmd = self._build_test_command_for_file(file_path)
            if not cmd:
                logger.warning(f"Could not build test command for: {file_path}")
                test["status"] = "skipped"
                continue
            result = self._run_test_command(test.get("description", file_path), cmd)
            if result:
                results.append(result)
                test["status"] = "passing" if result.passed else "failing"

        return results

    def _run_e2e_tests(self, feature: dict[str, Any]) -> list[TestResult]:
        """Run e2e tests for a feature.

        Args:
            feature: Feature dictionary

        Returns:
            List of TestResult objects
        """
        results: list[TestResult] = []
        testing = feature.get("testing", {})
        e2e_tests = testing.get("e2e_tests", [])

        if not e2e_tests:
            return results

        for test in e2e_tests:
            file_path = test.get("file_path")
            if not file_path:
                logger.warning("E2E test entry missing file_path, skipping")
                test["status"] = "skipped"
                continue
            if not Path(file_path).exists():
                logger.warning(f"E2E test file not found: {file_path}, skipping")
                test["status"] = "skipped"
                continue
            cmd = self._build_test_command_for_file(file_path, e2e=True)
            if not cmd:
                logger.warning(f"Could not build test command for: {file_path}")
                test["status"] = "skipped"
                continue
            result = self._run_test_command(test.get("scenario", file_path), cmd)
            if result:
                results.append(result)
                test["status"] = "passing" if result.passed else "failing"

        return results

    def _run_quality_gates(self, feature: dict[str, Any]) -> list[QualityGateResult]:
        """Run quality gates for a feature.

        Args:
            feature: Feature dictionary

        Returns:
            List of QualityGateResult objects
        """
        results: list[QualityGateResult] = []
        validation = feature.get("validation", {})
        quality_gates = validation.get("quality_gates", [])

        # Add default gates if none defined
        if not quality_gates:
            quality_gates = [
                {"gate": "Type Check", "requirement": "No type errors"},
                {"gate": "Lint Check", "requirement": "No lint errors"},
                {"gate": "Tests Pass", "requirement": "All tests pass"},
            ]

        for gate in quality_gates:
            gate_name = gate.get("gate", "Unknown")
            requirement = gate.get("requirement", "Must pass")

            result = self._run_quality_gate(gate_name, requirement)
            results.append(result)

            # Update gate status in tracker
            gate["passed"] = result.passed

        return results

    def _run_quality_gate(self, gate_name: str, requirement: str) -> QualityGateResult:
        """Run a specific quality gate.

        Args:
            gate_name: Name of the gate
            requirement: What must pass

        Returns:
            QualityGateResult
        """
        gate_lower = gate_name.lower()

        # Map gate names to commands
        gate_commands: dict[str, list[list[str]]] = {
            "type": [
                ["npx", "tsc", "--noEmit"],
                ["mypy", "."],
                ["cargo", "check"],
            ],
            "lint": [
                ["npm", "run", "lint"],
                ["pnpm", "lint"],
                ["ruff", "check", "."],
                ["cargo", "clippy"],
            ],
            "test": [
                ["make", "test"],
                ["npm", "test"],
                ["pytest"],
            ],
            "format": [
                ["npm", "run", "format:check"],
                ["ruff", "format", "--check", "."],
                ["cargo", "fmt", "--check"],
            ],
        }

        # Find matching gate
        commands: list[list[str]] = []
        for key, cmds in gate_commands.items():
            if key in gate_lower:
                commands = cmds
                break

        if not commands:
            logger.warning("No verification command found for gate: %s", gate_name)
            return QualityGateResult(
                gate=gate_name,
                requirement=requirement,
                passed=False,
                output="No verification command found",
                skipped=True,
            )

        # Try each command until one works
        for cmd in commands:
            try:
                out, err, exit_code = run_cmd(
                    cmd,
                    cwd=self.repo_root,
                    check=False,
                    timeout=self.timeout_seconds,
                )
                output = out + ("\n" + err if err else "")
                return QualityGateResult(
                    gate=gate_name,
                    requirement=requirement,
                    passed=(exit_code == 0),
                    output=output[:1000],  # Truncate
                )
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue
            except subprocess.TimeoutExpired:
                return QualityGateResult(
                    gate=gate_name,
                    requirement=requirement,
                    passed=False,
                    output=f"Gate timed out after {self.timeout_seconds}s",
                )

        logger.warning("No applicable command succeeded for gate: %s", gate_name)
        return QualityGateResult(
            gate=gate_name,
            requirement=requirement,
            passed=False,
            output="No applicable command succeeded",
            skipped=True,
        )

    def _run_test_command(self, name: str, cmd: list[str] | None) -> TestResult | None:
        """Run a test command and return results.

        Args:
            name: Test name for logging
            cmd: Command to run

        Returns:
            TestResult or None if command not available
        """
        if not cmd:
            return None

        import time

        start = time.time()

        try:
            out, err, exit_code = run_cmd(
                cmd,
                cwd=self.repo_root,
                check=False,
                timeout=self.timeout_seconds,
            )
            duration = time.time() - start
            output = out + ("\n" + err if err else "")

            return TestResult(
                name=name,
                passed=(exit_code == 0),
                output=output,
                exit_code=exit_code,
                duration_seconds=duration,
            )
        except subprocess.TimeoutExpired:
            return TestResult(
                name=name,
                passed=False,
                output=f"Test timed out after {self.timeout_seconds}s",
                exit_code=-1,
                duration_seconds=self.timeout_seconds,
            )
        except FileNotFoundError:
            return None

    def _detect_test_command(self, test_type: str) -> list[str] | None:
        """Detect the appropriate test command for the project.

        Args:
            test_type: Type of test (unit, integration, e2e)

        Returns:
            Command list or None
        """
        # Check for Makefile targets
        if (self.repo_root / "Makefile").exists():
            if test_type == "unit":
                return ["make", "test"]
            elif test_type == "e2e":
                return ["make", "test:e2e"]

        # Check for package.json scripts
        if (self.repo_root / "package.json").exists():
            if test_type == "unit":
                return ["npm", "test"]
            elif test_type == "e2e":
                return ["npm", "run", "test:e2e"]

        # Check for pytest
        if (self.repo_root / "pyproject.toml").exists():
            return ["pytest"]

        return None

    def _build_test_command_for_file(
        self, file_path: str, e2e: bool = False
    ) -> list[str] | None:
        """Build a test command for a specific file.

        Args:
            file_path: Path to test file
            e2e: Whether this is an e2e test

        Returns:
            Command list or None
        """
        path = Path(file_path)
        suffix = path.suffix.lower()

        if suffix in (".ts", ".tsx", ".js", ".jsx"):
            if e2e:
                return ["npx", "playwright", "test", file_path]
            return ["npx", "jest", file_path]
        elif suffix == ".py":
            return ["pytest", file_path]
        elif suffix == ".go":
            # Go test requires package path, not file path
            # Derive package directory from file's parent
            parent_dir = path.parent
            if parent_dir == Path(".") or str(parent_dir) == "":
                # File is in root directory
                pkg_path = "./..."
            else:
                # Use relative package path with ./ prefix
                pkg_path = f"./{parent_dir}"
            return ["go", "test", "-v", pkg_path]

        return None

    def _collect_evidence(
        self,
        feature_id: str,
        unit_results: list[TestResult],
        integration_results: list[TestResult],
        e2e_results: list[TestResult],
        duration: float,
    ) -> VerificationEvidence:
        """Collect verification evidence.

        Args:
            feature_id: Feature being verified
            unit_results: Unit test results
            integration_results: Integration test results
            e2e_results: E2E test results
            duration: Total verification duration

        Returns:
            VerificationEvidence object
        """
        # Create evidence directory
        self._evidence_dir.mkdir(parents=True, exist_ok=True)
        feature_evidence_dir = self._evidence_dir / feature_id
        feature_evidence_dir.mkdir(exist_ok=True)

        test_logs: list[str] = []

        # Save test outputs
        all_results = unit_results + integration_results + e2e_results
        for i, result in enumerate(all_results):
            log_file = feature_evidence_dir / f"test_{i}_{result.name}.log"
            log_file.write_text(result.output)
            test_logs.append(str(log_file))

        return VerificationEvidence(
            test_output_logs=test_logs,
            screenshots=[],  # Would be populated by e2e tests
            verified_at=datetime.now(timezone.utc).isoformat(),
            verified_by="verification_protocol",
            duration_seconds=duration,
        )

    def _update_tracker_with_results(
        self,
        tracker: dict[str, Any],
        feature_id: str,
        result: VerificationResult,
    ) -> None:
        """Update tracker with verification results.

        Args:
            tracker: Tracker dictionary
            feature_id: Feature ID
            result: Verification result
        """
        for feature in tracker.get("features", []):
            if feature.get("id") == feature_id:
                feature["verification_evidence"] = {
                    "verified_at": result.evidence.verified_at,
                    "verified_by": result.evidence.verified_by,
                    "test_output_logs": result.evidence.test_output_logs,
                    "screenshots": result.evidence.screenshots,
                }

                # Update acceptance criteria status
                for criterion in feature.get("acceptance_criteria", []):
                    # Mark as passed if all relevant tests pass
                    method = criterion.get("verification_method", "")
                    if method == "unit_test" and result.all_tests_passing:
                        criterion["status"] = "passed"
                    elif method == "type_check":
                        type_gate = next(
                            (
                                g
                                for g in result.quality_gates
                                if "type" in g.gate.lower()
                            ),
                            None,
                        )
                        if type_gate and type_gate.passed:
                            criterion["status"] = "passed"
                    elif method == "lint_check":
                        lint_gate = next(
                            (
                                g
                                for g in result.quality_gates
                                if "lint" in g.gate.lower()
                            ),
                            None,
                        )
                        if lint_gate and lint_gate.passed:
                            criterion["status"] = "passed"

                break


def verify_feature(
    feature: dict[str, Any],
    repo_root: Path,
    tracker: dict[str, Any] | None = None,
    timeout_seconds: int = 300,
    dry_run: bool = False,
) -> VerificationResult:
    """Convenience function to verify a feature.

    Args:
        feature: Feature dictionary from tracker
        repo_root: Repository root directory
        tracker: Optional tracker to update with results
        timeout_seconds: Timeout for test commands
        dry_run: If True, skip actual verification

    Returns:
        VerificationResult with all test and gate results
    """
    protocol = VerificationProtocol(
        repo_root=repo_root,
        timeout_seconds=timeout_seconds,
        dry_run=dry_run,
    )
    return protocol.verify_feature(feature, tracker)
