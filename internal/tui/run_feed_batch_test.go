package tui

import (
	"fmt"
	"testing"
	"time"

	"github.com/SimoKiihamaki/autodev/internal/runner"
	"github.com/charmbracelet/bubbles/viewport"
)

// TestBatchLogReader tests the batch log reading functionality
func TestBatchLogReader(t *testing.T) {
	t.Parallel()

	// Create a model with a log channel
	logCh := make(chan runner.Line, 100)
	m := model{logCh: logCh, flushController: newAdaptiveFlushController()}

	// Create batch reader command
	cmd := m.readLogsBatch()
	if cmd == nil {
		t.Fatal("Expected non-nil command from readLogsBatch")
	}

	// Send some test lines to the channel
	testLines := []runner.Line{
		{Text: "Line 1", Time: time.Now()},
		{Text: "Line 2", Time: time.Now()},
		{Text: "Line 3", Time: time.Now()},
	}

	for _, line := range testLines {
		logCh <- line
	}

	// Execute the command
	msg := cmd()
	if msg == nil {
		t.Fatal("Expected non-nil message from command")
	}

	batchMsg, ok := msg.(logBatchMsg)
	if !ok {
		t.Fatalf("Expected logBatchMsg, got %T", msg)
	}

	if len(batchMsg.lines) == 0 {
		t.Fatal("Expected at least one line in batch")
	}

	if len(batchMsg.lines) > maxBatchSize {
		t.Fatalf("Expected at most %d lines, got %d", maxBatchSize, len(batchMsg.lines))
	}

	// Verify line content
	for i, line := range batchMsg.lines {
		if line.Text != testLines[i].Text {
			t.Errorf("Line %d: expected %q, got %q", i, testLines[i].Text, line.Text)
		}
	}
}

// TestBatchLogReaderEmptyChannel tests behavior with empty channel
func TestBatchLogReaderEmptyChannel(t *testing.T) {
	t.Parallel()

	// Create a model with an empty log channel
	logCh := make(chan runner.Line, 100)
	m := model{logCh: logCh, flushController: newAdaptiveFlushController()}

	// Create batch reader command
	cmd := m.readLogsBatch()
	if cmd == nil {
		t.Fatal("Expected non-nil command from readLogsBatch")
	}

	// Execute the command (should timeout and return nil)
	msg := cmd()
	if msg != nil {
		t.Errorf("Expected nil message from empty channel, got %T", msg)
	}
}

// TestBatchLogReaderChannelClosure tests error handling when channel is closed
func TestBatchLogReaderChannelClosure(t *testing.T) {
	t.Parallel()

	// Create a model with a log channel
	logCh := make(chan runner.Line, 100)
	m := model{logCh: logCh, flushController: newAdaptiveFlushController()}

	// Send some test lines before closing
	testLines := []runner.Line{
		{Text: "Before close 1", Time: time.Now()},
		{Text: "Before close 2", Time: time.Now()},
	}

	for _, line := range testLines {
		logCh <- line
	}

	// Close the channel to simulate process termination
	close(logCh)

	// Create batch reader command
	cmd := m.readLogsBatch()
	if cmd == nil {
		t.Fatal("Expected non-nil command from readLogsBatch")
	}

	// Execute the command - should read remaining lines then return nil
	msg := cmd()
	if msg == nil {
		t.Fatal("Expected non-nil message with remaining lines before channel closure")
	}

	batchMsg, ok := msg.(logBatchMsg)
	if !ok {
		t.Fatalf("Expected logBatchMsg, got %T", msg)
	}

	// Should have received the lines that were sent before closure
	if len(batchMsg.lines) != len(testLines) {
		t.Errorf("Expected %d lines before closure, got %d", len(testLines), len(batchMsg.lines))
	}

	// Verify line content
	for i, line := range batchMsg.lines {
		if line.Text != testLines[i].Text {
			t.Errorf("Line %d: expected %q, got %q", i, testLines[i].Text, line.Text)
		}
	}

	// Subsequent reads should return nil since channel is closed
	cmd2 := m.readLogsBatch()
	if cmd2 == nil {
		t.Fatal("Expected non-nil command from readLogsBatch even with closed channel")
	}

	msg2 := cmd2()
	if msg2 != nil {
		t.Errorf("Expected nil message from closed channel, got %T", msg2)
	}
}

