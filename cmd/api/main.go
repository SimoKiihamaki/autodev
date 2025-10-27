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
	deps := api.Dependencies{
		UserRepo: api.NewInMemoryUserRepository(nil),
	}
	server := api.NewServer(cfg, deps)

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
