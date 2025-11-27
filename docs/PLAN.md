# AutoDev System Build Plan

**Version:** 1.1.0
**Created:** 2025-11-27
**Updated:** 2025-11-27
**Based on:** Anthropic's "Effective Harnesses for Long-Running Agents"

---

## Executive Summary

This plan transforms `aprd-tui` from a functional TUI into a **production-grade long-running agent harness** following Anthropic's recommended patterns. The current system has strong fundamentals (security, error handling, separation of concerns) but needs improvements in:

1. **Agent Architecture** - Implement two-agent pattern (initializer + incremental worker)
2. **Session Management** - Robust checkpoint/resume with verification
3. **Observability** - Structured progress tracking with explicit pass/fail states
4. **TUI Refactoring** - Split monolithic files for maintainability
5. **Edge Case Handling** - Address resource leaks and race conditions

---

## Current State Analysis

### Strengths
- Excellent security posture (command allowlists, path validation, symlink resolution)
- Comprehensive error handling with recovery hints
- Well-structured Python automation pipeline (5,681 LOC across 20 modules)
- Good test coverage for critical paths (57.2% on config validation)
- Thread-safe channel communication

### Critical Issues Found

| Issue | Severity | Location |
|-------|----------|----------|
| TUI code too monolithic | High | `view.go` (762 LOC), `update_keys.go` (695 LOC) |
| PRD path not validated before run | High | `internal/tui/run.go` |
| Config load silently falls back to defaults | Medium | `internal/config/config.go` |
| Log file close errors ignored | Medium | `internal/tui/logging.go` |
| API server hardcoded port `:8080` | Medium | `internal/api/server.go` |
| No debouncing for concurrent PRD scans | Medium | `internal/tui/prd.go` |
| Toast notification potential goroutine leak | Low | `internal/tui/model.go` |

---

## Implementation Phases

### Phase 1: Core Infrastructure Fixes (Foundation)

#### 1.1 Resource Management & Error Handling

**Goal:** Eliminate silent failures and resource leaks

```
Files to modify:
- internal/tui/logging.go     - Handle close errors properly
- internal/tui/model.go       - Cleanup on destruction
- internal/tui/run.go         - Validate PRD exists before execution
- internal/config/config.go   - Warn on corrupt config instead of silent fallback
```

**Tasks:**
1. Add error return to `closeLogFile()` and handle at call sites
2. Implement model cleanup method for graceful shutdown
3. Add PRD existence check in `startRun()`
4. Log warning when config load fails and preserve partial state
5. Add timeout on config save operations

#### 1.2 Configuration System Hardening

**Goal:** Make configuration robust and extensible

**Tasks:**
1. Add config schema validation on load
2. Implement config versioning with migration strategy
3. Add environment variable overrides for all timing defaults
4. Extract hardcoded values:
   - `:8080` API port -> config
   - `2000` max log lines -> config
   - `4 seconds` toast TTL -> config
   - `2048` channel buffer -> config

#### 1.3 Input Validation

**Goal:** Prevent invalid state from propagating

**Tasks:**
1. Add length limits on text inputs (tag input, branch names)
2. Validate Git branch name format
3. Verify base branch exists in repository
4. Validate codex model name format
5. Add comprehensive Python arg validation

---

### Phase 2: TUI Refactoring (Maintainability)

#### 2.1 Split Monolithic Files

**Goal:** Reduce cognitive load and improve testability

**Current state:**
```
view.go           762 LOC  -> Split into tab-specific renderers
update_keys.go    695 LOC  -> Split by tab/context
model.go          578 LOC  -> Extract submodels
```

**New structure:**
```
internal/tui/
├── model.go              # Core state (reduced)
├── model_run.go          # Run-specific state
├── model_prd.go          # PRD selection state
├── model_settings.go     # Settings state
├── view.go               # Main view dispatcher
├── view_run.go           # Run tab rendering
├── view_prd.go           # PRD tab rendering
├── view_settings.go      # Settings tab rendering
├── view_env.go           # Env tab rendering
├── view_logs.go          # Logs tab rendering
├── keys.go               # Key definitions
├── keys_run.go           # Run tab key handlers
├── keys_prd.go           # PRD tab key handlers
├── keys_settings.go      # Settings tab key handlers
└── ...
```

**Tasks:**
1. Extract tab-specific rendering to separate files
2. Extract tab-specific key handlers
3. Create submodels for each major state cluster
4. Add interface for tab behaviors
5. Update tests to match new structure

#### 2.2 Improve PRD Handling

**Goal:** Robust file selection with proper async handling

