package tui

import (
	"strings"
	"time"

	"github.com/SimoKiihamaki/autodev/internal/config"
	"github.com/charmbracelet/bubbles/list"
	tea "github.com/charmbracelet/bubbletea"
)

func batchCmd(cmds []tea.Cmd) tea.Cmd {
	switch len(cmds) {
	case 0:
		return nil
	case 1:
		return cmds[0]
	default:
		return tea.Batch(cmds...)
	}
}

func (m model) handleKeyMsg(msg tea.KeyMsg) (model, tea.Cmd) {
	mPtr := &m

	tabID := mPtr.currentTabID()
	perTabActions := mPtr.keys.TabActions(tabID, msg)

	if handled, cmd := mPtr.handleTabActions(tabID, perTabActions, msg); handled {
		mPtr.refreshTypingState()
		return *mPtr, cmd
	}

	mPtr.refreshTypingState()

	globalActions := mPtr.keys.GlobalActions(msg)
	for _, act := range globalActions {
		if mPtr.IsTyping() && mPtr.keys.IsTypingSensitive(act) {
			continue
		}
		if handled, cmd := mPtr.handleGlobalAction(act, msg); handled {
			mPtr.refreshTypingState()
			return *mPtr, cmd
		}
	}

	return *mPtr, nil
}

func (m *model) handleTabActions(tabID string, actions []Action, msg tea.KeyMsg) (bool, tea.Cmd) {
	switch tabID {
	case tabIDRun:
		return m.handleRunTabActions(actions, msg)
	case tabIDPRD:
		return m.handlePRDTabActions(actions, msg)
	case tabIDSettings:
		return m.handleSettingsTabActions(actions, msg)
	case tabIDEnv:
		return m.handleEnvTabActions(actions, msg)
	case tabIDPrompt:
		return m.handlePromptTabActions(actions, msg)
	case tabIDLogs:
		return m.handleLogsTabActions(actions, msg)
	default:
		return false, nil
	}
}

func (m *model) handleGlobalAction(act Action, msg tea.KeyMsg) (bool, tea.Cmd) {
	switch act {
	case ActInterrupt:
		if m.running && m.cancel != nil {
			m.cancelling = true
			m.status = "Cancelling run…"
			m.cancel()
			return true, nil
		}
		m.closeLogFile("quit")
		return true, tea.Quit
	case ActQuit:
		if m.running {
			return true, nil
		}
		m.closeLogFile("quit")
		return true, tea.Quit
	case ActHelp:
		m.tab = tabHelp
		m.blurAllInputs()
		return true, nil
	case ActGotoTab1, ActGotoTab2, ActGotoTab3, ActGotoTab4, ActGotoTab5, ActGotoTab6:
		if idx, ok := tabIndexFromAction(act); ok && idx >= 0 && idx < len(tabNames) {
			m.tab = tab(idx)
			m.blurAllInputs()
			return true, nil
		}
	}
	return false, nil
}

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
				continue
			}
			if cmd := m.startRunCmd(); cmd != nil {
				cmds = append(cmds, cmd)
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
			if hasFeed {
				m.runFeedAutoFollow = !m.runFeedAutoFollow
				if m.runFeedAutoFollow {
					m.runFeed.GotoBottom()
				}
			}
			handled = true
		}
	}

	if handled {
		return true, batchCmd(cmds)
	}
	return false, nil
}

