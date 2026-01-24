# Research: Standalone Support Mode CLI

**Date**: January 20, 2025
**Item**: 024-standalone-support-mode-cli

## Research Question
Support mode is currently embedded within the auto_prd tool, preventing it from being used with other coding frameworks (Cursor, Windsurf, Claude Code, Copilot, etc.)

**Motivation:** Creates a framework-agnostic companion tool for continuous monitoring and review, improving developer workflow and enabling broader adoption across different AI coding environments

**Success criteria:**
- Tool runs without auto_prd installed
- Works with existing tracker/state files
- Simple CLI with sensible defaults
- Configurable polling interval with graceful shutdown

**Technical constraints:**
- Maintain compatibility with existing .aprd/support_state.json format
- Extract minimal dependencies from auto_prd (command.run_cmd, git_ops, tracker_generator)
- Support multiple entry points: python -m support, installed CLI, optional Go binary

**In scope:**
- Repository state monitoring (branch, commit SHA, working tree)
- Tracker validation (structure, features, tasks, dependencies)
- PRD synchronization (checkbox extraction, comparison)
- Git quality checks (git diff --check)
- State persistence between iterations

**Out of scope:**
- Complete rewrite of auto_prd
- Breaking changes to existing tracker/state file formats

**Signals:** priority: high, urgency: ASAP

## Summary

The current support mode implementation (`/tools/auto_prd/support_loop.py:138`) is deeply integrated into the auto_prd tool, requiring the full auto_prd package to be installed. To create a standalone support mode CLI, we need to extract the core monitoring and validation logic while maintaining backward compatibility with existing tracker and state file formats.

The implementation requires extracting minimal dependencies from auto_prd:
1. **Git operations** (`git_ops.py`) - repository state monitoring
2. **Command execution** (`command.py`) - safe subprocess execution
3. **Tracker utilities** (`tracker_generator.py`, `tracker_validator.py`) - tracker validation and loading
4. **Verification persistence** (`verification_persistence.py`) - verification run status checking
5. **Logging utilities** (`logging_utils.py`) - consistent logging
6. **Guardrails** (`guardrails.py`) - optional, for guardrail sign display

The standalone tool should be packaged as a separate Python package (`support-mode`) with its own CLI entry point, while sharing the same `.aprd` directory structure and file formats.

## Current State Analysis

### Existing Implementation

Support mode is currently invoked via the `--support-mode` flag in auto_prd's CLI (`/tools/auto_prd/cli.py:92-95`), which calls `run_support_mode()` from `support_loop.py`. The function runs an infinite loop that:

1. Monitors repository state (branch, commit SHA, working tree status)
2. Loads and validates the tracker file (`.aprd/tracker.json`)
3. Checks tracker state consistency
4. Compares PRD checkboxes with tracker tasks
5. Runs git quality checks (`git diff --check`)
6. Checks verification run status and freshness
7. Displays guardrails sign count
8. Outputs issues, warnings, and suggestions
9. Persists state to `.aprd/support_state.json`
10. Sleeps for configured polling interval

The implementation has these key characteristics:
- **Entry point**: `/tools/auto_prd/cli.py:92` (`--support-mode` flag)
- **Main logic**: `/tools/auto_prd/support_loop.py:138` (`run_support_mode()`)
- **State format**: `.aprd/support_state.json` (JSON with iteration, last_reviewed_sha, last_reviewed_prd_hash, last_reviewed_at)
- **Polling**: Configurable via `--review-poll-seconds` (default 120s, minimum 5s)
- **Shutdown**: Graceful via KeyboardInterrupt handler (`/tools/auto_prd/support_loop.py:452`)

### Key Files

#### Core Support Mode Logic
- **`/tools/auto_prd/support_loop.py`** (459 lines)
  - Lines 26-32: `SupportState` dataclass definition
  - Lines 34-62: State persistence functions (`load_support_state`, `save_support_state`)
  - Lines 65-105: Text normalization and PRD checkbox extraction helpers
  - Lines 108-129: Recent commits retrieval with git log parsing
  - Lines 138-458: `run_support_mode()` main polling loop
  - Lines 180-226: Tracker loading, validation, and statistics
  - Lines 265-296: Dependency validation between features
  - Lines 353-386: PRD checkbox to tracker task comparison
  - Lines 388-417: Git quality checks and verification status

