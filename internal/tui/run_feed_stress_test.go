package tui

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/SimoKiihamaki/autodev/internal/config"
	"github.com/SimoKiihamaki/autodev/internal/runner"
	"github.com/charmbracelet/bubbles/viewport"
)

// timestampedLine represents a line with captured timing information
type timestampedLine struct {
	timestamp  time.Time
	runnerTime time.Time
	text       string
	iteration  int
	burstPhase string
}

// feedStressTester captures detailed timing information during stress testing
type feedStressTester struct {
	lines         []timestampedLine
	runnerStart   time.Time
	lastFlush     time.Time
	flushInterval time.Duration
}

func (f *feedStressTester) recordLine(text string, runnerTime time.Time) {
	now := time.Now()
	line := timestampedLine{
		timestamp:  now,
		runnerTime: runnerTime,
		text:       text,
	}

	// Parse iteration information
	if match := regexp.MustCompile(`Iteration (\d+(?:\.\d+)?)`).FindStringSubmatch(text); match != nil {
		if iter, err := strconv.Atoi(strings.Split(match[1], ".")[0]); err == nil {
			line.iteration = iter
		}
	}

	// Parse phase information
	if strings.Contains(text, "BURST") {
		line.burstPhase = "burst"
	} else if strings.Contains(text, "SLOW DRIP") {
		line.burstPhase = "slow_drip"
	} else if strings.Contains(text, "LARGE BLOCK") {
		line.burstPhase = "large_block"
	} else if strings.Contains(text, "MIXED PATTERNS") {
		line.burstPhase = "mixed"
	} else if strings.Contains(text, "FINAL") {
		line.burstPhase = "final"
	}

	f.lines = append(f.lines, line)

	// Check for potential stalls
	if !f.lastFlush.IsZero() && now.Sub(f.lastFlush) > f.flushInterval {
		fmt.Printf("POTENTIAL STALL: %v since last flush (current line: %s)\n",
			now.Sub(f.lastFlush), text)
	}
}

func (f *feedStressTester) recordFlush() {
	f.lastFlush = time.Now()
}

func (f *feedStressTester) analyzeStalls() {
	if len(f.lines) == 0 {
		return
	}

	fmt.Printf("\n=== FEED STRESS ANALYSIS ===\n")
	fmt.Printf("Total lines captured: %d\n", len(f.lines))
	fmt.Printf("Test duration: %v\n", f.lines[len(f.lines)-1].timestamp.Sub(f.runnerStart))

	// Analyze gaps between lines
	var maxGap time.Duration
	maxGapIndex := -1
	var stallThreshold = 2 * time.Second

	for i := 1; i < len(f.lines); i++ {
		gap := f.lines[i].timestamp.Sub(f.lines[i-1].timestamp)
		if gap > maxGap {
			maxGap = gap
			maxGapIndex = i
		}

		if gap > stallThreshold {
			fmt.Printf("STALL DETECTED: %v gap between lines %d and %d\n", gap, i-1, i)
			fmt.Printf("  Line %d: %s\n", i-1, f.lines[i-1].text)
			fmt.Printf("  Line %d: %s\n", i, f.lines[i].text)
		}
	}

	fmt.Printf("Maximum gap: %v at line %d\n", maxGap, maxGapIndex)
	if maxGapIndex > 0 && maxGapIndex < len(f.lines) {
		fmt.Printf("  Context: %s\n", f.lines[maxGapIndex].text)
	}

	// Analyze by phase
	phases := make(map[string][]timestampedLine)
	for _, line := range f.lines {
		if line.burstPhase != "" {
			phases[line.burstPhase] = append(phases[line.burstPhase], line)
		}
	}

	for phase, phaseLines := range phases {
		if len(phaseLines) > 1 {
			duration := phaseLines[len(phaseLines)-1].timestamp.Sub(phaseLines[0].timestamp)
			avgRate := float64(len(phaseLines)) / duration.Seconds()
			fmt.Printf("Phase %s: %d lines in %v (%.1f lines/sec)\n",
				phase, len(phaseLines), duration, avgRate)
		}
	}

	// Check runner vs TUI timestamp correlation
	var totalRunnerDelay time.Duration
	var maxRunnerDelay time.Duration
	delayCount := 0

	for _, line := range f.lines {
		if !line.runnerTime.IsZero() {
			delay := line.timestamp.Sub(line.runnerTime)
			if delay > 0 {
				totalRunnerDelay += delay
				delayCount++
				if delay > maxRunnerDelay {
					maxRunnerDelay = delay
				}
			}
		}
	}

	if delayCount > 0 {
		avgDelay := totalRunnerDelay / time.Duration(delayCount)
		fmt.Printf("Runner -> TUI delay: avg %v, max %v\n", avgDelay, maxRunnerDelay)
	}
}

