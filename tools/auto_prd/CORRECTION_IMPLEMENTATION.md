## Tracker Auto-Correction Implementation Summary

### Features Implemented

**New Module**: `/tools/auto_prd/tracker_correction.py`

Provides automatic correction functions for common AI mistakes in generated tracker.json files.

### Correction Functions

#### 1. `correct_ac_ids(tracker)` - Fixes acceptance criterion ID patterns
**Schema Requirement**: `^AC[0-9]{3}$` (exactly AC + 3 digits)

**Common AI Mistakes Handled**:
- `AC-001` (dash) → `AC001`
- `AC-DOC-003` (text prefix + dash) → `AC003`
- `AC01` (1 digit) → `AC001`
- `AC` (0 digits) → `AC000`
- `AC1234` (4 digits) → `AC123`

**Correction Logic**:
```python
# Extract all digits, take first 3, pad to 3
digits = re.sub(r"[^0-9]", "", ac_id)
if digits:
    corrected_id = f"AC{digits[:3].zfill(3)}"
```

**Behavior**:
- Valid 3-digit IDs (e.g., AC123) → unchanged
- 2-digit IDs (e.g., AC12) → padded to AC012
- 4+ digit IDs (e.g., AC1234) → truncated to AC123
- Empty AC ID → padded to AC000 (ensures 3 digits)

#### 2. `correct_verification_methods(tracker)` - Fixes invalid verification methods
**Schema Requirement**: Must be one of: `manual_test`, `unit_test`, `integration_test`, `e2e_test`, `code_review`, `type_check`, `lint_check`

**Common AI Mistakes Handled**:
- `performance_test` → `unit_test`
- `load_test` → `unit_test`
- `stress_test` → `unit_test`
- Unknown methods → criterion removed

**Behavior**:
- `performance_test` variants mapped to `unit_test`
- Unknown values removed entirely (can't auto-correct)

#### 3. `apply_auto_corrections(tracker)` - Master function
Applies all correction functions in sequence before validation and saving.

### Integration

**Modified Files**:
1. `/tools/auto_prd/tracker_generator.py` - Added import and call to `apply_auto_corrections()`
   - Location: Line 29 (import), Line 863 (call after JSON parsing)
   - Ensures all corrections run before schema validation

### Testing

**Test File**: `/tools/auto_prd/tests/test_tracker_correction.py`

**Coverage**:
- ✅ Valid AC IDs preserved
- ✅ Dash removal (`AC-001` → `AC001`)
- ✅ Text prefix removal (`AC-DOC-003` → `AC003`)
- ✅ 2-digit padding (`AC12` → `AC012`)
- ✅ Long ID truncation (`AC1234` → `AC123`)
- ✅ Verification method correction (`performance_test` → `unit_test`)
- ✅ Unknown method removal
- ✅ Empty ID handling

### How It Works

1. **AI generates tracker** → JSON parsed
2. **Auto-correction applied** → `apply_auto_corrections()` runs
   - AC IDs corrected to match schema
   - Invalid verification methods corrected or removed
3. **Metadata injection** → Version, hash, timestamps added
4. **Schema validation** → Validated against schema
5. **Saved** → Tracker saved to `.aprd/tracker.json`

### Benefits

- **No validation failures** - Invalid AI outputs auto-corrected before validation
- **Fresh start guaranteed** - Combined with tracker deletion in `app.py`
- **Transparent** - Console logs show what was corrected
- **Consistent** - All trackers follow schema requirements

### Error Messages

When corrections are made, users see:
```
Auto-corrected 2 acceptance criterion ID(s) to match schema pattern
Auto-corrected 2 verification_method error(s)
```

This provides clear feedback that corrections were applied automatically.
