# Ralph Mode - Autonomous Iteration

## Overview

Ralph mode is an autonomous iteration feature that helps AI agents learn from their mistakes and avoid repeating them. Named after Ralph Wiggum from The Simpsons (via Ryan Carson's "Ralph" technique), it emphasizes learning through experience and maintaining clean context.

**Key Benefits:**
- **Reduced repeated mistakes** - Guardrails prevent the same error from occurring twice
- **Better long-running sessions** - Progress tracking provides visibility into iteration history
- **Stall recovery** - Gutter detection detects when the agent is stuck and takes action
- **Context hygiene** - Fresh context per iteration prevents "conversation rot"

**When to use Ralph mode:**
- Large PRDs with multiple user stories (10+ stories)
- Complex codebases where mistakes are costly
- Multi-iteration tasks where learning from errors is critical
- Long-running automation sessions that may get stuck

**Current State:** Ralph mode is **production-ready** with three fully implemented features (Guardrails, Progress Tracking, Gutter Detection). Additional features are planned for future releases.

## Ralph Mode Concepts

### Context Hygiene

AI agents can develop "conversation rot" when the same context accumulates across iterations, leading to repeated mistakes and degraded performance. Ralph mode maintains context hygiene by:

- Starting each iteration with fresh context from the PRD
- Externalizing state to files (not chat memory)
- Injecting only relevant guardrails, not entire conversation history

This approach ensures each iteration starts clean, with only the most important lessons learned from previous mistakes.

### Guardrails (Mistake Prevention)

Guardrails use a "signs" pattern: when a mistake occurs, a **sign** is created that describes what went wrong and how to avoid it. These signs are stored per-repository and injected into the agent's context each iteration.

**Example sign:**
```markdown
## sign: check_imports_before_using
- **Trigger**: Adding a new import statement
- **Instruction**: Check if import already exists and verify the module is available
- **Added**: Iteration 3
- **File**: src/main.py
- **Category**: import
- **Phase**: local
```

The agent sees this sign and avoids making the same mistake again.

### Progress Tracking

Each iteration records:
- **Status** - `completed`, `completed_with_warnings`, `failed`
- **Files changed** - List of modified files
- **Learnings** - Insights from code reviews (e.g., "Clean code: 1 reviews without findings")
- **Issues found** - Problems detected during the iteration
- **Tasks completed/remaining** - Story IDs finished vs. total left
- **Commits made** - Number of git commits

This history provides visibility into what's working and what isn't.

### Gutter Detection

Sometimes agents get stuck in a "gutter" - making no progress or producing no output. Gutter detection monitors two conditions:

1. **No output timeout** - No output from the agent for N seconds (default: 180s)
2. **No progress iterations** - N consecutive iterations without task completion (default: 3)

When either threshold is exceeded, Ralph mode can:
- Automatically add a guardrail sign to prevent future stalls
- Log the stall for analysis
- Help the agent recover

## Features

### Implemented Features (Current Version)

✅ **Guardrails (Phase 1)** - Sign creation, storage, loading, and injection into agent context
✅ **Progress Tracking (Phase 3)** - Iteration summaries with learnings, issues, and task tracking
✅ **Gutter Detection (Phase 4)** - Stall detection with configurable thresholds and auto-add signs

### Planned Features (Future)

⏸️ **Pattern Discovery (Phase 2)** - Automatic discovery of recurring mistake patterns
⏸️ **Context Rotation (Phase 3)** - Rotate context every N iterations to prevent bloat
⏸️ **Task Selection (Phase 6)** - Intelligent task prioritization based on progress
⏸️ **Idempotency (Phase 7)** - Ensure repeated operations are safe and predictable

See [Ralph Integration Plan](ralph-integration-plan.md) for technical details on planned features.

## Quick Start

### Step 1: Enable Ralph Mode

#### Via TUI (Recommended)

1. Open aprd TUI (`./bin/aprd`)
2. Navigate to **Settings** tab
3. Find **"Ralph (Autonomous Mode)"** section
4. Set **"Enabled"** to `true`
5. Adjust other settings (see [Configuration](#configuration) below)
6. Save and return to **Run** tab

#### Via YAML Config

Edit `~/.config/aprd/config.yaml`:

```yaml
ralph:
  enabled: true
  auto_add_signs: true
  show_guardrails: true
  show_progress_log: true
  gutter_output_timeout_sec: 180
  gutter_no_progress_iters: 3
```

### Step 2: Run Automation

- Run automation as normal from **Run** tab
- Ralph mode operates transparently in the background
- No changes to your workflow needed

### Step 3: View Outputs

- **Guardrails** displayed on startup (if `show_guardrails=true`)
- **Progress log** displayed at end (if `show_progress_log=true`)
- **Guardrails file:** `~/.config/aprd/guardrails/<repo>.md`
- **Progress files:** `~/.config/aprd/progress/<session>.jsonl`

## Configuration

### TUI Settings Reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| **Enabled** | boolean | `false` | Enable all Ralph features |
| **Context Rotate Every** | int | `0` | Rotate context every N iterations (0 = disabled, planned feature) |
| **Max Consecutive Failures** | int | `3` | Gutter detection: iterations without progress before stall |
| **Auto Add Signs** | boolean | `true` | Automatically add guardrails on failures |
| **Show Progress Log** | boolean | `false` | Print progress summary at end of session |
| **Show Guardrails** | boolean | `false` | Show active guardrails on startup |
| **Gutter Output Timeout Sec** | int | `180` | Seconds without output before stall detection |
| **Gutter No Progress Iters** | int | `3` | Iterations without progress before stall detection |

### YAML Configuration Reference

Full configuration example:

```yaml
# ~/.config/aprd/config.yaml
ralph:
  enabled: true
  context_rotate_every: 0
  max_consecutive_failures: 3
  auto_add_signs: true
  show_progress_log: true
  show_guardrails: true
  gutter_output_timeout_sec: 180
  gutter_no_progress_iters: 3
```

**Note:** Defaults match the values in `internal/config/config.go:89-107` and `tools/auto_prd/ralph.py:12-22`

### Recommended Settings

**For First-Time Users:**
```yaml
ralph:
  enabled: true
  show_guardrails: true
  show_progress_log: true
```
Start with visibility into what Ralph is doing. This shows guardrails on startup and progress logs at the end.

**For Production:**
```yaml
ralph:
  enabled: true
  auto_add_signs: true
  gutter_output_timeout_sec: 300
  gutter_no_progress_iters: 5
```
More lenient gutter thresholds for real-world workloads with long-running operations (builds, tests).

**For Debugging:**
```yaml
ralph:
  enabled: true
  show_guardrails: true
  show_progress_log: true
  auto_add_signs: false
```
See what would happen without auto-adding signs. Useful for tuning gutter thresholds.

## Storage and Files

### Guardrails Storage

**Location:** `~/.config/aprd/guardrails/<repo_slug>.md`

**Format:** Markdown with structured sections

**Real example:**
```markdown
## sign: test_sign
- **Trigger**: Test trigger
- **Instruction**: Test instruction
- **Added**: Iteration 1
- **File**: src/test.py
- **Category**: test
- **Phase**: local
- **Timestamp**: 2026-01-19T23:23:16.110367+00:00
```

**Repo Slug Generation:**
- From git remote: `owner/repo` → `owner_repo.md`
- Fallback: directory name → `dirname.md`
- See implementation: `tools/auto_prd/guardrails.py:136-157`

**Per-Repository Storage:**
Each repository has its own guardrails file. Signs learned in one repo do not affect other repos. This prevents inappropriate signs from spreading across different projects.

### Progress Storage

**Location:** `~/.config/aprd/progress/<session_id>.jsonl`

**Format:** JSONL (one JSON object per line)

**Real example:**
```json
{"iteration": 1, "timestamp": "2026-01-13T18:53:47.836723+00:00", "status": "completed", "files_changed": [], "learnings": [], "issues_found": [], "tasks_completed": [], "tasks_remaining": 44, "phase": "local", "commits_made": 1}
{"iteration": 2, "timestamp": "2026-01-13T19:06:17.888971+00:00", "status": "completed", "files_changed": [], "learnings": ["Clean code: 1 reviews without findings"], "issues_found": [], "tasks_completed": [], "tasks_remaining": 37, "phase": "local", "commits_made": 1}
{"iteration": 3, "timestamp": "2026-01-13T19:16:06.558752+00:00", "status": "completed", "files_changed": [], "learnings": [], "issues_found": [], "tasks_completed": [], "tasks_remaining": 30, "phase": "local", "commits_made": 1}
```

**Session ID Format:** `<phase>-<identifier>` (e.g., `local-prd`, `review-fix-123`)

**Human-Readable Output:** Set `show_progress_log=true` to see a formatted progress.txt at end of session

### Config Storage

**Location:** `~/.config/aprd/config.yaml`

**Format:** YAML with `ralph:` top-level key

See [Configuration](#configuration) section above for reference.

### XDG Base Directory

Ralph mode follows [XDG Base Directory Specification](https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html):

- **Default:** `~/.config/aprd/`
- **Override:** Set `XDG_CONFIG_HOME` environment variable
- **Windows:** `%APPDATA%\aprd\`
- **macOS:** `~/Library/Application Support/aprd/` (if XDG not set)

## Usage Workflow

### Typical Session with Ralph Mode

1. **Enable Ralph Mode** (one-time setup)
   - Open TUI **Settings**
   - Enable Ralph mode
   - Configure settings (show_guardrails, show_progress_log)
   - Save

2. **Select PRD and Configure** (normal workflow)
   - Pick PRD file
   - Set phases, executors, etc.
   - No Ralph-specific configuration needed

3. **Run Automation** (normal workflow)
   - Press Enter on **Run**
   - Guardrails displayed on startup (if enabled)
   - Automation runs as normal
   - Ralph operates transparently in background

4. **Monitor Progress** (optional)
   - Check **Logs** tab for stall detection messages
   - No additional monitoring needed

5. **Review Outputs** (after completion)
   - Progress log displayed in terminal (if enabled)
   - Guardrails file updated with new signs
   - Progress JSONL file saved for later analysis

### Interpreting Guardrails

**On Startup:**
```
[guardrails]
Important: Follow these signs from previous iterations to avoid recurring issues:

SIGN [check_imports_before_using]
  When: Adding a new import statement
  Do: Check if import already exists and verify the module is available
  Context: src/main.py

[/guardrails]
```

**In Guardrails File:**
Each sign shows:
- **Trigger**: What situation causes this mistake
- **Instruction**: How to avoid the mistake
- **Added**: Which iteration learned this lesson
- **File**: Where the mistake occurred (optional)
- **Category**: Type of issue (import, migration, test, etc.)
- **Phase**: Which phase detected it (local, pr, review_fix)
- **Timestamp**: When the sign was added

### Interpreting Progress Logs

**At End of Session (progress.txt):**
```
# Progress Summary: local-prd
Started: 2026-01-13 18:53:47 UTC

## Iteration 1 (2026-01-13 18:53:47 UTC)
Status: completed
Files Changed: []
Learnings: []
Issues Found: []
Tasks Completed: []
Tasks Remaining: 44
Commits: 1

## Iteration 2 (2026-01-13 19:06:17 UTC)
Status: completed
Files Changed: []
Learnings:
  - Clean code: 1 reviews without findings
Issues Found: []
Tasks Completed: []
Tasks Remaining: 37
Commits: 1

## Iteration 3 (2026-01-13 19:16:06 UTC)
Status: completed
Files Changed: []
Learnings: []
Issues Found: []
Tasks Completed: []
Tasks Remaining: 30
Commits: 1
```

**Key Fields:**
- **Status**: `completed`, `completed_with_warnings`, `failed`
- **Tasks Completed**: Story IDs finished in this iteration
- **Tasks Remaining**: Total tasks left after this iteration
- **Commits**: Number of git commits made
- **Learnings**: Insights from code reviews or successful iterations

## Troubleshooting

### Guardrails Not Loading

**Symptom:** No guardrails displayed on startup

**Possible Causes:**
1. Ralph mode not enabled
2. `show_guardrails=false` in config
3. No guardrails file exists for this repository
4. Guardrails file is malformed

**Solutions:**
1. Check TUI **Settings**: Ralph (Autonomous Mode) → **Enabled** should be `true`
2. Check TUI **Settings**: **Show Guardrails** should be `true`
3. Check file exists: `ls ~/.config/aprd/guardrails/<repo>.md`
4. Inspect file: `cat ~/.config/aprd/guardrails/<repo>.md`
5. See implementation: `tools/auto_prd/guardrails.py:178-276`

### Progress Log Empty

**Symptom:** No progress displayed at end of session

**Possible Causes:**
1. `show_progress_log=false` in config
2. Progress file not written (error during save)
3. Session failed before first iteration

**Solutions:**
1. Check TUI **Settings**: **Show Progress Log** should be `true`
2. Check file exists: `ls ~/.config/aprd/progress/<session>.jsonl`
3. Check logs for errors: `~/.config/aprd/logs/<timestamp>.log`
4. See implementation: `tools/auto_prd/progress_renderer.py:178-210`

### Gutter Detection Too Sensitive

**Symptom:** Agent frequently stalls or adds too many guardrails

**Possible Causes:**
1. Thresholds too low for task complexity
2. Long-running operations (builds, tests) exceed timeout
3. Genuine stuck iterations (agent needs help)

**Solutions:**
1. Increase thresholds in TUI **Settings**:
   - **Gutter Output Timeout Sec**: 180 → 300 or 600
   - **Gutter No Progress Iters**: 3 → 5 or 10
2. Check if operations are genuinely stuck (review logs)
3. Disable auto-add signs if too many false positives:
   - **Auto Add Signs**: `true` → `false`
4. See implementation: `tools/auto_prd/local_loop.py:615-617`

### Signs Not Being Added

**Symptom:** Errors occur but no guardrails added

**Possible Causes:**
1. `auto_add_signs=false` in config
2. Error pattern not recognized by auto-suggester
3. Sign already exists (duplicate prevention)
4. Write failure (permissions, disk space)

**Solutions:**
1. Check TUI **Settings**: **Auto Add Signs** should be `true`
2. Check guardrails file: `cat ~/.config/aprd/guardrails/<repo>.md`
3. Add signs manually (see [Advanced Topics](#advanced-topics) below)
4. Check error patterns: `tools/auto_prd/guardrails.py:371-473`
5. Check logs for write errors: `~/.config/aprd/logs/<timestamp>.log`

### Wrong Repository in Guardrails File

**Symptom:** Signs from one repo appearing in another

**Possible Causes:**
1. Git remote not configured correctly
2. Fallback to directory name causing collisions
3. Manual config override pointing to wrong file

**Solutions:**
1. Check git remote: `git remote -v`
2. Check repo slug generation: `tools/auto_prd/guardrails.py:136-157`
3. Clear wrong file: `rm ~/.config/aprd/guardrails/wrong_repo.md`
4. Set correct remote: `git remote set-url origin <correct-url>`

## Advanced Topics

### Manual Sign Creation

**Create Sign Directly:**
Edit `~/.config/aprd/guardrails/<repo>.md`:

```markdown
## sign: my_custom_sign
- **Trigger**: Description of what triggers this mistake
- **Instruction**: What to do to avoid the mistake
- **Added**: Iteration 1
- **File**: optional_file.py
- **Category**: custom
- **Phase**: local
- **Timestamp**: 2026-01-15T10:00:00.000000+00:00
```

**Format Rules:**
- Sign name: snake_case, unique within file
- Trigger: Clear description of situation
- Instruction: Actionable advice
- Required fields: Trigger, Instruction, Added
- Optional fields: File, Category, Phase, Timestamp

### Exporting Progress Reports

**Convert JSONL to CSV:**
```bash
cd ~/.config/aprd/progress
jq -r '[.iteration, .timestamp, .status, .tasks_remaining] | @csv' local-prd.jsonl > progress.csv
```

**Convert JSONL to Markdown:**
Use `tools/auto_prd/progress_renderer.py:render_progress_txt()` (called automatically when `show_progress_log=true`)

**Backup Progress History:**
```bash
cp -r ~/.config/aprd/progress ~/backup/aprd-progress-$(date +%Y%m%d)
```

### Integration with Existing Workflows

**Pre-Commit Hooks:**
Run guardrails check before commit:
```bash
#!/bin/bash
# .git/hooks/pre-commit
python3 -c "
from pathlib import Path
from tools.auto_prd.guardrails import load_guardrails
signs = load_guardrails(Path.cwd())
if signs:
    print(f'⚠️  {len(signs)} guardrails active for this repo')
"
```

**CI/CD Integration:**
Upload progress logs to CI artifacts:
```yaml
# .github/workflows/test.yml
- name: Upload Ralph progress
  if: always()
  uses: actions/upload-artifact@v3
  with:
    name: ralph-progress
    path: ~/.config/aprd/progress/*.jsonl
```

**Custom Sign Patterns:**
Extend auto-suggester in `tools/auto_prd/guardrails.py:371-473`:
```python
# Add custom pattern to suggest_sign_from_error()
patterns.append({
    "patterns": ["your error pattern here"],
    "name": "your_custom_sign",
    "trigger": "When this happens",
    "instruction": "Do this instead",
    "category": "custom"
})
```

### Performance Considerations

**Guardrails Overhead:**
- Loading: ~10ms for 100 signs (negligible)
- Injection: ~1KB per 10 signs in context window
- Storage: ~500 bytes per sign on disk

**Progress Tracking Overhead:**
- Saving: ~5ms per iteration (JSONL append)
- Loading: ~50ms for 100 iterations
- Storage: ~300 bytes per iteration on disk

**Gutter Detection Overhead:**
- Stall check: O(1) per iteration
- No performance impact on normal operation

**Recommendations:**
- Keep guardrails under 100 signs for readability
- Archive old progress files quarterly
- Use `show_guardrails=false` in production to reduce noise

## Technical Details

For implementation details, architecture, and future plans, see:

- [Ralph Integration Plan](ralph-integration-plan.md) - Full implementation plan and phase status
- [Ralph Wiggum Loop](RALPH_WIGGUM_LOOP.md) - Technical details on loop implementation
- [Architecture](ARCHITECTURE.md) - System architecture with Ralph components

### Implementation Files

**Core Python Modules:**
- `tools/auto_prd/guardrails.py` - Guardrails and signs system (502 lines)
- `tools/auto_prd/progress_renderer.py` - Progress tracking and rendering (410 lines)
- `tools/auto_prd/ralph.py` - Configuration settings (51 lines)

**Integration:**
- `tools/auto_prd/local_loop.py:163-645` - Local loop with guardrails, gutter detection, progress
- `tools/auto_prd/review_loop.py` - Review loop with Ralph features
- `tools/auto_prd/app.py:122-126,163-169,613-621` - Main orchestration

**Configuration:**
- `internal/config/config.go:89-107` - Go config struct with defaults
- `internal/tui/view_settings.go:92-118` - TUI settings group

### Tests

Run Ralph mode tests:
```bash
cd tools/auto_prd
python -m pytest tests/test_guardrails.py -v
python -m pytest tests/test_progress_renderer.py -v
python -m pytest tests/test_ralph.py -v
```

**Test Coverage:**
- 22 guardrails tests (sign creation, loading, formatting, auto-suggestion)
- 21 progress renderer tests (iteration summaries, rendering, JSONL I/O)
- 3 RalphSettings tests (configuration defaults, normalization, thresholds)

## FAQ

**Q: What is Ralph mode named after?**
A: Ralph Wiggum from The Simpsons, via Ryan Carson's "Ralph" technique for autonomous AI iteration. The name emphasizes learning from mistakes (Ralph's innocent wisdom) and keeping things simple.

**Q: Do I need to know about Ryan Carson's Ralph technique to use this?**
A: No. This documentation explains everything from first principles. If you're curious, see the [Ralph Integration Plan](ralph-integration-plan.md) for background.

**Q: Will Ralph mode slow down my automation?**
A: Negligibly. Guardrails loading is ~10ms, progress saving is ~5ms per iteration. The benefits (fewer repeated mistakes) far outweigh the overhead.

**Q: Can I use Ralph mode with Claude-only or Codex-only executors?**
A: Yes. Ralph mode works with any executor (claude, codex, mixed). It's executor-agnostic.

**Q: What happens if I disable Ralph mode after using it?**
A: Guardrails and progress files remain in `~/.config/aprd/`. Re-enabling Ralph mode will use existing guardrails. No data is lost.

**Q: Can I share guardrails between repositories?**
A: Not automatically. Guardrails are per-repository to prevent inappropriate signs from spreading. You can manually copy signs between files if needed.

**Q: How do I delete old guardrails?**
A: Edit `~/.config/aprd/guardrails/<repo>.md` and remove unwanted signs. Or clear all: `rm ~/.config/aprd/guardrails/<repo>.md`

**Q: Can I use Ralph mode for non-PRD tasks?**
A: Yes. Ralph mode is enabled per-session in the TUI. It works with any automation workflow (local, pr, review_fix phases).

**Q: What happens if guardrails conflict with PRD instructions?**
A: Guardrails are injected as "signs to follow" but the agent can choose to ignore them if they conflict with explicit user instructions. They're guidance, not hard constraints.

**Q: Is Ralph mode production-ready?**
A: Yes. The implemented features (Phases 1, 3, 4) are fully tested and used in production. Planned features (Phases 2, 5, 6, 7) are clearly marked as future work.
