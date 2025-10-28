package tui

import (
	"context"
	"errors"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
)

const (
	maxLogLines = 2000
)

func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch typed := msg.(type) {
	case tea.WindowSizeMsg:
		return m.handleResize(typed), nil

	case tea.KeyMsg:
		return m.handleKeyMsg(typed)

	case tea.MouseMsg:
		return m, nil

	case prdScanMsg:
		m.prdList.SetItems(typed.items)
		m.ensureSelectedPRD(typed.items)
		return m, nil

	case statusMsg:
		if typed.note != "" {
			m.status = typed.note
		}
		return m, nil

	case runStartMsg:
		m.running = true
		m.cancelling = false
		m.errMsg = ""
		m.status = "Running…"
		m.tab = tabRun
		m.runFeedAutoFollow = true
		// Clear log buffer and logs display for new run.
		m.logBuf = nil
		m.logs.SetContent("")
		return m, nil

	case runFinishMsg:
		return m.handleRunFinish(typed)

	case logBatchMsg:
		newModel, cmd := m.handleLogBatch(typed)
		return newModel, cmd

	case runErrMsg:
		m.running = false
		m.errMsg = typed.err.Error()
		m.status = "Error."
		m.closeLogFile("failed")
		m.cancel = nil
		m.runResult = nil
		m.logCh = nil
		if m.logPersistCh != nil {
			close(m.logPersistCh)
			m.logPersistCh = nil
		}
		m.cancelling = false
		return m, nil
	}

	return m, nil
}

func (m model) handleResize(msg tea.WindowSizeMsg) model {
	w, h := msg.Width, msg.Height
	if w < 0 {
		w = 0
	}
	if h < 0 {
		h = 0
	}
	prdW, prdH := w-2, h-10
	if prdW < 0 {
		prdW = 0
	}
	if prdH < 0 {
		prdH = 0
	}
	m.prdList.SetSize(prdW, prdH)
	logW, logH := w-2, h-8
	if logW < 0 {
		logW = 0
	}
	if logH < 0 {
		logH = 0
	}
	m.logs.Width, m.logs.Height = logW, logH
	feedW, feedH := w-2, h-12
	if feedW < 0 {
		feedW = 0
	}
	if feedH < 0 {
		feedH = 0
	}
	m.runFeed.Width, m.runFeed.Height = feedW, feedH
	promptW := w - 2
	if promptW < 0 {
		promptW = 0
	}
	m.prompt.SetWidth(promptW)
	return m
}

func (m *model) handleLogBatch(msg logBatchMsg) (tea.Model, tea.Cmd) {
	if len(msg.lines) == 0 {
		if msg.closed {
			m.logCh = nil
			return m, nil
		}
		if m.logCh != nil {
			return m, m.readLogsBatch()
		}
		return m, nil
	}

	// Prepare batch arrays for run feed processing
	for _, line := range msg.lines {
		display, plain := m.formatLogLine(line)

		// Send log line to background persistence channel (non-blocking)
		select {
		case m.logPersistCh <- line:
		default:
			// Drop log lines if channel is full to prevent UI blocking
		}

		m.logBuf = append(m.logBuf, display)
		if len(m.logBuf) > maxLogLines {
			m.logBuf = m.logBuf[len(m.logBuf)-maxLogLines:]
		}
		m.handleRunFeedLine(display, plain)
	}

	// Unconditionally set content for logs tab (joining empty slice produces empty string)
	m.logs.SetContent(strings.Join(m.logBuf, "\n"))

	// Schedule another batch read if we still have a log channel
	if msg.closed {
		m.logCh = nil
		return m, nil
	}

	if m.logCh != nil {
		return m, m.readLogsBatch()
	}
	return m, nil
}

func (m model) handleRunFinish(msg runFinishMsg) (model, tea.Cmd) {
	m.running = false
	if m.cancel != nil {
		m.cancel()
	}
	m.cancel = nil
	m.runResult = nil
	m.logCh = nil
	if m.logPersistCh != nil {
		close(m.logPersistCh)
		m.logPersistCh = nil
	}
	m.cancelling = false

	logReason := "completed"
	switch {
	case msg.err == nil:
		m.errMsg = ""
		m.status = "Run finished successfully."
	case errors.Is(msg.err, context.Canceled):
		m.errMsg = ""
		m.status = "Run canceled."
		logReason = "canceled"
		// Reset log buffer, logs, and run dashboard state after cancellation to clean up state.
		m.resetLogState()
		m.resetRunDashboard()
	default:
		m.errMsg = msg.err.Error()
		m.status = "Run failed."
		logReason = "failed"
	}

	// No need to flush logs or run feed here:
	// handleLogBatch and handleRunFeedLine always flush content unconditionally,
	// so state is already up to date.

	m.closeLogFile(logReason)
	return m, nil
}