**Tasks:**
1. Add debouncing to PRD scan (prevent concurrent scans)
2. Watch for PRD deletion after selection
3. Stream large markdown previews (don't load entirely into memory)
4. Handle encoding errors gracefully in preview
5. Add file modification timestamp display

---

### Phase 3: Agent Harness Architecture (Anthropic Patterns)

This is the core innovation based on the Anthropic article.

#### 3.0 PRD Analysis & Tracker Generation (CRITICAL FIRST STEP)

**This is the foundational step that all subsequent agent work depends on.**

When starting the Local phase, the FIRST action is to have Claude/Codex analyze the PRD and generate a comprehensive JSON tracker. This tracker becomes the single source of truth for all subsequent agents.

##### 3.0.1 PRD Analyzer Prompt

The system sends the PRD to Claude/Codex with this structured prompt:

```markdown
# PRD Analysis Task

You are analyzing a Product Requirements Document (PRD) to create a detailed implementation tracker.

## Your Task
Read the PRD below and generate a JSON tracker file that:
1. Breaks down ALL requirements into discrete, implementable features
2. For each feature, defines clear success criteria and validation steps
3. Specifies testing requirements (unit, integration, e2e)
4. Identifies dependencies between features
5. Estimates complexity (S/M/L/XL)
6. Lists specific files likely to be created or modified

## Output Format
You MUST output valid JSON matching the schema below. Do not include any text outside the JSON.

## PRD Content:
{prd_content}
```

##### 3.0.2 Implementation Tracker JSON Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["version", "metadata", "features", "validation_summary"],
  "properties": {
    "version": {
      "type": "string",
      "const": "2.0.0"
    },
    "metadata": {
      "type": "object",
      "required": ["prd_source", "prd_hash", "created_at", "created_by", "project_context"],
      "properties": {
        "prd_source": { "type": "string", "description": "Path to source PRD file" },
        "prd_hash": { "type": "string", "description": "SHA-256 hash for change detection" },
        "created_at": { "type": "string", "format": "date-time" },
        "created_by": { "type": "string", "enum": ["claude", "codex"] },
        "project_context": {
          "type": "object",
          "properties": {
            "language": { "type": "string" },
            "framework": { "type": "string" },
            "test_framework": { "type": "string" },
            "build_system": { "type": "string" }
          }
        }
      }
    },
    "features": {
      "type": "array",
      "items": { "$ref": "#/$defs/feature" }
    },
    "validation_summary": {
      "type": "object",
      "required": ["total_features", "total_tasks", "estimated_complexity"],
      "properties": {
        "total_features": { "type": "integer" },
        "total_tasks": { "type": "integer" },
        "estimated_complexity": { "type": "string", "enum": ["small", "medium", "large", "xlarge"] },
        "critical_path": {
          "type": "array",
          "items": { "type": "string" },
          "description": "Feature IDs that form the critical dependency path"
        }
      }
    }
  },
  "$defs": {
    "feature": {
      "type": "object",
      "required": ["id", "name", "description", "priority", "status", "goals", "tasks", "acceptance_criteria", "testing", "validation"],
      "properties": {
        "id": { "type": "string", "pattern": "^F[0-9]{3}$" },
        "name": { "type": "string", "maxLength": 100 },
        "description": { "type": "string" },
        "priority": { "type": "string", "enum": ["critical", "high", "medium", "low"] },
        "complexity": { "type": "string", "enum": ["S", "M", "L", "XL"] },
        "status": {
          "type": "string",
          "enum": ["pending", "in_progress", "blocked", "completed", "verified", "failed"]
        },
        "dependencies": {
          "type": "array",
          "items": { "type": "string", "pattern": "^F[0-9]{3}$" },
          "description": "Feature IDs this feature depends on"
        },
        "goals": {
          "type": "object",
          "required": ["primary", "measurable_outcomes"],
          "properties": {
            "primary": { "type": "string", "description": "Single sentence primary goal" },
            "secondary": { "type": "array", "items": { "type": "string" } },
            "measurable_outcomes": {
              "type": "array",
              "items": { "type": "string" },
              "minItems": 1,
              "description": "Specific, measurable outcomes that prove success"
            }
          }
        },
        "tasks": {
          "type": "array",
          "items": { "$ref": "#/$defs/task" },
          "minItems": 1
        },
        "acceptance_criteria": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["id", "criterion", "verification_method"],
            "properties": {
              "id": { "type": "string", "pattern": "^AC[0-9]{3}$" },
              "criterion": { "type": "string" },
              "verification_method": {
                "type": "string",
                "enum": ["manual_test", "unit_test", "integration_test", "e2e_test", "code_review", "type_check", "lint_check"]
              },
              "status": { "type": "string", "enum": ["pending", "passed", "failed"] }
            }
          },
          "minItems": 1
        },
        "testing": {
          "type": "object",
          "required": ["unit_tests", "integration_tests"],
          "properties": {
            "unit_tests": {
              "type": "array",
              "items": {
                "type": "object",
                "required": ["description", "file_path"],
                "properties": {
                  "description": { "type": "string" },
                  "file_path": { "type": "string" },
                  "status": { "type": "string", "enum": ["pending", "written", "passing", "failing"] }
                }
              }
            },
            "integration_tests": {
              "type": "array",
              "items": {
                "type": "object",
                "required": ["description", "components_tested"],
                "properties": {
                  "description": { "type": "string" },
                  "components_tested": { "type": "array", "items": { "type": "string" } },
                  "file_path": { "type": "string" },
                  "status": { "type": "string", "enum": ["pending", "written", "passing", "failing"] }
                }
              }
            },
            "e2e_tests": {
              "type": "array",
              "items": {
                "type": "object",
                "properties": {
                  "scenario": { "type": "string" },
                  "steps": { "type": "array", "items": { "type": "string" } },
                  "status": { "type": "string", "enum": ["pending", "written", "passing", "failing"] }
                }
              }
            }
          }
        },
        "validation": {
          "type": "object",
          "required": ["benchmarks", "quality_gates"],
          "properties": {
            "benchmarks": {
              "type": "array",
              "items": {
                "type": "object",
                "required": ["metric", "target", "measurement_method"],
                "properties": {
                  "metric": { "type": "string" },
                  "target": { "type": "string" },
                  "measurement_method": { "type": "string" },
                  "actual": { "type": "string" },
                  "passed": { "type": "boolean" }
                }
              }
            },
            "quality_gates": {
              "type": "array",
              "items": {
                "type": "object",
                "required": ["gate", "requirement"],
                "properties": {
                  "gate": { "type": "string" },
                  "requirement": { "type": "string" },
                  "passed": { "type": "boolean" }
                }
              }
            }
          }
        },
        "files": {
          "type": "object",
          "properties": {
            "to_create": { "type": "array", "items": { "type": "string" } },
            "to_modify": { "type": "array", "items": { "type": "string" } }
          }
        },
        "commits": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "sha": { "type": "string" },
              "message": { "type": "string" },
              "timestamp": { "type": "string", "format": "date-time" }
            }
          },
          "description": "Git commits associated with this feature for rollback"
        },
        "verification_evidence": {
          "type": "object",
          "properties": {
            "screenshots": { "type": "array", "items": { "type": "string" } },
            "test_output_logs": { "type": "array", "items": { "type": "string" } },
            "verified_at": { "type": "string", "format": "date-time" },
            "verified_by": { "type": "string" }
          }
        }
      }
    },
    "task": {
      "type": "object",
      "required": ["id", "description", "status"],
      "properties": {
        "id": { "type": "string", "pattern": "^T[0-9]{3}$" },
        "description": { "type": "string" },
        "status": { "type": "string", "enum": ["pending", "in_progress", "completed", "blocked"] },
        "implementation_notes": { "type": "string" },
        "blockers": { "type": "array", "items": { "type": "string" } },
        "completed_at": { "type": "string", "format": "date-time" }
      }
    }
  }
}
```

##### 3.0.3 Example Generated Tracker

```json
{
  "version": "2.0.0",
  "metadata": {
    "prd_source": "prds/user-authentication.md",
    "prd_hash": "sha256:a1b2c3d4e5f6...",
    "created_at": "2025-11-27T10:00:00Z",
    "created_by": "claude",
    "project_context": {
      "language": "TypeScript",
      "framework": "Next.js 14",
      "test_framework": "Jest + Playwright",
      "build_system": "pnpm"
    }
  },
  "features": [
    {
      "id": "F001",
      "name": "User Registration Form",
      "description": "Create a registration form with email, password, and username fields",
      "priority": "critical",
      "complexity": "M",
      "status": "pending",
      "dependencies": [],
      "goals": {
        "primary": "Allow new users to create an account with validated credentials",
        "secondary": [
          "Provide real-time validation feedback",
          "Support password strength indicator"
        ],
        "measurable_outcomes": [
          "Form renders without console errors",
          "All validation rules trigger correctly",
          "Successful submission creates user in database",
          "Error states display appropriate messages"
        ]
      },
      "tasks": [
        {
          "id": "T001",
          "description": "Create RegisterForm component with controlled inputs",
          "status": "pending"
        },
        {
          "id": "T002",
          "description": "Implement Zod schema for form validation",
          "status": "pending"
        },
        {
          "id": "T003",
          "description": "Add password strength indicator component",
          "status": "pending"
        },
        {
          "id": "T004",
          "description": "Connect form to registration API endpoint",
          "status": "pending"
        },
        {
          "id": "T005",
          "description": "Add loading and error states",
          "status": "pending"
        }
      ],
      "acceptance_criteria": [
        {
          "id": "AC001",
          "criterion": "Email field validates correct format and shows error for invalid emails",
          "verification_method": "unit_test",
          "status": "pending"
        },
        {
          "id": "AC002",
          "criterion": "Password requires minimum 8 characters, 1 uppercase, 1 number",
          "verification_method": "unit_test",
          "status": "pending"
        },
        {
          "id": "AC003",
          "criterion": "Form prevents submission while validation errors exist",
          "verification_method": "e2e_test",
          "status": "pending"
        },
        {
          "id": "AC004",
          "criterion": "Successful registration redirects to dashboard",
          "verification_method": "e2e_test",
          "status": "pending"
        }
      ],
      "testing": {
        "unit_tests": [
          {
            "description": "RegisterForm renders all required fields",
            "file_path": "src/components/auth/__tests__/RegisterForm.test.tsx",
            "status": "pending"
          },
          {
            "description": "Validation schema rejects invalid inputs",
            "file_path": "src/lib/validations/__tests__/auth.test.ts",
            "status": "pending"
          }
        ],
        "integration_tests": [
          {
            "description": "Registration flow creates user and sends welcome email",
            "components_tested": ["RegisterForm", "AuthAPI", "EmailService"],
            "file_path": "src/__tests__/integration/registration.test.ts",
            "status": "pending"
          }
        ],
        "e2e_tests": [
          {
            "scenario": "New user completes registration successfully",
            "steps": [
              "Navigate to /register",
              "Fill in valid email, password, username",
              "Click submit",
              "Verify redirect to /dashboard",
              "Verify welcome toast appears"
            ],
            "status": "pending"
          }
        ]
      },
      "validation": {
        "benchmarks": [
          {
            "metric": "Form render time",
            "target": "< 100ms",
            "measurement_method": "React Profiler"
          },
          {
            "metric": "Validation feedback latency",
            "target": "< 50ms after input blur",
            "measurement_method": "Performance timing"
          }
        ],
        "quality_gates": [
          {
            "gate": "TypeScript strict mode",
            "requirement": "No type errors in component"
          },
          {
            "gate": "Accessibility",
            "requirement": "All inputs have labels, form is keyboard navigable"
          },
          {
            "gate": "Test coverage",
            "requirement": "> 80% line coverage for RegisterForm"
          }
        ]
      },
      "files": {
        "to_create": [
          "src/components/auth/RegisterForm.tsx",
          "src/components/auth/PasswordStrength.tsx",
          "src/lib/validations/auth.ts",
          "src/components/auth/__tests__/RegisterForm.test.tsx"
        ],
        "to_modify": [
          "src/app/(auth)/register/page.tsx",
          "src/lib/api/auth.ts"
        ]
      },
      "commits": [],
      "verification_evidence": {}
    },
    {
      "id": "F002",
      "name": "User Login Form",
      "description": "Create login form with email/password authentication",
      "priority": "critical",
      "complexity": "S",
      "status": "pending",
      "dependencies": ["F001"],
      "goals": {
        "primary": "Allow existing users to authenticate with their credentials",
        "measurable_outcomes": [
          "Valid credentials result in successful login",
          "Invalid credentials show appropriate error",
          "Session token is stored securely"
        ]
      },
      "tasks": [
        {
          "id": "T006",
          "description": "Create LoginForm component",
          "status": "pending"
        },
        {
          "id": "T007",
          "description": "Implement login API integration",
          "status": "pending"
        },
        {
          "id": "T008",
          "description": "Add 'Remember me' functionality",
          "status": "pending"
        }
      ],
      "acceptance_criteria": [
        {
          "id": "AC005",
          "criterion": "Valid login creates session and redirects to dashboard",
          "verification_method": "e2e_test",
          "status": "pending"
        }
      ],
      "testing": {
        "unit_tests": [],
        "integration_tests": []
      },
      "validation": {
        "benchmarks": [],
        "quality_gates": []
      },
      "files": {
        "to_create": ["src/components/auth/LoginForm.tsx"],
        "to_modify": ["src/app/(auth)/login/page.tsx"]
      },
      "commits": [],
      "verification_evidence": {}
    }
  ],
  "validation_summary": {
    "total_features": 2,
    "total_tasks": 8,
    "estimated_complexity": "medium",
    "critical_path": ["F001", "F002"]
  }
}
```

##### 3.0.4 Tracker Storage Location

```
{repo_root}/
└── .aprd/
    └── tracker.json          # THE source of truth for all agents
