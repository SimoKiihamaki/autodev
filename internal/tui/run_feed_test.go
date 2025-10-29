package tui

import (
	"fmt"
	"strings"
	"testing"

	"github.com/SimoKiihamaki/autodev/internal/config"
	"github.com/SimoKiihamaki/autodev/internal/runner"
	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
)

// Helper functions to create styled log lines for testing
func fLogLineInfo(format string, args ...interface{}) string {
	return fmt.Sprintf(format, args...)
}

func fLogLineAction(format string, args ...interface{}) string {
	return fmt.Sprintf(format, args...)
}

func TestHandleIterationHeader(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name             string
		line             string
		expectCurrent    int
		expectTotal      int
		expectLabel      string
		expectPhase      string
		expectRunCurrent string
	}{
		{
			name:             "with total and label",
			line:             "===== Iteration 3/10: Build =====",
			expectCurrent:    3,
			expectTotal:      10,
			expectLabel:      "Build",
			expectPhase:      "Iteration 3/10",
			expectRunCurrent: "Build",
		},
		{
			name:             "unknown total",
			line:             "===== Iteration 2/999999999999999999999 =====",
			expectCurrent:    2,
			expectTotal:      iterTotalUnknown,
			expectLabel:      "",
			expectPhase:      "Iteration 2/?",
			expectRunCurrent: "Iteration 2/?",
		},
		{
			name:             "unspecified total",
			line:             "===== Iteration 5 =====",
			expectCurrent:    5,
			expectTotal:      iterTotalUnspecified,
			expectLabel:      "",
			expectPhase:      "Iteration 5",
			expectRunCurrent: "Iteration 5",
		},
		{
			name:             "index overflow",
			line:             "===== Iteration 999999999999999999999 =====",
			expectCurrent:    iterIndexUnknown,
			expectTotal:      iterTotalUnspecified,
			expectLabel:      "",
			expectPhase:      "Iteration",
			expectRunCurrent: "Iteration",
		},
	}

	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			m := model{}
			matched := m.handleIterationHeader(tc.line)
			if !matched {
				t.Fatalf("expected header to match for line %q", tc.line)
			}
			if m.runIterCurrent != tc.expectCurrent {
				t.Fatalf("runIterCurrent=%d, want %d", m.runIterCurrent, tc.expectCurrent)
			}
			if m.runIterTotal != tc.expectTotal {
				t.Fatalf("runIterTotal=%d, want %d", m.runIterTotal, tc.expectTotal)
			}
			if m.runIterLabel != tc.expectLabel {
				t.Fatalf("runIterLabel=%q, want %q", m.runIterLabel, tc.expectLabel)
			}
			if m.runPhase != tc.expectPhase {
				t.Fatalf("runPhase=%q, want %q", m.runPhase, tc.expectPhase)
			}
			if m.runCurrent != tc.expectRunCurrent {
				t.Fatalf("runCurrent=%q, want %q", m.runCurrent, tc.expectRunCurrent)
			}
		})
	}
}

func TestConsumeRunSummaryStripsLogPrefix(t *testing.T) {
	t.Parallel()

	m := model{}
	line := "2025-10-27 13:14:40,704 INFO auto_prd.print: === Iteration 2/5: Build ==="
	m.consumeRunSummary(line)

	if m.runIterCurrent != 2 {
		t.Fatalf("runIterCurrent=%d, want 2", m.runIterCurrent)
	}
	if m.runIterTotal != 5 {
		t.Fatalf("runIterTotal=%d, want 5", m.runIterTotal)
	}
	if m.runIterLabel != "Build" {
		t.Fatalf("runIterLabel=%q, want Build", m.runIterLabel)
	}
	if m.runPhase != "Iteration 2/5" {
		t.Fatalf("runPhase=%q, want Iteration 2/5", m.runPhase)
	}
	if m.runCurrent != "Build" {
		t.Fatalf("runCurrent=%q, want Build", m.runCurrent)
	}

	m2 := model{}
	arrow := "2025-10-27 13:14:47,615 INFO auto_prd.print: → Launching implementation pass"
	m2.consumeRunSummary(arrow)
	if m2.runCurrent != "Launching implementation pass" {
		t.Fatalf("runCurrent=%q, want Launching implementation pass", m2.runCurrent)
	}
	if m2.runPhase != "Running" {
		t.Fatalf("runPhase=%q, want Running", m2.runPhase)
	}
}

