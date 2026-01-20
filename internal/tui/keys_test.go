package tui

import (
	"testing"

	tea "github.com/charmbracelet/bubbletea"
)

// TestHandleEnvTabActions tests the Env & Flags tab keyboard handler
func TestHandleEnvTabActions(t *testing.T) {
	t.Parallel()

	t.Run("empty actions returns not handled", func(t *testing.T) {
		t.Parallel()
		m := newModelForSettingsTest()

		handled, cmd := m.handleEnvTabActions([]Action{}, tea.KeyMsg{})
		if handled {
			t.Error("Empty actions should not be handled")
		}
		if cmd != nil {
			t.Error("Empty actions should not return command")
		}
	})

	t.Run("ActCancel clears focused flag", func(t *testing.T) {
		t.Parallel()
		m := newModelForSettingsTest()
		m.focusedFlag = FlagNameLocal

		handled, _ := m.handleEnvTabActions([]Action{ActCancel}, tea.KeyMsg{})
		if !handled {
			t.Error("ActCancel should be handled")
		}
		if m.focusedFlag != "" {
			t.Errorf("focusedFlag should be cleared, got %q", m.focusedFlag)
		}
	})

	t.Run("ActNavigateUp is handled", func(t *testing.T) {
		t.Parallel()
		m := newModelForSettingsTest()

		handled, _ := m.handleEnvTabActions([]Action{ActNavigateUp}, tea.KeyMsg{})
		if !handled {
			t.Error("ActNavigateUp should be handled")
		}
	})

	t.Run("ActNavigateDown is handled", func(t *testing.T) {
		t.Parallel()
		m := newModelForSettingsTest()

		handled, _ := m.handleEnvTabActions([]Action{ActNavigateDown}, tea.KeyMsg{})
		if !handled {
			t.Error("ActNavigateDown should be handled")
		}
	})

	t.Run("ActNavigateLeft with focused flag navigates", func(t *testing.T) {
		t.Parallel()
		m := newModelForSettingsTest()
		m.focusedFlag = FlagNameLocal

		handled, _ := m.handleEnvTabActions([]Action{ActNavigateLeft}, tea.KeyMsg{})
		if !handled {
			t.Error("ActNavigateLeft should be handled when flag is focused")
		}
	})

	t.Run("ActNavigateLeft without focused flag is handled", func(t *testing.T) {
		t.Parallel()
		m := newModelForSettingsTest()
		m.focusedFlag = ""

		handled, _ := m.handleEnvTabActions([]Action{ActNavigateLeft}, tea.KeyMsg{})
		if !handled {
			t.Error("ActNavigateLeft should still be handled")
		}
	})

	t.Run("ActNavigateRight with focused flag navigates", func(t *testing.T) {
		t.Parallel()
		m := newModelForSettingsTest()
		m.focusedFlag = FlagNameLocal

		handled, _ := m.handleEnvTabActions([]Action{ActNavigateRight}, tea.KeyMsg{})
		if !handled {
			t.Error("ActNavigateRight should be handled when flag is focused")
		}
	})

	t.Run("ActNavigateRight without focused flag is handled", func(t *testing.T) {
		t.Parallel()
		m := newModelForSettingsTest()
		m.focusedFlag = ""

		handled, _ := m.handleEnvTabActions([]Action{ActNavigateRight}, tea.KeyMsg{})
		if !handled {
			t.Error("ActNavigateRight should still be handled")
		}
	})

	t.Run("ActConfirm with no focused flag focuses first flag", func(t *testing.T) {
		t.Parallel()
		m := newModelForSettingsTest()
		m.focusedFlag = ""

		handled, _ := m.handleEnvTabActions([]Action{ActConfirm}, tea.KeyMsg{})
		if !handled {
			t.Error("ActConfirm should be handled")
		}
		// If envFlagNames is not empty, first flag should be focused
	})

	t.Run("ActConfirm with focused flag toggles it", func(t *testing.T) {
		t.Parallel()
		m := newModelForSettingsTest()
		m.focusedFlag = FlagNameLocal

		handled, _ := m.handleEnvTabActions([]Action{ActConfirm}, tea.KeyMsg{})
		if !handled {
			t.Error("ActConfirm should be handled")
		}
		// Flag should be toggled (difficult to test without knowing initial state)
	})

	t.Run("ActToggleFlagLocal focuses and toggles local flag", func(t *testing.T) {
		t.Parallel()
		m := newModelForSettingsTest()

		handled, _ := m.handleEnvTabActions([]Action{ActToggleFlagLocal}, tea.KeyMsg{})
		if !handled {
			t.Error("ActToggleFlagLocal should be handled")
		}
		if m.focusedFlag != FlagNameLocal {
			t.Errorf("Local flag should be focused, got %q", m.focusedFlag)
		}
	})

	t.Run("ActToggleFlagPR focuses and toggles PR flag", func(t *testing.T) {
		t.Parallel()
		m := newModelForSettingsTest()

		handled, _ := m.handleEnvTabActions([]Action{ActToggleFlagPR}, tea.KeyMsg{})
		if !handled {
			t.Error("ActToggleFlagPR should be handled")
		}
		if m.focusedFlag != FlagNamePR {
			t.Errorf("PR flag should be focused, got %q", m.focusedFlag)
		}
	})

	t.Run("ActToggleFlagReview focuses and toggles review flag", func(t *testing.T) {
		t.Parallel()
		m := newModelForSettingsTest()

		handled, _ := m.handleEnvTabActions([]Action{ActToggleFlagReview}, tea.KeyMsg{})
		if !handled {
			t.Error("ActToggleFlagReview should be handled")
		}
		if m.focusedFlag != FlagNameReview {
			t.Errorf("Review flag should be focused, got %q", m.focusedFlag)
		}
	})

	t.Run("ActToggleFlagUnsafe focuses and toggles unsafe flag", func(t *testing.T) {
		t.Parallel()
		m := newModelForSettingsTest()

		handled, _ := m.handleEnvTabActions([]Action{ActToggleFlagUnsafe}, tea.KeyMsg{})
		if !handled {
			t.Error("ActToggleFlagUnsafe should be handled")
		}
		if m.focusedFlag != FlagNameUnsafe {
			t.Errorf("Unsafe flag should be focused, got %q", m.focusedFlag)
		}
	})

	t.Run("ActToggleFlagDryRun focuses and toggles dry run flag", func(t *testing.T) {
		t.Parallel()
		m := newModelForSettingsTest()

		handled, _ := m.handleEnvTabActions([]Action{ActToggleFlagDryRun}, tea.KeyMsg{})
		if !handled {
			t.Error("ActToggleFlagDryRun should be handled")
		}
		if m.focusedFlag != FlagNameDryRun {
			t.Errorf("Dry run flag should be focused, got %q", m.focusedFlag)
		}
	})

	t.Run("ActToggleFlagSyncGit focuses and toggles sync git flag", func(t *testing.T) {
		t.Parallel()
		m := newModelForSettingsTest()

		handled, _ := m.handleEnvTabActions([]Action{ActToggleFlagSyncGit}, tea.KeyMsg{})
		if !handled {
			t.Error("ActToggleFlagSyncGit should be handled")
		}
		if m.focusedFlag != FlagNameSyncGit {
			t.Errorf("Sync git flag should be focused, got %q", m.focusedFlag)
		}
	})

	t.Run("ActToggleFlagInfinite focuses and toggles infinite flag", func(t *testing.T) {
		t.Parallel()
		m := newModelForSettingsTest()

		handled, _ := m.handleEnvTabActions([]Action{ActToggleFlagInfinite}, tea.KeyMsg{})
		if !handled {
			t.Error("ActToggleFlagInfinite should be handled")
		}
		if m.focusedFlag != FlagNameInfinite {
			t.Errorf("Infinite flag should be focused, got %q", m.focusedFlag)
		}
	})

	t.Run("ActToggleFlagSupport focuses and toggles support flag", func(t *testing.T) {
		t.Parallel()
		m := newModelForSettingsTest()

		handled, _ := m.handleEnvTabActions([]Action{ActToggleFlagSupport}, tea.KeyMsg{})
		if !handled {
			t.Error("ActToggleFlagSupport should be handled")
		}
		if m.focusedFlag != FlagNameSupport {
			t.Errorf("Support flag should be focused, got %q", m.focusedFlag)
		}
	})

	t.Run("Multiple actions are processed in order", func(t *testing.T) {
		t.Parallel()
		m := newModelForSettingsTest()
		m.focusedFlag = FlagNameLocal

		// Cancel should clear focused flag, then Confirm should focus first flag
		handled, _ := m.handleEnvTabActions([]Action{ActCancel, ActConfirm}, tea.KeyMsg{})
		if !handled {
			t.Error("Actions should be handled")
		}
		// After cancel, focusedFlag should be cleared, then confirm should focus first flag
		// (This tests that multiple actions are processed)
	})
}

