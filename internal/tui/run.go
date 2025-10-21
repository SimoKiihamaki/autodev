package tui

import (
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"strings"
	"time"

	"github.com/SimoKiihamaki/autodev/internal/config"
	"github.com/SimoKiihamaki/autodev/internal/runner"
	tea "github.com/charmbracelet/bubbletea"
)

func (m *model) normalizeLogLevel() {
	lvl := strings.TrimSpace(m.cfg.LogLevel)
	if lvl == "" {
		m.cfg.LogLevel = "INFO"
		return
	}
	m.cfg.LogLevel = strings.ToUpper(lvl)
}

func (m model) isActiveOrCancelling() bool {
	return m.running || m.cancelling
}

func (m *model) startRunCmd() tea.Cmd {
	m.hydrateConfigFromInputs()
	m.resolvePythonScript(false)
	m.normalizeLogLevel()
	m.cancelling = false

	if m.selectedPRD == "" {
		m.errMsg = "Select a PRD first (PRD tab)"
		return func() tea.Msg { return statusMsg{note: "No PRD selected"} }
	}
	if err := m.preflightChecks(); err != nil {
		m.errMsg = err.Error()
		return func() tea.Msg { return statusMsg{note: err.Error()} }
	}
	if err := config.Save(m.cfg); err != nil {
		m.errMsg = "Failed to save config: " + err.Error()
		return func() tea.Msg { return statusMsg{note: "Config save failed"} }
	}
	m.prepareRunLogFile()

	m.logCh = make(chan runner.Line, 2048)
	ch := m.logCh
	m.logBuf = nil
	m.logs.SetContent("")
	m.resetRunDashboard()
	m.runResult = make(chan error, 1)
	m.tab = tabRun

	ctx, cancel := context.WithCancel(context.Background())
	m.cancel = cancel

	go func(logCh chan runner.Line, resultCh chan error) {
		o := runner.Options{
			Config:        m.cfg,
			PRDPath:       m.selectedPRD,
			InitialPrompt: m.prompt.Value(),
			Logs:          logCh,
			LogFilePath:   m.logFilePath,
			LogLevel:      m.cfg.LogLevel,
		}
		err := o.Run(ctx)
		if err != nil && err != context.Canceled {
			select {
			case logCh <- runner.Line{Time: time.Now(), Text: "run error: " + err.Error(), Err: true}:
			default:
			}
		}
		select {
		case resultCh <- err:
		default:
		}
		close(resultCh)
	}(ch, m.runResult)

	return tea.Batch(func() tea.Msg { return runStartMsg{} }, m.readLogs(), m.waitRunResult())
}

func (m *model) preflightChecks() error {
	if strings.TrimSpace(m.cfg.PythonCommand) == "" {
		return errors.New("Set Python command in Settings")
	}
	if _, err := exec.LookPath(m.cfg.PythonCommand); err != nil {
		return fmt.Errorf("Python command not found on PATH: %w", err)
	}
	if strings.TrimSpace(m.cfg.PythonScript) == "" {
		return errors.New("Set Python script path in Settings")
	}
	scriptPath := m.cfg.PythonScript
	if info, err := os.Stat(scriptPath); err != nil || info.IsDir() {
		if err != nil {
			return fmt.Errorf(
				"Python script not found: %s. Set the correct path in Settings or via AUTO_PRD_SCRIPT.",
				abbreviatePath(scriptPath),
			)
		}
		return fmt.Errorf(
			"Python script path points to directory: %s. Set the correct path in Settings or via AUTO_PRD_SCRIPT.",
			abbreviatePath(scriptPath),
		)
	}
	if _, err := os.Stat(m.selectedPRD); err != nil {
		return fmt.Errorf("Selected PRD missing: %w", err)
	}
	return nil
}

func (m *model) resolvePythonScript(initial bool) bool {
	resolved, reason, changed, found := detectPythonScript(m.cfg.PythonScript, m.cfg.RepoPath)
	if resolved != "" && !pathsEqual(resolved, m.cfg.PythonScript) {
		m.cfg.PythonScript = resolved
		m.inPyScript.SetValue(resolved)
	}
	if changed && reason != "" {
		note := fmt.Sprintf("Resolved Python script (%s): %s", reason, abbreviatePath(resolved))
		if initial {
			if m.status == "" {
				m.status = note
			}
		} else {
			m.status = note
		}
	}
	return found
}

func (m *model) hydrateConfigFromInputs() {
	m.cfg.RepoPath = strings.TrimSpace(m.inRepo.Value())
	m.cfg.BaseBranch = strings.TrimSpace(m.inBase.Value())
	m.cfg.Branch = strings.TrimSpace(m.inBranch.Value())
	m.cfg.CodexModel = strings.TrimSpace(m.inCodexModel.Value())
	m.cfg.PythonCommand = strings.TrimSpace(m.inPyCmd.Value())
	m.cfg.PythonScript = strings.TrimSpace(m.inPyScript.Value())
	m.cfg.ExecutorPolicy = strings.TrimSpace(m.inPolicy.Value())
	m.cfg.Timings.WaitMinutes = atoiSafe(m.inWaitMin.Value())
	m.cfg.Timings.ReviewPollSeconds = atoiSafe(m.inPollSec.Value())
	m.cfg.Timings.IdleGraceMinutes = atoiSafe(m.inIdleMin.Value())
	m.cfg.Timings.MaxLocalIters = atoiSafe(m.inMaxIters.Value())
	m.cfg.Flags.AllowUnsafe = m.flagAllowUnsafe
	m.cfg.Flags.DryRun = m.flagDryRun
	m.cfg.Flags.SyncGit = m.flagSyncGit
	m.cfg.Flags.InfiniteReviews = m.flagInfinite
	m.cfg.RunPhases.Local = m.runLocal
	m.cfg.RunPhases.PR = m.runPR
	m.cfg.RunPhases.ReviewFix = m.runReview
}

func (m *model) saveConfig() tea.Cmd {
	m.hydrateConfigFromInputs()
	m.normalizeLogLevel()
	if err := config.Save(m.cfg); err != nil {
		m.status = "Failed to save config: " + err.Error()
	} else {
		m.status = "Config saved"
	}
	return func() tea.Msg { return statusMsg{note: m.status} }
}