```

**Why `.aprd/` directory in repo:**
- Version controlled with the code
- Visible to all agents without special paths
- Can be committed to show progress history
- Easy to inspect and debug

##### 3.0.5 Tracker Generation Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    LOCAL PHASE START                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 1: Check for existing tracker                              │
│   - If .aprd/tracker.json exists AND prd_hash matches → skip    │
│   - If exists but prd_hash differs → regenerate with warning    │
│   - If not exists → generate new                                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 2: Send PRD to Claude/Codex with analysis prompt           │
│   - Include project context (package.json, tsconfig, etc.)      │
│   - Include existing file structure                             │
│   - Request JSON output only                                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 3: Validate generated JSON                                 │
│   - Parse JSON (fail if invalid)                                │
│   - Validate against schema                                     │
│   - Check all required fields populated                         │
│   - Verify feature IDs are unique                               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 4: Write tracker and commit                                │
│   - Create .aprd/ directory if needed                           │
│   - Write tracker.json                                          │
│   - Git commit: "chore(aprd): initialize implementation tracker"│
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 5: Proceed to feature implementation                       │
│   - Select first feature with no unmet dependencies             │
│   - Mark as "in_progress"                                       │
│   - Begin implementation loop                                   │
└─────────────────────────────────────────────────────────────────┘
```

