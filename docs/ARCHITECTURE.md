# AutoDev Architecture

This document describes the architecture of the AutoDev system, a PRD-to-PR automation pipeline with a TUI frontend.

## System Overview

AutoDev consists of three main components:

1. **Go TUI Frontend** (`cmd/aprd/`) - Interactive terminal interface for configuration and execution
2. **Python Agent Harness** (`tools/auto_prd/`) - Backend automation pipeline
3. **Ralph Mode** (`tools/auto_prd/guardrails.py`, `tools/auto_prd/progress_renderer.py`) - Autonomous iteration features

```text
┌─────────────────────────────────────────────────────────────────┐
│                         Go TUI (aprd)                           │
│  ┌──────────┬──────────┬──────────┬──────────┬────────────────┐ │
│  │   Run    │   PRD    │ Settings │   Env    │  Logs / Help   │ │
│  └──────────┴──────────┴──────────┴──────────┴────────────────┘ │
│                              │                                   │
│                    subprocess execution                          │
│                              ▼                                   │
├─────────────────────────────────────────────────────────────────┤
│                    Python Agent Harness                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │  Tracker    │  │ Initializer │  │   Worker    │              │
│  │  Generator  │  │             │  │             │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │  Startup    │  │Verification │  │  Rollback   │              │
│  │  Protocol   │  │  Protocol   │  │   System    │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │              Ralph Mode (Autonomous Iteration)            │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │  │
│  │  │ Guardrails  │  │  Progress   │  │   Gutter    │      │  │
│  │  │   (Signs)   │  │  Tracking   │  │  Detection  │      │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘      │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                    agent execution
                              ▼
        ┌─────────────────────────────────────────┐
        │            External Agents              │
        │  ┌─────────┐          ┌─────────┐      │
        │  │  Codex  │          │ Claude  │      │
        │  │  CLI    │          │  CLI    │      │
        │  └─────────┘          └─────────┘      │
        └─────────────────────────────────────────┘
```

## Go TUI Architecture

### Package Structure

```text
internal/
├── config/          # Configuration management
│   └── config.go    # YAML config with versioning & migration
├── tui/             # Terminal UI components
│   ├── model.go     # Main Bubble Tea model
│   ├── update.go    # Update logic (message handling)
│   ├── view.go      # Main view dispatcher
│   ├── view_*.go    # Tab-specific views
│   ├── keys.go      # Action-based key mapping
│   ├── keys_*.go    # Tab-specific key handlers
│   ├── components.go# Reusable UI components
│   └── styles.go    # Lipgloss styling
├── runner/          # Process execution
│   └── runner.go    # Python subprocess management
└── api/             # Optional REST API server
    ├── server.go    # HTTP server lifecycle and configuration
    ├── router.go    # Chi router with middleware and endpoints
    └── server_test.go# Server lifecycle tests
```

### Key Design Patterns

#### 1. Action-Based Key Mapping

Instead of hardcoding key bindings, the TUI uses semantic actions:

```go
// Actions represent user intentions, not keys
type Action int

const (
    ActNavigateUp Action = iota
    ActNavigateDown
    ActConfirm
    ActCancel
    // ...
)

// Keys are mapped to actions per-tab
func (k *Keymap) TabActions(tabID string, msg tea.KeyMsg) []Action
```

This enables:
- Multiple keys triggering the same action
- Tab-specific key behaviors
- Easy key rebinding
- Typing guard protection

#### 2. Tab-Based View/Key Separation

Each tab has dedicated files:
- `view_run.go` / `keys_run.go` - Run tab
- `view_prd.go` / `keys_prd.go` - PRD selection tab
- `view_settings.go` / `keys_settings.go` - Settings tab

This keeps files focused and testable.

#### 3. Configuration System

```go
type Config struct {
    Version        string  // Schema version for migrations
    ExecutorPolicy string  // codex-first, codex-only, claude-only
    Flags          Flags   // Runtime flags
    Timings        Timings // Timeouts and intervals
    PhaseExecutors PhaseExec // Per-phase executor overrides
    // ...
}
```

Features:
- YAML persistence to `~/.config/aprd/config.yaml`
- Schema versioning with migration support
- `LoadWithWarnings()` for graceful degradation
- `SaveWithTimeout()` for filesystem protection
- Inter-field validation

