package tui

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/lipgloss"
)

// -----------------------------------------------------------------------------
// StepStatus represents the state of a step in a progress pipeline
// -----------------------------------------------------------------------------

type StepStatus int

const (
	StepPending StepStatus = iota
	StepActive
	StepComplete
	StepError
	StepSkipped
)

// -----------------------------------------------------------------------------
// Stepper renders a horizontal progress pipeline
// -----------------------------------------------------------------------------

type StepperStep struct {
	Label  string
	Status StepStatus
}

type Stepper struct {
	Steps     []StepperStep
	Connector string
}

func NewStepper(steps []StepperStep) Stepper {
	return Stepper{
		Steps:     steps,
		Connector: " -> ",
	}
}

func (s Stepper) Render() string {
	if len(s.Steps) == 0 {
		return ""
	}

	parts := make([]string, 0, len(s.Steps)*2-1)
	for i, step := range s.Steps {
		icon := s.iconForStatus(step.Status)
		style := s.styleForStatus(step.Status)
		label := style.Render(icon + " " + step.Label)
		parts = append(parts, label)

		if i < len(s.Steps)-1 {
			parts = append(parts, stepConnectorStyle.Render(s.Connector))
		}
	}

	return lipgloss.JoinHorizontal(lipgloss.Center, parts...)
}

func (s Stepper) iconForStatus(status StepStatus) string {
	switch status {
	case StepComplete:
		return "✓"
	case StepActive:
		return "●"
	case StepError:
		return "✗"
	case StepSkipped:
		return "○"
	default:
		return "○"
	}
}

func (s Stepper) styleForStatus(status StepStatus) lipgloss.Style {
	switch status {
	case StepComplete:
		return stepCompleteStyle
	case StepActive:
		return stepActiveStyle
	case StepError:
		return stepErrorStyle
	case StepSkipped:
		return stepSkippedStyle
	default:
		return stepPendingStyle
	}
}

// -----------------------------------------------------------------------------
// BorderedBox renders content in a bordered frame with optional title
// -----------------------------------------------------------------------------

type BorderedBox struct {
	Title       string
	Content     string
	Width       int
	Focused     bool
	BorderColor lipgloss.AdaptiveColor
}

func NewBorderedBox(title, content string) BorderedBox {
	return BorderedBox{
		Title:       title,
		Content:     content,
		BorderColor: colCyan,
	}
}

func (b BorderedBox) Render() string {
	style := lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		Padding(0, 1)

	if b.Focused {
		style = style.BorderForeground(b.BorderColor)
	} else {
		style = style.BorderForeground(colDimGray)
	}

	if b.Width > 0 {
		style = style.Width(b.Width)
	}

	content := b.Content
	if b.Title != "" {
		titleLine := boxTitleStyle.Render(b.Title)
		content = titleLine + "\n" + content
	}

	return style.Render(content)
}

// -----------------------------------------------------------------------------
// SplitPane renders two panes side by side
// -----------------------------------------------------------------------------

type SplitPane struct {
	Left      string
	Right     string
	LeftRatio float64 // 0.0-1.0, percentage of width for left pane
	Divider   string
}

func NewSplitPane(left, right string, leftRatio float64) SplitPane {
	if leftRatio <= 0 || leftRatio >= 1 {
		leftRatio = 0.5
	}
	return SplitPane{
		Left:      left,
		Right:     right,
		LeftRatio: leftRatio,
		Divider:   " │ ",
	}
}

func (s SplitPane) Render(totalWidth int) string {
	if totalWidth <= 0 {
		totalWidth = 80 // Default fallback
	}

	dividerWidth := lipgloss.Width(s.Divider)
	availableWidth := totalWidth - dividerWidth
	if availableWidth < 20 {
		availableWidth = 20
	}

	leftWidth := int(float64(availableWidth) * s.LeftRatio)
	rightWidth := availableWidth - leftWidth

	if leftWidth < 10 {
		leftWidth = 10
	}
	if rightWidth < 10 {
		rightWidth = 10
	}

	leftStyle := lipgloss.NewStyle().Width(leftWidth)
	rightStyle := lipgloss.NewStyle().Width(rightWidth)

	return lipgloss.JoinHorizontal(
		lipgloss.Top,
		leftStyle.Render(s.Left),
		splitDividerStyle.Render(s.Divider),
		rightStyle.Render(s.Right),
	)
}

