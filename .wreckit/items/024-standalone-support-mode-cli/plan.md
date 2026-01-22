# Standalone Support Mode CLI Implementation Plan

## Overview
Extract the support mode monitoring functionality from auto_prd into a standalone, framework-agnostic CLI tool that can work with any AI coding environment (Cursor, Windsurf, Claude Code, Copilot, etc.). The tool will continuously monitor repository state, tracker files, and PRD synchronization without requiring the full auto_prd installation.

## Current State Analysis

**What exists now:**
- Support mode is embedded in `/tools/auto_prd/support_loop.py` (459 lines)
- Entry point via `auto_prd --support-mode` flag (cli.py:92-95)
- Requires full auto_prd package with all dependencies (agents, LLM integrations, etc.)
- Dependencies: `command.run_cmd()`, `git_ops.py`, `tracker_generator.py`, `tracker_validator.py`, `verification_persistence.py`, `guardrails.py`, `logging_utils.py`

**What's missing:**
- Standalone package that can be installed independently
- Simplified CLI without auto_prd-specific flags (phases, Ralph mode, etc.)
- Ability to run without LLM/agent dependencies
- Cross-framework compatibility documentation

**Key constraints discovered:**
1. **File format compatibility**: Must maintain exact compatibility with `.aprd/support_state.json` and `.aprd/tracker.json` formats
2. **Minimal dependencies**: Core logic uses only git operations, JSON parsing, and basic validation - no LLM calls needed
3. **State persistence**: Support mode uses atomic writes to `.aprd/support_state.json` with iteration tracking
4. **Validation complexity**: `tracker_generator.py` has LLM dependencies but support mode only uses 3 simple functions: `compute_prd_hash()`, `load_tracker()`, `validate_tracker()`
5. **Safety features**: `command.run_cmd()` has extensive validation (allowlist, CWD checks, arg sanitization) that must be preserved

## Desired End State

A standalone Python package `support-mode` that:
1. Installs via `pip install support-mode` from PyPI
2. Runs without auto_prd installed
3. Reads/writes existing `.aprd/support_state.json` and `.aprd/tracker.json` files
4. Provides simple CLI: `support-mode --prd <path> [--repo <path>] [--poll-seconds <n>]`
5. Supports `python -m support_mode` invocation for development
6. Includes all monitoring features: repository state, tracker validation, PRD sync, git quality checks, verification status

**Key Discoveries:**
- Support mode is **read-only monitoring** - no LLM/agent dependencies needed
- Core logic is ~400 lines that can be extracted with minimal changes
- `command.run_cmd()` can be simplified to remove agent-specific safety checks
- `tracker_generator.py` dependencies are minimal - only 3 functions needed (lines 295-332, 580-672)
- State file format is stable and well-defined (SupportState dataclass)
- All validation functions are pure Python with no external deps except optional `jsonschema`

## What We're NOT Doing

**Explicitly out of scope:**
- Complete rewrite of auto_prd
- Breaking changes to tracker.json or support_state.json formats
- Adding new monitoring features beyond what support mode currently does
- Creating verification runs (support mode only reads verification status)
- Implementing guardrails management (only displays count)
- PRD path resolution security validation (simplified for read-only tool)
- Configuration file support (CLI flags only)
- Go binary implementation (Python-only for initial release)

**Deferred to future work:**
- Shared internal package to avoid code duplication
- Configuration file (`.supportrc`) for default values
- Auto-discovery of PRD file location
- Integration tests with Cursor/Windsurf/Claude Code

## Implementation Approach

**High-level strategy:**
1. Extract core support mode logic into new package with minimal dependencies
2. Simplify `command.run_cmd()` by removing agent-specific features
3. Copy only the needed functions from `tracker_generator.py`, `tracker_validator.py`, `verification_persistence.py`
4. Create new CLI with argparse, removing auto_prd-specific flags
5. Use same `.aprd` directory structure and file formats
6. Test backward compatibility with existing auto_prd projects

**Reasoning:**
- **Extraction over refactoring**: Faster to extract and simplify than to refactor auto_prd into shared packages
- **Acceptable duplication**: ~400 lines of core logic is acceptable to duplicate for standalone tool
- **Simplified safety**: Remove agent-specific command validation since tool is read-only monitoring only
- **PyPI distribution**: Standard Python packaging makes it easy to install alongside auto_prd

