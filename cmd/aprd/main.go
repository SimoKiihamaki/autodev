package main

import (
	"log"
	"os"

	"github.com/SimoKiihamaki/autodev/internal/tui"
	tea "github.com/charmbracelet/bubbletea"
)

// newTUIModel creates a new TUI model for the application.
func newTUIModel() tea.Model {
	return tui.New()
}

// newProgram creates a new bubbletea program with the given model.
func newProgram(m tea.Model) *tea.Program {
	return tea.NewProgram(m, tea.WithAltScreen())
}

// runProgram runs the bubbletea program and returns the final model.
func runProgram(p *tea.Program) (tea.Model, error) {
	return p.Run()
}

// cleanupModel performs cleanup on the final model after program exit.
func cleanupModel(m tea.Model) {
	tui.CleanupFinalModel(m)
}

func main() {
	m := newTUIModel()
	p := newProgram(m)
	finalModel, err := runProgram(p)
	if err != nil {
		log.Printf("TUI error: %v", err)
		os.Exit(1)
	}
	// Perform cleanup on the final model to release resources (cancel context,
	// close channels, etc.). Per Bubble Tea docs, the final model can contain
	// useful state for cleanup after exit. We use cleanupModel function
	// to access this functionality without coupling to concrete type.
	cleanupModel(finalModel)
}
