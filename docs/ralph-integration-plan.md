# Ralph-Style Integration Plan for Autodev

**Date:** 2026-01-12
**Status:** MVP Implemented (High-Priority phases complete)
**Last Updated:** 2026-01-12
**Author:** Analysis of Ryan Carson's Ralph technique applied to autodev architecture

## Implementation Status Summary

| Phase | Status | Files Added | Integration Points |
|-------|--------|-------------|-------------------|
| **Phase 1: Guardrails** | ✅ Complete | `tools/auto_prd/guardrails.py` | `local_loop.py`, `review_loop.py` |
| **Phase 3: Progress Logging** | ✅ Complete | `tools/auto_prd/progress_renderer.py` | `local_loop.py` |
| **Phase 4: Gutter Detection** | ✅ Complete | Used existing `context.StallDetector` | `local_loop.py`, `review_loop.py` |
| **Config Flags** | ✅ Complete | `internal/config/config.go` (Ralph struct) | TUI-ready |
| **Phase 2: Pattern Discovery** | ⏸️ Pending | `tools/auto_prd/patterns.py` | Not started |
| **Phase 5: Context Rotation** | ⏸️ Pending | Reuse `context.compact_context` | Not started |
| **Phase 6: Task Selection** | ⏸️ Pending | `tools/auto_prd/task_selector.py` | Not started |
| **Phase 7: Idempotency** | ⏸️ Pending | `tools/auto_prd/idempotent.py` | Not started |

### Key Metrics

- **Tests Added:** 43 Python tests (22 guardrails + 21 progress renderer)
- **New Storage Paths:**
  - `~/.config/aprd/guardrails/<repo_slug>.md` - Signs from mistakes
  - `~/.config/aprd/progress/<session_id>.jsonl` - Iteration history
- **Lines of Code:** ~900 new Python lines, ~100 new Go config lines

## Executive Summary

This document outlines how to integrate Ralph-style autonomous iteration concepts into autodev using existing components and storing new state under `~/.config/aprd`. The core Ralph insight is **context hygiene**: treating AI context as volatile and state as externalized. Autodev already has strong building blocks (checkpointing, tracker.json, structured error logging, journals, and context compaction). The plan below repurposes those components instead of introducing parallel systems.

Key principle for storage: repo artifacts only where they are part of the contract (for example, `.aprd/tracker.json`). All other session and learning state lives in `~/.config/aprd` (XDG config).

## Key Ralph Concepts

1. **Fresh Context Per Iteration** - Each iteration starts with a clean context window
2. **Externalized State** - Progress in files (git, JSON), not in chat memory
3. **Guardrails/Signs** - Past mistakes are recorded to prevent recurrence
4. **Small Stories** - Tasks fit in one context window
5. **Fast Feedback** - Tests run after each change
6. **Pattern Accumulation** - Learnings compound across iterations

## Current Autodev vs Ralph Comparison

| Feature | Autodev Current | Ralph Approach | Status |
|---------|-----------------|----------------|--------|
| State Persistence | Checkpoint JSON + `.aprd/tracker.json` + SessionMemory | progress log + guardrails in `~/.config/aprd` | ✅ Implemented |
| Context Management | Fresh prompts per iteration; review loop compaction | Fresh each iteration + compaction everywhere | ⏸️ Partial (local loop needs compaction) |
| Learning Storage | Root `AGENTS.md`, structured errors, journal | guardrails + patterns | ✅ Guardrails implemented |
| Mistake Prevention | Retry logic + StallDetector (not wired) | Signs/Guardrails | ✅ Implemented |
| Progress Tracking | SessionProgress + journal + TASKS_LEFT | Structured log + UI | ✅ Implemented |
| Gutter Detection | empty_change_streak + StallDetector (not wired) | Repeated failure detection | ✅ Implemented |
| Idempotency | Retry wrappers in git ops | Idempotent helpers | ⏸️ Partial |

---