##### 3.0.6 Implementation: `tools/auto_prd/tracker_generator.py`

```python
"""PRD Tracker Generator - Creates detailed JSON tracker from PRD analysis."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Optional

from .agents import run_agent
from .logging_utils import logger

TRACKER_VERSION = "2.0.0"
TRACKER_DIR = ".aprd"
TRACKER_FILE = "tracker.json"

ANALYSIS_PROMPT = '''
# PRD Analysis Task

You are an expert software architect analyzing a Product Requirements Document (PRD).
Your task is to create a comprehensive implementation tracker in JSON format.

## Requirements

1. **Feature Extraction**: Break down ALL requirements into discrete features
   - Each feature should be implementable in 1-4 hours
   - Complex requirements should be split into multiple features
   - Identify dependencies between features

2. **Task Breakdown**: For each feature, define specific tasks
   - Tasks should be atomic (completable in 15-60 minutes)
   - Include both implementation and testing tasks

3. **Acceptance Criteria**: Define clear, testable criteria
   - Each criterion must be verifiable
   - Specify the verification method (unit_test, e2e_test, etc.)

4. **Testing Requirements**: Specify required tests
   - Unit tests for individual components
   - Integration tests for component interactions
   - E2E tests for user-facing features

5. **Validation Benchmarks**: Define measurable quality targets
   - Performance targets where applicable
   - Quality gates (type safety, accessibility, coverage)

6. **File Mapping**: Predict files to create/modify
   - Use project conventions from context provided

## Project Context

Language: {language}
Framework: {framework}
Test Framework: {test_framework}
Existing Structure:
{file_structure}

## PRD Content

{prd_content}

## Output

Return ONLY valid JSON matching the tracker schema. No explanation or markdown.
'''


def compute_prd_hash(prd_path: Path) -> str:
    """Compute SHA-256 hash of PRD content."""
    content = prd_path.read_bytes()
    return f"sha256:{hashlib.sha256(content).hexdigest()[:16]}"


def get_tracker_path(repo_root: Path) -> Path:
    """Get path to tracker.json."""
    return repo_root / TRACKER_DIR / TRACKER_FILE


def load_tracker(repo_root: Path) -> Optional[dict[str, Any]]:
    """Load existing tracker if present."""
    tracker_path = get_tracker_path(repo_root)
    if not tracker_path.exists():
        return None
    try:
        return json.loads(tracker_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load tracker: %s", e)
        return None


def should_regenerate_tracker(
    existing: Optional[dict], prd_path: Path
) -> tuple[bool, str]:
    """Check if tracker needs regeneration."""
    if existing is None:
        return True, "no_existing_tracker"

    current_hash = compute_prd_hash(prd_path)
    stored_hash = existing.get("metadata", {}).get("prd_hash", "")

    if current_hash != stored_hash:
        return True, "prd_content_changed"

    return False, "tracker_current"


def detect_project_context(repo_root: Path) -> dict[str, str]:
    """Detect project language, framework, etc."""
    context = {
        "language": "unknown",
        "framework": "unknown",
        "test_framework": "unknown",
        "build_system": "unknown"
    }

    # Check for package.json (Node/JS/TS)
    pkg_json = repo_root / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text())
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

            context["language"] = "TypeScript" if "typescript" in deps else "JavaScript"

            if "next" in deps:
                context["framework"] = f"Next.js {deps.get('next', '')}"
            elif "react" in deps:
                context["framework"] = f"React {deps.get('react', '')}"
            elif "express" in deps:
                context["framework"] = "Express"

            if "jest" in deps:
                context["test_framework"] = "Jest"
            if "playwright" in deps:
                context["test_framework"] += " + Playwright" if context["test_framework"] != "unknown" else "Playwright"
            if "vitest" in deps:
                context["test_framework"] = "Vitest"

            context["build_system"] = "pnpm" if (repo_root / "pnpm-lock.yaml").exists() else "npm"
        except Exception:
            pass

    # Check for pyproject.toml (Python)
    pyproject = repo_root / "pyproject.toml"
    if pyproject.exists():
        context["language"] = "Python"
        context["test_framework"] = "pytest"
        context["build_system"] = "uv" if (repo_root / "uv.lock").exists() else "pip"

    # Check for go.mod (Go)
    if (repo_root / "go.mod").exists():
        context["language"] = "Go"
        context["test_framework"] = "go test"
        context["build_system"] = "go"

    return context


def get_file_structure(repo_root: Path, max_depth: int = 3) -> str:
    """Get simplified file structure for context."""
    lines = []

    def walk(path: Path, prefix: str = "", depth: int = 0):
        if depth > max_depth:
            return

        items = sorted(path.iterdir(), key=lambda x: (x.is_file(), x.name))

        # Filter out common non-essential directories
        skip_dirs = {".git", "node_modules", "__pycache__", ".next", "dist", "build", ".aprd"}
        items = [i for i in items if i.name not in skip_dirs]

        for i, item in enumerate(items[:20]):  # Limit items per directory
            is_last = i == len(items) - 1
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{item.name}")

            if item.is_dir():
                extension = "    " if is_last else "│   "
                walk(item, prefix + extension, depth + 1)

    walk(repo_root)
    return "\n".join(lines[:100])  # Limit total lines


def validate_tracker(tracker: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate tracker structure and content."""
    errors = []

    # Check version
    if tracker.get("version") != TRACKER_VERSION:
        errors.append(f"Invalid version: expected {TRACKER_VERSION}")

    # Check metadata
    metadata = tracker.get("metadata", {})
    for field in ["prd_source", "prd_hash", "created_at", "created_by"]:
        if not metadata.get(field):
            errors.append(f"Missing metadata.{field}")

    # Check features
    features = tracker.get("features", [])
    if not features:
        errors.append("No features defined")

    feature_ids = set()
    for feature in features:
        fid = feature.get("id", "")
        if not fid:
            errors.append("Feature missing id")
        elif fid in feature_ids:
            errors.append(f"Duplicate feature id: {fid}")
        else:
            feature_ids.add(fid)

        # Check required feature fields
        for field in ["name", "status", "goals", "tasks", "acceptance_criteria"]:
            if not feature.get(field):
                errors.append(f"Feature {fid} missing {field}")

        # Check tasks
        tasks = feature.get("tasks", [])
        if not tasks:
            errors.append(f"Feature {fid} has no tasks")

        # Check acceptance criteria
        criteria = feature.get("acceptance_criteria", [])
        if not criteria:
            errors.append(f"Feature {fid} has no acceptance criteria")

    # Check validation summary
    summary = tracker.get("validation_summary", {})
    if not summary.get("total_features"):
        errors.append("Missing validation_summary.total_features")

    return len(errors) == 0, errors


async def generate_tracker(
    prd_path: Path,
    repo_root: Path,
    executor: str = "claude",
    force: bool = False
) -> dict[str, Any]:
    """Generate tracker from PRD using Claude/Codex.

    Args:
        prd_path: Path to the PRD markdown file
        repo_root: Repository root directory
        executor: Which agent to use ("claude" or "codex")
        force: Regenerate even if current tracker exists

    Returns:
        The generated/loaded tracker dictionary

    Raises:
        ValueError: If tracker generation or validation fails
    """
    # Check for existing tracker
    existing = load_tracker(repo_root)
    should_regen, reason = should_regenerate_tracker(existing, prd_path)

    if not should_regen and not force:
        logger.info("Using existing tracker (reason: %s)", reason)
        return existing

    logger.info("Generating tracker (reason: %s)", reason)

    # Gather context
    prd_content = prd_path.read_text()
    context = detect_project_context(repo_root)
    file_structure = get_file_structure(repo_root)

    # Build prompt
    prompt = ANALYSIS_PROMPT.format(
        language=context["language"],
        framework=context["framework"],
        test_framework=context["test_framework"],
        file_structure=file_structure,
        prd_content=prd_content
    )

    # Call agent
    logger.info("Sending PRD to %s for analysis...", executor)
    result = await run_agent(
        executor=executor,
        prompt=prompt,
        expect_json=True
    )

    # Parse response
    try:
        tracker = json.loads(result.output)
    except json.JSONDecodeError as e:
        raise ValueError(f"Agent returned invalid JSON: {e}")

    # Inject metadata
    tracker["version"] = TRACKER_VERSION
    tracker.setdefault("metadata", {})
    tracker["metadata"]["prd_source"] = str(prd_path)
    tracker["metadata"]["prd_hash"] = compute_prd_hash(prd_path)
    tracker["metadata"]["created_by"] = executor

    # Validate
    valid, errors = validate_tracker(tracker)
    if not valid:
        raise ValueError(f"Tracker validation failed: {errors}")

    # Save
    tracker_path = get_tracker_path(repo_root)
    tracker_path.parent.mkdir(parents=True, exist_ok=True)
    tracker_path.write_text(json.dumps(tracker, indent=2))

    logger.info("Tracker generated: %d features, %d total tasks",
                tracker["validation_summary"]["total_features"],
                tracker["validation_summary"]["total_tasks"])

    return tracker
```

