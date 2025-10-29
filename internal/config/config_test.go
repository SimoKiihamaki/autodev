package config

import (
	"testing"
	"time"
)

func TestConfigCloneIndependence(t *testing.T) {
	base := Defaults()
	base.AllowedPythonDirs = []string{"/tmp/autodev"}
	stamp := time.Now()
	base.PRDs = map[string]PRDMeta{
		"/tmp/doc.md": {Tags: []string{"foo"}, LastUsed: stamp},
	}

	clone := base.Clone()
	if !base.Equal(clone) {
		t.Fatalf("expected clone to be equal to original")
	}

	clone.AllowedPythonDirs[0] = "/other"
	clone.PRDs["/tmp/doc.md"] = PRDMeta{Tags: []string{"bar"}}

	if base.AllowedPythonDirs[0] != "/tmp/autodev" {
		t.Fatalf("original slice mutated by clone change")
	}
	if got := base.PRDs["/tmp/doc.md"].Tags[0]; got != "foo" {
		t.Fatalf("original map mutated by clone change, got %q", got)
	}
}

func TestConfigEqual(t *testing.T) {
	base := Defaults()
	base.Flags.AllowUnsafe = true
	base.AllowedPythonDirs = []string{"/tmp/autodev"}
	base.PRDs = map[string]PRDMeta{
		"/tmp/doc.md": {Tags: []string{"foo"}},
	}

	if !base.Equal(base.Clone()) {
		t.Fatalf("expected equal configs to report true")
	}

	modified := base.Clone()
	modified.Flags.AllowUnsafe = false
	if base.Equal(modified) {
		t.Fatalf("expected differing flags to report inequality")
	}

	modified = base.Clone()
	modified.FollowLogs = boolPtr(!*base.FollowLogs)
	if base.Equal(modified) {
		t.Fatalf("expected differing follow_logs to report inequality")
	}

	modified = base.Clone()
	modified.PRDs["/tmp/doc.md"] = PRDMeta{Tags: []string{"foo"}, LastUsed: time.Now()}
	if base.Equal(modified) {
		t.Fatalf("expected differing PRD metadata to report inequality")
	}

	base = Defaults()
	base.AllowedPythonDirs = nil
	modified = base.Clone()
	modified.AllowedPythonDirs = []string{}
	if !base.Equal(modified) {
		t.Fatalf("nil vs empty slices should be considered equal")
	}
}
