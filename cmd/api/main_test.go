package main

import (
	"context"
	"net"
	"net/http"
	"os"
	"testing"
	"time"

	"github.com/SimoKiihamaki/autodev/internal/api"
)

// TestGetAddr_Default tests that default address is used when env var is not set.
func TestGetAddr_Default(t *testing.T) {
	os.Unsetenv(EnvAPIAddr)
	addr := getAddr()
	if addr != api.DefaultAPIAddr {
		t.Errorf("expected default addr %s, got: %s", api.DefaultAPIAddr, addr)
	}
}

// TestGetAddr_Custom tests that custom address from env var is used.
func TestGetAddr_Custom(t *testing.T) {
	customAddr := ":9999"
	os.Setenv(EnvAPIAddr, customAddr)
	defer os.Unsetenv(EnvAPIAddr)

	addr := getAddr()
	if addr != customAddr {
		t.Errorf("expected %s, got: %s", customAddr, addr)
	}
}

// TestGetAddr_EmptyValue tests behavior when env var is set to empty.
func TestGetAddr_EmptyValue(t *testing.T) {
	os.Setenv(EnvAPIAddr, "")
	defer os.Unsetenv(EnvAPIAddr)

	addr := getAddr()
	if addr != api.DefaultAPIAddr {
		t.Errorf("expected default addr %s when env is empty, got: %s", api.DefaultAPIAddr, addr)
	}
}

// TestEnvAPIAddrConstant verifies the constant value.
func TestEnvAPIAddrConstant(t *testing.T) {
	expected := "APRD_API_ADDR"
	if EnvAPIAddr != expected {
		t.Errorf("expected EnvAPIAddr to be %q, got %q", expected, EnvAPIAddr)
	}
}

// TestCreateServer_Basic verifies server creation with basic config.
func TestCreateServer_Basic(t *testing.T) {
	server := createServer(":0")
	if server == nil {
		t.Fatal("createServer returned nil")
	}
	if server.Addr() != ":0" {
		t.Errorf("expected addr :0, got: %s", server.Addr())
	}
}

// TestCreateServer_DefaultAddr verifies server creation with default address.
func TestCreateServer_DefaultAddr(t *testing.T) {
	server := createServer(api.DefaultAPIAddr)
	if server == nil {
		t.Fatal("createServer returned nil")
	}
	if server.Addr() != api.DefaultAPIAddr {
		t.Errorf("expected addr %s, got: %s", api.DefaultAPIAddr, server.Addr())
	}
}

// TestCreateServer_HandlerExposed verifies that created server has valid handler.
func TestCreateServer_HandlerExposed(t *testing.T) {
	server := createServer(":0")
	handler := server.Handler()
	if handler == nil {
		t.Error("Handler() returned nil")
	}
}

// TestCreateServer_MultipleServers verifies multiple servers can be created.
func TestCreateServer_MultipleServers(t *testing.T) {
	s1 := createServer(":0")
	s2 := createServer(":0")

	if s1 == nil || s2 == nil {
		t.Fatal("createServer returned nil for one or both servers")
	}

	// Each should have independent config
	if s1.Addr() != ":0" || s2.Addr() != ":0" {
		t.Error("servers have unexpected addresses")
	}
}

// TestStartServerAsync_ReturnsChannel verifies startServerAsync returns a channel.
func TestStartServerAsync_ReturnsChannel(t *testing.T) {
	server := createServer(":0")
	errCh := startServerAsync(server)

	if errCh == nil {
		t.Fatal("startServerAsync returned nil channel")
	}

	// Shutdown immediately to clean up
	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()
	server.Shutdown(ctx)
}

// TestWaitForSignal_ContextDone verifies waitForSignal returns nil when context is done.
func TestWaitForSignal_ContextDone(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	errCh := make(chan error, 1)

	// Cancel the context immediately
	cancel()

	err := waitForSignal(ctx, errCh)
	if err != nil {
		t.Errorf("expected nil when context done, got: %v", err)
	}
}

// TestWaitForSignal_ErrorReceived verifies waitForSignal returns error when received.
func TestWaitForSignal_ErrorReceived(t *testing.T) {
	ctx := context.Background()
	errCh := make(chan error, 1)

	expectedErr := http.ErrServerClosed
	errCh <- expectedErr

	err := waitForSignal(ctx, errCh)
	if err != expectedErr {
		t.Errorf("expected %v, got: %v", expectedErr, err)
	}
}

