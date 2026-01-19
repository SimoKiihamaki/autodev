# Remove redundant gofmt from Makefile Implementation Plan

## Overview
Remove the redundant `gofmt -w .` command from the `fmt-go` target in the Makefile. The `goimports` tool already handles both import management and code formatting (using gofmt internally), making the separate gofmt call unnecessary. This change will reduce CI execution time and align the Makefile with existing project guidelines.

## Current State Analysis

**Current Implementation (Makefile:70-73):**
```makefile
fmt-go:
	@echo "📝 Formatting Go code..."
	goimports -w .
	gofmt -w .
```

**What's Wrong:**
- Line 72: `goimports -w .` handles import sorting/removal AND formatting
- Line 73: `gofmt -w .` performs redundant formatting (already done by goimports)
- This wastes CI time by processing every Go file twice

**Key Constraints:**
- Project guidelines (AGENTS.md:20) explicitly state: "Use `goimports` to maintain import ordering"
- The redundancy is already documented in CODEBASE_ANALYSIS_REPORT.md (MEDIUM-002)
- No CI workflow files exist in `.github/workflows/`
- No pre-commit hooks or other automation depends on the separate gofmt call

## Desired End State

**Target Implementation (Makefile:70-72):**
```makefile
fmt-go:
	@echo "📝 Formatting Go code..."
	goimports -w .
```

**Verification:**
- `make fmt-go` runs successfully
- `make fmt` (which calls fmt-go) runs successfully
- Go code is properly formatted (imports sorted and formatted correctly)
- No loss of formatting functionality
- Consistent with fmt-py target which uses a single tool (ruff format)

### Key Discoveries:
- **Makefile:73** - The redundant `gofmt -w .` line that must be removed
- **AGENTS.md:20** - Project guidelines already recommend goimports for import ordering
- **CODEBASE_ANALYSIS_REPORT.md:357-363** - This exact issue is documented as MEDIUM-002
- **Makefile:75-77** - The fmt-py target uses only ruff format (single tool pattern to follow)
- **No CI workflow files** - Change only affects local development and manual CI runs

## What We're NOT Doing
- ❌ NOT modifying any other Makefile targets (fmt, fmt-py, lint, etc.)
- ❌ NOT changing the echo message or target structure
- ❌ NOT adding comments explaining the tool choice (maintains consistency with rest of Makefile)
- ❌ NOT updating documentation (AGENTS.md already recommends goimports)
- ❌ NOT removing gofmt from the Go toolchain (it will still be available if needed manually)

## Implementation Approach

This is a trivial, single-line removal with no dependencies or risks. The approach is:

1. **Remove the redundant line** - Delete line 73 from the Makefile
2. **Verify functionality** - Test that formatting still works correctly
3. **Confirm no side effects** - Ensure dependent targets still function

The change is:
- **Low risk** - goimports is a superset of gofmt functionality
- **High confidence** - Already documented as an issue and aligns with project guidelines
- **No migration needed** - No data or API changes
- **Immediately reversible** - Can add the line back if needed (though unlikely)

---

## Phase 1: Remove redundant gofmt line

### Overview
Remove the redundant `gofmt -w .` line from the fmt-go target in the Makefile, eliminating duplicate formatting operations.

### Changes Required:

#### 1. Makefile fmt-go target
**File**: `/Users/simo/Projects/autodev/Makefile`
**Changes**: Remove line 73 (`gofmt -w .`) from the fmt-go target

**Before (lines 70-73):**
```makefile
fmt-go:
	@echo "📝 Formatting Go code..."
	goimports -w .
	gofmt -w .
```

**After (lines 70-72):**
```makefile
fmt-go:
	@echo "📝 Formatting Go code..."
	goimports -w .
```

### Success Criteria:

#### Automated Verification:
- [ ] Makefile syntax is valid (no parse errors)
- [ ] `make fmt-go` executes without errors
- [ ] `make fmt` executes without errors (calls fmt-go and fmt-py)
- [ ] Existing Go tests pass: `go test ./...`
- [ ] Go build succeeds: `make build`

#### Manual Verification:
- [ ] Create a test Go file with formatting issues and unused imports
- [ ] Run `make fmt-go` and verify the file is correctly formatted
- [ ] Verify imports are sorted and unused imports are removed
- [ ] Verify code spacing and indentation are correct
- [ ] Confirm no difference in output between old (gofmt + goimports) and new (goimports only)

**Note**: Complete all automated verification, then pause for manual confirmation before proceeding.

---

## Testing Strategy

### Unit Tests:
Not applicable - this is a build system change, not a code change.

### Integration Tests:
- **Test 1: Verify fmt-go target works**
  ```bash
  make fmt-go
  ```
  Expected: Success message "📝 Formatting Go code..." followed by successful completion

- **Test 2: Verify parent fmt target works**
  ```bash
  make fmt
  ```
  Expected: Both fmt-go and fmt-py execute, ending with "✅ All formatting complete"

- **Test 3: Verify CI integration (if applicable)**
  ```bash
  make ci
  ```
  Expected: All CI checks pass, including fmt targets

### Manual Testing Steps:

1. **Create a test file with formatting issues:**
   ```bash
   cat > /tmp/test_fmt.go << 'EOF'
   package main
   import (
       "fmt"
       "os"
   )
   func main( ){
   fmt.Println("test")
   }
   EOF
   ```

2. **Run the fmt-go target:**
   ```bash
   make fmt-go
   ```

3. **Verify the results:**
   - Unused `os` import should be removed
   - Spacing around `func main()` should be fixed
   - Indentation should be corrected
   - File should be formatted identically to what `gofmt -w .` would produce

4. **Test with actual project files:**
   ```bash
   # Intentionally malform a Go file
   # Run make fmt-go
   # Verify it's corrected
   ```

## Migration Notes
No migration required. This is a simple line removal with no data or API changes.

## Rollback Plan
If issues arise (highly unlikely):
1. Add back line 73: `gofmt -w .` to the fmt-go target
2. Re-run `make fmt` to verify restoration

## References
- Research: `/Users/simo/Projects/autodev/.wreckit/items/017-remove-redundant-gofmt-from-makefile/research.md`
- Makefile: `/Users/simo/Projects/autodev/Makefile:70-73`
- Project Guidelines: `/Users/simo/Projects/autodev/AGENTS.md:20`
- Codebase Analysis: `/Users/simo/Projects/autodev/CODEBASE_ANALYSIS_REPORT.md:357-363`
