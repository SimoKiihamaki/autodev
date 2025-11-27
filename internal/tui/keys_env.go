package tui

import (
	tea "github.com/charmbracelet/bubbletea"
)

// handleEnvTabActions handles key actions for the Env & Flags tab.
func (m *model) handleEnvTabActions(actions []Action, msg tea.KeyMsg) (bool, tea.Cmd) {
	_ = msg // unused, but kept for interface consistency

	if len(actions) == 0 {
		return false, nil
	}

	handled := false

	for _, act := range actions {
		switch act {
		case ActCancel:
			m.focusedFlag = ""
			handled = true
		case ActNavigateUp:
			m.navigateFlags("up")
			handled = true
		case ActNavigateDown:
			m.navigateFlags("down")
			handled = true
		case ActNavigateLeft:
			if m.focusedFlag != "" {
				m.navigateFlags("left")
			}
			handled = true
		case ActNavigateRight:
			if m.focusedFlag != "" {
				m.navigateFlags("right")
			}
			handled = true
		case ActConfirm:
			if m.focusedFlag == "" {
				if len(envFlagNames) == 0 {
					break
				}
				m.focusFlag(envFlagNames[0])
			} else {
				m.toggleFocusedFlag()
			}
			handled = true
		case ActToggleFlagLocal, ActToggleFlagPR, ActToggleFlagReview, ActToggleFlagUnsafe, ActToggleFlagDryRun, ActToggleFlagSyncGit, ActToggleFlagInfinite:
			if flag := flagNameForAction(act); flag != "" {
				m.focusFlag(flag)
				m.toggleFocusedFlag()
				handled = true
			}
		}
	}

	return handled, nil
}

// flagNameForAction returns the flag name constant for a toggle action.
func flagNameForAction(act Action) string {
	switch act {
	case ActToggleFlagLocal:
		return FlagNameLocal
	case ActToggleFlagPR:
		return FlagNamePR
	case ActToggleFlagReview:
		return FlagNameReview
	case ActToggleFlagUnsafe:
		return FlagNameUnsafe
	case ActToggleFlagDryRun:
		return FlagNameDryRun
	case ActToggleFlagSyncGit:
		return FlagNameSyncGit
	case ActToggleFlagInfinite:
		return FlagNameInfinite
	default:
		return ""
	}
}
