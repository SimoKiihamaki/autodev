package tui

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/lipgloss"
)

const focusedBgColor = "240"

// toggleSeparator defines the spacing between toggle groups (toggles).
// The double space is intentional to provide clear visual separation between toggle groups in the TUI;
// a single space does not provide enough separation for readability and aesthetics.
const toggleSeparator = "  "

// footerActions defines priority actions per tab for the contextual help footer.
var footerActions = map[string][]Action{
	tabIDRun:      {ActConfirm, ActToggleFollow, ActCopyError, ActQuit},
	tabIDPRD:      {ActConfirm, ActFocusTags, ActRescanPRDs, ActSave},
	tabIDSettings: {ActNavigateDown, ActConfirm, ActCancel, ActSave},
	tabIDEnv:      {ActConfirm, ActNavigateDown, ActSave},
	tabIDPrompt:   {ActConfirm, ActCancel, ActSave},
	tabIDLogs:     {ActToggleFollow, ActScrollBottom, ActPageDown},
	tabIDProgress: {ActRefresh, ActNavigateDown, ActQuit},
	tabIDHelp:     {ActQuit, ActHelp},
}

// focusStyle returns a style with background highlighting if active.
func focusStyle(active bool) lipgloss.Style {
	style := lipgloss.NewStyle()
	if active {
		style = style.Background(lipgloss.Color(focusedBgColor))
	}
	return style
}

// renderContextualFooter generates a context-sensitive help footer for the current tab.
func renderContextualFooter(tabID string, keys KeyMap) string {
	actions, ok := footerActions[tabID]
	if !ok || len(actions) == 0 {
		return ""
	}

	var parts []string
	for _, act := range actions {
		keyLabel := actionKeyLabel(keys, tabID, act)
		if keyLabel == "" {
			continue
		}
		actionLabel := keys.Label(act)
		parts = append(parts, fmt.Sprintf("%s %s", keyLabel, actionLabel))
	}

	if len(parts) == 0 {
		return ""
	}

	return helpStyle.Render(strings.Join(parts, " · "))
}

// tabShortcutLabel returns the keyboard shortcut label for a tab index.
func tabShortcutLabel(keys KeyMap, idx int) string {
	if act, ok := gotoTabAction(idx); ok {
		if combos := keys.Global[act]; len(combos) > 0 {
			labels := make([]string, 0, len(combos))
			for _, combo := range combos {
				labels = append(labels, combo.Display())
			}
			return strings.Join(labels, "/")
		}
	}
	return fmt.Sprintf("%d", idx+1)
}

// actionKeyLabel returns the key label(s) for an action in a given tab context.
func actionKeyLabel(keys KeyMap, tabID string, act Action) string {
	var combos []KeyCombo
	if keys.PerTab != nil {
		if perTab := keys.PerTab[tabID]; perTab != nil {
			combos = perTab[act]
		}
	}
	if len(combos) == 0 {
		combos = keys.Global[act]
	}
	if len(combos) == 0 {
		return ""
	}
	labels := make([]string, 0, len(combos))
	for _, combo := range combos {
		labels = append(labels, combo.Display())
	}
	return strings.Join(labels, "/")
}

// annotateUnsaved appends "[unsaved]" indicator if dirty.
func annotateUnsaved(text string, dirty bool) string {
	if !dirty {
		return text
	}
	if strings.Contains(text, "[unsaved]") || strings.Contains(text, "[Unsaved]") {
		return text
	}
	return text + " [unsaved]"
}

// View renders the complete TUI view.
func (m model) View() string {
	var b strings.Builder

	// Render title
	title := "autodev — PRD→PR TUI"
	if m.dirty {
		title += " [unsaved]"
	}
	b.WriteString(titleStyle.Render(title) + "\n")

	// Render tab bar
	for i, tabID := range m.tabs {
		shortcuts := tabShortcutLabel(m.keys, i)
		label := fmt.Sprintf("[%s] %s  ", shortcuts, tabTitle(tabID))
		if i == m.tabIndex {
			b.WriteString(tabActive.Render(label))
			continue
		}
		b.WriteString(tabInactive.Render(label))
	}
	b.WriteString("\n\n")

	// Dispatch to tab-specific view
	switch m.currentTabID() {
	case tabIDRun:
		renderRunView(&b, m)
	case tabIDPRD:
		renderPRDView(&b, m)
	case tabIDSettings:
		renderSettingsView(&b, m)
	case tabIDEnv:
		renderEnvView(&b, m)
	case tabIDPrompt:
		renderPromptView(&b, m)
	case tabIDLogs:
		renderLogsView(&b, m)
	case tabIDProgress:
		renderProgressView(&b, m)
	case tabIDHelp:
		renderHelpView(&b, m)
	}

	// Render quit confirmation dialog if active
	if m.quitConfirmActive {
		renderQuitConfirmation(&b, m)
	}

	// Render help overlay if active
	renderHelpOverlay(&b, m)

	// Render status bar
	renderStatusBar(&b, m)

	return b.String()
}

