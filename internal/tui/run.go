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
	"github.com/SimoKiihamaki/autodev/internal/utils"
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

type numericParseError struct {
	label string
	raw   string
	err   error
}

// safeSendCritical is used for error/panic messages that must not be dropped.
// It safely sends a critical log line to the channel with timeout and panic recovery.
func safeSendCritical(logCh chan runner.Line, line runner.Line) {
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
		m.lastRunErr = errors.New(m.errMsg)
		return func() tea.Msg { return statusMsg{note: "No PRD selected"} }
	}
	if err := m.preflightChecks(); err != nil {
		m.errMsg = err.Error()
		m.lastRunErr = err
		return func() tea.Msg { return statusMsg{note: err.Error()} }
	}
	if err := config.Save(m.cfg); err != nil {
		m.lastSaveErr = err
		m.errMsg = "Failed to save config: " + err.Error()
		m.lastRunErr = err
		m.updateDirtyState()
		return func() tea.Msg { return statusMsg{note: "Config save failed"} }
	}
	m.lastSaveErr = nil
	m.lastRunErr = nil
	m.markSaved()
	m.prepareRunLogFile()

	// Channel buffers up to 2048 log lines for the TUI to bound memory usage; drops occur only when
	// the producer outpaces the consumer beyond this buffer, but every line remains in the file log written by the runner.
	m.logCh = make(chan runner.Line, 2048)

	ch := m.logCh
	m.resetLogState()
	m.resetRunDashboard()
	m.runResult = make(chan error, 1)
	m.setActiveTabByID(tabIDRun)

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

		var err error
		defer func() {
			if r := recover(); r != nil {
				panicErr := fmt.Errorf("runner panic: %v", r)
				stack := string(debug.Stack())
				msg := panicErr.Error()
				if stack != "" {
					msg = msg + "\n" + stack
				}
				safeSendCritical(logCh, runner.Line{Time: time.Now(), Text: msg, Err: true})
				err = panicErr
			}
			if err != nil && err != context.Canceled {
				safeSendCritical(logCh, runner.Line{Time: time.Now(), Text: "run error: " + err.Error(), Err: true})
			}
			select {
			case resultCh <- err:
			case <-ctx.Done():
			}
			close(resultCh)
		}()
		err = opts.Run(ctx)
	}(ctx, options, ch, m.runResult)

	return tea.Batch(func() tea.Msg { return runStartMsg{} }, m.readLogsBatch(), m.waitRunResult())
}

