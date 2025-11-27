package tui

import (
	"strings"

	tea "github.com/charmbracelet/bubbletea"
)

// batchCmd combines multiple tea.Cmd into a single batched command.
func batchCmd(cmds []tea.Cmd) tea.Cmd {
	switch len(cmds) {
	case 0:
		return nil
	case 1:
		return cmds[0]
	default:
		return tea.Batch(cmds...)
	}
}

// handleKeyMsg is the main entry point for key event handling.
func (m model) handleKeyMsg(msg tea.KeyMsg) (model, tea.Cmd) {
	mPtr := &m

	// Handle quit confirmation dialog first
	if mPtr.quitConfirmActive {
		if handled, cmd := mPtr.handleQuitConfirmation(msg); handled {
			return *mPtr, cmd
		}
		return *mPtr, nil
	}

	// Get tab-specific actions and handle them
	tabID := mPtr.currentTabID()
	perTabActions := mPtr.keys.TabActions(tabID, msg)

	if handled, cmd := mPtr.handleTabActions(tabID, perTabActions, msg); handled {
		mPtr.refreshTypingState()
		return *mPtr, cmd
	}

	mPtr.refreshTypingState()

	// Handle global actions
	globalActions := mPtr.keys.GlobalActions(msg)
	for _, act := range globalActions {
		if mPtr.IsTyping() && mPtr.keys.IsTypingSensitive(act) {
			continue
		}
		if handled, cmd := mPtr.handleGlobalAction(act, msg); handled {
			mPtr.refreshTypingState()
			return *mPtr, cmd
		}
	}

	return *mPtr, nil
}

// handleTabActions dispatches to tab-specific action handlers.
func (m *model) handleTabActions(tabID string, actions []Action, msg tea.KeyMsg) (bool, tea.Cmd) {
	switch tabID {
	case tabIDRun:
		return m.handleRunTabActions(actions, msg)
	case tabIDPRD:
		return m.handlePRDTabActions(actions, msg)
	case tabIDSettings:
		return m.handleSettingsTabActions(actions, msg)
	case tabIDEnv:
		return m.handleEnvTabActions(actions, msg)
	case tabIDPrompt:
		return m.handlePromptTabActions(actions, msg)
	case tabIDLogs:
		return m.handleLogsTabActions(actions, msg)
	case tabIDProgress:
		return m.handleProgressTabActions(actions, msg)
	default:
		return false, nil
	}
}

// handleGlobalAction handles actions that work across all tabs.
func (m *model) handleGlobalAction(act Action, msg tea.KeyMsg) (bool, tea.Cmd) {
	_ = msg // unused, but kept for potential future use

	switch act {
	case ActInterrupt:
		if m.running && m.cancel != nil {
			m.cancelling = true
			m.status = "Cancelling run…"
			m.cancel()
			return true, nil
		}
		if m.dirty {
			m.beginQuitConfirm()
			return true, nil
		}
		m.Cleanup()
		return true, tea.Quit
	case ActQuit:
		if m.running {
			return true, nil
		}
		if m.dirty {
			m.beginQuitConfirm()
			return true, nil
		}
		m.Cleanup()
		return true, tea.Quit
	case ActHelp:
		m.showHelp = !m.showHelp
		if m.showHelp {
			m.blurAllInputs()
		}
		return true, nil
	case ActSave:
		return true, m.handleSaveShortcut()
	case ActResetDefaults:
		return true, m.resetToDefaults()
	case ActGotoTab1, ActGotoTab2, ActGotoTab3, ActGotoTab4, ActGotoTab5, ActGotoTab6, ActGotoTab7, ActGotoTab8:
		if idx, ok := tabIndexFromAction(act); ok && m.setActiveTabIndex(idx) {
			m.blurAllInputs()
			// Trigger async tracker load when switching to Progress tab
			if m.currentTabID() == tabIDProgress && !m.trackerLoaded {
				return true, loadTrackerCmd(m.cfg.RepoPath)
			}
			return true, nil
		}
	}
	return false, nil
}

// handleQuitConfirmation handles key events in the quit confirmation dialog.
func (m *model) handleQuitConfirmation(msg tea.KeyMsg) (bool, tea.Cmd) {
	switch msg.Type {
	case tea.KeyLeft:
		m.moveQuitSelection(-1)
		return true, nil
	case tea.KeyRight:
		m.moveQuitSelection(1)
		return true, nil
	case tea.KeyTab:
		m.moveQuitSelection(1)
		return true, nil
	case tea.KeyShiftTab:
		m.moveQuitSelection(-1)
		return true, nil
	case tea.KeyEsc, tea.KeyCtrlC:
		m.cancelQuitConfirm()
		return true, nil
	case tea.KeyEnter:
		return m.executeQuitSelection()
	}

	switch strings.ToLower(msg.String()) {
	case "s":
		m.quitConfirmIndex = 0
		return m.executeQuitSelection()
	case "d":
		m.quitConfirmIndex = 1
		return m.executeQuitSelection()
	case "c":
		m.cancelQuitConfirm()
		return true, nil
	}

	return false, nil
}

// executeQuitSelection executes the selected quit action.
func (m *model) executeQuitSelection() (bool, tea.Cmd) {
	if !m.quitConfirmActive {
		return false, nil
	}

	switch m.quitConfirmIndex {
	case 0: // Save
		// Set a flag so the save result handler knows to quit after save
		m.quitAfterSave = true
		return true, m.saveConfig()
	case 1: // Discard
		m.cancelQuitConfirm()
		m.Cleanup()
		return true, tea.Quit
	default: // Cancel
		m.cancelQuitConfirm()
		m.updateDirtyState()
		return true, nil
	}
}

// tabIndexFromAction maps a goto tab action to its index.
func tabIndexFromAction(act Action) (int, bool) {
	for i, tabAction := range tabActions {
		if tabAction == act {
			return i, true
		}
	}
	return 0, false
}

// isRuneKey returns true if the key event represents a rune input.
func isRuneKey(msg tea.KeyMsg) bool {
	return msg.Type == tea.KeyRunes && len(msg.Runes) > 0
}

// isDigitKey returns true if the key event is a single digit (0-9).
func isDigitKey(msg tea.KeyMsg) bool {
	if msg.Type != tea.KeyRunes || len(msg.Runes) != 1 {
		return false
	}
	r := msg.Runes[0]
	return r >= '0' && r <= '9'
}
