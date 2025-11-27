package main

import (
	"log"

	"github.com/SimoKiihamaki/autodev/internal/tui"
	tea "github.com/charmbracelet/bubbletea"
)

func main() {
	m := tui.New()
	p := tea.NewProgram(m, tea.WithAltScreen())
	finalModel, err := p.Run()
	if err != nil {
		log.Fatal(err)
	}
	// Perform cleanup on the final model to release resources (cancel context,
	// close channels, etc.). Per Bubble Tea docs, the final model can contain
	// useful state for cleanup after exit. We use CleanupableModel interface
	// to access this functionality without coupling to concrete type.
	tui.CleanupFinalModel(finalModel)
}
