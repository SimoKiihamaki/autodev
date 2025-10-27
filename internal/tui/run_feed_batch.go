package tui

import (
	"time"
)

// max returns the maximum of two integers
func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}

// min returns the minimum of two integers
func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

// Constants for batch processing
const (
	minAdaptiveFlushStep = 2    // Minimum flush threshold for high-volume scenarios
	highVolumeRate       = 10.0 // Lines per second considered high volume
	lowVolumeRate        = 2.0  // Lines per second considered low volume
	diagnosticCount      = 50   // Number of recent diagnostics to keep
	stallThresholdMs     = 100  // Processing time threshold for stall detection
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
			afc.adaptiveStep = max(minAdaptiveFlushStep, feedFollowFlushStep/2)
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

// handleRunFeedLineBatch processes a batch of lines with adaptive flush control
func (m *model) handleRunFeedLineBatch(displayLines, rawLines []string) {
	if len(displayLines) == 0 {
		return
	}

	// Update output rate sample for adaptive flush control
	m.flushController.updateSample(len(displayLines))

	for i, displayLine := range displayLines {
		rawLine := ""
		if i < len(rawLines) {
			rawLine = rawLines[i]
		}

		// Use the original handleRunFeedLine logic
		m.handleRunFeedLine(displayLine, rawLine)
	}

	// Record flush with adaptive controller if flush just occurred
	if m.runFeedDirtyLines == 0 { // Flush just occurred
		m.flushController.recordFlush()
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
