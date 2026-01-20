# Update Ralph Integration documentation Implementation Plan

## Overview

Create comprehensive user-facing documentation for Ralph mode, an autonomous iteration feature that is **fully implemented** but **poorly documented**. The existing implementation (guardrails, progress tracking, gutter detection) is production-ready with comprehensive tests, but users lack guidance on what Ralph mode is, how to enable it, and how to interpret its outputs.

This documentation effort will transform Ralph mode from an "advanced feature known only to implementers" to an "accessible tool for all users" by creating clear, practical guides that complement (not replace) the existing technical design documents.

## Current State Analysis

### What Exists Now

**Implementation (Production-Ready):**
- ✅ **Guardrails System** (`tools/auto_prd/guardrails.py`, 502 lines)
  - Sign creation, storage, and loading
  - Automatic sign suggestion from error patterns
  - Markdown storage under `~/.config/aprd/guardrails/<repo_slug>.md`
  - Injection into agent context via system prompt suffix

- ✅ **Progress Tracking** (`tools/auto_prd/progress_renderer.py`, 410 lines)
  - Iteration summaries with learnings, issues, tasks completed/remaining
  - JSONL storage under `~/.config/aprd/progress/<session_id>.jsonl`
  - Human-readable progress.txt rendering

- ✅ **Gutter Detection** (integrated in `tools/auto_prd/local_loop.py:163-645`)
  - StallDetector integration for detecting stuck iterations
  - Configurable thresholds (180s no output, 3 iters no progress)
  - Auto-add guardrails on gutter detection

- ✅ **Configuration** (`internal/config/config.go:89-107`)
  - Ralph struct with 8 configurable fields
  - TUI Settings tab integration (`internal/tui/view_settings.go:92-118`)
  - YAML config support via `~/.config/aprd/config.yaml`

- ✅ **Tests:** 43 Python tests (22 guardrails + 21 progress renderer)

**Existing Documentation (Design-Focused):**
- `docs/ralph-integration-plan.md` (677 lines) - Implementation plan with architecture details
- `docs/RALPH_WIGGUM_LOOP.md` (344 lines) - Ralph Loop technical implementation

### What's Missing