## Python Agent Harness

### Module Structure

```text
tools/auto_prd/
├── __init__.py
├── cli.py              # Main CLI entry point
├── tracker_generator.py # PRD to JSON tracker conversion
├── tracker_schema.json  # JSON Schema for tracker validation
├── initializer.py      # Session initialization
├── worker.py           # Main execution loop
├── startup.py          # Session startup protocol
├── verification.py     # Feature verification protocol
├── rollback.py         # Git-based rollback system
├── checkpoint.py       # Session checkpointing
├── agents.py           # Codex/Claude agent wrappers
├── git_ops.py          # Git operations
├── command.py          # Subprocess execution
└── logging_utils.py    # Structured logging
```

### Core Protocols

#### 1. Tracker Generator

Converts PRD markdown into structured JSON tracker:

```text
PRD.md → [Claude/Codex Analysis] → tracker.json
```

The tracker serves as the contract between all agent invocations, containing:
- Feature list with priorities and dependencies
- Task breakdowns
- Acceptance criteria
- Testing requirements
- Validation benchmarks

See [TRACKER_SCHEMA.md](./TRACKER_SCHEMA.md) for details.

#### 2. Session Startup Protocol

Every session begins with verification:

```python
class SessionStartup:
    STEPS = [
        "verify_working_directory",
        "review_git_history",
        "load_tracker",
        "check_environment_health",
        "run_baseline_tests",
        "select_next_feature",
    ]
```

#### 3. Verification Protocol

Features are not marked complete without verification:

```python
class VerificationProtocol:
    def verify_feature(self, feature, tracker):
        # 1. Run unit tests
        # 2. Run integration tests
        # 3. Run e2e tests (if defined)
        # 4. Check quality gates
        # 5. Collect evidence
        return VerificationResult(...)
```

#### 4. Rollback System

Git-based feature rollback:

```python
def rollback_feature(tracker, feature_id, repo_root):
    # 1. Get commits for feature from tracker
    # 2. Verify commits in history
    # 3. Revert commits in reverse order
    # 4. Create rollback commit
    # 5. Update tracker status
    return RollbackResult(...)
```

## Ralph Mode Architecture

Ralph mode provides autonomous iteration capabilities through three core components:

### Components

**Guardrails System** (`tools/auto_prd/guardrails.py`)
- Signs pattern for mistake prevention
- Per-repository storage in `~/.config/aprd/guardrails/`
- Injection into agent context via system prompt suffix
- Auto-suggestion from error patterns

**Progress Tracking** (`tools/auto_prd/progress_renderer.py`)
- Iteration summaries with learnings, issues, tasks
- JSONL storage in `~/.config/aprd/progress/`
- Human-readable progress.txt rendering

**Gutter Detection** (integrated in `tools/auto_prd/local_loop.py`)
- StallDetector integration for stuck iterations
- Configurable thresholds (time and iteration-based)
- Auto-add guardrails on stall detection

### Integration Points

**Configuration:**
- Go struct: `internal/config/config.go:89-107` (Ralph config with 8 fields)
- TUI integration: `internal/tui/view_settings.go:92-118` (Settings group)
- Python helpers: `tools/auto_prd/ralph.py` (RalphSettings dataclass with defaults)

**Loop Integration:**
- Local loop: `tools/auto_prd/local_loop.py:163-645` (loads guardrails, injects context, tracks progress, detects stalls)
- Review loop: `tools/auto_prd/review_loop.py` (similar Ralph integration)

**App Entry Point:**
- Main orchestration: `tools/auto_prd/app.py:122-126,163-169,613-621` (shows guardrails, displays progress)

### Storage

- **Guardrails:** `~/.config/aprd/guardrails/<repo_slug>.md` (Markdown with sign metadata)
- **Progress:** `~/.config/aprd/progress/<session_id>.jsonl` (JSONL with iteration summaries)
- **Config:** `~/.config/aprd/config.yaml` (YAML with Ralph section)

See [Ralph Mode documentation](ralph-mode.md) for user-facing guide and [Ralph Integration Plan](ralph-integration-plan.md) for implementation details.

## HTTP API Server

