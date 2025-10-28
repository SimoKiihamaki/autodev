package tui

import tea "github.com/charmbracelet/bubbletea"

// envFlagKeyMap documents the single-letter key bindings and their corresponding
// config flag names; keep in sync with envFlagNames/model fields.
var envFlagKeyMap = map[string]string{
	"l": "local",
	"p": "pr",
	"r": "review",
	"a": "unsafe",
	"d": "dryrun",
	"g": "syncgit",
	"i": "infinite",
}

// tryNavigateOrCycle attempts navigation within the settings input list; if focus remains unchanged
// (i.e., navigation is blocked or does not change the focused input, such as at grid boundaries or other non-navigable states),
// cycles the current toggle instead. This provides fallback behavior whenever directional movement is blocked or at the start/end of the list.
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

func (m *model) handleSettingsTabKey(msg tea.KeyMsg) (model, tea.Cmd) {
	if msg.Type == tea.KeyEnter && m.focusedInput == "" {
		m.focusInput("repo")
		return *m, nil
	}

	switch msg.String() {
	case "esc":
		m.blurAllInputs()
		return *m, nil
	case "tab":
		if m.focusedInput == "" {
			m.focusInput("repo")
		} else {
			m.navigateSettings("down")
		}
		return *m, nil
	case "shift+tab":
		m.navigateSettings("up")
		return *m, nil
	case "up":
		if m.focusedInput == "" {
			m.focusInput("repo")
		} else {
			m.navigateSettings("up")
		}
		return *m, nil
	case "down":
		if m.focusedInput == "" {
			m.focusInput("repo")
		} else {
			m.navigateSettings("down")
		}
		return *m, nil
	case "alt+left":
		if m.focusedInput != "" {
			m.navigateSettings("left")
			return *m, nil
		}
	case "alt+right":
		if m.focusedInput != "" {
			m.navigateSettings("right")
			return *m, nil
		}
	case "alt+up":
		if m.focusedInput != "" {
			m.navigateSettings("up")
			return *m, nil
		}
	case "alt+down":
		if m.focusedInput != "" {
			m.navigateSettings("down")
			return *m, nil
		}
	case "ctrl+s":
		return *m, m.saveConfig()
	case "left":
		if m.focusedInput == "" {
			m.focusInput("repo")
			return *m, nil
		}
		if isExecutorToggle(m.focusedInput) {
			m.tryNavigateOrCycle("left", -1)
			return *m, nil
		}
		m.navigateSettings("left")
		return *m, nil
	case "right":
		if m.focusedInput == "" {
			m.focusInput("repo")
			return *m, nil
		}
		if isExecutorToggle(m.focusedInput) {
			m.tryNavigateOrCycle("right", 1)
			return *m, nil
		}
		m.navigateSettings("right")
		return *m, nil
	}

	if m.focusedInput != "" {
		if isExecutorToggle(m.focusedInput) {
			switch msg.String() {
			case "enter":
				m.cycleExecutorChoice(m.focusedInput, 1)
				return *m, nil
			case "space":
				m.cycleExecutorChoice(m.focusedInput, -1)
				return *m, nil
			}
			return *m, nil
		}
		field := m.getInputField(m.focusedInput)
		if field != nil {
			var cmd tea.Cmd
			*field, cmd = field.Update(msg)
			return *m, cmd
		}
	}
	return *m, nil
}

func (m *model) handleEnvTabKey(msg tea.KeyMsg) (model, tea.Cmd) {
	switch msg.String() {
	case "esc":
		m.focusedFlag = ""
		return *m, nil
	case "up":
		m.navigateFlags("up")
		return *m, nil
	case "down":
		m.navigateFlags("down")
		return *m, nil
	case "left":
		if m.focusedFlag != "" {
			m.navigateFlags("left")
		}
		return *m, nil
	case "right":
		if m.focusedFlag != "" {
			m.navigateFlags("right")
		}
		return *m, nil
	case "enter":
		if m.focusedFlag == "" {
			if len(envFlagNames) == 0 {
				return *m, nil
			}
			m.focusFlag(envFlagNames[0])
		} else {
			m.toggleFocusedFlag()
		}
		return *m, nil
	case "ctrl+s":
		return *m, m.saveConfig()
	default:
		if name, ok := envFlagKeyMap[msg.String()]; ok {
			m.focusFlag(name)
			m.toggleFocusedFlag()
			return *m, nil
		}
	}
	return *m, nil
}

func (m *model) handlePromptTabKey(msg tea.KeyMsg) (model, tea.Cmd) {
	switch msg.String() {
	case "enter":
		if !m.prompt.Focused() {
			m.prompt.Focus()
			return *m, nil
		}
	case "esc":
		if m.prompt.Focused() {
			m.prompt.Blur()
			return *m, nil
		}
	case "ctrl+s":
		return *m, m.saveConfig()
	}
	var cmd tea.Cmd
	m.prompt, cmd = m.prompt.Update(msg)
	return *m, cmd
}
