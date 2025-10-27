package api

import (
	"html"
	"net/http"
	"net/url"
	"regexp"
	"unicode/utf8"
)

// SecurityMiddleware provides security headers and input sanitization
func SecurityMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Set security headers
		w.Header().Set("X-Content-Type-Options", "nosniff")
		w.Header().Set("X-Frame-Options", "DENY")
		w.Header().Set("X-XSS-Protection", "1; mode=block")
		w.Header().Set("Referrer-Policy", "strict-origin-when-cross-origin")
		w.Header().Set("Content-Security-Policy", "default-src 'self'")

		next.ServeHTTP(w, r)
	})
}

// InputSanitizationMiddleware sanitizes request inputs to prevent XSS
func InputSanitizationMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Sanitize URL parameters by building a new query map
		originalQuery := r.URL.Query()
		sanitizedQuery := make(url.Values)

		for key, values := range originalQuery {
			for _, value := range values {
				sanitizedQuery.Add(key, sanitizeInput(value))
			}
		}

		// Update the request with the sanitized query parameters
		r.URL.RawQuery = sanitizedQuery.Encode()

		// For POST/PUT requests, we'd need to sanitize the body
		// This is a basic implementation - in production, you'd want more sophisticated
		// sanitization based on content type and specific requirements

		next.ServeHTTP(w, r)
	})
}

// Precompiled regex patterns for security filtering
var (
	dangerousPatterns = []*regexp.Regexp{
		// Script tags and event handlers
		regexp.MustCompile(`(?i)<script[^>]*>.*?</script>`),
		regexp.MustCompile(`(?i)on\w+\s*=`),

		// JavaScript and data URLs
		regexp.MustCompile(`(?i)javascript:`),
		regexp.MustCompile(`(?i)data:.*?base64`),

		// Common XSS patterns
		regexp.MustCompile(`(?i)<iframe[^>]*>`),
		regexp.MustCompile(`(?i)<object[^>]*>`),
		regexp.MustCompile(`(?i)<embed[^>]*>`),
		regexp.MustCompile(`(?i)<link[^>]*>`),
		regexp.MustCompile(`(?i)<meta[^>]*>`),
		regexp.MustCompile(`(?i)<style[^>]*>.*?</style>`),
		regexp.MustCompile(`(?i)<form[^>]*>.*?</form>`),
		regexp.MustCompile(`(?i)<input[^>]*>`),
		regexp.MustCompile(`(?i)<button[^>]*>.*?</button>`),

		// Expression patterns
		regexp.MustCompile(`(?i)expression\s*\(`),
	}
)

// sanitizeInput removes potentially harmful characters from input
func sanitizeInput(input string) string {
	if input == "" {
		return input
	}

	// Remove potentially dangerous patterns from raw input first
	sanitized := removeDangerousPatterns(input)

	// HTML escape the cleaned input
	sanitized = html.EscapeString(sanitized)

	return sanitized
}

// removeDangerousPatterns removes potentially dangerous patterns from input
func removeDangerousPatterns(input string) string {
	result := input
	for _, pattern := range dangerousPatterns {
		result = pattern.ReplaceAllString(result, "")
	}
	return result
}

// validateInputLength checks if input exceeds maximum length
func validateInputLength(input string, maxLength int) bool {
	return utf8.RuneCountInString(input) <= maxLength
}

// sanitizeAndValidateInput combines sanitization and length validation
func sanitizeAndValidateInput(input string, maxLength int) (string, bool) {
	if input == "" {
		return input, true
	}

	sanitized := sanitizeInput(input)
	return sanitized, validateInputLength(sanitized, maxLength)
}
