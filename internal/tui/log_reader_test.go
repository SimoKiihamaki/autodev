package tui

import (
	"testing"
	"time"

	"github.com/SimoKiihamaki/autodev/internal/config"
	"github.com/SimoKiihamaki/autodev/internal/runner"
)

func TestReadLogsBatchBlocksUntilFirstLine(t *testing.T) {
	t.Parallel()

	cfg := config.Defaults()
	cfg.BatchProcessing.MaxBatchSize = 3

	logCh := make(chan runner.Line, 8)
	m := model{cfg: cfg, logCh: logCh}

	cmd := m.readLogsBatch()
	if cmd == nil {
		t.Fatal("expected command from readLogsBatch")
	}

	result := make(chan interface{}, 1)
	go func() {
		result <- cmd()
	}()

	select {
	case msg := <-result:
		t.Fatalf("expected command to block, got %T", msg)
	case <-time.After(10 * time.Millisecond):
		// command is still waiting for the first line as expected
	}

	want := runner.Line{Text: "first", Time: time.Now()}
	logCh <- want

	select {
	case msg := <-result:
		batch, ok := msg.(logBatchMsg)
		if !ok {
			t.Fatalf("expected logBatchMsg, got %T", msg)
		}
		if batch.closed {
			t.Fatalf("unexpected closed batch: %+v", batch)
		}
		if len(batch.lines) != 1 || batch.lines[0].Text != want.Text {
			t.Fatalf("unexpected batch lines: %+v", batch.lines)
		}
	case <-time.After(100 * time.Millisecond):
		t.Fatal("command did not return after first line")
	}
}

func TestReadLogsBatchDrainsUpToBatchSize(t *testing.T) {
	t.Parallel()

	cfg := config.Defaults()
	cfg.BatchProcessing.MaxBatchSize = 2

	logCh := make(chan runner.Line, 8)
	m := model{cfg: cfg, logCh: logCh}

	lines := []runner.Line{
		{Text: "one", Time: time.Now()},
		{Text: "two", Time: time.Now()},
		{Text: "three", Time: time.Now()},
	}
	for _, line := range lines {
		logCh <- line
	}

	cmd := m.readLogsBatch()
	if cmd == nil {
		t.Fatal("expected command from readLogsBatch")
	}
	msg := cmd()
	batch, ok := msg.(logBatchMsg)
	if !ok {
		t.Fatalf("expected logBatchMsg, got %T", msg)
	}
	if batch.closed {
		t.Fatalf("unexpected closed batch")
	}
	if len(batch.lines) != cfg.BatchProcessing.MaxBatchSize {
		t.Fatalf("batch size=%d, want %d", len(batch.lines), cfg.BatchProcessing.MaxBatchSize)
	}

	cmd = m.readLogsBatch()
	if cmd == nil {
		t.Fatal("expected command from readLogsBatch")
	}
	msg = cmd()
	batch, ok = msg.(logBatchMsg)
	if !ok {
		t.Fatalf("expected logBatchMsg, got %T", msg)
	}
	if batch.closed {
		t.Fatalf("unexpected closed batch on remaining data")
	}
	if len(batch.lines) != 1 || batch.lines[0].Text != "three" {
		t.Fatalf("unexpected remainder batch: %+v", batch.lines)
	}
}

func TestReadLogsBatchHandlesChannelClosure(t *testing.T) {
	t.Parallel()

	cfg := config.Defaults()
	cfg.BatchProcessing.MaxBatchSize = 4

	// Case 1: channel closed before any data
	emptyCh := make(chan runner.Line)
	close(emptyCh)
	m := model{cfg: cfg, logCh: emptyCh}

	cmd := m.readLogsBatch()
	if cmd == nil {
		t.Fatal("expected command even when channel closed")
	}
	msg := cmd()
	batch, ok := msg.(logBatchMsg)
	if !ok {
		t.Fatalf("expected logBatchMsg, got %T", msg)
	}
	if !batch.closed || len(batch.lines) != 0 {
		t.Fatalf("expected closed empty batch, got %+v", batch)
	}

	// Case 2: channel closes after emitting data
	closedCh := make(chan runner.Line, 2)
	closedCh <- runner.Line{Text: "line1", Time: time.Now()}
	closedCh <- runner.Line{Text: "line2", Time: time.Now()}
	close(closedCh)

	m2 := model{cfg: cfg, logCh: closedCh}
	cmd = m2.readLogsBatch()
	msg = cmd()
	batch, ok = msg.(logBatchMsg)
	if !ok {
		t.Fatalf("expected logBatchMsg, got %T", msg)
	}
	if !batch.closed {
		t.Fatal("expected closed flag to be true")
	}
	if len(batch.lines) != 2 {
		t.Fatalf("expected 2 lines before closure, got %d", len(batch.lines))
	}
}
