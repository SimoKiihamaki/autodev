package tui

import (
	"strings"
)

// renderPromptView renders the Initial Prompt tab content.
func renderPromptView(b *strings.Builder, m model) {
	b.WriteString(sectionTitle.Render("Initial Prompt (optional)") + "\n")
	b.WriteString(m.prompt.View() + "\n")

	if m.prompt.Focused() {
		b.WriteString(okStyle.Render("Text area focused (Esc to blur)") + "\n")
	} else {
		b.WriteString("Press Enter to edit text, Esc to blur\n")
	}
}
