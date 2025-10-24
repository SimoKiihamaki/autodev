package tui

import (
	"fmt"
	"testing"

	"github.com/SimoKiihamaki/autodev/internal/config"
	"github.com/charmbracelet/bubbles/textinput"
)

func TestSettingsInputNamesAreSynchronized(t *testing.T) {
	t.Parallel()
	m := newModelForSettingsTest()
	nameSet := make(map[string]struct{}, len(settingsInputNames))
	for _, name := range settingsInputNames {
		if name == "" {
			t.Fatalf("settingsInputNames contains empty entry")
		}
		if _, exists := nameSet[name]; exists {
			t.Fatalf("settingsInputNames contains duplicate entry %q", name)
		}
		nameSet[name] = struct{}{}
	}

	for key := range m.settingsInputs {
		if _, ok := nameSet[key]; !ok {
			t.Errorf("settingsInputs includes unexpected key %q", key)
		}
	}

	for _, name := range settingsInputNames {
		if _, exists := m.settingsInputs[name]; !exists {
			t.Errorf("settingsInputNames entry %q missing from settingsInputs", name)
		}
	}

	if len(m.settingsInputs) != len(settingsInputNames) {
		t.Fatalf("settingsInputs has %d entries; expected %d", len(m.settingsInputs), len(settingsInputNames))
	}
}

func newModelForSettingsTest() model {
	cfg := config.Defaults()
	m := model{cfg: cfg}

	m.inRepo = mkInput("Repo path", cfg.RepoPath, 60)
	m.inBase = mkInput("Base branch", cfg.BaseBranch, 20)
	m.inBranch = mkInput("Feature branch (optional)", cfg.Branch, 30)
	m.inCodexModel = mkInput("Codex model", cfg.CodexModel, 24)
	m.inPyCmd = mkInput("Python command", cfg.PythonCommand, 20)
	m.inPyScript = mkInput("Python script path", cfg.PythonScript, 80)
	m.inPolicy = mkInput("Executor policy (codex-first|codex-only|claude-only)", cfg.ExecutorPolicy, 28)
	m.inExecImpl = mkInput("Exec (implement): codex|claude|<empty>", cfg.PhaseExecutors.Implement, 16)
	m.inExecFix = mkInput("Exec (fix): codex|claude|<empty>", cfg.PhaseExecutors.Fix, 16)
	m.inExecPR = mkInput("Exec (pr): codex|claude|<empty>", cfg.PhaseExecutors.PR, 16)
	m.inExecRev = mkInput("Exec (review_fix): codex|claude|<empty>", cfg.PhaseExecutors.ReviewFix, 22)
	m.inWaitMin = mkInput("Wait minutes", fmt.Sprint(cfg.Timings.WaitMinutes), 6)
	m.inPollSec = mkInput("Review poll seconds", fmt.Sprint(cfg.Timings.ReviewPollSeconds), 6)
	m.inIdleMin = mkInput("Idle grace minutes", fmt.Sprint(cfg.Timings.IdleGraceMinutes), 6)
	m.inMaxIters = mkInput("Max local iters", fmt.Sprint(cfg.Timings.MaxLocalIters), 6)

	m.settingsInputs = map[string]*textinput.Model{
		"repo":     &m.inRepo,
		"base":     &m.inBase,
		"branch":   &m.inBranch,
		"codex":    &m.inCodexModel,
		"pycmd":    &m.inPyCmd,
		"pyscript": &m.inPyScript,
		"policy":   &m.inPolicy,
		"execimpl": &m.inExecImpl,
		"execfix":  &m.inExecFix,
		"execpr":   &m.inExecPR,
		"execrev":  &m.inExecRev,
		"waitmin":  &m.inWaitMin,
		"pollsec":  &m.inPollSec,
		"idlemin":  &m.inIdleMin,
		"maxiters": &m.inMaxIters,
	}

	return m
}
