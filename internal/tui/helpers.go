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
// decrement) along with the collection length. The function returns 0 when
// n <= 0 so callers can safely use it with empty slices.
func wrapIndex(idx, n int) int {
	if n <= 0 {
		return 0
	}
	idx %= n
	if idx < 0 {
		idx += n
	}
	return idx
}
