package tui

import (
	"strings"

	"github.com/charmbracelet/lipgloss"
)

// renderHelpView renders the Help tab content.
func renderHelpView(b *strings.Builder, m model) {
	b.WriteString(sectionTitle.Render("Help") + "\n")

	writeHelpSection := func(title string, entries []HelpEntry) {
		if len(entries) == 0 {
			return
		}
		b.WriteString("• " + title + ":\n")
		for _, entry := range entries {
			var comboLabels []string
			for _, combo := range entry.Combos {
				comboLabels = append(comboLabels, combo.Display())
			}
			b.WriteString("  - " + entry.Label + ": " + strings.Join(comboLabels, ", ") + "\n")
		}
	}

	writeHelpSection("Global", m.keys.GlobalHelpEntries())

	for _, tabID := range tabIDOrder {
		entries := m.keys.HelpEntriesForTab(tabID)
		if len(entries) == 0 || !m.hasTabID(tabID) {
			continue
		}
		writeHelpSection(tabTitle(tabID), entries)
	}

	b.WriteString("\nSee NAVIGATION_GUIDE.md for detailed instructions.")
}

// renderHelpOverlay renders the help overlay if active.
func renderHelpOverlay(b *strings.Builder, m model) {
	if !m.showHelp {
		return
	}

	panel := buildHelpOverlayContent(m)
	if panel == "" {
		return
	}

	if b.Len() > 0 {
		b.WriteString("\n")
	}
	b.WriteString(panel)
}

// buildHelpOverlayContent builds the help overlay panel content.
func buildHelpOverlayContent(m model) string {
	tabID := m.currentTabID()
	var sections []string

	if global := overlayHelpSection("Global", m.keys.GlobalHelpEntries()); global != "" {
		sections = append(sections, global)
	}

	if tabSection := overlayHelpSection(tabTitle(tabID), m.keys.HelpEntriesForTab(tabID)); tabSection != "" {
		sections = append(sections, tabSection)
	}

	if len(sections) == 0 {
		return ""
	}

	content := lipgloss.JoinVertical(lipgloss.Left, sections...)
	return helpBoxStyle.Render(content)
}

// overlayHelpSection builds a single section for the help overlay.
func overlayHelpSection(title string, entries []HelpEntry) string {
	if len(entries) == 0 {
		return ""
	}

	lines := make([]string, 0, len(entries))
	for _, entry := range entries {
		combos := make([]string, 0, len(entry.Combos))
		for _, combo := range entry.Combos {
			combos = append(combos, combo.Display())
		}
		comboText := strings.Join(combos, " / ")
		line := lipgloss.JoinHorizontal(lipgloss.Left,
			helpKeyStyle.Render(comboText),
			" ",
			helpLabelStyle.Render(entry.Label),
		)
		lines = append(lines, line)
	}

	content := lipgloss.JoinVertical(lipgloss.Left, lines...)
	return lipgloss.JoinVertical(lipgloss.Left,
		helpBoxTitle.Render(title),
		content,
	)
}