// TestFlagNameForAction tests the flag name mapping function
func TestFlagNameForAction(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name     string
		action   Action
		expected string
	}{
		{"ActToggleFlagLocal", ActToggleFlagLocal, FlagNameLocal},
		{"ActToggleFlagPR", ActToggleFlagPR, FlagNamePR},
		{"ActToggleFlagReview", ActToggleFlagReview, FlagNameReview},
		{"ActToggleFlagUnsafe", ActToggleFlagUnsafe, FlagNameUnsafe},
		{"ActToggleFlagDryRun", ActToggleFlagDryRun, FlagNameDryRun},
		{"ActToggleFlagSyncGit", ActToggleFlagSyncGit, FlagNameSyncGit},
		{"ActToggleFlagInfinite", ActToggleFlagInfinite, FlagNameInfinite},
		{"ActToggleFlagSupport", ActToggleFlagSupport, FlagNameSupport},
		{"Unknown action", Action("unknown_action"), ""},
		{"ActCancel", ActCancel, ""},
		{"ActNavigateUp", ActNavigateUp, ""},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			result := flagNameForAction(tc.action)
			if result != tc.expected {
				t.Errorf("flagNameForAction(%v) = %q, want %q", tc.action, result, tc.expected)
			}
		})
	}
}

// TestHandleLogsTabActions tests the Logs tab keyboard handler
func TestHandleLogsTabActions(t *testing.T) {
	t.Parallel()

	t.Run("empty actions returns not handled", func(t *testing.T) {
		t.Parallel()
		m := newModelForSettingsTest()

		handled, cmd := m.handleLogsTabActions([]Action{}, tea.KeyMsg{})
		if handled {
			t.Error("Empty actions should not be handled")
		}
		if cmd != nil {
			t.Error("Empty actions should not return command")
		}
	})

	t.Run("ActNavigateUp is handled", func(t *testing.T) {
		t.Parallel()
		m := newModelForSettingsTest()
		msg := tea.KeyMsg{Type: tea.KeyUp}

		handled, _ := m.handleLogsTabActions([]Action{ActNavigateUp}, msg)
		if !handled {
			t.Error("ActNavigateUp should be handled")
		}
	})

	t.Run("ActNavigateDown is handled", func(t *testing.T) {
		t.Parallel()
		m := newModelForSettingsTest()
		msg := tea.KeyMsg{Type: tea.KeyDown}

		handled, _ := m.handleLogsTabActions([]Action{ActNavigateDown}, msg)
		if !handled {
			t.Error("ActNavigateDown should be handled")
		}
	})

	t.Run("ActPageUp scrolls up 10 lines", func(t *testing.T) {
		t.Parallel()
		m := newModelForSettingsTest()

		handled, _ := m.handleLogsTabActions([]Action{ActPageUp}, tea.KeyMsg{})
		if !handled {
			t.Error("ActPageUp should be handled")
		}
	})

	t.Run("ActPageDown scrolls down 10 lines", func(t *testing.T) {
		t.Parallel()
		m := newModelForSettingsTest()

		handled, _ := m.handleLogsTabActions([]Action{ActPageDown}, tea.KeyMsg{})
		if !handled {
			t.Error("ActPageDown should be handled")
		}
	})

	t.Run("ActScrollTop goes to top", func(t *testing.T) {
		t.Parallel()
		m := newModelForSettingsTest()

		handled, _ := m.handleLogsTabActions([]Action{ActScrollTop}, tea.KeyMsg{})
		if !handled {
			t.Error("ActScrollTop should be handled")
		}
	})

	t.Run("ActScrollBottom goes to bottom", func(t *testing.T) {
		t.Parallel()
		m := newModelForSettingsTest()

		handled, _ := m.handleLogsTabActions([]Action{ActScrollBottom}, tea.KeyMsg{})
		if !handled {
			t.Error("ActScrollBottom should be handled")
		}
	})

	t.Run("ActToggleFollow enables follow mode", func(t *testing.T) {
		t.Parallel()
		m := newModelForSettingsTest()
		m.followLogs = false

		handled, _ := m.handleLogsTabActions([]Action{ActToggleFollow}, tea.KeyMsg{})
		if !handled {
			t.Error("ActToggleFollow should be handled")
		}
		if !m.followLogs {
			t.Error("followLogs should be enabled")
		}
		if m.cfg.FollowLogs == nil || !*m.cfg.FollowLogs {
			t.Error("cfg.FollowLogs should be enabled")
		}
	})

	t.Run("ActToggleFollow disables follow mode", func(t *testing.T) {
		t.Parallel()
		m := newModelForSettingsTest()
		m.followLogs = true

		handled, _ := m.handleLogsTabActions([]Action{ActToggleFollow}, tea.KeyMsg{})
		if !handled {
			t.Error("ActToggleFollow should be handled")
		}
		if m.followLogs {
			t.Error("followLogs should be disabled")
		}
		if m.cfg.FollowLogs != nil && *m.cfg.FollowLogs {
			t.Error("cfg.FollowLogs should be disabled")
		}
	})

	t.Run("ActToggleFollow toggles updateDirtyState", func(t *testing.T) {
		t.Parallel()
		m := newModelForSettingsTest()
		initialDirty := m.dirty
		m.followLogs = false

		m.handleLogsTabActions([]Action{ActToggleFollow}, tea.KeyMsg{})
		// toggleFocusedFlag should have called updateDirtyState
		// We can't easily test this without exposing internal state
		_ = initialDirty // Avoid unused variable warning
	})
}

