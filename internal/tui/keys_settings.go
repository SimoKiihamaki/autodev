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

// inputFieldAccessors centralizes the mapping from setting names to their corresponding
// textinput.Model fields on the model. This avoids duplicating large switch statements.
type inputFieldGetter func(*model) *textinput.Model
type inputFieldSetter func(*model, string)

var inputFieldAccessors = map[string]struct {
	get inputFieldGetter
	set inputFieldSetter
}{
	"repo": {
		get: func(m *model) *textinput.Model { return &m.inRepo },
		set: func(m *model, v string) { m.inRepo.SetValue(v) },
	},
	"base": {
		get: func(m *model) *textinput.Model { return &m.inBase },
		set: func(m *model, v string) { m.inBase.SetValue(v) },
	},
	"branch": {
		get: func(m *model) *textinput.Model { return &m.inBranch },
		set: func(m *model, v string) { m.inBranch.SetValue(v) },
	},
	"codex": {
		get: func(m *model) *textinput.Model { return &m.inCodexModel },
		set: func(m *model, v string) { m.inCodexModel.SetValue(v) },
	},
	"pycmd": {
		get: func(m *model) *textinput.Model { return &m.inPyCmd },
		set: func(m *model, v string) { m.inPyCmd.SetValue(v) },
	},
	"pyscript": {
		get: func(m *model) *textinput.Model { return &m.inPyScript },
		set: func(m *model, v string) { m.inPyScript.SetValue(v) },
	},
	"policy": {
		get: func(m *model) *textinput.Model { return &m.inPolicy },
		set: func(m *model, v string) { m.inPolicy.SetValue(v) },
	},
	"waitmin": {
		get: func(m *model) *textinput.Model { return &m.inWaitMin },
		set: func(m *model, v string) { m.inWaitMin.SetValue(v) },
	},
	"pollsec": {
		get: func(m *model) *textinput.Model { return &m.inPollSec },
		set: func(m *model, v string) { m.inPollSec.SetValue(v) },
	},
	"idlemin": {
		get: func(m *model) *textinput.Model { return &m.inIdleMin },
		set: func(m *model, v string) { m.inIdleMin.SetValue(v) },
	},
	"maxiters": {
		get: func(m *model) *textinput.Model { return &m.inMaxIters },
		set: func(m *model, v string) { m.inMaxIters.SetValue(v) },
	},
	"codextimeout": {
		get: func(m *model) *textinput.Model { return &m.inCodexTimeout },
		set: func(m *model, v string) { m.inCodexTimeout.SetValue(v) },
	},
	"claudetimeout": {
		get: func(m *model) *textinput.Model { return &m.inClaudeTimeout },
		set: func(m *model, v string) { m.inClaudeTimeout.SetValue(v) },
	},
	"ralphenabled": {
		get: func(m *model) *textinput.Model { return &m.inRalphEnabled },
		set: func(m *model, v string) { m.inRalphEnabled.SetValue(v) },
	},
	"ralphcontextrotate": {
		get: func(m *model) *textinput.Model { return &m.inRalphContextRotate },
		set: func(m *model, v string) { m.inRalphContextRotate.SetValue(v) },
	},
	"ralphmaxconsecutive": {
		get: func(m *model) *textinput.Model { return &m.inRalphMaxConsecutive },
		set: func(m *model, v string) { m.inRalphMaxConsecutive.SetValue(v) },
	},
	"ralphautoaddsigns": {
		get: func(m *model) *textinput.Model { return &m.inRalphAutoAddSigns },
		set: func(m *model, v string) { m.inRalphAutoAddSigns.SetValue(v) },
	},
	"ralphshowprogresslog": {
		get: func(m *model) *textinput.Model { return &m.inRalphShowProgressLog },
		set: func(m *model, v string) { m.inRalphShowProgressLog.SetValue(v) },
	},
	"ralphshowguardrails": {
		get: func(m *model) *textinput.Model { return &m.inRalphShowGuardrails },
		set: func(m *model, v string) { m.inRalphShowGuardrails.SetValue(v) },
	},
	"ralphguttertimeout": {
		get: func(m *model) *textinput.Model { return &m.inRalphGutterTimeout },
		set: func(m *model, v string) { m.inRalphGutterTimeout.SetValue(v) },
	},
	"ralphgutternoprogress": {
		get: func(m *model) *textinput.Model { return &m.inRalphGutterNoProgress },
		set: func(m *model, v string) { m.inRalphGutterNoProgress.SetValue(v) },
	},
	"safescriptdirs": {
		get: func(m *model) *textinput.Model { return &m.inSafeScriptDirs },
		set: func(m *model, v string) { m.inSafeScriptDirs.SetValue(v) },
	},
	"allowedpythondirs": {
		get: func(m *model) *textinput.Model { return &m.inAllowedPythonDirs },
		set: func(m *model, v string) { m.inAllowedPythonDirs.SetValue(v) },
	},
}

// handleFocusedInputUpdate handles direct input updates when focused on a non-toggle field.
// This extracted helper eliminates code duplication between two call sites in handleSettingsTabActions.
func (m *model) handleFocusedInputUpdate(msg tea.KeyMsg) (bool, tea.Cmd) {
	if m.focusedInput == "" || isExecutorToggle(m.focusedInput) {
		return false, nil
	}

	// Toggle boolean inputs with Space
	if msg.Type == tea.KeySpace && isBooleanInput(m.focusedInput) {
		return m.toggleBooleanInput()
	}

	// For non-boolean fields, update directly via the model's actual field
	// This avoids the stale pointer issue with settingsInputs map
	accessor, ok := inputFieldAccessors[m.focusedInput]
	if !ok {
		return false, nil
	}
	actualField := accessor.get(m)

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
	*actualField = updatedField
	m.updateDirtyState()
	return true, cmd
}

// handleSettingsTabActions handles key actions for the Settings tab.
func (m *model) handleSettingsTabActions(actions []Action, msg tea.KeyMsg) (bool, tea.Cmd) {
	handled := false

	// Handle direct input updates when focused on non-toggle field
	if len(actions) == 0 {
		return m.handleFocusedInputUpdate(msg)
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
				return m.toggleBooleanInput()
			} else {
				m.navigateSettings("down")
			}
			handled = true
		case ActCycleBackward:
			if isBooleanInput(m.focusedInput) {
				return m.toggleBooleanInput()
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
	return m.handleFocusedInputUpdate(msg)
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
	if accessor, ok := inputFieldAccessors[name]; ok {
		accessor.set(m, field.Value())
	}
}

// syncInputFieldFromModel copies the value from the model's actual field to the map pointer.
// This is the inverse of syncInputField.
func (m *model) syncInputFieldFromModel(name string, field *textinput.Model) {
	if accessor, ok := inputFieldAccessors[name]; ok {
		actualField := accessor.get(m)
		field.SetValue(actualField.Value())
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
