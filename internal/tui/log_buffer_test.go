package tui

import (
	"fmt"
	"runtime"
	"strings"
	"testing"
	"time"

	"github.com/SimoKiihamaki/autodev/internal/config"
	"github.com/SimoKiihamaki/autodev/internal/runner"
)

// TestLogBufferMemoryLeakFix verifies that the log buffer memory fix works correctly.
// The fix creates a new slice when the buffer exceeds maxLines instead of re-slicing,
// which would retain the old backing array and cause memory growth.
func TestLogBufferMemoryLeakFix(t *testing.T) {
	t.Parallel()

	// Create a model with a small max log lines setting for testing
	maxLines := 100
	cfg := config.Defaults()
	cfg.UI.MaxLogLines = &maxLines

	m := &model{
		cfg:    cfg,
		logBuf: make([]string, 0),
	}

	// Add more lines than maxLines to trigger the buffer trim logic
	totalLines := maxLines + 50

	for i := 0; i < totalLines; i++ {
		lines := []runner.Line{
			{Time: time.Now(), Text: fmt.Sprintf("Log line %d", i), Err: false},
		}
		msg := logBatchMsg{lines: lines, closed: false}
		m.handleLogBatch(msg)
	}

	// Verify buffer length is capped at maxLines
	if len(m.logBuf) != maxLines {
		t.Errorf("Expected log buffer to have %d lines, got %d", maxLines, len(m.logBuf))
	}

	// Verify capacity is also capped (not retaining old backing array)
	if cap(m.logBuf) != maxLines {
		t.Errorf("Expected log buffer capacity to be %d, got %d (memory leak)", maxLines, cap(m.logBuf))
	}

	// Verify the buffer contains the latest lines (oldest should be trimmed)
	// The first line in buffer should be line 50 (0-indexed: lines 0-49 trimmed)
	firstLine := m.logBuf[0]
	expectedFirstIdx := totalLines - maxLines // Should be 50
	expectedPrefix := fmt.Sprintf("Log line %d", expectedFirstIdx)
	if !strings.Contains(firstLine, expectedPrefix) {
		t.Errorf("First line should contain '%s', got '%s'", expectedPrefix, firstLine)
	}

	// The last line should be the most recent
	lastLine := m.logBuf[len(m.logBuf)-1]
	expectedLastIdx := totalLines - 1
	expectedLastPrefix := fmt.Sprintf("Log line %d", expectedLastIdx)
	if !strings.Contains(lastLine, expectedLastPrefix) {
		t.Errorf("Last line should contain '%s', got '%s'", expectedLastPrefix, lastLine)
	}
}

// TestLogBufferNewSliceReleasesOldMemory tests that creating a new slice
// allows the old backing array to be garbage collected.
func TestLogBufferNewSliceReleasesOldMemory(t *testing.T) {
	t.Parallel()

	maxLines := 50
	cfg := config.Defaults()
	cfg.UI.MaxLogLines = &maxLines

	m := &model{
		cfg:    cfg,
		logBuf: make([]string, 0),
	}

	// Force GC to get a baseline
	runtime.GC()
	var memBefore runtime.MemStats
	runtime.ReadMemStats(&memBefore)

	// Add many large log lines to create significant memory usage
	// We'll do multiple rounds to simulate long-running sessions
	for round := 0; round < 10; round++ {
		for i := 0; i < maxLines*2; i++ {
			// Create large log lines to make memory differences more noticeable
			largeText := fmt.Sprintf("Round %d Line %d %s", round, i, strings.Repeat("x", 1000))
			lines := []runner.Line{
				{Time: time.Now(), Text: largeText, Err: false},
			}
			msg := logBatchMsg{lines: lines, closed: false}
			m.handleLogBatch(msg)
		}

		// Force GC between rounds
		runtime.GC()
	}

	// Final GC
	runtime.GC()
	var memAfter runtime.MemStats
	runtime.ReadMemStats(&memAfter)

	// Verify buffer is still capped at maxLines
	if len(m.logBuf) != maxLines {
		t.Errorf("Buffer length should be %d, got %d", maxLines, len(m.logBuf))
	}

	// The capacity should also be maxLines (not growing unbounded)
	if cap(m.logBuf) != maxLines {
		t.Errorf("Buffer capacity should be %d, got %d", maxLines, cap(m.logBuf))
	}
}

