package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/SimoKiihamaki/autodev/internal/api"
)

// Environment variable for configuring the API server bind address (e.g., ":8080" or "localhost:8080")
const EnvAPIAddr = "APRD_API_ADDR"

// getAddr returns the address to bind the server to.
// It reads from the environment variable EnvAPIAddr, falling back to the default.
func getAddr() string {
	addr := os.Getenv(EnvAPIAddr)
	if addr == "" {
		return api.DefaultAPIAddr
	}
	return addr
}

// createServer creates a new API server with the given address.
func createServer(addr string) *api.Server {
	cfg := api.Config{Addr: addr}
	return api.NewServer(cfg, api.Dependencies{})
}

// startServerAsync starts the server in a goroutine and returns an error channel.
// The channel will receive an error if the server fails to start.
func startServerAsync(server *api.Server) chan error {
	errCh := make(chan error, 1)
	go func() {
		log.Printf("starting api server on %s", server.Addr())
		if err := server.Start(); err != nil && err != http.ErrServerClosed {
			log.Printf("server error: %v", err)
			errCh <- err
		}
	}()
	return errCh
}

// waitForSignal blocks until a shutdown signal is received or an error occurs.
// It returns the error if one was received, or nil if signal was received.
func waitForSignal(ctx context.Context, errCh <-chan error) error {
	select {
	case <-ctx.Done():
		// Signal received, proceed to shutdown
		return nil
	case err := <-errCh:
		// Server failed to start
		return err
	}
}

// shutdownServer performs graceful shutdown of the server.
func shutdownServer(server *api.Server) error {
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := server.Shutdown(shutdownCtx); err != nil {
		log.Printf("graceful shutdown failed: %v", err)
		return err
	}

	log.Println("server shutdown complete")
	return nil
}

// runServer starts the server and blocks until it exits or an error occurs.
// It returns the error if the server fails to start, or nil on graceful shutdown.
func runServer(server *api.Server) error {
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	errCh := startServerAsync(server)

	if err := waitForSignal(ctx, errCh); err != nil {
		return err
	}

	return shutdownServer(server)
}

func main() {
	addr := getAddr()
	server := createServer(addr)

	if err := runServer(server); err != nil {
		log.Fatalf("server error: %v", err)
	}
}
