# Research: Remove redundant gofmt from Makefile

**Date**: 2026-01-19
**Item**: 017-remove-redundant-gofmt-from-makefile

## Research Question
Redundant formatting command wastes CI time.

**Motivation:** Simplifies Makefile and removes redundant operation.

**Technical constraints:**
- Remove 'gofmt -w .' line from Makefile as goimports handles both imports and formatting

**Signals:** priority: medium

## Summary
The Makefile currently runs both `goimports -w .` and `gofmt -w .` in the `fmt-go` target (lines 72-73). This is redundant because `goimports` internally uses `gofmt` for formatting and also handles import sorting/removal. Running `gofmt` after `goimports` provides no additional benefit and wastes CI time. The fix is straightforward: remove line 73 from the Makefile.

The research confirms that:
1. `goimports` handles both import management AND code formatting (verified through testing and documentation)
2. The redundancy is already documented in CODEBASE_ANALYSIS_REPORT.md (MEDIUM-002)
3. Project guidelines (AGENTS.md) explicitly state to use `goimports` for import ordering
4. No other parts of the codebase depend on running `gofmt` separately

## Current State Analysis

### Existing Implementation
The Makefile defines a `fmt-go` target that runs two formatting commands sequentially:

**File: `/Users/simo/Projects/autodev/Makefile:70-73`**
```makefile
fmt-go:
	@echo "📝 Formatting Go code..."
	goimports -w .
	gofmt -w .
```

Line 72 runs `goimports -w .` which:
- Sorts and groups import declarations
- Removes unused imports
- Formats code using the same logic as `gofmt`

Line 73 runs `gofmt -w .` which:
- Only formats code (already done by goimports)
- Provides no additional functionality

### Key Files

- **`/Users/simo/Projects/autodev/Makefile:70-73`** - The `fmt-go` target with redundant formatting commands
  - Line 72: `goimports -w .` - Handles imports + formatting
  - Line 73: `gofmt -w .` - Redundant formatting only

- **`/Users/simo/Projects/autodev/CODEBASE_ANALYSIS_REPORT.md:357-363`** - Documents this exact issue:
  ```markdown
  ### MEDIUM-002: Redundant Formatting Commands
  **Location:** `Makefile:72-73`

  **Issue:** Both `goimports` and `gofmt` are run, but `goimports` already includes formatting.

  **Recommended Fix:** Remove `gofmt -w .` as `goimports` handles both import sorting and formatting.
  ```

- **`/Users/simo/Projects/autodev/AGENTS.md:20`** - Project guidelines state:
  ```markdown
  - Use `goimports` to maintain import ordering.
  ```

- **`/Users/simo/Projects/autodev/.github/copilot-instructions.md:12`** - Review expectations mention:
  ```markdown
  - Enforce `go fmt ./...` + `goimports` ordering before approving.
  ```
  Note: This refers to `go fmt ./...` (the command, not gofmt), and is about the development workflow, not the Makefile target.

## Technical Considerations

### Dependencies
- **goimports**: Currently installed and used in the project
- **gofmt**: Built into Go toolchain, will still be available but not needed in Makefile

### Patterns to Follow

**Existing formatting workflow:**
- `make fmt` calls `fmt-go` and `fmt-py`
- `fmt-go` runs both goimports and gofmt (redundant)
- `fmt-py` runs ruff format (single tool, no redundancy)

**Pattern to maintain:**
- Keep the `fmt-go` target structure
- Keep the echo message for consistency with other targets
- Simply remove the redundant `gofmt -w .` line

### Verification Testing
Tested goimports behavior with a malformed Go file:

**Before goimports:**
```go
package main
import (
	"fmt"
	"os"
)
func main( ) {
fmt.Println("test")
}
```

**After goimports -w:**
```go
package main

import (
	"fmt"
)

func main() {
	fmt.Println("test")
}
```

goimports correctly:
1. Removed unused `os` import
2. Fixed spacing around function declaration
3. Indented the function body properly

This confirms goimports provides full formatting capability.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Developer workflow relies on both commands | Low | goimports is a superset of gofmt functionality; no functionality is lost |
| CI/CD pipelines might expect gofmt | Low | No CI workflows found in `.github/workflows/`; CI uses `make ci` which calls `make fmt` indirectly |
| Formatting differences between tools | Low | goimports uses gofmt internally; identical formatting output |
| Team habit of running gofmt manually | Low | Documentation change (AGENTS.md) already recommends goimports; this aligns Makefile with documentation |

## Recommended Approach

### Implementation Steps

1. **Remove the redundant line** from `/Users/simo/Projects/autodev/Makefile`:
   - Delete line 73: `gofmt -w .`
   - Keep line 72: `goimports -w .`

2. **Verify the change**:
   - Run `make fmt-go` to ensure it works correctly
   - Run `make fmt` to verify the parent target still works
   - Test with an unformatted Go file to confirm formatting is applied

3. **No documentation updates needed**:
   - AGENTS.md already recommends goimports
   - CODEBASE_ANALYSIS_REPORT.md already documents this issue
   - Change aligns Makefile with existing documentation

### Expected Result
After removal, the `fmt-go` target will be:

```makefile
fmt-go:
	@echo "📝 Formatting Go code..."
	goimports -w .
```

This is consistent with the `fmt-py` target which uses a single tool (ruff format).

### Benefits
- **Faster CI/CD**: Eliminates redundant file processing
- **Simpler Makefile**: Removes unnecessary line
- **Consistency**: Aligns with project guidelines in AGENTS.md
- **No functionality loss**: goimports is a superset of gofmt

## Open Questions

1. **Should we verify this with the team?**
   - The change is straightforward and low-risk
   - Already documented as an issue in CODEBASE_ANALYSIS_REPORT.md
   - Aligns with existing project guidelines
   - Recommendation: No team consultation needed for this trivial change

2. **Are there any pre-commit hooks or other automation?**
   - No `.pre-commit-config.yaml` found in project
   - No git hooks detected
   - Recommendation: Not applicable

3. **Should we add a comment explaining why goimports is sufficient?**
   - Current Makefile has no comments explaining tool choices
   - The redundancy is self-evident from tool behavior
   - Recommendation: No comment needed; maintains consistency with rest of Makefile
