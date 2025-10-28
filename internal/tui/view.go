package tui

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/lipgloss"
)

const focusedBgColor = "240"

const (
	// Help text constants for better readability
	toggleHint         = "Enter/Space to switch Codex/Claude"
	executorToggleHelp = "Toggle focused: %s (" + toggleHint + ", Tab or arrows to navigate, Esc unfocus)"
	inputFocusHelp     = "Input focused: %s (↑/↓/←/→ to navigate, Enter/Esc to unfocus)"
	generalKeysHelp    = "Keys: ↑/↓/←/→ move focus · Enter focuses first field · " + toggleHint + " when on a switch · Ctrl+S save · 1-%d,? switch tabs"
)

func focusStyle(active bool) lipgloss.Style {
	style := lipgloss.NewStyle()
	if active {
		style = style.Background(lipgloss.Color(focusedBgColor))
	}
	return style
}

func (m model) View() string {
	var b strings.Builder
	b.WriteString(titleStyle.Render("autodev — PRD→PR TUI") + "\n")
	for i, name := range tabNames {
		if tab(i) == m.tab {
			b.WriteString(tabActive.Render(fmt.Sprintf("[%d] %s  ", i+1, name)))
		} else {
			b.WriteString(tabInactive.Render(fmt.Sprintf("[%d] %s  ", i+1, name)))
		}
	}
	b.WriteString("\n\n")

	switch m.tab {
	case tabRun:
		renderRunView(&b, m)
	case tabPRD:
		renderPRDView(&b, m)
	case tabSettings:
		renderSettingsView(&b, m)
	case tabEnv:
		renderEnvView(&b, m)
	case tabPrompt:
		renderPromptView(&b, m)
	case tabLogs:
		renderLogsView(&b, m)
	case tabHelp:
		renderHelpView(&b, m)
	}

	return b.String()
}