#### 3.1 Two-Agent Architecture

**Initializer Agent (First Run) - NOW INCLUDES TRACKER GENERATION**
- **Step 1: Generate Implementation Tracker** (see 3.0 above)
- Sets up repository scaffolding
- Establishes baseline tests
- Selects first feature to implement

**Incremental Worker Agent (Subsequent Runs)**
- **MUST load and use the tracker** - no work without it
- Works on ONE feature at a time
- Updates tracker status after each task/feature
- Runs verification before marking feature complete
- Commits progress with descriptive messages

**Implementation:**
```python
# tools/auto_prd/initializer.py (NEW)
class InitializerAgent:
    """First-run setup agent - creates tracker and prepares workspace"""

    async def run(self, prd_path: Path, repo_root: Path) -> InitResult:
        # Step 1: Generate tracker (CRITICAL)
        tracker = await generate_tracker(prd_path, repo_root)

        # Step 2: Commit tracker
        await self.commit_tracker(repo_root)

        # Step 3: Run baseline tests
        baseline = await self.run_baseline_tests(repo_root)

        # Step 4: Select first feature
        first_feature = self.select_next_feature(tracker)

        return InitResult(
            tracker=tracker,
            baseline_passed=baseline.success,
            next_feature=first_feature
        )

# tools/auto_prd/worker.py (REFACTOR from local_loop.py)
class IncrementalWorker:
    """Single-feature worker agent - MUST use tracker"""

    def __init__(self, tracker: dict, repo_root: Path):
        self.tracker = tracker
        self.repo_root = repo_root
        self.tracker_path = get_tracker_path(repo_root)

    async def run_feature(self, feature_id: str) -> FeatureResult:
        feature = self.get_feature(feature_id)

        # Update status
        feature["status"] = "in_progress"
        self.save_tracker()

        # Implement each task
        for task in feature["tasks"]:
            result = await self.implement_task(feature, task)
            task["status"] = "completed" if result.success else "blocked"
            self.save_tracker()  # Save after each task!

        # Run verification
        verification = await self.verify_feature(feature)

        # Update final status
        if verification.passed:
            feature["status"] = "verified"
            feature["verification_evidence"] = verification.evidence
        else:
            feature["status"] = "failed"

        self.save_tracker()
        return FeatureResult(feature_id, verification)
```