---

## Phase 1: Create Package Skeleton

### Overview
Create the Python package structure with pyproject.toml, basic CLI, and verify the tool can be installed and invoked.

### Changes Required:

#### 1. Package Structure
**Directory**: `/Users/simo/Projects/autodev/tools/support-mode/`

Create the following structure:
```
support-mode/
├── pyproject.toml
├── README.md
├── src/
│   └── support_mode/
│       ├── __init__.py
│       ├── cli.py
│       ├── support_loop.py
│       ├── git_ops.py
│       ├── command.py
│       ├── tracker.py
│       ├── verification.py
│       └── guardrails.py
└── tests/
    ├── __init__.py
    └── test_cli.py
```

#### 2. pyproject.toml
**File**: `pyproject.toml`

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "support-mode"
version = "0.1.0"
description = "Framework-agnostic continuous monitoring and review tool"
readme = "README.md"
requires-python = ">=3.10"
license = {text = "MIT"}
authors = [
    {name = "AutoDev Contributors"}
]
keywords = ["monitoring", "review", "tracker", "continuous"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
]

dependencies = [
    "jsonschema>=4.0.0",  # Optional but recommended for validation
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-cov>=4.0.0",
]

[project.scripts]
support-mode = "support_mode.cli:main"

[project.urls]
Homepage = "https://github.com/autodev/support-mode"
Repository = "https://github.com/autodev/support-mode"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
support_mode = ["*.json"]
```

#### 3. Basic CLI Skeleton
**File**: `src/support_mode/cli.py`

```python
"""CLI entry point for support-mode standalone tool."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Continuous monitoring and review tool for AI-assisted development",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--prd",
        required=True,
        type=Path,
        help="Path to PRD/task .md file",
    )
    parser.add_argument(
        "--repo",
        default=None,
        type=Path,
        help="Path to repo root (default: current git root)",
    )
    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=120,
        help="Polling interval in seconds (min: 5)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 0.1.0",
    )

    return parser

def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # Validation
    if args.poll_seconds < 5:
        print("Error: --poll-seconds must be at least 5", file=sys.stderr)
        return 1

    print(f"Support Mode CLI v0.1.0")
    print(f"PRD: {args.prd}")
    print(f"Repo: {args.repo or 'auto-detect'}")
    print(f"Poll: {args.poll_seconds}s")

    # TODO: Call support loop in next phase
    print("\n[TODO: Implement support loop in Phase 2]")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

#### 4. Empty Module Files
**Files**: `src/support_mode/__init__.py`, `src/support_mode/support_loop.py`, etc.

Create stub files with docstrings for each module.

### Success Criteria:

#### Automated Verification:
- [ ] Package builds successfully: `python -m build`
- [ ] Package installs in editable mode: `pip install -e .`
- [ ] CLI entry point registered: `support-mode --help` displays usage
- [ ] Module invocation works: `python -m support_mode --help` displays same usage
- [ ] Basic argument parsing works: `support-mode --prd test.md --poll-seconds 30`

#### Manual Verification:
- [ ] Run `support-mode --version` and verify version output
- [ ] Run `support-mode --help` and verify all arguments documented
- [ ] Test invalid arguments (e.g., `--poll-seconds 1`) and see error message
- [ ] Verify tool can be invoked without auto_prd installed

**Note**: Complete all automated verification, then pause for manual confirmation before proceeding to Phase 2.

---

## Phase 2: Extract Core Dependencies

### Overview
Extract and simplify the minimal dependencies needed from auto_prd: command execution, git operations, and tracker utilities.

### Changes Required:

#### 1. Simplified Command Execution
**File**: `src/support_mode/command.py`

Extract simplified version of `run_cmd()` from auto_prd, removing:
- Agent-specific validation (COMMAND_ALLOWLIST, SAFE_CWD_ROOTS)
- Retry logic (use simple subprocess.run)
- Complex error handling (basic CalledProcessError only)

```python
"""Simplified command execution for support-mode."""

from __future__ import annotations

import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

@dataclass
class CommandResult:
    """Result of command execution."""
    stdout: str
    stderr: str
    exit_code: int

    def is_success(self) -> bool:
        return self.exit_code == 0

    def __iter__(self):
        return iter((self.stdout, self.stderr, self.exit_code))

def run_cmd(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    capture: bool = True,
) -> CommandResult:
    """Execute a command safely.

    Simplified version for support-mode - removes agent-specific
    validation since this tool is read-only monitoring only.
    """
    # Basic safety: ensure executable exists
    exe = shutil.which(cmd[0])
    if not exe:
        raise FileNotFoundError(f"Command not found: {cmd[0]}")

    # Execute
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=capture,
        text=True,
        check=False,
    )

    cmd_result = CommandResult(
        stdout=result.stdout,
        stderr=result.stderr,
        exit_code=result.returncode,
    )

    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, cmd, result.stdout, result.stderr
        )

    return cmd_result
```

#### 2. Minimal Git Operations
**File**: `src/support_mode/git_ops.py`

Copy 3 functions needed from auto_prd/git_ops.py:

```python
"""Minimal git operations for support-mode."""

from __future__ import annotations

from pathlib import Path

from .command import run_cmd

def git_root() -> Path:
    """Find repository root directory."""
    out, _, _ = run_cmd(["git", "rev-parse", "--show-toplevel"])
    return Path(out.strip())

def git_current_branch(repo_root: Path) -> str:
    """Get current branch name."""
    result = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_root)
    return result.stdout.strip()

def git_head_sha(repo_root: Path) -> str:
    """Get HEAD commit SHA."""
    result = run_cmd(["git", "rev-parse", "HEAD"], cwd=repo_root)
    return result.stdout.strip()

def git_status_snapshot(repo_root: Path) -> tuple[str, ...]:
    """Get working tree status snapshot."""
    result = run_cmd(["git", "status", "--porcelain"], cwd=repo_root, check=False)
    return tuple(sorted(result.stdout.splitlines()))
```

#### 3. Tracker Utilities
**File**: `src/support_mode/tracker.py`

Extract needed functions from auto_prd/tracker_generator.py:

```python
"""Tracker loading and validation utilities."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