## Phase 1: Guardrails and Signs System

### 1.1 Purpose

Record mistakes as "signs" so they never happen twice. When something breaks, add a sign. Next iteration reads signs first.

### 1.2 File Structure

```text
~/.config/aprd/
├── sessions/                    # Existing: checkpoint JSON (per session)
├── journals/                    # Existing: journal JSONL (per session)
├── errors/                      # Existing: structured error log JSONL (per session)
├── guardrails/                  # NEW: signs/guardrails per repo
│   └── <repo_slug>.md
├── patterns/                    # OPTIONAL: extracted patterns per repo
│   └── <repo_slug>.md
└── progress/                    # OPTIONAL: derived progress summaries (per session)
    └── <session_id>.jsonl

.aprd/tracker.json               # Existing repo artifact used by TUI
```

### 1.3 Guardrails Format

```markdown
# Guardrails - Signs from Past Iterations

## sign: check imports before adding
- **Trigger**: Adding a new import statement
- **Instruction**: Check if import already exists
- **Added**: Iteration 3 (duplicate import broke build)
- **File**: src/utils/helpers.ts

## sign: use IF NOT EXISTS for migrations
- **Trigger**: Creating database migrations
- **Instruction**: Always use `IF NOT EXISTS` for idempotency
- **Added**: Iteration 5 (migration failed on re-run)

## sign: update both schema and resolver
- **Trigger**: Modifying GraphQL schema
- **Instruction**: When changing type in schema, update resolver return type
- **Added**: Iteration 7 (type mismatch caused runtime error)
```

### 1.4 Implementation: New Module `guardrails.py`

```python
# tools/auto_prd/guardrails.py

from pathlib import Path
from datetime import datetime
from typing import NamedTuple

class Sign(NamedTuple):
    """A sign represents a learned pattern from a mistake."""
    name: str
    trigger: str
    instruction: str
    added_iteration: int
    file_context: str | None = None
    added_at: str = ""  # ISO timestamp

# Example: Get guardrails path for a repository
# repo_slug would be derived from git remote or directory name
# e.g., "owner_repo" for https://github.com/owner/repo
GUARDRAILS_PATH = Path.home() / ".config" / "aprd" / "guardrails" / f"{repo_slug}.md"

def add_sign(
    name: str,
    trigger: str,
    instruction: str,
    iteration: int,
    file_context: str | None = None,
    repo_root: Path,
) -> None:
    """Add a new sign to guardrails after detecting a mistake pattern."""

def get_signs(repo_root: Path) -> list[Sign]:
    """Load all signs for injection into agent context."""

def format_signs_for_prompt(signs: list[Sign]) -> str:
    """Format signs as structured text for agent system prompt."""
```

### 1.5 Integration Points (Reuse Existing Components)

1. **After fix pass failure** - Leverage `errors.py` (StructuredError + ErrorLog) as the source of truth; convert repeated error patterns into guardrails.
2. **Before implementation pass** - Inject guardrails via `system_prompt_suffix` (Claude) and scrub text via `utils.scrub_cli_text` to satisfy CLI safety.
3. **Persistence** - Store guardrails under `~/.config/aprd/guardrails/<repo_slug>.md`.

---

## Phase 2: Pattern Discovery and AGENTS.md

### 2.1 Purpose

Automatically document codebase patterns discovered during implementation. These persist as `AGENTS.md` files in relevant directories.

### 2.2 Pattern Categories

1. **Structural Patterns** - How code is organized
2. **Gotchas** - Common pitfalls specific to codebase
3. **Dependencies** - What depends on what
4. **Conventions** - Naming, formatting, architectural rules

### 2.3 AGENTS.md Format

