package tui

import tea "github.com/charmbracelet/bubbletea"

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
		m.navigateSettings("down")
		return *m, nil
	case "shift+tab":
		m.navigateSettings("up")
		return *m, nil
	case "left":
		if m.focusedInput != "" {
			m.navigateSettings("left")
			return *m, nil
		}
	case "right":
		if m.focusedInput != "" {
			m.navigateSettings("right")
			return *m, nil
		}
	case "up":
		if m.focusedInput != "" {
			m.navigateSettings("up")
			return *m, nil
		}
	case "down":
		if m.focusedInput != "" {
			m.navigateSettings("down")
			return *m, nil
		}
	case "s":
		return *m, m.saveConfig()
	}

	if m.focusedInput != "" {
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
			m.focusFlag(envFlagNames[0])
		} else {
			m.toggleFocusedFlag()
		}
		return *m, nil
	case "l":
		m.focusFlag("local")
		m.toggleFocusedFlag()
		return *m, nil
	case "p":
		m.focusFlag("pr")
		m.toggleFocusedFlag()
		return *m, nil
	case "r":
		m.focusFlag("review")
		m.toggleFocusedFlag()
		return *m, nil
	case "a":
		m.focusFlag("unsafe")
		m.toggleFocusedFlag()
		return *m, nil
	case "d":
		m.focusFlag("dryrun")
		m.toggleFocusedFlag()
		return *m, nil
	case "g":
		m.focusFlag("syncgit")
		m.toggleFocusedFlag()
		return *m, nil
	case "i":
		m.focusFlag("infinite")
		m.toggleFocusedFlag()
		return *m, nil
	case "s":
		return *m, m.saveConfig()
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
	case "s":
		return *m, m.saveConfig()
	}
	var cmd tea.Cmd
	m.prompt, cmd = m.prompt.Update(msg)
	return *m, cmd
}
