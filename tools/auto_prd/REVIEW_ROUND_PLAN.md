# Ralph Mode Review Round - Implementation Plan

## Overview

After each implementation round, a new independent agent instance should review what was done against the task requirements, determine if task statuses are correct, and add insights to guide the next implementation round.

## Current Flow Analysis

### Current Ralph Loop (readiness_loop.py)
```
┌─────────────────────────────────────────────────────────────────┐
│                    RALPH WIGGUM LOOP                             │
├─────────────────────────────────────────────────────────────────┤
│ 1. SCOPE_REVIEW    → Check if scope needs review                 │
│ 2. EXECUTING       → Run local_loop.py (implementation)          │
│ 3. VERIFYING       → Run verification gates                      │
│ 4. EVALUATING      → Check 7-signal convergence                  │
└─────────────────────────────────────────────────────────────────┘
```

### Current Local Loop (local_loop.py)
```
┌─────────────────────────────────────────────────────────────────┐
│                    LOCAL IMPLEMENTATION LOOP                     │
├─────────────────────────────────────────────────────────────────┤
│ For each iteration:                                              │
│   1. Implementation pass (Codex/Claude)                         │
│   2. Parse TASKS_LEFT from output                               │
│   3. CodeRabbit review (if changes detected)                    │
│   4. Fix pass (if findings detected)                            │
│   5. Update iteration summary                                   │
│   6. Check stall conditions                                     │
└─────────────────────────────────────────────────────────────────┘
```

### Current Tracker Status Tracking
- Tasks have status: `pending | in_progress | completed | blocked`
- Features have status: `pending | in_progress | blocked | completed | verified | failed`
- Acceptance criteria have status: `pending | passed | failed`
- **No review-specific tracking exists**

---

## Design: Review Round

### Where to Insert

The review round should run **after implementation/fix but before the next iteration's implementation**:

```
┌─────────────────────────────────────────────────────────────────┐
│                    NEW LOCAL LOOP FLOW                           │
├─────────────────────────────────────────────────────────────────┤
│ For each iteration:                                              │
│   1. Implementation pass (Codex/Claude)                         │
│   2. Parse TASKS_LEFT from output                               │
│   3. CodeRabbit review (if changes detected)                    │
│   4. Fix pass (if findings detected)                            │
│   5. ⭐ REVIEW ROUND (NEW)                                      │
│   6. Update iteration summary                                   │
│   7. Check stall conditions                                     │
└─────────────────────────────────────────────────────────────────┘
```

### Review Round Responsibilities

1. **Review What Was Done**
   - Read the task/feature requirements from tracker.json
   - Examine git diff to see what actually changed
   - Compare implementation against requirements

2. **Validate Task Statuses**
   - Check if tasks marked "completed" are actually complete
   - Check if tasks marked "in_progress" have made progress
   - Identify any incorrectly completed tasks (revert to in_progress)
   - Identify any completed tasks not marked as such (mark as completed)

3. **Generate Review Insights**
   - List what went well (patterns to reinforce)
   - List what went wrong (issues to fix)
   - Suggest specific next steps for the next implementation round
   - Add insights to tracker for next agent

---

## Data Model Changes

### 1. New Field in Task Object

```json
{
  "id": "T001",
  "description": "Implement user authentication",
  "status": "completed",
  "completed_at": "2025-01-24T10:00:00Z",
  "review_insights": [
    {
      "iteration": 1,
      "reviewer": "claude-review",
      "status": "confirmed",  // confirmed | reverted | partial
      "notes": "Implementation complete but missing error handling",
      "next_steps": ["Add validation for invalid credentials"]
    }
  ]
}
```

### 2. New Field in Feature Object

