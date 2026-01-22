"""Pluggable verification monitoring for support-mode.

Supports multiple verification backends:
- pytest: Run pytest and parse results
- custom: Run custom command and parse exit code
- manual: Manual verification state from tracker

This allows verification monitoring to work with different test frameworks
and quality gate systems.
"""

from __future__ import annotations

import json
import logging
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from .command import run_cmd

logger = logging.getLogger(__name__)


class VerificationStatus(str, Enum):
    """Verification status values."""

    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    STALE = "stale"


@dataclass
class TestResult:
    """Result of a single test/check."""

    name: str
    status: VerificationStatus = VerificationStatus.PENDING
    duration: float = 0.0
    message: str = ""


@dataclass
class VerificationSummary:
    """Summary of a verification run."""

    backend: str
    status: VerificationStatus = VerificationStatus.PENDING
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    duration: float = 0.0
    results: list[TestResult] = field(default_factory=list)


class VerificationBackend(ABC):
    """Abstract base for verification backends."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Backend name."""

    @abstractmethod
    def run(self, repo_root: Path, **kwargs: Any) -> VerificationSummary:
        """Run verification.

        Args:
            repo_root: Repository root directory.
            **kwargs: Additional backend-specific options.

        Returns:
            VerificationSummary with results.
        """

    def is_available(self, repo_root: Path) -> bool:
        """Check if backend is available.

        Args:
            repo_root: Repository root directory.

        Returns:
            True if backend can be used.
        """
        return True


class PytestBackend(VerificationBackend):
    """Pytest test runner backend."""

    def __init__(self) -> None:
        """Initialize pytest backend."""
        self._name = "pytest"

    @property
    def name(self) -> str:
        """Backend name."""
        return self._name

    def is_available(self, repo_root: Path) -> bool:
        """Check if pytest is available."""
        try:
            run_cmd(["pytest", "--version"], cwd=repo_root, check=False, capture=True)
            return True
        except (OSError, FileNotFoundError):
            return False

    def run(
        self,
        repo_root: Path,
        test_path: str | None = None,
        args: list[str] | None = None,
        **kwargs: Any,
    ) -> VerificationSummary:
        """Run pytest tests.

        Args:
            repo_root: Repository root.
            test_path: Specific test path or directory.
            args: Additional pytest arguments.

        Returns:
            VerificationSummary with test results.
        """
        import time

        cmd = ["pytest", "-v", "--tb=no"]
        if test_path:
            cmd.append(test_path)
        if args:
            cmd.extend(args)

        # Add JSON output if pytest-json-report is available
        try:
            cmd.extend(["--json-report", "--json-report-file=/dev/stdout"])
        except (OSError, ValueError):
            pass

        start = time.time()
        try:
            stdout, stderr, exit_code = run_cmd(cmd, cwd=repo_root, check=False)
        except (OSError, subprocess.CalledProcessError) as e:
            return VerificationSummary(
                backend=self.name,
                status=VerificationStatus.FAILED,
                duration=time.time() - start,
                results=[
                    TestResult(
                        name="pytest", status=VerificationStatus.FAILED, message=str(e)
                    )
                ],
            )

        duration = time.time() - start

        # Parse pytest output
        results = self._parse_pytest_output(stdout)

        # Count results
        passed = sum(1 for r in results if r.status == VerificationStatus.PASSED)
        failed = sum(1 for r in results if r.status == VerificationStatus.FAILED)
        skipped = sum(1 for r in results if r.status == VerificationStatus.SKIPPED)

        status = (
            VerificationStatus.PASSED if exit_code == 0 else VerificationStatus.FAILED
        )
        if failed == 0 and passed == 0:
            status = VerificationStatus.SKIPPED

        return VerificationSummary(
            backend=self.name,
            status=status,
            total=len(results),
            passed=passed,
            failed=failed,
            skipped=skipped,
            duration=duration,
            results=results,
        )

    def _parse_pytest_output(self, output: str) -> list[TestResult]:
        """Parse pytest stdout for test results.

        Args:
            output: Pytest stdout.

        Returns:
            List of TestResult.
        """
        results = []
        for line in output.splitlines():
            line = line.strip()
            # Match lines like "tests/test_foo.py::test_bar PASSED"
            if " PASSED" in line or " FAILED" in line or " SKIPPED" in line:
                parts = line.split()
                if len(parts) >= 2:
                    name = parts[0]
                    status_str = parts[1]
                    if "PASSED" in status_str:
                        status = VerificationStatus.PASSED
                    elif "FAILED" in status_str:
                        status = VerificationStatus.FAILED
                    elif "SKIPPED" in status_str or "SKIP" in status_str:
                        status = VerificationStatus.SKIPPED
                    else:
                        status = VerificationStatus.PENDING

                    results.append(TestResult(name=name, status=status))
        return results


