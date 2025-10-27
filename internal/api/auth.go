package api

import (
	"context"
	"net/http"
	"strings"
)

// contextKey is a custom type for context keys to prevent collisions
type contextKey string

// Typed context keys for user authentication
const (
	UserIDKey    contextKey = "user_id"
	UserEmailKey contextKey = "user_email"
	UsernameKey  contextKey = "user_username"
)

// AuthMiddleware creates a JWT authentication middleware
func AuthMiddleware(userRepo UserRepository) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			authHeader := r.Header.Get("Authorization")
			if authHeader == "" {
				writeError(w, http.StatusUnauthorized, "authorization header required")
				return
			}

			// Extract token from "Bearer <token>" format
			tokenParts := strings.Split(authHeader, " ")
			if len(tokenParts) != 2 || tokenParts[0] != "Bearer" {
				writeError(w, http.StatusUnauthorized, "invalid authorization header format")
				return
			}

			token := tokenParts[1]
			claims, err := userRepo.ValidateJWTToken(token)
			if err != nil {
				writeError(w, http.StatusUnauthorized, "invalid token")
				return
			}

			// Add user context to the request
			ctx := context.WithValue(r.Context(), UserIDKey, claims.UserID)
			ctx = context.WithValue(ctx, UserEmailKey, claims.Email)
			ctx = context.WithValue(ctx, UsernameKey, claims.Username)

			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

// OptionalAuthMiddleware adds user context if token is present, but doesn't require authentication
func OptionalAuthMiddleware(userRepo UserRepository) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			authHeader := r.Header.Get("Authorization")
			if authHeader == "" {
				next.ServeHTTP(w, r)
				return
			}

			tokenParts := strings.Split(authHeader, " ")
			if len(tokenParts) != 2 || tokenParts[0] != "Bearer" {
				next.ServeHTTP(w, r)
				return
			}

			token := tokenParts[1]
			claims, err := userRepo.ValidateJWTToken(token)
			if err != nil {
				next.ServeHTTP(w, r)
				return
			}

			// Add user context to the request
			ctx := context.WithValue(r.Context(), UserIDKey, claims.UserID)
			ctx = context.WithValue(ctx, UserEmailKey, claims.Email)
			ctx = context.WithValue(ctx, UsernameKey, claims.Username)

			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

// GetUserIDFromContext extracts the user ID from the request context
func GetUserIDFromContext(ctx context.Context) (string, bool) {
	userID, ok := ctx.Value(UserIDKey).(string)
	return userID, ok
}

// GetUserEmailFromContext extracts the user email from the request context
func GetUserEmailFromContext(ctx context.Context) (string, bool) {
	userEmail, ok := ctx.Value(UserEmailKey).(string)
	return userEmail, ok
}

// GetUserUsernameFromContext extracts the username from the request context
func GetUserUsernameFromContext(ctx context.Context) (string, bool) {
	username, ok := ctx.Value(UsernameKey).(string)
	return username, ok
}
