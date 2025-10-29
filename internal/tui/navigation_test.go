package tui

import (
	"testing"

	tea "github.com/charmbracelet/bubbletea"
)

func TestNavigationWrapping(t *testing.T) {
	t.Parallel()

	tcs := []struct {
		name      string
		setup     func(*model)
		action    func(*testing.T, *model)
		wantFocus string
		focusKind string
	}{
		{
			name: "settings wrap down",
			setup: func(m *model) {
				m.focusInput("maxiters")
			},
			action: func(_ *testing.T, m *model) {
				m.navigateSettings("down")
			},
			wantFocus: "repo",
			focusKind: "input",
		},
		{
			name: "settings wrap up",
			setup: func(m *model) {
				m.focusInput("repo")
			},
			action: func(_ *testing.T, m *model) {
				m.navigateSettings("up")
			},
			wantFocus: "waitmin",
			focusKind: "input",
		},
		{
			name: "settings confirm advances focus",
			setup: func(m *model) {
				m.focusInput("repo")
			},
			action: func(t *testing.T, m *model) {
				if handled, _ := m.handleSettingsTabActions([]Action{ActConfirm}, tea.KeyMsg{}); !handled {
					t.Fatal("expected confirm action to be handled")
				}
			},
			wantFocus: "base",
			focusKind: "input",
		},
		{
			name: "settings confirm wraps to repo",
			setup: func(m *model) {
				m.focusInput("maxiters")
			},
			action: func(t *testing.T, m *model) {
				if handled, _ := m.handleSettingsTabActions([]Action{ActConfirm}, tea.KeyMsg{}); !handled {
					t.Fatal("expected confirm action to be handled when wrapping")
				}
			},
			wantFocus: "repo",
			focusKind: "input",
		},
		{
			name: "flags wrap up",
			setup: func(m *model) {
				m.focusFlag("local")
			},
			action: func(_ *testing.T, m *model) {
				m.navigateFlags("up")
			},
			wantFocus: "infinite",
			focusKind: "flag",
		},
		{
			name: "flags wrap down",
			setup: func(m *model) {
				m.focusFlag("infinite")
			},
			action: func(_ *testing.T, m *model) {
				m.navigateFlags("down")
			},
			wantFocus: "local",
			focusKind: "flag",
		},
	}

	for _, tc := range tcs {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			m := newModelForSettingsTest()
			if tc.setup != nil {
				tc.setup(&m)
			}
			if tc.action != nil {
				tc.action(t, &m)
			}

			var got string
			switch tc.focusKind {
			case "input":
				got = m.focusedInput
			case "flag":
				got = m.focusedFlag
			default:
				t.Fatalf("unknown focus kind %q", tc.focusKind)
			}

			if got != tc.wantFocus {
				t.Fatalf("expected focus on %q, got %q", tc.wantFocus, got)
			}
		})
	}
}
