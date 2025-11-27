package tui

import (
	"fmt"
	"strings"
)

// renderRunView renders the Run tab content.
func renderRunView(b *strings.Builder, m model) {
	if m.running || len(m.runFeedBuf) > 0 {
		renderRunDashboard(b, m)
		return
	}
	renderRunIdle(b, m)
}

// renderRunDashboard renders the active/completed run dashboard.
func renderRunDashboard(b *strings.Builder, m model) {
	b.WriteString(sectionTitle.Render("Run Dashboard") + "\n")

	// Progress stepper
	if stepper := renderProgressStepper(m); stepper != "" {
		b.WriteString(stepper + "\n\n")
	}

	b.WriteString("PRD: " + formatPRDDisplay(m.selectedPRD) + "\n")
	fmt.Fprintf(b, "Executor policy: %s\n", m.cfg.ExecutorPolicy)
	fmt.Fprintf(b, "Phases -> local:%v pr:%v review_fix:%v\n", m.runLocal, m.runPR, m.runReview)

	renderRunStatus(b, m)
	renderLastError(b, m)
	renderPhaseDetails(b, m)
	renderLiveFeed(b, m)
	renderRunHelpFooter(b, m)
}

// renderRunIdle renders the idle state run view.
func renderRunIdle(b *strings.Builder, m model) {
	b.WriteString(sectionTitle.Render("Run") + "\n")

	// Progress stepper shows planned phases
	if stepper := renderProgressStepper(m); stepper != "" {
		b.WriteString(stepper + "\n\n")
	}

	b.WriteString("PRD: " + formatPRDDisplay(m.selectedPRD) + "\n")
	fmt.Fprintf(b, "Executor policy: %s\n", m.cfg.ExecutorPolicy)
	fmt.Fprintf(b, "Phases -> local:%v pr:%v review_fix:%v\n", m.runLocal, m.runPR, m.runReview)

	if m.errMsg != "" {
		b.WriteString(errorStyle.Render(annotateUnsaved("Status: Error: "+m.errMsg, m.dirty)) + "\n")
	} else if m.status != "" {
		b.WriteString(annotateUnsaved("Status: "+m.status, m.dirty) + "\n")
	} else {
		b.WriteString(annotateUnsaved("Status: Idle", m.dirty) + "\n")
	}
	b.WriteString(helpStyle.Render("Enter start · s skip to PR · Shift+S skip to Review · q quit\n"))
}

// renderRunStatus renders the current run status line.
func renderRunStatus(b *strings.Builder, m model) {
	switch {
	case m.running:
		b.WriteString(okStyle.Render(annotateUnsaved("Status: Running (Ctrl+C cancel)", m.dirty)) + "\n")
	case m.errMsg != "":
		b.WriteString(errorStyle.Render(annotateUnsaved("Status: Error: "+m.errMsg, m.dirty)) + "\n")
	case m.status != "":
		b.WriteString(annotateUnsaved("Status: "+m.status, m.dirty) + "\n")
	default:
		b.WriteString(annotateUnsaved("Status: Idle", m.dirty) + "\n")
	}
}

// renderLastError renders the last error banner if present.
func renderLastError(b *strings.Builder, m model) {
	lastErrText := getLastErrorText(&m)
	if lastErrText == "" {
		return
	}

	firstLine := lastErrText
	if idx := strings.IndexByte(firstLine, '\n'); idx >= 0 {
		firstLine = firstLine[:idx]
	}
	banner := fmt.Sprintf("Last error: %s", firstLine)
	b.WriteString(errorBanner.Render(banner) + "\n")

	hints := make([]string, 0, 4)
	if retryKeys := actionKeyLabel(m.keys, tabIDRun, ActConfirm); retryKeys != "" {
		hints = append(hints, fmt.Sprintf("%s retry all", retryKeys))
	}
	if skipPRKeys := actionKeyLabel(m.keys, tabIDRun, ActResumeFromPR); skipPRKeys != "" {
		hints = append(hints, fmt.Sprintf("%s retry from PR", skipPRKeys))
	}
	if skipReviewKeys := actionKeyLabel(m.keys, tabIDRun, ActResumeFromReview); skipReviewKeys != "" {
		hints = append(hints, fmt.Sprintf("%s retry from Review", skipReviewKeys))
	}
	if copyKeys := actionKeyLabel(m.keys, tabIDRun, ActCopyError); copyKeys != "" {
		hints = append(hints, fmt.Sprintf("%s copy error", copyKeys))
	}
	if len(hints) > 0 {
		b.WriteString(helpStyle.Render(strings.Join(hints, " · ")) + "\n")
	}
}

// renderPhaseDetails renders phase, current task, and iteration info.
func renderPhaseDetails(b *strings.Builder, m model) {
	phase := m.runPhase
	if phase == "" {
		if m.running {
			phase = "Preparing..."
		} else {
			phase = "Idle"
		}
	}

	current := m.runCurrent
	if current == "" {
		if m.running {
			current = "Awaiting updates..."
		} else {
			current = "Idle"
		}
	}

	previous := m.runPrevious
	if previous == "" {
		previous = "(none)"
	}

	lastComplete := m.runLastComplete
	if lastComplete == "" {
		lastComplete = "(none)"
	}

	iteration := formatIterationDisplay(m)

	fmt.Fprintf(b, "Phase: %s\n", phase)
	fmt.Fprintf(b, "Current: %s\n", current)
	fmt.Fprintf(b, "Previous: %s\n", previous)
	fmt.Fprintf(b, "Last Complete: %s\n", lastComplete)
	fmt.Fprintf(b, "Iteration: %s\n\n", iteration)
}

