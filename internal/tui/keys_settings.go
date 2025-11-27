package tui

import (
	tea "github.com/charmbracelet/bubbletea"
)

// handleSettingsTabActions handles key actions for the Settings tab.
func (m *model) handleSettingsTabActions(actions []Action, msg tea.KeyMsg) (bool, tea.Cmd) {
	handled := false

	// Handle direct input updates when focused on non-toggle field
	if len(actions) == 0 {
		if m.focusedInput != "" && !isExecutorToggle(m.focusedInput) {
			if field := m.getInputField(m.focusedInput); field != nil {
				// Allow Ctrl+S to pass through for global save
				if msg.Type == tea.KeyCtrlS {
					return false, nil
				}
				prev := field.Value()
				var cmd tea.Cmd
				*field, cmd = field.Update(msg)
				if field.Value() != prev {
					m.updateDirtyState()
				}
				return true, cmd
			}
		}
		return false, nil
	}

	for _, act := range actions {
		switch act {
		case ActCancel:
			m.blurAllInputs()
			handled = true
		case ActTabForward:
			if m.focusedInput == "" {
				m.focusInput("repo")
			} else {
				m.navigateSettings("down")
			}
			handled = true
		case ActTabBackward:
			m.navigateSettings("up")
			handled = true
		case ActNavigateUp:
			if m.focusedInput == "" {
				m.focusInput("repo")
			} else {
				m.navigateSettings("up")
			}
			handled = true
		case ActNavigateDown:
			if m.focusedInput == "" {
				m.focusInput("repo")
			} else {
				m.navigateSettings("down")
			}
			handled = true
		case ActNavigateLeft:
			if m.focusedInput == "" {
				m.focusInput("repo")
			} else if isExecutorToggle(m.focusedInput) {
				m.tryNavigateOrCycle("left", -1)
			} else {
				m.navigateSettings("left")
			}
			handled = true
		case ActNavigateRight:
			if m.focusedInput == "" {
				m.focusInput("repo")
			} else if isExecutorToggle(m.focusedInput) {
				m.tryNavigateOrCycle("right", 1)
			} else {
				m.navigateSettings("right")
			}
			handled = true
		case ActAltNavigateLeft:
			if m.focusedInput != "" {
				m.navigateSettings("left")
				handled = true
			}
		case ActAltNavigateRight:
			if m.focusedInput != "" {
				m.navigateSettings("right")
				handled = true
			}
		case ActAltNavigateUp:
			if m.focusedInput != "" {
				m.navigateSettings("up")
				handled = true
			}
		case ActAltNavigateDown:
			if m.focusedInput != "" {
				m.navigateSettings("down")
				handled = true
			}
		case ActConfirm:
			// ActConfirm in settings tab has three contextual behaviors:
			// 1. If no field is focused: focus first field ("repo")
			// 2. If executor toggle is focused: cycle choice forward
			// 3. If regular field is focused: navigate to next field
			if m.focusedInput == "" {
				m.focusInput("repo")
			} else if isExecutorToggle(m.focusedInput) {
				m.cycleExecutorChoice(m.focusedInput, 1)
			} else {
				m.navigateSettings("down")
			}
			handled = true
		case ActCycleBackward:
			if isExecutorToggle(m.focusedInput) {
				m.cycleExecutorChoice(m.focusedInput, -1)
				handled = true
			}
		}
	}

	if handled {
		return true, nil
	}

	// Handle remaining input updates for focused non-toggle fields
	if m.focusedInput != "" && !isExecutorToggle(m.focusedInput) {
		if field := m.getInputField(m.focusedInput); field != nil {
			// Allow Ctrl+S to pass through for global save
			if msg.Type == tea.KeyCtrlS {
				return false, nil
			}
			prev := field.Value()
			var cmd tea.Cmd
			*field, cmd = field.Update(msg)
			if field.Value() != prev {
				m.updateDirtyState()
			}
			return true, cmd
		}
	}

	return false, nil
}

// tryNavigateOrCycle navigates the settings input list, or cycles the current toggle if navigation is blocked.
func (m *model) tryNavigateOrCycle(direction string, cycleDir int) {
	prev := m.focusedInput
	m.navigateSettings(direction)
	if m.focusedInput == prev && isExecutorToggle(m.focusedInput) {
		m.cycleExecutorChoice(m.focusedInput, cycleDir)
	}
	// If navigation is blocked and the current input is NOT an executor toggle,
	// no action is taken. This is intentional: only toggles are cycled as a fallback,
	// while other input types remain unchanged when navigation is blocked.
}
