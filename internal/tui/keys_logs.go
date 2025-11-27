package tui

import (
	"github.com/SimoKiihamaki/autodev/internal/utils"
	tea "github.com/charmbracelet/bubbletea"
)

// handleLogsTabActions handles key actions for the Logs tab.
func (m *model) handleLogsTabActions(actions []Action, msg tea.KeyMsg) (bool, tea.Cmd) {
	if len(actions) == 0 {
		return false, nil
	}

	var cmds []tea.Cmd
	handled := false

	for _, act := range actions {
		switch act {
		case ActNavigateUp, ActNavigateDown:
			var cmd tea.Cmd
			m.logs, cmd = m.logs.Update(msg)
			cmds = append(cmds, cmd)
			handled = true
		case ActPageUp:
			m.logs.LineUp(10)
			handled = true
		case ActPageDown:
			m.logs.LineDown(10)
			handled = true
		case ActScrollTop:
			m.logs.GotoTop()
			handled = true
		case ActScrollBottom:
			m.logs.GotoBottom()
			handled = true
		case ActToggleFollow:
			m.followLogs = !m.followLogs
			m.cfg.FollowLogs = utils.BoolPtr(m.followLogs)
			if m.followLogs {
				m.logs.GotoBottom()
			}
			m.runFeedAutoFollow = m.followLogs && m.runFeed.AtBottom()
			m.updateDirtyState()
			handled = true
		}
	}

	return handled, batchCmd(cmds)
}
