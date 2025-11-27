package tui

import (
	"github.com/SimoKiihamaki/autodev/internal/utils"
	clipboard "github.com/atotto/clipboard"
	tea "github.com/charmbracelet/bubbletea"
)

// handleRunTabActions handles key actions for the Run tab.
func (m *model) handleRunTabActions(actions []Action, msg tea.KeyMsg) (bool, tea.Cmd) {
	if len(actions) == 0 {
		return false, nil
	}

	var cmds []tea.Cmd
	handled := false

	hasFeed := len(m.runFeedBuf) > 0 || m.running

	for _, act := range actions {
		switch act {
		case ActConfirm:
			if m.isActiveOrCancelling() {
				note := "Cannot start new run while current run is active"
				m.status = note
				if flash := m.flash(note, 0); flash != nil {
					cmds = append(cmds, flash)
				}
				handled = true
				break
			}
			if cmd := m.startRunCmd(); cmd != nil {
				cmds = append(cmds, cmd)
			}
			handled = true
		case ActCopyError:
			text := getLastErrorText(m)
			note := ""
			if text == "" {
				note = "No error available to copy"
			} else {
				if err := clipboard.WriteAll(text); err != nil {
					note = "Failed to copy error: " + err.Error()
				} else {
					note = "Error copied to clipboard"
				}
			}
			m.status = note
			if note != "" {
				if flash := m.flash(note, 0); flash != nil {
					cmds = append(cmds, flash)
				}
			}
			handled = true
		case ActNavigateUp, ActNavigateDown:
			if !hasFeed {
				continue
			}
			var cmd tea.Cmd
			m.runFeed, cmd = m.runFeed.Update(msg)
			cmds = append(cmds, cmd)
			m.updateRunFeedFollowFromViewport()
			handled = true
		case ActPageUp:
			if !hasFeed {
				continue
			}
			m.runFeed.LineUp(10)
			m.updateRunFeedFollowFromViewport()
			handled = true
		case ActPageDown:
			if !hasFeed {
				continue
			}
			m.runFeed.LineDown(10)
			m.updateRunFeedFollowFromViewport()
			handled = true
		case ActScrollTop:
			if !hasFeed {
				continue
			}
			m.runFeed.GotoTop()
			m.updateRunFeedFollowFromViewport()
			handled = true
		case ActScrollBottom:
			if !hasFeed {
				continue
			}
			m.runFeed.GotoBottom()
			m.updateRunFeedFollowFromViewport()
			handled = true
		case ActToggleFollow:
			m.followLogs = !m.followLogs
			m.cfg.FollowLogs = utils.BoolPtr(m.followLogs)
			m.runFeedAutoFollow = m.followLogs
			if m.runFeedAutoFollow && len(m.runFeedBuf) > 0 {
				m.runFeed.GotoBottom()
			}
			m.updateDirtyState()
			handled = true
		}
	}

	if handled {
		return true, batchCmd(cmds)
	}
	return false, nil
}