```json
{
  "id": "F001",
  "name": "User Authentication",
  "status": "in_progress",
  "review_history": [
    {
      "iteration": 1,
      "reviewer": "claude-review",
      "overall_assessment": "partial",
      "tasks_reviewed": 3,
      "tasks_confirmed": 2,
      "tasks_reverted": 1,
      "findings": [
        "T002 marked complete but login form is missing",
        "Good progress on T001 (backend auth)"
      ]
    }
  ]
}
```

### 3. New Top-Level Section in Tracker

```json
{
  "version": "2.0.0",
  "metadata": {...},
  "features": [...],
  "validation_summary": {...},
  "review_insights": {
    "last_review_iteration": 1,
    "common_patterns": [],
    "recurring_issues": []
  }
}
```

---

## Architecture

### New Module: `review_round.py`

```python
# tools/auto_prd/review_round.py

@dataclass
class ReviewConfig:
    """Configuration for review round."""
    enabled: bool = True
    executor: str = "claude"  # claude | codex
    model: str = "claude-sonnet-4-5-20250514"
    max_review_time: int = 300  # seconds


@dataclass
class ReviewResult:
    """Result of a review round."""
    iteration: int
    reviewer: str
    timestamp: str
    overall_status: str  # passed | failed | partial
    tasks_reviewed: int
    statuses_updated: dict[str, str]  # task_id -> new_status
    insights: list[str]
    next_steps: list[str]
    git_diff_summary: str


class ReviewRound:
    """Orchestrates the review round after implementation."""

    def __init__(
        self,
        repo_root: Path,
        config: ReviewConfig | None = None,
    ):
        self.repo_root = Path(repo_root)
        self.config = config or ReviewConfig()

    def execute_review(
        self,
        iteration: int,
        tracker: dict[str, Any],
        base_branch: str,
    ) -> ReviewResult:
        """Execute the review round.

        1. Get git diff since last iteration
        2. Build review prompt with:
           - Task/feature requirements
           - Git diff
           - Current tracker state
        3. Call reviewer agent (fresh instance)
        4. Parse review result
        5. Update tracker with insights
        6. Return result
        """

    def build_review_prompt(
        self,
        tracker: dict[str, Any],
        git_diff: str,
        iteration: int,
    ) -> str:
        """Build the review prompt for the agent."""

    def parse_review_result(
        self,
        agent_output: str,
    ) -> ReviewResult:
        """Parse structured output from review agent."""

    def apply_review_updates(
        self,
        tracker: dict[str, Any],
        result: ReviewResult,
    ) -> dict[str, Any]:
        """Apply status updates and insights to tracker."""
```

### Integration Point: `local_loop.py`

Insert after fix pass completion (around line 604):

```python
# After fix pass, before stall detection
if ralph.enabled and ralph.enable_review_round:
    from .review_round import ReviewRound, ReviewConfig

    review_config = ReviewConfig(
        executor=runner_name,
        model=codex_model if runner is codex_exec else None,
    )
    review_round = ReviewRound(repo_root, review_config)

    print("\n=== Review Round: Validating implementation ===", flush=True)
    review_result = review_round.execute_review(
        iteration=i,
        tracker=tracker,
        base_branch=base_branch,
    )

    print(f"  Review result: {review_result.overall_status}")
    print(f"  Tasks reviewed: {review_result.tasks_reviewed}")
    print(f"  Statuses updated: {len(review_result.statuses_updated)}")

    # Reload tracker after review updates
    tracker = load_tracker(repo_root)

    # Track review stats for stall detection
    if review_result.statuses_updated:
        # If statuses were reverted, we made backward progress
        reverted_count = sum(
            1 for s in review_result.statuses_updated.values()
            if s in ("pending", "in_progress")
        )
        if reverted_count > 0:
            # Adjust tasks_left to reflect reverted tasks
            if tasks_left is not None:
                tasks_left += reverted_count
```

### Integration Point: `readiness_loop.py`

Add review phase after execution (optional, for outer loop):

