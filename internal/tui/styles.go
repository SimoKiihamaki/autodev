package tui

import "github.com/charmbracelet/lipgloss"

var (
	colRed    = "#FF5555"
	colGreen  = "#50FA7B"
	colYellow = "#F1FA8C"
	colCyan   = "#8BE9FD"
	colPurple = "#BD93F9"

	titleStyle      = lipgloss.NewStyle().Bold(true).MarginBottom(1)
	tabActive       = lipgloss.NewStyle().Bold(true).Underline(true)
	tabInactive     = lipgloss.NewStyle().Faint(true)
	sectionTitle    = lipgloss.NewStyle().Bold(true).MarginTop(1).MarginBottom(0)
	helpStyle       = lipgloss.NewStyle().Faint(true)
	errorStyle      = lipgloss.NewStyle().Foreground(lipgloss.Color(colRed))
	okStyle         = lipgloss.NewStyle().Foreground(lipgloss.Color(colGreen))
	borderStyle     = lipgloss.NewStyle().Border(lipgloss.RoundedBorder())
	logInfoStyle    = lipgloss.NewStyle()
	logErrorStyle   = lipgloss.NewStyle().Foreground(lipgloss.Color(colRed)).Bold(true)
	logWarnStyle    = lipgloss.NewStyle().Foreground(lipgloss.Color(colYellow)).Bold(true)
	logSuccessStyle = lipgloss.NewStyle().Foreground(lipgloss.Color(colGreen)).Bold(true)
	logActionStyle  = lipgloss.NewStyle().Foreground(lipgloss.Color(colCyan))
	logSystemStyle  = lipgloss.NewStyle().Foreground(lipgloss.Color(colPurple))
)