**User-Facing Documentation:**
- ❌ No "Getting Started" guide for Ralph mode
- ❌ No explanation of what Ralph mode is (assumes familiarity with Ryan Carson's technique)
- ❌ No practical examples or workflows
- ❌ No troubleshooting guide
- ❌ No TUI walkthrough (only Settings reference in code)
- ❌ No explanation of storage formats and locations
- ❌ No CLI/TUI configuration reference (documented only in design doc)
- ❌ No real-world examples of guardrails and progress files

**README Integration:**
- ❌ Ralph mode not mentioned in README.md features list
- ❌ No link to Ralph documentation from main docs

### Key Constraints Discovered

1. **Implementation vs. Design Docs:** Must clearly distinguish between what's **implemented** (Phases 1, 3, 4) vs **planned** (Phases 2, 5, 6, 7) to avoid user confusion

2. **Code as Source of Truth:** Documentation should reference actual code implementations with file:line references, not design docs, to prevent drift

3. **XDG Config Paths:** Storage paths (`~/.config/aprd/`) may vary on different systems; must explain XDG Base Directory specification

4. **TUI-First Configuration:** Ralph mode is configured primarily via TUI Settings tab; YAML config is secondary but should be documented

5. **Repo-Specific Storage:** Guardrails are per-repository (based on git remote), not global; this is a key feature to explain

6. **No CLI Flags:** Currently no CLI flags for Ralph mode (only TUI/YAML); must document current state without implying CLI flags exist

### Patterns to Follow

**Documentation Style (from `docs/API.md`):**
- Clear sections: Overview, Quick Start, Features, Configuration, Troubleshooting
- Code examples with syntax highlighting
- Tables for configuration reference
- File:line references for implementation details
- Status indicators (e.g., "Current State: Experimental")

**Markdown Structure (from existing docs):**
- H1 for title, H2 for major sections, H3 for subsections
- Code blocks with language specifiers (```bash, ```yaml, ```python)
- Bullet lists for features and examples
- Horizontal rules (`---`) to separate major sections

**Tone:**
- Practical and user-focused (not design/implementation focused)
- Assume familiarity with autodev but NOT with Ralph technique
- Provide "why this matters" context for each feature

## Desired End State

### Specification

**Primary Deliverable:** `docs/ralph-mode.md` (600-800 lines)
- Comprehensive user guide for Ralph mode
- Explains concepts from first principles (no prior Ralph knowledge assumed)
- Includes practical examples and real-world workflows
- Links to technical design docs for implementation details

**Secondary Deliverables:**
1. Updated `README.md` with Ralph mode in features list
2. Updated `docs/ARCHITECTURE.md` with Ralph components
3. Optional: TUI screenshot or detailed text description of Settings tab

### Verification Criteria

**Completeness:**
- [ ] User can understand what Ralph mode is without prior knowledge
- [ ] User can enable Ralph mode via TUI or YAML config
- [ ] User can interpret guardrails and progress logs
- [ ] User knows where files are stored and in what format
- [ ] User can troubleshoot common issues

**Accuracy:**
- [ ] All configuration fields documented with correct defaults
- [ ] All file paths match actual implementation
- [ ] All features match what's implemented (Phases 1, 3, 4 only)
- [ ] All code references have correct file:line numbers

**Quality:**
- [ ] Follows existing documentation style (`docs/API.md` as template)
- [ ] Includes real examples from `~/.config/aprd/guardrails/` and `~/.config/aprd/progress/`
- [ ] Clear distinction between implemented vs. planned features
- [ ] Links to technical design docs for deep dives

## What We're NOT Doing

### Out of Scope (Explicitly Excluded)

1. **Implementing Missing Features:**
   - Phase 2 (Pattern Discovery) - not implemented
   - Phase 5 (Context Rotation) - not implemented
   - Phase 6 (Task Selection) - not implemented
   - Phase 7 (Idempotency) - not implemented

2. **Adding CLI Flags:**
   - No new CLI arguments for Ralph mode
   - Document current TUI/YAML configuration only

3. **Creating Video Tutorials:**
   - Text-only documentation
   - Screenshots optional (text description sufficient)

4. **Modifying Existing Design Docs:**
   - Keep `docs/ralph-integration-plan.md` and `docs/RALPH_WIGGUM_LOOP.md` unchanged
   - Create new user guide, not replace technical docs

5. **Adding Examples to Codebase:**
   - Use existing examples from `~/.config/aprd/` only
   - Do not create example guardrails/progress files in repo

6. **Internationalization:**
   - English documentation only
   - No translations planned

7. **Advanced Configuration:**
   - Document only the 8 Ralph fields in config
   - No advanced tuning guides or performance optimization

8. **Migration Tools:**
   - No scripts to migrate from non-Ralph to Ralph mode
   - Manual enablement only

### Why These Exclusions Matter

Prevents scope creep by:
- Focusing on **documentation only**, not code changes
- Avoiding feature requests disguised as documentation tasks
- Keeping the plan achievable in a single documentation pass
- Respecting the wreckit item's scope: "update documentation" not "implement features"

## Implementation Approach

### High-Level Strategy

**Incremental Documentation:** Build documentation in layers, starting with overview and ending with troubleshooting. Each layer adds depth without requiring rewrites.

**Code-First Verification:** For every claim in documentation, verify against actual code implementation. Use `grep` and `Read` tools to confirm file:line references.

**Real Examples:** Use actual guardrails and progress files from `~/.config/aprd/` as examples, not synthetic ones. This ensures accuracy and shows real-world usage.

**User Journey Structure:** Organize documentation to follow the user's journey: "What is it?" → "How do I use it?" → "What does it output?" → "How do I fix problems?"

**Complement, Don't Replace:** Keep existing design docs (`ralph-integration-plan.md`, `RALPH_WIGGUM_LOOP.md`) as technical references. Link to them from user guide for implementation details.

### Phase Ordering

1. **Create User Guide** (`docs/ralph-mode.md`) - Primary deliverable, highest value
2. **Update README.md** - Quick visibility boost, links to user guide
3. **Update ARCHITECTURE.md** - Context for developers, links to user guide

This ordering ensures the most important documentation (user guide) is completed first, with incremental updates to existing docs.

---

## Phase 1: Create User Guide (`docs/ralph-mode.md`)

### Overview

Create comprehensive user-facing documentation for Ralph mode that explains concepts from first principles, provides practical examples, and includes troubleshooting guidance.

### Changes Required

#### 1. Create `docs/ralph-mode.md`

**File:** `docs/ralph-mode.md` (NEW FILE)
**Changes:** Create new user guide with following structure:

```markdown
# Ralph Mode - Autonomous Iteration

## Overview
- Brief explanation: What is Ralph mode and why does it exist?
- Context: Based on Ryan Carson's Ralph technique for autonomous iteration
- Key benefits: Reduced repeated mistakes, better long-running sessions, visibility into progress
- When to use: Large PRDs, complex codebases, multi-iteration tasks

## Ralph Mode Concepts
### Context Hygiene
- Fresh context per iteration prevents "conversation rot"
- Externalized state (files, not chat memory) enables recovery

### Guardrails (Mistake Prevention)
- "Signs" pattern: Learn from mistakes, never repeat them
- Signs stored per-repository in `~/.config/aprd/guardrails/<repo>.md`
- Injected into agent context each iteration

### Progress Tracking
- Iteration history with learnings, issues, tasks completed/remaining
- JSONL files in `~/.config/aprd/progress/<session>.jsonl`
- Human-readable progress.txt summary at end

### Gutter Detection
- Detects when agent is stuck (no output or no progress)
- Configurable thresholds: time-based (180s) and iteration-based (3 iters)
- Auto-adds guardrails when gutter detected

## Features
### Implemented Features (Current Version)
- ✅ Guardrails (Phase 1)
- ✅ Progress Tracking (Phase 3)
- ✅ Gutter Detection (Phase 4)

### Planned Features (Future)
- ⏸️ Pattern Discovery (Phase 2)
- ⏸️ Context Rotation (Phase 5)
- ⏸️ Task Selection (Phase 6)
- ⏸️ Idempotency (Phase 7)

See [Ralph Integration Plan](ralph-integration-plan.md) for technical details on planned features.

## Quick Start
### Step 1: Enable Ralph Mode
#### Via TUI (Recommended)
1. Open aprd TUI
2. Navigate to Settings tab
3. Find "Ralph (Autonomous Mode)" section
4. Set "Enabled" to true
5. Adjust other settings (see Configuration below)
6. Save and return to Run tab

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
- Run automation as normal from Run tab
- Ralph mode operates transparently in background
- No changes to workflow needed

### Step 3: View Outputs
- Guardrails displayed on startup (if `show_guardrails=true`)
- Progress log displayed at end (if `show_progress_log=true`)
- Guardrails file: `~/.config/aprd/guardrails/<repo>.md`
- Progress files: `~/.config/aprd/progress/<session>.jsonl`

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

**Note:** Defaults match the values in `internal/config/config.go:169-178`

### Recommended Settings

**For First-Time Users:**
```yaml
ralph:
  enabled: true
  show_guardrails: true
  show_progress_log: true
```
(Start with visibility into what Ralph is doing)

**For Production:**
```yaml
ralph:
  enabled: true
  auto_add_signs: true
  gutter_output_timeout_sec: 300
  gutter_no_progress_iters: 5
```
(More lenient gutter thresholds, auto-add signs)

**For Debugging:**
```yaml
ralph:
  enabled: true
  show_guardrails: true
  show_progress_log: true
  auto_add_signs: false
```
(See what would happen without auto-adding signs)

## Storage and Files

### Guardrails Storage

**Location:** `~/.config/aprd/guardrails/<repo_slug>.md`

**Format:** Markdown with structured sections

**Example:**
```markdown
## sign: check_imports_before_using
- **Trigger**: Adding a new import statement
- **Instruction**: Check if import already exists and verify the module is available
- **Added**: Iteration 3
- **File**: src/main.py
- **Category**: import
- **Phase**: local
- **Timestamp**: 2026-01-15T10:30:45.123456+00:00
```

**Repo Slug Generation:**
- From git remote: `owner/repo` → `owner_repo.md`
- Fallback: directory name → `dirname.md`
- See `tools/auto_prd/guardrails.py:136-157`

**Per-Repository Storage:**
Each repository has its own guardrails file. Signs learned in one repo do not affect other repos.

### Progress Storage

**Location:** `~/.config/aprd/progress/<session_id>.jsonl`

**Format:** JSONL (one JSON object per line)

**Example:**
```json
{"iteration": 1, "timestamp": "2026-01-15T10:00:00.000000+00:00", "status": "completed", "files_changed": ["src/main.py"], "learnings": ["Clean code: 1 reviews without findings"], "issues_found": [], "tasks_completed": ["US-001", "US-002"], "tasks_remaining": 5, "phase": "local", "commits_made": 1}
{"iteration": 2, "timestamp": "2026-01-15T10:15:00.000000+00:00", "status": "completed", "files_changed": [], "learnings": [], "issues_found": ["Test failure in src/test.py"], "tasks_completed": [], "tasks_remaining": 5, "phase": "local", "commits_made": 0}
```

**Session ID Format:** `<phase>-<identifier>` (e.g., `local-prd`, `review-fix-123`)

**Human-Readable Output:** Set `show_progress_log=true` to see progress.txt at end of session

### Config Storage

**Location:** `~/.config/aprd/config.yaml`

**Format:** YAML with `ralph:` top-level key

See Configuration section above for reference.

### XDG Base Directory

Ralph mode follows [XDG Base Directory Specification](https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html):

- **Default:** `~/.config/aprd/`
- **Override:** Set `XDG_CONFIG_HOME` environment variable
- **Windows:** `%APPDATA%\aprd\`
- **macOS:** `~/Library/Application Support/aprd/` (if XDG not set)

## Usage Workflow

### Typical Session with Ralph Mode

1. **Enable Ralph Mode** (one-time setup)
   - Open TUI Settings
   - Enable Ralph mode
   - Configure settings (show_guardrails, show_progress_log)
   - Save

2. **Select PRD and Configure** (normal workflow)
   - Pick PRD file
   - Set phases, executors, etc.
   - No Ralph-specific configuration needed

3. **Run Automation** (normal workflow)
   - Press Enter on Run
   - Guardrails displayed on startup (if enabled)
   - Automation runs as normal
   - Ralph operates transparently in background

4. **Monitor Progress** (optional)
   - Check Logs tab for stall detection messages
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
- **Category**: Type of issue (import, migration, etc.)
- **Phase**: Which phase detected it (local, pr, review_fix)
- **Timestamp**: When the sign was added

### Interpreting Progress Logs

**At End of Session (progress.txt):**
```
# Progress Summary: local-prd
Started: 2026-01-15 10:00:00 UTC

## Iteration 1 (2026-01-15 10:15:00 UTC)
Status: completed
Files Changed: src/main.py, src/test.py
Learnings:
  - Clean code: 1 reviews without findings
Issues Found: []
Tasks Completed: US-001, US-002
Tasks Remaining: 5
Commits: 1

## Iteration 2 (2026-01-15 10:30:00 UTC)
Status: completed_with_warnings
Files Changed: src/main.py
Learnings: []
Issues Found:
  - Test failure in src/test.py
Tasks Completed: []
Tasks Remaining: 5
Commits: 0
```

**Key Fields:**
- **Status**: `completed`, `completed_with_warnings`, `failed`
- **Tasks Completed**: Story IDs finished in this iteration
- **Tasks Remaining**: Total tasks left after this iteration
- **Commits**: Number of git commits made

## Troubleshooting

### Guardrails Not Loading

**Symptom:** No guardrails displayed on startup

**Possible Causes:**
1. Ralph mode not enabled
2. `show_guardrails=false` in config
3. No guardrails file exists for this repository
4. Guardrails file is malformed

**Solutions:**
1. Check TUI Settings: Ralph (Autonomous Mode) → Enabled should be true
2. Check TUI Settings: Show Guardrails should be true
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
1. Check TUI Settings: Show Progress Log should be true
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
1. Increase thresholds in TUI Settings:
   - Gutter Output Timeout Sec: 180 → 300 or 600
   - Gutter No Progress Iters: 3 → 5 or 10
2. Check if operations are genuinely stuck (review logs)
3. Disable auto-add signs if too many false positives:
   - Auto Add Signs: true → false
4. See implementation: `tools/auto_prd/local_loop.py:615-617`

### Signs Not Being Added

**Symptom:** Errors occur but no guardrails added

**Possible Causes:**
1. `auto_add_signs=false` in config
2. Error pattern not recognized by auto-suggester
3. Sign already exists (duplicate prevention)
4. Write failure (permissions, disk space)

**Solutions:**
1. Check TUI Settings: Auto Add Signs should be true
2. Check guardrails file: `cat ~/.config/aprd/guardrails/<repo>.md`
3. Add signs manually (see Advanced Topics below)
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

- `tools/auto_prd/guardrails.py` - Guardrails and signs system
- `tools/auto_prd/progress_renderer.py` - Progress tracking and rendering
- `tools/auto_prd/ralph.py` - Configuration settings
- `tools/auto_prd/local_loop.py:163-645` - Loop integration with Ralph features
- `internal/config/config.go:89-107` - Go configuration struct
- `internal/tui/view_settings.go:92-118` - TUI settings group

### Tests

Run Ralph mode tests:
```bash
cd tools/auto_prd
python -m pytest tests/test_guardrails.py -v
python -m pytest tests/test_progress_renderer.py -v
python -m pytest tests/test_ralph.py -v
```

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
```

### Success Criteria

#### Automated Verification:
- [ ] Markdown syntax valid (can be parsed by CommonMark)
- [ ] All file paths referenced exist (use `ls` to verify)
- [ ] All code references have correct file:line numbers (use `grep` to verify)
- [ ] All links resolve (check with markdown linter)

#### Manual Verification:
- [ ] User can understand what Ralph mode is without prior knowledge
- [ ] User can enable Ralph mode via TUI steps (follow instructions literally)
- [ ] User can interpret guardrails file example (shows real file from `~/.config/aprd/guardrails/`)
- [ ] User can interpret progress log example (shows real file from `~/.config/aprd/progress/`)
- [ ] Troubleshooting section covers common issues (test with simulated errors)
- [ ] Recommended settings are practical (test with actual use)
- [ ] FAQ answers realistic questions (avoid edge cases)

**Note:** Complete all automated verification, then pause for manual review before proceeding to Phase 2.

---

## Phase 2: Update README.md

### Overview

Add Ralph mode to README.md features list and provide quick link to full documentation. This gives visibility to Ralph mode without cluttering the main README.

### Changes Required

#### 1. Update README.md Features Section

**File:** `README.md`
**Changes:** Add Ralph mode to features list

**Current section (lines 7-16):**
```markdown
## Features

- Single binary `aprd` to start the TUI.
- Configure flags & env (executor policy, repo/base/branch, CI toggles, timings).
- **Select & tag** a PRD file (quick scan for `*.md`, add/remove tags).
- **Initial prompt** field (optional); injected as a temp overlay above your PRD for the first pass.
- **Per-phase executors** (implement, fix, PR, review_fix) via env overrides or policy fallback.
- **Start from any step** by toggling phases: local, pr, review_fix.
- Finds the Python automation script relative to the binary when the default path is missing.
- Persists each run's logs to `~/.config/aprd/logs/` for post-run debugging.
```

**Updated section:**
```markdown
## Features

- **Ralph Mode** - Autonomous iteration with guardrails, progress tracking, and gutter detection ([docs](docs/ralph-mode.md))
- Single binary `aprd` to start the TUI.
- Configure flags & env (executor policy, repo/base/branch, CI toggles, timings, Ralph settings).
- **Select & tag** a PRD file (quick scan for `*.md`, add/remove tags).
- **Initial prompt** field (optional); injected as a temp overlay above your PRD for the first pass.
- **Per-phase executors** (implement, fix, PR, review_fix) via env overrides or policy fallback.
- **Start from any step** by toggling phases: local, pr, review_fix.
- Finds the Python automation script relative to the binary when the default path is missing.
- Persists each run's logs to `~/.config/aprd/logs/` for post-run debugging.
```

**Changes:**
- Add Ralph mode as first feature (most prominent position)
- Include link to `docs/ralph-mode.md`
- Update "Configure flags & env" to mention Ralph settings

#### 2. Optional: Add Ralph Mode to Advanced Control Section

**File:** `README.md`
**Changes:** Add brief mention in existing advanced sections

**Current section (lines 56-64):**
```markdown
### Per-phase executors
In **Settings**, set the executor for each phase:
- Exec (implement): `codex|claude|<empty>`
- Exec (fix): `codex|claude|<empty>`
- Exec (pr): `codex|claude|<empty>`
- Exec (review_fix): `codex|claude|<empty>`
```

**Add after this section:**
```markdown
### Ralph Mode (Autonomous Iteration)
Enable Ralph mode in **Settings** for autonomous iteration with:
- **Guardrails** - Learn from mistakes and never repeat them
- **Progress tracking** - See iteration history and learnings
- **Gutter detection** - Automatically detect when stuck

See [Ralph Mode documentation](docs/ralph-mode.md) for details.
```

### Success Criteria

#### Automated Verification:
- [ ] Markdown syntax valid
- [ ] Link to `docs/ralph-mode.md` resolves (file exists after Phase 1)
- [ ] No duplicate or conflicting feature descriptions

#### Manual Verification:
- [ ] Ralph mode is visible in README (first feature listed)
- [ ] Link works (click through to ralph-mode.md)
- [ ] Description is concise but informative (doesn't overwhelm main README)
- [ ] README tone matches existing content (technical but accessible)

**Note:** Complete all automated verification, then pause for manual review before proceeding to Phase 3.

---

## Phase 3: Update ARCHITECTURE.md

### Overview

Add Ralph mode components to ARCHITECTURE.md to provide context for developers working on the codebase. This is a technical addition, not user-facing.

### Changes Required

#### 1. Add Ralph Components to System Overview

**File:** `docs/ARCHITECTURE.md`
**Changes:** Add Ralph mode to architecture diagrams and component descriptions

**Current section (lines 1-42):**
```markdown
## System Overview

AutoDev consists of two main components:

1. **Go TUI Frontend** (`cmd/aprd/`) - Interactive terminal interface for configuration and execution
2. **Python Agent Harness** (`tools/auto_prd/`) - Backend automation pipeline
```

**Add after "Python Agent Harness":**
```markdown
3. **Ralph Mode** (`tools/auto_prd/guardrails.py`, `tools/auto_prd/progress_renderer.py`) - Autonomous iteration features
```

**Update diagram to include Ralph mode:**
```markdown
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
```

#### 2. Add Ralph Mode Section

**File:** `docs/ARCHITECTURE.md`
**Changes:** Add new section describing Ralph mode architecture

**Add before "Go TUI Architecture" section:**
```markdown
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
- Go struct: `internal/config/config.go:89-107` (Ralph config)
- TUI integration: `internal/tui/view_settings.go:92-118` (Settings group)
- Python helpers: `tools/auto_prd/ralph.py` (RalphSettings dataclass)

**Loop Integration:**
- Local loop: `tools/auto_prd/local_loop.py:163-645` (loads guardrails, injects context, tracks progress, detects stalls)
- Review loop: `tools/auto_prd/review_loop.py` (similar Ralph integration)

**App Entry Point:**
- Main orchestration: `tools/auto_prd/app.py:122-126,163-169,613-621` (shows guardrails, displays progress)

### Storage

- Guardrails: `~/.config/aprd/guardrails/<repo_slug>.md` (Markdown)
- Progress: `~/.config/aprd/progress/<session_id>.jsonl` (JSONL)
- Config: `~/.config/aprd/config.yaml` (YAML, Ralph section)

See [Ralph Mode documentation](ralph-mode.md) for user-facing guide.
```

### Success Criteria

#### Automated Verification:
- [ ] Markdown syntax valid
- [ ] All file paths exist (verify with `ls`)
- [ ] All line numbers correct (verify with `grep -n`)
- [ ] Diagram renders correctly (ASCII art aligned)

#### Manual Verification:
- [ ] Ralph mode section fits with existing architecture content
- [ ] Component descriptions are accurate (match actual implementation)
- [ ] Integration points are clear (developer can find code)
- [ ] Links to user docs work (ralph-mode.md exists)

**Note:** Complete all automated and manual verification. This is the final phase.

---

## Testing Strategy

### Unit Tests
Not applicable (documentation-only changes)

### Integration Tests
Not applicable (documentation-only changes)

### Manual Testing Steps

#### Phase 1: User Guide

1. **Follow Quick Start literally:**
   - Enable Ralph mode via TUI Settings
   - Run a small PRD (2-3 user stories)
   - Verify guardrails displayed on startup
   - Verify progress log displayed at end
   - Check files exist in `~/.config/aprd/`

2. **Test Configuration Examples:**
   - Copy YAML config from docs to `~/.config/aprd/config.yaml`
   - Verify TUI reflects the settings
   - Test each recommended setting (first-time, production, debugging)

3. **Verify Storage Paths:**
   - Check `~/.config/aprd/guardrails/<repo>.md` exists
   - Check `~/.config/aprd/progress/<session>.jsonl` exists
   - Verify paths match documentation

4. **Test Troubleshooting Steps:**
   - Simulate "Guardrails Not Loading" (disable show_guardrails)
   - Simulate "Progress Log Empty" (disable show_progress_log)
   - Follow troubleshooting steps to verify fixes

5. **Review Examples:**
   - Compare guardrails example in docs to real file
   - Compare progress example in docs to real file
   - Verify format matches

#### Phase 2: README Update

1. **Check README rendering:**
   - View README.md in GitHub/GitLab UI
   - Verify Ralph mode is visible as first feature
   - Click link to ralph-mode.md
   - Verify link works

2. **Check README clarity:**
   - Read README as a new user
   - Verify Ralph mode description is clear
   - Verify it doesn't overwhelm other features

#### Phase 3: Architecture Update

1. **Verify architecture accuracy:**
   - Cross-reference file paths with actual code
   - Verify line numbers match current codebase
   - Check diagram renders correctly (monospaced font)

2. **Check integration points:**
   - Follow each file:line reference
   - Verify Ralph integration exists as documented
   - Check links to ralph-mode.md work

## Migration Notes

Not applicable (new documentation, no existing docs to migrate)

## References

### Source Files
- Research: `/Users/simo/Projects/autodev/.wreckit/items/022-update-ralph-integration-documentation/research.md`
- Implementation: `tools/auto_prd/guardrails.py:1-502`
- Implementation: `tools/auto_prd/progress_renderer.py:1-410`
- Implementation: `tools/auto_prd/ralph.py:1-51`
- Configuration: `internal/config/config.go:89-107`
- TUI: `internal/tui/view_settings.go:92-118`
- Loop Integration: `tools/auto_prd/local_loop.py:163-645`

### Existing Documentation
- Design Plan: `docs/ralph-integration-plan.md:1-677`
- Technical Details: `docs/RALPH_WIGGUM_LOOP.md:1-344`
- Architecture: `docs/ARCHITECTURE.md:1-50+`
- API Reference: `docs/API.md:1-100+` (style template)

### Example Files
- Guardrails: `~/.config/aprd/guardrails/add_first_test.md`
- Progress: `~/.config/aprd/progress/local-prd.jsonl`

### External References
- XDG Base Directory Spec: https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html
- Ryan Carson's Ralph technique (mentioned in ralph-integration-plan.md)
