# Tracker Generation Robustness Plan

## Problem Statement

The tracker generation system fails silently when an agent (Codex/Claude) returns an empty response, producing the error:

```
Warning: Tracker generation failed: Agent returned invalid JSON: Expecting value: line 1 column 1 (char 0)
```

This error indicates `json.loads("")` was called with an empty string, meaning the agent CLI returned no stdout.

---

## Error Chain Analysis

```
codex/claude CLI → run_cmd() → codex_exec()/claude_exec() → generate_tracker() → _extract_json_from_response() → json.loads() → ValueError
```

When the agent CLI returns **empty stdout**, the chain produces:

| Step | Input | Output | Problem |
|------|-------|--------|---------|
| `run_cmd()` | CLI command | `("", stderr, 0)` | Success with empty output |
| `codex_exec()` | stdout | `""` | Discards stderr |
| `_extract_json_from_response()` | `""` | `""` | No validation |
| `json.loads()` | `""` | `ValueError` | "char 0" error |

---

## Root Causes of Empty Agent Output

| Cause | Exit Code | Stdout | Stderr | Current Handling |
|-------|-----------|--------|--------|------------------|
| Rate limiting | 0 | Empty | Error message | ❌ stderr discarded |
| Auth failure | Non-0 | Empty | Error message | ✅ CalledProcessError |
| Network issues | Timeout | N/A | N/A | ⚠️ TimeoutExpired raised |
| Context too large | 0 | Empty/truncated | Warning | ❌ No validation |
| Agent timeout | Kill signal | Empty | N/A | ⚠️ TimeoutExpired raised |
| Empty model response | 0 | Empty | Empty | ❌ No validation |

---

## Existing Infrastructure (Underutilized)

The codebase has mature infrastructure that is not being used for tracker generation:

### 1. Structured Error System (`auto_prd/errors.py`)

```python
class ErrorCategory(str, Enum):
    NETWORK = "network"
    API = "api"           # Rate limits
    RUNNER = "runner"     # Codex/Claude failures
    TIMEOUT = "timeout"
    # ...

def classify_error(error, operation, phase) -> StructuredError:
    # Auto-classifies errors with recovery hints
```

### 2. Policy Fallback Runner (`auto_prd/policy.py:108`)

```python
def policy_fallback_runner(
    command_name: str,
    policy: str,
    executor_factory: Callable,
    verify: Callable | None = None,
) -> str:
    # Retries with fallback to different executors
```

### 3. Command Retry Logic (`auto_prd/command.py:341`)

```python
def run_cmd(
    cmd,
    retries: int = 0,           # Not used for tracker
    retry_on_codes: set = None,
    retry_on_stderr: list = None,
    backoff_base: float = 1.0,
    backoff_max: float = 60.0,
):
```

---

## Vulnerability Points

### 1. `_extract_json_from_response()` - No Input Validation

**File:** `tools/auto_prd/tracker_generator.py:569`

```python
def _extract_json_from_response(response: str) -> str:
    text = response.strip()              # Empty → ""
    # ... markdown handling ...
    brace_start = text.find("{")         # Empty → -1
    if brace_start >= 0:                 # Skipped for empty
        # brace matching logic
    return text                          # Returns "" silently!
```

**Issue:** No validation, returns empty string silently.

### 2. Agent Executors Discard stderr

**File:** `tools/auto_prd/agents.py:102,283`

```python
out, _, _ = run_cmd(...)  # stderr discarded
return out
```

**Issue:** Rate limit and error messages are lost.

### 3. No Retry Mechanism for Tracker Generation

**File:** `tools/auto_prd/app.py:353`

```python
tracker = generate_tracker(...)  # Single attempt, no fallback
```

**Issue:** Transient failures cause complete failure.

---

## Implementation Plan

### Phase 1: Input Validation (Quick Wins)

#### 1.1 Validate Agent Response Before JSON Extraction

