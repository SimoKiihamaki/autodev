package api

import (
	"context"
	"net"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestNewServer(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name       string
		cfg        Config
		wantAddr   string
		wantNotNil bool
	}{
		{
			name:       "default address",
			cfg:        Config{},
			wantAddr:   ":8080",
			wantNotNil: true,
		},
		{
			name:       "custom address",
			cfg:        Config{Addr: ":9090"},
			wantAddr:   ":9090",
			wantNotNil: true,
		},
		{
			name: "with timeouts",
			cfg: Config{
				Addr:         ":8080",
				ReadTimeout:  10 * time.Second,
				WriteTimeout: 5 * time.Second,
				IdleTimeout:  120 * time.Second,
			},
			wantAddr:   ":8080",
			wantNotNil: true,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			srv := NewServer(tc.cfg, Dependencies{})
			if srv == nil && tc.wantNotNil {
				t.Fatal("NewServer() returned nil")
			}
			if srv.Addr() != tc.wantAddr {
				t.Errorf("Addr() = %q, want %q", srv.Addr(), tc.wantAddr)
			}
			if srv.Handler() == nil {
				t.Error("Handler() returned nil")
			}
		})
	}
}

func TestServerAddr(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name string
		cfg  Config
		want string
	}{
		{
			name: "default port",
			cfg:  Config{},
			want: ":8080",
		},
		{
			name: "custom port",
			cfg:  Config{Addr: ":9090"},
			want: ":9090",
		},
		{
			name: "custom address",
			cfg:  Config{Addr: "127.0.0.1:3000"},
			want: "127.0.0.1:3000",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			srv := NewServer(tc.cfg, Dependencies{})
			if got := srv.Addr(); got != tc.want {
				t.Errorf("Addr() = %q, want %q", got, tc.want)
			}
		})
	}
}

func TestServerHandler(t *testing.T) {
	t.Parallel()

	srv := NewServer(Config{}, Dependencies{})
	if srv.Handler() == nil {
		t.Fatal("Handler() returned nil")
	}

	// Verify handler is functional
	req := httptest.NewRequest(http.MethodGet, "/healthz", nil)
	rr := httptest.NewRecorder()

	srv.Handler().ServeHTTP(rr, req)

	if rr.Code != http.StatusOK {
		t.Errorf("Handler() returned status %d, want %d", rr.Code, http.StatusOK)
	}
}

func TestServerLifecycle(t *testing.T) {
	// Can't use t.Parallel() here as we're testing actual server lifecycle

	t.Run("Start and Shutdown", func(t *testing.T) {
		// Use listener to get actual address
		listener, err := net.Listen("tcp", "127.0.0.1:0")
		if err != nil {
			t.Fatalf("Failed to create listener: %v", err)
		}
		addr := listener.Addr().String()

		srv := NewServer(Config{}, Dependencies{})

		// Start server in background with listener
		errCh := make(chan error, 1)
		go func() {
			errCh <- srv.StartListener(listener)
		}()

		// Wait for server to be ready
		time.Sleep(100 * time.Millisecond)

		// Test that server responds
		client := &http.Client{Timeout: 1 * time.Second}
		resp, err := client.Get("http://" + addr + "/healthz")
		if err != nil {
			t.Fatalf("Failed to connect to server: %v", err)
		}
		if resp.StatusCode != http.StatusOK {
			t.Errorf("Health check returned status %d", resp.StatusCode)
		}
		_ = resp.Body.Close() // Ignore error in test

		// Shutdown server
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if err := srv.Shutdown(ctx); err != nil {
			t.Errorf("Shutdown() failed: %v", err)
		}

		// Verify StartListener() returned
		if err := <-errCh; err != nil && err != http.ErrServerClosed {
			t.Errorf("StartListener() returned error: %v", err)
		}
	})
}

func TestServerStartListener(t *testing.T) {
	// Can't use t.Parallel() here as we're testing actual server lifecycle

	t.Run("StartListener with custom listener", func(t *testing.T) {
		srv := NewServer(Config{}, Dependencies{})

		listener, err := net.Listen("tcp", ":0")
		if err != nil {
			t.Fatalf("Failed to create listener: %v", err)
		}
		defer func() { _ = listener.Close() }()

		errCh := make(chan error, 1)
		go func() {
			errCh <- srv.StartListener(listener)
		}()

		time.Sleep(100 * time.Millisecond)

		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if err := srv.Shutdown(ctx); err != nil {
			t.Errorf("Shutdown() failed: %v", err)
		}

		if err := <-errCh; err != nil && err != http.ErrServerClosed {
			t.Errorf("StartListener() returned error: %v", err)
		}
	})
}

func TestChooseDuration(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name      string
		candidate time.Duration
		fallback  time.Duration
		want      time.Duration
	}{
		{
			name:      "positive candidate uses candidate",
			candidate: 10 * time.Second,
			fallback:  5 * time.Second,
			want:      10 * time.Second,
		},
		{
			name:      "zero candidate uses fallback",
			candidate: 0,
			fallback:  5 * time.Second,
			want:      5 * time.Second,
		},
		{
			name:      "negative candidate uses fallback",
			candidate: -5 * time.Second,
			fallback:  5 * time.Second,
			want:      5 * time.Second,
		},
		{
			name:      "zero fallback with zero candidate returns zero",
			candidate: 0,
			fallback:  0,
			want:      0,
		},
		{
			name:      "zero fallback with positive candidate returns candidate",
			candidate: 10 * time.Second,
			fallback:  0,
			want:      10 * time.Second,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			got := chooseDuration(tc.candidate, tc.fallback)
			if got != tc.want {
				t.Errorf("chooseDuration(%v, %v) = %v, want %v",
					tc.candidate, tc.fallback, got, tc.want)
			}
		})
	}
}

func TestServerShutdownContext(t *testing.T) {
	// Can't use t.Parallel() here as we're testing actual server lifecycle

	t.Run("Shutdown with cancelled context", func(t *testing.T) {
		listener, err := net.Listen("tcp", "127.0.0.1:0")
		if err != nil {
			t.Fatalf("Failed to create listener: %v", err)
		}

		srv := NewServer(Config{}, Dependencies{})

		// Start server
		errCh := make(chan error, 1)
		go func() {
			errCh <- srv.StartListener(listener)
		}()

		time.Sleep(100 * time.Millisecond)

		// Shutdown with already-cancelled context
		ctx, cancel := context.WithCancel(context.Background())
		cancel() // Cancel immediately

		_ = srv.Shutdown(ctx)
		// Shutdown with cancelled context may or may not error depending on timing
		// The important thing is that the server stops

		// Clean up with valid context
		ctx2, cancel2 := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel2()
		_ = srv.Shutdown(ctx2) // Ignore error in cleanup
		<-errCh
	})
}