```markdown
# AGENTS.md - Patterns for agents working on this directory

## Codebase Patterns

### Error Handling
- All async functions use `Result<T, E>` pattern
- Never throw; return `Result.err()`

### Testing
- Test files co-located: `Component.test.ts`
- Use `describe` blocks for public API only

### Gotchas
- When modifying `UserSchema`, also update `UserValidator`
- State changes must dispatch via `store.dispatch()`

### File Relationships
- `components/Button.tsx` → `styles/button.css`
- Changing API in `routes/users.ts` requires updating `types/api.ts`
```

### 2.4 Implementation: New Module `patterns.py`

```python
# tools/auto_prd/patterns.py (or reuse tracker + git ops)

import json
from pathlib import Path
from collections import defaultdict

class PatternExtractor:
    """Extract patterns from codebase changes."""

    def extract_from_changes(self, changed_files: list[Path]) -> dict:
        """Analyze changed files to identify patterns."""

    def detect_dependencies(self, file_path: Path) -> list[Path]:
        """Find what this file depends on."""

    def suggest_gotchas(self, file_path: Path) -> list[str]:
        """Suggest potential gotchas based on file type and content."""

class PatternStore:
    """Manage AGENTS.md files."""

    def update_agents_md(self, directory: Path, patterns: dict) -> None:
        """Append discovered patterns to AGENTS.md."""
```

### 2.5 Integration

1. **After each implementation pass** - Extract patterns from changed files (use `git_status_snapshot` and tracker data).
2. **Before next pass** - Read `AGENTS.md` from relevant directories (root already exists).
3. **Persistence** - Update `AGENTS.md` in-repo; optional mirror under `~/.config/aprd/patterns/<repo_slug>.md`.
4. **Injection** - Add patterns to prompt with `scrub_cli_text` before `system_prompt_suffix`.

---

## Phase 3: Enhanced Progress Tracking

### 3.1 Current Issues

- `TASKS_LEFT=` parsing is fragile
- Progress metrics exist but are not persisted or surfaced consistently
- No unified "iteration history" view for TUI/CLI

### 3.2 New: progress.txt

```text
# Ralph Progress Log - Session prd-auth-feature-20250112
Started: 2025-01-12T10:00:00Z

## Codebase Patterns (Discovered)
- Migrations: Use IF NOT EXISTS for idempotency
- TypeScript: Export types from dedicated types/ files
- Tests: Co-locate with source, use .test.ts suffix

## Iteration History

### Iteration 1 - 2025-01-12T10:05:00Z
**Status:** Completed
**Changes:** Added User model, migration, basic CRUD
**Files Changed:**
- src/models/User.ts (new)
- prisma/migrations/20250112_init.sql (new)
**Learnings:**
- Discovered: Uses Prisma ORM, not raw SQL
- Pattern: All models inherit from BaseModel
**Tasks Completed:** T001, T002
**Tasks Remaining:** 8

### Iteration 2 - 2025-01-12T10:25:00Z
**Status:** Completed with warnings
**Changes:** Added authentication endpoints
**Files Changed:**
- src/routes/auth.ts (new)
- src/middleware/auth.ts (new)
**Issues Found:**
- Type mismatch: User.id is string, not number (guardrail added)
- Missing error handling on password validation
**Learnings:**
- Gotcha: User.id type is string (UUID), not int
**Tasks Completed:** T003, T004
**Tasks Remaining:** 6
```

### 3.3 Implementation

```python
# REUSE: tools/auto_prd/journal.py + tools/auto_prd/progress.py

from pathlib import Path
from datetime import datetime, timezone
from typing import TypedDict

class IterationSummary(TypedDict):
    iteration: int
    timestamp: str
    status: str
    files_changed: list[str]
    learnings: list[str]
    issues_found: list[str]
    tasks_completed: list[str]
    tasks_remaining: int

def append_iteration(
    repo_root: Path,
    summary: IterationSummary,
    session_id: str,
) -> None:
    """Append iteration summary to progress.txt."""

def get_progress_history(repo_root: Path) -> list[IterationSummary]:
    """Load progress history for context injection."""

def format_progress_for_prompt(history: list[IterationSummary]) -> str:
    """Format recent history for agent context."""
```