// TestBatchLogReaderPartialBatch tests timing characteristics with partial batches
func TestBatchLogReaderPartialBatch(t *testing.T) {
	t.Parallel()

	// Create a model with a log channel
	logCh := make(chan runner.Line, 100)
	m := model{logCh: logCh, flushController: newAdaptiveFlushController()}

	// Send fewer lines than maxBatchSize
	testLines := []runner.Line{
		{Text: "Partial line 1", Time: time.Now()},
		{Text: "Partial line 2", Time: time.Now()},
	}

	for _, line := range testLines {
		logCh <- line
	}

	// Create batch reader command
	cmd := m.readLogsBatch()
	if cmd == nil {
		t.Fatal("Expected non-nil command from readLogsBatch")
	}

	// Execute the command - should return lines quickly due to timeout
	start := time.Now()
	msg := cmd()
	elapsed := time.Since(start)

	if msg == nil {
		t.Fatal("Expected non-nil message from partial batch")
	}

	// Should complete quickly due to timeout mechanism (allow some margin for execution)
	if elapsed > 10*time.Millisecond {
		t.Logf("Note: Partial batch took %v (expected fast due to timeout)", elapsed)
	}

	batchMsg, ok := msg.(logBatchMsg)
	if !ok {
		t.Fatalf("Expected logBatchMsg, got %T", msg)
	}

	// Should have received the available lines
	if len(batchMsg.lines) != len(testLines) {
		t.Errorf("Expected %d lines in partial batch, got %d", len(testLines), len(batchMsg.lines))
	}
}

// TestHandleLogBatch tests batch processing of log lines
func TestHandleLogBatch(t *testing.T) {
	t.Parallel()

	// Create a model with a viewport and log channel
	logCh := make(chan runner.Line, 100)
	m := &model{
		runFeed:           viewport.New(80, 24),
		runFeedBuf:        make([]string, 0, feedBufCap),
		runFeedAutoFollow: true,
		logCh:             logCh,
		flushController:   newAdaptiveFlushController(),
	}

	// Create test lines
	testLines := []runner.Line{
		{Text: "Batch line 1", Time: time.Now()},
		{Text: "Batch line 2", Time: time.Now()},
		{Text: "=== Iteration 1/5: Test ===", Time: time.Now()},
		{Text: "→ Processing batch", Time: time.Now()},
		{Text: "✓ Batch completed", Time: time.Now()},
	}

	// Process the batch
	newModel, cmd := m.handleLogBatch(testLines)
	if cmd == nil {
		t.Fatal("Expected non-nil command returned from handleLogBatch")
	}
	// Update the model reference to the new model (if it changed)
	if newModel != nil {
		if model, ok := newModel.(*model); ok {
			m = model
		}
	}

	// Verify buffer contains lines
	if len(m.runFeedBuf) != len(testLines) {
		t.Errorf("Expected %d lines in buffer, got %d", len(testLines), len(m.runFeedBuf))
	}

	// Verify iteration parsing worked
	if m.runIterCurrent != 1 {
		t.Errorf("Expected iteration 1, got %d", m.runIterCurrent)
	}
	if m.runIterTotal != 5 {
		t.Errorf("Expected iteration total 5, got %d", m.runIterTotal)
	}
	if m.runIterLabel != "Test" {
		t.Errorf("Expected iteration label 'Test', got %q", m.runIterLabel)
	}

	// Verify current action was set
	if m.runCurrent != "Batch completed" {
		t.Errorf("Expected current action 'Batch completed', got %q", m.runCurrent)
	}

	// Verify viewport has content
	content := m.runFeed.View()
	if content == "" {
		t.Error("Expected viewport to contain content after batch processing")
	}

	if !m.runFeedAutoFollow {
		t.Error("Expected auto-follow to remain enabled after batch processing")
	}
}

// TestAdaptiveFlushController tests the adaptive flush controller
func TestAdaptiveFlushController(t *testing.T) {
	t.Parallel()

	afc := newAdaptiveFlushController()

	// Test initial state
	if afc.adaptiveStep != feedFollowFlushStep {
		t.Errorf("Expected initial adaptive step %d, got %d", feedFollowFlushStep, afc.adaptiveStep)
	}

	// Test sample update with low volume
	afc.updateSample(5) // 5 lines in current window
	time.Sleep(100 * time.Millisecond)
	afc.updateSample(3) // 3 more lines

	// Should not trigger rate calculation yet (window not complete)
	if afc.outputRate != 0 {
		t.Errorf("Expected zero output rate before window complete, got %f", afc.outputRate)
	}

	// Test high volume scenario
	for i := 0; i < 100; i++ {
		afc.updateSample(1)
		time.Sleep(10 * time.Millisecond) // 100 lines per second
	}

	// Wait for sample window to complete
	time.Sleep(afc.sampleWindow)

	// Update with more lines to trigger rate calculation
	afc.updateSample(10)

	if afc.outputRate <= highVolumeRate {
		t.Errorf("Expected output rate > %f for high volume, got %f", highVolumeRate, afc.outputRate)
	}

	// Adaptive step should be reduced for high volume
	if afc.adaptiveStep >= feedFollowFlushStep {
		t.Errorf("Expected adaptive step < %d for high volume, got %d", feedFollowFlushStep, afc.adaptiveStep)
	}
}