**File:** `tools/auto_prd/tracker_generator.py`

**Location:** Before line 747

```python
# Validate response is not empty before extraction
if not result or not result.strip():
    logger.error("Agent (%s) returned empty response", executor)
    raise ValueError(
        f"Agent ({executor}) returned empty response. "
        "This may indicate rate limiting, authentication issues, or network problems. "
        "Check agent CLI configuration and API status."
    )
```

#### 1.2 Improve `_extract_json_from_response()` Error Handling

**File:** `tools/auto_prd/tracker_generator.py:569`

```python
def _extract_json_from_response(response: str) -> str:
    """Extract JSON from agent response, handling markdown code blocks.

    Args:
        response: Raw response from agent

    Returns:
        Extracted JSON string

    Raises:
        ValueError: If response is empty or contains no JSON
    """
    text = response.strip()

    # Validate input
    if not text:
        raise ValueError("Empty response from agent - cannot extract JSON")

    # Try to find JSON in markdown code block
    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        if end > start:
            text = text[start:end].strip()
    elif "```" in text:
        start = text.find("```") + 3
        end = text.find("```", start)
        if end > start:
            text = text[start:end].strip()

    # Find the actual JSON object
    brace_start = text.find("{")
    if brace_start < 0:
        # Log preview of what we received for debugging
        preview = text[:200] + "..." if len(text) > 200 else text
        raise ValueError(
            f"No JSON object found in response. "
            f"Response preview: {preview}"
        )

    # Find matching closing brace
    depth = 0
    for i, char in enumerate(text[brace_start:], start=brace_start):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[brace_start : i + 1]

    # Unbalanced braces
    raise ValueError("Unbalanced braces in JSON response - incomplete output")
```

#### 1.3 Log stderr When stdout Is Empty

**File:** `tools/auto_prd/agents.py`

**For `codex_exec()` (around line 102):**

```python
out, stderr, returncode = run_cmd(
    args,
    cwd=repo_root,
    check=True,
    stdin=prompt,
    timeout=get_codex_exec_timeout(),
)

# Log warning if stdout is empty but stderr has content
if not out.strip() and stderr.strip():
    logger.warning(
        "Codex returned empty stdout. Stderr content: %s",
        stderr[:500] if len(stderr) > 500 else stderr
    )

return out, stderr
```

**For `claude_exec()` (around line 283):** Apply same pattern.

---

### Phase 2: Retry & Fallback

#### 2.1 Add Retry Logic to Tracker Generation

**File:** `tools/auto_prd/tracker_generator.py`

**Add at module level:**

```python
import time

MAX_TRACKER_GEN_ATTEMPTS = 3
TRACKER_GEN_RETRY_BACKOFF_BASE = 10  # seconds
```

**Modify `generate_tracker()` around line 728:**

```python
# Call agent with retry logic
logger.info("Sending PRD to %s for analysis...", executor)

last_error = None
for attempt in range(MAX_TRACKER_GEN_ATTEMPTS):
    try:
        if executor == "codex":
            result = codex_exec(
                prompt=prompt,
                repo_root=repo_root,
                allow_unsafe_execution=allow_unsafe_execution,
                dry_run=dry_run,
            )
        else:
            result = claude_exec(
                prompt=prompt,
                repo_root=repo_root,
                allow_unsafe_execution=allow_unsafe_execution,
                dry_run=dry_run,
            )

        # Validate response before proceeding
        if not result or not result.strip():
            raise ValueError(f"Empty response from {executor}")

        # If we get here, we have a valid response
        break

    except (ValueError, RuntimeError) as e:
        last_error = e
        if attempt < MAX_TRACKER_GEN_ATTEMPTS - 1:
            wait_time = TRACKER_GEN_RETRY_BACKOFF_BASE * (2 ** attempt)
            logger.warning(
                "Tracker generation attempt %d/%d failed: %s. Retrying in %ds...",
                attempt + 1,
                MAX_TRACKER_GEN_ATTEMPTS,
                e,
                wait_time,
            )
            time.sleep(wait_time)
        else:
            logger.error(
                "Tracker generation failed after %d attempts: %s",
                MAX_TRACKER_GEN_ATTEMPTS,
                e,
            )
            raise
