package tui

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/SimoKiihamaki/autodev/internal/config"
	"github.com/SimoKiihamaki/autodev/internal/runner"
)

func (m *model) prepareRunLogFile() {
	if m.logFile != nil {
		m.closeLogFile("superseded")
	}
	m.logStatus = ""
	cfgDir, err := config.EnsureDir()
	if err != nil {
		m.status = "Failed to prepare log directory: " + err.Error()
		m.logFile = nil
		m.logFilePath = ""
		m.logStatus = "unavailable: " + err.Error()
		return
	}
	logDir := filepath.Join(cfgDir, "logs")
	if err := os.MkdirAll(logDir, 0o700); err != nil {
		m.status = "Failed to create log directory: " + err.Error()
		m.logFile = nil
		m.logFilePath = ""
		m.logStatus = "unavailable: " + err.Error()
		return
	}
	if err := os.Chmod(logDir, 0o700); err != nil {
		m.status = "Failed to secure log directory: " + err.Error()
		m.logStatus = "unavailable: " + err.Error()
		m.logFile = nil
		m.logFilePath = ""
		return
	}
	name := fmt.Sprintf("run_%s.log", time.Now().Format("20060102_150405"))
	path := filepath.Join(logDir, name)
	m.logFilePath = path
	m.logStatus = abbreviatePath(path)
	// Note: File is now opened by the background log writer goroutine
	// to avoid concurrent file handle issues
}

func (m *model) writeLogHeader() {
	// Header writing is now handled by the background log writer goroutine
	// to avoid concurrent file handle issues
}

// persistLogLine is no longer needed - log persistence is handled by background goroutine

func (m *model) closeLogFile(reason string) {
	// Close the log persistence channel first to ensure background writer finishes
	closeLogChannel(&m.logPersistCh)

	// File writing is now handled by background goroutine
	// Just update the status display
	if m.logFilePath != "" {
		summary := abbreviatePath(m.logFilePath)
		if reason != "" && reason != "superseded" {
			summary = fmt.Sprintf("%s (%s)", summary, reason)
		}
		m.logStatus = summary
	}
}

func classifyLevel(line runner.Line) string {
	switch {
	case line.Err:
		return "ERROR"
	case strings.HasPrefix(line.Text, "⚠️"):
		return "WARN"
	case strings.HasPrefix(line.Text, "✓"):
		return "SUCCESS"
	default:
		return "INFO"
	}
}

// formatLogEntry formats a log line into a consistent string format for persistence
func formatLogEntry(line runner.Line) string {
	ts := line.Time
	if ts.IsZero() {
		ts = time.Now()
	}
	text := strings.TrimRight(line.Text, "\r\n")
	return fmt.Sprintf("[%s] %s: %s\n", ts.Format(time.RFC3339), classifyLevel(line), text)
}