func renderRunView(b *strings.Builder, m model) {
	if m.running || len(m.runFeedBuf) > 0 {
		b.WriteString(sectionTitle.Render("Run Dashboard") + "\n")
		b.WriteString("PRD: " + formatPRDDisplay(m.selectedPRD) + "\n")
		b.WriteString(fmt.Sprintf("Executor policy: %s\n", m.cfg.ExecutorPolicy))
		b.WriteString(fmt.Sprintf("Phases -> local:%v pr:%v review_fix:%v\n", m.runLocal, m.runPR, m.runReview))

		switch {
		case m.running:
			b.WriteString(okStyle.Render("Status: Running (Ctrl+C cancel)") + "\n")
		case m.errMsg != "":
			b.WriteString(errorStyle.Render("Status: Error: "+m.errMsg) + "\n")
		case m.status != "":
			b.WriteString("Status: " + m.status + "\n")
		default:
			b.WriteString("Status: Idle\n")
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

		feedMode := "paused"
		if m.runFeedAutoFollow {
			feedMode = "auto"
		}
		b.WriteString(sectionTitle.Render(fmt.Sprintf("Live Feed — follow %s", feedMode)) + "\n")
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
		b.WriteString(errorStyle.Render("Status: Error: "+m.errMsg) + "\n")
	} else if m.status != "" {
		b.WriteString("Status: " + m.status + "\n")
	} else {
		b.WriteString("Status: Idle\n")
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
	localToggle := renderExecutorToggle("Local Loop", m.execLocalChoice, m.focusedInput == "toggleLocal")
	prToggle := renderExecutorToggle("PR Push", m.execPRChoice, m.focusedInput == "togglePR")
	reviewToggle := renderExecutorToggle("Review Fix", m.execReviewChoice, m.focusedInput == "toggleReview")
	b.WriteString(localToggle + "  " + prToggle + "  " + reviewToggle + "\n")
	b.WriteString(m.inWaitMin.View() + "  ")
	b.WriteString(m.inPollSec.View() + "  ")
	b.WriteString(m.inIdleMin.View() + "  ")
	b.WriteString(m.inMaxIters.View() + "\n")

	if m.focusedInput != "" {
		if isExecutorToggle(m.focusedInput) {
			b.WriteString("\n" + okStyle.Render(fmt.Sprintf(executorToggleHelp, executorToggleLabel(m.focusedInput))) + "\n")
		} else {
			b.WriteString("\n" + okStyle.Render(fmt.Sprintf(inputFocusHelp, m.focusedInput)) + "\n")
		}
	} else {
		b.WriteString(fmt.Sprintf("\n"+generalKeysHelp+"\n", len(tabNames)))
	}
}

func renderExecutorToggle(label string, choice executorChoice, focused bool) string {
	codex := renderExecutorOption("Codex", choice == executorCodex)
	claude := renderExecutorOption("Claude", choice == executorClaude)
	line := fmt.Sprintf("%s: %s  %s", label, codex, claude)
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
		return "Local Loop"
	case "togglePR":
		return "PR Push"
	case "toggleReview":
		return "Review Fix"
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
		reviewStyle.Render("[R] ReviewFix="+fmt.Sprint(m.runReview)) + "\n")

	unsafeStyle := focusStyle(m.focusedFlag == "unsafe")
	dryrunStyle := focusStyle(m.focusedFlag == "dryrun")
	syncgitStyle := focusStyle(m.focusedFlag == "syncgit")
	infiniteStyle := focusStyle(m.focusedFlag == "infinite")

	b.WriteString(unsafeStyle.Render(fmt.Sprintf("[a] Allow Unsafe: %v (AUTO_PRD_ALLOW_UNSAFE_EXECUTION=1 and CI=1)", m.flagAllowUnsafe)) + "\n")
	b.WriteString(dryrunStyle.Render(fmt.Sprintf("[d] Dry Run:     %v", m.flagDryRun)) + "\n")
	b.WriteString(syncgitStyle.Render(fmt.Sprintf("[g] Sync Git:    %v", m.flagSyncGit)) + "\n")
	b.WriteString(infiniteStyle.Render(fmt.Sprintf("[i] Infinite Reviews: %v", m.flagInfinite)) + "\n")

	if m.focusedFlag != "" {
		b.WriteString("\n" + okStyle.Render("Flag focused: "+m.focusedFlag+" (↑/↓ navigate, ←/→/Enter toggle, Esc unfocus)") + "\n")
		return
	}
	b.WriteString("\n" + helpStyle.Render("Arrow keys to navigate · Enter/←/→ toggle · s save") + "\n")
}

func renderPromptView(b *strings.Builder, m model) {
	b.WriteString(sectionTitle.Render("Initial Prompt (optional)") + "\n")
	b.WriteString(m.prompt.View() + "\n")
	if m.prompt.Focused() {
		b.WriteString(okStyle.Render("Text area focused (Esc to unfocus)") + "\n")
	} else {
		b.WriteString("Press Enter to edit text, Esc to unfocus\n")
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
	b.WriteString("• PRD tab: ↑/↓ navigate list · Enter select · t tag · Ctrl+S save · r rescan\n")
	b.WriteString("• Settings: Arrow keys move focus · ←/→ or Enter/Space toggles Codex/Claude when on a switch · Tab steps downward · Esc unfocus · Ctrl+S save\n")
	b.WriteString("• Prompt: Arrow keys to focus/edit · Enter for newline · Esc to finish · Ctrl+S save\n")
	b.WriteString("• Env: ↑/↓ navigate flags · ←/→/Enter toggle focused · Letter keys direct toggle (see NAVIGATION_GUIDE.md for mapping) · Ctrl+S save\n")
	b.WriteString("• Logs: ↑/↓ scroll · PgUp/PgDn page · Home/End top/bottom · path shown in the Logs tab\n")
	b.WriteString("• Run: Enter start · Ctrl+C cancel · f toggle follow\n")
	b.WriteString(fmt.Sprintf("\nGlobal: 1-%d tabs · ? help · q quit · Ctrl+C force quit\n", len(tabNames)))
	b.WriteString("\nSee NAVIGATION_GUIDE.md for detailed instructions.")
}
