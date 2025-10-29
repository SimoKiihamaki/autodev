package tui

import (
	"fmt"
	"strconv"
	"strings"
)

const atoiDefault = 0

// atoiSafe trims whitespace and converts to int, returning (atoiDefault, error) when parsing fails.
// Callers (e.g., hydrateConfigFromInputs) log the error and surface fallback messaging to the user.
func atoiSafe(s string) (int, error) {
	s = strings.TrimSpace(s)
	if s == "" {
		return atoiDefault, nil
	}
	n, err := strconv.Atoi(s)
	if err != nil {
		return atoiDefault, fmt.Errorf("invalid integer %q: %w", s, err)
	}
	return n, nil
}

// wrapIndex normalizes idx into the range [0, n). It gracefully handles
// negative offsets and values greater than n by applying modular arithmetic.
// Callers should pass the desired index (after applying an increment or
// decrement) along with the collection length.
//
// When n <= 0, this function returns (0, false) to make misuse explicit
// rather than silently returning a valid-looking but potentially unsafe index.
// The returned bool indicates whether the index is valid for use in slice/array access.
func wrapIndex(idx, n int) (int, bool) {
	// n must be > 0 for modulo operation to be safe
	if n <= 0 {
		return 0, false
	}
	// n is guaranteed > 0 here, so modulo operation is safe
	idx %= n
	if idx < 0 {
		idx += n
	}
	return idx, true
}

// boolPtr returns a pointer to a bool value.
func boolPtr(b bool) *bool {
	return &b
}
