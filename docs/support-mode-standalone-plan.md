# Standalone Support Mode Implementation Plan

## Overview

**Goal**: Extract support mode from the auto_prd tool to create a standalone CLI application that can run independently in its own terminal. This will allow support mode to work with any coding/Ralph framework (Cursor, Windsurf, Claude Code, Copilot, etc.) for continuous monitoring, review, and task tracking.

## Current State Analysis

### Current Support Mode Features

Located in `tools/auto_prd/support_loop.py`, support mode currently provides:

1. **Repository State Monitoring**
   - Current Git branch and commit SHA tracking
   - Working tree status (uncommitted changes)
   - Recent commits display

2. **Tracker Validation**
   - Tracker file structure validation
   - Feature and task counting
   - Acceptance criteria validation
   - Dependency relationship checks
   - Blocked task detection
   - Completion timestamp verification

3. **PRD Synchronization**
   - Extracts checkbox items from PRD markdown
   - Compares PRD with tracker tasks
   - Suggests missing items

4. **Git Quality Checks**
   - Runs `git diff --check` for whitespace/style issues

5. **Verification Status**
   - Checks latest verification runs
   - Identifies failed/stale runs

6. **Guardrails Monitoring**
   - Reports guardrail signs on record

7. **State Persistence**
   - Saves state to `.aprd/support_state.json`

### Current Dependencies

| Module | Purpose | Standalone Strategy |
|--------|---------|---------------------|
| `command.run_cmd` | Subprocess execution | Extract or replace |
| `git_ops` | Git operations | Extract minimal subset |
| `tracker_generator` | Tracker loading/validation | Extract minimal subset |
| `tracker_validator` | Tracker state validation | Include in standalone |
| `verification_persistence` | Verification run tracking | Extract or stub |
| `guardrails` | Guardrail loading | Extract or stub |
| `logging_utils` | Logging | Extract or use stdlib |

---

## Proposed Standalone Architecture

### Directory Structure

```
autodev/
├── cmd/
│   └── support/
│       └── main.go              # Go entry point (optional, matches existing tooling)
│
├── tools/
│   ├── support/                 # NEW: Standalone support mode
│   │   ├── __init__.py
│   │   ├── __main__.py          # For `python -m support` execution
│   │   ├── cli.py               # Argument parsing
│   │   ├── core.py              # Main support loop logic
│   │   ├── config.py            # Configuration management
│   │   ├── output.py            # Formatted output rendering
│   │   ├── validators/
│   │   │   ├── __init__.py
│   │   │   ├── tracker.py       # Tracker validation
│   │   │   ├── git.py           # Git quality checks
│   │   │   └── prd.py           # PRD validation
│   │   ├── monitors/
│   │   │   ├── __init__.py
│   │   │   ├── git_monitor.py   # Git state monitoring
│   │   │   ├── tracker_monitor.py
│   │   │   └── verification_monitor.py
│   │   └── utils/
│   │       ├── __init__.py
│   │       ├── git_ops.py       # Minimal git operations
│   │       ├── state.py         # State persistence
│   │       └── logging.py       # Logging setup
│   │
│   └── auto_prd/                # Existing (keep for compatibility)
│       └── support_loop.py      # Deprecate in favor of standalone
│
└── pyproject.toml               # Add support CLI entry point
```

### Entry Points

1. **Python module**: `python -m support --prd ./docs/feature.md`
2. **Installed CLI**: `support-mode --prd ./docs/feature.md`
3. **Go binary** (optional): `support` binary matching `aprd` pattern

---

## Implementation Plan

### Phase 1: Core Extraction (Minimal Viable Product)

**Goal**: Create a standalone tool with core monitoring features.

#### 1.1 Create Module Structure
- [ ] Create `tools/support/` directory
- [ ] Create `__init__.py` with package metadata
- [ ] Create `__main__.py` for `python -m support` execution

#### 1.2 Extract Minimal Dependencies
- [ ] Copy `run_cmd()` from `command.py` to `utils/git_ops.py`
- [ ] Extract required git functions:
  - `git_root()`
  - `git_head_sha()`
  - `git_current_branch()`
  - `git_status_snapshot()`
- [ ] Create state persistence module with `SupportState` dataclass

#### 1.3 Core Monitoring Loop
- [ ] Port `run_support_mode()` to `core.py`
- [ ] Implement polling loop with configurable interval
- [ ] Add graceful shutdown (SIGINT/SIGTERM handling)
- [ ] State persistence between iterations