# Optional jsonschema import
try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

logger = logging.getLogger(__name__)

TRACKER_DIR = ".aprd"
TRACKER_FILE = "tracker.json"
MAX_TRACKER_SIZE = 1 * 1024 * 1024  # 1 MB

# Inline the schema (copied from tracker_schema.json, simplified)
_TRACKER_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["version", "metadata", "features", "validation_summary"],
    "properties": {
        "version": {"const": "2.0.0"},
        # ... (copy full schema from auto_prd/tracker_schema.json)
    }
}

def compute_prd_hash(prd_path: Path) -> str:
    """Compute SHA-256 hash of PRD content."""
    content = prd_path.read_bytes()
    return f"sha256:{hashlib.sha256(content).hexdigest()[:16]}"

def get_tracker_path(repo_root: Path) -> Path:
    """Get path to tracker.json."""
    return repo_root / TRACKER_DIR / TRACKER_FILE

def load_tracker(repo_root: Path) -> dict[str, Any] | None:
    """Load existing tracker if present."""
    tracker_path = get_tracker_path(repo_root)
    if not tracker_path.exists():
        return None

    try:
        file_size = tracker_path.stat().st_size
        if file_size > MAX_TRACKER_SIZE:
            logger.warning("Tracker file too large: %d bytes", file_size)
            return None
        return json.loads(tracker_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load tracker: %s", e)
        return None

def validate_tracker(tracker: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate tracker structure."""
    errors: list[str] = []

    if HAS_JSONSCHEMA:
        try:
            jsonschema.validate(instance=tracker, schema=_TRACKER_SCHEMA)
        except jsonschema.ValidationError as e:
            errors.append(f"Schema validation failed: {e.message}")
            return False, errors
    else:
        # Basic fallback validation
        for field in ["version", "metadata", "features", "validation_summary"]:
            if field not in tracker:
                errors.append(f"Missing required field: {field}")
        if errors:
            return False, errors

    # Additional validation (copy from auto_prd lines 609-672)
    # ...

    return len(errors) == 0, errors
```

#### 4. Tracker Validation
**File**: `src/support_mode/tracker_validator.py`

Copy entire file from auto_prd/tracker_validator.py (pure validation, no dependencies).

### Success Criteria:

#### Automated Verification:
- [ ] `run_cmd()` executes basic git commands: `git status`, `git rev-parse HEAD`
- [ ] Git operations return correct values for branch, SHA, status
- [ ] `load_tracker()` loads existing .aprd/tracker.json
- [ ] `validate_tracker()` passes validation for valid tracker
- [ ] `validate_tracker()` fails validation for malformed tracker
- [ ] `compute_prd_hash()` returns consistent hash for same file

#### Manual Verification:
- [ ] Create test repo with .aprd/tracker.json and verify loading
- [ ] Test with malformed tracker.json and verify error messages
- [ ] Verify PRD hash changes when file content changes

**Note**: Complete all automated verification, then pause for manual confirmation before proceeding to Phase 3.

---

## Phase 3: Extract Support Loop

### Overview
Extract the main `run_support_mode()` function from auto_prd/support_loop.py, adapting it to use the simplified dependencies.

### Changes Required:

#### 1. Support Loop Main Logic
**File**: `src/support_mode/support_loop.py`

Copy entire `run_support_mode()` function from auto_prd/support_loop.py (lines 138-458), with changes:

1. Update imports to use local modules:
```python
# Old imports from auto_prd:
# from .command import run_cmd
# from .git_ops import git_current_branch, git_head_sha, git_status_snapshot
# from .tracker_generator import compute_prd_hash, load_tracker, validate_tracker
# from .tracker_validator import validate_tracker_state

# New imports:
from .command import run_cmd
from .git_ops import git_current_branch, git_head_sha, git_status_snapshot
from .tracker import compute_prd_hash, load_tracker, validate_tracker
from .tracker_validator import validate_tracker_state
```

2. Remove logger import (use standard logging instead):
```python
import logging
logger = logging.getLogger(__name__)
```

3. Keep all logic identical - no changes to monitoring behavior

#### 2. State Persistence
**File**: `src/support_mode/state.py`

Copy state management functions from auto_prd/support_loop.py (lines 26-63):

```python
"""Support state persistence."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

@dataclass
class SupportState:
    iteration: int = 1
    last_reviewed_sha: str = ""
    last_reviewed_prd_hash: str = ""
    last_reviewed_at: str = ""

def _state_path(repo_root: Path) -> Path:
    return repo_root / ".aprd" / "support_state.json"

def load_support_state(repo_root: Path) -> SupportState:
    """Load support state from disk."""
    path = _state_path(repo_root)
    if not path.exists():
        return SupportState()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return SupportState()

    return SupportState(
        iteration=int(data.get("iteration", 1) or 1),
        last_reviewed_sha=str(data.get("last_reviewed_sha", "") or ""),
        last_reviewed_prd_hash=str(data.get("last_reviewed_prd_hash", "") or ""),
        last_reviewed_at=str(data.get("last_reviewed_at", "") or ""),
    )

def save_support_state(repo_root: Path, state: SupportState) -> None:
    """Save support state to disk."""
    path = _state_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(state)
    path.write_text(json.dumps(payload, indent=2))
```

#### 3. Verification Persistence
**File**: `src/support_mode/verification.py`

Extract from auto_prd/verification_persistence.py, removing dependency on `utils.get_prd_hash()`:

```python
"""Verification status checking for support-mode."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .git_ops import git_head_sha
from .tracker import compute_prd_hash  # Use our own function

class VerificationStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    STALE = "stale"

@dataclass
class VerificationRun:
    # ... (copy from auto_prd)

class VerificationPersistence:
    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)
        self.runs_dir = self.repo_root / ".aprd" / "verification"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.runs_log = self.runs_dir / "runs.jsonl"

    def get_latest_run(self) -> VerificationRun | None:
        # ... (copy from auto_prd lines 190-204)

    def is_run_fresh(
        self,
        run: VerificationRun,
        current_prd_hash: str
    ) -> bool:
        # ... (copy from auto_prd lines 232-252)
        # Replace get_prd_hash() with current_prd_hash parameter
```

#### 4. Guardrails (Optional)
**File**: `src/support_mode/guardrails.py`

Copy minimal version from auto_prd/guardrails.py - only need `load_guardrails()` and `Sign` dataclass.

### Success Criteria:

#### Automated Verification:
- [ ] Support loop starts without errors
- [ ] State file is created on first run: `.aprd/support_state.json`
- [ ] State file is updated on each iteration
- [ ] Iteration counter increments correctly
- [ ] KeyboardInterrupt triggers graceful shutdown
- [ ] All validation checks run (tracker, PRD, git, verification)

#### Manual Verification:
- [ ] Run support mode for 2-3 iterations in test repo
- [ ] Check state file format matches auto_prd format
- [ ] Verify all output messages appear correctly
- [ ] Test Ctrl+C and verify graceful shutdown message
- [ ] Check that tracker.json is read correctly

**Note**: Complete all automated verification, then pause for manual confirmation before proceeding to Phase 4.

---

## Phase 4: Integrate CLI with Support Loop

### Overview
Connect the CLI entry point to the extracted support loop, add logging configuration, and test end-to-end functionality.

### Changes Required:

#### 1. Update CLI
**File**: `src/support_mode/cli.py`

Replace TODO placeholder with actual support loop call:

```python
"""CLI entry point for support-mode standalone tool."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .support_loop import run_support_mode
from .git_ops import git_root

def setup_logging(log_level: str = "INFO") -> None:
    """Configure logging for support mode."""
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Continuous monitoring and review tool for AI-assisted development",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--prd",
        required=True,
        type=Path,
        help="Path to PRD/task .md file",
    )
    parser.add_argument(
        "--repo",
        default=None,
        type=Path,
        help="Path to repo root (default: current git root)",
    )
    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=120,
        help="Polling interval in seconds (min: 5)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level for diagnostics",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 0.1.0",
    )

    return parser