**Reuse plan:**
- Use `Journal` (JSONL) as the canonical progress log.
- Add an optional renderer that converts journal entries into a human-friendly "progress.txt" view for TUI/CLI.

---

## Phase 4: Gutter Detection and Smart Stopping

### 4.1 Purpose

Detect when the agent is "in the gutter" - repeating the same failure without making progress.

### 4.2 Detection Strategies

1. **Repeated Command Failure** - Same command fails N times
2. **File Thrashing** - Same file edited repeatedly without commit
3. **Context Rotation** - Rotate agent when approaching context limits
4. **Stagnation Detection** - No progress after M iterations

### 4.3 Implementation

```python
# REUSE: tools/auto_prd/context.py StallDetector

from collections import deque
from typing import NamedTuple

class CommandAttempt(NamedTuple):
    command: str
    exit_code: int | None
    timestamp: float

class GutterDetector:
    """Detect when agent is stuck repeating failures."""

    def __init__(self, window: int = 10):
        self.command_history: deque[CommandAttempt] = deque(maxlen=window)
        self.file_edit_history: dict[str, int] = {}
        self.consecutive_failures = 0

    def record_command(self, command: str, exit_code: int | None) -> None:
        """Record a command execution attempt."""

    def record_file_edit(self, file_path: str) -> None:
        """Record a file being edited."""

    def check_gutter_state(self) -> tuple[bool, str]:
        """Check if we're in a gutter state.

        Returns: (is_gutter, reason)
        """

    def get_recovery_suggestion(self) -> str:
        """Suggest recovery action based on gutter type."""
```

### 4.4 Gutter Types and Recovery

| Gutter Type | Detection | Recovery |
|-------------|-----------|----------|
| Repeated command | Same cmd fails 3x | Add sign, skip to next task |
| File thrashing | Same file edited 5x without commit | Add sign, force commit |
| Context approaching limit | Token count > 80% | Rotate session |
| No progress | No new commits after 3 iters | Add sign, switch model |
| Test loop | Same test fails repeatedly | Add sign, skip test |

---

## Phase 5: Fresh Context Rotation

### 5.1 Current Problem

Autodev already uses fresh prompts per iteration (no `--resume`), but
context compaction is only wired in the review loop:
- Failed attempts stay in memory
- Agent re-reads its own previous outputs
- No way to "forget" bad approaches

### 5.2 Ralph Approach: Deliberate Rotation

Instead of one long session, use multiple fresh sessions:

```python
# Existing: Continuous session
for i in range(max_iters):
    output = agent(prompt, resume=True)  # Carries all previous context

# Ralph: Fresh sessions
for i in range(max_iters):
    # Load state from files, not from session
    state = load_state_from_files()
    prompt = build_prompt_with_state(state)
    output = agent(prompt, resume=False)  # Fresh context each time
```

### 5.3 Implementation Strategy

1. **State Compression** - Between iterations, compress to structured formats
2. **Context Injection** - Re-inject only essential context next iteration
3. **Rotation Triggers**:
   - Every N iterations (configurable, default 5)
   - When approaching token limit (80%)
   - After gutter detection

### 5.4 Module: `context_manager.py`

```python
# REUSE: tools/auto_prd/context.py (build_phase_context + compact_context)

class ContextManager:
    """Manage agent context with Ralph-style rotation."""

    def __init__(
        self,
        rotation_interval: int = 5,
        token_limit: int = 150_000,
    ):
        self.rotation_interval = rotation_interval
        self.iteration_count = 0

    def should_rotate(self, token_estimate: int) -> bool:
        """Decide if context should rotate this iteration."""

    def build_fresh_prompt(
        self,
        prd_path: Path,
        tracker: dict,
        guardrails: list[Sign],
        patterns: dict,
        recent_progress: list[IterationSummary],
    ) -> str:
        """Build a fresh prompt with externalized state."""

    def compress_and_save(self, iteration_output: str) -> None:
        """Compress iteration output to persistent storage."""
```

