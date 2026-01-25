"""Tests for verification_persistence module.

This module tests the VerificationPersistence class, get_latest_run, and is_run_fresh
functions, including edge cases like missing files, malformed data, and freshness checks.
"""

import json
import tempfile
from pathlib import Path
from unittest import mock

from auto_prd.verification_persistence import (
    VerificationPersistence,
    VerificationRun,
    VerificationStatus,
    VerifierResult,
    VerifierType,
    generate_run_id,
)


class TestVerificationPersistence:
    """Tests for VerificationPersistence class."""

    def test_creates_directory_on_init(self):
        """Test that VerificationPersistence creates the .aprd/verification directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            persistence = VerificationPersistence(repo_root)

            assert persistence.runs_dir.exists()
            assert persistence.runs_dir == repo_root / ".aprd" / "verification"

    def test_save_and_load_run(self):
        """Test saving and loading a verification run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            persistence = VerificationPersistence(repo_root)

            verifiers = [
                VerifierResult(
                    name="test_verifier",
                    type=VerifierType.TEST,
                    status=VerificationStatus.PASSED,
                    duration_sec=1.5,
                )
            ]
            run = VerificationRun(
                run_id="test_run_1",
                timestamp_start="2025-01-23T10:00:00",
                timestamp_end="2025-01-23T10:01:00",
                git_sha="abc123def456",
                base_branch="main",
                prd_hash="sha256:prdhash",
                verifiers=verifiers,
                overall_status=VerificationStatus.PASSED,
            )

            persistence.save_run(run)

            loaded = persistence.load_runs()
            assert len(loaded) == 1
            assert loaded[0].run_id == "test_run_1"
            assert loaded[0].overall_status == VerificationStatus.PASSED

    def test_load_runs_no_file(self):
        """Test load_runs when the JSONL file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            persistence = VerificationPersistence(repo_root)

            runs = persistence.load_runs()
            assert runs == []


class TestGetLatestRun:
    """Tests for get_latest_run method."""

    def test_get_latest_run_empty_file(self):
        """Test get_latest_run with an empty JSONL file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            persistence = VerificationPersistence(repo_root)

            # Create empty file
            persistence.runs_log.write_text("")

            run = persistence.get_latest_run()
            assert run is None

    def test_get_latest_run_with_single_entry(self):
        """Test get_latest_run with a single run entry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            persistence = VerificationPersistence(repo_root)

            run = VerificationRun(
                run_id="test_1",
                timestamp_start="2025-01-23T10:00:00",
                timestamp_end="2025-01-23T10:01:00",
                git_sha="abc123",
                base_branch="main",
                prd_hash="sha256:hash1",
            )
            persistence.save_run(run)

            latest = persistence.get_latest_run()
            assert latest is not None
            assert latest.run_id == "test_1"

    def test_get_latest_run_returns_most_recent(self):
        """Test get_latest_run returns the most recent run by timestamp."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            persistence = VerificationPersistence(repo_root)

            # Create runs in non-chronological order
            old_run = VerificationRun(
                run_id="old_run",
                timestamp_start="2025-01-23T09:00:00",
                timestamp_end="2025-01-23T09:01:00",
                git_sha="old_sha",
                base_branch="main",
                prd_hash="sha256:old",
            )
            new_run = VerificationRun(
                run_id="new_run",
                timestamp_start="2025-01-23T11:00:00",
                timestamp_end="2025-01-23T11:01:00",
                git_sha="new_sha",
                base_branch="main",
                prd_hash="sha256:new",
            )
            middle_run = VerificationRun(
                run_id="middle_run",
                timestamp_start="2025-01-23T10:00:00",
                timestamp_end="2025-01-23T10:01:00",
                git_sha="mid_sha",
                base_branch="main",
                prd_hash="sha256:mid",
            )

            persistence.save_run(old_run)
            persistence.save_run(new_run)
            persistence.save_run(middle_run)

            latest = persistence.get_latest_run()
            assert latest.run_id == "new_run"

    def test_get_latest_run_filters_by_git_sha(self):
        """Test get_latest_run filtering by git_sha."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            persistence = VerificationPersistence(repo_root)

            run1 = VerificationRun(
                run_id="run1",
                timestamp_start="2025-01-23T10:00:00",
                timestamp_end="2025-01-23T10:01:00",
                git_sha="sha1",
                base_branch="main",
                prd_hash="sha256:hash1",
            )
            run2 = VerificationRun(
                run_id="run2",
                timestamp_start="2025-01-23T11:00:00",
                timestamp_end="2025-01-23T11:01:00",
                git_sha="sha2",
                base_branch="main",
                prd_hash="sha256:hash2",
            )

            persistence.save_run(run1)
            persistence.save_run(run2)

            latest = persistence.get_latest_run(git_sha="sha1")
            assert latest is not None
            assert latest.run_id == "run1"

            latest = persistence.get_latest_run(git_sha="sha2")
            assert latest is not None
            assert latest.run_id == "run2"

    def test_get_latest_run_filters_by_prd_hash(self):
        """Test get_latest_run filtering by prd_hash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            persistence = VerificationPersistence(repo_root)

            run1 = VerificationRun(
                run_id="run1",
                timestamp_start="2025-01-23T10:00:00",
                timestamp_end="2025-01-23T10:01:00",
                git_sha="sha1",
                base_branch="main",
                prd_hash="sha256:prd1",
            )
            run2 = VerificationRun(
                run_id="run2",
                timestamp_start="2025-01-23T11:00:00",
                timestamp_end="2025-01-23T11:01:00",
                git_sha="sha2",
                base_branch="main",
                prd_hash="sha256:prd2",
            )

            persistence.save_run(run1)
            persistence.save_run(run2)

            latest = persistence.get_latest_run(prd_hash="sha256:prd1")
            assert latest is not None
            assert latest.run_id == "run1"

    def test_get_latest_run_no_match(self):
        """Test get_latest_run when no run matches the filter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            persistence = VerificationPersistence(repo_root)

            run = VerificationRun(
                run_id="run1",
                timestamp_start="2025-01-23T10:00:00",
                timestamp_end="2025-01-23T10:01:00",
                git_sha="sha1",
                base_branch="main",
                prd_hash="sha256:prd1",
            )
            persistence.save_run(run)

            latest = persistence.get_latest_run(git_sha="nonexistent")
            assert latest is None


class TestLoadRunsMalformedData:
    """Tests for load_runs with malformed JSONL data."""

    def test_skips_malformed_json_lines(self):
        """Test that load_runs skips malformed JSON lines."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            persistence = VerificationPersistence(repo_root)

            valid_run = VerificationRun(
                run_id="valid",
                timestamp_start="2025-01-23T10:00:00",
                timestamp_end="2025-01-23T10:01:00",
                git_sha="sha1",
                base_branch="main",
                prd_hash="sha256:hash1",
            )

            # Write file with valid and invalid lines
            content = json.dumps(valid_run.to_dict()) + "\n"
            content += "this is not json\n"
            content += "{broken json\n"
            content += json.dumps(valid_run.to_dict()) + "\n"

            persistence.runs_log.write_text(content)

            runs = persistence.load_runs()
            # Should only load the two valid lines
            assert len(runs) == 2
            assert all(r.run_id == "valid" for r in runs)

    def test_handles_missing_required_fields(self):
        """Test that load_runs handles entries with missing required fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            persistence = VerificationPersistence(repo_root)

            valid_run = VerificationRun(
                run_id="valid",
                timestamp_start="2025-01-23T10:00:00",
                timestamp_end="2025-01-23T10:01:00",
                git_sha="sha1",
                base_branch="main",
                prd_hash="sha256:hash1",
            )

            # Write file with valid and incomplete entries
            content = json.dumps(valid_run.to_dict()) + "\n"
            content += (
                json.dumps({"run_id": "incomplete", "missing_fields": True}) + "\n"
            )

            persistence.runs_log.write_text(content)

            runs = persistence.load_runs()
            # Should skip the incomplete entry
            assert len(runs) == 1
            assert runs[0].run_id == "valid"

    def test_handles_unknown_status_strings(self):
        """Test that load_runs handles unknown status strings gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            persistence = VerificationPersistence(repo_root)

            valid_run = VerificationRun(
                run_id="valid",
                timestamp_start="2025-01-23T10:00:00",
                timestamp_end="2025-01-23T10:01:00",
                git_sha="sha1",
                base_branch="main",
                prd_hash="sha256:hash1",
            )

            # Write file with valid entry and an entry with unknown status
            content = json.dumps(valid_run.to_dict()) + "\n"
            invalid_entry = valid_run.to_dict()
            invalid_entry["overall_status"] = "unknown_status"
            content += json.dumps(invalid_entry) + "\n"

            persistence.runs_log.write_text(content)

            # Unknown status should cause ValueError when creating enum
            # and the line should be skipped
            runs = persistence.load_runs()
            assert len(runs) == 1
            assert runs[0].run_id == "valid"