#### 3.2 How Subsequent Agents Use the Tracker

**Every agent invocation MUST:**

1. **Load tracker at startup**
   ```python
   tracker = load_tracker(repo_root)
   if not tracker:
       raise RuntimeError("No tracker found - run initializer first")
   ```

2. **Include tracker context in prompts**
   ```python
   prompt = f"""
   ## Current Implementation Status

   You are working on feature {feature['id']}: {feature['name']}

   ### Goals
   Primary: {feature['goals']['primary']}

   ### Tasks to Complete
   {format_tasks(feature['tasks'])}

   ### Acceptance Criteria
   {format_criteria(feature['acceptance_criteria'])}

   ### Testing Requirements
   {format_tests(feature['testing'])}

   ### Quality Gates
   {format_quality_gates(feature['validation']['quality_gates'])}

   ## Instructions
   Implement the next pending task. After implementation:
   1. Run relevant tests
   2. Verify acceptance criteria
   3. Report what was completed
   """
   ```

3. **Update tracker after EVERY action**
   - Task completed → update task status
   - Test written → update test status
   - Test passing → update test status
   - Feature done → run verification, update status

4. **Never mark complete without verification**
   ```python
   # WRONG
   feature["status"] = "completed"  # NO!

   # RIGHT
   verification = await verify_feature(feature)
   if verification.all_criteria_passed and verification.all_tests_passing:
       feature["status"] = "verified"
       feature["verification_evidence"] = {
           "verified_at": datetime.now().isoformat(),
           "test_output_logs": verification.logs,
           "screenshots": verification.screenshots
       }
   ```

5. **Commit tracker changes with code**
   ```bash
   git add .aprd/tracker.json src/components/...
   git commit -m "feat(F001): implement user registration form

   - Created RegisterForm component
   - Added Zod validation schema
   - All acceptance criteria verified

   Tracker: F001 status → verified"
   ```

#### 3.3 Session Startup Protocol

Every agent session begins with this sequence:

```python
class SessionStartup:
    def __init__(self):
        self.steps = [
            "verify_working_directory",
            "review_git_history",
            "load_feature_spec",
            "check_environment_health",
            "run_baseline_tests",
            "select_next_feature"
        ]

    def execute(self) -> StartupResult:
        for step in self.steps:
            result = getattr(self, step)()
            if not result.success:
                return StartupResult(success=False, failed_at=step)
        return StartupResult(success=True)
```

#### 3.4 Explicit Verification Requirements

**Problem:** Agents mark features complete without end-to-end testing

**Solution:** Require explicit verification before completion

