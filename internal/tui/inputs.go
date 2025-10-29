package tui

import (
	"fmt"
	"log"

	"github.com/charmbracelet/bubbles/textinput"
)

var settingsGrid = map[string][2]int{
	"repo":         {0, 0},
	"base":         {1, 0},
	"branch":       {2, 0},
	"codex":        {3, 0},
	"pycmd":        {4, 0},
	"pyscript":     {5, 0},
	"policy":       {6, 0},
	"toggleLocal":  {7, 0},
	"togglePR":     {7, 1},
	"toggleReview": {7, 2},
	"waitmin":      {8, 0},
	"pollsec":      {8, 1},
	"idlemin":      {8, 2},
	"maxiters":     {8, 3},
}

func (m *model) blurAllInputs() {
	m.inRepo.Blur()
	m.inBase.Blur()
	m.inBranch.Blur()
	m.inCodexModel.Blur()
	m.inPyCmd.Blur()
	m.inPyScript.Blur()
	m.inPolicy.Blur()
	m.inWaitMin.Blur()
	m.inPollSec.Blur()
	m.inIdleMin.Blur()
	m.inMaxIters.Blur()
	m.prompt.Blur()
	m.tagInput.Blur()
	m.focusedInput = ""
	m.focusedFlag = ""
}

func (m *model) focusInput(inputName string) {
	m.blurAllInputs()
	m.focusedInput = inputName

	switch inputName {
	case "repo":
		m.inRepo.Focus()
	case "base":
		m.inBase.Focus()
	case "branch":
		m.inBranch.Focus()
	case "codex":
		m.inCodexModel.Focus()
	case "pycmd":
		m.inPyCmd.Focus()
	case "pyscript":
		m.inPyScript.Focus()
	case "policy":
		m.inPolicy.Focus()
	case "toggleLocal", "togglePR", "toggleReview":
		// Toggles have no text input field to focus
		return
	case "waitmin":
		m.inWaitMin.Focus()
	case "pollsec":
		m.inPollSec.Focus()
	case "idlemin":
		m.inIdleMin.Focus()
	case "maxiters":
		m.inMaxIters.Focus()
	case "prompt":
		m.prompt.Focus()
	default:
		// Unknown input: clear state so tab navigation can recover gracefully.
		log.Printf("tui: unknown settings input focus request %q", inputName)
		m.status = fmt.Sprintf("Unknown settings input: %s", inputName)
		m.focusedInput = ""
		return
	}
}

func (m *model) navigateHorizontal(direction string, row, col int, reverseGrid [][]string) {
	var startCol, endCol, step int
	rowLen := len(reverseGrid[row])

	if direction == "left" {
		if col == 0 {
			return
		}
		startCol = col - 1
		endCol = -1
		step = -1
	} else { // "right"
		if col >= rowLen-1 {
			return
		}
		startCol = col + 1
		endCol = rowLen
		step = 1
	}

	// Try adjacent cell first
	if startCol >= 0 && startCol < rowLen && reverseGrid[row][startCol] != "" {
		m.focusInput(reverseGrid[row][startCol])
		return
	}

	// Then search in the specified direction
	for c := startCol; c != endCol; c += step {
		if reverseGrid[row][c] != "" {
			m.focusInput(reverseGrid[row][c])
			return
		}
	}
}

func (m *model) navigateVertical(direction string, row, col int, reverseGrid [][]string) {
	rows := len(reverseGrid)
	if rows == 0 {
		return
	}

	step := 1
	switch direction {
	case "up":
		step = -1
	case "down":
		step = 1
	default:
		return
	}

	for offset := 1; offset < rows; offset++ {
		nextRow, ok := wrapIndex(row+step*offset, rows)
		if !ok || nextRow == row {
			break
		}

		if col < len(reverseGrid[nextRow]) && reverseGrid[nextRow][col] != "" {
			m.focusInput(reverseGrid[nextRow][col])
			return
		}

		if m.searchHorizontalInRow(reverseGrid, nextRow, col) {
			return
		}
	}
}

