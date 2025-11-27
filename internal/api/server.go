package api

import (
	"context"
	"net"
	"net/http"
	"time"
)

// DefaultAPIAddr is the default address the API server binds to.
const DefaultAPIAddr = ":8080"

// Config controls the HTTP server behaviour.
type Config struct {
	Addr         string
	ReadTimeout  time.Duration
	WriteTimeout time.Duration
	IdleTimeout  time.Duration
}

// Dependencies enumerates the collaborators required by the router.
type Dependencies struct{}

// Server wraps the configured HTTP server instance.
type Server struct {
	cfg        Config
	httpServer *http.Server
}

// NewServer constructs a server using the supplied configuration and dependencies.
func NewServer(cfg Config, deps Dependencies) *Server {
	if cfg.Addr == "" {
		cfg.Addr = DefaultAPIAddr
	}

	handler := newRouter(deps)

	srv := &http.Server{
		Addr:         cfg.Addr,
		Handler:      handler,
		ReadTimeout:  chooseDuration(cfg.ReadTimeout, 5*time.Second),
		WriteTimeout: chooseDuration(cfg.WriteTimeout, 5*time.Second),
		IdleTimeout:  chooseDuration(cfg.IdleTimeout, 60*time.Second),
	}

	return &Server{cfg: cfg, httpServer: srv}
}

// Start launches the HTTP server using ListenAndServe.
func (s *Server) Start() error {
	return s.httpServer.ListenAndServe()
}

// StartListener serves HTTP traffic on an explicit listener.
func (s *Server) StartListener(l net.Listener) error {
	return s.httpServer.Serve(l)
}

// Shutdown gracefully terminates the server.
func (s *Server) Shutdown(ctx context.Context) error {
	return s.httpServer.Shutdown(ctx)
}

// Addr returns the configured bind address.
func (s *Server) Addr() string {
	return s.httpServer.Addr
}

// Handler exposes the underlying router for testing.
func (s *Server) Handler() http.Handler {
	return s.httpServer.Handler
}

func chooseDuration(candidate, fallback time.Duration) time.Duration {
	if candidate <= 0 {
		return fallback
	}
	return candidate
}
