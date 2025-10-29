package tui

import (
	"strings"
	"testing"
	"time"

	"github.com/SimoKiihamaki/autodev/internal/config"
	"github.com/charmbracelet/bubbles/textarea"
	tea "github.com/charmbracelet/bubbletea"
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
	m := model{
		cfg:           cfg,
		defaultConfig: cfg.Clone(),
	}
	m.initSettingsInputs()
	m.initExecutorChoices()

	return m
}

func TestExecutorToggleDefaults(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name       string
		phase      config.PhaseExec
		wantLocal  executorChoice
		wantPR     executorChoice
		wantReview executorChoice
	}{
		{
			name:       "empty defaults to codex",
			phase:      config.PhaseExec{},
			wantLocal:  executorCodex,
			wantPR:     executorCodex,
			wantReview: executorCodex,
		},
		{
			name: "claude selections respected",
			phase: config.PhaseExec{
				Implement: "claude",
				Fix:       "codex",
				PR:        "claude",
				ReviewFix: "claude",
			},
			wantLocal:  executorClaude,
			wantPR:     executorClaude,
			wantReview: executorClaude,
		},
		{
			name: "case insensitive values",
			phase: config.PhaseExec{
				Implement: "CoDeX",
				Fix:       "ClAuDe",
				PR:        "",
				ReviewFix: "unknown",
			},
			wantLocal:  executorClaude,
			wantPR:     executorCodex,
			wantReview: executorCodex,
		},
	}

	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			cfg := config.Defaults()
			cfg.PhaseExecutors = tc.phase
			m := model{cfg: cfg}
			m.initExecutorChoices()
			if m.execLocalChoice != tc.wantLocal {
				t.Fatalf("local choice mismatch: got %q want %q", m.execLocalChoice, tc.wantLocal)
			}
			if m.execPRChoice != tc.wantPR {
				t.Fatalf("PR choice mismatch: got %q want %q", m.execPRChoice, tc.wantPR)
			}
			if m.execReviewChoice != tc.wantReview {
				t.Fatalf("review choice mismatch: got %q want %q", m.execReviewChoice, tc.wantReview)
			}
		})
	}
}

func TestCycleExecutorChoice(t *testing.T) {
	t.Parallel()

	m := newModelForSettingsTest()
	if m.execLocalChoice != executorCodex {
		t.Fatalf("expected initial local choice codex, got %q", m.execLocalChoice)
	}

	steps := []struct {
		name      string
		direction int
		want      executorChoice
	}{
		{
			name:      "forward toggles to claude",
			direction: 1,
			want:      executorClaude,
		},
		{
			name:      "second forward wraps to codex",
			direction: 1,
			want:      executorCodex,
		},
		{
			name:      "reverse moves back to claude",
			direction: -1,
			want:      executorClaude,
		},
	}

	for _, tc := range steps {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			m.cycleExecutorChoice("toggleLocal", tc.direction)
			if m.execLocalChoice != tc.want {
				t.Fatalf("local cycle %q: got %q want %q", tc.name, m.execLocalChoice, tc.want)
			}
		})
	}

	prModel := newModelForSettingsTest()
	prModel.cycleExecutorChoice("togglePR", -1)
	if prModel.execPRChoice != executorClaude {
		t.Fatalf("PR toggle should handle negative direction, got %q", prModel.execPRChoice)
	}
}

func TestHelpToggleViaKeybinding(t *testing.T) {
	t.Parallel()
	m := model{
		keys: DefaultKeyMap(),
		tabs: defaultTabIDs(),
	}

	msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'?'}}
	updated, _ := m.handleKeyMsg(msg)
	if !updated.showHelp {
		t.Fatalf("expected help overlay to be enabled after '?' key")
	}

	updated, _ = updated.handleKeyMsg(msg)
	if updated.showHelp {
		t.Fatalf("expected help overlay to toggle off after second '?' press")
	}

	f1 := tea.KeyMsg{Type: tea.KeyF1}
	updated, _ = updated.handleKeyMsg(f1)
	if !updated.showHelp {
		t.Fatalf("expected F1 to enable help overlay")
	}
}