```python
class VerificationProtocol:
    """Verification required before marking feature complete"""

    def verify_feature(self, feature: Feature) -> VerificationResult:
        # 1. Run unit tests
        unit_result = self.run_unit_tests(feature)

        # 2. Run integration tests
        integration_result = self.run_integration_tests(feature)

        # 3. Run e2e test (with browser if UI feature)
        e2e_result = self.run_e2e_test(feature)

        # 4. Collect evidence
        evidence = self.collect_evidence(feature)

        return VerificationResult(
            passed=all([unit_result, integration_result, e2e_result]),
            evidence=evidence
        )
```

---

### Phase 4: Observability & Progress Tracking

#### 4.1 Structured Progress File

```
~/.config/aprd/sessions/{session_id}/
├── feature_spec.json      # Itemized features with status
├── progress.txt           # Human-readable log
├── journal.jsonl          # Machine-readable events
├── checkpoints/           # Resumable state snapshots
└── evidence/              # Screenshots, test outputs
```

#### 4.2 Progress Dashboard in TUI

**New "Progress" tab showing:**
- Total features: X
- Completed: Y (with pass/fail counts)
- In progress: Z
- Remaining: W
- Current feature details
- Recent verification results

#### 4.3 Journal System Enhancements

```python
# Extend existing journal.py
class EnhancedJournal:
    def log_feature_start(self, feature_id: str)
    def log_step_complete(self, feature_id: str, step_id: str, result: str)
    def log_verification(self, feature_id: str, result: VerificationResult)
    def log_commit(self, feature_id: str, commit_sha: str)
    def export_summary(self) -> Dict
```

---

### Phase 5: Error Recovery & Resilience

#### 5.1 Git-Based Rollback

**Tasks:**
1. Enforce clean commits per feature
2. Add `rollback_feature(feature_id)` command
3. Track commit SHAs in feature spec
4. Add recovery protocol for failed features

#### 5.2 Checkpoint Enhancements

```python
# Extend existing checkpoint.py
class EnhancedCheckpoint:
    def save_with_verification(self) -> CheckpointResult
    def validate_integrity(self) -> bool
    def recover_from_corruption(self) -> RecoveryResult
    def list_recoverable_points(self) -> List[CheckpointInfo]
```

#### 5.3 Retry Logic Improvements

**Tasks:**
1. Add exponential backoff for all network operations
2. Implement circuit breaker for repeated failures
3. Add retry budget per session
4. Log all retry attempts to journal

---

### Phase 6: Testing & Quality

#### 6.1 Increase Test Coverage

**Current coverage:**
- Config validation: 57.2%
- Runner: ~40% (estimated)
- TUI: ~30% (estimated)
- Python: Variable

**Target coverage:**
- Config validation: 80%+
- Runner: 70%+
- TUI: 50%+
- Python critical paths: 80%+

**New test files needed:**
```
internal/tui/run_test.go           # Run execution tests
internal/tui/startup_test.go       # Startup sequence tests
internal/runner/validation_test.go # Comprehensive validation
tools/tests/test_initializer.py    # Initializer agent tests
tools/tests/test_verification.py   # Verification protocol tests
```

#### 6.2 Integration Tests

**Tasks:**
1. Add end-to-end test harness
2. Test full session lifecycle
3. Test checkpoint/resume cycle
4. Test error recovery paths
5. Add performance benchmarks

#### 6.3 Linting & Type Safety

**Go:**
```bash
golangci-lint run --enable-all
```

**Python:**
```bash
ruff check tools/
mypy tools/auto_prd/
```

---

### Phase 7: Documentation & Developer Experience

#### 7.1 Architecture Documentation

**Tasks:**
1. Create `docs/ARCHITECTURE.md` with diagrams
2. Document two-agent pattern
3. Document feature spec format
4. Document checkpoint system

#### 7.2 Operational Guides

**Tasks:**
1. Create `docs/OPERATIONS.md` for running in production
2. Add troubleshooting guide
3. Document environment variables
4. Add FAQ

#### 7.3 Developer Onboarding

**Tasks:**
1. Improve README with quick start
2. Add contributing guidelines
3. Document code style conventions
4. Add example workflows

---

## Implementation Order

Based on dependencies and impact:

```
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 3.0: PRD→TRACKER GENERATION (HIGHEST PRIORITY)          │
│  This is the foundational change that enables everything else   │
└─────────────────────────────────────────────────────────────────┘
                              │
Phase 3.0 (Tracker Generator)       [Week 1-2]
  - Create tracker_generator.py
  - Create tracker_schema.json
  - Integrate into app.py at Local phase start
  - Test with sample PRDs
                              │
                              ▼
Phase 1.1 (Resource Management)     [Week 2]
    ↓
Phase 1.2 (Config Hardening)        [Week 2]
    ↓
Phase 1.3 (Input Validation)        [Week 2]
    ↓
Phase 3.1 (Initializer Agent)       [Week 3]
  - Builds on tracker_generator
  - Creates initializer.py
    ↓
Phase 3.2 (Worker Agent)            [Week 3]
  - Refactor local_loop.py → worker.py
  - Must read/update tracker
    ↓
Phase 3.3 (Session Startup)         [Week 3-4]
    ↓
Phase 3.4 (Verification Protocol)   [Week 4]
    ↓
Phase 2.1 (TUI Split)               [Week 4]
    ↓
Phase 2.2 (PRD Handling)            [Week 4]
    ↓
Phase 4.1-4.3 (Observability)       [Week 5]
  - Add Progress tab to TUI
  - Show tracker status
    ↓
Phase 5.1-5.3 (Error Recovery)      [Week 5]
    ↓
Phase 6.1-6.3 (Testing)             [Week 6]
    ↓
Phase 7.1-7.3 (Documentation)       [Week 6]

┌─────────────────────────────────────────────────────────────────┐
│  KEY DEPENDENCY: All Phase 3.x work depends on 3.0 completion   │
│  The tracker is the contract between all agent invocations      │
└─────────────────────────────────────────────────────────────────┘
```

