package tui

import (
	"context"
	"errors"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
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
		return m, nil

	case runFinishMsg:
		return m.handleRunFinish(typed)

	case logLineMsg:
		display, plain := m.formatLogLine(typed.line)
		m.persistLogLine(typed.line)
		m.logBuf = append(m.logBuf, display)
		if len(m.logBuf) > 2000 {
			m.logBuf = m.logBuf[len(m.logBuf)-2000:]
		}
		m.logs.SetContent(strings.Join(m.logBuf, "\n"))
		m.handleRunFeedLine(display, plain)
		return m, m.readLogs()

	case runErrMsg:
		m.running = false
		m.errMsg = typed.err.Error()
		m.status = "Error."
		m.closeLogFile("failed")
		m.cancel = nil
		m.runResult = nil
		m.logCh = nil
		m.cancelling = false
		return m, nil
	}

	return m, nil
}

func (m model) handleResize(msg tea.WindowSizeMsg) model {
	w, h := msg.Width, msg.Height
	m.prdList.SetSize(w-2, h-10)
	m.logs.Width, m.logs.Height = w-2, h-8
	m.runFeed.Width, m.runFeed.Height = w-2, h-12
	m.prompt.SetWidth(w - 2)
	return m
}

func (m model) handleRunFinish(msg runFinishMsg) (model, tea.Cmd) {
	m.running = false
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
		logReason = "canceled"
	default:
		m.errMsg = msg.err.Error()
		m.status = "Run failed."
		logReason = "failed"
	}

	m.closeLogFile(logReason)
	return m, nil
}
