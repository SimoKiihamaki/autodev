# Document AUTO_PRD_* environment variables Implementation Plan

## Overview
Expand the Environment Variables section in `docs/OPERATIONS.md` to document all 18 AUTO_PRD_* environment variables used throughout the AutoDev codebase. Currently only 8 of 18 variables are documented, forcing users to read source code to discover configuration options for security settings, performance tuning, and debugging features.

## Current State Analysis

### Existing Documentation
The file `docs/OPERATIONS.md` contains a partial Environment Variables section at lines 181-193 with only 8 variables documented in a simple two-column table format (Variable | Purpose).

**Documented variables:**
- AUTO_PRD_EXECUTOR_POLICY
- AUTO_PRD_EXECUTOR_IMPLEMENT
- AUTO_PRD_EXECUTOR_FIX
- AUTO_PRD_EXECUTOR_PR
- AUTO_PRD_EXECUTOR_REVIEW_FIX
- AUTO_PRD_ALLOW_UNSAFE_EXECUTION
- AUTO_PRD_CODEX_TIMEOUT_SECONDS
- AUTO_PRD_CLAUDE_TIMEOUT_SECONDS

**Missing documentation for 10 variables:**
- AUTO_PRD_ALLOW_NO_ZSH (constants.py:33)
- AUTO_PRD_STREAMING_CHUNK_SIZE (agents.py:172)
- AUTO_PRD_STREAMING_POLL_TIMEOUT (agents.py:198)
- AUTO_PRD_SAFE_SCRIPT_DIRS (runner.go:233)
- AUTO_PRD_ASCII_OUTPUT (review_loop.py:179)
- AUTO_PRD_STRICT (config.go:26)
- AUTO_PRD_ROOT (command.py:109,645,781,787,838)
- AUTO_PRD_SHELL (command.py:316)
- AUTO_PRD_SCRIPT (path.go:25)

### Key Discoveries

1. **Pattern:** All environment variables use the `AUTO_PRD_` prefix consistently across both Python and Go codebases
2. **Performance variables read at import time:** `AUTO_PRD_STREAMING_CHUNK_SIZE` and `AUTO_PRD_STREAMING_POLL_TIMEOUT` are read once at module import (agents.py:160-164), meaning they require process restart to take effect
3. **Timeout variable behavior:** Both timeout variables accept special values "none", "no", "off", "disable", "disabled" to disable timeouts (agents.py:227-242)
4. **Security-critical variable:** `AUTO_PRD_SAFE_SCRIPT_DIRS` is a colon-separated whitelist for Python automation scripts (runner.go:233) - critical for security
5. **Internal variables:** `AUTO_PRD_ROOT` and `AUTO_PRD_SHELL` are auto-set by the system for subprocess communication, not typically user-configured
6. **Default values:**
   - AUTO_PRD_STREAMING_CHUNK_SIZE: 4096 bytes
   - AUTO_PRD_STREAMING_POLL_TIMEOUT: 0.1 seconds
   - AUTO_PRD_CLAUDE_TIMEOUT_SECONDS: 5400 (90 minutes)
   - AUTO_PRD_CODEX_TIMEOUT_SECONDS: None (no default timeout)

### Constraint: Documentation-Only Change
This task is documentation-only. No code changes are required. The scope is limited to expanding `docs/OPERATIONS.md`.

## Desired End State

The Environment Variables section in `docs/OPERATIONS.md` will contain:

1. **Categorized organization** - Variables grouped by functional area (Executor Control, Security & Safety, Timeout & Performance, Output & Debugging, Internal System)
2. **Complete documentation** - All 18 environment variables documented
3. **Enhanced detail** - Table format includes columns for Variable, Purpose, Valid Values, and Default
4. **Clear usage notes** - Special behaviors documented (e.g., performance vars read at startup, internal variables auto-set)
5. **Security warnings** - Security-sensitive variables marked appropriately

### Success Criteria

#### Automated Verification:
- [ ] Markdown syntax is valid (no broken tables, proper formatting)
- [ ] All documented environment variables exist in the codebase (verified by grep)