func TestFlashLifecycle(t *testing.T) {
	t.Parallel()
	m := model{keys: DefaultKeyMap(), tabs: defaultTabIDs()}

	cmd := m.flash("Saved config", 5*time.Millisecond)
	if cmd == nil {
		t.Fatalf("expected flash to return command to expire toast")
	}
	if m.toast == nil {
		t.Fatalf("expected toast to be set after flash")
	}
	id := m.toast.id

	updatedModel, _ := m.Update(toastExpiredMsg{id: id})
	updated := updatedModel.(model)
	if updated.toast != nil {
		t.Fatalf("expected toast to clear after expiration message, got %+v", updated.toast)
	}
}

func TestResetToDefaultsMarksDirty(t *testing.T) {
	t.Parallel()
	defaults := config.Defaults()
	custom := defaults.Clone()
	custom.RepoPath = "/tmp/project"
	custom.Flags.AllowUnsafe = true
	custom.Flags.DryRun = true
	custom.RunPhases = config.Phases{Local: false, PR: false, ReviewFix: true}
	custom.FollowLogs = boolPtr(false)
	custom.PhaseExecutors = config.PhaseExec{
		Implement: "codex",
		Fix:       "codex",
		PR:        "codex",
		ReviewFix: "codex",
	}

	m := model{
		cfg:           custom,
		savedConfig:   custom.Clone(),
		defaultConfig: defaults,
		keys:          DefaultKeyMap(),
		tabs:          defaultTabIDs(),
	}
	m.prompt = textarea.New()
	m.tagInput = mkInput("Add tag", "", 24)
	m.initSettingsInputs()
	m.initExecutorChoices()
	m.runLocal = custom.RunPhases.Local
	m.runPR = custom.RunPhases.PR
	m.runReview = custom.RunPhases.ReviewFix
	m.followLogs = *custom.FollowLogs
	m.runFeedAutoFollow = *custom.FollowLogs
	m.flagAllowUnsafe = custom.Flags.AllowUnsafe
	m.flagDryRun = custom.Flags.DryRun
	m.flagSyncGit = custom.Flags.SyncGit
	m.flagInfinite = custom.Flags.InfiniteReviews
	snapshot, invalid := m.pendingConfigSnapshot()
	if len(invalid) > 0 {
		t.Fatalf("expected no invalid inputs before reset, got %v", invalid)
	}
	if !m.cfg.Equal(m.savedConfig) {
		t.Fatalf("expected cfg and savedConfig to match before reset")
	}
	if !snapshot.Equal(m.savedConfig) {
		t.Fatalf("expected snapshot to match saved config before reset (snapshot=%+v saved=%+v)", snapshot, m.savedConfig)
	}
	m.dirty = false

	cmd := m.resetToDefaults()
	if cmd == nil {
		t.Fatalf("expected reset to emit command for status/toast")
	}
	if !m.cfg.Equal(m.defaultConfig) {
		t.Fatalf("expected config to equal defaults after reset")
	}
	if !m.dirty {
		t.Fatalf("expected dirty flag after reset")
	}
	if got := m.inRepo.Value(); got != "" {
		t.Fatalf("expected repo input cleared, got %q", got)
	}
	if m.flagAllowUnsafe {
		t.Fatalf("expected allow unsafe to be false after reset")
	}
	if !m.followLogs {
		t.Fatalf("expected follow logs to reset to true")
	}
	if m.toast == nil || !strings.Contains(strings.ToLower(m.toast.message), "reset") {
		t.Fatalf("expected toast message to mention reset, got %+v", m.toast)
	}
	if note := strings.ToLower(m.status); !strings.Contains(note, "reset") {
		t.Fatalf("expected status to indicate reset, got %q", m.status)
	}
	if m.savedConfig.Equal(m.cfg) {
		t.Fatalf("expected savedConfig to remain unchanged after reset")
	}
}
