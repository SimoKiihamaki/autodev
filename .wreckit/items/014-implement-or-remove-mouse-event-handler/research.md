# Research: Implement or remove mouse event handler

**Date**: 2025-01-19
**Item**: 014-implement-or-remove-mouse-event-handler

## Research Question
Mouse events are captured but not handled, potentially confusing users who try to interact via mouse.

**Motivation:** Either completes mouse support feature or removes unnecessary event handling code.

**Technical constraints:**
- Either implement mouse handling functionality or remove the case if not needed

**Signals:** priority: high

## Summary
The TUI application currently captures mouse events in the `Update` function but does nothing with them (lines 29-30 in `/Users/simo/Projects/autodev/internal/tui/update.go`). This is a stub implementation that was likely added for future mouse support but never completed. The application is a keyboard-driven TUI with no existing mouse interactions, and mouse events are not even enabled in the Bubble Tea program initialization. **Recommendation: Remove the mouse event handler case** as it serves no purpose and creates confusion. If mouse support is desired in the future, it should be properly designed and implemented as a feature with clear requirements.

## Current State Analysis

### Existing Implementation
The mouse event handler is a no-op stub in the update loop:
- **File**: `/Users/simo/Projects/autodev/internal/tui/update.go:29-30`
- **Code**:
  ```go
  case tea.MouseMsg:
      return m, nil
  ```
- This case receives mouse events but immediately returns without any processing
- Mouse events are **not enabled** in the program initialization (missing `tea.WithMouseCell()` option)
- The application is entirely keyboard-driven with comprehensive keyboard shortcuts

### Current Architecture
The application is a sophisticated TUI built with Bubble Tea featuring:

**Tab System** (8 tabs):
- Run, PRD, Settings, Env, Prompt, Logs, Progress, Help
- Keyboard navigation: 1-8 keys to switch tabs
- Tab navigation: Tab/Shift+Tab to cycle through fields

**Interactive Components**:
- `list.Model` for PRD selection (keyboard navigation with arrows, enter to select)
- `viewport.Model` for logs and previews (keyboard scrolling with PgUp/PgDn, Home/End)
- `textinput.Model` for settings fields (keyboard typing and navigation)
- `textarea.Model` for prompt input (keyboard typing)

**Keyboard-First Design**:
- Comprehensive keymap system in `/Users/simo/Projects/autodev/internal/tui/keys.go`
- Global actions: quit (q), interrupt (Ctrl+C), help (?/F1), save (Ctrl+S)
- Tab-specific actions with contextual help footers
- Typing-sensitive mode that blocks global shortcuts when editing text

## Key Files

### Core TUI Files
- `/Users/simo/Projects/autodev/internal/tui/update.go:29-30` - **Mouse event stub (THE ISSUE)**
- `/Users/simo/Projects/autodev/internal/tui/model.go:114-224` - Model struct definition with all UI components
- `/Users/simo/Projects/autodev/internal/tui/keys.go:1-483` - Comprehensive keymap system
- `/Users/simo/Projects/autodev/cmd/aprd/main.go:11-14` - Program initialization (missing mouse enable)

### View Components
- `/Users/simo/Projects/autodev/internal/tui/view.go:108-163` - Main view rendering with tab bar
- `/Users/simo/Projects/autodev/internal/tui/components.go:1-335` - Custom UI components (Stepper, BorderedBox, SplitPane, ToggleGroup)
- `/Users/simo/Projects/autodev/internal/tui/view_prd.go:1-44` - PRD tab with split-pane layout
- `/Users/simo/Projects/autodev/internal/tui/view_settings.go:1-189` - Settings tab with form inputs

## Technical Considerations

### Dependencies
- **External**: `github.com/charmbracelet/bubbletea` (v0.25+), `github.com/charmbracelet/bubbles/list`, `github.com/charmbracelet/bubbles/viewport`, `github.com/charmbracelet/bubbles/textinput`, `github.com/charmbracelet/bubbles/textarea`
- **Internal**: `internal/config`, `internal/runner`, `internal/utils`

### Bubble Tea Mouse Support
To enable mouse events, Bubble Tea requires:
1. **Program initialization**: `tea.WithMouseCell()` option in `tea.NewProgram()`
2. **Event handling**: Process `tea.MouseMsg` in the `Update` function
3. **Event types**: Mouse clicks, scroll wheel, drag events with position data

### Patterns to Follow
The codebase follows these patterns:
- **Message type switching**: Each message type has its own case and handler function
- **Handler functions**: `handleResize()`, `handleKeyMsg()`, `handleLogBatch()`, `handleRunFinish()`
- **State mutations**: Handlers return updated model and optional commands
- **Component delegation**: List, viewport, and text components handle their own events

