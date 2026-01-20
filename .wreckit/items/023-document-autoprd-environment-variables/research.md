# Research: Document AUTO_PRD_* environment variables

**Date**: 2025-01-20
**Item**: 023-document-autoprd-environment-variables

## Research Question
Users must read source code to discover available environment variables.

**Motivation:** Improves discoverability of configuration options.

**Signals:** priority: low

## Summary
The AutoDev codebase uses 18 different `AUTO_PRD_*` environment variables for configuration across both Python (tools/auto_prd) and Go (internal/) components. These variables control executor selection, security settings, timeout behavior, output formatting, and system paths. Currently, only 8 of these variables are documented in `docs/OPERATIONS.md:181-193`, leaving users to discover the remaining 10 variables by reading source code.

The environment variables fall into five categories:
1. **Executor Control** (6 vars): Policy selection and per-phase executor overrides
2. **Security & Safety** (3 vars): Script whitelisting and unsafe operation controls
3. **Timeout & Performance** (4 vars): Execution timeouts and streaming parameters
4. **Output & Debugging** (2 vars): ASCII mode and test utilities
5. **Internal System** (3 vars): Auto-set paths for subprocess communication

The documentation should be added to `docs/OPERATIONS.md` where a partial Environment Variables section already exists, expanding it to cover all 18 variables with clear descriptions, valid values, and use cases.

## Current State Analysis

### Existing Implementation
The codebase has comprehensive environment variable support across Python and Go:

**Python (tools/auto_prd):**
- `constants.py:33` - `AUTO_PRD_ALLOW_NO_ZSH` - Skip zsh requirement
- `constants.py:54` - `AUTO_PRD_ALLOW_UNSAFE_EXECUTION` - Enable unsafe operations
- `agents.py:172-219` - `AUTO_PRD_STREAMING_CHUNK_SIZE`, `AUTO_PRD_STREAMING_POLL_TIMEOUT` - Streaming performance tuning
- `agents.py:254` - `AUTO_PRD_CODEX_TIMEOUT_SECONDS` - Codex execution timeout
- `agents.py:277-278` - `AUTO_PRD_CLAUDE_TIMEOUT_SECONDS` - Claude execution timeout
- `policy.py:15,80-83` - `AUTO_PRD_EXECUTOR_POLICY`, `AUTO_PRD_EXECUTOR_*` - Executor selection
- `review_loop.py:179` - `AUTO_PRD_ASCII_OUTPUT` - ASCII mode for terminal output
- `command.py:109,645,781,787,838` - `AUTO_PRD_ROOT` - Auto-set repository root path
- `command.py:316` - `AUTO_PRD_SHELL` - Auto-set zsh path for subprocess

**Go (internal/runner, internal/config):**
- `config/config.go:16-27` - Env var constants for executor policy, timeouts, strict mode
- `runner/runner.go:233` - `AUTO_PRD_SAFE_SCRIPT_DIRS` - Script directory whitelist
- `runner/runner.go:173,230,398,999` - Script directory validation logic
- `runner/runner_test.go:199-203` - Test environment setup
- `runner/build_args_test.go:86` - Integration tests for script whitelisting
- `tui/path.go:25,35` - `AUTO_PRD_SCRIPT` - Override Python script path
- `tui/run.go:192,197` - Script path validation error messages

**Current Documentation:**
- `docs/OPERATIONS.md:181-193` - Documents 8 variables (executor policy, per-phase executors, unsafe execution, timeouts)
- Missing: 10 variables including security settings, performance tuning, and debugging options

### Key Files

#### Configuration & Constants
- `tools/auto_prd/constants.py:33-54` - Safety and shell environment variables
  - `AUTO_PRD_ALLOW_NO_ZSH`: Skip zsh binary requirement
  - `AUTO_PRD_ALLOW_UNSAFE_EXECUTION`: Allow dangerous commands (requires CI=1)

- `tools/auto_prd/policy.py:13-83` - Executor policy environment variables
  - `AUTO_PRD_EXECUTOR_POLICY`: Global executor selection (codex-first/codex-only/claude-only)
  - `AUTO_PRD_EXECUTOR_IMPLEMENT`: Override executor for local implementation phase
  - `AUTO_PRD_EXECUTOR_FIX`: Override executor for CodeRabbit fix phase
  - `AUTO_PRD_EXECUTOR_PR`: Override executor for PR creation phase
  - `AUTO_PRD_EXECUTOR_REVIEW_FIX`: Override executor for review/fix phase

- `internal/config/config.go:16-27` - Go-side environment variable constants
  - Defines all env var names as constants for consistency
  - Used for config loading and validation

