package tui

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/lipgloss"
)

const focusedBgColor = "240"

// toggleSeparator defines the spacing between toggle groups (toggles).
// The double space is intentional to provide clear visual separation between toggle groups in the TUI;
// a single space does not provide enough separation for readability and aesthetics.
const toggleSeparator = "  "

// Executor label constants to maintain single source of truth
const (
	executorLocalLabel  = "Local Loop"
	executorPRLabel     = "PR Push"
	executorReviewLabel = "Review Fix"
)

// toggleHint is the help text for toggling executors.
const toggleHint = "Enter/Space to switch Codex/Claude"

// inputFocusHelpTemplate expects the input name as the first argument.
const inputFocusHelpTemplate = "Input focused: %s (↑/↓/←/→ to navigate, Enter/Esc to blur)"

func focusStyle(active bool) lipgloss.Style {
	style := lipgloss.NewStyle()
	if active {
		style = style.Background(lipgloss.Color(focusedBgColor))
	}
	return style
}

func tabShortcutLabel(keys KeyMap, idx int) string {
	if act, ok := gotoTabAction(idx); ok {
		if combos := keys.Global[act]; len(combos) > 0 {
			labels := make([]string, 0, len(combos))
			for _, combo := range combos {
				labels = append(labels, combo.Display())
			}
			return strings.Join(labels, "/")
		}
	}
	return fmt.Sprintf("%d", idx+1)
}

func actionKeyLabel(keys KeyMap, tabID string, act Action) string {
	var combos []KeyCombo
	if keys.PerTab != nil {
		if perTab := keys.PerTab[tabID]; perTab != nil {
			combos = perTab[act]
		}
	}
	if len(combos) == 0 {
		combos = keys.Global[act]
	}
	if len(combos) == 0 {
		return ""
	}
	labels := make([]string, 0, len(combos))
	for _, combo := range combos {
		labels = append(labels, combo.Display())
	}
	return strings.Join(labels, "/")
}

func annotateUnsaved(text string, dirty bool) string {
	if !dirty {
		return text
	}
	if strings.Contains(text, "[unsaved]") || strings.Contains(text, "[Unsaved]") {
		return text
	}
	return text + " [unsaved]"
}

func (m model) View() string {
	var b strings.Builder
	title := "autodev — PRD→PR TUI"
	if m.dirty {
		title += " [unsaved]"
	}
	b.WriteString(titleStyle.Render(title) + "\n")
	for i, tabID := range m.tabs {
		shortcuts := tabShortcutLabel(m.keys, i)
		label := fmt.Sprintf("[%s] %s  ", shortcuts, tabTitle(tabID))
		if i == m.tabIndex {
			b.WriteString(tabActive.Render(label))
			continue
		}
		b.WriteString(tabInactive.Render(label))
	}
	b.WriteString("\n\n")

	switch m.currentTabID() {
	case tabIDRun:
		renderRunView(&b, m)
	case tabIDPRD:
		renderPRDView(&b, m)
	case tabIDSettings:
		renderSettingsView(&b, m)
	case tabIDEnv:
		renderEnvView(&b, m)
	case tabIDPrompt:
		renderPromptView(&b, m)
	case tabIDLogs:
		renderLogsView(&b, m)
	case tabIDHelp:
		renderHelpView(&b, m)
	}

	if m.quitConfirmActive {
		b.WriteString("\n")
		b.WriteString(errorStyle.Render("Unsaved changes detected. Choose how to quit:") + "\n")
		labels := make([]string, len(quitOptions))
		for i, opt := range quitOptions {
			label := fmt.Sprintf("[%s]", opt)
			if i == m.quitConfirmIndex {
				labels[i] = okStyle.Render(label)
			} else {
				labels[i] = helpStyle.Render(label)
			}
		}
		b.WriteString(strings.Join(labels, "  ") + "\n")
		b.WriteString(helpStyle.Render("Left/Right cycle · Enter confirm · Esc cancel") + "\n")
	}

	renderHelpOverlay(&b, m)
	renderStatusBar(&b, m)

	return b.String()
}