#### Git Operations Dependency
- **`/tools/auto_prd/git_ops.py`** (375 lines)
  - Lines 36-38: `git_root()` - find repository root
  - Lines 98-100: `workspace_has_changes()` - check for uncommitted changes
  - Lines 103-105: `git_status_snapshot()` - get working tree status
  - Lines 108-110: `git_current_branch()` - get current branch name
  - Lines 113-115: `git_head_sha()` - get HEAD commit SHA
  - Uses `run_cmd()` from `command.py` for all git operations

#### Command Execution Dependency
- **`/tools/auto_prd/command.py`** (851 lines)
  - Lines 422-612: `run_cmd()` - main command execution with retry logic
  - Lines 32-90: `CommandResult` dataclass for structured output
  - Lines 134-157: `find_repo_root()` - locate .git directory
  - Safety validation: command allowlist, CWD validation, argument sanitization
  - Retry support with exponential backoff for transient failures

#### Tracker Dependencies
- **`/tools/auto_prd/tracker_generator.py`** (1075 lines)
  - Lines 295-298: `compute_prd_hash()` - SHA-256 hash for PRD change detection
  - Lines 301-303: `get_tracker_path()` - path to `.aprd/tracker.json`
  - Lines 306-332: `load_tracker()` - load existing tracker with size validation
  - Lines 580-672: `validate_tracker()` - structural validation with JSON schema

- **`/tools/auto_prd/tracker_validator.py`** (285 lines)
  - Lines 16-18: `_as_list()` - coerce values to list for safe iteration
  - Lines 21-103: `validate_tracker_state()` - state consistency validation
  - Lines 106-164: `validate_completion_consistency()` - agent vs tracker comparison

#### Verification Persistence
- **`/tools/auto_prd/verification_persistence.py`** (342 lines)
  - Lines 38-96: `VerifierResult` and `VerificationRun` dataclasses
  - Lines 98-188: `VerificationPersistence` class for JSONL storage
  - Lines 190-204: `get_latest_run()` - retrieve most recent verification
  - Lines 232-252: `is_run_fresh()` - check if verification is current
  - Storage format: `.aprd/verification/runs.jsonl` (JSONL format)

#### Guardrails (Optional)
- **`/tools/auto_prd/guardrails.py`** (177 lines shown, file continues)
  - `Sign` dataclass for learned patterns from mistakes
  - `load_guardrails()` function to load signs from `~/.config/aprd/guardrails/<repo_slug>.md`
  - Used in support mode to display count of active guardrails

### State File Formats

#### Support State: `.aprd/support_state.json`
```json
{
  "iteration": 1,
  "last_reviewed_sha": "abc123...",
  "last_reviewed_prd_hash": "sha256:def456...",
  "last_reviewed_at": "2025-01-20T12:00:00+00:00"
}
```

#### Tracker: `.aprd/tracker.json`
- Version: "2.0.0"
- Metadata includes: prd_source, prd_hash, created_at, created_by, project_context
- Features array with: id, name, status, dependencies, tasks, acceptance_criteria
- validation_summary includes: total_features, total_tasks, estimated_complexity
- Full schema defined in `/tools/auto_prd/tracker_schema.json`

## Technical Considerations

### Dependencies

#### Internal (auto_prd modules to extract)
1. **command.py** (partial extraction needed)
   - `run_cmd()` function (lines 422-612)
   - `CommandResult` dataclass (lines 32-90)
   - `find_repo_root()` function (lines 134-157)
   - Safety helpers: `validate_command_args()`, `validate_cwd()`, `sanitize_args()`
   - Constants: `COMMAND_ALLOWLIST`, `SAFE_CWD_ROOTS`, `UNSAFE_ARG_CHARS`
   - **Estimated extraction complexity**: Medium - has many interdependencies with constants, logging, and validation

2. **git_ops.py** (partial extraction needed)
   - Functions: `git_status_snapshot()`, `git_current_branch()`, `git_head_sha()`
   - No extraction needed if using `run_cmd()` directly for git commands
   - **Alternative**: Inline git operations as simple `run_cmd(["git", ...])` calls

