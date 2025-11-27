package tui

import (
	"fmt"
	"os"
	"path/filepath"
	"time"

	"github.com/SimoKiihamaki/autodev/internal/config"
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
	// Note: The log file is not opened here; only the path is prepared.
	// File writing is handled by the Python process (via --log-file argument) to avoid concurrent file handle issues.
}

func (m *model) closeLogFile(reason string) {
	// Note: Log file persistence is handled exclusively by the Python process via --log-file argument.
	// The Go runner and TUI do not write log lines to disk; they only manage the UI state and file path.
	// Just update the status display
	if m.logFilePath != "" {
		summary := abbreviatePath(m.logFilePath)
		if reason != "" && reason != "superseded" {
			summary = fmt.Sprintf("%s (%s)", summary, reason)
		}
		m.logStatus = summary
	}
}
