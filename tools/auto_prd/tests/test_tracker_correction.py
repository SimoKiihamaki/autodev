"""Tests for tracker_correction module."""

import unittest

from auto_prd.tracker_correction import (
    apply_auto_corrections,
    correct_ac_ids,
    correct_verification_methods,
)


class CorrectAcIdsTests(unittest.TestCase):
    """Tests for correct_ac_ids function."""

    def test_valid_ac_ids_unchanged(self) -> None:
        """Valid AC IDs should remain unchanged."""
        tracker = {
            "features": [
                {
                    "id": "F001",
                    "acceptance_criteria": [
                        {"id": "AC001", "criterion": "Test 1"},
                        {"id": "AC123", "criterion": "Test 2"},
                        {"id": "AC999", "criterion": "Test 3"},
                    ],
                }
            ]
        }

        result = correct_ac_ids(tracker)

        self.assertEqual(result["features"][0]["acceptance_criteria"][0]["id"], "AC001")
        self.assertEqual(result["features"][0]["acceptance_criteria"][1]["id"], "AC123")
        self.assertEqual(result["features"][0]["acceptance_criteria"][2]["id"], "AC999")

    def test_dash_in_ac_id_corrected(self) -> None:
        """AC IDs with dashes should be corrected."""
        tracker = {
            "features": [
                {
                    "id": "F001",
                    "acceptance_criteria": [
                        {"id": "AC-001", "criterion": "Test"},
                        {"id": "AC-DOC-003", "criterion": "Test 2"},
                        {"id": "AC-TEST-123", "criterion": "Test 3"},
                    ],
                }
            ]
        }

        result = correct_ac_ids(tracker)

        self.assertEqual(result["features"][0]["acceptance_criteria"][0]["id"], "AC001")
        self.assertEqual(result["features"][0]["acceptance_criteria"][1]["id"], "AC003")
        self.assertEqual(result["features"][0]["acceptance_criteria"][2]["id"], "AC123")

    def test_short_ac_ids_padded(self) -> None:
        """AC IDs with fewer than 3 digits should be padded."""
        tracker = {
            "features": [
                {
                    "id": "F001",
                    "acceptance_criteria": [
                        {"id": "AC1", "criterion": "Test 1"},
                        {"id": "AC12", "criterion": "Test 2"},
                        {"id": "AC", "criterion": "Test 3"},
                    ],
                }
            ]
        }

        result = correct_ac_ids(tracker)

        self.assertEqual(result["features"][0]["acceptance_criteria"][0]["id"], "AC001")
        # 2-digit AC ID gets padded to 012 (AC12 → AC012)
        self.assertEqual(result["features"][0]["acceptance_criteria"][1]["id"], "AC012")
        # Empty AC ID without digits becomes AC000 (or is preserved if schema allows, but current logic converts to AC000)
        self.assertEqual(result["features"][0]["acceptance_criteria"][2]["id"], "AC001")

    def test_long_ac_ids_truncated(self) -> None:
        """AC IDs with more than 3 digits should be truncated."""
        tracker = {
            "features": [
                {
                    "id": "F001",
                    "acceptance_criteria": [
                        {"id": "AC1234", "criterion": "Test 1"},
                        {"id": "AC9999", "criterion": "Test 2"},
                    ],
                }
            ]
        }

        result = correct_ac_ids(tracker)

        # First 3 digits kept
        self.assertEqual(result["features"][0]["acceptance_criteria"][0]["id"], "AC123")
        self.assertEqual(result["features"][0]["acceptance_criteria"][1]["id"], "AC999")

    def test_text_prefix_removed(self) -> None:
        """Text prefixes in AC IDs should be removed."""
        tracker = {
            "features": [
                {
                    "id": "F001",
                    "acceptance_criteria": [
                        {"id": "AC-TEST-001", "criterion": "Test"},
                        {"id": "AC-DOC-123", "criterion": "Test 2"},
                    ],
                }
            ]
        }

        result = correct_ac_ids(tracker)

        self.assertEqual(result["features"][0]["acceptance_criteria"][0]["id"], "AC001")
        self.assertEqual(result["features"][0]["acceptance_criteria"][1]["id"], "AC123")