// renderQuitConfirmation renders the quit confirmation dialog.
func renderQuitConfirmation(b *strings.Builder, m model) {
	b.WriteString("\n")
	b.WriteString(errorStyle.Render("Unsaved changes detected. Choose how to quit:") + "\n")
	labels := make([]string, len(quitOptions))
	for i, opt := range quitOptions {
		label := fmt.Sprintf("[%s]", opt)
		if i == m.quitConfirmIndex {
			labels[i] = okStyle.Render(label)
		} else {
			labels[i] = helpStyle.Render(label)
		}
	}
	b.WriteString(strings.Join(labels, "  ") + "\n")
	b.WriteString(helpStyle.Render("Left/Right cycle · Enter confirm · Esc cancel") + "\n")
}

// renderStatusBar renders the bottom status bar.
func renderStatusBar(b *strings.Builder, m model) {
	segments := []PowerlineSegment{}

	// Tab indicator (left segment)
	tabName := m.tabTitleAt(m.tabIndex)
	segments = append(segments, PowerlineSegment{
		Text:  tabName,
		Style: powerlineLeftStyle,
	})

	// PRD indicator (if selected)
	if m.selectedPRD != "" {
		prdName := abbreviatePath(m.selectedPRD)
		if len(prdName) > 25 {
			prdName = "..." + prdName[len(prdName)-22:]
		}
		segments = append(segments, PowerlineSegment{
			Text:  prdName,
			Style: powerlineCenterStyle,
		})
	}

	// Run phase indicator (if running)
	if m.running && m.runPhase != "" {
		phaseText := m.runPhase
		if m.runIterCurrent > 0 {
			if m.runIterTotal > 0 {
				phaseText = fmt.Sprintf("%s %d/%d", m.runPhase, m.runIterCurrent, m.runIterTotal)
			} else {
				phaseText = fmt.Sprintf("%s %d", m.runPhase, m.runIterCurrent)
			}
		}
		segments = append(segments, PowerlineSegment{
			Text:  phaseText,
			Style: powerlineRightStyle,
		})
	}

	// Status/toast message
	message, style := statusBarMessage(m)
	if message != "" {
		segments = append(segments, PowerlineSegment{
			Text:  message,
			Style: style,
		})
	}

	// Render the powerline bar
	if len(segments) > 0 {
		if b.Len() > 0 {
			b.WriteString("\n")
		}
		bar := NewPowerlineBar(segments)
		b.WriteString(bar.Render())
		b.WriteString("\n")
	}
}

// statusBarMessage returns the status bar message and its style.
func statusBarMessage(m model) (string, lipgloss.Style) {
	if m.toast != nil {
		return m.toast.message, classifyStatusStyle(m.toast.message)
	}
	if note := strings.TrimSpace(m.status); note != "" {
		return annotateUnsaved(note, m.dirty), classifyStatusStyle(note)
	}
	if m.dirty {
		return "Unsaved changes pending — press Ctrl+S to save", statusWarnStyle
	}
	return "", lipgloss.NewStyle()
}

// classifyStatusStyle determines the style for a status message based on keywords.
func classifyStatusStyle(text string) lipgloss.Style {
	lower := strings.ToLower(text)
	switch {
	case strings.Contains(lower, "error"),
		strings.Contains(lower, "fail"),
		strings.Contains(lower, "panic"):
		return statusErrorStyle
	case strings.Contains(lower, "warn"):
		return statusWarnStyle
	case strings.Contains(lower, "saved"),
		strings.Contains(lower, "success"),
		strings.Contains(lower, "completed"),
		strings.Contains(lower, "finished"):
		return statusSuccessStyle
	case strings.Contains(lower, "cancel"),
		strings.Contains(lower, "pending"),
		strings.Contains(lower, "unsaved"):
		return statusWarnStyle
	default:
		return statusInfoStyle
	}
}
