# TUI Analysis Plan: Strengths, Weaknesses & Improvement Opportunities

**Generated:** 2025-11-27
**Status:** Analysis Only (No Changes)

---

## Executive Summary

The `aprd-tui` is a well-architected Bubble Tea application with 8 tabs, comprehensive configuration management, and real-time process monitoring. However, there are significant gaps between the Python script capabilities and what the TUI exposes, plus several UX opportunities for improvement.

---

## Part 1: Current Strengths

### 1.1 Architecture & Code Quality

| Strength | Details |
|----------|---------|
| **Clean separation of concerns** | TUI logic isolated from runner/executor logic; config validation is comprehensive |
| **State management** | Well-structured model with clear state tracking, dirty detection, and snapshot comparison |
| **Message-driven updates** | Proper Bubble Tea patterns with channels for async communication |
| **Security validation** | Python command/script validation with symlink resolution, path whitelisting, and shell injection prevention |
| **Cross-platform support** | Windows and Unix process management with graceful SIGINT/SIGKILL handling |

### 1.2 User Experience

| Strength | Details |
|----------|---------|
| **Progress visibility** | Visual stepper showing Local → PR → Review phases with real-time status |
| **Live feed** | Real-time log streaming with auto-follow toggle (auto/paused/off modes) |
| **Contextual help** | Per-tab keyboard shortcuts in footer, help overlay with `?` |
| **Toast notifications** | Non-blocking feedback for save/error states |
| **Powerline status bar** | Clear tab/PRD/phase/status indicators at bottom |
| **Quit confirmation** | Prompts when unsaved changes exist |

### 1.3 Configuration System

| Strength | Details |
|----------|---------|
| **Comprehensive validation** | Inter-field validation (e.g., poll interval vs idle grace), branch name validation |
| **Smart defaults** | Only applies defaults to nil/empty fields, preserves explicit zeros |
| **PRD metadata** | Tags and last-used timestamps persist per-PRD |
| **Environment variable support** | 10+ env vars for runtime overrides |
| **Version tracking** | Schema version for future migrations |

### 1.4 Visual Design

| Strength | Details |
|----------|---------|
| **Adaptive colors** | Light/dark terminal detection with `lipgloss.AdaptiveColor` |
| **Grouped settings** | Bordered boxes for Repository, Executors, Timings sections |
| **Split panes** | PRD tab shows file list + preview side-by-side |
| **Keyboard-first** | Full operation via keyboard, no mouse required |

---

## Part 2: Current Weaknesses

### 2.1 Missing Python Script Features (Not Exposed in TUI)

These features exist in `tools/auto_prd_to_pr_v3.py` but are **NOT** accessible through the TUI:

| Feature | Python CLI | Impact |
|---------|-----------|--------|
| **Session Resume** | `--resume`, `--resume-session ID`, `--force-new` | Users cannot resume interrupted runs without CLI |
| **List Sessions** | `--list-sessions` | No visibility into available sessions |
| **Repo Slug Override** | `--repo-slug owner/repo` | Cannot override git remote parsing |
| **Codex Timeout** | `AUTO_PRD_CODEX_TIMEOUT_SECONDS` | No control over execution timeouts |
| **Claude Timeout** | `AUTO_PRD_CLAUDE_TIMEOUT_SECONDS` | No control over execution timeouts |
| **Shell Override** | `AUTO_PRD_ALLOW_NO_ZSH` | Cannot bypass zsh requirement |

### 2.2 Configuration Gaps

| Issue | Details |
|-------|---------|
| **No timeout configuration** | Python supports per-executor timeouts but TUI doesn't expose them |
| **No retry configuration** | `max_retries` is hardcoded in Python |
| **No webhook/notification support** | Can't set up completion notifications |
| **No custom log path** | Log file path is auto-generated, not configurable |
| **Limited PRD filtering** | Tags exist but aren't used for filtering in list |

### 2.3 UX Pain Points

| Issue | Details |
|-------|---------|
| **Single PRD per run** | Cannot queue multiple PRDs or batch process |
| **No partial resume** | After error, must restart from beginning (no phase-level resume in TUI) |
| **Phase dependency unclear** | No warning if PR phase runs without Local completion |
| **Input validation delayed** | Errors only shown on save, not while typing |
| **Split pane ratio fixed** | PRD list/preview split is hardcoded at 0.4 |
| **No log search/filter** | Cannot search within logs in real-time |
| **Tab overflow** | 8 tabs may be too many for narrow terminals |

### 2.4 Information Density Issues

| Tab | Issue |
|-----|-------|
| **Run** | Shows both idle and running states in same view; could benefit from separation |
| **Settings** | All settings in one scrolling view; grouped but dense |
| **Env** | Phase toggles and flags could be better organized |
| **Progress** | Good concept but requires `.aprd/tracker.json` to exist (not auto-generated) |