```

#### 2.2 Use `policy_fallback_runner()` for Executor Fallback

**File:** `tools/auto_prd/tracker_generator.py`

**Add new function:**

```python
from .policy import policy_fallback_runner, get_executor_policy

def generate_tracker_with_fallback(
    prd_path: Path,
    repo_root: Path,
    policy: str | None = None,
    force: bool = False,
    dry_run: bool = False,
    allow_unsafe_execution: bool = True,
) -> dict[str, Any]:
    """Generate tracker with automatic executor fallback on failure.

    Uses policy_fallback_runner to try alternate executors if the
    primary executor fails.

    Args:
        prd_path: Path to the PRD markdown file
        repo_root: Repository root directory
        policy: Executor policy (defaults to environment/config)
        force: Regenerate even if current tracker exists
        dry_run: If True, skip actual agent execution
        allow_unsafe_execution: Allow unsafe execution mode

    Returns:
        The generated/loaded tracker dictionary

    Raises:
        RuntimeError: If all executor attempts fail
    """
    effective_policy = policy or get_executor_policy()

    def executor_factory(current_policy: str):
        # Determine executor from policy
        if "codex" in current_policy and "only" in current_policy:
            executor = "codex"
        elif "claude" in current_policy:
            executor = "claude"
        else:
            # codex-first: try codex
            executor = "codex"

        def run_generation():
            return generate_tracker(
                prd_path=prd_path,
                repo_root=repo_root,
                executor=executor,
                force=force,
                dry_run=dry_run,
                allow_unsafe_execution=allow_unsafe_execution,
            )

        return run_generation

    def verify_tracker(tracker: dict) -> bool:
        """Verify tracker is valid."""
        return (
            isinstance(tracker, dict)
            and tracker.get("version") == TRACKER_VERSION
            and len(tracker.get("features", [])) > 0
        )

    return policy_fallback_runner(
        command_name="tracker_generation",
        policy=effective_policy,
        executor_factory=executor_factory,
        verify=verify_tracker,
    )
```

---

### Phase 3: Enhanced Error Classification

#### 3.1 Use Structured Errors for Diagnostics

**File:** `tools/auto_prd/tracker_generator.py`

**Modify exception handling around line 750:**

```python
from .errors import classify_error, ErrorCategory

try:
    tracker = json.loads(json_str)
except json.JSONDecodeError as e:
    # Classify the error for better diagnostics
    structured = classify_error(
        e,
        operation="tracker_json_parse",
        phase="initialization",
    )

    logger.error(
        "Tracker JSON parse failed. Category: %s, Retryable: %s, Hint: %s",
        structured.category.value,
        structured.retryable,
        structured.recovery_hint or "Check agent output format",
    )

    # Include response preview in error message
    preview = result[:500] + "..." if len(result) > 500 else result
    logger.debug("Raw response that failed to parse: %s", preview)

    raise ValueError(
        f"Agent returned invalid JSON: {e}. "
        f"Response preview: {json_str[:100]}..."
    ) from e
