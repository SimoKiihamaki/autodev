package tui

import (
	"fmt"
	"os"
	"time"

	"github.com/SimoKiihamaki/autodev/internal/runner"
	tea "github.com/charmbracelet/bubbletea"
)

const (
	// criticalLogSendTimeout is the timeout for sending critical error/panic messages
	// Uses a longer timeout to ensure critical diagnostics are not dropped
	criticalLogSendTimeout = 2 * time.Second
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
func (m model) readLogsBatch() tea.Cmd {
	if m.logCh == nil {
		return nil
	}
	ch := m.logCh
	maxBatch := m.cfg.BatchProcessing.MaxBatchSize
	return func() tea.Msg {
		line, ok := <-ch
		if !ok {
			return logBatchMsg{closed: true}
		}

		lines := make([]runner.Line, 0, maxBatch)
		lines = append(lines, line)

		channelClosed := false
		// Try to read additional lines without blocking
		for len(lines) < maxBatch && !channelClosed {
			select {
			case next, ok := <-ch:
				if !ok {
					channelClosed = true
					break
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

// startLogWriter starts a background goroutine to handle log persistence
func (m model) startLogWriter() tea.Cmd {
	if m.logPersistCh == nil {
		return nil
	}
	ch := m.logPersistCh
	logFilePath := m.logFilePath
	return func() tea.Msg {
		// This runs in background and writes directly to disk
		// Open the log file independently for background writing
		logFile, err := os.OpenFile(logFilePath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o600)
		if err != nil {
			fmt.Fprintf(os.Stderr, "failed to open log file (%s): %v\n", logFilePath, err)
			return nil // If we can't open the file, skip logging
		}
		defer logFile.Close()

		for line := range ch {
			entry := formatLogEntry(line)
			if _, err := logFile.WriteString(entry); err != nil {
				fmt.Fprintf(os.Stderr, "log write error (%s): %v\n", logFilePath, err)
			}
		}
		return nil
	}
}