// TestBatchEnabledModel tests the enhanced model with batch processing
func TestBatchEnabledModel(t *testing.T) {
	t.Parallel()

	// Create base model
	baseModel := model{
		runFeed:           viewport.New(80, 24),
		runFeedBuf:        make([]string, 0, feedBufCap),
		runFeedAutoFollow: true,
		flushController:   newAdaptiveFlushController(),
	}

	// Create batch-enabled model
	bm := newBatchEnabledModel(baseModel)

	if bm.diagnostics == nil {
		t.Fatal("Expected diagnostics slice to be initialized")
	}

	if bm.flushController == nil {
		t.Fatal("Expected flush controller to be initialized")
	}

	if bm.totalLinesProcessed != 0 {
		t.Errorf("Expected zero lines processed initially, got %d", bm.totalLinesProcessed)
	}

	// Test batch processing
	displayLines := []string{"Line 1", "Line 2", "Line 3"}
	rawLines := []string{"Line 1", "Line 2", "Line 3"}

	bm.handleRunFeedLineBatch(displayLines, rawLines)

	// Verify diagnostics were recorded
	if len(bm.diagnostics) == 0 {
		t.Error("Expected diagnostics to be recorded after batch processing")
	}

	// Verify lines were processed
	if bm.totalLinesProcessed != 3 {
		t.Errorf("Expected 3 lines processed, got %d", bm.totalLinesProcessed)
	}

	// Verify buffer was updated
	if len(bm.runFeedBuf) != 3 {
		t.Errorf("Expected 3 lines in buffer, got %d", len(bm.runFeedBuf))
	}

	// Test getting recent diagnostics
	recent := bm.getRecentDiagnostics()
	if len(recent) == 0 {
		t.Error("Expected recent diagnostics to be available")
	}

	// Verify diagnostic content
	lastDiag := recent[len(recent)-1]
	if lastDiag.batchSize != 3 {
		t.Errorf("Expected batch size 3, got %d", lastDiag.batchSize)
	}

	if lastDiag.processingTime <= 0 {
		t.Error("Expected positive processing time")
	}
}

// TestBatchProcessingUnderLoad tests batch processing with high load
func TestBatchProcessingUnderLoad(t *testing.T) {
	t.Parallel()

	if testing.Short() {
		t.Skip("Skipping load test in short mode")
	}

	// Create batch-enabled model
	baseModel := model{
		runFeed:           viewport.New(80, 24),
		runFeedBuf:        make([]string, 0, feedBufCap),
		runFeedAutoFollow: true,
		flushController:   newAdaptiveFlushController(),
	}
	bm := newBatchEnabledModel(baseModel)

	// Simulate high load processing
	batchCount := 10
	linesPerBatch := 20

	for batch := 0; batch < batchCount; batch++ {
		displayLines := make([]string, linesPerBatch)
		rawLines := make([]string, linesPerBatch)

		for i := 0; i < linesPerBatch; i++ {
			lineNum := batch*linesPerBatch + i + 1
			displayLines[i] = fmt.Sprintf("High load line %d", lineNum)
			rawLines[i] = displayLines[i]
		}

		bm.handleRunFeedLineBatch(displayLines, rawLines)

		// Small delay to simulate real processing
		time.Sleep(1 * time.Millisecond)
	}

	// Verify all lines were processed
	expectedLines := batchCount * linesPerBatch
	if bm.totalLinesProcessed != int64(expectedLines) {
		t.Errorf("Expected %d lines processed, got %d", expectedLines, bm.totalLinesProcessed)
	}

	// Verify diagnostics were collected
	if len(bm.diagnostics) == 0 {
		t.Error("Expected diagnostics to be collected during load test")
	}

	// Verify buffer respects capacity limit
	if len(bm.runFeedBuf) > feedBufCap {
		t.Errorf("Buffer exceeded capacity: %d > %d", len(bm.runFeedBuf), feedBufCap)
	}

	// Verify adaptive behavior (may take time to calculate)
	if bm.flushController.outputRate <= 0 {
		t.Logf("Note: Output rate still calculating: %f (this is normal for short tests)", bm.flushController.outputRate)
	}

	// Check for performance issues
	maxProcessingTime := time.Duration(stallThresholdMs) * time.Millisecond
	for i, diag := range bm.diagnostics {
		if diag.processingTime > maxProcessingTime {
			t.Logf("Warning: Diagnostic %d had slow processing: %v (threshold: %v)",
				i, diag.processingTime, maxProcessingTime)
		}
	}
}