```

#### 3.2 Add Error Patterns for Tracker Failures

**File:** `tools/auto_prd/errors.py`

**Add to `ERROR_PATTERNS[ErrorCategory.RUNNER]`:**

```python
ErrorCategory.RUNNER: [
    # ... existing patterns ...
    "empty response",
    "no JSON found",
    "invalid tracker",
    "tracker generation failed",
    "Unbalanced braces",
],
```

**Add to `RECOVERY_HINTS`:**

```python
RECOVERY_HINTS: dict[str, str] = {
    # ... existing hints ...
    "empty response": "Agent returned no output - check API rate limits and authentication",
    "no JSON found": "Agent output was not valid JSON - may need to retry or adjust prompt",
    "Unbalanced braces": "Agent output was truncated - context may be too large",
}
```

---

### Phase 4: Test Coverage

#### 4.1 Add Unit Tests for Edge Cases

**File:** `tools/auto_prd/tests/test_tracker_generator.py`

> **Note:** The actual implementation uses `unittest.TestCase` with methods like
> `self.assertRaises`, `self.assertEqual`, etc. The examples below reflect this.

```python
"""Tests for tracker_generator module edge cases."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from auto_prd.tracker_generator import (
    _extract_json_from_response,
    generate_tracker,
    TRACKER_VERSION,
)


class ExtractJsonFromResponseTests(unittest.TestCase):
    """Tests for _extract_json_from_response function."""

    def test_empty_response_raises_value_error(self) -> None:
        """Empty string should raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            _extract_json_from_response("")
        self.assertIn("Empty response", str(ctx.exception))

    def test_whitespace_only_raises_value_error(self) -> None:
        """Whitespace-only string should raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            _extract_json_from_response("   \n\t  ")
        self.assertIn("Empty response", str(ctx.exception))

    def test_no_json_object_raises_value_error(self) -> None:
        """Response without JSON object should raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            _extract_json_from_response("Error: rate limit exceeded")
        self.assertIn("No JSON object", str(ctx.exception))

    def test_unbalanced_braces_raises_value_error(self) -> None:
        """Truncated JSON should raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            _extract_json_from_response('{"version": "2.0.0", "features": [')
        self.assertIn("Unbalanced braces", str(ctx.exception))

    def test_valid_json_extracted(self) -> None:
        """Valid JSON should be extracted correctly."""
        response = '{"version": "2.0.0"}'
        result = _extract_json_from_response(response)
        self.assertEqual(result, '{"version": "2.0.0"}')

    def test_json_in_markdown_code_block(self) -> None:
        """JSON in markdown code block should be extracted."""
        response = """Here is the tracker:
```json
{"version": "2.0.0"}
```
"""
        result = _extract_json_from_response(response)
        self.assertEqual(result, '{"version": "2.0.0"}')

    def test_json_with_surrounding_text(self) -> None:
        """JSON with surrounding text should be extracted."""
        response = 'Here is the output: {"version": "2.0.0"} End of output.'
        result = _extract_json_from_response(response)
        self.assertEqual(result, '{"version": "2.0.0"}')


class GenerateTrackerRetryTests(unittest.TestCase):
    """Tests for generate_tracker retry behavior."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.repo_root = Path(self.temp_dir)
        self.prd_path = self.repo_root / "test.md"
        self.prd_path.write_text("# Test PRD\n\n- [ ] Task 1")

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir)

    @patch("auto_prd.tracker_generator.codex_exec")
    @patch("auto_prd.tracker_generator.time.sleep")
    def test_retries_on_empty_response(
        self, mock_sleep: MagicMock, mock_codex: MagicMock
    ) -> None:
        """Should retry when agent returns empty response."""
        import json

        valid_tracker = {
            "version": TRACKER_VERSION,
            "metadata": {
                "prd_source": str(self.prd_path),
                "prd_hash": "sha256:abc123",
                "created_at": "2024-01-01T00:00:00Z",
                "created_by": "codex",
            },
            "features": [
                {
                    "id": "F001",
                    "name": "Test",
                    "description": "Test description",
                    "priority": "medium",
                    "complexity": "S",
                    "status": "pending",
                    "dependencies": [],
                    "goals": {
                        "primary": "Test",
                        "secondary": [],
                        "measurable_outcomes": [],
                    },
                    "tasks": [
                        {"id": "T001", "description": "Test", "status": "pending"}
                    ],
                    "acceptance_criteria": [
                        {
                            "id": "AC001",
                            "criterion": "Test",
                            "verification_method": "unit_test",
                            "status": "pending",
                        }
                    ],
                    "testing": {"unit_tests": [], "integration_tests": []},
                    "validation": {"benchmarks": [], "quality_gates": []},
                    "files": {"to_create": [], "to_modify": []},
                    "commits": [],
                    "verification_evidence": {},
                }
            ],
            "validation_summary": {
                "total_features": 1,
                "total_tasks": 1,
                "estimated_complexity": "small",
            },
        }

        # First two calls return empty, third succeeds (return tuples of stdout, stderr)
        mock_codex.side_effect = [("", ""), ("", ""), (json.dumps(valid_tracker), "")]

        result = generate_tracker(
            prd_path=self.prd_path,
            repo_root=self.repo_root,
            executor="codex",
            allow_unsafe_execution=True,
        )

        self.assertEqual(mock_codex.call_count, 3)
        self.assertEqual(result["version"], TRACKER_VERSION)

    @patch("auto_prd.tracker_generator.codex_exec")
    @patch("auto_prd.tracker_generator.time.sleep")
    def test_fails_after_max_retries(
        self, mock_sleep: MagicMock, mock_codex: MagicMock
    ) -> None:
        """Should fail after exhausting retries."""
        mock_codex.return_value = ("", "")  # Always empty (stdout, stderr tuple)

        with self.assertRaises(ValueError) as ctx:
            generate_tracker(
                prd_path=self.prd_path,
                repo_root=self.repo_root,
                executor="codex",
                allow_unsafe_execution=True,
            )

        self.assertIn("Empty response", str(ctx.exception))
        self.assertEqual(mock_codex.call_count, 3)  # MAX_TRACKER_GEN_ATTEMPTS


