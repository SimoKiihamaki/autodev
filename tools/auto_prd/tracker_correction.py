"""Tracker Auto-Correction Module.

This module provides automatic correction functions for common AI generation mistakes
in tracker.json files, such as invalid AC ID patterns or verification methods.
"""

import re
from typing import Any


def correct_ac_ids(tracker: dict[str, Any]) -> dict[str, Any]:
    """Correct acceptance criterion IDs to match schema pattern.

    Schema requires: ^AC[0-9]{3}$ (e.g., AC001, AC999)

    Common AI mistakes:
    - AC-001 (has dash) → AC001
    - AC01 (not 3 digits) → AC001
    - AC-DOC-003 (text prefix + dash) → AC003
    - AC0001 (4 digits) → AC001

    Args:
        tracker: Tracker dictionary to correct

    Returns:
        Corrected tracker dictionary
    """
    ac_id_pattern = re.compile(r"^AC[0-9]{3}$")
    corrections_made = 0

    for feature in tracker.get("features", []):
        for criterion in feature.get("acceptance_criteria", []):
            ac_id = criterion.get("id", "")
            if ac_id and not ac_id_pattern.match(ac_id):
                # Extract all digits from ID and format as AC + 3 digits
                digits = re.sub(r"[^0-9]", "", ac_id)
                if digits:
                    # Take first 3 digits and pad to 3
                    corrected_id = f"AC{digits[:3].zfill(3)}"
                    criterion["id"] = corrected_id
                    corrections_made += 1

    if corrections_made > 0:
        print(
            f"Auto-corrected {corrections_made} acceptance criterion ID(s) "
            "to match schema pattern",
            flush=True,
        )

    return tracker


def correct_verification_methods(tracker: dict[str, Any]) -> dict[str, Any]:
    """Correct invalid verification_method values.

    Schema requires: manual_test, unit_test, integration_test, e2e_test,
                 code_review, type_check, lint_check

    Common AI mistakes:
    - performance_test → unit_test or remove criterion
    - load_test → unit_test or remove criterion
    - stress_test → unit_test or remove criterion
    - Any unknown value → unit_test or remove criterion

    Args:
        tracker: Tracker dictionary to correct

    Returns:
        Corrected tracker dictionary
    """
    valid_methods = {
        "manual_test",
        "unit_test",
        "integration_test",
        "e2e_test",
        "code_review",
        "type_check",
        "lint_check",
    }

    corrections_made = 0
    criteria_to_remove = []

    for feature in tracker.get("features", []):
        for criterion in feature.get("acceptance_criteria", []):
            vm = criterion.get("verification_method", "")
            if vm not in valid_methods:
                # Try to map to valid method or mark for removal
                if "performance" in vm.lower():
                    criterion["verification_method"] = "unit_test"
                    corrections_made += 1
                elif "test" in vm.lower() and vm != "manual_test":
                    # Map load_test, stress_test to unit_test
                    criterion["verification_method"] = "unit_test"
                    corrections_made += 1
                else:
                    # Unknown - flag for removal (can't auto-correct)
                    criteria_to_remove.append((feature.get("id"), criterion.get("id")))

    # Remove criteria that can't be auto-corrected
    if criteria_to_remove:
        for feature_id, criterion_id in criteria_to_remove:
            for feature in tracker.get("features", []):
                if feature.get("id") == feature_id:
                    criteria = feature.get("acceptance_criteria", [])
                    feature["acceptance_criteria"] = [
                        ac for ac in criteria if ac.get("id") != criterion_id
                    ]
                    corrections_made += 1
                    break

    if corrections_made > 0:
        print(
            f"Auto-corrected {corrections_made} verification_method error(s)",
            flush=True,
        )

    return tracker


def apply_auto_corrections(tracker: dict[str, Any]) -> dict[str, Any]:
    """Apply all automatic corrections to generated tracker.

    This function runs all correction functions in sequence to fix common AI mistakes
    before the tracker is validated and saved.

    Args:
        tracker: Generated tracker dictionary from AI

    Returns:
        Corrected tracker dictionary
    """
    tracker = correct_ac_ids(tracker)
    tracker = correct_verification_methods(tracker)
    return tracker