3. **tracker_generator.py** (partial extraction needed)
   - `compute_prd_hash()` - simple hashlib operations (lines 295-298)
   - `get_tracker_path()` - path construction (lines 301-303)
   - `load_tracker()` - JSON loading with size validation (lines 306-332)
   - `validate_tracker()` - uses optional jsonschema library (lines 580-672)
   - **Estimated extraction complexity**: Low-Medium - has dependencies on agents module for LLM calls (not needed for support mode)

4. **tracker_validator.py** (full extraction possible)
   - Pure validation logic with no external dependencies
   - Can be copied directly
   - **Estimated extraction complexity**: Low

5. **verification_persistence.py** (full extraction possible)
   - Depends on: `git_head_sha()` from git_ops, `get_prd_hash()` from utils
   - Can replace `get_prd_hash()` with `compute_prd_hash()`
   - **Estimated extraction complexity**: Low

6. **logging_utils.py** (reuse or replace)
   - Simple logging setup
   - Can replace with standard library logging

#### External Dependencies
- **jsonschema** (optional) - for tracker validation; has fallback to basic validation
- **No LLM/agent dependencies needed** - support mode is read-only monitoring

### Package Structure Options

#### Option 1: Python Package (Recommended)
```
support-mode/
├── pyproject.toml
├── README.md
├── src/
│   └── support_mode/
│       ├── __init__.py
│       ├── cli.py              # New CLI entry point
│       ├── support_loop.py     # Extracted from auto_prd
│       ├── git_ops.py          # Minimal git helpers
│       ├── command.py          # Minimal command execution
│       ├── tracker.py          # Tracker loading/validation
│       ├── verification.py     # Verification status checking
│       └── state.py            # State persistence
└── tests/
```

**Advantages:**
- Leverages existing Python ecosystem
- Easy to distribute via PyPI
- Can share code with auto_prd via shared internal package
- Multiple entry points: `python -m support_mode`, `support-mode` CLI

**Disadvantages:**
- Requires Python installation
- Larger package size compared to Go binary

#### Option 2: Go Binary (Optional Future Enhancement)
- Implement core logic in Go for single-binary distribution
- Read JSON state/tracker files using Go's encoding/json
- Execute git commands via os/exec
- **Advantages**: Single binary, no runtime dependencies
- **Disadvantages**: Code duplication, harder to maintain parity with Python version

### Patterns to Follow

1. **Backward Compatibility**
   - Keep all file formats identical (`.aprd/support_state.json`, `.aprd/tracker.json`)
   - Use same field names and data structures
   - Support migration if format changes in future

