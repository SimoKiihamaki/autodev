package tui

import (
	"github.com/SimoKiihamaki/autodev/internal/runner"
	tea "github.com/charmbracelet/bubbletea"
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
		maxBatch = 25
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