### 2.5 Missing Features

| Feature | Details |
|---------|---------|
| **Profiles/Presets** | No way to save/load configuration profiles |
| **Recent PRDs** | Tags exist but no "recently used" quick access |
| **Command history** | No history of previous runs or their outcomes |
| **Export/Import config** | No way to share configs between machines |
| **Diff view** | No way to see what changed vs defaults |

---

## Part 3: Improvement Opportunities

### 3.1 High-Priority Additions (Missing Core Features)

#### 3.1.1 Session Management Tab/Section
**Goal:** Expose Python's session/checkpoint system

```
Proposed Features:
- List available sessions (from ~/.config/aprd/checkpoints/)
- Resume most recent session
- Resume specific session by ID
- Force new session option
- Show session metadata (PRD hash, last phase, timestamp)
```

**Implementation:** Add "Sessions" sub-section to Run tab or new tab

#### 3.1.2 Timeout Configuration
**Goal:** Control per-executor timeouts

```
Proposed Settings:
- Codex timeout (seconds, or "none" for unlimited)
- Claude timeout (seconds, or "none" for unlimited)
- Global timeout for entire run
```

**Implementation:** Add to Timings group in Settings tab

#### 3.1.3 Phase Resume
**Goal:** Start from any phase, not just beginning

```
Proposed UI:
- When error occurs in a phase, offer "Retry phase" vs "Start over"
- Phase selector: "Start from: [Local] [PR] [Review]"
- Preserve state from completed phases
```

**Implementation:** Extend Run tab with phase picker when previous run exists

### 3.2 Medium-Priority Improvements (UX Enhancements)

#### 3.2.1 PRD Quick Actions
- **Recent PRDs:** Show 5 most recently used at top of list
- **Tag filtering:** Filter PRD list by tags
- **Favorites:** Star/pin frequently used PRDs
- **Search:** Real-time search across PRD names/content

#### 3.2.2 Settings Organization
- **Tabs within Settings:** Split into "Core", "Executors", "Timings", "Advanced"
- **Inline validation:** Show errors/warnings as user types
- **Diff from defaults:** Highlight non-default values
- **Reset to defaults:** Per-field or all-fields reset

#### 3.2.3 Run Dashboard Enhancements
- **Estimated time:** Based on historical runs
- **Cost estimation:** Approximate API costs (if available)
- **Progress percentage:** Show completion % within phase
- **Abort with resume:** Save checkpoint before abort

#### 3.2.4 Log Improvements
- **Search:** Find text within logs
- **Filter by level:** DEBUG/INFO/WARN/ERROR toggles
- **Export:** Save current logs to file
- **Tail mode:** Auto-follow with manual scroll lock

### 3.3 Lower-Priority Additions (Nice-to-Have)

#### 3.3.1 Configuration Profiles
```
Features:
- Save current config as named profile
- Load profile from list
- Export/import profiles as YAML
- "Dev", "Prod", "Quick Test" presets
```

#### 3.3.2 Run History
```
Features:
- List of past 10-20 runs with outcomes
- Re-run with same settings
- Compare run durations
- View logs from past runs
```

#### 3.3.3 Notifications
```
Features:
- Desktop notification on completion
- Webhook URL for external notifications
- Sound alert option
- Slack/Discord integration
```

#### 3.3.4 Advanced Mode Toggle
```
Features:
- "Simple" view: Only essential options
- "Advanced" view: All configuration options
- Hide batch processing, UI tuning in simple mode
```

---

## Part 4: Options to Consider Removing

### 4.1 Candidates for Simplification

| Current Option | Recommendation | Rationale |
|----------------|----------------|-----------|
| **Batch Processing settings** | Move to config file only | Power-user setting, rarely changed |
| **UI settings (max_log_lines, toast_ttl)** | Move to config file only | Implementation detail |
| **Python command customization** | Default with override in config | Rarely needed |
| **Python script path** | Auto-detect with validation | Users shouldn't need to set this |

### 4.2 Tab Consolidation Options

| Current Structure | Alternative | Trade-offs |
|-------------------|-------------|------------|
| 8 tabs | Merge Env + Settings | Less navigation, more scrolling |
| Separate Progress tab | Integrate into Run | Reduces tabs, but crowds Run |
| Separate Help tab | Keep as overlay only | Help is rarely a "primary" destination |

---

## Part 5: Recommended Priorities

### Phase 1: Critical Gaps (Immediate)
1. **Session resume UI** - Users currently lose progress on interruption
2. **Timeout configuration** - Missing safety net for hung executions
3. **Phase-level retry** - Avoid full restart on late-stage errors

