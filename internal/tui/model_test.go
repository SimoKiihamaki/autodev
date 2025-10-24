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

	return m
}