class CustomBackend(VerificationBackend):
    """Custom command backend."""

    def __init__(self, command: list[str]) -> None:
        """Initialize custom backend.

        Args:
            command: Command to run (list of strings).
        """
        self._command = command

    @property
    def name(self) -> str:
        """Backend name."""
        return f"custom:{self._command[0]}"

    def run(self, repo_root: Path, **kwargs: Any) -> VerificationSummary:
        """Run custom command.

        Args:
            repo_root: Repository root.
            **kwargs: Additional options (ignored).

        Returns:
            VerificationSummary with results.
        """
        import time

        start = time.time()
        try:
            stdout, stderr, exit_code = run_cmd(
                self._command, cwd=repo_root, check=False
            )
        except (OSError, subprocess.CalledProcessError) as e:
            return VerificationSummary(
                backend=self.name,
                status=VerificationStatus.FAILED,
                duration=time.time() - start,
                results=[
                    TestResult(
                        name=self._command[0],
                        status=VerificationStatus.FAILED,
                        message=str(e),
                    )
                ],
            )

        duration = time.time() - start
        status = (
            VerificationStatus.PASSED if exit_code == 0 else VerificationStatus.FAILED
        )

        return VerificationSummary(
            backend=self.name,
            status=status,
            total=1,
            passed=1 if status == VerificationStatus.PASSED else 0,
            failed=0 if status == VerificationStatus.PASSED else 1,
            duration=duration,
            results=[
                TestResult(
                    name=self._command[0],
                    status=status,
                    message=stderr if stderr else stdout,
                )
            ],
        )


class ManualBackend(VerificationBackend):
    """Manual verification backend - reads from tracker state.

    This backend doesn't run tests but reads the manual verification
    status from the tracker.json file.
    """

    @property
    def name(self) -> str:
        """Backend name."""
        return "manual"

    def run(self, repo_root: Path, **kwargs: Any) -> VerificationSummary:
        """Read manual verification status from tracker.

        Args:
            repo_root: Repository root.
            **kwargs: Additional options (ignored).

        Returns:
            VerificationSummary with manual verification status.
        """
        from .tracker import get_tracker_path, load_tracker

        tracker_path = get_tracker_path(repo_root)
        tracker = load_tracker(repo_root)

        if tracker is None:
            return VerificationSummary(
                backend=self.name,
                status=VerificationStatus.PENDING,
                results=[
                    TestResult(
                        name="tracker",
                        status=VerificationStatus.PENDING,
                        message="No tracker found",
                    )
                ],
            )

        # Count verification status from features
        results = []
        passed = 0
        failed = 0
        skipped = 0

        for feature in tracker.get("features", []):
            for ac in feature.get("acceptance_criteria", []):
                ac_status = ac.get("verification_status", "pending")
                ac_id = ac.get("id", "unknown")
                name = f"{feature.get('id', 'unknown')}:{ac_id}"

                if ac_status == "verified":
                    status = VerificationStatus.PASSED
                    passed += 1
                elif ac_status == "failed":
                    status = VerificationStatus.FAILED
                    failed += 1
                elif ac_status == "skipped":
                    status = VerificationStatus.SKIPPED
                    skipped += 1
                else:
                    status = VerificationStatus.PENDING

                results.append(TestResult(name=name, status=status))

        total = len(results)
        overall_status = VerificationStatus.PENDING
        if failed > 0:
            overall_status = VerificationStatus.FAILED
        elif passed == total and total > 0:
            overall_status = VerificationStatus.PASSED
        elif skipped == total:
            overall_status = VerificationStatus.SKIPPED

        return VerificationSummary(
            backend=self.name,
            status=overall_status,
            total=total,
            passed=passed,
            failed=failed,
            skipped=skipped,
            results=results,
        )