func (m *model) handlePRDTabActions(actions []Action, msg tea.KeyMsg) (bool, tea.Cmd) {
	var cmds []tea.Cmd

	if m.tagInput.Focused() {
		handled := false
		for _, act := range actions {
			switch act {
			case ActConfirm:
				if tag := strings.TrimSpace(m.tagInput.Value()); tag != "" {
					m.tags = append(m.tags, tag)
					m.tagInput.SetValue("")
					m.tagInput.Blur()
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
		var cmd tea.Cmd
		m.tagInput, cmd = m.tagInput.Update(msg)
		return true, cmd
	}

	if len(actions) == 0 {
		var cmd tea.Cmd
		m.prdList, cmd = m.prdList.Update(msg)
		if isRuneKey(msg) || m.prdList.FilterState() == list.Filtering {
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
			}
			handled = true
		case ActSave:
			if m.selectedPRD == "" {
				m.status = "Select a PRD before saving metadata"
				handled = true
				continue
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
	return false, batchCmd(cmds)
}

func (m *model) handleSettingsTabActions(actions []Action, msg tea.KeyMsg) (bool, tea.Cmd) {
	var cmds []tea.Cmd
	handled := false

	if len(actions) == 0 {
		if m.focusedInput != "" && !isExecutorToggle(m.focusedInput) {
			if field := m.getInputField(m.focusedInput); field != nil {
				var cmd tea.Cmd
				*field, cmd = field.Update(msg)
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
		case ActSave:
			cmds = append(cmds, m.saveConfig())
			handled = true
		case ActConfirm:
			if m.focusedInput == "" {
				m.focusInput("repo")
			} else if isExecutorToggle(m.focusedInput) {
				m.cycleExecutorChoice(m.focusedInput, 1)
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
		return true, batchCmd(cmds)
	}

	if m.focusedInput != "" && !isExecutorToggle(m.focusedInput) {
		if field := m.getInputField(m.focusedInput); field != nil {
			var cmd tea.Cmd
			*field, cmd = field.Update(msg)
			return true, cmd
		}
	}

	return false, batchCmd(cmds)
}

func (m *model) handleEnvTabActions(actions []Action, msg tea.KeyMsg) (bool, tea.Cmd) {
	if len(actions) == 0 {
		return false, nil
	}

	handled := false

	for _, act := range actions {
		switch act {
		case ActCancel:
			m.focusedFlag = ""
			handled = true
		case ActNavigateUp:
			m.navigateFlags("up")
			handled = true
		case ActNavigateDown:
			m.navigateFlags("down")
			handled = true
		case ActNavigateLeft:
			if m.focusedFlag != "" {
				m.navigateFlags("left")
			}
			handled = true
		case ActNavigateRight:
			if m.focusedFlag != "" {
				m.navigateFlags("right")
			}
			handled = true
		case ActConfirm:
			if m.focusedFlag == "" {
				if len(envFlagNames) == 0 {
					break
				}
				m.focusFlag(envFlagNames[0])
			} else {
				m.toggleFocusedFlag()
			}
			handled = true
		case ActSave:
			return true, m.saveConfig()
		case ActToggleFlagLocal, ActToggleFlagPR, ActToggleFlagReview, ActToggleFlagUnsafe, ActToggleFlagDryRun, ActToggleFlagSyncGit, ActToggleFlagInfinite:
			if flag := flagNameForAction(act); flag != "" {
				m.focusFlag(flag)
				m.toggleFocusedFlag()
				handled = true
			}
		}
	}

	return handled, nil
}

func (m *model) handlePromptTabActions(actions []Action, msg tea.KeyMsg) (bool, tea.Cmd) {
	handled := false
	var cmds []tea.Cmd

	for _, act := range actions {
		switch act {
		case ActConfirm:
			if !m.prompt.Focused() {
				m.prompt.Focus()
				handled = true
			}
		case ActCancel:
			if m.prompt.Focused() {
				m.prompt.Blur()
				handled = true
			}
		case ActSave:
			cmds = append(cmds, m.saveConfig())
			handled = true
		}
	}

	if handled {
		return true, batchCmd(cmds)
	}

	var cmd tea.Cmd
	m.prompt, cmd = m.prompt.Update(msg)
	return true, cmd
}

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
		}
	}

	return handled, batchCmd(cmds)
}

func tabIndexFromAction(act Action) (int, bool) {
	switch act {
	case ActGotoTab1:
		return 0, true
	case ActGotoTab2:
		return 1, true
	case ActGotoTab3:
		return 2, true
	case ActGotoTab4:
		return 3, true
	case ActGotoTab5:
		return 4, true
	case ActGotoTab6:
		return 5, true
	default:
		return 0, false
	}
}

func flagNameForAction(act Action) string {
	switch act {
	case ActToggleFlagLocal:
		return "local"
	case ActToggleFlagPR:
		return "pr"
	case ActToggleFlagReview:
		return "review"
	case ActToggleFlagUnsafe:
		return "unsafe"
	case ActToggleFlagDryRun:
		return "dryrun"
	case ActToggleFlagSyncGit:
		return "syncgit"
	case ActToggleFlagInfinite:
		return "infinite"
	default:
		return ""
	}
}

func isRuneKey(msg tea.KeyMsg) bool {
	return msg.Type == tea.KeyRunes && len(msg.Runes) > 0
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
