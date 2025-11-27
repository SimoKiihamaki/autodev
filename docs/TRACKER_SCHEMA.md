# Implementation Tracker Schema

This document describes the JSON schema for the implementation tracker file (`.aprd/tracker.json`).

## Overview

The tracker serves as the contract between all agent invocations in the AutoDev system. It:

- Defines all features to implement
- Tracks progress through task completion
- Records verification evidence
- Associates git commits for rollback
- Validates agent output

## Schema Location

```
tools/auto_prd/tracker_schema.json
```

JSON Schema version: Draft 2020-12

## Top-Level Structure

```json
{
  "version": "2.0.0",
  "metadata": { ... },
  "features": [ ... ],
  "validation_summary": { ... }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `version` | string | Yes | Schema version (currently "2.0.0") |
| `metadata` | object | Yes | Source and context information |
| `features` | array | Yes | List of features to implement |
| `validation_summary` | object | Yes | Summary statistics |

## Metadata

```json
{
  "metadata": {
    "prd_source": "path/to/prd.md",
    "prd_hash": "sha256:abc123...",
    "created_at": "2024-01-01T00:00:00Z",
    "created_by": "claude",
    "project_context": {
      "language": "Go",
      "framework": "Bubble Tea",
      "test_framework": "go test",
      "build_system": "make"
    }
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `prd_source` | string | Yes | Path to source PRD file |
| `prd_hash` | string | Yes | SHA-256 hash for change detection (format: `sha256:xxxx`) |
| `created_at` | string | Yes | ISO 8601 timestamp |
| `created_by` | string | Yes | Which agent generated it (`claude` or `codex`) |
| `project_context` | object | Yes | Project technology context |

## Feature

```json
{
  "id": "F001",
  "name": "User Authentication",
  "description": "Implement user login and registration",
  "priority": "high",
  "complexity": "M",
  "status": "pending",
  "dependencies": [],
  "goals": { ... },
  "tasks": [ ... ],
  "acceptance_criteria": [ ... ],
  "testing": { ... },
  "validation": { ... },
  "files": { ... },
  "commits": [ ... ],
  "verification_evidence": { ... }
}
```

### Core Fields

| Field | Type | Required | Values |
|-------|------|----------|--------|
| `id` | string | Yes | Format: `F001`, `F002`, etc. |
| `name` | string | Yes | Max 100 chars |
| `description` | string | Yes | Detailed description |
| `priority` | string | Yes | `critical`, `high`, `medium`, `low` |
| `complexity` | string | No | `S`, `M`, `L`, `XL` |
| `status` | string | Yes | `pending`, `in_progress`, `blocked`, `completed`, `verified`, `failed` |
| `dependencies` | array | No | List of feature IDs (e.g., `["F001"]`) |

### Goals

```json
{
  "goals": {
    "primary": "Allow users to securely log in",
    "secondary": ["Support OAuth providers"],
    "measurable_outcomes": [
      "Login success rate > 99%",
      "Session management works correctly"
    ]
  }
}
```

| Field | Type | Required |
|-------|------|----------|
| `primary` | string | Yes |
| `secondary` | array[string] | No |
| `measurable_outcomes` | array[string] | Yes |

### Tasks

```json
{
  "tasks": [
    {
      "id": "T001",
      "description": "Create login form component",
      "status": "pending",
      "implementation_notes": "Use React Hook Form",
      "blockers": [],
      "completed_at": null
    }
  ]
}
```

| Field | Type | Required | Values |
|-------|------|----------|--------|
| `id` | string | Yes | Format: `T001`, `T002`, etc. |
| `description` | string | Yes | What needs to be done |
| `status` | string | Yes | `pending`, `in_progress`, `completed`, `blocked` |
| `implementation_notes` | string | No | How to implement |
| `blockers` | array[string] | No | What's blocking |
| `completed_at` | string | No | ISO 8601 timestamp |

### Acceptance Criteria

```json
{
  "acceptance_criteria": [
    {
      "id": "AC001",
      "criterion": "Users can log in with email/password",
      "verification_method": "e2e_test",
      "status": "pending"
    }
  ]
}
```

| Field | Type | Required | Values |
|-------|------|----------|--------|
| `id` | string | Yes | Format: `AC001`, `AC002`, etc. |
| `criterion` | string | Yes | Testable criterion |
| `verification_method` | string | Yes | `manual_test`, `unit_test`, `integration_test`, `e2e_test`, `code_review`, `type_check`, `lint_check` |
| `status` | string | No | `pending`, `passed`, `failed` |

### Testing

```json
{
  "testing": {
    "unit_tests": [
      {
        "description": "Test password validation",
        "file_path": "src/auth/__tests__/password.test.ts",
        "status": "pending"
      }
    ],
    "integration_tests": [
      {
        "description": "Test login flow with database",
        "components_tested": ["AuthService", "UserRepository"],
        "file_path": "tests/integration/auth.test.ts",
        "status": "pending"
      }
    ],
    "e2e_tests": [
      {
        "scenario": "User login flow",
        "steps": [
          "Navigate to login page",
          "Enter credentials",
          "Click submit",
          "Verify redirect to dashboard"
        ],
        "file_path": "e2e/auth.spec.ts",
        "status": "pending"
      }
    ]
  }
}
```

Test status values: `pending`, `written`, `passing`, `failing`

### Validation

```json
{
  "validation": {
    "benchmarks": [
      {
        "metric": "Login response time",
        "target": "< 200ms",
        "measurement_method": "k6 load test",
        "actual": null,
        "passed": null
      }
    ],
    "quality_gates": [
      {
        "gate": "Type Check",
        "requirement": "No type errors",
        "passed": null
      }
    ]
  }
}
```

### Files

```json
{
  "files": {
    "to_create": [
      "src/auth/LoginForm.tsx",
      "src/auth/authService.ts"
    ],
    "to_modify": [
      "src/App.tsx",
      "src/routes.ts"
    ]
  }
}
```

### Commits

```json
{
  "commits": [
    {
      "sha": "abc123def456",
      "message": "feat(auth): add login form",
      "timestamp": "2024-01-01T12:00:00Z"
    }
  ]
}
```

Used for rollback operations.

### Verification Evidence

```json
{
  "verification_evidence": {
    "screenshots": [
      ".aprd/evidence/F001/login-success.png"
    ],
    "test_output_logs": [
      ".aprd/evidence/F001/test_0_unit_tests.log"
    ],
    "verified_at": "2024-01-01T12:30:00Z",
    "verified_by": "verification_protocol"
  }
}
```

## Validation Summary

```json
{
  "validation_summary": {
    "total_features": 5,
    "total_tasks": 23,
    "estimated_complexity": "medium",
    "critical_path": ["F001", "F002", "F003"]
  }
}
```

| Field | Type | Required | Values |
|-------|------|----------|--------|
| `total_features` | integer | Yes | >= 1 |
| `total_tasks` | integer | Yes | >= 1 |
| `estimated_complexity` | string | Yes | `small`, `medium`, `large`, `xlarge` |
| `critical_path` | array[string] | No | Feature IDs in order |

## Status Transitions

### Feature Status Flow

```
pending → in_progress → completed → verified
                    ↘      ↓
                     blocked  failed
                        ↓
                     pending (after unblock/retry)
```

### Task Status Flow

```
pending → in_progress → completed
                    ↘
                     blocked → pending (after unblock)
```

## Validation

Trackers are validated against the JSON Schema at:
- Generation time
- Load time
- Save time

To validate manually:

```python
from tools.auto_prd.tracker_generator import validate_tracker

tracker = {...}
is_valid, errors = validate_tracker(tracker)
if not is_valid:
    print(f"Validation errors: {errors}")
```

## Example Complete Tracker

```json
{
  "version": "2.0.0",
  "metadata": {
    "prd_source": "prds/auth-feature.md",
    "prd_hash": "sha256:1234567890abcdef",
    "created_at": "2024-01-01T00:00:00Z",
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
      "name": "User Login",
      "description": "Implement secure user login with email/password",
      "priority": "critical",
      "complexity": "M",
      "status": "pending",
      "dependencies": [],
      "goals": {
        "primary": "Users can authenticate with email and password",
        "secondary": [],
        "measurable_outcomes": [
          "Login success rate > 99%",
          "Invalid credentials show appropriate error"
        ]
      },
      "tasks": [
        {
          "id": "T001",
          "description": "Create login form UI",
          "status": "pending"
        },
        {
          "id": "T002",
          "description": "Implement authentication API route",
          "status": "pending"
        }
      ],
      "acceptance_criteria": [
        {
          "id": "AC001",
          "criterion": "Valid credentials result in successful login",
          "verification_method": "e2e_test",
          "status": "pending"
        }
      ],
      "testing": {
        "unit_tests": [
          {
            "description": "Test password validation logic",
            "file_path": "src/auth/__tests__/validation.test.ts",
            "status": "pending"
          }
        ],
        "integration_tests": [],
        "e2e_tests": [
          {
            "scenario": "Successful login flow",
            "steps": [
              "Navigate to /login",
              "Enter valid credentials",
              "Submit form",
              "Verify redirect to /dashboard"
            ],
            "file_path": "e2e/auth/login.spec.ts",
            "status": "pending"
          }
        ]
      },
      "validation": {
        "benchmarks": [],
        "quality_gates": [
          {
            "gate": "Type Check",
            "requirement": "No TypeScript errors"
          },
          {
            "gate": "Lint Check",
            "requirement": "No ESLint errors"
          }
        ]
      },
      "files": {
        "to_create": [
          "src/app/login/page.tsx",
          "src/app/api/auth/login/route.ts"
        ],
        "to_modify": [
          "src/middleware.ts"
        ]
      },
      "commits": [],
      "verification_evidence": {}
    }
  ],
  "validation_summary": {
    "total_features": 1,
    "total_tasks": 2,
    "estimated_complexity": "medium",
    "critical_path": ["F001"]
  }
}
```
