package tui

import (
	"fmt"
	"strconv"
	"strings"
)

const atoiDefault = 0

// atoiSafe trims whitespace and converts to int, returning atoiDefault alongside an error when parsing fails.
// Callers are expected to check the error and decide how to surface defaults to the user.
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
