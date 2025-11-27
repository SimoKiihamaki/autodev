package tui

import (
	"strings"

	"github.com/charmbracelet/bubbles/list"
	tea "github.com/charmbracelet/bubbletea"
)

// handlePRDTabActions handles key actions for the PRD selection tab.
func (m *model) handlePRDTabActions(actions []Action, msg tea.KeyMsg) (bool, tea.Cmd) {
	var cmds []tea.Cmd

	// Handle tag input when focused
	if m.tagInput.Focused() {
		handled := false
		for _, act := range actions {
			switch act {
			case ActConfirm:
				if tag := strings.TrimSpace(m.tagInput.Value()); tag != "" {
					m.tags = append(m.tags, tag)
					m.tagInput.SetValue("")
					m.tagInput.Blur()
					m.updateDirtyState()
				}
				handled = true
			case ActCancel:
				m.tagInput.Blur()
				handled = true
			}
		}
		if handled {
			return true, nil
		}
		// Allow Ctrl+S to pass through for global save
		if msg.Type == tea.KeyCtrlS {
			return false, nil
		}
		var cmd tea.Cmd
		m.tagInput, cmd = m.tagInput.Update(msg)
		return true, cmd
	}

	// Handle list navigation when no specific action
	if len(actions) == 0 {
		var cmd tea.Cmd
		prevFilter := m.prdList.FilterState()
		m.prdList, cmd = m.prdList.Update(msg)
		if prevFilter == list.Filtering {
			return true, cmd
		}
		if isDigitKey(msg) {
			if m.prdList.FilterState() == list.Filtering {
				m.prdList.ResetFilter()
			}
			return false, cmd
		}
		if m.prdList.FilterState() == list.Filtering {
			return true, cmd
		}
		if isRuneKey(msg) {
			return true, cmd
		}
		return false, cmd
	}

	handled := false

	for _, act := range actions {
		switch act {
		case ActConfirm:
			if sel, ok := m.prdList.SelectedItem().(item); ok {
				m.selectedPRD = sel.path
				if meta, ok := m.cfg.PRDs[sel.path]; ok {
					m.tags = append([]string{}, meta.Tags...)
				} else {
					m.tags = []string{}
				}
				m.updateDirtyState()
				// Load preview for newly selected PRD
				cmds = append(cmds, m.loadPRDPreviewCmd())
			}
			handled = true
		case ActFocusTags:
			m.tagInput.Focus()
			handled = true
		case ActNavigateLeft, ActNavigateRight:
			var cmd tea.Cmd
			m.prdList, cmd = m.prdList.Update(msg)
			cmds = append(cmds, cmd)
			handled = true
		case ActListBackspace:
			if m.prdList.FilterState() == list.Filtering {
				var cmd tea.Cmd
				m.prdList, cmd = m.prdList.Update(msg)
				cmds = append(cmds, cmd)
			} else if len(m.tags) > 0 {
				m.tags = m.tags[:len(m.tags)-1]
				m.updateDirtyState()
			}
			handled = true
		case ActRescanPRDs:
			m.rescanPRDs()
			cmds = append(cmds, m.scanPRDsCmd())
			handled = true
		}
	}

	if handled {
		return true, batchCmd(cmds)
	}
	// Allow Ctrl+S to pass through for global save
	if msg.Type == tea.KeyCtrlS {
		return false, nil
	}
	return false, batchCmd(cmds)
}
