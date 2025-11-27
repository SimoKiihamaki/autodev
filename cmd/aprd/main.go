package main

import (
	"log"

	"github.com/SimoKiihamaki/autodev/internal/tui"
	tea "github.com/charmbracelet/bubbletea"
)

func main() {
	m := tui.New()
	p := tea.NewProgram(m, tea.WithAltScreen())
	if _, err := p.Run(); err != nil {
		log.Fatal(err)
	}
}
