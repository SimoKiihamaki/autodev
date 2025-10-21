package tui

import "github.com/charmbracelet/bubbles/textinput"

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
		m.focusedInput = ""
		return
	}
}

func (m *model) navigateSettings(direction string) {
	if m.focusedInput == "" {
		m.focusInput("repo")
		return
	}

	grid := map[string][2]int{
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

	var reverseGrid [settingsGridRows][settingsGridCols]string
	for input, pos := range grid {
		if pos[0] < settingsGridRows && pos[1] < settingsGridCols {
			reverseGrid[pos[0]][pos[1]] = input
		}
	}

	currentPos, exists := grid[m.focusedInput]
	if !exists {
		m.focusInput("repo")
		return
	}

	row, col := currentPos[0], currentPos[1]
	if row < 0 || row >= settingsGridRows || col < 0 || col >= settingsGridCols {
		m.focusInput("repo")
		return
	}

	switch direction {
	case "up":
		if row > 0 {
			for r := row - 1; r >= 0; r-- {
				if reverseGrid[r][col] != "" {
					m.focusInput(reverseGrid[r][col])
					return
				}
			}
			m.searchHorizontalInRow(reverseGrid, row-1, col)
		}
	case "down":
		if row < settingsGridRows-1 {
			for r := row + 1; r < settingsGridRows; r++ {
				if reverseGrid[r][col] != "" {
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
		if col < settingsGridCols-1 && reverseGrid[row][col+1] != "" {
			m.focusInput(reverseGrid[row][col+1])
			return
		}
		for c := col + 1; c < settingsGridCols; c++ {
			if reverseGrid[row][c] != "" {
				m.focusInput(reverseGrid[row][c])
				return
			}
		}
	}
}

func (m *model) searchHorizontalInRow(reverseGrid [settingsGridRows][settingsGridCols]string, targetRow, startCol int) {
	if targetRow < 0 || targetRow >= settingsGridRows {
		return
	}
	for offset := 1; offset < settingsGridCols; offset++ {
		if startCol-offset >= 0 && reverseGrid[targetRow][startCol-offset] != "" {
			m.focusInput(reverseGrid[targetRow][startCol-offset])
			return
		}
		if startCol+offset < settingsGridCols && reverseGrid[targetRow][startCol+offset] != "" {
			m.focusInput(reverseGrid[targetRow][startCol+offset])
			return
		}
	}
}

func (m *model) focusFlag(flagName string) {
	m.focusedFlag = flagName
}

func (m *model) navigateFlags(direction string) {
	flags := envFlagNames

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
	if field, ok := m.settingsInputMap()[inputName]; ok {
		return field
	}
	return nil
}