---

## Phase 6: Enhanced Task Selection

### 6.1 Current: Linear Processing

Tasks processed in order defined in PRD/tracker. No adaptation based on difficulty or past failures.

### 6.2 Ralph: Adaptive Task Selection

1. **Small tasks first** - Build momentum
2. **Blocked tasks get deprioritized** - Come back later
3. **Failed tasks get signs** - Don't retry same way

### 6.3 Implementation

```python
# REUSE: .aprd/tracker.json as the source of truth

class TaskSelector:
    """Select next task based on Ralph heuristics."""

    def select_next_task(
        self,
        tracker: dict,
        failure_history: dict[str, int],
    ) -> tuple[dict | None, str]:
        """Select next task to implement.

        Returns: (task, reasoning)
        """

    def estimate_task_cost(self, task: dict) -> str:
        """Estimate if task fits in context window: S/M/L/XL"""

    def should_skip_task(
        self,
        task_id: str,
        failure_history: dict[str, int],
    ) -> tuple[bool, str]:
        """Check if task should be skipped due to repeated failures."""
```

---

## Phase 7: Idempotency Helpers

### 7.1 Purpose

Ensure operations can be safely re-run without side effects.

### 7.2 Idempotency Patterns

| Operation | Non-Idempotent | Idempotent |
|-----------|----------------|------------|
| SQL Add Column | `ADD COLUMN x` | `ADD COLUMN IF NOT EXISTS x` |
| File Write | `write(path, content)` | Check exists, backup first |
| Git Push | `git push` | `git push --force-with-lease` |
| Install | `npm install pkg` | `npm install pkg \|\| true` |

### 7.3 Implementation: Wrapper Functions

```python
# REUSE: tools/auto_prd/command.py + git_ops.py retry wrappers

import shutil
from pathlib import Path

def write_idempotent(path: Path, content: str) -> bool:
    """Write file only if content differs. Returns True if written."""

def mkdir_idempotent(path: Path) -> Path:
    """Create directory, return path regardless of existence."""

def sql_idempotent(statement: str) -> str:
    """Wrap SQL statement for idempotency where possible."""

def command_idempotent(cmd: str) -> str:
    """Add idempotency flags to common commands."""
    # e.g., npm install → npm install --prefer-offline --no-audit
```

---

## Implementation Priority

### High Priority (MVP)

1. **Guardrails System** (Phase 1, reusing `errors.py`)
   - Core value: mistakes don't repeat
   - Implementation: `guardrails.py` (backed by errors/journal logs)
   - Files: `~/.config/aprd/guardrails/<repo_slug>.md`

2. **Progress Logging** (Phase 3, reusing `journal.py`)
   - Core value: visibility into what's been tried
   - Implementation: render journal entries into a progress summary
   - Files: `~/.config/aprd/journals/<session_id>.jsonl`

3. **Gutter Detection** (Phase 4, reuse StallDetector)
   - Core value: detect and recover from stuck states
   - Implementation: wire `context.StallDetector` into loops

### Medium Priority

4. **Pattern Discovery** (Phase 2)
   - Value: agents learn codebase faster
   - Implementation: update `AGENTS.md` in repo; optional mirror under `~/.config/aprd/patterns/`

5. **Context Rotation** (Phase 5)
   - Value: prevent context pollution in long runs
   - Implementation: reuse `context.compact_context` in local loop

### Lower Priority

6. **Enhanced Task Selection** (Phase 6)
   - Value: smarter task ordering
   - Implementation: `task_selector.py` module

7. **Idempotency Helpers** (Phase 7)
   - Value: safer re-runs
   - Implementation: `idempotent.py` module

---

## Modified File Structure

