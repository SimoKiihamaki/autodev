package tui

import (
	"log"
	"strconv"
	"strings"
)

func atoiSafe(s string) int {
	s = strings.TrimSpace(s)
	if s == "" {
		return 0
	}
	n, err := strconv.Atoi(s)
	if err != nil {
		log.Printf("tui: atoiSafe failed to parse %q: %v", s, err)
		return 0
	}
	return n
}