func (m *model) navigateSettings(direction string) {
	if m.focusedInput == "" {
		m.focusInput("repo")
		return
	}

	maxRow, maxCol := 0, 0
	for _, pos := range settingsGrid {
		if pos[0] > maxRow {
			maxRow = pos[0]
		}
		if pos[1] > maxCol {
			maxCol = pos[1]
		}
	}

	reverseGrid := make([][]string, maxRow+1)
	for r := range reverseGrid {
		reverseGrid[r] = make([]string, maxCol+1)
	}
	for input, pos := range settingsGrid {
		row, col := pos[0], pos[1]
		if row >= 0 && row < len(reverseGrid) && col >= 0 && col < len(reverseGrid[row]) {
			reverseGrid[row][col] = input
		}
	}

	currentPos, exists := settingsGrid[m.focusedInput]
	if !exists {
		m.focusInput("repo")
		return
	}

	row, col := currentPos[0], currentPos[1]
	if row < 0 || row >= len(reverseGrid) {
		log.Printf("tui: detected out-of-bounds settings grid row=%d", row)
		m.focusInput("repo")
		return
	}
	if col < 0 || col >= len(reverseGrid[row]) {
		log.Printf("tui: detected out-of-bounds settings grid column=%d", col)
		m.focusInput("repo")
		return
	}

	switch direction {
	case "up", "down":
		m.navigateVertical(direction, row, col, reverseGrid)
	case "left", "right":
		m.navigateHorizontal(direction, row, col, reverseGrid)
	}
}

func (m *model) searchHorizontalInRow(reverseGrid [][]string, targetRow, startCol int) bool {
	if targetRow < 0 || targetRow >= len(reverseGrid) {
		return false
	}
	row := reverseGrid[targetRow]
	if len(row) == 0 {
		return false
	}
	if startCol >= 0 && startCol < len(row) && row[startCol] != "" {
		m.focusInput(row[startCol])
		return true
	}
	for offset := 1; offset < len(row); offset++ {
		left := startCol - offset
		if left >= 0 && left < len(row) && row[left] != "" {
			m.focusInput(row[left])
			return true
		}
		right := startCol + offset
		if right >= 0 && right < len(row) && row[right] != "" {
			m.focusInput(row[right])
			return true
		}
	}
	return false
}

func (m *model) focusFlag(flagName string) {
	m.focusedFlag = flagName
}

func (m *model) navigateFlags(direction string) {
	flags := envFlagNames

	// Guard helps if configuration trims available flags (tests or future changes).
	if len(flags) == 0 {
		return
	}

	if m.focusedFlag == "" {
		m.focusFlag(flags[0])
		return
	}

	currentIndex := -1
	for i, flag := range flags {
		if flag == m.focusedFlag {
			currentIndex = i
			break
		}
	}

	if currentIndex == -1 {
		m.focusFlag(flags[0])
		return
	}

	switch direction {
	case "up":
		newIndex, ok := wrapIndex(currentIndex-1, len(flags))
		if ok {
			m.focusFlag(flags[newIndex])
		}
	case "down":
		newIndex, ok := wrapIndex(currentIndex+1, len(flags))
		if ok {
			m.focusFlag(flags[newIndex])
		}
	case "left", "right":
		m.toggleFocusedFlag()
	}
}

func (m *model) toggleFocusedFlag() {
	switch m.focusedFlag {
	case "local":
		m.runLocal = !m.runLocal
	case "pr":
		m.runPR = !m.runPR
	case "review":
		m.runReview = !m.runReview
	case "unsafe":
		m.flagAllowUnsafe = !m.flagAllowUnsafe
	case "dryrun":
		m.flagDryRun = !m.flagDryRun
	case "syncgit":
		m.flagSyncGit = !m.flagSyncGit
	case "infinite":
		m.flagInfinite = !m.flagInfinite
	}
	m.updateDirtyState()
}

func (m *model) getInputField(inputName string) *textinput.Model {
	return m.settingsInputs[inputName]
}

func (m *model) cycleExecutorChoice(name string, direction int) {
	// Get a pointer to the appropriate executor choice field
	var target *executorChoice
	switch name {
	case "toggleLocal":
		target = &m.execLocalChoice
	case "togglePR":
		target = &m.execPRChoice
	case "toggleReview":
		target = &m.execReviewChoice
	default:
		return
	}

	// Calculate new choice and update via pointer
	n := len(executorChoices)
	if n == 0 {
		return
	}

	// Find current index in executorChoices
	current := *target
	idx := 0
	for i, choice := range executorChoices {
		if choice == current {
			idx = i
			break
		}
	}

	newIdx, ok := wrapIndex(idx+direction, n)
	if ok {
		*target = executorChoices[newIdx]
		m.updateDirtyState()
	}
}

func isExecutorToggle(name string) bool {
	switch name {
	case "toggleLocal", "togglePR", "toggleReview":
		return true
	default:
		return false
	}
}
