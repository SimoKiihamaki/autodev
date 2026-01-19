package tui

import (
	"strings"

	"github.com/charmbracelet/bubbles/textinput"
	tea "github.com/charmbracelet/bubbletea"
)

// Boolean input fields that can be toggled with Space
var booleanInputs = map[string]bool{
	"ralphenabled":         true,
	"ralphautoaddsigns":    true,
	"ralphshowprogresslog": true,
	"ralphshowguardrails":  true,
}

func isBooleanInput(name string) bool {
	return booleanInputs[name]
}

// handleSettingsTabActions handles key actions for the Settings tab.
func (m *model) handleSettingsTabActions(actions []Action, msg tea.KeyMsg) (bool, tea.Cmd) {
	handled := false

	// Handle direct input updates when focused on non-toggle field
	if len(actions) == 0 {
		if m.focusedInput != "" && !isExecutorToggle(m.focusedInput) {
			// Toggle boolean inputs with Space
			if msg.Type == tea.KeySpace && isBooleanInput(m.focusedInput) {
				return m.toggleBooleanInput()
			}
			// For non-boolean fields, update directly via the model's actual field
			// This avoids the stale pointer issue with settingsInputs map
			if actualField := m.getActualInputField(m.focusedInput); actualField != nil {
				// Allow Ctrl+S to pass through for global save
				if msg.Type == tea.KeyCtrlS {
					return false, nil
				}
				// On first printable character when cursor is at start of non-empty field, clear for easier editing
				if isRuneKey(msg) && actualField.Value() != "" && actualField.Position() == 0 {
					actualField.SetValue("")
				}
				updatedField, cmd := actualField.Update(msg)
				// Write the updated field back to the model
				m.setActualInputField(m.focusedInput, updatedField)
				m.updateDirtyState()
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
			// 3. If boolean input is focused: toggle the value
			// 4. If regular field is focused: navigate to next field
			if m.focusedInput == "" {
				m.focusInput("repo")
			} else if isExecutorToggle(m.focusedInput) {
				m.cycleExecutorChoice(m.focusedInput, 1)
			} else if isBooleanInput(m.focusedInput) {
				m.toggleBooleanInput()
			} else {
				m.navigateSettings("down")
			}
			handled = true
		case ActCycleBackward:
			if isBooleanInput(m.focusedInput) {
				m.toggleBooleanInput()
				handled = true
			} else if isExecutorToggle(m.focusedInput) {
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
		// Toggle boolean inputs with Space
		if msg.Type == tea.KeySpace && isBooleanInput(m.focusedInput) {
			return m.toggleBooleanInput()
		}
		// For non-boolean fields, update directly via the model's actual field
		// This avoids the stale pointer issue with settingsInputs map
		if actualField := m.getActualInputField(m.focusedInput); actualField != nil {
			// Allow Ctrl+S to pass through for global save
			if msg.Type == tea.KeyCtrlS {
				return false, nil
			}
			// On first printable character when cursor is at start of non-empty field, clear for easier editing
			if isRuneKey(msg) && actualField.Value() != "" && actualField.Position() == 0 {
				actualField.SetValue("")
			}
			updatedField, cmd := actualField.Update(msg)
			// Write the updated field back to the model
			m.setActualInputField(m.focusedInput, updatedField)
			m.updateDirtyState()
			return true, cmd
		}
	}

	return false, nil
}

// toggleBooleanInput toggles the value of the currently focused boolean input.
func (m *model) toggleBooleanInput() (bool, tea.Cmd) {
	field := m.getInputField(m.focusedInput)
	if field == nil {
		return false, nil
	}
	// Sync current value from model field first (fixes stale pointer issue)
	m.syncInputFieldFromModel(m.focusedInput, field)
	current := strings.ToLower(strings.TrimSpace(field.Value()))
	var newValue string
	if current == "true" || current == "1" || current == "yes" {
		newValue = "false"
	} else {
		newValue = "true"
	}
	field.SetValue(newValue)
	// Sync back to model field
	m.syncInputField(m.focusedInput, field)
	m.updateDirtyState()
	return true, nil
}

// syncInputField copies the value from the map pointer back to the model's actual field.
// This is necessary because the settingsInputs map contains pointers that may become
// stale when the model is copied by Bubble Tea.
func (m *model) syncInputField(name string, field *textinput.Model) {
	switch name {
	case "repo":
		m.inRepo.SetValue(field.Value())
	case "base":
		m.inBase.SetValue(field.Value())
	case "branch":
		m.inBranch.SetValue(field.Value())
	case "codex":
		m.inCodexModel.SetValue(field.Value())
	case "pycmd":
		m.inPyCmd.SetValue(field.Value())
	case "pyscript":
		m.inPyScript.SetValue(field.Value())
	case "policy":
		m.inPolicy.SetValue(field.Value())
	case "waitmin":
		m.inWaitMin.SetValue(field.Value())
	case "pollsec":
		m.inPollSec.SetValue(field.Value())
	case "idlemin":
		m.inIdleMin.SetValue(field.Value())
	case "maxiters":
		m.inMaxIters.SetValue(field.Value())
	case "codextimeout":
		m.inCodexTimeout.SetValue(field.Value())
	case "claudetimeout":
		m.inClaudeTimeout.SetValue(field.Value())
	// Ralph settings
	case "ralphenabled":
		m.inRalphEnabled.SetValue(field.Value())
	case "ralphcontextrotate":
		m.inRalphContextRotate.SetValue(field.Value())
	case "ralphmaxconsecutive":
		m.inRalphMaxConsecutive.SetValue(field.Value())
	case "ralphautoaddsigns":
		m.inRalphAutoAddSigns.SetValue(field.Value())
	case "ralphshowprogresslog":
		m.inRalphShowProgressLog.SetValue(field.Value())
	case "ralphshowguardrails":
		m.inRalphShowGuardrails.SetValue(field.Value())
	case "ralphguttertimeout":
		m.inRalphGutterTimeout.SetValue(field.Value())
	case "ralphgutternoprogress":
		m.inRalphGutterNoProgress.SetValue(field.Value())
	}
}

// syncInputFieldFromModel copies the value from the model's actual field to the map pointer.
// This is the inverse of syncInputField.
func (m *model) syncInputFieldFromModel(name string, field *textinput.Model) {
	switch name {
	case "repo":
		field.SetValue(m.inRepo.Value())
	case "base":
		field.SetValue(m.inBase.Value())
	case "branch":
		field.SetValue(m.inBranch.Value())
	case "codex":
		field.SetValue(m.inCodexModel.Value())
	case "pycmd":
		field.SetValue(m.inPyCmd.Value())
	case "pyscript":
		field.SetValue(m.inPyScript.Value())
	case "policy":
		field.SetValue(m.inPolicy.Value())
	case "waitmin":
		field.SetValue(m.inWaitMin.Value())
	case "pollsec":
		field.SetValue(m.inPollSec.Value())
	case "idlemin":
		field.SetValue(m.inIdleMin.Value())
	case "maxiters":
		field.SetValue(m.inMaxIters.Value())
	case "codextimeout":
		field.SetValue(m.inCodexTimeout.Value())
	case "claudetimeout":
		field.SetValue(m.inClaudeTimeout.Value())
	// Ralph settings
	case "ralphenabled":
		field.SetValue(m.inRalphEnabled.Value())
	case "ralphcontextrotate":
		field.SetValue(m.inRalphContextRotate.Value())
	case "ralphmaxconsecutive":
		field.SetValue(m.inRalphMaxConsecutive.Value())
	case "ralphautoaddsigns":
		field.SetValue(m.inRalphAutoAddSigns.Value())
	case "ralphshowprogresslog":
		field.SetValue(m.inRalphShowProgressLog.Value())
	case "ralphshowguardrails":
		field.SetValue(m.inRalphShowGuardrails.Value())
	case "ralphguttertimeout":
		field.SetValue(m.inRalphGutterTimeout.Value())
	case "ralphgutternoprogress":
		field.SetValue(m.inRalphGutterNoProgress.Value())
	}
}

// getActualInputField returns a pointer to the actual model field for the given input name.
// This returns the real field in the model, not a stale pointer from the settingsInputs map.
func (m *model) getActualInputField(name string) *textinput.Model {
	switch name {
	case "repo":
		return &m.inRepo
	case "base":
		return &m.inBase
	case "branch":
		return &m.inBranch
	case "codex":
		return &m.inCodexModel
	case "pycmd":
		return &m.inPyCmd
	case "pyscript":
		return &m.inPyScript
	case "policy":
		return &m.inPolicy
	case "waitmin":
		return &m.inWaitMin
	case "pollsec":
		return &m.inPollSec
	case "idlemin":
		return &m.inIdleMin
	case "maxiters":
		return &m.inMaxIters
	case "codextimeout":
		return &m.inCodexTimeout
	case "claudetimeout":
		return &m.inClaudeTimeout
	// Ralph settings
	case "ralphenabled":
		return &m.inRalphEnabled
	case "ralphcontextrotate":
		return &m.inRalphContextRotate
	case "ralphmaxconsecutive":
		return &m.inRalphMaxConsecutive
	case "ralphautoaddsigns":
		return &m.inRalphAutoAddSigns
	case "ralphshowprogresslog":
		return &m.inRalphShowProgressLog
	case "ralphshowguardrails":
		return &m.inRalphShowGuardrails
	case "ralphguttertimeout":
		return &m.inRalphGutterTimeout
	case "ralphgutternoprogress":
		return &m.inRalphGutterNoProgress
	}
	return nil
}

// setActualInputField updates the actual model field with the given textinput.Model value.
// It uses getActualInputField to avoid duplicating the switch statement.
func (m *model) setActualInputField(name string, field textinput.Model) {
	if actual := m.getActualInputField(name); actual != nil {
		*actual = field
	}
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
