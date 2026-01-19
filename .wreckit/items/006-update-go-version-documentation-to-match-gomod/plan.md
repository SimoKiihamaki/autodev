# Update Go version documentation to match go.mod Implementation Plan

## Overview
This implementation addresses a critical documentation mismatch where README.md specifies "Go 1.21+" while go.mod requires "go 1.23.0". This discrepancy causes user frustration when attempting to build with incompatible Go versions. The fix aligns all documentation and CI configuration with the actual Go version requirement specified in go.mod.

## Current State Analysis

### Verified Issues
1. **README.md:26** states "- Go 1.21+" - INCORRECT
2. **go.mod:3** specifies "go 1.23.0" - SOURCE OF TRUTH
3. **.codacy/codacy.yaml:3** specifies "- go@1.22.3" - INCORRECT (CI compatibility issue)

### Impact Analysis
- **User Impact**: Users with Go 1.21/1.22 will encounter build failures
- **CI Impact**: Codacy CI may fail or use wrong Go version for analysis
- **Documentation Credibility**: Mismatched requirements undermine trust in documentation

### Key Constraints
- **Technical constraints explicitly require**: Update README.md line 26 to state 'Go 1.23+'
- **Scope decision**: Include .codacy/codacy.yaml update as secondary fix to prevent CI failures
- **No code changes required**: This is purely a documentation/configuration fix

## Desired End State

### Specification
1. README.md line 26 displays: "- Go 1.23+"
2. .codacy/codacy.yaml line 3 displays: "- go@1.23.0" or later compatible version
3. All documentation consistently reflects the actual Go version requirement from go.mod
4. Users can build successfully following the documented requirements
5. CI/CD uses the correct Go version

### Verification Methods
1. **Automated**: Read README.md and verify line 26 contains "Go 1.23+"
2. **Automated**: Read .codacy/codacy.yaml and verify line 3 contains "go@1.23.0" or later
3. **Automated**: Verify go.mod still specifies "go 1.23.0" (no regressions)
4. **Manual**: README renders correctly with updated requirement
5. **Manual**: Build succeeds with Go 1.23 (if available)

### Key Discoveries
- **Line 26 is exact**: README.md line 26 contains exactly "- Go 1.21+" (verified via sed)
- **Codacy uses exact version**: .codacy/codacy.yaml uses three-part version format "go@1.22.3"
- **No GitHub workflows**: The project has no .github/workflows directory (confirmed via ls)
- **Pattern to follow**: README uses "Go X.Y+" format, go.mod uses "go X.Y.Z" format
- **Constraint**: Must maintain existing markdown formatting and structure

## What We're NOT Doing

1. **NOT updating go.mod**: The go.mod file is the source of truth and should not be changed
2. **NOT updating CODEBASE_ANALYSIS_REPORT.md**: While it documents this issue as CRITICAL-006, updating it is out of scope (documentation housekeeping)
3. **NOT adding automated validation**: No scripts to prevent future drift (out of scope for this item)
4. **NOT updating other documentation**: Only README.md and .codacy/codacy.yaml are in scope
5. **NOT changing version format**: Maintain existing "Go X.Y+" format in README, use "go@X.Y.Z" in Codacy config

## Implementation Approach

### High-Level Strategy
This is a minimal, isolated documentation fix consisting of two simple text replacements:

1. **Primary Fix (REQUIRED)**: Update README.md line 26
   - Change "- Go 1.21+" to "- Go 1.23+"
   - Single-line string replacement
   - No structural changes to markdown

2. **Secondary Fix (RECOMMENDED)**: Update .codacy/codacy.yaml line 3
   - Change "- go@1.22.3" to "- go@1.23.0"
   - Ensures CI/CD uses correct Go version
   - Prevents CI failures due to version mismatch

### Rationale
- **Low Risk**: Simple text replacements with no code changes
- **High Impact**: Prevents user confusion and CI failures
- **Incremental**: Each change is independently valuable
- **Reversible**: Changes can be easily reverted if needed
- **Consistent**: Aligns all documentation with source of truth (go.mod)

---

## Phase 1: Update README.md Go Version Requirement

### Overview
Update the user-facing README.md to correctly state Go 1.23+ as the minimum required version, matching the actual requirement in go.mod.

### Changes Required

#### 1. README.md Line 26
**File**: `/Users/simo/Projects/autodev/README.md`
**Line**: 26
**Current Content**: `- Go 1.21+`
**New Content**: `- Go 1.23+`

**Change Type**: String replacement (single line)
**Change Context** (lines 24-28):
```markdown
## Requirements

- Go 1.21+                    ← CHANGE THIS LINE to "- Go 1.23+"
- Python 3.10+ (required for `zip(strict=True)` and modern type hints)
- CLIs: `codex` (for codex-first|codex-only), `claude` (for claude-only|codex-first), `coderabbit`, `git`, `gh`
```

**Implementation**:
```bash
# Using sed for precise single-line replacement
sed -i '' 's/- Go 1\.21+/- Go 1.23+/' README.md
```

**Preserve These Elements**:
- Markdown list format: "- Go X.Y+"
- Trailing "+" to indicate minimum version
- Bullet point formatting
- Surrounding context (Python requirement, CLI tools)

### Success Criteria

#### Automated Verification:
- [ ] File content verified: Line 26 of README.md contains exactly "- Go 1.23+"
- [ ] No unintended changes: Only line 26 is modified, all other lines unchanged
- [ ] Markdown syntax valid: README.md is still valid markdown
- [ ] go.mod unchanged: Verify go.mod still specifies "go 1.23.0" (regression check)