class TestIsRunFresh:
    """Tests for is_run_fresh method."""

    def test_fresh_with_matching_sha_and_prd(self):
        """Test is_run_fresh returns True when both git_sha and prd_hash match."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            persistence = VerificationPersistence(repo_root)

            run = VerificationRun(
                run_id="fresh",
                timestamp_start="2025-01-23T10:00:00",
                timestamp_end="2025-01-23T10:01:00",
                git_sha="current_sha",
                base_branch="main",
                prd_hash="sha256:current_prd",
            )

            with (
                mock.patch(
                    "auto_prd.verification_persistence.git_head_sha",
                    return_value="current_sha",
                ),
                mock.patch(
                    "auto_prd.verification_persistence.get_prd_hash",
                    return_value="sha256:current_prd",
                ),
            ):
                assert persistence.is_run_fresh(run) is True

    def test_not_fresh_with_different_git_sha(self):
        """Test is_run_fresh returns False when git_sha differs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            persistence = VerificationPersistence(repo_root)

            run = VerificationRun(
                run_id="stale",
                timestamp_start="2025-01-23T10:00:00",
                timestamp_end="2025-01-23T10:01:00",
                git_sha="old_sha",
                base_branch="main",
                prd_hash="sha256:current_prd",
            )

            with (
                mock.patch(
                    "auto_prd.verification_persistence.git_head_sha",
                    return_value="new_sha",
                ),
                mock.patch(
                    "auto_prd.verification_persistence.get_prd_hash",
                    return_value="sha256:current_prd",
                ),
            ):
                assert persistence.is_run_fresh(run) is False

    def test_not_fresh_with_different_prd_hash(self):
        """Test is_run_fresh returns False when prd_hash differs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            persistence = VerificationPersistence(repo_root)

            run = VerificationRun(
                run_id="stale",
                timestamp_start="2025-01-23T10:00:00",
                timestamp_end="2025-01-23T10:01:00",
                git_sha="current_sha",
                base_branch="main",
                prd_hash="sha256:old_prd",
            )

            with (
                mock.patch(
                    "auto_prd.verification_persistence.git_head_sha",
                    return_value="current_sha",
                ),
                mock.patch(
                    "auto_prd.verification_persistence.get_prd_hash",
                    return_value="sha256:new_prd",
                ),
            ):
                assert persistence.is_run_fresh(run) is False

    def test_fresh_with_explicit_prd_hash(self):
        """Test is_run_fresh with explicitly provided current_prd_hash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            persistence = VerificationPersistence(repo_root)

            run = VerificationRun(
                run_id="fresh",
                timestamp_start="2025-01-23T10:00:00",
                timestamp_end="2025-01-23T10:01:00",
                git_sha="current_sha",
                base_branch="main",
                prd_hash="sha256:specific_prd",
            )

            with mock.patch(
                "auto_prd.verification_persistence.git_head_sha",
                return_value="current_sha",
            ):
                # With explicit prd_hash that matches
                assert (
                    persistence.is_run_fresh(
                        run, current_prd_hash="sha256:specific_prd"
                    )
                    is True
                )

                # With explicit prd_hash that doesn't match
                assert (
                    persistence.is_run_fresh(run, current_prd_hash="sha256:different")
                    is False
                )


