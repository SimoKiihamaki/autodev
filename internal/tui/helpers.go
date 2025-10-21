package tui

import (
	"log"
	"strconv"
	"strings"
)

const atoiDefault = 0

func atoiSafe(s string) int {
	s = strings.TrimSpace(s)
	if s == "" {
		return atoiDefault
	}
	n, err := strconv.Atoi(s)
	if err != nil {
		log.Printf("tui: atoiSafe failed to parse %q: %v", s, err)
		return atoiDefault
	}
	return n
}
