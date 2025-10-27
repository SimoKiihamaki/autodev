package api

import (
	"context"
	"net/http"
	"strings"
	"sync"
	"time"
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

// getClientIP extracts the real client IP from request headers, considering trusted proxies
func getClientIP(r *http.Request) string {
	// Start with the direct connection IP
	clientIP := r.RemoteAddr

	// Check X-Forwarded-For header first (can contain multiple IPs, leftmost is original client)
	if forwarded := r.Header.Get("X-Forwarded-For"); forwarded != "" {
		// Split on commas and trim whitespace, then take the first (leftmost) IP
		ips := strings.Split(forwarded, ",")
		if len(ips) > 0 {
			leftmostIP := strings.TrimSpace(ips[0])
			if leftmostIP != "" {
				clientIP = leftmostIP
			}
		}
	} else if realIP := r.Header.Get("X-Real-IP"); realIP != "" {
		// Fall back to X-Real-IP if X-Forwarded-For is not present
		clientIP = strings.TrimSpace(realIP)
	}

	// Note: In production, you should validate the IP format and maintain a list
	// of trusted proxy IPs to prevent IP spoofing via X-Forwarded-For header
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
	tokensToAdd := int(elapsed.Seconds() * float64(rl.rate) / 60.0)
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
	rl.mu.Lock()
	defer rl.mu.Unlock()

	for ip, limiter := range rl.clients {
		limiter.mu.Lock()
		if time.Since(limiter.lastSeen) > rl.window*5 { // Remove after 5 minutes of inactivity
			delete(rl.clients, ip)
		}
		limiter.mu.Unlock()
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