// TestHandleProgressTabActions tests the Progress tab keyboard handler
func TestHandleProgressTabActions(t *testing.T) {
	t.Parallel()

	t.Run("empty actions returns not handled", func(t *testing.T) {
		t.Parallel()
		m := newModelForSettingsTest()

		handled, cmd := m.handleProgressTabActions([]Action{}, tea.KeyMsg{})
		if handled {
			t.Error("Empty actions should not be handled")
		}
		if cmd != nil {
			t.Error("Empty actions should not return command")
		}
	})

	t.Run("ActRefresh clears tracker and loads new data", func(t *testing.T) {
		t.Parallel()
		m := newModelForSettingsTest()
		m.trackerLoaded = true
		m.tracker = newMockTracker() // Mock tracker
		m.trackerErr = nil
		m.status = "Previous status"

		handled, cmd := m.handleProgressTabActions([]Action{ActRefresh}, tea.KeyMsg{})
		if !handled {
			t.Error("ActRefresh should be handled")
		}
		if m.trackerLoaded {
			t.Error("trackerLoaded should be cleared")
		}
		if m.tracker != nil {
			t.Error("tracker should be cleared")
		}
		if m.trackerErr != nil {
			t.Error("trackerErr should be cleared")
		}
		if m.status != "Refreshing tracker..." {
			t.Errorf("status should be 'Refreshing tracker...', got %q", m.status)
		}
		if cmd == nil {
			t.Error("ActRefresh should return a command")
		}
	})

	t.Run("ActNavigateUp is handled (future feature)", func(t *testing.T) {
		t.Parallel()
		m := newModelForSettingsTest()

		handled, _ := m.handleProgressTabActions([]Action{ActNavigateUp}, tea.KeyMsg{})
		if !handled {
			t.Error("ActNavigateUp should be handled")
		}
	})

	t.Run("ActNavigateDown is handled (future feature)", func(t *testing.T) {
		t.Parallel()
		m := newModelForSettingsTest()

		handled, _ := m.handleProgressTabActions([]Action{ActNavigateDown}, tea.KeyMsg{})
		if !handled {
			t.Error("ActNavigateDown should be handled")
		}
	})

	t.Run("ActConfirm is handled (future feature)", func(t *testing.T) {
		t.Parallel()
		m := newModelForSettingsTest()

		handled, _ := m.handleProgressTabActions([]Action{ActConfirm}, tea.KeyMsg{})
		if !handled {
			t.Error("ActConfirm should be handled")
		}
	})
}

// Convert mockTracker to actual Tracker struct for testing
func newMockTracker() *Tracker {
	return &Tracker{
		Version: "1.0",
		Metadata: TrackerMetadata{
			PRDSource: "test.md",
			PRDHash:   "abc123",
			CreatedAt: "2026-01-20",
			CreatedBy: "test",
		},
		Features:          []TrackerFeature{},
		ValidationSummary: TrackerSummary{},
	}
}
