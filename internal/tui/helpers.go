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

// wrapIndex normalizes (current + delta) into the range [0, n). It gracefully handles
// negative offsets and values greater than n by applying modular arithmetic.
// Callers should pass the current index, the desired increment or decrement (delta),
// and the collection length.
//
// When n <= 0, this function returns (0, false) to make misuse explicit
// rather than silently returning a valid-looking but potentially unsafe index.
// The returned bool indicates whether the index is valid for use in slice/array access.
// Assumes delta values are reasonable for UI navigation (not extreme values that would cause overflow).
func wrapIndex(current, delta, n int) (int, bool) {
	// n must be > 0 for modulo operation to be safe
	if n <= 0 {
		return 0, false
	}
	// Validate that current is within bounds [0, n)
	if current < 0 || current >= n {
		return 0, false
	}
	// Check for potential overflow - only for extreme delta values
	// This handles the case where delta is extremely large (positive or negative)
	// For typical UI navigation (delta = -1, 1, etc.), this won't trigger
	if delta > 0 && current > 0 && delta >= int(^uint(0)>>1)-current {
		return 0, false // Would overflow on addition
	}
	// Note: Overflow check for negative delta removed since modulo operation handles negative results correctly
	// and UI navigation deltas are typically small values that won't cause overflow

	idx := (current + delta) % n
	if idx < 0 {
		idx += n
	}
	return idx, true
}

// boolPtr returns a pointer to a bool value.
func boolPtr(b bool) *bool {
	return &b
}
