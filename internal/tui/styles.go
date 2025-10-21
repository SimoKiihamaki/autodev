package tui

import "github.com/charmbracelet/lipgloss"

var (
	colRed    = lipgloss.AdaptiveColor{Light: "#D70000", Dark: "#FF5555"}
	colGreen  = lipgloss.AdaptiveColor{Light: "#008700", Dark: "#50FA7B"}
	colYellow = lipgloss.AdaptiveColor{Light: "#AF8700", Dark: "#F1FA8C"}
	colCyan   = lipgloss.AdaptiveColor{Light: "#0087AF", Dark: "#8BE9FD"}
	colPurple = lipgloss.AdaptiveColor{Light: "#5F00AF", Dark: "#BD93F9"}

	titleStyle      = lipgloss.NewStyle().Bold(true).MarginBottom(1)
	tabActive       = lipgloss.NewStyle().Bold(true).Underline(true)
	tabInactive     = lipgloss.NewStyle().Faint(true)
	sectionTitle    = lipgloss.NewStyle().Bold(true).MarginTop(1).MarginBottom(0)
	helpStyle       = lipgloss.NewStyle().Faint(true)
	errorStyle      = lipgloss.NewStyle().Foreground(colRed)
	okStyle         = lipgloss.NewStyle().Foreground(colGreen)
	borderStyle     = lipgloss.NewStyle().Border(lipgloss.RoundedBorder())
	logInfoStyle    = lipgloss.NewStyle()
	logErrorStyle   = lipgloss.NewStyle().Foreground(colRed).Bold(true)
	logWarnStyle    = lipgloss.NewStyle().Foreground(colYellow).Bold(true)
	logSuccessStyle = lipgloss.NewStyle().Foreground(colGreen).Bold(true)
	logActionStyle  = lipgloss.NewStyle().Foreground(colCyan)
	logSystemStyle  = lipgloss.NewStyle().Foreground(colPurple)
)