## Mouse Support Implementation Options

### Option 1: Remove the Handler (RECOMMENDED)
**Pros**:
- Removes dead code that serves no purpose
- Eliminates confusion about mouse support
- Simplifies the codebase
- No maintenance burden

**Cons**:
- None - mouse is not currently enabled or advertised

**Implementation**:
Simply delete lines 29-30 from `update.go`

### Option 2: Implement Full Mouse Support
**Pros**:
- Could improve usability for mouse users
- Modern TUIs often support both keyboard and mouse

**Cons**:
- Significant development effort required
- Requires careful design for all interactive components
- Adds complexity to keyboard-first UX
- Potential accessibility concerns

**Implementation Requirements**:
1. **Enable mouse events**: Add `tea.WithMouseCell()` to `main.go`
2. **Design interactions**:
   - Tab switching (click on tab bar)
   - List item selection (click on PRD list)
   - Text input focus (click on input fields)
   - Button/toggle activation (click on toggles)
   - Viewport scrolling (scroll wheel)
   - Link/button clicks (if added)
3. **Update each component's view**:
   - Add visual feedback for hover state
   - Maintain focus indicators
   - Handle coordinate tracking
4. **Test thoroughly**: Ensure mouse doesn't break keyboard workflows

### Option 3: Implement Limited Mouse Support
**Pros**:
- Lower implementation effort
- Can add specific high-value interactions (e.g., tab switching, viewport scrolling)

**Cons**:
- Partial implementation may be inconsistent
- Users might expect full mouse support

**Implementation**: Start with scrolling in viewports and tab switching, test user response

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Breaking existing keyboard workflows | High | If implementing mouse, ensure all keyboard shortcuts continue to work; add tests |
| Accessibility issues | Medium | Mouse should never be required; keyboard must remain fully functional |
| Performance degradation | Low | Mouse events are lightweight; Bubble Tea handles them efficiently |
| User confusion | Low | If removing stub, no user impact. If adding mouse, update help text and documentation |
| Terminal compatibility | Medium | Some terminals don't support mouse; always provide keyboard alternative |

## Recommended Approach

### Primary Recommendation: **Remove the Mouse Event Handler**

**Rationale**:
1. **No current value**: The handler does nothing and mouse is not enabled
2. **Keyboard-first design**: The application is comprehensively designed for keyboard use with excellent keybindings
3. **No user demand**: The issue was filed internally, not by users requesting mouse support
4. **Future flexibility**: Removing the stub doesn't prevent future mouse support; it just removes dead code
5. **Low effort**: Simple deletion with no risk

**Implementation Steps**:
1. Delete lines 29-30 from `/Users/simo/Projects/autodev/internal/tui/update.go`
2. Verify tests still pass (the handler currently does nothing, so tests should be unaffected)
3. No documentation changes needed (mouse was never documented)

### Alternative: If Mouse Support is Desired

**Requirements Phase**:
1. Define which mouse interactions are valuable (recommend starting with tab switching and viewport scrolling)
2. Create a design document showing mouse click zones and interactions
3. Consider accessibility implications
4. Plan testing strategy

**Implementation Phase**:
1. Enable mouse events in `main.go` with `tea.WithMouseCell()`
2. Add handler function `handleMouseMsg(msg tea.MouseMsg)` following existing patterns
3. Implement interactions incrementally:
   - Phase 1: Viewport scrolling (most valuable, least complex)
   - Phase 2: Tab switching (high value, medium complexity)
   - Phase 3: List item selection (medium value, medium complexity)
   - Phase 4: Input focus (lower value, high complexity)
4. Update help text to document mouse interactions
5. Add tests for mouse handling
6. Update README with mouse support documentation

## Open Questions

1. **User feedback**: Do actual users want mouse support? The current keyboard interface is well-designed and efficient.
2. **Scope**: If implementing mouse, which interactions are most valuable? A user survey or interview would be helpful.
3. **Accessibility**: Will mouse support impact users who rely on keyboard-only navigation or screen readers?
4. **Terminal support**: Which terminal emulators properly support mouse events? This affects the user base that can benefit.

## Conclusion

The mouse event handler is currently dead code that should be removed. The application is well-designed as a keyboard-first TUI with comprehensive keyboard shortcuts. If mouse support is to be added in the future, it should be properly designed as a feature with clear requirements, not just a stub handler. The recommended action is to **remove the mouse event case** from `update.go`.