---

## Key Anthropic Principles Applied

| Principle | Implementation |
|-----------|----------------|
| **PRD→Tracker First** | **NEW:** First step generates detailed JSON tracker with goals, tasks, criteria, tests |
| **Two-Agent Architecture** | Initializer creates tracker; Worker implements one feature at a time using tracker |
| **Single Feature Per Session** | Tracker tracks individual features; worker selects one with no unmet dependencies |
| **JSON Over Markdown** | Tracker in JSON (`.aprd/tracker.json`) for model stability and programmatic updates |
| **Session Startup Verification** | Load tracker, validate PRD hash, check all dependencies before work |
| **Git-Based Rollback** | Tracker records commit SHAs per feature; enables surgical rollbacks |
| **Explicit Verification** | Tracker requires all acceptance criteria + tests pass before `status: "verified"` |
| **Progress Documentation** | Tracker IS the progress doc + human-readable journal.jsonl for debugging |
| **Context Optimization** | Tracker provides structured context; agents don't need to re-analyze PRD |
| **Handover Contract** | Tracker is the contract between agent sessions - all state lives there |

---

## Success Metrics

1. **Reliability:** 95%+ of sessions complete without manual intervention
2. **Accuracy:** 90%+ of marked-complete features pass verification
3. **Recovery:** 100% of interrupted sessions can resume
4. **Observability:** Real-time visibility into agent progress
5. **Maintainability:** No single file > 400 LOC in TUI package

---

## Files to Create

```
# Core Agent Harness (Phase 3.0 - CRITICAL)
tools/auto_prd/tracker_generator.py  # PRD→JSON tracker generation (NEW - PRIORITY)
tools/auto_prd/tracker_schema.json   # JSON Schema for tracker validation
tools/auto_prd/initializer.py        # Initializer agent (uses tracker_generator)
tools/auto_prd/worker.py             # Incremental worker (refactored from local_loop)
tools/auto_prd/verification.py       # Verification protocol
tools/auto_prd/startup.py            # Session startup protocol
tools/auto_prd/rollback.py           # Git-based feature rollback

# TUI Refactoring (Phase 2)
internal/tui/view_run.go             # Run tab rendering
internal/tui/view_prd.go             # PRD tab rendering
internal/tui/view_settings.go        # Settings tab rendering
internal/tui/view_env.go             # Env tab rendering
internal/tui/view_logs.go            # Logs tab rendering
internal/tui/view_progress.go        # NEW: Progress dashboard tab
internal/tui/keys_run.go             # Run tab key handlers
internal/tui/keys_prd.go             # PRD tab key handlers
internal/tui/keys_settings.go        # Settings tab key handlers

# Documentation (Phase 7)
docs/ARCHITECTURE.md                 # Architecture documentation
docs/OPERATIONS.md                   # Operations guide
docs/TRACKER_SCHEMA.md               # Tracker format documentation
```

## Files to Modify

```
# Core Pipeline Integration (Phase 3.0)
tools/auto_prd/app.py              # Integrate tracker generation at Local phase start
tools/auto_prd/local_loop.py       # Refactor to worker pattern, use tracker
tools/auto_prd/agents.py           # Add JSON output mode, tracker context injection
tools/auto_prd/checkpoint.py       # Integrate tracker state, add integrity validation
tools/auto_prd/journal.py          # Add feature-level logging (F001, T001 events)

# TUI Modifications (Phase 2)
internal/tui/model.go              # Reduce, extract submodels, add tracker state
internal/tui/view.go               # Make dispatcher only
internal/tui/update_keys.go        # Split by context
internal/tui/logging.go            # Fix error handling
internal/tui/run.go                # Add PRD validation, tracker status display

# Infrastructure (Phase 1)
internal/config/config.go          # Add versioning, warnings
internal/api/server.go             # Configurable port
.gitignore                         # Ensure .aprd/ is NOT ignored (we want it tracked)
```

---

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| TUI refactor breaks UX | Comprehensive test coverage before split |
| Two-agent complexity | Start with simple initializer, iterate |
| Feature spec format changes | Version field enables migrations |
| Checkpoint corruption | Add integrity checks and recovery |
| Test coverage gaps | CI enforcement of coverage thresholds |

---

## Conclusion

This plan transforms `aprd-tui` into a production-grade agent harness by:

1. **Creating the PRD→Tracker system** (Phase 3.0) - **THE KEY INNOVATION**
   - First step: Claude/Codex analyzes PRD and generates detailed `.aprd/tracker.json`
   - Tracker contains: features, tasks, acceptance criteria, testing requirements, benchmarks
   - All subsequent agents MUST use the tracker - it's the handover contract

2. **Fixing critical infrastructure issues** (Phase 1)
3. **Implementing Anthropic's proven patterns** for long-running agents (Phase 3.1-3.4)
4. **Improving maintainability** through TUI refactoring (Phase 2)
5. **Building resilience** with proper error recovery (Phase 5)
6. **Ensuring quality** with comprehensive testing (Phase 6)
7. **Documenting** for future developers (Phase 7)

**The tracker is the heart of the system.** Without it, agents operate blind. With it, every agent knows:
- What features exist and their status
- What tasks remain for each feature
- What acceptance criteria must pass
- What tests must be written and passing
- What quality gates must be met
- Which commits belong to which feature (for rollback)

The result will be a robust, observable, and recoverable automation system that can reliably implement features from PRDs with minimal human intervention, with clear handover between agent sessions.
