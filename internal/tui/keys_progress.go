package tui

import tea "github.com/charmbracelet/bubbletea"

// handleProgressTabActions handles key actions for the Progress tab.
func (m *model) handleProgressTabActions(actions []Action, msg tea.KeyMsg) (bool, tea.Cmd) {
	if len(actions) == 0 {
		return false, nil
	}

	handled := false
	var cmd tea.Cmd

	for _, act := range actions {
		switch act {
		case ActRefresh:
			// Refresh tracker data asynchronously
			m.trackerLoaded = false
			m.tracker = nil
			m.trackerErr = nil
			m.status = "Refreshing tracker..."
			cmd = loadTrackerCmd(m.cfg.RepoPath)
			handled = true
		case ActNavigateUp, ActNavigateDown:
			// Future: scroll through feature list
			handled = true
		case ActConfirm:
			// Future: expand feature details
			handled = true
		}
	}

	return handled, cmd
}
