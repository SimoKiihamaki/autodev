package tui

import "github.com/charmbracelet/lipgloss"

var (
	titleStyle      = lipgloss.NewStyle().Bold(true).MarginBottom(1)
	tabActive       = lipgloss.NewStyle().Bold(true).Underline(true)
	tabInactive     = lipgloss.NewStyle().Faint(true)
	sectionTitle    = lipgloss.NewStyle().Bold(true).MarginTop(1).MarginBottom(0)
	helpStyle       = lipgloss.NewStyle().Faint(true)
	errorStyle      = lipgloss.NewStyle().Foreground(lipgloss.Color("#FF5555"))
	okStyle         = lipgloss.NewStyle().Foreground(lipgloss.Color("#50FA7B"))
	borderStyle     = lipgloss.NewStyle().Border(lipgloss.RoundedBorder())
	logInfoStyle    = lipgloss.NewStyle()
	logErrorStyle   = lipgloss.NewStyle().Foreground(lipgloss.Color("#FF5555")).Bold(true)
	logWarnStyle    = lipgloss.NewStyle().Foreground(lipgloss.Color("#F1FA8C")).Bold(true)
	logSuccessStyle = lipgloss.NewStyle().Foreground(lipgloss.Color("#50FA7B")).Bold(true)
	logActionStyle  = lipgloss.NewStyle().Foreground(lipgloss.Color("#8BE9FD"))
	logSystemStyle  = lipgloss.NewStyle().Foreground(lipgloss.Color("#BD93F9"))
)