#### Manual Verification:
- [ ] Documentation renders correctly in Markdown viewer
- [ ] Default values match source code
- [ ] Valid values lists are complete and accurate
- [ ] Security variables have appropriate warnings
- [ ] Internal variables are clearly marked as auto-set

## What We're NOT Doing

- **No code changes** - Not adding comments to source code pointing to documentation (out of scope)
- **No automated testing** - Not creating tests to verify documentation accuracy (out of scope)
- **No reorganization** - Not restructuring the entire OPERATIONS.md file (only expanding the existing section)
- **No new documentation files** - Not creating separate environment variable reference (staying in OPERATIONS.md)

## Implementation Approach

### Strategy: Expand Existing Section
Rather than reorganizing the entire documentation structure, expand the existing Environment Variables section at `docs/OPERATIONS.md:181-193`. This minimizes disruption and follows the principle of least change.

### Documentation Structure

Replace the simple 2-column table with categorized 4-column tables:

1. **Executor Control** (5 variables) - User-facing, high priority
2. **Security & Safety** (3 variables) - User-facing, high priority
3. **Timeout & Performance** (4 variables) - User-facing, medium priority
4. **Output & Debugging** (2 variables) - User-facing, low priority
5. **Internal System Variables** (3 variables) - Not user-facing, document for reference

### Table Format
Use 4-column format for clarity:
- **Variable**: Environment variable name (in code font)
- **Purpose**: Concise description of what it does
- **Valid Values**: Accepted values (e.g., "codex-first, codex-only, claude-only")
- **Default**: Default value or behavior (e.g., "(uses policy)", "4096", "(unset)")

---

## Phase 1: Document Executor Control Variables

### Overview
Expand documentation for the 5 executor policy variables that control which AI executor (Codex or Claude) handles different phases of the PRD workflow.

### Changes Required:

#### 1. docs/OPERATIONS.md
**File**: `docs/OPERATIONS.md`
**Location**: Lines 181-193
**Changes**: Replace the existing simple table with a categorized 4-column table starting with Executor Control

**New content structure:**
```markdown
## Environment Variables

### Executor Control

Control which AI executor (Codex or Claude) handles different phases of the PRD workflow.

| Variable | Purpose | Valid Values | Default |
|----------|---------|--------------|---------|
| `AUTO_PRD_EXECUTOR_POLICY` | Override global executor policy | codex-first, codex-only, claude-only | codex-first |
| `AUTO_PRD_EXECUTOR_IMPLEMENT` | Override executor for local implementation phase | codex, claude, or empty | (uses policy) |
| `AUTO_PRD_EXECUTOR_FIX` | Override executor for CodeRabbit fix phase | codex, claude, or empty | (uses policy) |
| `AUTO_PRD_EXECUTOR_PR` | Override executor for PR creation phase | codex, claude, or empty | (uses policy) |
| `AUTO_PRD_EXECUTOR_REVIEW_FIX` | Override executor for review/fix phase | codex, claude, or empty | (uses policy) |
```

### Success Criteria:

#### Automated Verification:
- [ ] Markdown table syntax is valid (check with markdown linter)

#### Manual Verification:
- [ ] Table renders correctly with all columns aligned
- [ ] Valid values match the constants in `tools/auto_prd/policy.py:13-83`
- [ ] Default values are accurate (policy.py:14, env_key_map:79-84)

**Note**: Complete verification before proceeding to Phase 2.

---

## Phase 2: Document Security & Safety Variables

### Overview
Document the 3 environment variables that control security settings and safety checks, including script directory whitelisting and unsafe operation controls.

### Changes Required:

#### 1. docs/OPERATIONS.md
**File**: `docs/OPERATIONS.md`
**Location**: After Executor Control section (new section)
**Changes**: Add Security & Safety section

