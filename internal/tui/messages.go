package tui

import (
	"time"

	"github.com/SimoKiihamaki/autodev/internal/runner"
	tea "github.com/charmbracelet/bubbletea"
)

type runStartMsg struct{}
type logLineMsg struct{ line runner.Line }
type logBatchMsg struct{ lines []runner.Line }
type runErrMsg struct{ err error }
type statusMsg struct{ note string }
type runFinishMsg struct{ err error }

func (m model) readLogs() tea.Cmd {
	if m.logCh == nil {
		return nil
	}
	ch := m.logCh
	return func() tea.Msg {
		line, ok := <-ch
		if !ok {
			return nil
		}
		return logLineMsg{line: line}
	}
}

func (m model) readLogsBatch() tea.Cmd {
	if m.logCh == nil {
		return nil
	}
	ch := m.logCh
	batchConfig := m.cfg.BatchProcessing
	return func() tea.Msg {
		var lines []runner.Line

		// Read up to maxBatchSize lines or until channel is empty
		for i := 0; i < batchConfig.MaxBatchSize; i++ {
			select {
			case line, ok := <-ch:
				if !ok {
					// Channel closed
					if len(lines) > 0 {
						return logBatchMsg{lines: lines}
					}
					return nil
				}
				lines = append(lines, line)

			case <-time.After(time.Duration(batchConfig.BatchTimeoutMs) * time.Millisecond):
				// Channel is empty, return what we have
				if len(lines) > 0 {
					return logBatchMsg{lines: lines}
				}
				// No lines available, schedule another read
				return nil
			}
		}

		// Got maxBatchSize lines
		if len(lines) > 0 {
			return logBatchMsg{lines: lines}
		}
		return nil
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
