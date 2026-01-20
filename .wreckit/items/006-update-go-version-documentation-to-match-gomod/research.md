# Research: Update Go version documentation to match go.mod

**Date**: 2026-01-19
**Item**: 006-update-go-version-documentation-to-match-gomod

## Research Question
Users may attempt to build with Go 1.21/1.22 and encounter compatibility issues.

**Motivation:** Ensures documentation matches actual requirements, preventing user frustration and build failures.

**Technical constraints:**
- Update README.md line 26 to state 'Go 1.23+'

**Signals:** priority: critical

## Summary
This research confirms a critical documentation mismatch where the README.md specifies "Go 1.21+" while the go.mod file requires "go 1.23.0". This discrepancy has been previously identified in the CODEBASE_ANALYSIS_REPORT.md as item CRITICAL-006. The fix is straightforward: update line 26 of README.md from "Go 1.21+" to "Go 1.23+".

Additionally, research revealed a secondary issue: the Codacy CI configuration (`.codacy/codacy.yaml:3`) specifies `go@1.22.3`, which is also incompatible with the go.mod requirement of Go 1.23.0. While this was not explicitly mentioned in the technical constraints, it represents the same category of documentation mismatch that should be addressed to prevent CI failures.

The change scope is minimal and isolated to documentation updates, with no code changes required. The main README.md change is a simple one-line text replacement. The Codacy configuration change is equally straightforward.

## Current State Analysis

### Existing Implementation
The project currently has inconsistent Go version requirements across different files:

1. **README.md:26** states "Go 1.21+" - This is the PRIMARY issue to fix
2. **go.mod:3** specifies "go 1.23.0" - This is the source of truth
3. **CODEBASE_ANALYSIS_REPORT.md:126-133** documents this exact issue as CRITICAL-006
4. **.codacy/codacy.yaml:3** specifies `go@1.22.3` - This is a SECONDARY issue (CI compatibility)

### Key Files
- `README.md:26` - Current line: "- Go 1.21+" - **MUST BE UPDATED** to "Go 1.23+"
- `go.mod:3` - Line: "go 1.23.0" - Source of truth for the actual requirement
- `CODEBASE_ANALYSIS_REPORT.md:126-133` - Documents the issue as CRITICAL-006 with the recommended fix
- `.codacy/codacy.yaml:3` - Current line: "- go@1.22.3" - **SHOULD BE UPDATED** to "go@1.23.0" or later

### Dependencies
The Go modules in go.mod include several dependencies:
- `github.com/charmbracelet/bubbletea v0.26.0`
- `github.com/charmbracelet/lipgloss v1.1.1-0.20250404203927-76690c660834`
- `github.com/go-chi/chi/v5 v5.0.10`
- Various `github.com/charmbracelet/x/*` packages

These dependencies may require Go 1.23 features, which is why the go.mod specifies this version.

## Technical Considerations

### Patterns to Follow
1. **Version notation consistency**: The README uses the format "Go X.Y+" which indicates minimum version X.Y and any compatible later version. This should be maintained.
2. **Documentation structure**: The Requirements section in README.md follows a clear bullet-point format that should be preserved.
3. **Go version format in go.mod**: Uses the format "go X.Y.Z" (three-part version), which is the standard for Go module files.

### Dependencies
- **No code changes required** - This is purely a documentation fix
- **No external dependencies** - The fix doesn't require any new packages or tools
- **Internal modules unaffected** - This change doesn't impact any Go code, Python code, or other components

### Integration Points
- **README.md** is the main user-facing documentation and the primary target for changes
- **CODEBASE_ANALYSIS_REPORT.md** should be updated after the fix to reflect that CRITICAL-006 is resolved
- **.codacy/codacy.yaml** is a CI configuration file that should match the go.mod requirement

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Users with Go 1.21/1.22 cannot build the project | **High** | Update README.md to clearly state Go 1.23+ requirement |
| Codacy CI may fail or use wrong Go version | **Medium** | Update .codacy/codacy.yaml to use Go 1.23+ |
| Breaking existing user workflows | **Low** | This is a documentation correction that aligns docs with reality; users already need Go 1.23 to build successfully |
| Inconsistency if only one file is updated | **Low** | Update both README.md and .codacy/codacy.yaml to maintain consistency |

## Recommended Approach

### Primary Fix (Required)
1. Update `README.md:26` from "- Go 1.21+" to "- Go 1.23+"
   - This is a simple string replacement
   - No other lines in README.md need to be changed
   - Maintains the existing markdown formatting and structure

### Secondary Fix (Recommended)
2. Update `.codacy/codacy.yaml:3` from "- go@1.22.3" to "- go@1.23.0" (or latest 1.23.x version)
   - This ensures CI/CD uses the correct Go version
   - Prevents potential CI failures due to version mismatch
   - Maintains consistency across all configuration files

### Post-Fix Actions (Optional)
3. Update `CODEBASE_ANALYSIS_REPORT.md` to mark CRITICAL-006 as resolved
   - This is documentation housekeeping
   - Not strictly required for the fix itself

### Implementation Steps
1. Edit README.md line 26
2. Verify the change renders correctly
3. Optionally update .codacy/codacy.yaml
4. Test that the build still works (should already be working for users with Go 1.23)

## Open Questions
1. **Scope clarification**: Should the .codacy/codacy.yaml update be included in this item, or should it be a separate item? The technical constraints only mention README.md, but the Codacy file has the same type of mismatch.

2. **Version specificity**: For .codacy/codacy.yaml, should we specify "go@1.23.0" (exact patch version) or "go@1.23" (any 1.23.x version)? The go.mod uses 1.23.0 specifically, but CI tools often handle version ranges differently.

3. **Verification method**: Should we add any automated checks to prevent this type of drift in the future (e.g., a script that verifies README requirements match go.mod)?

## Additional Findings

### Codebase Analysis Report Reference
The issue was previously documented in `CODEBASE_ANALYSIS_REPORT.md` at lines 126-133:
```markdown
### CRITICAL-006: Go Version Mismatch in Documentation
**Location:** `README.md:26` vs `go.mod:3`

**Issue:** README states "Go 1.21+" but go.mod requires "go 1.23.0"

**Impact:** Users may attempt to build with Go 1.21/1.22 and encounter compatibility issues.

**Recommended Fix:** Update README.md to match go.mod:
- Go 1.23+
```

This confirms that the issue is well-understood and the recommended fix aligns with the technical constraints.

### Related Items
Item 007 (`.wreckit/items/007-create-github-cicd-workflow`) references Go 1.23 in its workflow configuration, which suggests awareness of the correct version requirement in some parts of the codebase. This reinforces the importance of updating the user-facing documentation to match.
