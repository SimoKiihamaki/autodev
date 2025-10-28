package tui

import (
	"context"
	"errors"
	"fmt"
	"log"
	"os"
	"os/exec"
	"runtime/debug"
	"strings"
	"time"

	"github.com/SimoKiihamaki/autodev/internal/config"
	"github.com/SimoKiihamaki/autodev/internal/runner"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/google/shlex"
)

var (
	validLogLevels = map[string]struct{}{
		"DEBUG":    {},
		"INFO":     {},
		"WARNING":  {},
		"ERROR":    {},
		"CRITICAL": {},
	}
	logLevelAliases = map[string]string{
		"WARN":  "WARNING",
		"TRACE": "DEBUG",
	}
)

func (m *model) normalizeLogLevel() {
	lvl := strings.TrimSpace(m.cfg.LogLevel)
	if lvl == "" {
		m.cfg.LogLevel = "INFO"
		return
	}
	upper := strings.ToUpper(lvl)
	if mapped, ok := logLevelAliases[upper]; ok {
		upper = mapped
	}
	if _, ok := validLogLevels[upper]; ok {
		m.cfg.LogLevel = upper
		return
	}
	m.cfg.LogLevel = "INFO"
}

func (m model) isActiveOrCancelling() bool {
	return m.running || m.cancelling
}

func (m *model) startRunCmd() tea.Cmd {
	if m.isActiveOrCancelling() {
		note := "Run already in progress; wait or cancel before starting a new one"
		m.errMsg = note
		return func() tea.Msg { return statusMsg{note: note} }
	}
	invalidNumeric := m.hydrateConfigFromInputs()
	if len(invalidNumeric) > 0 {
		note := fmt.Sprintf("Reset invalid numeric settings: %s", strings.Join(invalidNumeric, ", "))
		m.status = note
	}
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

	// Channel buffers up to 2048 log lines for the TUI to bound memory usage; drops occur only when
	// the producer outpaces the consumer beyond this buffer, but every line remains in the file log written by the runner.
	m.logCh = make(chan runner.Line, 2048)

	// Recreate log persistence channel for background writing
	if m.logPersistCh != nil {
		close(m.logPersistCh)
	}
	m.logPersistCh = make(chan runner.Line, 100) // Buffered to prevent UI blocking
	ch := m.logCh
	m.resetLogState()
	m.resetRunDashboard()
	m.runResult = make(chan error, 1)
	m.tab = tabRun

	ctx, cancel := context.WithCancel(context.Background())
	m.cancel = cancel

	options := runner.Options{
		Config:        m.cfg,
		PRDPath:       m.selectedPRD,
		InitialPrompt: m.prompt.Value(),
		Logs:          ch,
		LogFilePath:   m.logFilePath,
		LogLevel:      m.cfg.LogLevel,
	}

	go func(ctx context.Context, opts runner.Options, logCh chan runner.Line, resultCh chan error) {
		// safeSendCritical is used for error/panic messages that must not be dropped
		safeSendCritical := func(line runner.Line) {
			defer func() {
				if r := recover(); r != nil {
					// Defensive: catch all panics, including send-on-closed-channel, to prevent process crash
					log.Printf("tui: safeSendCritical recovered from panic: %v", r)
				}
			}()
			select {
			case logCh <- line:
			case <-time.After(criticalLogSendTimeout):
				// Critical messages should never be dropped, but we need a timeout to prevent blocking forever
				// Use a much longer timeout for critical diagnostics
				log.Printf("tui: dropped CRITICAL log line after %v timeout (UI consumer extremely slow)", criticalLogSendTimeout)
			}
		}

		var err error
		defer func() {
			if r := recover(); r != nil {
				panicErr := fmt.Errorf("runner panic: %v", r)
				stack := string(debug.Stack())
				msg := panicErr.Error()
				if stack != "" {
					msg = msg + "\n" + stack
				}
				safeSendCritical(runner.Line{Time: time.Now(), Text: msg, Err: true})
				err = panicErr
			}
			if err != nil && err != context.Canceled {
				safeSendCritical(runner.Line{Time: time.Now(), Text: "run error: " + err.Error(), Err: true})
			}
			select {
			case resultCh <- err:
			case <-ctx.Done():
			}
			close(resultCh)
		}()
		err = opts.Run(ctx)
	}(ctx, options, ch, m.runResult)

	return tea.Batch(func() tea.Msg { return runStartMsg{} }, m.readLogsBatch(), m.startLogWriter(), m.waitRunResult())
}

