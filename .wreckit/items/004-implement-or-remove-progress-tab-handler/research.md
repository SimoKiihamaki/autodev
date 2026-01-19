# Research: Implement or remove Progress tab handler

**Date**: 2026-01-19
**Item**: 004-implement-or-remove-progress-tab-handler

## Research Question
Users can navigate to the Progress tab but key bindings do nothing because handleProgressTabActions() function is missing.

**Motivation:** Either completes the Progress tab feature or removes dead code that confuses users.

**Technical constraints:**
- Either implement handleProgressTabActions() in update_keys.go or remove the unused tab entirely

**Signals:** priority: critical

## Summary
**FINDING: This issue has already been resolved.** The `handleProgressTabActions()` function exists and is properly integrated into the codebase. The Progress tab is fully functional with refresh, navigation, and confirm actions implemented. The CODEBASE_ANALYSIS_REPORT.md (generated 2026-01-19) contains outdated information (CRITICAL-004) that does not reflect the current state of the code.

**Key Discovery:** The handler was added in commit `98a50a3` on November 27, 2025, nearly two months before the report was generated. The Progress tab is a complete feature that:
- Displays implementation tracker data from `.aprd/tracker.json`
- Supports refresh functionality (key: `u`)
- Has placeholder handlers for navigation (up/down arrows)
- Integrates with the async tracker loading system
- Is properly wired into the TUI's key handling dispatch

**Recommendation:** This item should be **closed as resolved** with a note to update the CODEBASE_ANALYSIS_REPORT.md to remove the outdated CRITICAL-004 entry.

## Current State Analysis

### Existing Implementation

The Progress tab handler **exists and is functional**:

**File**: `internal/tui/keys_progress.go:6-34`
- Implements `handleProgressTabActions(actions []Action, msg tea.KeyMsg) (bool, tea.Cmd)`
- Handles `ActRefresh` - reloads tracker data asynchronously
- Handles `ActNavigateUp/Down` - placeholder for future scrolling
- Handles `ActConfirm` - placeholder for future feature expansion
- Properly returns `(bool, tea.Cmd)` tuple following Bubble Tea patterns

**Integration**:
- `internal/tui/update_keys.go:74-75` - Handler is dispatched in the `handleTabActions()` switch statement
- `internal/tui/keys.go:404-408` - Key bindings defined (u=refresh, up/down=navigate)
- `internal/tui/tabs.go:15,26` - Tab is registered in default tab specs
- `internal/tui/view_progress.go:92-109` - Complete view rendering implementation
- `internal/tui/messages.go:55-59` - Message type for async tracker loading
- `internal/tui/update.go:100-104` - Message handler updates model state

### Key Files

**Progress Tab Handler**:
- `internal/tui/keys_progress.go:6` - `handleProgressTabActions()` function implementation
- `internal/tui/keys_progress.go:16-23` - Refresh action loads tracker asynchronously via `loadTrackerCmd(m.cfg.RepoPath)`

**Key Bindings**:
- `internal/tui/keys.go:404-408` - Progress tab key mappings:
  - `u` → ActRefresh (reload tracker data)
  - `↑/↓` → ActNavigateUp/Down (future scrolling)
  - ActRefresh label: `keys.go:456` - "Refresh"

**View Rendering**:
- `internal/tui/view_progress.go:92-109` - `renderProgressView()` main renderer
- `internal/tui/view_progress.go:136-177` - `renderTrackerOverview()` displays metadata and progress summary
- `internal/tui/view_progress.go:180-198` - `renderFeatureList()` shows all features with status icons
- `internal/tui/view_progress.go:201-204` - `renderProgressFooter()` shows help text ("Press u to refresh")

**Data Loading**:
- `internal/tui/view_progress.go:64-81` - `loadTracker()` reads `.aprd/tracker.json` from repo
- `internal/tui/view_progress.go:84-89` - `loadTrackerCmd()` returns async tea.Cmd
- `internal/tui/view_progress.go:56-59` - `trackerLoadedMsg` delivers loaded tracker to Update loop

**Message Handling**:
- `internal/tui/update.go:100-104` - Handles `trackerLoadedMsg`, updates model state
- `internal/tui/model.go:219-222` - Tracker state fields: `tracker`, `trackerErr`, `trackerLoaded`

**Tab Integration**:
- `internal/tui/tabs.go:15` - `tabIDProgress = "progress"` constant
- `internal/tui/tabs.go:26` - Progress tab in default tab specs
- `internal/tui/update_keys.go:74-75` - Handler dispatch in switch statement

## Technical Considerations

### Dependencies
- **External**: None (uses only Bubbletea v3+)
- **Internal modules**:
  - `github.com/SimoKiihamaki/autodev/internal/config` - Config struct (RepoPath field)
  - Tracker JSON format defined in `view_progress.go:13-61`

### Patterns to Follow
The implementation follows established patterns in the codebase:

**Tab Handler Pattern** (consistent across all tabs):
1. Handler function in separate file: `keys_<tab>.go`
2. Returns `(bool, tea.Cmd)` tuple
3. Iterates through actions, uses switch statement
4. Sets `handled = true` and optionally returns `cmd`

