package tui

import "github.com/charmbracelet/lipgloss"

var (
	colRed     = lipgloss.AdaptiveColor{Light: "#D70000", Dark: "#FF5555"}
	colGreen   = lipgloss.AdaptiveColor{Light: "#008700", Dark: "#50FA7B"}
	colYellow  = lipgloss.AdaptiveColor{Light: "#AF8700", Dark: "#F1FA8C"}
	colCyan    = lipgloss.AdaptiveColor{Light: "#0087AF", Dark: "#8BE9FD"}
	colPurple  = lipgloss.AdaptiveColor{Light: "#5F00AF", Dark: "#BD93F9"}
	colDimGray = lipgloss.AdaptiveColor{Light: "#888888", Dark: "#666666"}

	titleStyle         = lipgloss.NewStyle().Bold(true).MarginBottom(1)
	tabActive          = lipgloss.NewStyle().Bold(true).Underline(true)
	tabInactive        = lipgloss.NewStyle().Faint(true)
	sectionTitle       = lipgloss.NewStyle().Bold(true).MarginTop(1).MarginBottom(0)
	helpStyle          = lipgloss.NewStyle().Faint(true)
	errorStyle         = lipgloss.NewStyle().Foreground(colRed)
	okStyle            = lipgloss.NewStyle().Foreground(colGreen)
	borderStyle        = lipgloss.NewStyle().Border(lipgloss.RoundedBorder())
	helpBoxStyle       = borderStyle.BorderForeground(colCyan).Padding(0, 1).MarginTop(1)
	helpBoxTitle       = lipgloss.NewStyle().Bold(true)
	helpKeyStyle       = lipgloss.NewStyle().Bold(true)
	helpLabelStyle     = lipgloss.NewStyle()
	errorBanner        = borderStyle.BorderForeground(colRed).Padding(0, 1)
	logInfoStyle       = lipgloss.NewStyle()
	logErrorStyle      = lipgloss.NewStyle().Foreground(colRed).Bold(true)
	logWarnStyle       = lipgloss.NewStyle().Foreground(colYellow).Bold(true)
	logSuccessStyle    = lipgloss.NewStyle().Foreground(colGreen).Bold(true)
	logActionStyle     = lipgloss.NewStyle().Foreground(colCyan)
	logSystemStyle     = lipgloss.NewStyle().Foreground(colPurple)
	statusInfoStyle    = lipgloss.NewStyle().Foreground(colCyan)
	statusSuccessStyle = lipgloss.NewStyle().Foreground(colGreen)
	statusWarnStyle    = lipgloss.NewStyle().Foreground(colYellow)
	statusErrorStyle   = lipgloss.NewStyle().Foreground(colRed)

	// Stepper styles for progress pipeline
	stepPendingStyle   = lipgloss.NewStyle().Faint(true)
	stepActiveStyle    = lipgloss.NewStyle().Bold(true).Foreground(colCyan)
	stepCompleteStyle  = lipgloss.NewStyle().Foreground(colGreen)
	stepErrorStyle     = lipgloss.NewStyle().Foreground(colRed)
	stepSkippedStyle   = lipgloss.NewStyle().Faint(true).Strikethrough(true)
	stepConnectorStyle = lipgloss.NewStyle().Faint(true)

	// Powerline styles for status bar
	powerlineLeftStyle   = lipgloss.NewStyle().Background(colPurple).Foreground(lipgloss.Color("15")).Padding(0, 1)
	powerlineCenterStyle = lipgloss.NewStyle().Background(lipgloss.Color("237")).Foreground(lipgloss.Color("252")).Padding(0, 1)
	powerlineRightStyle  = lipgloss.NewStyle().Background(colCyan).Foreground(lipgloss.Color("0")).Padding(0, 1)

	// Box styles for BorderedBox component
	boxTitleStyle = lipgloss.NewStyle().Bold(true).MarginBottom(1)

	// Split pane styles
	splitDividerStyle = lipgloss.NewStyle().Faint(true).Foreground(colDimGray)

	// Log enhancement styles
	logTasksLeftStyle = lipgloss.NewStyle().Bold(true).Foreground(colPurple)
	logPhaseStyle     = lipgloss.NewStyle().Bold(true).Background(colCyan).Foreground(lipgloss.Color("0"))
)