// -----------------------------------------------------------------------------
// PowerlineBar renders a status bar with powerline-style segments
// -----------------------------------------------------------------------------

type PowerlineSegment struct {
	Text  string
	Style lipgloss.Style
}

type PowerlineBar struct {
	Segments  []PowerlineSegment
	Separator string
}

func NewPowerlineBar(segments []PowerlineSegment) PowerlineBar {
	return PowerlineBar{
		Segments:  segments,
		Separator: " ",
	}
}

func (p PowerlineBar) Render() string {
	if len(p.Segments) == 0 {
		return ""
	}

	parts := make([]string, 0, len(p.Segments))
	for _, seg := range p.Segments {
		if seg.Text == "" {
			continue
		}
		parts = append(parts, seg.Style.Render(seg.Text))
	}

	return lipgloss.JoinHorizontal(lipgloss.Center, parts...)
}

// RenderFullWidth renders the powerline bar filling the specified width
func (p PowerlineBar) RenderFullWidth(width int) string {
	if len(p.Segments) == 0 {
		return ""
	}

	// Calculate content width
	var contentParts []string
	totalContentWidth := 0
	for i, seg := range p.Segments {
		if seg.Text == "" {
			continue
		}
		rendered := seg.Style.Render(seg.Text)
		contentParts = append(contentParts, rendered)
		totalContentWidth += lipgloss.Width(rendered)
		if i < len(p.Segments)-1 {
			totalContentWidth += len(p.Separator)
		}
	}

	content := strings.Join(contentParts, p.Separator)

	// If we have extra width, pad the last segment
	if width > totalContentWidth {
		paddingNeeded := width - totalContentWidth
		return content + strings.Repeat(" ", paddingNeeded)
	}

	return content
}

// -----------------------------------------------------------------------------
// ToggleGroup renders a labeled set of mutually exclusive options
// -----------------------------------------------------------------------------

type ToggleOption struct {
	Label    string
	Value    string
	Selected bool
}

type ToggleGroup struct {
	Label   string
	Options []ToggleOption
	Focused bool
}

func NewToggleGroup(label string, options []ToggleOption) ToggleGroup {
	return ToggleGroup{
		Label:   label,
		Options: options,
	}
}

func (t ToggleGroup) Render() string {
	parts := make([]string, 0, len(t.Options))
	for _, opt := range t.Options {
		var style lipgloss.Style
		text := opt.Label
		if opt.Selected {
			text = "[" + text + "]"
			style = lipgloss.NewStyle().Bold(true).Foreground(colGreen)
		} else {
			style = lipgloss.NewStyle().Faint(true)
		}
		parts = append(parts, style.Render(text))
	}

	optionLine := strings.Join(parts, "  ")
	result := t.Label + ": " + optionLine

	if t.Focused {
		return focusStyle(true).Render(result)
	}
	return result
}

// -----------------------------------------------------------------------------
// StatusIndicator renders a simple status with icon
// -----------------------------------------------------------------------------

type StatusIndicator struct {
	Label  string
	Status string // "ok", "error", "warn", "info"
}

func (s StatusIndicator) Render() string {
	var icon string
	var style lipgloss.Style

	switch s.Status {
	case "ok":
		icon = "✓"
		style = okStyle
	case "error":
		icon = "✗"
		style = errorStyle
	case "warn":
		icon = "⚠"
		style = logWarnStyle
	default:
		icon = "●"
		style = statusInfoStyle
	}

	return style.Render(fmt.Sprintf("%s %s", icon, s.Label))
}