#### Performance & Timeouts
- `tools/auto_prd/agents.py:160-279` - Performance tuning environment variables
  - `AUTO_PRD_STREAMING_CHUNK_SIZE`: Bytes read per streaming chunk (default: 4096)
  - `AUTO_PRD_STREAMING_POLL_TIMEOUT`: Seconds to wait for streaming data (default: 0.1)
  - `AUTO_PRD_CODEX_TIMEOUT_SECONDS`: Codex execution timeout (default: none)
  - `AUTO_PRD_CLAUDE_TIMEOUT_SECONDS`: Claude execution timeout (default: 5400)

  **Important Pattern:** These vars are read ONCE at module import time (line 160-164 comment). This is intentional for performance but means they can't be changed during execution.

#### Security & Paths
- `internal/runner/runner.go:173,233,398,999` - Script directory whitelist
  - `AUTO_PRD_SAFE_SCRIPT_DIRS`: Colon-separated path whitelist for Python scripts
  - Critical security feature preventing arbitrary script execution
  - Merged with config `SafeScriptDirs` field at runtime

- `internal/tui/path.go:25,35` - Script path override
  - `AUTO_PRD_SCRIPT`: Override Python automation script path
  - Fallback for users with non-standard script locations

- `tools/auto_prd/command.py:109,645,781,787,838` - Repository root tracking
  - `AUTO_PRD_ROOT`: Auto-set repository root path for subprocesses
  - Set by runner, read by Python tools for project location
  - Internal variable, not typically user-configured

- `tools/auto_prd/command.py:316` - Shell environment
  - `AUTO_PRD_SHELL`: Auto-set zsh path for shell environment policy
  - Set by runner, consumed by Python subprocess

#### Output & Debugging
- `tools/auto_prd/review_loop.py:163-185` - ASCII output mode
  - `AUTO_PRD_ASCII_OUTPUT`: Force ASCII instead of Unicode box-drawing chars
  - Useful for terminals with poor Unicode support
  - Values: "1", "true", "yes" (case-insensitive)

#### Internal / Test Variables
- `tools/auto_prd/tests/test_agents.py:69-105` - Test-only variable
  - `AUTO_PRD_TEST_TIMEOUT`: Mock variable for timeout testing
  - Not used in production code

- `internal/config/config.go:26,456-461` - Strict validation mode
  - `AUTO_PRD_STRICT`: Enable strict config validation (fail on errors instead of warning)
  - Values: "1" to enable
  - Example: Rejects invalid MaxBatchSize instead of auto-correcting

## Technical Considerations

### Dependencies
- **Documentation Format:** Markdown (existing docs use Markdown)
- **Documentation Location:** `docs/OPERATIONS.md` (section exists at lines 181-193)
- **No Code Changes Required:** This is documentation-only

### Patterns to Follow
1. **Existing Documentation Pattern** (from `docs/OPERATIONS.md:181-193`):
   - Table format with Variable | Purpose columns
   - Concise descriptions
   - Alphabetical ordering

2. **Environment Variable Naming**:
   - All use `AUTO_PRD_` prefix (not `APRD_`)
   - Use underscores instead of hyphens
   - Use uppercase for variable names
   - See `internal/config/config.go:16-27` for canonical definitions

3. **Categorization Strategy**:
   - Group related variables together
   - Separate user-facing from internal variables
   - Mark security-sensitive variables clearly

