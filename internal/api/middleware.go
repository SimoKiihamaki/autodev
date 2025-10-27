package api

import (
	"context"
	"net"
	"net/http"
	"sync"
	"time"
)

// Rate limiting constants
const (
	SecondsPerMinute        = 60.0
	CleanupWindowMultiplier = 5
	DefaultCleanupInterval  = 5 * time.Minute
	// Default rate limit settings
	DefaultRequestsPerMinute = 60
	DefaultBurstSize         = 10
)

// RateLimiter implements a simple token bucket rate limiter
type RateLimiter struct {
	clients map[string]*ClientLimiter
	mu      sync.RWMutex
	rate    int           // requests per minute
	burst   int           // maximum burst size
	window  time.Duration // time window for rate limiting
}

// ClientLimiter tracks rate limits for a specific client
type ClientLimiter struct {
	tokens   int
	lastSeen time.Time
	mu       sync.Mutex
}

// NewRateLimiter creates a new rate limiter with the specified rate and burst
func NewRateLimiter(requestsPerMinute, burst int) *RateLimiter {
	return &RateLimiter{
		clients: make(map[string]*ClientLimiter),
		rate:    requestsPerMinute,
		burst:   burst,
		window:  time.Minute,
	}
}

// getClientIP extracts the real client IP from the request.
func getClientIP(r *http.Request) string {
	clientIP := r.RemoteAddr
	if host, _, err := net.SplitHostPort(clientIP); err == nil && host != "" {
		clientIP = host
	}

	// Do not trust X-Forwarded-For or X-Real-IP headers unless behind trusted proxies.
	// See https://github.com/golang/go/issues/38678 for discussion.
	return clientIP
}

// RateLimit middleware implements rate limiting based on client IP
func (rl *RateLimiter) RateLimit(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		clientIP := getClientIP(r)

		if !rl.allowRequest(clientIP) {
			writeError(w, http.StatusTooManyRequests, "rate limit exceeded")
			return
		}

		next.ServeHTTP(w, r)
	})
}

// allowRequest checks if a request from the given client should be allowed
func (rl *RateLimiter) allowRequest(clientIP string) bool {
	rl.mu.RLock()
	limiter, exists := rl.clients[clientIP]
	rl.mu.RUnlock()

	if !exists {
		rl.mu.Lock()
		// Double-check after acquiring write lock
		limiter, exists = rl.clients[clientIP]
		if !exists {
			limiter = &ClientLimiter{
				tokens:   rl.burst,
				lastSeen: time.Now(),
			}
			rl.clients[clientIP] = limiter
		}
		rl.mu.Unlock()
	}

	limiter.mu.Lock()
	defer limiter.mu.Unlock()

	now := time.Now()
	elapsed := now.Sub(limiter.lastSeen)

	// Add tokens based on elapsed time
	tokensToAdd := int(elapsed.Seconds() * float64(rl.rate) / SecondsPerMinute)
	if tokensToAdd > 0 {
		limiter.tokens += tokensToAdd
		if limiter.tokens > rl.burst {
			limiter.tokens = rl.burst
		}
	}

	limiter.lastSeen = now

	if limiter.tokens > 0 {
		limiter.tokens--
		return true
	}

	return false
}

// Cleanup removes old entries from the rate limiter map
func (rl *RateLimiter) Cleanup() {
	// First, collect IPs to delete without holding rl.mu and limiter.mu at the same time
	var toDelete []string
	rl.mu.RLock()
	for ip, limiter := range rl.clients {
		limiter.mu.Lock()
		if time.Since(limiter.lastSeen) > rl.window*CleanupWindowMultiplier { // Remove after cleanup window multiplier of inactivity
			toDelete = append(toDelete, ip)
		}
		limiter.mu.Unlock()
	}
	rl.mu.RUnlock()

	// Now, delete the collected IPs under write lock
	if len(toDelete) > 0 {
		rl.mu.Lock()
		for _, ip := range toDelete {
			delete(rl.clients, ip)
		}
		rl.mu.Unlock()
	}
}

// CleanupRoutine runs cleanup periodically and can be cancelled via context
func (rl *RateLimiter) CleanupRoutine(ctx context.Context, interval time.Duration) {
	ticker := time.NewTicker(interval)
	go func() {
		defer ticker.Stop()
		for {
			select {
			case <-ticker.C:
				rl.Cleanup()
			case <-ctx.Done():
				// Context cancelled, exit the goroutine
				return
			}
		}
	}()
}