### Phase 2: UX Polish (Short-term)
4. **PRD search/filter** - Faster PRD selection
5. **Log search** - Debug faster with searchable logs
6. **Inline validation** - Better error feedback

### Phase 3: Power Features (Medium-term)
7. **Configuration profiles** - Quick switching between setups
8. **Run history** - Track and compare past runs
9. **Notifications** - Know when long runs complete

### Phase 4: Advanced (Long-term)
10. **Multi-PRD batching** - Process multiple PRDs in sequence
11. **Simple/Advanced mode** - Hide complexity for new users
12. **Cost estimation** - Track API usage

---

## Part 6: Specific Design Recommendations

### 6.1 Session Management Integration

**Option A: Dedicated Tab**
```
Tab 8: Sessions
- List view of available sessions
- Session details (PRD, phase, timestamp)
- Resume/Delete actions
```

**Option B: Run Tab Integration**
```
Run Tab:
- Add "Previous Sessions" section
- Show resume option when starting new run
- Checkbox: [ ] Resume from checkpoint
```

**Recommendation:** Option B - integrates naturally with run workflow

### 6.2 Settings Reorganization

**Current:**
```
Settings Tab:
├── Repository (3 inputs)
├── Executors (7 inputs + 3 toggles)
└── Timings (4 inputs)
```

**Proposed:**
```
Settings Tab with sub-navigation:
├── [1] Core
│   ├── Repository
│   └── Branch
├── [2] Executors
│   ├── Model
│   ├── Policy
│   └── Per-phase toggles
├── [3] Timings
│   ├── Wait/Poll/Idle
│   ├── Max iterations
│   └── NEW: Timeouts
└── [4] Advanced (hidden by default)
    ├── Python paths
    ├── Batch processing
    └── Log settings
```

### 6.3 Env Tab Enhancement

**Current:** Phase toggles + 4 flags in single view

**Proposed:**
```
Env Tab:
├── Phases
│   ├── [L] Local: enabled/disabled
│   ├── [P] PR: enabled/disabled
│   └── [R] Review: enabled/disabled
├── Execution Mode
│   ├── [a] Allow Unsafe
│   └── [d] Dry Run
├── Git Options
│   ├── [g] Sync Git
│   └── NEW: [f] Force New Session
└── Review Options
    ├── [i] Infinite Reviews
    └── NEW: Auto-approve trivial
```

---

## Part 7: Technical Considerations

### 7.1 Backward Compatibility
- Config schema versioning already exists (v1.0.0)
- New fields should have sensible defaults
- Existing configs should work without migration

### 7.2 Code Organization
- New session management logic should go in `internal/session/`
- Timeout config should extend `config.Config.Timings`
- Search/filter should use existing list.Model filtering

### 7.3 Testing Requirements
- Unit tests for new config validation
- Integration tests for session resume flow
- E2E tests for timeout behavior

---

## Appendix A: Configuration Fields Summary

### Currently Exposed (30+ fields)
- Repository: repo_path, base_branch, branch
- Executors: policy, codex_model, python_command, python_script, phase_executors.{implement,fix,pr,review_fix}
- Phases: local, pr, review_fix
- Flags: allow_unsafe, dry_run, sync_git, infinite_reviews
- Timings: wait_minutes, review_poll_seconds, idle_grace_minutes, max_local_iters
- Batch: max_batch_size, batch_timeout_ms, log_channel_buffer
- UI: max_log_lines, toast_ttl_ms

### Recommended Additions
- Timings: codex_timeout_seconds, claude_timeout_seconds
- Sessions: auto_resume, checkpoint_retention_days
- Notifications: notification_webhook, desktop_notify

### Recommended for Config-Only (Remove from UI)
- Batch processing settings
- UI tuning settings (toast_ttl, max_log_lines)
- Python paths (unless error)

---

## Appendix B: Keyboard Shortcut Recommendations

### Current Global Keys
```
1-8: Tab navigation
?: Help
Ctrl+S: Save
q: Quit
Ctrl+C: Cancel/Force quit
```

### Proposed Additions
```
Ctrl+R: Resume last session (from Run tab)
Ctrl+F: Focus search/filter
Ctrl+L: Clear current view
/: Quick command palette (vim-style)
```

---

## Conclusion

The TUI is fundamentally sound with good architecture and UX foundations. The main gaps are:

1. **Feature parity with Python CLI** - Session management is the biggest gap
2. **Timeout/safety controls** - Missing important safeguards
3. **Search/filter capabilities** - Needed for larger PRD sets and log analysis
4. **Configuration complexity** - Could benefit from progressive disclosure

Addressing these would significantly improve the tool's usability without requiring architectural changes.