func renderStatusBar(b *strings.Builder, m model) {
	message, style := statusBarMessage(m)
	if message == "" {
		return
	}
	if b.Len() > 0 {
		b.WriteString("\n")
	}
	b.WriteString(style.Render(message))
	b.WriteString("\n")
}

func statusBarMessage(m model) (string, lipgloss.Style) {
	if m.toast != nil {
		return m.toast.message, classifyStatusStyle(m.toast.message)
	}
	if note := strings.TrimSpace(m.status); note != "" {
		return annotateUnsaved(note, m.dirty), classifyStatusStyle(note)
	}
	if m.dirty {
		return "Unsaved changes pending — press Ctrl+S to save", statusWarnStyle
	}
	return "", lipgloss.NewStyle()
}

func classifyStatusStyle(text string) lipgloss.Style {
	lower := strings.ToLower(text)
	switch {
	case strings.Contains(lower, "error"),
		strings.Contains(lower, "fail"),
		strings.Contains(lower, "panic"):
		return statusErrorStyle
	case strings.Contains(lower, "warn"):
		return statusWarnStyle
	case strings.Contains(lower, "saved"),
		strings.Contains(lower, "success"),
		strings.Contains(lower, "completed"),
		strings.Contains(lower, "finished"):
		return statusSuccessStyle
	case strings.Contains(lower, "cancel"),
		strings.Contains(lower, "pending"),
		strings.Contains(lower, "unsaved"):
		return statusWarnStyle
	default:
		return statusInfoStyle
	}
}

func renderRunView(b *strings.Builder, m model) {
	if m.running || len(m.runFeedBuf) > 0 {
		b.WriteString(sectionTitle.Render("Run Dashboard") + "\n")
		b.WriteString("PRD: " + formatPRDDisplay(m.selectedPRD) + "\n")
		b.WriteString(fmt.Sprintf("Executor policy: %s\n", m.cfg.ExecutorPolicy))
		b.WriteString(fmt.Sprintf("Phases -> local:%v pr:%v review_fix:%v\n", m.runLocal, m.runPR, m.runReview))

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

		lastErrText := getLastErrorText(&m)
		if lastErrText != "" {
			firstLine := lastErrText
			if idx := strings.IndexByte(firstLine, '\n'); idx >= 0 {
				firstLine = firstLine[:idx]
			}
			banner := fmt.Sprintf("Last error: %s", firstLine)
			b.WriteString(errorBanner.Render(banner) + "\n")
			hints := make([]string, 0, 2)
			if retryKeys := actionKeyLabel(m.keys, tabIDRun, ActConfirm); retryKeys != "" {
				hints = append(hints, fmt.Sprintf("%s retry", retryKeys))
			}
			if copyKeys := actionKeyLabel(m.keys, tabIDRun, ActCopyError); copyKeys != "" {
				hints = append(hints, fmt.Sprintf("%s copy error", copyKeys))
			}
			if len(hints) > 0 {
				b.WriteString(helpStyle.Render(strings.Join(hints, " · ")) + "\n")
			}
		}

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

		iteration := "(none)"
		switch {
		case m.runIterCurrent == iterIndexUnknown:
			if m.runIterLabel != "" {
				iteration = m.runIterLabel
			} else {
				iteration = ""
			}
		case m.runIterCurrent > 0:
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
		case m.runIterLabel != "":
			iteration = m.runIterLabel
		default:
			iteration = ""
		}

		b.WriteString(fmt.Sprintf("Phase: %s\n", phase))
		b.WriteString(fmt.Sprintf("Current: %s\n", current))
		b.WriteString(fmt.Sprintf("Previous: %s\n", previous))
		b.WriteString(fmt.Sprintf("Last Complete: %s\n", lastComplete))
		b.WriteString(fmt.Sprintf("Iteration: %s\n\n", iteration))

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

		if m.running {
			b.WriteString(helpStyle.Render(fmt.Sprintf("Ctrl+C cancel · q quit · %s\n", runScrollHelp)))
		} else {
			b.WriteString(helpStyle.Render("Press Enter to start a new run\n"))
			b.WriteString(helpStyle.Render(fmt.Sprintf("Enter start · q quit · Ctrl+C force quit · %s\n", runScrollHelp)))
		}
		return
	}

	b.WriteString(sectionTitle.Render("Run") + "\n")
	b.WriteString("PRD: " + formatPRDDisplay(m.selectedPRD) + "\n")
	b.WriteString(fmt.Sprintf("Executor policy: %s\n", m.cfg.ExecutorPolicy))
	b.WriteString(fmt.Sprintf("Phases -> local:%v pr:%v review_fix:%v\n", m.runLocal, m.runPR, m.runReview))
	if m.errMsg != "" {
		b.WriteString(errorStyle.Render(annotateUnsaved("Status: Error: "+m.errMsg, m.dirty)) + "\n")
	} else if m.status != "" {
		b.WriteString(annotateUnsaved("Status: "+m.status, m.dirty) + "\n")
	} else {
		b.WriteString(annotateUnsaved("Status: Idle", m.dirty) + "\n")
	}
	b.WriteString(helpStyle.Render("Press Enter to start a run · q quit · Ctrl+C force quit\n"))
}

