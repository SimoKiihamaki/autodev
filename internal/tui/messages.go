package tui

import (
	"time"

	"github.com/SimoKiihamaki/autodev/internal/runner"
	tea "github.com/charmbracelet/bubbletea"
)

const (
	// defaultMaxBatchSize is the default number of log lines to batch together
	defaultMaxBatchSize = 25

	// logSendTimeout is the timeout for sending log lines to the UI channel
	logSendTimeout = 100 * time.Millisecond
)

type runStartMsg struct{}
type logBatchMsg struct {
	lines  []runner.Line
	closed bool
}
type runErrMsg struct{ err error }
type statusMsg struct{ note string }
type runFinishMsg struct{ err error }

func (m model) readLogsBatch() tea.Cmd {
	if m.logCh == nil {
		return nil
	}
	ch := m.logCh
	maxBatch := m.cfg.BatchProcessing.MaxBatchSize
	if maxBatch <= 0 {
		maxBatch = defaultMaxBatchSize
	}
	return func() tea.Msg {
		line, ok := <-ch
		if !ok {
			return logBatchMsg{closed: true}
		}

		lines := make([]runner.Line, 0, maxBatch)
		lines = append(lines, line)

		for len(lines) < maxBatch {
			select {
			case next, ok := <-ch:
				if !ok {
					return logBatchMsg{lines: lines, closed: true}
				}
				lines = append(lines, next)
			default:
				return logBatchMsg{lines: lines, closed: false}
			}
		}

		return logBatchMsg{lines: lines, closed: false}
	}
}

func (m model) waitRunResult() tea.Cmd {
	if m.runResult == nil {
		return nil
	}
	ch := m.runResult
	return func() tea.Msg {
		err, ok := <-ch
		if !ok {
			return nil
		}
		return runFinishMsg{err: err}
	}
}