4. **Value Specification**:
   - Document default values where applicable
   - List valid values (e.g., codex-first/codex-only/claude-only)
   - Note special values (e.g., "off", "none", "disable" for timeouts)

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Documentation drift (code changes but docs don't) | Medium | Add comment in code pointing to docs when variables are defined; include file:line references |
| Overwhelming users with too many options | Low | Separate user-facing variables from internal/debug variables; use collapsible sections or separate tables |
| Incorrect default values documented | Medium | Cross-reference with source code; verify defaults at time of writing |
| Security implications of exposing sensitive vars | Low | Only document security variables that are meant for user configuration (e.g., SAFE_SCRIPT_DIRS); mark internal ones clearly |

## Recommended Approach

### Phase 1: Categorize Variables
Create organized sections:

1. **Executor Control** (User-facing, high priority)
   - AUTO_PRD_EXECUTOR_POLICY
   - AUTO_PRD_EXECUTOR_IMPLEMENT
   - AUTO_PRD_EXECUTOR_FIX
   - AUTO_PRD_EXECUTOR_PR
   - AUTO_PRD_EXECUTOR_REVIEW_FIX

2. **Security & Safety** (User-facing, high priority)
   - AUTO_PRD_ALLOW_UNSAFE_EXECUTION
   - AUTO_PRD_SAFE_SCRIPT_DIRS
   - AUTO_PRD_ALLOW_NO_ZSH

3. **Timeout & Performance** (User-facing, medium priority)
   - AUTO_PRD_CODEX_TIMEOUT_SECONDS
   - AUTO_PRD_CLAUDE_TIMEOUT_SECONDS
   - AUTO_PRD_STREAMING_CHUNK_SIZE
   - AUTO_PRD_STREAMING_POLL_TIMEOUT

4. **Output & Debugging** (User-facing, low priority)
   - AUTO_PRD_ASCII_OUTPUT
   - AUTO_PRD_STRICT

5. **Internal System** (Not user-facing, document for reference)
   - AUTO_PRD_ROOT
   - AUTO_PRD_SHELL
   - AUTO_PRD_SCRIPT

### Phase 2: Write Documentation
Expand `docs/OPERATIONS.md:181-193` with:

```markdown
## Environment Variables

### Executor Control

| Variable | Purpose | Valid Values | Default |
|----------|---------|--------------|---------|
| `AUTO_PRD_EXECUTOR_POLICY` | Override executor policy | codex-first, codex-only, claude-only | codex-first |
| `AUTO_PRD_EXECUTOR_IMPLEMENT` | Override implement phase executor | codex, claude, or empty | (uses policy) |
| `AUTO_PRD_EXECUTOR_FIX` | Override fix phase executor | codex, claude, or empty | (uses policy) |
| `AUTO_PRD_EXECUTOR_PR` | Override PR phase executor | codex, claude, or empty | (uses policy) |
| `AUTO_PRD_EXECUTOR_REVIEW_FIX` | Override review_fix phase executor | codex, claude, or empty | (uses policy) |

### Security & Safety

| Variable | Purpose | Valid Values | Default |
|----------|---------|--------------|---------|
| `AUTO_PRD_ALLOW_UNSAFE_EXECUTION` | Allow unsafe operations | 1 (requires CI=1) | (unset) |
| `AUTO_PRD_SAFE_SCRIPT_DIRS` | Whitelist directories for automation scripts | colon-separated paths | (from config) |
| `AUTO_PRD_ALLOW_NO_ZSH` | Skip zsh requirement | 1, true, yes | (unset) |

### Timeout & Performance

| Variable | Purpose | Valid Values | Default |
|----------|---------|--------------|---------|
| `AUTO_PRD_CODEX_TIMEOUT_SECONDS` | Codex execution timeout | seconds, "none", "off" | (no timeout) |
| `AUTO_PRD_CLAUDE_TIMEOUT_SECONDS` | Claude execution timeout | seconds, "none", "off" | 5400 (90 min) |
| `AUTO_PRD_STREAMING_CHUNK_SIZE` | Streaming read chunk size in bytes | positive integer | 4096 |
| `AUTO_PRD_STREAMING_POLL_TIMEOUT` | Streaming poll timeout in seconds | positive float | 0.1 |

**Note:** Performance variables are read once at process startup. Changes require restarting the TUI.

### Output & Debugging

| Variable | Purpose | Valid Values | Default |
|----------|---------|--------------|---------|
| `AUTO_PRD_ASCII_OUTPUT` | Force ASCII instead of Unicode output | 1, true, yes | (unset) |
| `AUTO_PRD_STRICT` | Enable strict config validation | 1 | (unset) |

### Internal System Variables

These variables are set automatically by the system and typically not configured by users:

| Variable | Purpose |
|----------|---------|
| `AUTO_PRD_ROOT` | Auto-set repository root path |
| `AUTO_PRD_SHELL` | Auto-set zsh path for subprocess |
| `AUTO_PRD_SCRIPT` | Override Python automation script path |
```

### Phase 3: Cross-Reference
Add comments in source code pointing to documentation:
- In `tools/auto_prd/constants.py` near env var definitions
- In `internal/config/config.go` near env var constants
- Example: `# See docs/OPERATIONS.md for complete environment variable reference`

## Open Questions

1. **Internal Variables**: Should `AUTO_PRD_ROOT`, `AUTO_PRD_SHELL`, and `AUTO_PRD_SCRIPT` be documented in the user guide or kept as internal implementation details?
   - **Recommendation**: Document them in a separate "Internal System Variables" subsection with clear notation that they're auto-set

2. **Variable Ordering**: Should variables be ordered alphabetically or by category/importance?
   - **Recommendation**: By category (Executor, Security, Performance, etc.) as this aligns with user mental models

3. **Default Values**: Should all defaults be documented, even when they're computed or conditionally set?
   - **Recommendation**: Document explicit defaults, note computed defaults (e.g., "(uses policy)")

4. **Documentation Testing**: How to ensure documentation stays in sync with code?
   - **Recommendation**: Add file:line references in docs; consider automated tests that verify documented vars exist in code
