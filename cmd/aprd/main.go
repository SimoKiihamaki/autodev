package main

import (
	"log"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/example/aprd-tui/internal/tui"
)

func main() {
	m := tui.New()
	p := tea.NewProgram(m, tea.WithAltScreen())
	if err := p.Start(); err != nil {
		log.Fatal(err)
	}
}
