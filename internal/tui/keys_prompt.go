package tui

import (
	tea "github.com/charmbracelet/bubbletea"
)

// handlePromptTabActions handles key actions for the Initial Prompt tab.
func (m *model) handlePromptTabActions(actions []Action, msg tea.KeyMsg) (bool, tea.Cmd) {
	handled := false
	var cmds []tea.Cmd

	for _, act := range actions {
		switch act {
		case ActConfirm:
			if !m.prompt.Focused() {
				m.prompt.Focus()
				handled = true
			}
		case ActCancel:
			if m.prompt.Focused() {
				m.prompt.Blur()
				handled = true
			}
		}
	}

	if handled {
		return true, batchCmd(cmds)
	}

	if !m.prompt.Focused() {
		return false, nil
	}

	// Allow Ctrl+S to pass through for global save
	if msg.Type == tea.KeyCtrlS {
		return false, nil
	}

	var cmd tea.Cmd
	m.prompt, cmd = m.prompt.Update(msg)
	return true, cmd
}
