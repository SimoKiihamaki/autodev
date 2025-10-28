package tui

import (
	"context"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/SimoKiihamaki/autodev/internal/config"
	"github.com/SimoKiihamaki/autodev/internal/runner"
	"github.com/charmbracelet/bubbles/viewport"
)

func TestRunnerIntegrationLiveFeed(t *testing.T) {
	t.Parallel()

	tempDir := t.TempDir()
	scriptPath := filepath.Join(tempDir, "emit.py")
	logFile := filepath.Join(tempDir, "run.log")
	prdPath := filepath.Join(tempDir, "dummy.md")

	script := `import argparse, time

parser = argparse.ArgumentParser()
parser.add_argument("--log-level")
parser.add_argument("--prd")
parser.add_argument("--phases")
parser.add_argument("--executor-policy")
parser.add_argument("--codex-model")
parser.add_argument("--base")
parser.add_argument("--repo")
parser.add_argument("--branch")
parser.parse_known_args()

for i in range(10):
    print(f"line {i+1}", flush=True)
    time.sleep(0.05)
`

	if err := os.WriteFile(scriptPath, []byte(script), 0o644); err != nil {
		t.Fatalf("write script: %v", err)
	}
	if err := os.WriteFile(prdPath, []byte("# dummy"), 0o644); err != nil {
		t.Fatalf("write prd: %v", err)
	}

	cfg := config.Defaults()
	cfg.PythonScript = scriptPath
	cfg.BaseBranch = ""
	cfg.Branch = ""
	cfg.CodexModel = ""
	cfg.ExecutorPolicy = ""
	cfg.RunPhases = config.Phases{}
	cfg.LogLevel = ""

	logCh := make(chan runner.Line, 2048)

	opts := runner.Options{
		Config:      cfg,
		PRDPath:     prdPath,
		Logs:        logCh,
		LogFilePath: logFile,
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	errCh := make(chan error, 1)
	go func() {
		errCh <- opts.Run(ctx)
	}()

	m := model{
		cfg:               cfg,
		logCh:             logCh,
		logs:              viewport.New(80, 24),
		runFeed:           viewport.New(80, 24),
		runFeedBuf:        make([]string, 0, feedBufCap),
		runFeedAutoFollow: true,
	}

	totalLines := 0
	deadline := time.NewTimer(5 * time.Second)
	defer deadline.Stop()

	for {
		cmd := m.readLogsBatch()
		if cmd == nil {
			t.Fatal("readLogsBatch returned nil")
		}

		type anyMsg = interface{}
		msgCh := make(chan anyMsg, 1)
		go func() { msgCh <- cmd() }()
		select {
		case <-deadline.C:
			t.Fatal("timed out waiting for log batches")
		case raw := <-msgCh:
			batch, ok := raw.(logBatchMsg)
			if !ok {
				t.Fatalf("unexpected message type: %T", raw)
			}
			totalLines += len(batch.lines)
			m.handleLogBatch(batch)
			if batch.closed {
				break
			}
		}

		if totalLines >= 10 {
			// Exit early if we've collected enough lines
			break
		}
	}

	if err := <-errCh; err != nil {
		t.Fatalf("runner returned error: %v", err)
	}

	if totalLines < 10 {
		t.Fatalf("expected at least 10 lines, got %d", totalLines)
	}
	if len(m.logBuf) < totalLines {
		t.Fatalf("log buffer stored %d lines, want %d", len(m.logBuf), totalLines)
	}
	if len(m.runFeedBuf) == 0 {
		t.Fatal("run feed buffer should not be empty")
	}
}
