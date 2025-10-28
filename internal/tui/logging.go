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
	// Note: The log file is not opened here; only the path is prepared.
	// File writing is handled by the Python process (via --log-file argument) to avoid concurrent file handle issues.
}

// writeLogHeader is kept as a stub for interface compatibility.
// Header writing is now handled by the Python runner via --log-file argument
// to avoid concurrent file handle issues between Go TUI and Python process.
func (m *model) writeLogHeader() {
	// No-op: Header writing delegated to Python runner
}

// buildLogHeader constructs the log header content for persistence
func buildLogHeader(ts time.Time, selectedPRD, cfgRepoPath, cfgExecutorPolicy, cfgBranch string) []string {
	headers := []string{
		fmt.Sprintf("// autodev run started %s", ts.Format(time.RFC3339)),
		fmt.Sprintf("PRD: %s", selectedPRD),
		fmt.Sprintf("Repo: %s", cfgRepoPath),
		fmt.Sprintf("Executor policy: %s", cfgExecutorPolicy),
	}
	if cfgBranch != "" {
		headers = append(headers, fmt.Sprintf("Branch: %s", cfgBranch))
	}
	headers = append(headers, "")
	return headers
}

// persistLogLine is no longer needed - log persistence is handled by the Python runner via --log-file

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