func renderPRDView(b *strings.Builder, m model) {
	b.WriteString(sectionTitle.Render("PRD Selection") + "\n")
	b.WriteString(m.prdList.View() + "\n")
	if m.selectedPRD != "" {
		b.WriteString(okStyle.Render("Selected: "+abbreviatePath(m.selectedPRD)) + "\n")
	} else {
		b.WriteString(errorStyle.Render("No PRD selected") + "\n")
	}
	if len(m.tags) > 0 {
		b.WriteString("Tags: " + strings.Join(m.tags, ", ") + "\n")
	}
	b.WriteString("t add tag · r rescan · Enter select · ←/→ filter · Ctrl+S save\n")
}

func renderSettingsView(b *strings.Builder, m model) {
	b.WriteString(sectionTitle.Render("Settings") + "\n")
	b.WriteString(m.inRepo.View() + "\n")
	b.WriteString(m.inBase.View() + "\n")
	b.WriteString(m.inBranch.View() + "\n")
	b.WriteString(m.inCodexModel.View() + "\n")
	b.WriteString(m.inPyCmd.View() + "\n")
	b.WriteString(m.inPyScript.View() + "\n")
	b.WriteString(m.inPolicy.View() + "\n")
	localToggle := renderExecutorToggle(executorLocalLabel, m.execLocalChoice, m.focusedInput == "toggleLocal")
	prToggle := renderExecutorToggle(executorPRLabel, m.execPRChoice, m.focusedInput == "togglePR")
	reviewToggle := renderExecutorToggle(executorReviewLabel, m.execReviewChoice, m.focusedInput == "toggleReview")
	b.WriteString(localToggle + toggleSeparator + prToggle + toggleSeparator + reviewToggle + "\n")
	b.WriteString(m.inWaitMin.View() + "  ")
	b.WriteString(m.inPollSec.View() + "  ")
	b.WriteString(m.inIdleMin.View() + "  ")
	b.WriteString(m.inMaxIters.View() + "\n")

	if m.focusedInput != "" {
		if isExecutorToggle(m.focusedInput) {
			b.WriteString("\n" + okStyle.Render(fmt.Sprintf("Toggle focused: %s (%s, arrows to navigate, Esc to blur)", executorToggleLabel(m.focusedInput), toggleHint)) + "\n")
		} else {
			b.WriteString("\n" + okStyle.Render(fmt.Sprintf(inputFocusHelpTemplate, m.focusedInput)) + "\n")
		}
	} else {
		b.WriteString(fmt.Sprintf("\nKeys: ↑/↓/←/→ move focus · Enter focus first field · %s when on a switch · Ctrl+S save · 1-%d,? switch tabs\n", toggleHint, m.tabCount()))
	}
}