**New content:**
```markdown
### Security & Safety

Control security settings and safety checks for automation scripts and command execution.

| Variable | Purpose | Valid Values | Default |
|----------|---------|--------------|---------|
| `AUTO_PRD_ALLOW_UNSAFE_EXECUTION` | Allow unsafe operations (e.g., command injection risks) | 1 (requires CI=1) | (unset) |
| `AUTO_PRD_SAFE_SCRIPT_DIRS` | Colon-separated whitelist of directories for Python automation scripts | colon-separated absolute paths | (from config) |
| `AUTO_PRD_ALLOW_NO_ZSH` | Skip zsh binary requirement | 1, true, yes | (unset) |

**⚠️ Security Note:** `AUTO_PRD_SAFE_SCRIPT_DIRS` is a critical security feature. Only add directories you trust. Python scripts outside these directories cannot be executed.
```

### Success Criteria:

#### Automated Verification:
- [ ] Markdown syntax is valid

#### Manual Verification:
- [ ] AUTO_PRD_ALLOW_UNSAFE_EXECUTION docs match `tools/auto_prd/constants.py:54` and `internal/config/config.go:23`
- [ ] AUTO_PRD_SAFE_SCRIPT_DIRS docs match `internal/runner/runner.go:233`
- [ ] AUTO_PRD_ALLOW_NO_ZSH docs match `tools/auto_prd/constants.py:33`
- [ ] Security warning is prominently displayed

**Note**: Complete verification before proceeding to Phase 3.

---

## Phase 3: Document Timeout & Performance Variables

### Overview
Document the 4 environment variables that control execution timeouts and streaming performance parameters.

### Changes Required:

#### 1. docs/OPERATIONS.md
**File**: `docs/OPERATIONS.md`
**Location**: After Security & Safety section (new section)
**Changes**: Add Timeout & Performance section

**New content:**
```markdown
### Timeout & Performance

Control execution timeouts and streaming performance parameters.

| Variable | Purpose | Valid Values | Default |
|----------|---------|--------------|---------|
| `AUTO_PRD_CODEX_TIMEOUT_SECONDS` | Codex execution timeout in seconds | positive integer, "none", "off", "disable" | (no timeout) |
| `AUTO_PRD_CLAUDE_TIMEOUT_SECONDS` | Claude execution timeout in seconds | positive integer, "none", "off", "disable" | 5400 (90 min) |
| `AUTO_PRD_STREAMING_CHUNK_SIZE` | Streaming read chunk size in bytes | positive integer | 4096 |
| `AUTO_PRD_STREAMING_POLL_TIMEOUT` | Streaming poll timeout in seconds | positive float | 0.1 |

**⚠️ Performance Note:** Streaming variables (`AUTO_PRD_STREAMING_CHUNK_SIZE`, `AUTO_PRD_STREAMING_POLL_TIMEOUT`) are read once at process startup. Changes require restarting the TUI to take effect.
```

### Success Criteria:

#### Automated Verification:
- [ ] Markdown syntax is valid

#### Manual Verification:
- [ ] Timeout defaults match `tools/auto_prd/agents.py:254,260,277-279`
- [ ] Special timeout values ("none", "off", "disable") documented per `agents.py:227-242`
- [ ] Streaming defaults match `tools/auto_prd/agents.py:174,200`
- [ ] Performance note accurately describes the import-time reading behavior documented at `agents.py:160-164`

**Note**: Complete verification before proceeding to Phase 4.

---

## Phase 4: Document Output & Debugging Variables

### Overview
Document the 2 environment variables that control output formatting and debugging/validation behavior.

### Changes Required:

#### 1. docs/OPERATIONS.md
**File**: `docs/OPERATIONS.md`
**Location**: After Timeout & Performance section (new section)
**Changes**: Add Output & Debugging section

**New content:**
```markdown
### Output & Debugging

Control output formatting and validation behavior.

| Variable | Purpose | Valid Values | Default |
|----------|---------|--------------|---------|
| `AUTO_PRD_ASCII_OUTPUT` | Force ASCII instead of Unicode box-drawing characters | 1, true, yes | (unset) |
| `AUTO_PRD_STRICT` | Enable strict config validation (fail on errors instead of warning) | 1 | (unset) |
```

### Success Criteria:

#### Automated Verification:
- [ ] Markdown syntax is valid