func (m *model) preflightChecks() error {
	cmd := strings.TrimSpace(m.cfg.PythonCommand)
	exeParts, err := shlex.Split(cmd)
	if err != nil {
		return fmt.Errorf("failed to parse Python command %q (after trimming): %w", cmd, err)
	}
	if len(exeParts) == 0 || strings.TrimSpace(exeParts[0]) == "" {
		return errors.New("Python command is required (configure in Settings)")
	}
	if _, err := exec.LookPath(exeParts[0]); err != nil {
		return fmt.Errorf("python executable %q not found on PATH: %w", exeParts[0], err)
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
	info, err := os.Stat(m.selectedPRD)
	if err != nil {
		return fmt.Errorf("Selected PRD missing: %w", err)
	}
	if info.IsDir() {
		return fmt.Errorf("Selected PRD points to a directory: %s", abbreviatePath(m.selectedPRD))
	}
	if !strings.HasSuffix(strings.ToLower(m.selectedPRD), ".md") {
		log.Printf("tui: selected PRD without .md extension: %s", abbreviatePath(m.selectedPRD))
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

func (m *model) hydrateConfigFromInputs() []string {
	m.cfg.RepoPath = strings.TrimSpace(m.inRepo.Value())
	m.cfg.BaseBranch = strings.TrimSpace(m.inBase.Value())
	m.cfg.Branch = strings.TrimSpace(m.inBranch.Value())
	m.cfg.CodexModel = strings.TrimSpace(m.inCodexModel.Value())
	m.cfg.PythonCommand = strings.TrimSpace(m.inPyCmd.Value())
	m.cfg.PythonScript = strings.TrimSpace(m.inPyScript.Value())
	m.cfg.ExecutorPolicy = strings.TrimSpace(m.inPolicy.Value())

	invalid := make([]string, 0, 4)
	setNumeric := func(raw, label string, apply func(int)) {
		val, err := atoiSafe(raw)
		if err != nil {
			invalid = append(invalid, label)
			log.Printf("tui: invalid %s value %q: %v", strings.ToLower(label), raw, err)
		}
		apply(val)
	}

	setNumeric(m.inWaitMin.Value(), "Wait minutes", func(v int) {
		if v < 0 {
			v = 0
		}
		m.cfg.Timings.WaitMinutes = v
	})
	setNumeric(m.inPollSec.Value(), "Review poll seconds", func(v int) {
		if v <= 0 {
			v = 15
		}
		m.cfg.Timings.ReviewPollSeconds = v
	})
	setNumeric(m.inIdleMin.Value(), "Idle grace minutes", func(v int) {
		if v < 0 {
			v = 0
		}
		m.cfg.Timings.IdleGraceMinutes = v
	})
	setNumeric(m.inMaxIters.Value(), "Max local iters", func(v int) {
		if v < 0 {
			v = 0
		}
		m.cfg.Timings.MaxLocalIters = v
	})
	m.cfg.Flags.AllowUnsafe = m.flagAllowUnsafe
	m.cfg.Flags.DryRun = m.flagDryRun
	m.cfg.Flags.SyncGit = m.flagSyncGit
	m.cfg.Flags.InfiniteReviews = m.flagInfinite
	m.cfg.RunPhases.Local = m.runLocal
	m.cfg.RunPhases.PR = m.runPR
	m.cfg.RunPhases.ReviewFix = m.runReview
	localExec := m.execLocalChoice.configValue()
	m.cfg.PhaseExecutors.Implement = localExec
	m.cfg.PhaseExecutors.Fix = localExec
	m.cfg.PhaseExecutors.PR = m.execPRChoice.configValue()
	m.cfg.PhaseExecutors.ReviewFix = m.execReviewChoice.configValue()

	return invalid
}

func (m *model) saveConfig() tea.Cmd {
	invalidNumeric := m.hydrateConfigFromInputs()
	m.normalizeLogLevel()
	if err := config.Save(m.cfg); err != nil {
		m.status = "Failed to save config: " + err.Error()
	} else {
		if len(invalidNumeric) > 0 {
			m.status = fmt.Sprintf("Config saved (defaults used for: %s)", strings.Join(invalidNumeric, ", "))
		} else {
			m.status = "Config saved"
		}
	}
	return func() tea.Msg { return statusMsg{note: m.status} }
}
