package tui

import (
	"strings"
	"time"

	"github.com/SimoKiihamaki/autodev/internal/config"
	"github.com/charmbracelet/bubbles/list"
	tea "github.com/charmbracelet/bubbletea"
)

func (m model) handleKeyMsg(msg tea.KeyMsg) (model, tea.Cmd) {
	mPtr := &m

	if handled, cmd := mPtr.handleGlobalKey(msg); handled {
		return *mPtr, cmd
	}

	switch mPtr.tab {
	case tabRun:
		return mPtr.handleRunTabKey(msg)
	case tabPRD:
		return mPtr.handlePRDTabKey(msg)
	case tabSettings:
		return mPtr.handleSettingsTabKey(msg)
	case tabEnv:
		return mPtr.handleEnvTabKey(msg)
	case tabPrompt:
		return mPtr.handlePromptTabKey(msg)
	case tabLogs:
		var cmd tea.Cmd
		mPtr.logs, cmd = mPtr.logs.Update(msg)
		return *mPtr, cmd
	default:
		return *mPtr, nil
	}
}

func (m *model) handleGlobalKey(msg tea.KeyMsg) (bool, tea.Cmd) {
	switch msg.String() {
	case "ctrl+c":
		if m.running && m.cancel != nil {
			m.cancelling = true
			m.status = "Cancelling run…"
			m.cancel()
			return true, nil
		}
		m.closeLogFile("quit")
		return true, tea.Quit
	case "q":
		if m.running {
			return true, nil
		}
		m.closeLogFile("quit")
		return true, tea.Quit
	case "?":
		m.tab = tabHelp
		m.blurAllInputs()
		return true, nil
	case "1", "2", "3", "4", "5", "6":
		if len(msg.Runes) == 0 {
			return true, nil
		}
		idx := int(msg.Runes[0] - '1')
		if idx >= 0 && idx < len(tabNames) {
			m.tab = tab(idx)
			m.blurAllInputs()
		}
		return true, nil
	}
	return false, nil
}

func (m *model) handleRunTabKey(msg tea.KeyMsg) (model, tea.Cmd) {
	switch msg.String() {
	case "enter":
		if m.isActiveOrCancelling() {
			return *m, nil
		}
		return *m, m.startRunCmd()
	case "up", "down":
		if len(m.runFeedBuf) > 0 || m.running {
			var cmd tea.Cmd
			m.runFeed, cmd = m.runFeed.Update(msg)
			m.updateRunFeedFollowFromViewport()
			return *m, cmd
		}
	case "pgup":
		if len(m.runFeedBuf) > 0 || m.running {
			m.runFeed.LineUp(10)
			m.updateRunFeedFollowFromViewport()
			return *m, nil
		}
	case "pgdown":
		if len(m.runFeedBuf) > 0 || m.running {
			m.runFeed.LineDown(10)
			m.updateRunFeedFollowFromViewport()
			return *m, nil
		}
	case "home":
		if len(m.runFeedBuf) > 0 || m.running {
			m.runFeed.GotoTop()
			m.updateRunFeedFollowFromViewport()
			return *m, nil
		}
	case "end":
		if len(m.runFeedBuf) > 0 || m.running {
			m.runFeed.GotoBottom()
			m.updateRunFeedFollowFromViewport()
			return *m, nil
		}
	case "f":
		if len(m.runFeedBuf) > 0 || m.running {
			m.runFeedAutoFollow = !m.runFeedAutoFollow
			if m.runFeedAutoFollow {
				m.runFeed.GotoBottom()
			}
		}
		return *m, nil
	}
	return *m, nil
}

func (m *model) handlePRDTabKey(msg tea.KeyMsg) (model, tea.Cmd) {
	if m.tagInput.Focused() {
		switch msg.String() {
		case "enter":
			if tag := strings.TrimSpace(m.tagInput.Value()); tag != "" {
				m.tags = append(m.tags, tag)
				m.tagInput.SetValue("")
				m.tagInput.Blur()
			}
			return *m, nil
		case "esc":
			m.tagInput.Blur()
			return *m, nil
		}
		var cmd tea.Cmd
		m.tagInput, cmd = m.tagInput.Update(msg)
		return *m, cmd
	}

	switch msg.String() {
	case "enter":
		if sel, ok := m.prdList.SelectedItem().(item); ok {
			m.selectedPRD = sel.path
			if meta, ok := m.cfg.PRDs[sel.path]; ok {
				m.tags = append([]string{}, meta.Tags...)
			} else {
				m.tags = []string{}
			}
		}
		return *m, nil
	case "t":
		m.tagInput.Focus()
		return *m, nil
	case "left", "right":
		var cmd tea.Cmd
		m.prdList, cmd = m.prdList.Update(msg)
		return *m, cmd
	case "backspace":
		if m.prdList.FilterState() == list.Filtering {
			var cmd tea.Cmd
			m.prdList, cmd = m.prdList.Update(msg)
			return *m, cmd
		}
		if len(m.tags) > 0 {
			m.tags = m.tags[:len(m.tags)-1]
		}
		return *m, nil
	case "s":
		if m.selectedPRD == "" {
			m.status = "Select a PRD before saving metadata"
			return *m, nil
		}
		normalized := make([]string, 0, len(m.tags))
		seen := make(map[string]struct{}, len(m.tags))
		for _, tag := range m.tags {
			tag = strings.TrimSpace(tag)
			if tag == "" {
				continue
			}
			lower := strings.ToLower(tag)
			if _, ok := seen[lower]; ok {
				continue
			}
			seen[lower] = struct{}{}
			normalized = append(normalized, tag)
		}
		if m.cfg.PRDs == nil {
			m.cfg.PRDs = make(map[string]config.PRDMeta)
		}
		meta := m.cfg.PRDs[m.selectedPRD]
		meta.Tags = normalized
		meta.LastUsed = time.Now()
		m.cfg.PRDs[m.selectedPRD] = meta
		if err := config.Save(m.cfg); err != nil {
			m.errMsg = err.Error()
			m.status = "Failed to save PRD metadata"
		} else {
			m.errMsg = ""
			m.status = "Saved PRD metadata for " + abbreviatePath(m.selectedPRD)
		}
		return *m, nil
	case "r":
		m.rescanPRDs()
		return *m, m.scanPRDsCmd()
	default:
		var cmd tea.Cmd
		m.prdList, cmd = m.prdList.Update(msg)
		return *m, cmd
	}
}