// TestLogBufferCopyPreservesCorrectEntries verifies that the copy operation
// preserves the correct (most recent) log entries when trimming.
func TestLogBufferCopyPreservesCorrectEntries(t *testing.T) {
	t.Parallel()

	maxLines := 10
	cfg := config.Defaults()
	cfg.UI.MaxLogLines = &maxLines

	m := &model{
		cfg:    cfg,
		logBuf: make([]string, 0),
	}

	// Add exactly 2x maxLines entries
	totalLines := maxLines * 2
	for i := 0; i < totalLines; i++ {
		lines := []runner.Line{
			{Time: time.Now(), Text: fmt.Sprintf("Entry_%d", i), Err: false},
		}
		msg := logBatchMsg{lines: lines, closed: false}
		m.handleLogBatch(msg)
	}

	// Verify we have exactly maxLines entries
	if len(m.logBuf) != maxLines {
		t.Fatalf("Expected %d entries, got %d", maxLines, len(m.logBuf))
	}

	// Verify entries 10-19 are present (the last maxLines entries)
	for i := 0; i < maxLines; i++ {
		expectedIdx := totalLines - maxLines + i
		expectedContent := fmt.Sprintf("Entry_%d", expectedIdx)
		if !strings.Contains(m.logBuf[i], expectedContent) {
			t.Errorf("Entry %d should contain '%s', got '%s'", i, expectedContent, m.logBuf[i])
		}
	}
}

// TestLogBufferBelowMaxLinesNoTrimming verifies that buffers below maxLines
// are not unnecessarily reallocated.
func TestLogBufferBelowMaxLinesNoTrimming(t *testing.T) {
	t.Parallel()

	maxLines := 100
	cfg := config.Defaults()
	cfg.UI.MaxLogLines = &maxLines

	m := &model{
		cfg:    cfg,
		logBuf: make([]string, 0),
	}

	// Add fewer lines than maxLines
	numLines := maxLines / 2
	for i := 0; i < numLines; i++ {
		lines := []runner.Line{
			{Time: time.Now(), Text: fmt.Sprintf("Line %d", i), Err: false},
		}
		msg := logBatchMsg{lines: lines, closed: false}
		m.handleLogBatch(msg)
	}

	// Buffer should have exactly numLines entries
	if len(m.logBuf) != numLines {
		t.Errorf("Expected %d entries, got %d", numLines, len(m.logBuf))
	}

	// All entries should be preserved
	for i := 0; i < numLines; i++ {
		expectedContent := fmt.Sprintf("Line %d", i)
		if !strings.Contains(m.logBuf[i], expectedContent) {
			t.Errorf("Entry %d should contain '%s', got '%s'", i, expectedContent, m.logBuf[i])
		}
	}
}

// TestLogBufferExactlyAtMaxLines verifies behavior when buffer is exactly at maxLines.
func TestLogBufferExactlyAtMaxLines(t *testing.T) {
	t.Parallel()

	maxLines := 50
	cfg := config.Defaults()
	cfg.UI.MaxLogLines = &maxLines

	m := &model{
		cfg:    cfg,
		logBuf: make([]string, 0),
	}

	// Add exactly maxLines entries
	for i := 0; i < maxLines; i++ {
		lines := []runner.Line{
			{Time: time.Now(), Text: fmt.Sprintf("Line %d", i), Err: false},
		}
		msg := logBatchMsg{lines: lines, closed: false}
		m.handleLogBatch(msg)
	}

	if len(m.logBuf) != maxLines {
		t.Errorf("Expected %d entries at boundary, got %d", maxLines, len(m.logBuf))
	}

	// Add one more to trigger trimming
	lines := []runner.Line{
		{Time: time.Now(), Text: "Overflow line", Err: false},
	}
	msg := logBatchMsg{lines: lines, closed: false}
	m.handleLogBatch(msg)

	// Still should have maxLines
	if len(m.logBuf) != maxLines {
		t.Errorf("Expected %d entries after overflow, got %d", maxLines, len(m.logBuf))
	}

	// Capacity should also be maxLines
	if cap(m.logBuf) != maxLines {
		t.Errorf("Expected capacity %d after overflow, got %d", maxLines, cap(m.logBuf))
	}

	// First entry should now be "Line 1" (not "Line 0")
	if !strings.Contains(m.logBuf[0], "Line 1") {
		t.Errorf("First entry should be 'Line 1', got '%s'", m.logBuf[0])
	}

	// Last entry should be "Overflow line"
	if !strings.Contains(m.logBuf[len(m.logBuf)-1], "Overflow line") {
		t.Errorf("Last entry should be 'Overflow line', got '%s'", m.logBuf[len(m.logBuf)-1])
	}
}

// TestLogBufferDefaultMaxLines verifies the default max lines is used when not configured.
func TestLogBufferDefaultMaxLines(t *testing.T) {
	t.Parallel()

	cfg := config.Defaults()
	// Don't set UI.MaxLogLines - should use DefaultMaxLogLines

	m := &model{
		cfg:    cfg,
		logBuf: make([]string, 0),
	}

	// Add more than default max lines
	totalLines := config.DefaultMaxLogLines + 100

	for i := 0; i < totalLines; i++ {
		lines := []runner.Line{
			{Time: time.Now(), Text: fmt.Sprintf("Line %d", i), Err: false},
		}
		msg := logBatchMsg{lines: lines, closed: false}
		m.handleLogBatch(msg)
	}

	// Buffer should be capped at default
	if len(m.logBuf) != config.DefaultMaxLogLines {
		t.Errorf("Expected %d entries (default), got %d", config.DefaultMaxLogLines, len(m.logBuf))
	}
}