The API server provides an optional REST interface for external control and monitoring.
It is built with the [chi v5](https://github.com/go-chi/chi) router and includes:

- **Middleware Stack**: RequestID, RealIP, Logger, Recoverer
- **Graceful Shutdown**: SIGINT/SIGTERM handling with 5-second timeout
- **Configuration**: Bind address, read/write/idle timeouts
- **Extensibility**: Dependencies struct for future dependency injection

**Current Endpoints:**
- `GET /healthz` - Health check returning `{"status": "ok"}`

See [API.md](./API.md) for complete API documentation including:
- Endpoints reference with request/response examples
- Configuration options and environment variables
- Integration examples in Go, curl, and Python
- Development guide for adding new endpoints

**Architecture:**
```text
┌─────────────────────────────────────┐
│         cmd/api/main.go             │
│    (Server binary entry point)      │
│  - Signal handling (SIGINT/SIGTERM) │
│  - Graceful shutdown (5s timeout)   │
│  - Environment variable config      │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│     internal/api/server.go          │
│  (Server lifecycle & Config)        │
│  - Server construction              │
│  - Start/StartListener methods      │
│  - Shutdown with context            │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│     internal/api/router.go          │
│  (Chi router + middleware)          │
│                                     │
│  ┌────────────────────────────────┐ │
│  │ Middleware Stack:              │ │
│  │ - RequestID (X-Request-ID)     │ │
│  │ - RealIP (X-Forwarded-For)     │ │
│  │ - Logger (stdout logging)      │ │
│  │ - Recoverer (panic recovery)   │ │
│  └────────────────────────────────┘ │
│                                     │
│  ┌────────────────────────────────┐ │
│  │ Endpoints:                     │ │
│  │ GET /healthz                   │ │
│  └────────────────────────────────┘ │
└─────────────────────────────────────┘
```

**Key Design Decisions:**
- **Chi Router**: Lightweight, idiomatic Go HTTP router with composable middleware
- **Middleware-first**: Cross-cutting concerns (logging, recovery, request ID) handled at router level
- **Empty Dependencies**: Struct designed for future DI (runner control, config access, log streaming)
- **No Authentication**: Currently open, may add auth middleware in future releases
- **Graceful Shutdown**: 5-second timeout for active request completion on SIGINT/SIGTERM

## Data Flow

### Run Execution Flow

```text
1. User selects PRD in TUI
2. User configures settings (phases, executors)
3. User triggers "Run"
4. TUI spawns Python subprocess
5. Python loads/creates tracker
6. For each feature:
   a. Run startup protocol
   b. Execute feature tasks via agents
   c. Run verification protocol
   d. Update tracker status
7. TUI displays live logs
8. On completion/error, show summary
```

### Configuration Flow

```text
~/.config/aprd/config.yaml
        │
        ▼
┌───────────────────┐
│ Load with version │
│    migration      │
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ Apply defaults    │
│ for nil fields    │
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ Validate inter-   │
│ field constraints │
└───────────────────┘
        │
        ▼
┌───────────────────┐
│  TUI model.cfg    │
└───────────────────┘
```

## Security Considerations

1. **Command Injection Prevention**
   - All subprocess args are validated
   - No shell=True execution
   - Path traversal checks

2. **Secret Protection**
   - Config file permissions: 0600
   - No secrets in config
   - Environment variables for API keys

3. **Input Validation**
   - Branch name validation (git refname rules)
   - PRD path validation
   - Executor choice validation

## Testing Strategy

1. **Go Tests** (`internal/*_test.go`)
   - Unit tests for config, TUI logic
   - Integration tests for runner
   - Race detector enabled in CI

2. **Python Tests** (`tools/auto_prd/tests/`)
   - Unit tests for tracker operations
   - Integration tests for agent execution
   - Stress tests for log streaming

3. **CI Pipeline** (`make ci`)
   - golangci-lint for Go
   - ruff for Python
   - All tests with race detection
   - Optional mypy type checking

## Extension Points

1. **New Agents**: Add to `agents.py` with standard interface
2. **New Phases**: Extend `PhaseExec` in config
3. **New Tabs**: Add `view_*.go` and `keys_*.go`
4. **New Quality Gates**: Extend `verification.py`
