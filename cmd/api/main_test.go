package main

import (
	"context"
	"net/http"
	"testing"
	"time"

	"github.com/SimoKiihamaki/autodev/internal/api"
)

// TestMain_NewServer verifies server initialization.
func TestMain_NewServer(t *testing.T) {
	cfg := api.Config{Addr: ":0"} // Use :0 for random available port

	server := api.NewServer(cfg, api.Dependencies{})
	if server == nil {
		t.Fatal("NewServer returned nil")
	}

	if server.Addr() != ":0" {
		t.Errorf("unexpected server addr: %s", server.Addr())
	}
}

// TestMain_ServerStart verifies server starts without error.
func TestMain_ServerStart(t *testing.T) {
	cfg := api.Config{Addr: ":0"}
	server := api.NewServer(cfg, api.Dependencies{})

	// Start server in goroutine
	serverErr := make(chan error, 1)
	go func() {
		if err := server.Start(); err != nil && err != http.ErrServerClosed {
			serverErr <- err
		}
	}()

	// Ensure server is shut down after test
	defer func() {
		ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
		defer cancel()
		if err := server.Shutdown(ctx); err != nil {
			t.Logf("shutdown error: %v", err)
		}
	}()

	// Wait a bit for server to start
	time.Sleep(50 * time.Millisecond)

	select {
	case err := <-serverErr:
		t.Fatalf("server start failed: %v", err)
	default:
		// Server started successfully
	}
}

// TestMain_ShutdownContext verifies graceful shutdown.
func TestMain_ShutdownContext(t *testing.T) {
	cfg := api.Config{Addr: ":0"}
	server := api.NewServer(cfg, api.Dependencies{})

	serverErr := make(chan error, 1)
	go func() {
		serverErr <- server.Start()
	}()

	// Wait for server to start
	time.Sleep(50 * time.Millisecond)

	if err := server.Shutdown(context.Background()); err != nil {
		t.Logf("shutdown error (expected during test): %v", err)
	}

	// Wait for server goroutine to finish
	select {
	case err := <-serverErr:
		if err != nil && err != http.ErrServerClosed {
			t.Errorf("unexpected server error: %v", err)
		}
	case <-time.After(1 * time.Second):
		t.Error("server did not shut down within timeout")
	}
}
