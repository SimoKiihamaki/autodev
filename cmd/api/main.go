package main

import (
	"context"
	"log"
	"net/http"
	"os/signal"
	"syscall"
	"time"

	"github.com/SimoKiihamaki/autodev/internal/api"
)

func main() {
	cfg := api.Config{Addr: ":8080"}

	// Initialize config with JWT secret
	apiConfig, err := api.NewUserConfig()
	if err != nil {
		log.Fatalf("Failed to initialize API config: %v", err)
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	deps := api.Dependencies{
		UserRepo:     api.NewInMemoryUserRepository(nil, apiConfig),
		ResourceRepo: api.NewInMemoryResourceRepository(),
		RateLimiter:  api.NewRateLimiter(60, 10), // 60 requests per minute, burst of 10
	}

	// Start rate limiter cleanup routine
	deps.RateLimiter.CleanupRoutine(ctx, 5*time.Minute)

	server := api.NewServer(cfg, deps)

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