#### Manual Verification:
- [ ] README renders correctly in GitHub markdown viewer
- [ ] The Requirements section formatting is preserved
- [ ] No visual artifacts or formatting issues
- [ ] The change is clear and unambiguous to users

**Note**: This is the primary fix and must be completed before Phase 2.

---

## Phase 2: Update Codacy CI Go Version Configuration

### Overview
Update the .codacy/codacy.yaml configuration to use Go 1.23.0, ensuring CI/CD analysis uses the correct Go version matching the go.mod requirement.

### Changes Required

#### 1. .codacy/codacy.yaml Line 3
**File**: `/Users/simo/Projects/autodev/.codacy/codacy.yaml`
**Line**: 3
**Current Content**: `- go@1.22.3`
**New Content**: `- go@1.23.0`

**Change Type**: String replacement (single line)
**Change Context** (lines 1-6):
```yaml
runtimes:
    - dart@3.7.2
    - go@1.22.3                    ← CHANGE THIS LINE to "- go@1.23.0"
    - java@17.0.10
    - node@22.2.0
    - python@3.11.11
```

**Implementation**:
```bash
# Using sed for precise single-line replacement
sed -i '' 's/- go@1\.22\.3/- go@1.23.0/' .codacy/codacy.yaml
```

**Rationale for Version Choice**:
- go.mod specifies "go 1.23.0" exactly, so we use the same version
- Using exact patch version (1.23.0) ensures consistency
- Codacy uses three-part version format: "go@X.Y.Z"
- This matches the pattern used for other runtimes (e.g., "dart@3.7.2")

### Success Criteria

#### Automated Verification:
- [ ] File content verified: Line 3 of .codacy/codacy.yaml contains exactly "- go@1.23.0"
- [ ] No unintended changes: Only line 3 is modified, all other lines unchanged
- [ ] YAML syntax valid: .codacy/codacy.yaml is still valid YAML
- [ ] Consistency check: Version matches go.mod requirement

#### Manual Verification:
- [ ] YAML file is valid and properly formatted
- [ ] The runtimes section structure is preserved
- [ ] No YAML syntax errors introduced
- [ ] Version format matches other runtime specifications

**Note**: This is a secondary but highly recommended fix to prevent CI issues.

---

## Testing Strategy

### Unit Tests
**N/A**: This is a documentation fix with no code changes requiring unit tests.

### Integration Tests
**N/A**: No code integration points are affected by this change.

### Manual Testing Steps

#### Pre-Change Verification (Optional)
1. Confirm current README.md line 26 shows "Go 1.21+"
2. Confirm current .codacy/codacy.yaml line 3 shows "go@1.22.3"
3. Confirm go.mod line 3 shows "go 1.23.0"

#### Post-Change Verification (Required)
1. **README.md Verification**:
   - Open README.md in a text editor or markdown viewer
   - Navigate to the Requirements section
   - Verify line 26 displays "Go 1.23+"
   - Confirm the formatting matches other bullet points
   - Check that the markdown renders correctly

2. **Codacy Configuration Verification**:
   - Open .codacy/codacy.yaml in a text editor
   - Verify line 3 displays "go@1.23.0"
   - Confirm YAML syntax is valid (no parsing errors)
   - Verify the runtimes section is properly formatted

3. **Build Verification (If Go 1.23 Available)**:
   - Run `make build` to ensure the project still builds
   - Verify no errors related to Go version mismatch
   - Confirm the build succeeds as expected

4. **Documentation Review**:
   - Read the Requirements section in its entirety
   - Verify all requirements are clearly stated
   - Check for consistency across the document

## Migration Notes

### No Migration Required
This is a documentation-only change with no data migration, API changes, or system modifications required.

### User Impact
- **Users with Go 1.23+**: No impact, they can already build successfully
- **Users with Go 1.21/1.22**: Will now see correct requirement in documentation and can upgrade Go before attempting build
- **New users**: Will see correct requirement from the start, avoiding confusion

### Rollback Strategy
If issues arise, changes can be easily reverted:
```bash
# Revert README.md
git checkout HEAD -- README.md

# Revert .codacy/codacy.yaml
git checkout HEAD -- .codacy/codacy.yaml
```

## References

### Research
- Research Summary: `/Users/simo/Projects/autodev/.wreckit/items/006-update-go-version-documentation-to-match-gomod/research.md`
- Item Definition: `/Users/simo/Projects/autodev/.wreckit/items/006-update-go-version-documentation-to-match-gomod/item.json`

### Codebase References
- **README.md:26** - Line to update (primary fix)
- **go.mod:3** - Source of truth (do not modify)
- **.codacy/codacy.yaml:3** - CI configuration to update (secondary fix)
- **CODEBASE_ANALYSIS_REPORT.md:123-133** - Documents this issue as CRITICAL-006

### Related Items
- Item 007 (`.wreckit/items/007-create-github-cicd-workflow`) - References Go 1.23 correctly

## Implementation Order

1. ✅ **Phase 1**: Update README.md line 26 (REQUIRED)
2. ✅ **Phase 2**: Update .codacy/codacy.yaml line 3 (RECOMMENDED)
3. ⏭️ **Verification**: Manual review and testing

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Typo in version number | Low | High | Double-check version before committing |
| Markdown formatting breaks | Low | Medium | Verify markdown renders correctly |
| YAML syntax error | Low | Medium | Validate YAML syntax |
| Users already using Go 1.23 | N/A | None | No negative impact |
| CI failures after update | Low | Medium | Test Codacy configuration if possible |

**Overall Risk Level**: LOW
- Simple text replacements with well-defined changes
- No code logic modifications
- Changes align documentation with actual requirements
- Easily reversible if issues arise
