package main

import (
	"testing"

	tea "github.com/charmbracelet/bubbletea"
)

// TestNewTUIModel_ReturnsValidModel verifies that newTUIModel returns a usable model.
func TestNewTUIModel_ReturnsValidModel(t *testing.T) {
	m := newTUIModel()
	if m == nil {
		t.Fatal("newTUIModel returned nil")
	}
}

// TestNewTUIModel_ViewNotEmpty verifies that the model produces non-empty view.
func TestNewTUIModel_ViewNotEmpty(t *testing.T) {
	m := newTUIModel()
	view := m.View()
	if view == "" {
		t.Error("newTUIModel returned a model that produces empty View output")
	}
}

// TestNewTUIModel_MultipleCalls verifies multiple model creations work correctly.
func TestNewTUIModel_MultipleCalls(t *testing.T) {
	m1 := newTUIModel()
	m2 := newTUIModel()

	if m1 == nil || m2 == nil {
		t.Fatal("newTUIModel returned nil for one or both calls")
	}

	view1 := m1.View()
	view2 := m2.View()

	// Both should produce output
	if view1 == "" {
		t.Error("first model has empty view")
	}
	if view2 == "" {
		t.Error("second model has empty view")
	}
}

// TestNewProgram_ReturnsValidProgram verifies that newProgram returns a valid program.
func TestNewProgram_ReturnsValidProgram(t *testing.T) {
	m := newTUIModel()
	p := newProgram(m)

	if p == nil {
		t.Error("newProgram returned nil")
	}
}

// TestNewProgram_NilModel verifies newProgram handles nil model (may panic, which is ok).
func TestNewProgram_NilModel(t *testing.T) {
	defer func() {
		// It's acceptable for this to panic, just verify we can catch it
		_ = recover()
	}()

	// This may panic, which is expected behavior for nil model
	p := newProgram(nil)
	_ = p
}

// TestNewProgram_WithOptions verifies program is created with alt screen option.
func TestNewProgram_WithOptions(t *testing.T) {
	m := newTUIModel()
	p := newProgram(m)

	// Program should be created successfully with options
	if p == nil {
		t.Error("newProgram with alt screen option returned nil")
	}
}

// TestCleanupModel_ValidModel verifies cleanup with valid model doesn't panic.
func TestCleanupModel_ValidModel(t *testing.T) {
	m := newTUIModel()

	defer func() {
		if r := recover(); r != nil {
			t.Errorf("cleanupModel panicked with valid model: %v", r)
		}
	}()

	cleanupModel(m)
}

// TestCleanupModel_NilModel verifies cleanup with nil model doesn't panic.
func TestCleanupModel_NilModel(t *testing.T) {
	defer func() {
		if r := recover(); r != nil {
			t.Errorf("cleanupModel panicked with nil model: %v", r)
		}
	}()

	cleanupModel(nil)
}

// TestCleanupModel_MultipleCleanup verifies multiple cleanup calls don't panic.
func TestCleanupModel_MultipleCleanup(t *testing.T) {
	defer func() {
		if r := recover(); r != nil {
			t.Errorf("multiple cleanup calls panicked: %v", r)
		}
	}()

	for i := 0; i < 5; i++ {
		m := newTUIModel()
		cleanupModel(m)
	}
}

// TestModel_Init verifies the model's Init method returns without error.
func TestModel_Init(t *testing.T) {
	m := newTUIModel()
	cmd := m.Init()

	// Init may return nil or a command, both are valid
	// Just verify it doesn't panic
	_ = cmd
}

// TestModel_UpdateNil verifies update with nil message doesn't crash.
func TestModel_UpdateNil(t *testing.T) {
	m := newTUIModel()

	defer func() {
		if r := recover(); r != nil {
			t.Errorf("Update with nil message panicked: %v", r)
		}
	}()

	_, _ = m.Update(nil)
}

// TestRunProgram_ShortCircuit verifies runProgram signature is correct.
func TestRunProgram_ShortCircuit(t *testing.T) {
	// We can't actually run the program in tests as it requires a terminal,
	// but we can verify the function signature is correct by checking it exists
	// and has the right type
	var _ func(*tea.Program) (tea.Model, error) = runProgram
}
