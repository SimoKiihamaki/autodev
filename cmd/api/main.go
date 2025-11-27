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

	go func() {
		log.Printf("starting api server on %s", server.Addr())
		if err := server.Start(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("server error: %v", err)
		}
	}()

	<-ctx.Done()

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := server.Shutdown(shutdownCtx); err != nil {
		log.Fatalf("graceful shutdown failed: %v", err)
	}

	log.Println("server shutdown complete")
}