func renderExecutorToggle(label string, choice executorChoice, focused bool) string {
	codex := renderExecutorOption("Codex", choice == executorCodex)
	claude := renderExecutorOption("Claude", choice == executorClaude)
	line := fmt.Sprintf("%s: %s%s%s", label, codex, toggleSeparator, claude)
	return focusStyle(focused).Render(line)
}

func renderExecutorOption(name string, selected bool) string {
	style := lipgloss.NewStyle()
	if selected {
		return style.Bold(true).Render("[" + name + "]")
	}
	return style.Render(name)
}

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

func renderEnvView(b *strings.Builder, m model) {
	b.WriteString(sectionTitle.Render("Env & Flags") + "\n")

	localStyle := focusStyle(m.focusedFlag == "local")
	prStyle := focusStyle(m.focusedFlag == "pr")
	reviewStyle := focusStyle(m.focusedFlag == "review")

	b.WriteString("Phases: " + localStyle.Render("[L] Local="+fmt.Sprint(m.runLocal)) + "  " +
		prStyle.Render("[P] PR="+fmt.Sprint(m.runPR)) + "  " +
		reviewStyle.Render(actionKeyLabel(m.keys, tabIDEnv, ActToggleFlagReview)+" Review Fix="+fmt.Sprint(m.runReview)) + "\n")

	unsafeStyle := focusStyle(m.focusedFlag == "unsafe")
	dryrunStyle := focusStyle(m.focusedFlag == "dryrun")
	syncgitStyle := focusStyle(m.focusedFlag == "syncgit")
	infiniteStyle := focusStyle(m.focusedFlag == "infinite")

	b.WriteString(unsafeStyle.Render(fmt.Sprintf("[a] Allow Unsafe: %v (AUTO_PRD_ALLOW_UNSAFE_EXECUTION=1 and CI=1)", m.flagAllowUnsafe)) + "\n")
	b.WriteString(dryrunStyle.Render(fmt.Sprintf("[d] Dry Run:     %v", m.flagDryRun)) + "\n")
	b.WriteString(syncgitStyle.Render(fmt.Sprintf("[g] Sync Git:    %v", m.flagSyncGit)) + "\n")
	b.WriteString(infiniteStyle.Render(fmt.Sprintf("[i] Infinite Reviews: %v", m.flagInfinite)) + "\n")

	if m.focusedFlag != "" {
		b.WriteString("\n" + okStyle.Render("Flag focused: "+m.focusedFlag+" (↑/↓ navigate, ←/→/Enter toggle, Esc blur)") + "\n")
		return
	}
	b.WriteString("\n" + helpStyle.Render("Arrow keys to navigate · Enter/←/→ toggle · s save") + "\n")
}

func renderPromptView(b *strings.Builder, m model) {
	b.WriteString(sectionTitle.Render("Initial Prompt (optional)") + "\n")
	b.WriteString(m.prompt.View() + "\n")
	if m.prompt.Focused() {
		b.WriteString(okStyle.Render("Text area focused (Esc to blur)") + "\n")
	} else {
		b.WriteString("Press Enter to edit text, Esc to blur\n")
	}
}

func renderLogsView(b *strings.Builder, m model) {
	b.WriteString(sectionTitle.Render("Logs") + "\n")
	if m.logFilePath != "" {
		b.WriteString(helpStyle.Render("Persisted at: "+abbreviatePath(m.logFilePath)) + "\n")
	} else if m.logStatus != "" {
		b.WriteString(helpStyle.Render("Log file: "+m.logStatus) + "\n")
	}
	b.WriteString(m.logs.View() + "\n")
}

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