// TestRunFeedStressTest runs a comprehensive stress test of the live feed system
func TestRunFeedStressTest(t *testing.T) {
	if testing.Short() {
		t.Skip("Skipping stress test in short mode")
	}

	// Create temporary log file for detailed debugging
	tempDir := t.TempDir()
	logFile := filepath.Join(tempDir, "stress_test.log")

	// Create a test PRD file
	prdContent := `# Stress Test PRD

## Test Feature
This is a stress test PRD for evaluating the live feed system under various load conditions.

## Requirements
- Handle bursty output
- Handle slow steady output
- Handle large output blocks
- Maintain responsiveness throughout

## Expected Behavior
The TUI should continuously update and display all output without stalling.
`
	prdFile := filepath.Join(tempDir, "stress_test.md")
	if err := os.WriteFile(prdFile, []byte(prdContent), 0644); err != nil {
		t.Fatalf("Failed to create test PRD: %v", err)
	}

	// Build the stress test script path
	scriptPath := filepath.Join("..", "..", "tools", "auto_prd", "tests", "test_feed_stress.py")
	if _, err := os.Stat(scriptPath); os.IsNotExist(err) {
		t.Skipf("Stress test script not found at %s", scriptPath)
	}

	// Configure test
	cfg := config.Config{
		RepoPath:      tempDir,
		PythonCommand: "python3",
		PythonScript:  scriptPath,
		BaseBranch:    "main",
		Branch:        "test-stress-feed",
		Flags: config.Flags{
			DryRun: true,
		},
		Timings: config.Timings{
			WaitMinutes:       0,
			ReviewPollSeconds: 1,
		},
		LogLevel: "INFO",
	}

	// Create tester
	tester := &feedStressTester{
		flushInterval: 5 * time.Second, // Consider > 5s as potential stall
	}

	// Create channel for capturing logs
	logCh := make(chan runner.Line, 2048)

	// Create context with timeout for test
	ctx, cancel := context.WithTimeout(context.Background(), 120*time.Second)
	defer cancel()

	// Start log collector
	done := make(chan struct{})
	go func() {
		defer close(done)
		tester.runnerStart = time.Now()

		for line := range logCh {
			// Parse timestamp from line if present
			runnerTime := line.Time
			if match := regexp.MustCompile(`\[([0-9]+\.[0-9]+)\]`).FindStringSubmatch(line.Text); match != nil {
				if _, err := strconv.ParseFloat(match[1], 64); err == nil {
					// This is a timestamp from our stress script
					// Use the line's own time as approximation
					runnerTime = line.Time
				}
			}

			tester.recordLine(line.Text, runnerTime)

			// Record flush events
			if strings.Contains(line.Text, "FLUSH") || strings.Contains(line.Text, "Completed") {
				tester.recordFlush()
			}

			// Break on completion
			if strings.Contains(line.Text, "STRESS TEST COMPLETED") ||
				strings.Contains(line.Text, "process finished") {
				break
			}
		}
	}()

	// Run the stress test
	opts := runner.Options{
		Config:      cfg,
		PRDPath:     prdFile,
		Logs:        logCh,
		LogFilePath: logFile,
		LogLevel:    "DEBUG",
	}

	// Add script arguments
	if !strings.Contains(cfg.PythonScript, "test_feed_stress.py") {
		// If not using our stress test script, skip
		t.Skip("Stress test requires test_feed_stress.py script")
	}

	// Run the test
	err := opts.Run(ctx)
	if err != nil && !strings.Contains(err.Error(), "context deadline exceeded") {
		t.Logf("Stress test completed with error: %v", err)
	}

	// Wait for collector to finish (runner closes the channel)
	<-done

	// Analyze results
	tester.analyzeStalls()

	// Verify we captured reasonable amount of output
	if len(tester.lines) < 50 {
		t.Errorf("Expected at least 50 lines of output, got %d", len(tester.lines))
	}

	// Check that we saw multiple phases
	phases := make(map[string]bool)
	for _, line := range tester.lines {
		if line.burstPhase != "" {
			phases[line.burstPhase] = true
		}
	}

	expectedPhases := []string{"burst", "slow_drip", "large_block", "mixed", "final"}
	for _, phase := range expectedPhases {
		if !phases[phase] {
			t.Logf("Warning: phase %s not detected in output", phase)
		}
	}

	// The test passes if we don't find any major stalls (> 10 seconds)
	// and we captured a reasonable amount of output
	maxAcceptableGap := 10 * time.Second
	for i := 1; i < len(tester.lines); i++ {
		gap := tester.lines[i].timestamp.Sub(tester.lines[i-1].timestamp)
		if gap > maxAcceptableGap {
			t.Errorf("Unacceptable gap detected: %v between lines %d and %d",
				gap, i-1, i)
		}
	}
}

// TestRunFeedBurstHandling specifically tests burst handling and flush behavior
func TestRunFeedBurstHandling(t *testing.T) {
	// Create a model with viewport
	m := model{
		runFeed:           viewport.New(80, 24),
		runFeedBuf:        make([]string, 0, feedBufCap),
		runFeedAutoFollow: true,
		flushController:   newAdaptiveFlushController(),
	}

	// Simulate a rapid burst that exceeds normal flush thresholds
	burstSize := feedFollowFlushStep * 3 // 12 lines
	start := time.Now()

	for i := 0; i < burstSize; i++ {
		displayLine := fmt.Sprintf("Burst line %d at %v", i, time.Now().Sub(start))
		rawLine := displayLine
		m.handleRunFeedLine(displayLine, rawLine)

		// Small delay to simulate real timing
		time.Sleep(1 * time.Millisecond)
	}

	// Verify the buffer was handled correctly
	if len(m.runFeedBuf) > feedBufCap {
		t.Errorf("Buffer exceeded capacity: %d > %d", len(m.runFeedBuf), feedBufCap)
	}

	// Verify content made it to viewport
	content := m.runFeed.View()
	if content == "" {
		t.Error("Viewport should contain content after burst")
	}

	if !strings.Contains(content, "Burst line") {
		t.Error("Viewport should contain burst lines")
	}

	// Verify auto-follow is still enabled
	if !m.runFeedAutoFollow {
		t.Error("Auto-follow should remain enabled after burst")
	}

	// Verify viewport is at bottom
	if !m.runFeed.AtBottom() {
		t.Error("Viewport should be at bottom after burst with auto-follow")
	}
}