class VerificationMonitor:
    """Monitor verification runs across multiple backends.

    Supports multiple tracker formats:
    - .aprd/tracker.json (auto_prd format)
    - .taskmaster/tracker.json (taskmaster format)
    - tasks.json (simple format)
    """

    def __init__(self, backends: list[VerificationBackend] | None = None) -> None:
        """Initialize verification monitor.

        Args:
            backends: List of verification backends to use.
        """
        self.backends = backends or []
        self._results: dict[str, VerificationSummary] = {}

    def add_backend(self, backend: VerificationBackend) -> None:
        """Add a verification backend.

        Args:
            backend: Backend to add.
        """
        self.backends.append(backend)

    def run_all(self, repo_root: Path) -> dict[str, VerificationSummary]:
        """Run all verification backends.

        Args:
            repo_root: Repository root.

        Returns:
            Dictionary mapping backend name to results.
        """
        results = {}
        for backend in self.backends:
            if not backend.is_available(repo_root):
                logger.debug(f"Backend {backend.name} not available, skipping")
                continue

            try:
                summary = backend.run(repo_root)
                results[backend.name] = summary
            except Exception as e:
                logger.exception(f"Backend {backend.name} failed: {e}")
                results[backend.name] = VerificationSummary(
                    backend=backend.name,
                    status=VerificationStatus.FAILED,
                    results=[
                        TestResult(
                            name=backend.name,
                            status=VerificationStatus.FAILED,
                            message=str(e),
                        )
                    ],
                )

        self._results = results
        return results

    def get_status(self) -> VerificationStatus:
        """Get overall verification status.

        Returns:
            Overall status (failed if any failed, pending if none run).
        """
        if not self._results:
            return VerificationStatus.PENDING

        for summary in self._results.values():
            if summary.status == VerificationStatus.FAILED:
                return VerificationStatus.FAILED

        return VerificationSummary.PASSED

    def load_tracker(
        self, repo_root: Path, tracker_format: str = "auto"
    ) -> dict[str, Any] | None:
        """Load tracker from repository.

        Supports multiple formats:
        - auto: Auto-detect format
        - aprd: .aprd/tracker.json
        - taskmaster: .taskmaster/tracker.json
        - tasks: tasks.json

        Args:
            repo_root: Repository root.
            tracker_format: Format to use.

        Returns:
            Tracker dictionary or None.
        """
        if tracker_format == "auto":
            # Try each format
            for fmt in ["aprd", "taskmaster", "tasks"]:
                tracker = self._load_tracker_format(repo_root, fmt)
                if tracker is not None:
                    return tracker
            return None
        else:
            return self._load_tracker_format(repo_root, tracker_format)

    def _load_tracker_format(self, repo_root: Path, fmt: str) -> dict[str, Any] | None:
        """Load tracker in specific format.

        Args:
            repo_root: Repository root.
            fmt: Format name.

        Returns:
            Tracker dictionary or None.
        """
        if fmt == "aprd":
            from .tracker import load_tracker as load_aprd_tracker

            return load_aprd_tracker(repo_root)
        elif fmt == "taskmaster":
            return self._load_taskmaster_tracker(repo_root)
        elif fmt == "tasks":
            return self._load_simple_tracker(repo_root)
        return None

    def _load_taskmaster_tracker(self, repo_root: Path) -> dict[str, Any] | None:
        """Load taskmaster format tracker."""
        path = repo_root / ".taskmaster" / "tracker.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return None

    def _load_simple_tracker(self, repo_root: Path) -> dict[str, Any] | None:
        """Load simple tasks.json format."""
        path = repo_root / "tasks.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return None