def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # Validation
    if args.poll_seconds < 5:
        print("Error: --poll-seconds must be at least 5", file=sys.stderr)
        return 1

    if not args.prd.exists():
        print(f"Error: PRD file not found: {args.prd}", file=sys.stderr)
        return 1

    # Determine repo root
    repo_root = args.repo if args.repo else git_root()

    if not repo_root.exists():
        print(f"Error: Repo root not found: {repo_root}", file=sys.stderr)
        return 1

    # Setup logging
    setup_logging(args.log_level)

    # Run support mode
    try:
        run_support_mode(repo_root, args.prd, args.poll_seconds)
        return 0
    except KeyboardInterrupt:
        print("\nSupport mode stopped.")
        return 0
    except Exception as e:
        logging.exception("Support mode crashed")
        print(f"Error: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
```

#### 2. Add Basic Tests
**File**: `tests/test_cli.py`

```python
"""Basic CLI tests."""

import subprocess
import sys
from pathlib import Path

def test_cli_help():
    result = subprocess.run(
        [sys.executable, "-m", "support_mode", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Continuous monitoring" in result.stdout

def test_cli_version():
    result = subprocess.run(
        [sys.executable, "-m", "support_mode", "--version"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "0.1.0" in result.stdout

def test_cli_requires_prd():
    result = subprocess.run(
        [sys.executable, "-m", "support_mode"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "required: --prd" in result.stderr
```

### Success Criteria:

#### Automated Verification:
- [ ] `support-mode --help` displays all arguments
- [ ] `support-mode --version` displays version
- [ ] `support-mode --prd nonexistent.md` exits with error
- [ ] `support-mode --prd valid.md --poll-seconds 1` validates minimum poll interval
- [ ] Tests pass: `pytest tests/`

#### Manual Verification:
- [ ] Run in test repo with existing .aprd directory from auto_prd
- [ ] Verify support mode reads existing tracker.json
- [ ] Verify support mode updates existing support_state.json
- [ ] Run alongside auto_prd --support-mode and compare output
- [ ] Test with Cursor/Windsurf/Claude Code (verify no conflicts)

**Note**: Complete all automated verification, then pause for manual confirmation before proceeding to Phase 5.

---

## Phase 5: Package and Document

### Overview
Create README.md, prepare for PyPI publishing, and document installation and usage.

### Changes Required:

#### 1. README.md
**File**: `README.md`

```markdown
# Support Mode

Framework-agnostic continuous monitoring and review tool for AI-assisted development.

## Features

- Repository state monitoring (branch, commit SHA, working tree)
- Tracker validation (structure, features, tasks, dependencies)
- PRD synchronization (checkbox extraction, comparison)
- Git quality checks (`git diff --check`)
- Verification run status checking
- Guardrails display
- Configurable polling interval with graceful shutdown

## Installation

```bash
pip install support-mode
```

For development:

```bash
pip install -e .
```

## Usage

Basic usage:

```bash
support-mode --prd path/to/prd.md
```

With custom polling interval:

```bash
support-mode --prd path/to/prd.md --poll-seconds 60
```

Specify repository path:

```bash
support-mode --prd path/to/prd.md --repo /path/to/repo
```

## Compatibility

Support mode reads and writes the same `.aprd` directory structure as auto_prd:

- `.aprd/tracker.json` - Implementation tracker
- `.aprd/support_state.json` - Review state persistence
- `.aprd/verification/runs.jsonl` - Verification run history

This means you can use support-mode alongside auto_prd, or as a replacement
for the monitoring functionality.

## Requirements

- Python 3.10 or higher
- Git repository
- Existing `.aprd/tracker.json` file

## Exit Codes

- 0: Clean exit (Ctrl+C or completion)
- 1: Error (missing PRD, invalid arguments, etc.)

## License

MIT

## Contributing

Contributions welcome! Please open an issue or PR.
```

#### 2. MANIFEST.in (if needed)
**File**: `MANIFEST.in`

```
include README.md
include LICENSE
recursive-include src/support_mode *.json
```

#### 3. LICENSE
**File**: `LICENSE`

Use MIT license (same as auto_prd).

#### 4. .gitignore
**File**: `.gitignore`

```
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
build/
dist/
*.egg-info/
.eggs/
.pytest_cache/
.coverage
htmlcov/
*.log
```

### Success Criteria:

#### Automated Verification:
- [ ] README.md renders correctly on GitHub
- [ ] Package builds with `python -m build`
- [ ] Package can be installed from dist: `pip install dist/support-mode-0.1.0.tar.gz`
- [ ] All files included in distribution (check with `tar -tzf`)

#### Manual Verification:
- [ ] Test installation in clean virtual environment
- [ ] Verify tool works without auto_prd installed
- [ ] Follow README instructions in fresh environment
- [ ] Test with actual AI coding workflow (Cursor/Windsurf/etc.)

**Note**: Complete all automated verification, then pause for manual confirmation before proceeding to final release.

---

## Testing Strategy

### Unit Tests:
- `test_command.py`: Test `run_cmd()` with various git commands
- `test_git_ops.py`: Test git operations (branch, SHA, status)
- `test_tracker.py`: Test tracker loading and validation
- `test_state.py`: Test state persistence (load/save)

### Integration Tests:
- `test_support_loop.py`: Test full iteration of support loop
- `test_cli.py`: Test CLI argument parsing and invocation
- `test_compatibility.py`: Test backward compatibility with auto_prd files

### Manual Testing Steps:
1. **Create test repo** with .aprd directory from existing auto_prd project
2. **Run support mode** for 5 iterations, verify output
3. **Make changes** to tracker.json, verify warnings appear
4. **Modify PRD**, verify hash drift detection
5. **Test Ctrl+C**, verify graceful shutdown
6. **Run alongside auto_prd --support-mode**, compare output
7. **Test with Cursor/Windsurf**, verify no conflicts

## Migration Notes

**No migration needed** - support-mode uses the same file formats as auto_prd:

- `.aprd/support_state.json` - identical format
- `.aprd/tracker.json` - identical format
- `.aprd/verification/runs.jsonl` - identical format

Existing auto_prd users can:
1. Install support-mode: `pip install support-mode`
2. Run in same directory: `support-mode --prd prd.md`
3. Tool will read existing tracker and state files
4. State files remain compatible with auto_prd

## References

- Research: `/Users/simo/Projects/autodev/.wreckit/items/024-standalone-support-mode-cli/research.md`
- Source files:
  - `/tools/auto_prd/support_loop.py` (lines 138-458: main loop)
  - `/tools/auto_prd/command.py` (lines 422-612: run_cmd)
  - `/tools/auto_prd/git_ops.py` (lines 98-115: git operations)
  - `/tools/auto_prd/tracker_generator.py` (lines 295-332, 580-672: tracker utilities)
  - `/tools/auto_prd/tracker_validator.py` (entire file)
  - `/tools/auto_prd/verification_persistence.py` (lines 98-252: verification checking)
  - `/tools/auto_prd/guardrails.py` (lines 1-150: guardrails loading)
  - `/tools/auto_prd/cli.py` (lines 22-95: CLI argument parsing)
  - `/tools/auto_prd/tracker_schema.json` (entire file: tracker JSON schema)
