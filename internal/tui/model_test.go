package tui

import (
	"testing"

	"github.com/SimoKiihamaki/autodev/internal/config"
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

	m.cycleExecutorChoice("toggleLocal", 1)
	if m.execLocalChoice != executorClaude {
		t.Fatalf("cycle should toggle to claude, got %q", m.execLocalChoice)
	}

	m.cycleExecutorChoice("toggleLocal", 1)
	if m.execLocalChoice != executorCodex {
		t.Fatalf("cycle should wrap to codex, got %q", m.execLocalChoice)
	}

	m.cycleExecutorChoice("toggleLocal", -1)
	if m.execLocalChoice != executorClaude {
		t.Fatalf("cycle with negative direction should toggle to claude, got %q", m.execLocalChoice)
	}

	m.cycleExecutorChoice("togglePR", -1)
	if m.execPRChoice != executorClaude {
		t.Fatalf("PR toggle should handle negative direction, got %q", m.execPRChoice)
	}
}