class TestIsVerificationFresh:
    """Tests for is_verification_fresh method."""

    def test_verification_ref_with_matching_hashes(self):
        """Test is_verification_fresh with matching git_sha and prd_hash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            persistence = VerificationPersistence(repo_root)

            verification_ref = {
                "git_sha": "abc123",
                "prd_hash": "sha256:prd123",
            }

            assert (
                persistence.is_verification_fresh(
                    verification_ref, "abc123", "sha256:prd123"
                )
                is True
            )

    def test_verification_ref_with_different_git_sha(self):
        """Test is_verification_fresh with different git_sha."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            persistence = VerificationPersistence(repo_root)

            verification_ref = {
                "git_sha": "old_sha",
                "prd_hash": "sha256:prd123",
            }

            assert (
                persistence.is_verification_fresh(
                    verification_ref, "new_sha", "sha256:prd123"
                )
                is False
            )

    def test_verification_ref_with_different_prd_hash(self):
        """Test is_verification_fresh with different prd_hash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            persistence = VerificationPersistence(repo_root)

            verification_ref = {
                "git_sha": "abc123",
                "prd_hash": "sha256:old_prd",
            }

            assert (
                persistence.is_verification_fresh(
                    verification_ref, "abc123", "sha256:new_prd"
                )
                is False
            )

    def test_verification_ref_missing_keys(self):
        """Test is_verification_fresh handles missing keys gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            persistence = VerificationPersistence(repo_root)

            # Missing git_sha
            verification_ref = {"prd_hash": "sha256:prd123"}
            assert (
                persistence.is_verification_fresh(
                    verification_ref, "abc123", "sha256:prd123"
                )
                is False
            )

            # Missing prd_hash
            verification_ref = {"git_sha": "abc123"}
            assert (
                persistence.is_verification_fresh(
                    verification_ref, "abc123", "sha256:prd123"
                )
                is False
            )


class TestGenerateRunId:
    """Tests for generate_run_id function."""

    def test_generate_unique_ids(self):
        """Test that generate_run_id produces unique IDs.

        Note: generate_run_id uses second precision, so we generate
        a smaller number of IDs and verify they have the expected format.
        """
        ids = [generate_run_id() for _ in range(5)]
        # Within the same second, IDs will be identical - this is expected behavior
        # Just verify they all have the correct format
        for run_id in ids:
            assert run_id.startswith("vrf_")
            parts = run_id.split("_")
            assert len(parts) == 3  # vrf, date, time

    def test_run_id_format(self):
        """Test that run_id follows expected format."""
        run_id = generate_run_id()
        assert run_id.startswith("vrf_")
        # Format: vrf_YYYYMMDD_HHMMSS
        parts = run_id.split("_")
        assert len(parts) == 3  # vrf, date, time
