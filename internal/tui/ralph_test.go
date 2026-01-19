package tui

import (
	"testing"
)

func TestRalphBooleanToggleDirect(t *testing.T) {
	t.Parallel()
	m := newModelForSettingsTest()

	// Focus on a Ralph boolean input
	m.focusInput("ralphenabled")
	if m.focusedInput != "ralphenabled" {
		t.Fatalf("expected focus on ralphenabled, got %q", m.focusedInput)
	}

	// Check initial value is false
	if m.inRalphEnabled.Value() != "false" {
		t.Fatalf("expected initial value 'false', got %q", m.inRalphEnabled.Value())
	}

	// Check that getInputField returns the field
	field := m.getInputField("ralphenabled")
	if field == nil {
		t.Fatal("getInputField returned nil for ralphenabled")
	}
	t.Logf("Field pointer: %p, inRalphEnabled pointer: %p", field, &m.inRalphEnabled)
	t.Logf("Field value before: %q", field.Value())

	// Directly call toggleBooleanInput
	handled, _ := m.toggleBooleanInput()
	t.Logf("Handled: %v", handled)
	t.Logf("Field value after: %q", m.inRalphEnabled.Value())

	if !handled {
		t.Fatal("toggleBooleanInput should return handled=true")
	}

	// Check that the value toggled to true
	if m.inRalphEnabled.Value() != "true" {
		t.Fatalf("expected value 'true' after toggle, got %q", m.inRalphEnabled.Value())
	}
}