```python
def _handle_execution_with_review(self, tracker: dict[str, Any]) -> None:
    """Handle execution phase with embedded review round."""
    # Run execution (local_loop)
    # After completion, run outer-level review
```

---

## Review Agent Prompt Template

```python
REVIEW_PROMPT = """# Task: Review Implementation Round

You are a senior code reviewer conducting an impartial review of an implementation round.
Your goal is to validate that claimed work matches actual changes and provide actionable feedback.

## Context

- **Iteration**: {iteration}
- **Base Branch**: {base_branch}
- **Git SHA**: {git_sha}

## Tasks/Features to Review

{tasks_to_review}

## Current Tracker State

{tracker_summary}

## Git Diff (What Actually Changed)

```diff
{git_diff}
```

## Your Responsibilities

### 1. Validate Task Statuses

For each task marked "completed":
- Does the git diff show implementation of this task?
- Are all acceptance criteria met?
- Should status remain "completed" or revert to "in_progress"?

For each task marked "in_progress":
- Is there evidence of progress in the diff?
- Should it be marked "completed" instead?

### 2. Generate Review Insights

**What went well** (patterns to reinforce):
- Implementation patterns that should continue
- Good test coverage, documentation, etc.

**What went wrong** (issues to fix):
- Missing or incomplete implementations
- Tasks marked complete but not actually done
- Code quality issues

**Next steps** (specific actions):
- Concrete steps for the next implementation round
- Priority ordering of remaining work

## Output Format

Respond with a JSON object (no markdown, no explanation):

```json
{{
  "overall_assessment": "passed|partial|failed",
  "tasks_reviewed": [
    {{
      "task_id": "T001",
      "current_status": "completed",
      "recommended_status": "completed|in_progress|pending",
      "reasoning": "Why this status is recommended",
      "findings": "Specific observations from git diff"
    }}
  ],
  "insights": {{
    "positive": ["What went well"],
    "negative": ["What went wrong"],
    "patterns": ["Patterns observed"]
  }},
  "next_steps": ["Specific next step 1", "Specific next step 2"],
  "summary": "One-line summary of review"
}}
```

Begin your review now.
"""
```

---

## Configuration

### Ralph Settings Extension

```python
# tools/auto_prd/ralph.py

@dataclass
class RalphSettings:
    enabled: bool = False
    show_guardrails: bool = True
    auto_add_signs: bool = True
    stall_no_output_seconds: int | None = 180
    stall_no_progress_iterations: int | None = 3

    # NEW: Review round settings
    enable_review_round: bool = True
    review_round_model: str = "claude-sonnet-4-5-20250514"
    review_round_timeout: int = 300
    review_round_after_fix: bool = True  # Run after fix pass
```

### TUI Integration

```go
// internal/config/config.go

type RalphConfig struct {
    Enabled             bool   `yaml:"enabled"`
    ShowGuardrails      bool   `yaml:"show_guardrails"`
    AutoAddSigns        bool   `yaml:"auto_add_signs"`
    StallNoOutput       *int   `yaml:"stall_no_output_seconds"`
    StallNoProgress     *int   `yaml:"stall_no_progress_iterations"`

    // Review round settings (NEW)
    EnableReviewRound   bool   `yaml:"enable_review_round"`
    ReviewRoundModel    string `yaml:"review_round_model"`
    ReviewRoundTimeout  int    `yaml:"review_round_timeout"`
}
```

---

## Tracker Schema Update

