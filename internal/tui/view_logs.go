package tui

import (
	"strings"
)

// renderLogsView renders the Logs tab content.
func renderLogsView(b *strings.Builder, m model) {
	b.WriteString(sectionTitle.Render("Logs") + "\n")

	renderLogFileInfo(b, m)
	b.WriteString(m.logs.View() + "\n")
	b.WriteString(renderContextualFooter(tabIDLogs, m.keys) + "\n")
}

// renderLogFileInfo renders the log file path or status.
func renderLogFileInfo(b *strings.Builder, m model) {
	if m.logFilePath != "" {
		b.WriteString(helpStyle.Render("Persisted at: "+abbreviatePath(m.logFilePath)) + "\n")
	} else if m.logStatus != "" {
		b.WriteString(helpStyle.Render("Log file: "+m.logStatus) + "\n")
	}
}
