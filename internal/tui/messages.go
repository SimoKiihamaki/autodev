package tui

import (
	"fmt"
	"time"

	"github.com/SimoKiihamaki/autodev/internal/runner"
	tea "github.com/charmbracelet/bubbletea"
)

// intPtrValue safely returns the value of an int pointer, treating nil as 0
func intPtrValue(p *int) int {
	if p == nil {
		return 0
	}
	return *p
}

// formatIntPtr converts an int pointer to a string, treating nil as "0"
func formatIntPtr(p *int) string {
	return fmt.Sprint(intPtrValue(p))
}

const (
	// criticalLogSendTimeout is the timeout for sending critical error/panic messages
	// Uses a longer timeout to ensure critical diagnostics are not dropped
	criticalLogSendTimeout = 2 * time.Second
)

// Message types used for Bubble Tea's Update loop.
// These messages drive state changes in the TUI:
//   - runStartMsg:     signals that a run has started
//   - logBatchMsg:     delivers a batch of log lines from the runner
//   - runErrMsg:       reports an error that occurred during run setup
//   - statusMsg:       updates the status bar text
//   - runFinishMsg:    signals that a run has completed (with optional error)
//   - toastExpiredMsg: signals that a toast notification should be dismissed
//   - prdPreviewMsg:   delivers PRD file content for preview display

type runStartMsg struct{}
type logBatchMsg struct {
	lines  []runner.Line
	closed bool
}
type runErrMsg struct{ err error }
type statusMsg struct{ note string }
type runFinishMsg struct{ err error }
type toastExpiredMsg struct{ id uint64 }
type prdPreviewMsg struct {
	path    string
	content string
	err     error
}

// trackerLoadedMsg delivers the loaded tracker (or error) to the Update loop.
type trackerLoadedMsg struct {
	tracker *Tracker
	err     error
}

// readLogsBatch attempts to read a batch of log lines from the log channel.
// Returns at least one line per batch unless the channel is already closed, in which case it returns a closed empty batch.
func (m *model) readLogsBatch() tea.Cmd {
	if m.logCh == nil {
		return nil
	}
	initialCh := m.logCh
	maxBatch := intPtrValue(m.cfg.BatchProcessing.MaxBatchSize)
	if maxBatch <= 0 {
		maxBatch = 1
	}
	return func() tea.Msg {
		// No need to check m.logCh here; only use the captured initialCh
		// If the channel was closed, this closure will simply drain initialCh
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
					break // exit the select statement and mark channel as closed
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
		// If the channel was closed, this closure will simply drain initialCh
		err, ok := <-initialCh
		if !ok {
			return nil
		}
		return runFinishMsg{err: err}
	}
}