2. **Error Handling**
   - Gracefully handle missing tracker file (display warning, continue polling)
   - Handle malformed JSON with fallback to empty state
   - Continue on git errors (log warning, don't crash)

3. **Logging**
   - Use structured logging with levels (DEBUG, INFO, WARNING, ERROR)
   - Support `--log-level` CLI flag
   - Optional `--log-file` for debugging

4. **CLI Design**
   - Follow auto_prd's argument patterns where applicable
   - Required: `--prd` (path to PRD file)
   - Optional: `--repo` (default: git root), `--poll-seconds` (default: 120)
   - Output format: emoji prefixes (✓, ⚠️, ❌, →) for consistency

5. **State Management**
   - Atomically write state files (write to temp, then rename)
   - Handle concurrent access (file locking or retry on write conflict)
   - Preserve state on crash/keyboard interrupt

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Code duplication between auto_prd and support-mode packages | High | Extract shared code into internal package (`auto_prd_core` or `aprd_shared`) that both packages import |
| Tracker format changes in auto_prd break support-mode | Medium | Version the tracker format; support reading multiple versions; add format migration logic |
| Breaking changes to .aprd directory structure | Medium | Document .aprd structure as stable API; use semantic versioning; announce changes in advance |
| Dependency version conflicts (auto_prd installed alongside support-mode) | Low | Use namespace packages or shared dependencies; minimal external dependencies reduces conflict surface |
| Git operations fail in non-git directories | Low | Validate git repository on startup; provide clear error message; exit gracefully |
| Performance issues with large tracker files | Medium | Already handled by `load_tracker()` size check (1MB max); implement streaming JSON parsing if needed |
| State file corruption from concurrent writes | Medium | Use file locking (fcntl.lockf on Unix, msvcrt.locking on Windows); retry on write failure; write to temp file then atomic rename |

## Recommended Approach

### Phase 1: Extract and Isolate (Week 1)
1. **Create standalone Python package skeleton**
   - Set up `pyproject.toml` with `support-mode` package name
   - Configure entry point: `support-mode = "support_mode.cli:main"`
   - Add `python -m support_mode` alternative entry point

2. **Extract minimal dependencies**
   - Copy `support_loop.py` and remove auto_prd imports
   - Extract `run_cmd()` and `CommandResult` from `command.py` (simplify - remove agent-specific features)
   - Copy tracker validation functions from `tracker_generator.py` and `tracker_validator.py`
   - Copy `VerificationPersistence` from `verification_persistence.py`
   - Create minimal `git_ops.py` with just the 3 needed functions

3. **Create new CLI**
   - `cli.py` with argparse setup similar to auto_prd's CLI
   - Arguments: `--prd` (required), `--repo` (optional), `--poll-seconds` (default: 120)
   - Remove auto_prd-specific flags (phases, Ralph mode, etc.)
   - Add `--version` flag

4. **Testing**
   - Test with existing `.aprd` directory from auto_prd project
   - Verify state file read/write compatibility
   - Test graceful shutdown (Ctrl+C)

### Phase 2: Package and Distribute (Week 2)
1. **PyPI publishing**
   - Register package on PyPI as `support-mode`
   - Configure CI/CD for automatic publishing on git tags
   - Add documentation (README.md, installation instructions)

2. **Installation options**
   - `pip install support-mode` (from PyPI)
   - `pip install -e .` (for development)
   - Document `python -m support_mode` alternative

3. **Validation**
   - Test installation in clean virtual environment
   - Verify it works without auto_prd installed
   - Test with Cursor, Windsurf, Claude Code workflows

### Phase 3: Optional Go Binary (Future)
1. **Port core logic to Go**
   - Implement state persistence, tracker loading, git operations
   - Use encoding/json for file parsing
   - Use os/exec for git command execution

2. **Build and distribution**
   - Compile for multiple platforms (linux, macos, windows)
   - Distribute via GitHub releases
   - Add installation script for convenience

3. **Maintenance**
   - Keep feature parity with Python version
   - Share test suite between implementations
   - Document any differences in behavior

## Open Questions

1. **Shared Code Strategy**: Should we create a shared internal package (`aprd_core`) that both auto_prd and support-mode import from, or duplicate the minimal code needed? This impacts maintenance burden vs. package complexity.

2. **Verification Persistence**: Support mode checks verification run status, but doesn't create verification runs. Should the standalone tool also support running verifiers, or remain read-only monitoring?

3. **Guardrails Integration**: Guardrails are loaded from `~/.config/aprd/guardrails/<repo_slug>.md`. Should support mode continue to display guardrail count, or is this auto_prd-specific? (Likely keep it - provides useful context)

4. **PRD Path Resolution**: auto_prd has complex PRD path resolution with security checks. Should support mode use the same validation, or simplify since it's read-only? (Recommend: keep security checks for consistency)

5. **Configuration File**: Should support mode support a configuration file (e.g., `.supportrc` or `~/.config/support-mode/config.toml`) for default values like poll interval, or rely only on CLI flags? (Recommend: start with CLI-only, add config file if requested)

6. **Dependency Version Compatibility**: If auto_prd adds new fields to tracker.json in v2.1.0, should support-mode v1.0.0 be able to read it? (Recommend: use forward-compatible JSON parsing - ignore unknown fields, validate required fields only)

7. **Cross-Platform File Locking**: What file locking mechanism should we use for concurrent write protection? (Recommend: use `filelock` library which handles platform differences, or implement simple retry logic without locking)

8. **Licensing**: The standalone tool should use the same MIT license as auto_prd, but should it be a separate repository or part of the auto_prd monorepo? (Recommend: separate repository for clearer separation of concerns)