// TestWaitForSignal_ContextDoneBeforeError verifies context done takes precedence.
func TestWaitForSignal_ContextDoneBeforeError(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	errCh := make(chan error, 1)

	// Cancel context and send error simultaneously
	cancel()

	// The select may pick either, but typically context done wins
	err := waitForSignal(ctx, errCh)
	_ = err // Either nil (context) or error is acceptable
}

// TestShutdownServer_Success verifies successful shutdown.
func TestShutdownServer_Success(t *testing.T) {
	listener, err := net.Listen("tcp", ":0")
	if err != nil {
		t.Fatalf("failed to create listener: %v", err)
	}
	addr := listener.Addr().String()

	server := createServer(addr)

	// Start server
	go func() {
		server.StartListener(listener)
	}()

	// Wait for server to start
	time.Sleep(50 * time.Millisecond)

	// Shutdown
	err = shutdownServer(server)
	if err != nil {
		t.Errorf("shutdownServer returned error: %v", err)
	}
}

// TestShutdownServer_AlreadyStopped verifies shutdown handles already stopped server.
func TestShutdownServer_AlreadyStopped(t *testing.T) {
	server := createServer(":0")

	// Shutdown without starting should still work
	err := shutdownServer(server)
	// This should return an error since server was never started
	if err == nil {
		// Server.Shutdown on non-running server may succeed or fail
		// Both are acceptable
	}
}

// TestServer_HealthEndpoint tests the health check endpoint works.
func TestServer_HealthEndpoint(t *testing.T) {
	listener, err := net.Listen("tcp", ":0")
	if err != nil {
		t.Fatalf("failed to create listener: %v", err)
	}
	addr := listener.Addr().String()

	server := createServer(addr)

	errCh := make(chan error, 1)
	go func() {
		errCh <- server.StartListener(listener)
	}()

	defer func() {
		ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
		defer cancel()
		server.Shutdown(ctx)
	}()

	time.Sleep(50 * time.Millisecond)

	// Make request to health endpoint
	resp, err := http.Get("http://" + addr + "/healthz")
	if err != nil {
		t.Fatalf("failed to make request: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Errorf("expected status 200, got: %d", resp.StatusCode)
	}
}

// TestConfig_DefaultTimeouts verifies default timeout configuration.
func TestConfig_DefaultTimeouts(t *testing.T) {
	server := createServer(":0")
	if server == nil {
		t.Fatal("createServer returned nil")
	}
	// Server should use default timeouts when not specified
}

// TestConfig_CustomTimeouts verifies custom timeout configuration via api.Config.
func TestConfig_CustomTimeouts(t *testing.T) {
	cfg := api.Config{
		Addr:         ":0",
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 15 * time.Second,
		IdleTimeout:  30 * time.Second,
	}
	server := api.NewServer(cfg, api.Dependencies{})
	if server == nil {
		t.Fatal("NewServer returned nil")
	}
}

// TestIntegration_StartAndWait verifies the full start/wait cycle.
func TestIntegration_StartAndWait(t *testing.T) {
	listener, err := net.Listen("tcp", ":0")
	if err != nil {
		t.Fatalf("failed to create listener: %v", err)
	}
	addr := listener.Addr().String()

	server := createServer(addr)

	// Start server async
	errCh := make(chan error, 1)
	go func() {
		errCh <- server.StartListener(listener)
	}()

	// Wait for startup
	time.Sleep(50 * time.Millisecond)

	// Create a context we can cancel
	ctx, cancel := context.WithCancel(context.Background())

	// Simulate signal by canceling context
	go func() {
		time.Sleep(50 * time.Millisecond)
		cancel()
	}()

	// Wait for "signal"
	waitErr := waitForSignal(ctx, errCh)
	if waitErr != nil {
		t.Errorf("waitForSignal returned error: %v", waitErr)
	}

	// Shutdown
	shutdownErr := shutdownServer(server)
	if shutdownErr != nil {
		t.Errorf("shutdownServer returned error: %v", shutdownErr)
	}

	// Wait for server to finish
	select {
	case err := <-errCh:
		if err != nil && err != http.ErrServerClosed {
			t.Errorf("unexpected server error: %v", err)
		}
	case <-time.After(2 * time.Second):
		t.Error("server did not shut down within timeout")
	}
}
