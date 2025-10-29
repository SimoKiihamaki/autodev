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

	case toastExpiredMsg:
		if m.toast != nil && m.toast.id == typed.id {
			m.toast = nil
		}
		return m, nil

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
		// Handle quit after save if the flag is set
		if m.quitAfterSave {
			if m.lastSaveErr == nil {
				// Only clear the flag when save succeeds
				m.quitAfterSave = false
				m.cancelQuitConfirm()
				m.closeLogFile("quit")
				return m, tea.Quit
			}
			// On error, preserve quitAfterSave so user can retry saving without re-confirming quit
			m.cancelQuitConfirm()
		}
		return m, nil

	case runStartMsg:
		m.running = true
		m.cancelling = false
		m.errMsg = ""
		m.status = "Running…"
		m.lastRunErr = nil
		m.setActiveTabByID(tabIDRun)
		m.runFeedAutoFollow = m.followLogs
		// Clear log buffer and logs display for new run.
		m.resetLogState()
		cmd := m.flash("Run started", defaultToastTTL)
		return m, cmd

	case runFinishMsg:
		return m.handleRunFinish(typed)

	case logBatchMsg:
		newModel, cmd := m.handleLogBatch(typed)
		return newModel, cmd

	case runErrMsg:
		m.running = false
		m.errMsg = typed.err.Error()
		m.status = "Error."
		m.lastRunErr = typed.err
		m.closeLogFile("failed")
		m.cancel = nil
		m.runResult = nil
		m.logCh = nil
		m.cancelling = false
		note := "Run failed."
		if typed.err != nil {
			if trimmed := strings.TrimSpace(typed.err.Error()); trimmed != "" {
				note = "Run failed: " + trimmed
			}
		}
		return m, m.flash(note, defaultToastTTL)
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
	// Process any lines first, even if the channel is closed
	if len(msg.lines) > 0 {
		// Prepare batch arrays for run feed processing
		for _, line := range msg.lines {
			display, plain := m.formatLogLine(line)

			m.logBuf = append(m.logBuf, display)
			if len(m.logBuf) > maxLogLines {
				m.logBuf = m.logBuf[len(m.logBuf)-maxLogLines:]
			}
			m.handleRunFeedLine(display, plain)
		}

		// Unconditionally set content for logs tab (joining empty slice produces empty string)
		m.logs.SetContent(strings.Join(m.logBuf, "\n"))
	}

	// Handle channel closure after processing lines to ensure final batch is not lost
	if msg.closed {
		m.logCh = nil
		return m, nil
	}

	// Schedule another batch read if we still have a log channel
	if m.logCh != nil {
		return m, m.readLogsBatch()
	}

	return m, nil
}

func (m *model) handleRunFinish(msg runFinishMsg) (model, tea.Cmd) {
	m.running = false
	if m.cancel != nil {
		m.cancel()
	}
	m.cancel = nil
	m.runResult = nil
	m.logCh = nil
	m.cancelling = false

	logReason := "completed"
	switch {
	case msg.err == nil:
		m.errMsg = ""
		m.status = "Run finished successfully."
	case errors.Is(msg.err, context.Canceled):
		m.errMsg = ""
		m.status = "Run canceled."
		m.lastRunErr = nil
		logReason = "canceled"
		// Reset log buffer, logs, and run dashboard state after cancellation to clean up state.
		m.resetLogState()
		m.resetRunDashboard()
	default:
		m.errMsg = msg.err.Error()
		m.status = "Run failed."
		m.lastRunErr = msg.err
		logReason = "failed"
	}

	if msg.err == nil {
		m.lastRunErr = nil
	}

	// No need to update logs or run feed here:
	// handleLogBatch and handleRunFeedLine call SetContent on every invocation,
	// so viewport state is always current.

	m.closeLogFile(logReason)
	note := strings.TrimSpace(m.status)
	if note == "" {
		switch logReason {
		case "completed":
			note = "Run finished."
		case "canceled":
			note = "Run canceled."
		case "failed":
			note = "Run failed."
		default:
			note = "Run finished."
		}
	}
	cmd := m.flash(note, defaultToastTTL)
	return *m, cmd
}