Update `tracker_schema.json` to include new fields:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "tracker_schema.json",
  "title": "AutoDev PRD Tracker",
  "type": "object",
  "required": ["version", "metadata", "features", "validation_summary"],
  "properties": {
    "version": {"type": "string", "pattern": "^2\\.0\\.1$"},  // Bump version
    "metadata": {...},
    "features": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "id": {...},
          "name": {...},
          "status": {...},
          "tasks": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "id": {...},
                "description": {...},
                "status": {...},
                "completed_at": {...},
                "review_insights": {  // NEW
                  "type": "array",
                  "items": {
                    "type": "object",
                    "properties": {
                      "iteration": {"type": "integer"},
                      "reviewer": {"type": "string"},
                      "status": {"type": "string", "enum": ["confirmed", "reverted", "partial"]},
                      "notes": {"type": "string"},
                      "next_steps": {"type": "array", "items": {"type": "string"}}
                    }
                  }
                }
              }
            }
          },
          "review_history": {  // NEW
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "iteration": {"type": "integer"},
                "reviewer": {"type": "string"},
                "overall_assessment": {"type": "string", "enum": ["passed", "partial", "failed"]},
                "tasks_reviewed": {"type": "integer"},
                "tasks_confirmed": {"type": "integer"},
                "tasks_reverted": {"type": "integer"},
                "findings": {"type": "array", "items": {"type": "string"}}
              }
            }
          }
        }
      }
    },
    "review_insights": {  // NEW - top level
      "type": "object",
      "properties": {
        "last_review_iteration": {"type": "integer"},
        "common_patterns": {"type": "array", "items": {"type": "string"}},
        "recurring_issues": {"type": "array", "items": {"type": "string"}}
      }
    }
  }
}
```

---

## Implementation Steps

### Phase 1: Core Review Module
1. Create `tools/auto_prd/review_round.py`
2. Implement `ReviewConfig`, `ReviewResult`, `ReviewRound` classes
3. Implement `build_review_prompt()` with JSON output format
4. Implement `parse_review_result()` with robust JSON extraction
5. Implement `apply_review_updates()` for tracker updates

### Phase 2: Tracker Schema Updates
1. Bump tracker version to `2.0.1`
2. Add `review_insights` field to task schema
3. Add `review_history` field to feature schema
4. Add top-level `review_insights` section
5. Update validation functions

### Phase 3: Local Loop Integration
1. Add `enable_review_round` to `RalphSettings`
2. Insert review round call after fix pass in `local_loop.py`
3. Update iteration summary to include review results
4. Handle status reverts (adjust tasks_left)

### Phase 4: Readiness Loop Integration
1. Add review statistics to `ReadinessStats`
2. Include review insights in scope review context
3. Display review history in evaluation phase

### Phase 5: TUI Configuration
1. Add review round settings to TUI Settings tab
2. Add review round toggle in Env tab (like other Ralph settings)
3. Update YAML config schema

### Phase 6: Testing
1. Unit tests for `ReviewRound` class
2. Integration tests for review round in local loop
3. Mock agent responses for testing
4. Test status revert scenarios

---

## Success Criteria

1. **After each implementation round:**
   - Review agent runs independently
   - Validates task statuses against git diff
   - Updates tracker with review insights

2. **Task status accuracy:**
   - Tasks not actually implemented are reverted to in_progress/pending
   - Tasks that are complete but not marked get marked as completed
   - Next implementation agent gets accurate state

3. **Insight quality:**
   - Review provides specific next steps
   - Common patterns are tracked across iterations
   - Recurring issues are identified

4. **No increase in stall rate:**
   - Review round timeout is configurable
   - Failed reviews don't cause stalls
   - Review is skipped if no changes detected

---

## Open Questions

1. **Executor choice**: Should review use the same executor as implementation or always use Claude?
   - **Recommendation**: Configurable, default to Claude for better reasoning

2. **Scope**: Should review cover all tasks or just those modified in this iteration?
   - **Recommendation**: Review all "in_progress" and recently "completed" tasks

3. **Failure handling**: What if review agent fails (timeout, error)?
   - **Recommendation**: Log warning, continue loop, record review failure in insights

4. **Idempotency**: Should review run if no git changes?
   - **Recommendation**: Skip review if no changes detected

5. **Tracker version**: Bump to 2.1.0 or 2.0.1?
   - **Recommendation**: 2.1.0 (adds significant new functionality)