```text
tools/auto_prd/
├── agents.py              # Existing
├── checkpoint.py          # Existing (extend with guardrails refs)
├── local_loop.py          # Existing (integrate gutter detection)
├── review_loop.py         # Existing (integrate guardrails)
├── tracker_generator.py   # Existing (integrate pattern extraction)
├── constants.py           # Existing (add new constants)
├── guardrails.py          # NEW: Signs/guardrails system (reuses errors/journal)
├── patterns.py            # NEW: Pattern discovery and AGENTS.md (optional)
└── task_selector.py       # NEW: Adaptive task selection (tracker-driven)

~/.config/aprd/            # Runtime directory (XDG)
├── sessions/              # Existing
├── journals/              # Existing
├── errors/                # Existing
├── guardrails/            # NEW: Signs from mistakes (per repo)
└── patterns/              # OPTIONAL: Discovered patterns (per repo)

.aprd/tracker.json         # Existing repo artifact
```

---

## Configuration: New CLI Flags

```bash
# Ralph mode flags
autodev --ralph-mode                    # Enable all Ralph features
autodev --context-rotate-every 5        # Rotate context every N iterations
autodev --guardrails-file ~/.config/aprd/guardrails/<repo_slug>.md
autodev --max-consecutive-failures 3    # Gutter detection threshold
autodev --auto-add-signs                # Automatically add signs on failures

# Debug visibility
autodev --show-progress-log             # Print progress summary at end
autodev --show-guardrails               # Show active guardrails
autodev --dry-run-add-signs             # Preview what signs would be added
```

Note: new flags must be wired through `internal/config` and surfaced in the TUI Env tab.

---

## Migration Path

### Step 1: Add Guardrails (Week 1)
- Implement `guardrails.py` (backed by errors/journal logs in `~/.config/aprd`)
- Add guardrails loading to prompt construction (scrubbed for CLI safety)
- Add guardrail suggestions after fix pass failures (reuse StructuredError)
- Test with a simple PRD

### Step 2: Add Progress Logging (Week 1-2)
- Reuse `journal.py` + optional progress renderer
- Integrate in `local_loop.py` and `review_loop.py`
- Add progress summary to TUI Logs tab

### Step 3: Add Gutter Detection (Week 2)
- Wire `context.StallDetector` into loops
- Add detection to `local_loop.py` and `review_loop.py`
- Implement recovery strategies

### Step 4: Add Pattern Discovery (Week 3)
- Implement `patterns.py`
- Add AGENTS.md generation
- Integrate pattern injection

### Step 5: Add Context Rotation (Week 3-4)
- Implement `context_manager.py`
- Add rotation logic to loops
- Test with large PRDs

### Step 6: Add Enhanced Task Selection (Week 4)
- Implement `task_selector.py`
- Integrate with `local_loop.py`

### Step 7: Add Idempotency Helpers (Week 4)
- Implement `idempotent.py`
- Add wrappers to common operations

---

## Success Metrics

1. **Reduced Iteration Waste** - Fewer repeated mistakes
2. **Better Long-Running Sessions** - Can complete larger PRDs without degradation
3. **Visibility** - Progress.txt shows clear history of what was tried
4. **Recovery** - Gutter detection prevents infinite loops
5. **Learning** - Guardrails grow with each session, making future runs faster

---

## Open Questions

1. **Sign Expiration** - Should signs expire after N successful iterations without issues?
2. **Pattern Conflict** - What if discovered patterns contradict?
3. **Multi-Repo Signs** - Should guardrails be per-repo or global?
4. **Sign Attribution** - How to attribute which iteration added which sign?
5. **TUI Integration** - How to show guardrails/signs in the TUI?

---

## References

- [Ryan Carson's Ralph Guide](https://twitter.com/ryancarson/status/1876616489234895314)
- [Ralph for Idiots](https://twitter.com/agrimsingh/status/1876815076699095377)
- Original autodev: `tools/auto_prd/`
- Storage decision: `~/.config/aprd` (XDG) for guardrails/progress/errors