func TestHandleRunFeedLine_LongStreamingSession(t *testing.T) {
	t.Parallel()

	// Create a model with a viewport
	m := model{
		runFeed:           viewport.New(80, 24),
		runFeedBuf:        make([]string, 0, feedBufCap),
		followLogs:        true,
		runFeedAutoFollow: true,
	}

	// Simulate a long streaming session with more lines than feedBufCap
	totalLines := feedBufCap * 2 // 1600 lines
	for i := 0; i < totalLines; i++ {
		displayLine := fLogLineAction("Processing item %d", i)
		rawLine := displayLine
		m.handleRunFeedLine(displayLine, rawLine)

		// Check that buffer doesn't exceed capacity
		if len(m.runFeedBuf) > feedBufCap {
			t.Fatalf("runFeedBuf length %d exceeds feedBufCap %d at iteration %d",
				len(m.runFeedBuf), feedBufCap, i)
		}
	}

	// After trimming, buffer should contain exactly the last feedBufCap lines
	if len(m.runFeedBuf) != feedBufCap {
		t.Fatalf("runFeedBuf length %d, want %d after streaming", len(m.runFeedBuf), feedBufCap)
	}

	// Check that the buffer contains the most recent lines
	lastExpectedLine := fLogLineAction("Processing item %d", totalLines-1)
	if m.runFeedBuf[feedBufCap-1] != lastExpectedLine {
		t.Fatalf("Last buffer line %q, want %q", m.runFeedBuf[feedBufCap-1], lastExpectedLine)
	}

	// Check that first line in buffer is from the trimmed portion
	firstExpectedLine := fLogLineAction("Processing item %d", totalLines-feedBufCap)
	if m.runFeedBuf[0] != firstExpectedLine {
		t.Fatalf("First buffer line %q, want %q", m.runFeedBuf[0], firstExpectedLine)
	}

	// Verify viewport content was updated
	content := m.runFeed.View()
	if content == "" {
		t.Fatal("viewport content should not be empty after streaming")
	}

	// Viewport has a limited height (24 lines), so we just check that it contains some of our buffer content
	if !strings.Contains(content, "Processing item") {
		t.Fatal("viewport content should contain our processing lines")
	}
}

func TestHandleRunFeedLine_FlushBoundaries(t *testing.T) {
	t.Parallel()

	// Test that first line always flushes (wasEmpty = true)
	m := model{
		runFeed:           viewport.New(80, 24),
		runFeedBuf:        make([]string, 0),
		followLogs:        true,
		runFeedAutoFollow: true,
	}

	line := fLogLineInfo("First line")
	m.handleRunFeedLine(line, line)

	// Dirty lines should be reset after first flush
	// Additional lines should appear in viewport
	for i := 1; i < 5; i++ {
		line = fLogLineInfo("Test line %d", i)
		m.handleRunFeedLine(line, line)
		if view := m.runFeed.View(); !strings.Contains(view, line) {
			t.Fatalf("viewport missing line %q", line)
		}
	}
}

func TestHandleRunFeedLine_EmptyBufferFirstFlush(t *testing.T) {
	t.Parallel()

	m := model{
		runFeed:           viewport.New(80, 24),
		runFeedBuf:        make([]string, 0),
		followLogs:        true,
		runFeedAutoFollow: true,
	}

	// First line should trigger immediate flush (wasEmpty = true)
	line := fLogLineInfo("First line")
	m.handleRunFeedLine(line, line)

	// Content should be updated immediately
	content := m.runFeed.View()
	if content == "" {
		t.Fatal("viewport content should be updated immediately for first line")
	}

	// Should contain the line
	if !strings.Contains(content, "First line") {
		t.Fatalf("content %q should contain 'First line'", content)
	}

	// Dirty lines should be reset after immediate flush
}

func TestHandleRunFeedLine_TrimmingFlush(t *testing.T) {
	t.Parallel()

	m := model{
		runFeed:           viewport.New(80, 24),
		runFeedBuf:        make([]string, 0),
		followLogs:        true,
		runFeedAutoFollow: true,
	}

	// Fill buffer to capacity to trigger trimming
	for i := 0; i < feedBufCap+1; i++ {
		line := fLogLineInfo("Line %d", i)
		m.handleRunFeedLine(line, line)
	}

	// Buffer should be trimmed to capacity
	if len(m.runFeedBuf) != feedBufCap {
		t.Fatalf("runFeedBuf length %d, want %d after trimming", len(m.runFeedBuf), feedBufCap)
	}

	// Content should be flushed when trimming occurs
	content := m.runFeed.View()
	if content == "" {
		t.Fatal("viewport content should be flushed when trimming occurs")
	}

	// Buffer should contain the most recent feedBufCap lines
	firstExpectedLine := fLogLineInfo("Line %d", 1) // Line 0 should be trimmed
	if m.runFeedBuf[0] != firstExpectedLine {
		t.Fatalf("first buffer line %q, want %q", m.runFeedBuf[0], firstExpectedLine)
	}

	lastExpectedLine := fLogLineInfo("Line %d", feedBufCap)
	if m.runFeedBuf[feedBufCap-1] != lastExpectedLine {
		t.Fatalf("last buffer line %q, want %q", m.runFeedBuf[feedBufCap-1], lastExpectedLine)
	}
}