// formatIterationDisplay formats the iteration counter for display.
func formatIterationDisplay(m model) string {
	switch {
	case m.runIterCurrent == iterIndexUnknown:
		return m.runIterLabel
	case m.runIterCurrent > 0:
		var iteration string
		switch {
		case m.runIterTotal > 0:
			iteration = fmt.Sprintf("%d/%d", m.runIterCurrent, m.runIterTotal)
		case m.runIterTotal == iterTotalUnknown:
			iteration = fmt.Sprintf("%d/?", m.runIterCurrent)
		default:
			iteration = fmt.Sprintf("%d", m.runIterCurrent)
		}
		if m.runIterLabel != "" {
			iteration = fmt.Sprintf("%s - %s", iteration, m.runIterLabel)
		}
		return iteration
	case m.runIterLabel != "":
		return m.runIterLabel
	default:
		return ""
	}
}

// renderLiveFeed renders the live feed section.
func renderLiveFeed(b *strings.Builder, m model) {
	followMode := "off"
	switch {
	case m.followLogs && m.runFeedAutoFollow:
		followMode = "auto"
	case m.followLogs:
		followMode = "paused"
	}
	b.WriteString(sectionTitle.Render(fmt.Sprintf("Live Feed — follow %s", followMode)) + "\n")
	b.WriteString(m.runFeed.View() + "\n")

	if m.logFilePath != "" {
		b.WriteString(helpStyle.Render("Log file: "+abbreviatePath(m.logFilePath)) + "\n")
	} else if m.logStatus != "" {
		b.WriteString(helpStyle.Render("Log file: "+m.logStatus) + "\n")
	}
}

// renderRunHelpFooter renders the help text for the run tab.
func renderRunHelpFooter(b *strings.Builder, m model) {
	if m.running {
		b.WriteString(helpStyle.Render(fmt.Sprintf("Ctrl+C cancel · q quit · %s\n", runScrollHelp)))
	} else {
		b.WriteString(helpStyle.Render("Enter start · s skip to PR · Shift+S skip to Review · q quit\n"))
		b.WriteString(helpStyle.Render(runScrollHelp + "\n"))
	}
}

// renderProgressStepper creates a visual progress indicator for the run phases.
func renderProgressStepper(m model) string {
	steps := []StepperStep{}

	if m.runLocal {
		steps = append(steps, StepperStep{Label: "Local", Status: stepStatusForPhase(m, "local")})
	}
	if m.runPR {
		steps = append(steps, StepperStep{Label: "PR", Status: stepStatusForPhase(m, "pr")})
	}
	if m.runReview {
		steps = append(steps, StepperStep{Label: "Review", Status: stepStatusForPhase(m, "review")})
	}

	if len(steps) == 0 {
		return ""
	}

	return NewStepper(steps).Render()
}

// stepStatusForPhase determines the status of a phase based on current run state.
func stepStatusForPhase(m model, phase string) StepStatus {
	if !m.running {
		return StepPending
	}

	currentPhase := strings.ToLower(m.runPhase)

	// Empty runPhase during active run indicates preparation/starting phase.
	// In this case, the first enabled phase will show as active (handled below
	// when currentIdx remains -1).

	// Determine phase order indices
	phaseOrder := []string{}
	if m.runLocal {
		phaseOrder = append(phaseOrder, "local")
	}
	if m.runPR {
		phaseOrder = append(phaseOrder, "pr")
	}
	if m.runReview {
		phaseOrder = append(phaseOrder, "review")
	}

	// Find target phase index
	targetIdx := -1
	for i, p := range phaseOrder {
		if p == phase {
			targetIdx = i
			break
		}
	}
	if targetIdx == -1 {
		return StepSkipped
	}

	// Normalize the current phase to a canonical name
	normalizedCurrent := normalizePhaseToCanonical(currentPhase)

	// Find current phase index using normalized comparison
	currentIdx := -1
	for i, p := range phaseOrder {
		if p == normalizedCurrent {
			currentIdx = i
			break
		}
	}

	// If no current phase detected, we're still preparing
	if currentIdx == -1 {
		if targetIdx == 0 {
			return StepActive // First phase is active during preparation
		}
		return StepPending
	}

	// Determine status based on position
	if targetIdx < currentIdx {
		return StepComplete
	}
	if targetIdx == currentIdx {
		return StepActive
	}
	return StepPending
}

// normalizePhaseToCanonical maps a raw phase string (from log output) to one
// of the canonical phase names: "local", "pr", or "review". Returns empty
// string if the phase cannot be mapped to a known canonical name.
func normalizePhaseToCanonical(phase string) string {
	phase = strings.ToLower(strings.TrimSpace(phase))

	// Map known patterns to canonical names
	switch {
	// Local phase patterns: iterations, implementation, codex tasks
	case strings.HasPrefix(phase, "iteration"),
		strings.Contains(phase, "implement"),
		strings.Contains(phase, "codex applies"),
		strings.Contains(phase, "coderabbit cli review"),
		phase == "local":
		return "local"

	// PR phase patterns: push, branch, open PR
	case strings.HasPrefix(phase, "pr"),
		strings.Contains(phase, "pushes branch"),
		strings.Contains(phase, "opens pr"),
		strings.Contains(phase, "bot pushes"):
		return "pr"

	// Review phase patterns: review/fix loop, feedback
	case strings.Contains(phase, "review/fix"),
		strings.Contains(phase, "review_fix"),
		strings.Contains(phase, "entering review"),
		(strings.Contains(phase, "review") && !strings.Contains(phase, "coderabbit")):
		return "review"

	default:
		return ""
	}
}
