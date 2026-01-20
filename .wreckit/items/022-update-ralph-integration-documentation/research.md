# Research: Update Ralph Integration documentation

**Date**: 2026-01-20
**Item**: 022-update-ralph-integration-documentation

## Research Question
Incomplete documentation makes Ralph mode features difficult to understand and use.

**Motivation:** Ensures users can effectively utilize Ralph mode capabilities.

**Signals:** priority: low

## Summary

The Ralph integration is **implemented and functional** but lacks comprehensive user-facing documentation. The implementation consists of three core Python modules (`guardrails.py`, `progress_renderer.py`, `ralph.py`), Go configuration structures, and TUI integration. However, existing documentation (`docs/ralph-integration-plan.md` and `docs/RALPH_WIGGUM_LOOP.md`) focuses on **design and implementation details** rather than **user guidance**.

**What needs to be done:** Create user-focused documentation that explains:
1. What Ralph mode is and when to use it
2. How to enable and configure Ralph mode via TUI and CLI
3. The three main features: Guardrails (mistake prevention), Progress Tracking (iteration history), and Gutter Detection (stall recovery)
4. Practical examples and workflows
5. Storage locations and file formats for guardrails and progress logs

**How to approach:** Leverage the existing implementation files as source material. The code is well-documented with docstrings, and real examples exist in `~/.config/aprd/guardrails/` and `~/.config/aprd/progress/`. Create a new comprehensive user guide that complements (not replaces) the existing technical design documents.

## Current State Analysis

### Existing Implementation

**Core Python Modules:**
1. **`tools/auto_prd/guardrails.py`** (502 lines) - Implements "signs" pattern for mistake prevention
   - `Sign` dataclass with metadata (name, trigger, instruction, iteration, file_context, category, phase)
   - `add_sign()` - Persists signs to `~/.config/aprd/guardrails/<repo_slug>.md`
   - `load_guardrails()` - Loads signs for agent context injection
   - `format_signs_for_prompt()` - Formats signs for Claude/Codex system prompts
   - `suggest_sign_from_error()` - Auto-suggests signs from error patterns
   - Storage: Markdown format under `~/.config/aprd/guardrails/`

2. **`tools/auto_prd/progress_renderer.py`** (410 lines) - Tracks iteration history
   - `IterationSummary` dataclass (iteration, timestamp, status, files_changed, learnings, issues_found, tasks_completed, tasks_remaining, phase, commits_made)
   - `ProgressHistory` dataclass (session_id, started_at, codebase_patterns, iterations)
   - `save_iteration_summary()` - Appends to `~/.config/aprd/progress/<session_id>.jsonl`
   - `load_progress_history()` - Loads history for analysis
   - `render_progress_txt()` - Renders human-readable progress.txt
   - Storage: JSONL format under `~/.config/aprd/progress/`

3. **`tools/auto_prd/ralph.py`** (51 lines) - Configuration settings
   - `RalphSettings` dataclass with defaults
   - `normalized()` - Ensures safe minimums and boolean conversion
   - `stall_thresholds()` - Returns StallDetector thresholds (no_output, no_progress)

**Go Configuration:**
- **`internal/config/config.go:89-107`** - `Ralph` struct in Config
  - All configuration fields with YAML tags
  - Defaults: enabled=false, auto_add_signs=true, gutter thresholds (180s, 3 iters)
  - Integrated into main Config struct

**TUI Integration:**
- **`internal/tui/view_settings.go:92-118`** - `renderRalphGroup()` function
  - 8 input fields for Ralph settings
  - Grouped under "Ralph (Autonomous Mode)" box
  - All inputs properly focused and styled

**Loop Integration:**
- **`tools/auto_prd/local_loop.py:163-645`** - Main orchestration with Ralph features
  - Loads guardrails on startup (line 232)
  - Injects guardrails into Claude prompts (line 310)
  - Auto-suggests signs from errors (lines 386, 540)
  - Auto-adds signs when `ralph.auto_add_signs=true` (lines 402, 556, 622)
  - Records progress for gutter detection (lines 615-617)
  - Saves iteration summaries (line 638)

- **`tools/auto_prd/review_loop.py`** - Similar Ralph integration for review phase
  - Guardrails loading and injection
  - Sign suggestion and auto-addition
  - Progress tracking

**App Entry Point:**
- **`tools/auto_prd/app.py:122-126, 163-169, 613-621`** - Main Ralph orchestration
  - Loads `ralph_settings` from args or defaults
  - Shows guardrails on startup if `show_guardrails=true`
  - Displays progress log at end if `show_progress_log=true`