#### 1.4 Basic CLI
- [ ] Create `cli.py` with argparse:
  - `--prd` (required): Path to PRD file
  - `--repo`: Repository root (default: git root)
  - `--poll-seconds`: Polling interval (default: 60, min: 5)
  - `--once`: Run single check and exit
  - `--json`: Output JSON for machine parsing
  - `--verbose`: Enable debug output

#### 1.5 Output Formatting
- [ ] Create `output.py` with formatters:
  - `ConsoleFormatter`: Human-readable terminal output
  - `JSONFormatter`: Machine-parseable JSON output
  - Support for emojis vs plain text (detect via env)

**Deliverable**: Working standalone tool that can be run with:
```bash
python -m support --prd ./docs/feature.md --poll-seconds 30
```

---

### Phase 2: Validation Integration

**Goal**: Add comprehensive validation capabilities.

#### 2.1 Tracker Validation
- [ ] Extract `load_tracker()` and `validate_tracker()` functions
- [ ] Create standalone tracker schema validation
- [ ] Add tracker state validation:
  - Feature/task status consistency
  - Dependency verification
  - Blocked task validation
  - Timestamp completeness

#### 2.2 PRD Validation
- [ ] Implement PRD checkbox extraction
- [ ] Compare PRD checkboxes with tracker tasks
- [ ] Detect orphaned PRD items
- [ ] PRD hash drift detection

#### 2.3 Git Quality Checks
- [ ] Implement `git diff --check` integration
- [ ] Detect trailing whitespace
- [ ] Detect conflicts markers
- [ ] Commit message quality (optional)

**Deliverable**: Support mode detects and reports all validation issues.

---

### Phase 3: Extended Monitoring

**Goal**: Add optional integrations for verification and guardrails.

#### 3.1 Verification Monitoring (Optional)
- [ ] Create `VerificationMonitor` class
- [ ] Support multiple verification backends:
  - pytest results
  - Custom test runners
  - Manual verification tracking
- [ ] Detect stale verification runs
- [ ] Report failed test results