**Async Loading Pattern**:
1. Command function returns `tea.Cmd`: `loadTrackerCmd()`
2. Message type defined in `messages.go`: `trackerLoadedMsg`
3. Update loop handles message: `update.go:100-104`
4. State tracked in model: `trackerLoaded`, `tracker`, `trackerErr`

**View Rendering Pattern**:
1. Main renderer: `renderProgressView()`
2. Helper renderers: `renderTrackerOverview()`, `renderFeatureList()`
3. Footer with help: `renderProgressFooter()`

## Current Functionality

### Working Features
1. **Tab Navigation**: Users can switch to Progress tab (key: `7` or click)
2. **Async Tracker Loading**: Automatically loads when tab first accessed
3. **Refresh** (key: `u`): Reloads tracker data from disk
4. **View Display**: Shows metadata, progress summary, and feature list
5. **Error Handling**: Gracefully displays errors and instructions for creating tracker
6. **Help Integration**: Progress tab actions shown in Help overlay

### Placeholder Features
The following actions are handled but only marked as placeholders for future work:
- **Navigation** (↑/↓): Comment says "Future: scroll through feature list"
- **Confirm** (Enter): Comment says "Future: expand feature details"

These are **not bugs** - they intentionally return `handled = true` to prevent unhandled key warnings, with the understanding that the features will be implemented later.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Outdated documentation** (CODEBASE_ANALYSIS_REPORT.md) | Low | Update report to remove CRITICAL-004 entry |
| **Missing test coverage** for Progress tab | Medium | Add tests in `keys_progress_test.go` for refresh, navigation actions |
| **Placeholder actions** (nav/confirm) might confuse users | Low | Add comments in code or disable until implemented |

## Recommended Approach

### For This Item
**STATUS: RESOLVED** - Close this item as "already implemented".

The Progress tab handler exists and works correctly. The issue report is based on outdated analysis from CODEBASE_ANALYSIS_REPORT.md (generated 2026-01-19), which doesn't reflect the state after commit 98a50a3 (2025-11-27).

### Follow-up Actions
1. **Update CODEBASE_ANALYSIS_REPORT.md**: Remove or correct CRITICAL-004 entry
2. **Add test coverage** (optional improvement):
   - Create `internal/tui/keys_progress_test.go`
   - Test refresh action triggers `loadTrackerCmd`
   - Test navigation actions are handled
   - Test error states

### Future Enhancement Opportunities
If the team wants to expand Progress tab functionality:
1. **Implement feature list scrolling** (ActNavigateUp/Down)
   - Add scroll state to model: `progressScrollOffset int`
   - Render viewport with scrolling
2. **Implement feature detail expansion** (ActConfirm)
   - Add selection state: `selectedFeatureID string`
   - Show detailed view when feature selected
3. **Add keyboard shortcuts for common actions**
   - `r` - switch to feature list view
   - `d` - show feature details
   - `b` - go back to summary

## Implementation Details

### Handler Flow
```
User presses 'u' in Progress tab
    ↓
handleKeyMsg() (update_keys.go:22)
    ↓
keys.TabActions(tabIDProgress, msg) returns [ActRefresh]
    ↓
handleTabActions() dispatches to handleProgressTabActions()
    ↓
keys_progress.go:16-23 handles ActRefresh
    ↓
Sets trackerLoaded=false, clears tracker state, sets status
    ↓
Returns loadTrackerCmd(m.cfg.RepoPath)
    ↓
Async load executes, sends trackerLoadedMsg
    ↓
update.go:100-104 handles message, updates model
    ↓
View re-renders with new data
```

### Data Flow
```
.aprd/tracker.json (on disk)
    ↓
loadTracker() reads file (view_progress.go:64)
    ↓
JSON unmarshal into Tracker struct
    ↓
trackerLoadedMsg delivers to Update loop
    ↓
model.tracker, model.trackerErr, model.trackerLoaded updated
    ↓
renderProgressView() uses model.tracker to display
```

## Open Questions

**None** - The handler is fully implemented and functional.

### Clarification Needed
None. The issue report is based on stale analysis.

## Evidence

### Git History
- **Commit 98a50a3** (2025-11-27): "fix: address CodeRabbit review findings (#53)"
  - Added `internal/tui/keys_progress.go` with complete handler implementation
  - This commit added 34 lines implementing the full handler

### Compilation Status
- Project builds successfully: `go build ./cmd/aprd` completes without errors
- No compilation errors related to Progress tab

### Test Status
- No specific Progress tab tests exist (but no tests fail either)
- Test pattern: Other tabs have `keys_<tab>_test.go` files
- Opportunity: Add `keys_progress_test.go` for completeness

## Conclusion

The Progress tab handler is **fully implemented and functional**. This item should be closed with the following notes:

1. **Status**: RESOLVED - Implementation completed 2025-11-27
2. **Action Required**: Update CODEBASE_ANALYSIS_REPORT.md to remove CRITICAL-004
3. **Optional Enhancement**: Add test coverage in `keys_progress_test.go`
4. **Future Work**: Implement placeholder navigation and detail expansion features when needed

The report that triggered this item was based on outdated analysis. The codebase is in a good state with the Progress tab working as designed.
