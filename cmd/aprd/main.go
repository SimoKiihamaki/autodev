package main

import (
	"log"
	"os"

	"github.com/SimoKiihamaki/autodev/internal/tui"
	tea "github.com/charmbracelet/bubbletea"
)

func main() {
	m := tui.New()
	p := tea.NewProgram(m, tea.WithAltScreen())
	finalModel, err := p.Run()
	if err != nil {
		log.Printf("TUI error: %v", err)
		os.Exit(1)
	}
	// Perform cleanup on the final model to release resources (cancel context,
	// close channels, etc.). Per Bubble Tea docs, the final model can contain
	// useful state for cleanup after exit. We use CleanupFinalModel function
	// to access this functionality without coupling to concrete type.
	tui.CleanupFinalModel(finalModel)
}