#### 3.2 Guardrails Monitoring (Optional)
- [ ] Create `GuardrailMonitor` class
- [ ] Load guardrail signs from `.aprd/guardrails.json`
- [ ] Report active guardrails
- [ - Add guardrail violation detection

#### 3.3 Framework-Agnostic Task Tracking
- [ ] Support multiple tracker formats:
  - `.aprd/tracker.json` (existing)
  - `.taskmaster/tracker.json` (Task Master)
  - `tasks.json` (simple format)
  - Custom format via `--tracker-path`

**Deliverable**: Support mode works with various coding frameworks.

---

### Phase 4: Enhanced Features

**Goal**: Make support mode a powerful companion tool.

#### 4.1 Interactive Commands
- [ ] Add keyboard shortcuts during monitoring:
  - `s`: Show summary
  - `t`: Show tracker status
  - `c`: Show recent commits
  - `q`: Quit
  - `r`: Force refresh now

#### 4.2 Notifications
- [ ] Desktop notifications on state changes
- [ ] Sound alerts on critical issues
- [ ] Webhook support for external integrations

#### 4.3 Configuration File
- [ ] Support `.support.toml` or `.support.yaml` config:
  ```yaml
  prd: ./docs/feature.md
  repo: /path/to/repo
  poll_seconds: 60
  enable_verification: true
  enable_guardrails: false
  output_format: console  # console|json|quiet
  notification:
    desktop: true
    webhook: https://...
  ```

#### 4.4 Multi-Repository Monitoring
- [ ] Support monitoring multiple repos
- [ ] Tabular output for multi-repo view
- [ ] Per-repo configuration

**Deliverable**: Production-ready companion tool.

---

### Phase 5: Distribution & Integration

**Goal**: Make it easy to install and use.

#### 5.1 PyPI Package
- [ ] Create `pyproject.toml` with proper metadata
- [ ] Add entry point: `support-mode = support.cli:main`
- [ ] Publish to PyPI

#### 5.2 Go Binary (Optional)
- [ ] Create Go wrapper in `cmd/support/`
- [ ] Embed Python or use subprocess
- [ ] Match existing `aprd` build process

#### 5.3 Documentation
- [ ] README with usage examples
- [ ] CLI help text (`--help`)
- [ ] Integration guide for various frameworks

#### 5.4 Tests
- [ ] Unit tests for all modules
- [ ] Integration tests with mock repo
- [ ] CI/CD integration

**Deliverable**: Installable tool available via pip.

---

## CLI Interface Design

### Basic Usage

```bash
# Minimal usage (auto-detect repo root)
support-mode --prd docs/feature.md

# Custom polling interval
support-mode --prd docs/feature.md --poll-seconds 30

# Single check (no loop)
support-mode --prd docs/feature.md --once

# JSON output for automation
support-mode --prd docs/feature.md --json

# Verbose mode
support-mode --prd docs/feature.md --verbose
```

### Configuration File

```bash
# Use config file
support-mode --config .support.toml

# Override config values
support-mode --config .support.toml --poll-seconds 10
```

### Example Output

```
=== Support Mode (continuous reviewer) ===
-> Polling every 60s

=== Iteration 1: Support Review ===
-> main @ abc1234
-> Recent commits:
-> abc1234 Add new feature
-> def5678 Fix bug in parser

✓ Tracker: 3 features, 12 tasks (5 completed)
✓ Guardrails: 2 sign(s) on record.

⚠️ Working tree has 3 uncommitted change(s).
⚠️ Feature F002 is in_progress but dependencies incomplete: F001.
⚠️ Task T004 completed without completed_at timestamp.

-> Suggestion: PRD checkbox items not represented in tracker: Add error handling

TASKS_LEFT=7
```

---

## Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--prd` | path | required | Path to PRD file |
| `--repo` | path | git root | Repository root |
| `--poll-seconds` | int | 60 | Polling interval |
| `--once` | flag | false | Run single check |
| `--json` | flag | false | JSON output |
| `--verbose` | flag | false | Debug output |
| `--config` | path | .support.toml | Config file |
| `--tracker-path` | path | .aprd/tracker.json | Custom tracker |
| `--no-emoji` | flag | false | Plain text output |
| `--webhook` | url | none | Notification webhook |

---

## Compatibility Matrix

| Feature | Phase | Notes |
|---------|-------|-------|
| AutoDev (auto_prd) | 1 | Full compatibility |
| Ralph Wiggum Loop | 2 | Reads same tracker/state |
| Cursor | 3 | Framework-agnostic |
| Windsurf | 3 | Framework-agnostic |
| Claude Code | 3 | Framework-agnostic |
| Copilot | 3 | Framework-agnostic |
| Task Master MCP | 3 | Optional integration |

---

## Migration Path

### For Existing Users

1. **Initial**: Support mode flag remains in `auto_prd`
   ```bash
   auto_prd --prd feature.md --support-mode
   ```

2. **Transition**: Both available, deprecation notice
   ```bash
   # Old way (deprecated)
   auto_prd --prd feature.md --support-mode

   # New way
   support-mode --prd feature.md
   ```

3. **Final**: Standalone only, flag removed
   ```bash
   support-mode --prd feature.md
   ```

### Backward Compatibility

- Keep `support_loop.py` during transition period
- Add deprecation warning directing to standalone tool
- Maintain same state file format (`.aprd/support_state.json`)
- Ensure same output format for compatibility

---

## Success Criteria

1. **Independence**: Tool runs without auto_prd installed
2. **Compatibility**: Works with existing tracker/state files
3. **Extensibility**: Easy to add new validators/monitors
4. **Usability**: Simple CLI with sensible defaults
5. **Documentation**: Clear usage examples and integration guide

---

## Open Questions

1. **Go vs Python Entry Point**: Should we create a Go binary wrapper to match `aprd`?
   - Recommendation: Start with Python, add Go later if needed

2. **Verification System**: How to handle verification without auto_prd's system?
   - Recommendation: Make it optional/pluggable

3. **Task Format**: Should we support other task tracking formats?
   - Recommendation: Yes, make it pluggable

4. **Notification Method**: Desktop notifications vs webhooks vs both?
   - Recommendation: Start with optional desktop, add webhook later

---

## Estimated Effort

| Phase | Tasks | Estimated Complexity |
|-------|-------|---------------------|
| Phase 1 | 5 | Medium |
| Phase 2 | 4 | Medium |
| Phase 3 | 3 | Low-Medium |
| Phase 4 | 4 | Medium |
| Phase 5 | 5 | Low-Medium |

**Total**: 21 tasks over 5 phases
