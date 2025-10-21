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
	if err := os.MkdirAll(logDir, 0o755); err != nil {
		m.status = "Failed to create log directory: " + err.Error()
		m.logFile = nil
		m.logFilePath = ""
		m.logStatus = "unavailable: " + err.Error()
		return
	}
	name := fmt.Sprintf("run_%s.log", time.Now().Format("20060102_150405"))
	path := filepath.Join(logDir, name)
	f, err := os.OpenFile(path, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644)
	if err != nil {
		m.status = "Failed to open log file: " + err.Error()
		m.logFile = nil
		m.logFilePath = ""
		m.logStatus = "unavailable: " + err.Error()
		return
	}
	m.logFile = f
	m.logFilePath = path
	m.logStatus = abbreviatePath(path)
	m.writeLogHeader()
}

func (m *model) writeLogHeader() {
	if m.logFile == nil {
		return
	}
	ts := time.Now().Format(time.RFC3339)
	headers := []string{
		fmt.Sprintf("# autodev run started %s", ts),
		fmt.Sprintf("PRD: %s", m.selectedPRD),
		fmt.Sprintf("Repo: %s", m.cfg.RepoPath),
		fmt.Sprintf("Executor policy: %s", m.cfg.ExecutorPolicy),
	}
	if m.cfg.Branch != "" {
		headers = append(headers, fmt.Sprintf("Branch: %s", m.cfg.Branch))
	}
	headers = append(headers, "")
	if _, err := m.logFile.WriteString(strings.Join(headers, "\n") + "\n"); err != nil {
		m.status = "Failed to write log header: " + err.Error()
		m.logStatus = "unavailable: " + err.Error()
		m.closeLogFile("header error")
	}
}

func (m *model) persistLogLine(line runner.Line) {
	if m.logFile == nil {
		return
	}
	ts := line.Time
	if ts.IsZero() {
		ts = time.Now()
	}
	text := strings.TrimRight(line.Text, "\r\n")
	entry := fmt.Sprintf("[%s] %s: %s\n", ts.Format(time.RFC3339), classifyLevel(line), text)
	if _, err := m.logFile.WriteString(entry); err != nil {
		m.status = "Failed to write log file: " + err.Error()
		m.closeLogFile("write error")
	}
}

func (m *model) closeLogFile(reason string) {
	if m.logFile == nil {
		return
	}
	if reason != "" {
		_, _ = m.logFile.WriteString(fmt.Sprintf("# run %s at %s\n", reason, time.Now().Format(time.RFC3339)))
	}
	_ = m.logFile.Close()
	m.logFile = nil
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