func TestHandleRunFeedLine_AutoFollowBehavior(t *testing.T) {
	t.Parallel()

	m := model{
		runFeed:           viewport.New(80, 24),
		runFeedBuf:        make([]string, 0),
		followLogs:        true,
		runFeedAutoFollow: true,
	}

	// Add enough lines to trigger updates
	for i := 0; i < 4; i++ {
		line := fLogLineInfo("Line %d", i)
		m.handleRunFeedLine(line, line)
	}

	// Auto-follow should be preserved when enabled
	if !m.runFeedAutoFollow {
		t.Fatal("runFeedAutoFollow should remain true when initially enabled")
	}

	// Viewport should be at bottom after flush
	if !m.runFeed.AtBottom() {
		t.Fatal("viewport should be at bottom when auto-follow is enabled")
	}

	// Add more lines to ensure viewport can scroll away from bottom
	for i := 4; i < 40; i++ {
		line := fLogLineInfo("Warmup line %d", i)
		m.handleRunFeedLine(line, line)
	}

	m.runFeed.GotoTop()
	if m.runFeed.AtBottom() {
		t.Fatal("viewport should not be at bottom after user scrolls to top")
	}

	m.runFeedAutoFollow = false

	for i := 0; i < 5; i++ {
		line := fLogLineInfo("Scrolled line %d", i)
		m.handleRunFeedLine(line, line)
	}

	if m.runFeedAutoFollow {
		t.Fatal("auto follow should remain false when user has scrolled away")
	}
}

func TestToggleFollowUpdatesPreference(t *testing.T) {
	t.Parallel()

	cfg := config.Defaults()
	m := model{
		cfg:               cfg,
		runFeed:           viewport.New(80, 24),
		runFeedBuf:        make([]string, 0),
		followLogs:        true,
		runFeedAutoFollow: true,
	}

	handled, _ := m.handleRunTabActions([]Action{ActToggleFollow}, tea.KeyMsg{})
	if !handled {
		t.Fatal("expected toggle follow action to be handled")
	}

	if m.followLogs {
		t.Fatal("expected followLogs to be disabled after toggle")
	}

	if m.cfg.FollowLogs {
		t.Fatal("expected config FollowLogs to reflect toggle state")
	}

	if m.runFeedAutoFollow {
		t.Fatal("runFeedAutoFollow should be disabled when follow logs is off")
	}

	handled, _ = m.handleRunTabActions([]Action{ActToggleFollow}, tea.KeyMsg{})
	if !handled {
		t.Fatal("expected second toggle follow action to be handled")
	}

	if !m.followLogs {
		t.Fatal("expected followLogs to be enabled after second toggle")
	}

	if !m.cfg.FollowLogs {
		t.Fatal("expected config FollowLogs to be enabled after second toggle")
	}

	if !m.runFeedAutoFollow {
		t.Fatal("runFeedAutoFollow should resume when follow logs is re-enabled")
	}
}

func TestFormatLogLine_VariousLogTypes(t *testing.T) {
	t.Parallel()

	m := model{}

	tests := []struct {
		name      string
		line      runner.Line
		wantPlain string
		wantStyle string // We'll just check that it's not empty
	}{
		{
			name:      "info line",
			line:      runner.Line{Text: "Processing file"},
			wantPlain: "Processing file",
		},
		{
			name:      "error line",
			line:      runner.Line{Text: "Something went wrong", Err: true},
			wantPlain: "Something went wrong",
		},
		{
			name:      "warning line",
			line:      runner.Line{Text: "⚠️ Potential issue"},
			wantPlain: "⚠️ Potential issue",
		},
		{
			name:      "success line",
			line:      runner.Line{Text: "✓ Task completed"},
			wantPlain: "✓ Task completed",
		},
		{
			name:      "action line",
			line:      runner.Line{Text: "→ Starting process"},
			wantPlain: "→ Starting process",
		},
		{
			name:      "process finished",
			line:      runner.Line{Text: "process finished successfully"},
			wantPlain: "process finished successfully",
		},
		{
			name:      "review loop",
			line:      runner.Line{Text: "starting review loop"},
			wantPlain: "starting review loop",
		},
	}

	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			styled, plain := m.formatLogLine(tc.line)

			if plain != tc.wantPlain {
				t.Fatalf("plain=%q, want %q", plain, tc.wantPlain)
			}

			if styled == "" {
				t.Fatal("styled output should not be empty")
			}

			// Styled output should contain the plain text (possibly with ANSI codes)
			if !strings.Contains(styled, tc.wantPlain) {
				t.Fatalf("styled output %q should contain plain text %q", styled, tc.wantPlain)
			}
		})
	}
}
