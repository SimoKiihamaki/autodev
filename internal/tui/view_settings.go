package tui

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/lipgloss"
)

// Executor label constants to maintain single source of truth.
const (
	executorLocalLabel  = "Local Loop"
	executorPRLabel     = "PR Push"
	executorReviewLabel = "Review Fix"
)

// toggleHint is the help text for toggling executors.
const toggleHint = "Enter/Space to switch Codex/Claude"

// inputFocusHelpTemplate expects the input name as the first argument.
const inputFocusHelpTemplate = "Input focused: %s (↑/↓/←/→ to navigate, Enter/Esc to blur)"

// renderSettingsView renders the Settings tab content.
func renderSettingsView(b *strings.Builder, m model) {
	b.WriteString(sectionTitle.Render("Settings") + "\n\n")

	renderRepositoryGroup(b, m)
	renderExecutorsGroup(b, m)
	renderTimingsGroup(b, m)
	renderSettingsHelp(b, m)
}

// renderRepositoryGroup renders the repository settings group.
func renderRepositoryGroup(b *strings.Builder, m model) {
	repoContent := lipgloss.JoinVertical(lipgloss.Left,
		m.inRepo.View(),
		m.inBase.View(),
		m.inBranch.View(),
	)
	repoBox := NewBorderedBox("Repository", repoContent)
	repoBox.Focused = isInSettingsGroup(m.focusedInput, []string{"repo", "base", "branch"})
	b.WriteString(repoBox.Render() + "\n\n")
}

// renderExecutorsGroup renders the executor settings group.
func renderExecutorsGroup(b *strings.Builder, m model) {
	localToggle := renderExecutorToggle(executorLocalLabel, m.execLocalChoice, m.focusedInput == "toggleLocal")
	prToggle := renderExecutorToggle(executorPRLabel, m.execPRChoice, m.focusedInput == "togglePR")
	reviewToggle := renderExecutorToggle(executorReviewLabel, m.execReviewChoice, m.focusedInput == "toggleReview")
	togglesLine := localToggle + toggleSeparator + prToggle + toggleSeparator + reviewToggle

	execContent := lipgloss.JoinVertical(lipgloss.Left,
		m.inCodexModel.View(),
		m.inPyCmd.View(),
		m.inPyScript.View(),
		m.inPolicy.View(),
		togglesLine,
	)
	execBox := NewBorderedBox("Executors", execContent)
	execBox.Focused = isInSettingsGroup(m.focusedInput, []string{"codex", "pycmd", "pyscript", "policy", "toggleLocal", "togglePR", "toggleReview"})
	b.WriteString(execBox.Render() + "\n\n")
}

// renderTimingsGroup renders the timings settings group.
func renderTimingsGroup(b *strings.Builder, m model) {
	timingsRow1 := lipgloss.JoinHorizontal(lipgloss.Top,
		m.inWaitMin.View()+"  ",
		m.inPollSec.View()+"  ",
		m.inIdleMin.View()+"  ",
		m.inMaxIters.View(),
	)
	timingsRow2 := lipgloss.JoinHorizontal(lipgloss.Top,
		m.inCodexTimeout.View()+"  ",
		m.inClaudeTimeout.View(),
	)
	timingsContent := lipgloss.JoinVertical(lipgloss.Left, timingsRow1, timingsRow2)
	timingsBox := NewBorderedBox("Timings", timingsContent)
	timingsBox.Focused = isInSettingsGroup(m.focusedInput, []string{"waitmin", "pollsec", "idlemin", "maxiters", "codextimeout", "claudetimeout"})
	b.WriteString(timingsBox.Render() + "\n")
}

// renderSettingsHelp renders the contextual help for settings.
func renderSettingsHelp(b *strings.Builder, m model) {
	if m.focusedInput != "" {
		if isExecutorToggle(m.focusedInput) {
			b.WriteString("\n" + okStyle.Render(fmt.Sprintf("Toggle focused: %s (%s, arrows to navigate, Esc to blur)", executorToggleLabel(m.focusedInput), toggleHint)) + "\n")
		} else {
			b.WriteString("\n" + okStyle.Render(fmt.Sprintf(inputFocusHelpTemplate, m.focusedInput)) + "\n")
		}
	} else {
		b.WriteString("\n" + overlayHelpSection("Settings", m.keys.HelpEntriesForTab(tabIDSettings)) + "\n")
	}
}

// isInSettingsGroup checks if the focused input is within a settings group.
func isInSettingsGroup(input string, group []string) bool {
	for _, g := range group {
		if input == g {
			return true
		}
	}
	return false
}

// renderExecutorToggle renders a single executor toggle (Codex/Claude).
func renderExecutorToggle(label string, choice executorChoice, focused bool) string {
	codex := renderExecutorOption("Codex", choice == executorCodex)
	claude := renderExecutorOption("Claude", choice == executorClaude)
	line := fmt.Sprintf("%s: %s%s%s", label, codex, toggleSeparator, claude)
	return focusStyle(focused).Render(line)
}

// renderExecutorOption renders a single executor option with selection styling.
func renderExecutorOption(name string, selected bool) string {
	style := lipgloss.NewStyle()
	if selected {
		return style.Bold(true).Render("[" + name + "]")
	}
	return style.Render(name)
}

// executorToggleLabel returns the human-readable label for a toggle name.
func executorToggleLabel(name string) string {
	switch name {
	case "toggleLocal":
		return executorLocalLabel
	case "togglePR":
		return executorPRLabel
	case "toggleReview":
		return executorReviewLabel
	default:
		return name
	}
}