### Existing Documentation

**Design Documents:**
1. **`docs/ralph-integration-plan.md`** (677 lines)
   - Comprehensive implementation plan for 7 phases
   - Phase 1 (Guardrails): ✅ Complete
   - Phase 2 (Pattern Discovery): ⏸️ Pending
   - Phase 3 (Progress Logging): ✅ Complete
   - Phase 4 (Gutter Detection): ✅ Complete
   - Phase 5-7: ⏸️ Pending
   - Heavy focus on architecture and implementation details
   - Code examples and file structure
   - Migration path and success metrics
   - **Status:** Implementation is 91% complete per document

2. **`docs/RALPH_WIGGUM_LOOP.md`** (344 lines)
   - Documents Ralph Wiggum Loop implementation (7-signal convergence)
   - Implementation details for termination conditions, guardrail evolution, versioned criteria
   - Integration points and testing evidence
   - **Status:** Technical documentation, not user-facing

**What's Missing:**
- No "Getting Started" guide for Ralph mode
- No explanation of what Ralph mode is (assumes familiarity with Ryan Carson's technique)
- No practical examples or workflows
- No troubleshooting guide
- No screenshots or TUI walkthrough
- No explanation of storage formats and locations
- No CLI flag reference (only documented in design doc)

### Key Files

**Implementation:**
- `tools/auto_prd/guardrails.py:1-502` - Core guardrails system with signs
- `tools/auto_prd/progress_renderer.py:1-410` - Progress tracking and rendering
- `tools/auto_prd/ralph.py:1-51` - Configuration settings
- `internal/config/config.go:89-107` - Go config struct with defaults
- `internal/tui/view_settings.go:92-118` - TUI settings group

**Integration:**
- `tools/auto_prd/local_loop.py:163-645` - Local loop with guardrails, gutter detection, progress
- `tools/auto_prd/review_loop.py` - Review loop with Ralph features
- `tools/auto_prd/app.py:122-126,163-169,613-621` - Main orchestration

**Tests:**
- `tools/auto_prd/tests/test_ralph.py:1-150` - RalphSettings configuration tests
- `tools/auto_prd/tests/test_progress_renderer.py` - Progress rendering tests
- `tools/auto_prd/tests/test_guardrails.py` - Guardrails system tests (22 tests)

**Existing Docs:**
- `docs/ralph-integration-plan.md:1-677` - Implementation plan (design-focused)
- `docs/RALPH_WIGGUM_LOOP.md:1-344` - Ralph Loop technical details

## Technical Considerations

### Dependencies

**External Dependencies:**
- None (Ralph mode is built on existing autodev infrastructure)

**Internal Modules:**
- `tools/auto_prd/context.py` - StallDetector for gutter detection
- `tools/auto_prd/git_ops.py` - parse_owner_repo_from_git() for repo_slug
- `tools/auto_prd/journal.py` - Existing journal system (reused for progress)
- `tools/auto_prd/errors.py` - StructuredError for error patterns
- `internal/config/config.go` - Configuration management
- `internal/tui/*` - TUI components

**Storage:**
- `~/.config/aprd/guardrails/` - Per-repo markdown files
- `~/.config/aprd/progress/` - Per-session JSONL files
- `~/.config/aprd/config.yaml` - Ralph settings

### Patterns to Follow

**Documentation Style:**
- Follow existing docs structure (`docs/live-feed.md` as template)
- Use clear sections: Overview, Features, Configuration, Usage, Troubleshooting
- Include code examples and file path references
- Use markdown for consistency with codebase

**Code Patterns:**
- Docstrings in Python modules are comprehensive - use as source material
- Configuration defaults in `config.go:169-178` should be documented
- Error handling patterns in `guardrails.py:371-473` can be referenced

**Conventions:**
- Ralph mode is **opt-in** (disabled by default)
- Settings are configured via TUI Settings tab or YAML config
- Storage follows XDG Base Directory specification (`~/.config/aprd/`)
- All Python code uses type hints and docstrings
- Go code follows standard project patterns

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Documentation drift** | Medium | Reference actual code implementations, not design docs; include file:line references |
| **Conceptual complexity** | High | Start with "What is Ralph mode?" section; explain concepts simply before diving into features |
| **Missing features** | Low | Clearly document what's implemented (Phases 1, 3, 4) vs planned (Phases 2, 5, 6, 7) |
| **TUI changes** | Low | Document current TUI implementation; note that UI may evolve |
| **Storage location confusion** | Medium | Clearly explain XDG config paths; provide examples of actual file locations |
| **Over-documentation** | Low | Keep user guide separate from technical design docs; link to design docs for details |

## Recommended Approach

### 1. Create User-Facing Guide (`docs/ralph-mode.md`)

**Structure:**
```markdown
# Ralph Mode - Autonomous Iteration

## What is Ralph Mode?
- Brief explanation of Ralph technique (context hygiene, mistake prevention)
- Benefits: Reduced repeated mistakes, better long-running sessions, visibility
- When to use: Large PRDs, complex codebases, multi-iteration tasks

## Features Overview
### 1. Guardrails (Mistake Prevention)
- What: Learn from mistakes, never repeat them
- How: Signs stored in `~/.config/aprd/guardrails/<repo>.md`
- Example: Show real guardrail file content

### 2. Progress Tracking
- What: Iteration history with learnings and issues
- How: JSONL files in `~/.config/aprd/progress/<session>.jsonl`
- Example: Show progress.txt output

### 3. Gutter Detection
- What: Detect when agent is stuck
- How: StallDetector with configurable thresholds
- Recovery: Auto-add guardrail signs

## Configuration
### TUI Configuration
- Screenshot/reference to Settings tab
- List all 8 Ralph fields with explanations
- Default values and recommended settings

### CLI Configuration
- YAML config example
- Environment variables (if any)

## Usage Workflow
1. Enable Ralph mode in TUI
2. Run automation as normal
3. View guardrails on startup
4. Monitor progress in logs
5. Review progress log at end
6. Inspect guardrails file for learnings

## Storage and Files
- Guardrails: `~/.config/aprd/guardrails/`
- Progress: `~/.config/aprd/progress/`
- Config: `~/.config/aprd/config.yaml`
- File formats explained (markdown, JSONL)

## Troubleshooting
- Guardrails not loading
- Progress log empty
- Gutter detection too sensitive
- Signs not being added

## Advanced Topics
- Manual sign creation
- Exporting progress reports
- Integration with existing workflows
- Links to design docs for technical details
```

### 2. Update README.md

Add Ralph mode to features list:
```markdown
## Features
- **Ralph Mode** - Autonomous iteration with guardrails, progress tracking, and gutter detection
```

Add reference to `docs/ralph-mode.md`

### 3. Create Quick Reference

Add "Ralph Mode" section to existing docs:
- `docs/OPERATIONS.md` - Operational procedures
- `docs/ARCHITECTURE.md` - Update with Ralph components

### 4. Examples and Screenshots

- Example guardrail file (already exists at `~/.config/aprd/guardrails/add_first_test.md`)
- Example progress JSONL (already exists at `~/.config/aprd/progress/local-prd.jsonl`)
- TUI Settings tab screenshot (if possible, or detailed text description)

## Open Questions

1. **Audience level** - Should docs assume familiarity with Ryan Carson's Ralph technique, or explain from first principles?
   - **Recommendation:** Explain from first principles with link to external resources

2. **Separate files vs single file** - Should Ralph mode docs be in `docs/ralph-mode.md` or integrated into existing docs?
   - **Recommendation:** Create new `docs/ralph-mode.md` as user guide, keep design docs separate

3. **TUI screenshots** - Are screenshots desired, or is text description sufficient?
   - **Recommendation:** Start with text description, add screenshots later if needed

4. **Feature completeness** - How to document unimplemented phases (2, 5, 6, 7)?
   - **Recommendation:** Clearly label as "Planned" or "Not Yet Implemented" with link to design doc

5. **CLI flags** - Are there CLI flags for Ralph mode, or only TUI/YAML config?
   - **Answer:** Currently only TUI/YAML; document current state, note CLI flags may be added

6. **Migration guide** - Should we include migration from non-Ralph to Ralph mode?
   - **Recommendation:** Add brief "Getting Started" section explaining how to enable for existing projects

## Next Steps

1. **Create user guide** (`docs/ralph-mode.md`) using structure above
2. **Update README.md** with Ralph mode reference
3. **Add examples section** with real guardrail/progress file content
4. **Create troubleshooting guide** based on common issues
5. **Link from design docs** to user guide for "how to use"
6. **Consider video walkthrough** if TUI is complex to explain in text

## Conclusion

Ralph mode is **well-implemented** but **poorly documented** from a user perspective. The code is production-ready with comprehensive tests, but users lack guidance on:
- What Ralph mode is
- How to enable it
- What benefits it provides
- How to interpret guardrails and progress logs

Creating a user-focused guide will unlock the value of the existing implementation and enable users to effectively utilize Ralph mode capabilities.
