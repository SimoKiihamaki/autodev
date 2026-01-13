package main

import (
	"testing"

	"github.com/SimoKiihamaki/autodev/internal/tui"
	tea "github.com/charmbracelet/bubbletea"
)

// TestMain_NewProgram verifies that program initialization completes without panicking
func TestMain_NewProgram(t *testing.T) {
	m := tui.New()

	// Verify that New() returns a usable model by checking its View output
	// A properly initialized model should produce non-empty output
	modelView := tea.Model(m).View()
	if modelView == "" {
		t.Error("New() returned a model that produces empty View output")
	}
}

// TestMain_CleanupFinalModel verifies cleanup behavior.
func TestMain_CleanupFinalModel(t *testing.T) {
	m := tui.New()
	finalModel := tea.Model(m)

	// Test that CleanupFinalModel doesn't panic
	// This is important for proper resource cleanup
	defer func() {
		if r := recover(); r != nil {
			t.Errorf("CleanupFinalModel panicked: %v", r)
		}
	}()

	tui.CleanupFinalModel(finalModel)
}

// TestMain_CleanupFinalModel_NilModel handles nil model gracefully.
func TestMain_CleanupFinalModel_NilModel(t *testing.T) {
	defer func() {
		if r := recover(); r != nil {
			t.Errorf("CleanupFinalModel panicked with nil model: %v", r)
		}
	}()

	// Should not panic even with nil input
	tui.CleanupFinalModel(nil)
}
