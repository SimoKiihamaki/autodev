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

func main() {
	addr := os.Getenv(EnvAPIAddr)
	if addr == "" {
		addr = api.DefaultAPIAddr
	}
	cfg := api.Config{Addr: addr}
	server := api.NewServer(cfg, api.Dependencies{})

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	// Error channel for server start failures
	errCh := make(chan error, 1)

	go func() {
		log.Printf("starting api server on %s", server.Addr())
		if err := server.Start(); err != nil && err != http.ErrServerClosed {
			log.Printf("server error: %v", err)
			errCh <- err
		}
	}()

	// Wait for signal or server error
	select {
	case <-ctx.Done():
		// Signal received, proceed to shutdown
	case err := <-errCh:
		// Server failed to start
		log.Fatalf("server startup failed: %v", err)
	}

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := server.Shutdown(shutdownCtx); err != nil {
		log.Printf("graceful shutdown failed: %v", err)
		os.Exit(1)
	}

	log.Println("server shutdown complete")
}
