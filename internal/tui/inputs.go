package tui

import (
	"fmt"
	"log"

	"github.com/charmbracelet/bubbles/textinput"
)

var settingsGrid = map[string][2]int{
	"repo":     {0, 0},
	"base":     {1, 0},
	"branch":   {2, 0},
	"codex":    {3, 0},
	"pycmd":    {4, 0},
	"pyscript": {5, 0},
	"policy":   {6, 0},
	"execimpl": {7, 0},
	"execfix":  {7, 1},
	"execpr":   {7, 2},
	"execrev":  {7, 3},
	"waitmin":  {8, 0},
	"pollsec":  {8, 1},
	"idlemin":  {8, 2},
	"maxiters": {8, 3},
}

func (m *model) blurAllInputs() {
	m.inRepo.Blur()
	m.inBase.Blur()
	m.inBranch.Blur()
	m.inCodexModel.Blur()
	m.inPyCmd.Blur()
	m.inPyScript.Blur()
	m.inPolicy.Blur()
	m.inExecImpl.Blur()
	m.inExecFix.Blur()
	m.inExecPR.Blur()
	m.inExecRev.Blur()
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
	case "execimpl":
		m.inExecImpl.Focus()
	case "execfix":
		m.inExecFix.Focus()
	case "execpr":
		m.inExecPR.Focus()
	case "execrev":
		m.inExecRev.Focus()
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
	case "up":
		if row > 0 {
			for r := row - 1; r >= 0; r-- {
				if col < len(reverseGrid[r]) && reverseGrid[r][col] != "" {
					m.focusInput(reverseGrid[r][col])
					return
				}
			}
			m.searchHorizontalInRow(reverseGrid, row-1, col)
		}
	case "down":
		if row < len(reverseGrid)-1 {
			for r := row + 1; r < len(reverseGrid); r++ {
				if col < len(reverseGrid[r]) && reverseGrid[r][col] != "" {
					m.focusInput(reverseGrid[r][col])
					return
				}
			}
			m.searchHorizontalInRow(reverseGrid, row+1, col)
		}
	case "left":
		if col > 0 && reverseGrid[row][col-1] != "" {
			m.focusInput(reverseGrid[row][col-1])
			return
		}
		for c := col - 1; c >= 0; c-- {
			if reverseGrid[row][c] != "" {
				m.focusInput(reverseGrid[row][c])
				return
			}
		}
	case "right":
		rowLen := len(reverseGrid[row])
		if col < rowLen-1 && reverseGrid[row][col+1] != "" {
			m.focusInput(reverseGrid[row][col+1])
			return
		}
		for c := col + 1; c < rowLen; c++ {
			if reverseGrid[row][c] != "" {
				m.focusInput(reverseGrid[row][c])
				return
			}
		}
	}
}

func (m *model) searchHorizontalInRow(reverseGrid [][]string, targetRow, startCol int) {
	if targetRow < 0 || targetRow >= len(reverseGrid) {
		return
	}
	row := reverseGrid[targetRow]
	if len(row) == 0 {
		return
	}
	for offset := 1; offset < len(row); offset++ {
		left := startCol - offset
		if left >= 0 && left < len(row) && row[left] != "" {
			m.focusInput(row[left])
			return
		}
		right := startCol + offset
		if right >= 0 && right < len(row) && row[right] != "" {
			m.focusInput(row[right])
			return
		}
	}
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
		newIndex := (currentIndex - 1 + len(flags)) % len(flags)
		m.focusFlag(flags[newIndex])
	case "down":
		newIndex := (currentIndex + 1) % len(flags)
		m.focusFlag(flags[newIndex])
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
}

func (m *model) getInputField(inputName string) *textinput.Model {
	return m.settingsInputs[inputName]
}
