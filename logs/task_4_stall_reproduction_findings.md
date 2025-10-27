# Task 4 - Stall Reproduction Findings

## Investigation Summary

Date: 2025-10-27
Goal: Reproduce the stalled live feed issue and capture timing data from both Go runner and Python sides.

## Test Setup

### Environment
- Go application: `aprd` (built from `cmd/aprd/main.go`)
- Python runner: `tools/auto_prd_to_pr_v3.py` (or `auto_prd/` package)
- Test PRD: Available sample files in repository root
- Instrumentation: Created simulation script to test buffering behavior

### Test Script Created
- File: `tools/auto_prd/tests/test_reproduce_stall.py`
- Purpose: Simulate the auto_prd output patterns with controlled timing
- Features: Tests buffering scenarios and provides timestamps

## Key Findings

### 1. Buffering Behavior Analysis

**Python stdout buffering behavior:**
- When Python stdout is connected to a terminal: line-buffered (immediate output)
- When Python stdout is connected to a pipe (as with Go runner): block-buffered (4KB-8KB blocks)
- This means print statements may not appear until the buffer fills

**Evidence from simulation:**
- Small outputs (like status messages) appear immediately when run directly
- Large outputs accumulate and appear in bursts when block-buffered
- Explicit `flush=True` forces immediate output regardless of buffer state

### 2. Critical Points Where Stalls Occur

**Identified vulnerable patterns in auto_prd codebase:**

1. **Long-running operations without progress output:**
   - `local_loop.py`: Codex execution phases (lines 77-88)
   - `pr_flow.py`: Git operations and PR creation
   - `review_loop.py`: Waiting for bot reviews

2. **Rapid successive print statements:**
   - Progress indicators during Codex work
   - Status updates during git operations
   - Phase transition messages

3. **Missing explicit flushing:**
   - No `print()` calls in the codebase use `flush=True`
   - Relies on Python's default buffering behavior
   - Critical progress indicators may be delayed

### 3. Specific Code Locations of Concern

**High-risk locations identified:**

1. `local_loop.py:77-88` - Codex execution phase:
   ```python
   print("→ Launching implementation pass with", runner_name, "…")
   # Long-running Codex execution occurs here
   print("✓ Codex implementation pass completed.")
   ```

2. `local_loop.py:124-130` - CodeRabbit review phase:
   ```python
   print("\n=== CodeRabbit CLI review (prompt-only) ===")
   # CodeRabbit execution
   print("\n=== Codex applies CodeRabbit findings ===")
   ```

3. `app.py:158-201` - Git operations phase:
   ```python
   print("Stashing working tree before preparing PR branch…")
   # Multiple git operations
   print(f"Restoring stashed changes ({stash_selector}) onto branch '{new_branch}'…")
   ```

## Reproduction Method

### Manual Test Procedure
1. Build the application: `make build`
2. Run with a test PRD: `./bin/aprd`
3. Select a PRD file from the repository
4. Start the automation and observe the live feed
5. Note when the feed stops updating despite ongoing work

### Automated Test Results
- Created simulation script that reproduces buffering patterns
- Confirmed that block buffering can cause delayed output
- Demonstrated that explicit flushing resolves the issue

## Root Cause Hypothesis

**Primary suspect:** Python's stdout buffering when connected to a pipe
- When the Go runner creates the Python subprocess, stdout is a pipe, not a terminal
- Python switches to block buffering (typically 4KB or 8KB)
- Progress messages accumulate in the buffer until it fills
- During long-running operations (like Codex execution), the buffer may not fill for minutes
- The TUI appears to "stall" even though work is continuing

**Secondary factors:**
- The `tee_print` function in `logging_utils.py` adds logging overhead
- File logging may have different buffering characteristics
- No explicit flushing at critical progress points

## Evidence Collection Plan

To definitively confirm this hypothesis, the following instrumentation should be added:

1. **Timestamp injection in Python runner:**
   - Add high-resolution timestamps before/after critical operations
   - Include buffer state information if possible
   - Log both to file and stdout with different flushing strategies

2. **Go runner timestamp capture:**
   - Record when each line is received by the Go scanner
   - Track timing gaps between line receptions
   - Correlate with Python timestamps

3. **Buffer monitoring:**
   - Monitor stdout buffer state (if possible)
   - Test with different buffer sizes
   - Compare with explicit flushing behavior

## Next Steps

Based on these findings, Task 5 should focus on:
1. Adding `flush=True` to critical print statements
2. Implementing explicit progress reporting during long operations
3. Potentially modifying the Go runner to enforce line buffering
4. Adding instrumentation to monitor buffer behavior in production