class CorrectVerificationMethodsTests(unittest.TestCase):
    """Tests for correct_verification_methods function."""

    def test_valid_verification_methods_unchanged(self) -> None:
        """Valid verification methods should remain unchanged."""
        tracker = {
            "features": [
                {
                    "id": "F001",
                    "acceptance_criteria": [
                        {
                            "id": "AC001",
                            "criterion": "Test",
                            "verification_method": "unit_test",
                        },
                        {
                            "id": "AC002",
                            "criterion": "Test",
                            "verification_method": "integration_test",
                        },
                    ],
                }
            ]
        }

        result = correct_verification_methods(tracker)

        self.assertEqual(
            result["features"][0]["acceptance_criteria"][0]["verification_method"],
            "unit_test",
        )
        self.assertEqual(
            result["features"][0]["acceptance_criteria"][1]["verification_method"],
            "integration_test",
        )

    def test_performance_test_corrected_to_unit_test(self) -> None:
        """performance_test should be corrected to unit_test."""
        tracker = {
            "features": [
                {
                    "id": "F001",
                    "acceptance_criteria": [
                        {
                            "id": "AC001",
                            "criterion": "Test",
                            "verification_method": "performance_test",
                        },
                        {
                            "id": "AC002",
                            "criterion": "Test",
                            "verification_method": "Performance Test",
                        },
                    ],
                }
            ]
        }

        result = correct_verification_methods(tracker)

        self.assertEqual(
            result["features"][0]["acceptance_criteria"][0]["verification_method"],
            "unit_test",
        )
        self.assertEqual(
            result["features"][0]["acceptance_criteria"][1]["verification_method"],
            "unit_test",
        )

    def test_load_test_corrected_to_unit_test(self) -> None:
        """load_test and stress_test should be corrected to unit_test."""
        tracker = {
            "features": [
                {
                    "id": "F001",
                    "acceptance_criteria": [
                        {
                            "id": "AC001",
                            "criterion": "Test",
                            "verification_method": "load_test",
                        },
                        {
                            "id": "AC002",
                            "criterion": "Test",
                            "verification_method": "stress_test",
                        },
                    ],
                }
            ]
        }

        result = correct_verification_methods(tracker)

        self.assertEqual(
            result["features"][0]["acceptance_criteria"][0]["verification_method"],
            "unit_test",
        )
        self.assertEqual(
            result["features"][0]["acceptance_criteria"][1]["verification_method"],
            "unit_test",
        )

    def test_unknown_verification_methods_removed(self) -> None:
        """Unknown verification methods should be removed."""
        tracker = {
            "features": [
                {
                    "id": "F001",
                    "acceptance_criteria": [
                        {
                            "id": "AC001",
                            "criterion": "Test",
                            "verification_method": "unit_test",
                        },
                        {
                            "id": "AC002",
                            "criterion": "Test",
                            "verification_method": "unknown",
                        },
                        {
                            "id": "AC003",
                            "criterion": "Test",
                            "verification_method": "custom",
                        },
                    ],
                }
            ]
        }

        result = correct_verification_methods(tracker)

        # First criterion unchanged
        self.assertEqual(
            result["features"][0]["acceptance_criteria"][0]["verification_method"],
            "unit_test",
        )
        # Unknown ones removed
        self.assertEqual(len(result["features"][0]["acceptance_criteria"]), 1)


class ApplyAutoCorrectionsTests(unittest.TestCase):
    """Tests for apply_auto_corrections function."""

    def test_all_corrections_applied(self) -> None:
        """All correction functions should run in sequence."""
        tracker = {
            "features": [
                {
                    "id": "F001",
                    "acceptance_criteria": [
                        {
                            "id": "AC-001",
                            "criterion": "Test 1",
                            "verification_method": "performance_test",
                        },
                        {
                            "id": "AC12",
                            "criterion": "Test 2",
                            "verification_method": "unit_test",
                        },
                        {
                            "id": "AC-DOC-003",
                            "criterion": "Test 3",
                            "verification_method": "load_test",
                        },
                    ],
                }
            ]
        }

        result = apply_auto_corrections(tracker)

        # AC IDs corrected
        self.assertEqual(result["features"][0]["acceptance_criteria"][0]["id"], "AC001")
        self.assertEqual(result["features"][0]["acceptance_criteria"][1]["id"], "AC012")
        self.assertEqual(result["features"][0]["acceptance_criteria"][2]["id"], "AC003")

        # Verification methods corrected
        self.assertEqual(
            result["features"][0]["acceptance_criteria"][0]["verification_method"],
            "unit_test",
        )
        self.assertEqual(
            result["features"][0]["acceptance_criteria"][1]["verification_method"],
            "unit_test",
        )
        self.assertEqual(
            result["features"][0]["acceptance_criteria"][2]["verification_method"],
            "unit_test",
        )


if __name__ == "__main__":
    unittest.main()
