package tui

import (
	"errors"
	"strings"
	"testing"

	"github.com/SimoKiihamaki/autodev/internal/config"
	"github.com/charmbracelet/bubbles/viewport"
)

func TestRenderRunViewErrorBanner(t *testing.T) {
	t.Parallel()

	m := model{
		cfg:               config.Defaults(),
		keys:              DefaultKeyMap(),
		runFeed:           viewport.New(80, 16),
		runFeedBuf:        []string{"line one"},
		followLogs:        true,
		runFeedAutoFollow: true,
		errMsg:            "runner exited with error: exit status 1",
		lastRunErr:        errors.New("runner exited with error: exit status 1"),
	}
	m.runFeed.SetContent(strings.Join(m.runFeedBuf, "\n"))

	var b strings.Builder
	renderRunView(&b, m)
	out := b.String()

	if !strings.Contains(out, "Last error: runner exited with error: exit status 1") {
		t.Fatalf("expected error banner in view, got:\n%s", out)
	}

	if !strings.Contains(out, "Y copy error") {
		t.Fatalf("expected copy hint in view, got:\n%s", out)
	}

	if !strings.Contains(out, "Enter retry") {
		t.Fatalf("expected retry hint in view, got:\n%s", out)
	}
}

func TestBuildHelpOverlayContentIncludesGlobalAndTabActions(t *testing.T) {
	t.Parallel()
	m := model{
		keys: DefaultKeyMap(),
		tabs: defaultTabIDs(),
	}

	content := buildHelpOverlayContent(m)
	if content == "" {
		t.Fatalf("expected help overlay content to render")
	}

	if !strings.Contains(content, "Global") {
		t.Fatalf("expected global section in help overlay, got:\n%s", content)
	}

	if !strings.Contains(content, "Save config") {
		t.Fatalf("expected save action label in help overlay, got:\n%s", content)
	}

	runTitle := tabTitle(tabIDRun)
	if !strings.Contains(content, runTitle) {
		t.Fatalf("expected current tab title %q in help overlay, got:\n%s", runTitle, content)
	}

	if !strings.Contains(content, "Enter") {
		t.Fatalf("expected key combo to appear in help overlay, got:\n%s", content)
	}
}
