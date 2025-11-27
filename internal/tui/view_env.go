package tui

import (
	"fmt"
	"strings"
)

// renderEnvView renders the Environment & Flags tab content.
func renderEnvView(b *strings.Builder, m model) {
	b.WriteString(sectionTitle.Render("Env & Flags") + "\n")

	renderPhaseToggles(b, m)
	renderFlagToggles(b, m)
	renderEnvHelp(b, m)
}

// renderPhaseToggles renders the phase toggle buttons.
func renderPhaseToggles(b *strings.Builder, m model) {
	localStyle := focusStyle(m.focusedFlag == FlagNameLocal)
	prStyle := focusStyle(m.focusedFlag == FlagNamePR)
	reviewStyle := focusStyle(m.focusedFlag == FlagNameReview)

	b.WriteString("Phases: " +
		localStyle.Render(actionKeyLabel(m.keys, tabIDEnv, ActToggleFlagLocal)+" Local="+fmt.Sprint(m.runLocal)) + "  " +
		prStyle.Render(actionKeyLabel(m.keys, tabIDEnv, ActToggleFlagPR)+" PR="+fmt.Sprint(m.runPR)) + "  " +
		reviewStyle.Render(actionKeyLabel(m.keys, tabIDEnv, ActToggleFlagReview)+" Review Fix="+fmt.Sprint(m.runReview)) + "\n")
}

// renderFlagToggles renders the flag toggle buttons.
func renderFlagToggles(b *strings.Builder, m model) {
	unsafeStyle := focusStyle(m.focusedFlag == FlagNameUnsafe)
	dryrunStyle := focusStyle(m.focusedFlag == FlagNameDryRun)
	syncgitStyle := focusStyle(m.focusedFlag == FlagNameSyncGit)
	infiniteStyle := focusStyle(m.focusedFlag == FlagNameInfinite)

	b.WriteString(unsafeStyle.Render(fmt.Sprintf("[a] Allow Unsafe: %v (AUTO_PRD_ALLOW_UNSAFE_EXECUTION=1 and CI=1)", m.flagAllowUnsafe)) + "\n")
	b.WriteString(dryrunStyle.Render(fmt.Sprintf("[d] Dry Run:     %v", m.flagDryRun)) + "\n")
	b.WriteString(syncgitStyle.Render(fmt.Sprintf("[g] Sync Git:    %v", m.flagSyncGit)) + "\n")
	b.WriteString(infiniteStyle.Render(fmt.Sprintf("[i] Infinite Reviews: %v", m.flagInfinite)) + "\n")
}

// renderEnvHelp renders the help text for the env tab.
func renderEnvHelp(b *strings.Builder, m model) {
	if m.focusedFlag != "" {
		b.WriteString("\n" + okStyle.Render("Flag focused: "+m.focusedFlag+" (↑/↓ navigate, ←/→/Enter toggle, Esc blur)") + "\n")
		return
	}
	b.WriteString("\n" + helpStyle.Render("Arrow keys to navigate · Enter/←/→ toggle · "+actionKeyLabel(m.keys, tabIDEnv, ActSave)+" save") + "\n")
}
