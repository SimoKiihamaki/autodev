package tui

import (
	"time"

	"github.com/SimoKiihamaki/autodev/internal/runner"
	tea "github.com/charmbracelet/bubbletea"
)

const (
	// criticalLogSendTimeout is the timeout for sending critical error/panic messages
	// Uses a longer timeout to ensure critical diagnostics are not dropped
	criticalLogSendTimeout = 2 * time.Second

	// logPersistBufferSize is the buffer size for the log persistence channel
	// This buffer prevents UI blocking when log writing is slow
	logPersistBufferSize = 100
)

type runStartMsg struct{}
type logBatchMsg struct {
	lines  []runner.Line
	closed bool
}
type runErrMsg struct{ err error }
type statusMsg struct{ note string }
type runFinishMsg struct{ err error }

// readLogsBatch attempts to read a batch of log lines from the log channel.
// Returns at least one line per batch unless the channel is already closed, in which case it returns a closed empty batch.
func (m *model) readLogsBatch() tea.Cmd {
	if m.logCh == nil {
		return nil
	}
	initialCh := m.logCh
	maxBatch := m.cfg.BatchProcessing.MaxBatchSize
	if maxBatch <= 0 {
		maxBatch = 1
	}
	return func() tea.Msg {
		// No need to check m.logCh here; only use the captured initialCh
		// If the channel was closed or swapped, this closure will simply drain initialCh
		line, ok := <-initialCh
		if !ok {
			return logBatchMsg{closed: true}
		}

		lines := make([]runner.Line, 0, maxBatch)
		lines = append(lines, line)

		channelClosed := false
		// Try to read additional lines without blocking
		for len(lines) < maxBatch && !channelClosed {
			select {
			case next, ok := <-initialCh:
				if !ok {
					channelClosed = true
					break // exit the loop immediately when the channel is closed
				}
				lines = append(lines, next)
			default:
				// No more lines immediately available
				return logBatchMsg{lines: lines, closed: false}
			}
		}

		return logBatchMsg{lines: lines, closed: channelClosed}
	}
}

func (m *model) waitRunResult() tea.Cmd {
	if m.runResult == nil {
		return nil
	}
	initialCh := m.runResult
	return func() tea.Msg {
		// No need to check m.runResult here; only use the captured initialCh
		// If the channel was closed or swapped, this closure will simply drain initialCh
		err, ok := <-initialCh
		if !ok {
			return nil
		}
		return runFinishMsg{err: err}
	}
}

// startLogWriter starts a background goroutine to drain the log persistence channel.
// The Python runner is responsible for writing logs to disk (via --log-file).
// This goroutine simply drains the channel to prevent blocking or resource leaks.
func (m model) startLogWriter() tea.Cmd {
	if m.logPersistCh == nil {
		return nil
	}
	ch := m.logPersistCh
	return func() tea.Msg {
		// Drain the log persistence channel; no log writing is performed here.
		for range ch {
			// No-op: log lines are already persisted by the runner.
		}
		return nil
	}
}
