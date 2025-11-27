package config

import (
	"testing"
	"time"

	"github.com/SimoKiihamaki/autodev/internal/utils"
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
	modified.FollowLogs = utils.BoolPtr(!*base.FollowLogs)
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

func TestIsValidGitBranchName(t *testing.T) {
	validBranches := []string{
		"main",
		"master",
		"feature/new-feature",
		"bugfix/123-fix-issue",
		"release-1.0.0",
		"codex/plan-20251127",
		"user/john/experiment",
		"v1.2.3",
		"some_branch",
		"UPPERCASE",
		"MixedCase123",
		"-hyphen-start",   // dashes at start/end are allowed per git spec
		"hyphen-end-",     // dashes at end are allowed
		"-both-ends-",     // dashes at both ends are allowed
		"--double-hyphen", // even multiple dashes are allowed
	}

	for _, branch := range validBranches {
		if !isValidGitBranchName(branch) {
			t.Errorf("expected %q to be valid, but was rejected", branch)
		}
	}

	invalidBranches := []string{
		"",               // empty
		".hidden",        // starts with dot
		"/leading-slash", // starts with slash
		"trailing.",      // ends with dot
		"trailing/",      // ends with slash
		"branch.lock",    // ends with .lock
		"has..dots",      // consecutive dots
		"has//slashes",   // consecutive slashes
		"has space",      // contains space
		"has~tilde",      // contains tilde
		"has^caret",      // contains caret
		"has:colon",      // contains colon
		"has?question",   // contains question mark
		"has*star",       // contains asterisk
		"has[bracket",    // contains open bracket
		"has@{seq",       // contains @{ sequence (security measure)
		"has\\backslash", // contains backslash
	}

	for _, branch := range invalidBranches {
		if isValidGitBranchName(branch) {
			t.Errorf("expected %q to be invalid, but was accepted", branch)
		}
	}
}

func TestValidateInterFieldBranchNames(t *testing.T) {
	// Valid branch name should not produce error
	cfg := Defaults()
	cfg.Branch = "feature/valid-branch"
	cfg.BaseBranch = "main"
	result := cfg.ValidateInterField()
	for _, issue := range result.Issues {
		if issue.Field == "branch" || issue.Field == "base_branch" {
			t.Errorf("unexpected validation issue for valid branch: %s - %s", issue.Field, issue.Message)
		}
	}

	// Invalid branch name should produce error
	cfg = Defaults()
	cfg.Branch = "invalid..branch"
	result = cfg.ValidateInterField()
	found := false
	for _, issue := range result.Issues {
		if issue.Field == "branch" && issue.Severity == "error" {
			found = true
			break
		}
	}
	if !found {
		t.Error("expected validation error for invalid branch name")
	}

	// Invalid base branch name should produce error
	cfg = Defaults()
	cfg.BaseBranch = "has space"
	result = cfg.ValidateInterField()
	found = false
	for _, issue := range result.Issues {
		if issue.Field == "base_branch" && issue.Severity == "error" {
			found = true
			break
		}
	}
	if !found {
		t.Error("expected validation error for invalid base_branch name")
	}
}