func (m *model) preflightChecks() error {
	cmd := strings.TrimSpace(m.cfg.PythonCommand)
	exeParts, err := shlex.Split(cmd)
	if err != nil {
		return fmt.Errorf("failed to parse Python command %q (after trimming): %w", cmd, err)
	}
	if len(exeParts) == 0 || strings.TrimSpace(exeParts[0]) == "" {
		return errors.New("python command is required (configure in Settings)")
	}
	if _, err := exec.LookPath(exeParts[0]); err != nil {
		return fmt.Errorf("python executable %q not found on PATH: %w", exeParts[0], err)
	}
	if strings.TrimSpace(m.cfg.PythonScript) == "" {
		return errors.New("set Python script path in Settings")
	}
	scriptPath := m.cfg.PythonScript
	if info, err := os.Stat(scriptPath); err != nil || info.IsDir() {
		if err != nil {
			return fmt.Errorf(
				"python script not found: %s (set the correct path in Settings or via AUTO_PRD_SCRIPT)",
				abbreviatePath(scriptPath),
			)
		}
		return fmt.Errorf(
			"python script path points to directory: %s (set the correct path in Settings or via AUTO_PRD_SCRIPT)",
			abbreviatePath(scriptPath),
		)
	}
	info, err := os.Stat(m.selectedPRD)
	if err != nil {
		return fmt.Errorf("selected PRD missing: %w", err)
	}
	if info.IsDir() {
		return fmt.Errorf("selected PRD points to a directory: %s", abbreviatePath(m.selectedPRD))
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
	if changed {
		m.updateDirtyState()
	}
	return found
}

// logParseErrors logs numeric parsing errors with consistent formatting
func logParseErrors(parseErrs []numericParseError) {
	for _, item := range parseErrs {
		log.Printf("tui: invalid %s value %q: %v", strings.ToLower(item.label), item.raw, item.err)
	}
}

func (m *model) hydrateConfigFromInputs() []string {
	invalid, parseErrs := m.populateConfigFromInputs(&m.cfg)
	logParseErrors(parseErrs)
	return invalid
}

func (m *model) populateConfigFromInputs(dst *config.Config) ([]string, []numericParseError) {
	dst.RepoPath = strings.TrimSpace(m.inRepo.Value())
	dst.BaseBranch = strings.TrimSpace(m.inBase.Value())
	dst.Branch = strings.TrimSpace(m.inBranch.Value())
	dst.CodexModel = strings.TrimSpace(m.inCodexModel.Value())
	dst.PythonCommand = strings.TrimSpace(m.inPyCmd.Value())
	dst.PythonScript = strings.TrimSpace(m.inPyScript.Value())
	dst.ExecutorPolicy = strings.TrimSpace(m.inPolicy.Value())

	const numNumericFields = 4 // Update if more numeric fields are added
	invalid := make([]string, 0, numNumericFields)
	parseErrs := make([]numericParseError, 0, numNumericFields)

	setNumeric := func(raw, label string, apply func(int)) {
		val, err := atoiSafe(raw)
		if err != nil {
			invalid = append(invalid, label)
			parseErrs = append(parseErrs, numericParseError{label: label, raw: raw, err: err})
		}
		apply(val)
	}

	setNumeric(m.inWaitMin.Value(), "Wait minutes", func(v int) {
		if v < 0 {
			v = 0
		}
		val := v
		dst.Timings.WaitMinutes = &val
	})
	setNumeric(m.inPollSec.Value(), "Review poll seconds", func(v int) {
		if v <= 0 {
			v = 15
		}
		val := v
		dst.Timings.ReviewPollSeconds = &val
	})
	setNumeric(m.inIdleMin.Value(), "Idle grace minutes", func(v int) {
		if v < 0 {
			v = 0
		}
		val := v
		dst.Timings.IdleGraceMinutes = &val
	})
	setNumeric(m.inMaxIters.Value(), "Max local iters", func(v int) {
		if v < 0 {
			v = 0
		}
		val := v
		dst.Timings.MaxLocalIters = &val
	})

	dst.Flags.AllowUnsafe = m.flagAllowUnsafe
	dst.Flags.DryRun = m.flagDryRun
	dst.Flags.SyncGit = m.flagSyncGit
	dst.Flags.InfiniteReviews = m.flagInfinite
	dst.RunPhases.Local = m.runLocal
	dst.RunPhases.PR = m.runPR
	dst.RunPhases.ReviewFix = m.runReview
	dst.FollowLogs = utils.BoolPtr(m.followLogs)
	localExec := m.execLocalChoice.configValue()
	dst.PhaseExecutors.Implement = localExec
	dst.PhaseExecutors.Fix = localExec
	dst.PhaseExecutors.PR = m.execPRChoice.configValue()
	dst.PhaseExecutors.ReviewFix = m.execReviewChoice.configValue()

	m.applyPRDMetadata(dst)

	return invalid, parseErrs
}

func (m *model) applyPRDMetadata(dst *config.Config) {
	if dst == nil || m.selectedPRD == "" {
		return
	}
	if dst.PRDs == nil {
		dst.PRDs = make(map[string]config.PRDMeta)
	}
	meta := dst.PRDs[m.selectedPRD]
	meta.Tags = normalizeTags(m.tags)
	dst.PRDs[m.selectedPRD] = meta
}

func (m *model) saveConfig() tea.Cmd {
	return func() tea.Msg {
		invalidNumeric, parseErrs := m.populateConfigFromInputs(&m.cfg)
		logParseErrors(parseErrs)
		m.normalizeLogLevel()
		err := config.Save(m.cfg)
		m.lastSaveErr = err
		if err != nil {
			m.status = "Failed to save config: " + err.Error()
			m.updateDirtyState()
		} else {
			// Update tags from saved metadata when save succeeds
			if m.selectedPRD != "" {
				if meta, ok := m.cfg.PRDs[m.selectedPRD]; ok {
					m.tags = append([]string{}, meta.Tags...)
				}
			}

			if len(invalidNumeric) > 0 {
				m.status = fmt.Sprintf("Config saved (defaults used for: %s)", strings.Join(invalidNumeric, ", "))
			} else {
				m.status = "Config saved"
			}
			if !strings.HasPrefix(m.status, "[saved]") {
				m.status = "[saved] " + m.status
			}
			if m.selectedPRD != "" {
				m.status = fmt.Sprintf("%s · %s", m.status, abbreviatePath(m.selectedPRD))
			}
			m.errMsg = ""
			m.markSaved()
		}
		return statusMsg{note: m.status}
	}
}