#### Manual Verification:
- [ ] AUTO_PRD_ASCII_OUTPUT values match `tools/auto_prd/review_loop.py:179-183`
- [ ] AUTO_PRD_STRICT docs match `internal/config/config.go:26`

**Note**: Complete verification before proceeding to Phase 5.

---

## Phase 5: Document Internal System Variables

### Overview
Document the 3 environment variables that are automatically set by the system for subprocess communication, typically not configured by users.

### Changes Required:

#### 1. docs/OPERATIONS.md
**File**: `docs/OPERATIONS.md`
**Location**: After Output & Debugging section (new section)
**Changes**: Add Internal System Variables section

**New content:**
```markdown
### Internal System Variables

These variables are set automatically by the system and typically do not require manual configuration. They are documented here for reference.

| Variable | Purpose |
|----------|---------|
| `AUTO_PRD_ROOT` | Auto-set repository root path for subprocess communication |
| `AUTO_PRD_SHELL` | Auto-set zsh path for shell environment policy |
| `AUTO_PRD_SCRIPT` | Override Python automation script path (for non-standard installations) |
```

### Success Criteria:

#### Automated Verification:
- [ ] Markdown syntax is valid

#### Manual Verification:
- [ ] AUTO_PRD_ROOT docs match usage in `tools/auto_prd/command.py:109,645,781,787,838`
- [ ] AUTO_PRD_SHELL docs match usage in `tools/auto_prd/command.py:316`
- [ ] AUTO_PRD_SCRIPT docs match usage in `internal/tui/path.go:25,35`
- [ ] Clear notation that these are typically auto-set

---

## Testing Strategy

### Manual Testing Steps:

1. **Verify all variables exist in codebase:**
   ```bash
   cd /Users/simo/Projects/autodev
   grep -r "AUTO_PRD_EXECUTOR_POLICY" --include="*.py" --include="*.go"
   grep -r "AUTO_PRD_STREAMING_CHUNK_SIZE" --include="*.py" --include="*.go"
   # ... repeat for all 18 variables
   ```

2. **Verify default values:**
   - Check `tools/auto_prd/agents.py:174` for STREAMING_CHUNK_SIZE (4096)
   - Check `tools/auto_prd/agents.py:200` for STREAMING_POLL_TIMEOUT (0.1)
   - Check `tools/auto_prd/agents.py:260` for CLAUDE_TIMEOUT (5400)
   - Check `tools/auto_prd/policy.py:14` for EXECUTOR_POLICY_DEFAULT (codex-first)

3. **Verify valid values:**
   - Check `tools/auto_prd/policy.py:13` for EXECUTOR_CHOICES
   - Check `tools/auto_prd/agents.py:227-242` for timeout value parsing
   - Check `tools/auto_prd/review_loop.py:179-183` for ASCII_OUTPUT truthy values

4. **Verify documentation rendering:**
   - Open `docs/OPERATIONS.md` in a Markdown viewer
   - Check that all tables render correctly
   - Verify column alignment is proper
   - Confirm categorization headers are clear

5. **Verify security warnings:**
   - Check that `AUTO_PRD_SAFE_SCRIPT_DIRS` has a security warning
   - Verify the warning text is appropriately cautionary

6. **Verify performance note:**
   - Check that streaming variables have a note about being read at startup
   - Verify the note accurately describes the behavior

## Migration Notes

No migration required. This is a documentation-only change that expands existing documentation without modifying any code or changing any behavior.

## References

- Research: `/Users/simo/Projects/autodev/.wreckit/items/023-document-autoprd-environment-variables/research.md`
- Current documentation: `docs/OPERATIONS.md:181-193`
- Executor policy: `tools/auto_prd/policy.py:13-83`, `internal/config/config.go:16-22`
- Constants: `tools/auto_prd/constants.py:33,54`
- Performance: `tools/auto_prd/agents.py:160-279`
- Security: `internal/runner/runner.go:233`, `tools/auto_prd/constants.py:54`
- Output: `tools/auto_prd/review_loop.py:163-185`, `internal/config/config.go:26`
- Internal: `tools/auto_prd/command.py:109,316,645,781,787,838`, `internal/tui/path.go:25,35`