if __name__ == "__main__":
    unittest.main()
```

---

## Implementation Priority

| Priority | Change | File(s) | Effort | Impact | Status |
|----------|--------|---------|--------|--------|--------|
| **P0** | Validate empty response before JSON parse | `tracker_generator.py` | Low | High | ✅ Done |
| **P0** | Improve `_extract_json_from_response()` errors | `tracker_generator.py` | Low | High | ✅ Done |
| **P1** | Log stderr when stdout is empty | `agents.py` | Low | Medium | ✅ Done |
| **P1** | Add retry logic with exponential backoff | `tracker_generator.py` | Medium | High | ✅ Done |
| **P2** | Use `policy_fallback_runner()` | `tracker_generator.py` | Medium | Medium | ⏳ Pending |
| **P2** | Add structured error classification | `tracker_generator.py`, `errors.py` | Medium | Medium | ✅ Done (errors.py patterns) |
| **P3** | Add comprehensive test coverage | `tests/test_tracker_generator.py` | Medium | Medium | ✅ Done |

---

## Success Criteria

After implementation:

1. ✅ **Empty responses detected early** with clear error message
2. ✅ **Transient failures recovered** via automatic retry (up to 3 attempts)
3. ✅ **Rate limiting handled** by detecting stderr messages and backing off
4. ⏳ **Executor fallback available** when primary executor fails consistently (P2 - pending)
5. ✅ **Test coverage** for all edge cases (empty, truncated, invalid responses)
6. ✅ **Structured logging** for debugging failed attempts

---

## Rollout Plan

1. **Phase 1** (Week 1): Deploy input validation changes
   - Low risk, immediate improvement
   - Monitor for new error patterns in logs

2. **Phase 2** (Week 2): Add retry logic
   - Test with `dry_run=True` first
   - Validate backoff timing is appropriate

3. **Phase 3** (Week 3): Integrate structured errors
   - Requires coordination with error logging system
   - Add dashboard/alerting for error categories

4. **Phase 4** (Ongoing): Expand test coverage
   - Add tests as new edge cases discovered
   - Integration tests for full retry/fallback paths
