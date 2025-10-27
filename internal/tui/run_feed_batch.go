package tui

import (
	"time"

	"github.com/SimoKiihamaki/autodev/internal/runner"
	tea "github.com/charmbracelet/bubbletea"
)

// logBatchMsg represents multiple log lines processed in a batch
type logBatchMsg struct {
	lines []runner.Line
}

// batchLogReader reads multiple lines from the log channel in one operation
func (m model) readLogsBatch() tea.Cmd {
	if m.logCh == nil {
		return nil
	}
	ch := m.logCh
	return func() tea.Msg {
		var lines []runner.Line

		// Read up to maxBatchSize lines or until channel is empty
		for i := 0; i < maxBatchSize; i++ {
			select {
			case line, ok := <-ch:
				if !ok {
					// Channel closed
					if len(lines) > 0 {
						return logBatchMsg{lines: lines}
					}
					return nil
				}
				lines = append(lines, line)

			case <-time.After(1 * time.Millisecond):
				// Channel is empty, return what we have
				if len(lines) > 0 {
					return logBatchMsg{lines: lines}
				}
				// No lines available, schedule another read
				return nil
			}
		}

		// Got maxBatchSize lines
		if len(lines) > 0 {
			return logBatchMsg{lines: lines}
		}
		return nil
	}
}

// handleLogBatch processes multiple log lines efficiently
func (m *model) handleLogBatch(lines []runner.Line) tea.Cmd {
	if len(lines) == 0 {
		return nil
	}

	// Process each line in the batch
	for _, line := range lines {
		styled, plain := m.formatLogLine(line)
		m.handleRunFeedLine(styled, plain)
	}

	// Schedule another read if we still have a log channel
	if m.logCh != nil {
		return m.readLogsBatch()
	}
	return nil
}

// Constants for batch processing
const (
	maxBatchSize     = 25   // Maximum lines to process in one batch (reduced from 50 for responsiveness)
	batchTimeoutMs   = 1    // Timeout in milliseconds to wait for more lines
	highVolumeRate   = 10.0 // Lines per second considered high volume
	lowVolumeRate    = 2.0  // Lines per second considered low volume
	diagnosticCount  = 50   // Number of recent diagnostics to keep
	stallThresholdMs = 100  // Processing time threshold for stall detection
)

// feedDiagnostic captures performance metrics for troubleshooting
type feedDiagnostic struct {
	timestamp      time.Time
	batchSize      int
	bufferSize     int
	dirtyLines     int
	processingTime time.Duration
	outputRate     float64 // lines per second
}

// adaptiveFlushController manages dynamic flush thresholds
type adaptiveFlushController struct {
	lastFlush       time.Time
	outputRate      float64
	adaptiveStep    int
	sampleWindow    time.Duration
	sampleLineCount int
	lastSampleTime  time.Time
}

// newAdaptiveFlushController creates a new adaptive flush controller
func newAdaptiveFlushController() *adaptiveFlushController {
	return &adaptiveFlushController{
		adaptiveStep:   feedFollowFlushStep,
		sampleWindow:   5 * time.Second,
		lastSampleTime: time.Now(),
	}
}

// updateSample updates the output rate calculation
func (afc *adaptiveFlushController) updateSample(lineCount int) {
	now := time.Now()
	timeSinceSample := now.Sub(afc.lastSampleTime)

	if timeSinceSample >= afc.sampleWindow {
		// Calculate output rate over the sample window
		if timeSinceSample > 0 {
			afc.outputRate = float64(afc.sampleLineCount) / timeSinceSample.Seconds()
		}

		// Reset for next sample
		afc.sampleLineCount = lineCount
		afc.lastSampleTime = now

		// Adjust adaptive step based on output rate
		switch {
		case afc.outputRate > highVolumeRate:
			// High volume: flush more frequently
			afc.adaptiveStep = max(2, feedFollowFlushStep/2)
		case afc.outputRate < lowVolumeRate:
			// Low volume: flush less frequently
			afc.adaptiveStep = min(feedFollowFlushStep*2, feedFlushStep)
		default:
			// Normal volume: use default
			afc.adaptiveStep = feedFollowFlushStep
		}
	} else {
		afc.sampleLineCount += lineCount
	}
}

// shouldFlush determines if a flush should occur based on current conditions
func (afc *adaptiveFlushController) shouldFlush(dirtyLines, bufferSize int, wasEmpty, trimmed bool) bool {
	// Always flush on critical conditions
	if wasEmpty || trimmed {
		return true
	}

	// Adaptive flush based on output rate
	return dirtyLines >= afc.adaptiveStep || bufferSize >= feedBufCap-100
}

// recordFlush records that a flush occurred
func (afc *adaptiveFlushController) recordFlush() {
	afc.lastFlush = time.Now()
}

// Enhanced model with batch processing support
type batchEnabledModel struct {
	model               // Embed the original model
	diagnostics         []feedDiagnostic
	flushController     *adaptiveFlushController
	lastBatchProcess    time.Time
	totalLinesProcessed int64
}

// newBatchEnabledModel creates a model with batch processing capabilities
func newBatchEnabledModel(baseModel model) *batchEnabledModel {
	return &batchEnabledModel{
		model:           baseModel,
		diagnostics:     make([]feedDiagnostic, 0, diagnosticCount),
		flushController: newAdaptiveFlushController(),
	}
}

// handleRunFeedLineBatch processes a batch of lines with enhanced diagnostics
func (bm *batchEnabledModel) handleRunFeedLineBatch(displayLines, rawLines []string) {
	if len(displayLines) == 0 {
		return
	}

	start := time.Now()

	// Update output rate sample
	bm.flushController.updateSample(len(displayLines))

	for i, displayLine := range displayLines {
		rawLine := ""
		if i < len(rawLines) {
			rawLine = rawLines[i]
		}

		// Use the original handleRunFeedLine logic
		bm.handleRunFeedLine(displayLine, rawLine)
	}

	processingTime := time.Since(start)
	bm.lastBatchProcess = time.Now()
	bm.totalLinesProcessed += int64(len(displayLines))

	// Record diagnostic information
	diag := feedDiagnostic{
		timestamp:      time.Now(),
		batchSize:      len(displayLines),
		bufferSize:     len(bm.runFeedBuf),
		dirtyLines:     bm.runFeedDirtyLines,
		processingTime: processingTime,
		outputRate:     bm.flushController.outputRate,
	}

	bm.diagnostics = append(bm.diagnostics, diag)
	if len(bm.diagnostics) > diagnosticCount {
		bm.diagnostics = bm.diagnostics[1:] // Keep only recent diagnostics
	}

	// Check for performance issues
	if processingTime > time.Duration(stallThresholdMs)*time.Millisecond {
		// This could indicate a performance problem
		bm.runFeedAutoFollow = true // Force auto-follow to ensure visibility
	}

	// Record flush with adaptive controller
	if bm.runFeedDirtyLines == 0 { // Flush just occurred
		bm.flushController.recordFlush()
	}
}

// getRecentDiagnostics returns recent performance diagnostics
func (bm *batchEnabledModel) getRecentDiagnostics() []feedDiagnostic {
	return append([]feedDiagnostic(nil), bm.diagnostics...)
}

// Helper functions
func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
