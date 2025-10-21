package tui

import (
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/SimoKiihamaki/autodev/internal/config"
	"github.com/SimoKiihamaki/autodev/internal/runner"
	"github.com/charmbracelet/bubbles/list"
	"github.com/charmbracelet/bubbles/textarea"
	"github.com/charmbracelet/bubbles/textinput"
	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

type tab int

const (
	tabRun tab = iota
	tabPRD
	tabSettings
	tabEnv
	tabPrompt
	tabLogs
	tabHelp
)

var tabNames = []string{"Run", "PRD", "Settings", "Env", "Prompt", "Logs", "Help"}

type item struct {
	title, desc string
	path        string
}

func (i item) Title() string       { return i.title }
func (i item) Description() string { return i.desc }
func (i item) FilterValue() string { return i.title + " " + i.path }

type model struct {
	tab    tab
	cfg    config.Config
	status string
	errMsg string

	// PRD selection
	prdList     list.Model
	selectedPRD string
	tags        []string
	tagInput    textinput.Model

	// Inputs in Settings
	inRepo       textinput.Model
	inBase       textinput.Model
	inBranch     textinput.Model
	inCodexModel textinput.Model
	inPyCmd      textinput.Model
	inPyScript   textinput.Model
	inPolicy     textinput.Model
	inExecImpl   textinput.Model
	inExecFix    textinput.Model
	inExecPR     textinput.Model
	inExecRev    textinput.Model
	inWaitMin    textinput.Model
	inPollSec    textinput.Model
	inIdleMin    textinput.Model
	inMaxIters   textinput.Model

	// Focus management
	focusedInput string
	focusedFlag  string // For Env tab flag selection

	// Phases toggles
	runLocal  bool
	runPR     bool
	runReview bool

	// Flags
	flagAllowUnsafe bool
	flagDryRun      bool
	flagSyncGit     bool
	flagInfinite    bool

	// Prompt
	prompt textarea.Model

	// Logs
	logs   viewport.Model
	logBuf []string

	// Live run dashboard
	runFeed         viewport.Model
	runFeedBuf      []string
	runPhase        string
	runCurrent      string
	runPrevious     string
	runLastComplete string
	runIterCurrent  int
	runIterTotal    int
	runIterLabel    string

	// Runner
	running   bool
	cancel    context.CancelFunc
	logCh     chan runner.Line
	runResult chan error
}

const (
	settingsGridRows = 9
	settingsGridCols = 4
)

// Centralized input names for settings
// This list defines the linear order of inputs for Tab navigation,
// while the grid map in navigateSettings defines the 2D spatial layout.
var settingsInputNames = []string{
	"repo", "base", "branch", "codex", "pycmd", "pyscript", "policy",
	"execimpl", "execfix", "execpr", "execrev", "waitmin", "pollsec", "idlemin", "maxiters",
}

// Centralized flag names for env tab
var envFlagNames = []string{"local", "pr", "review", "unsafe", "dryrun", "syncgit", "infinite"}

var (
	reSectionHeader   = regexp.MustCompile(`^=+\s*(.+?)\s*=+$`)
	reIterationHeader = regexp.MustCompile(`^=+\s*Iteration\s+(\d+)(?:/(\d+))?:\s*(.+?)\s*=+$`)
)

// Returns a map of input name to pointer to textinput.Model for the given model instance
func (m *model) settingsInputMap() map[string]*textinput.Model {
	return map[string]*textinput.Model{
		"repo":     &m.inRepo,
		"base":     &m.inBase,
		"branch":   &m.inBranch,
		"codex":    &m.inCodexModel,
		"pycmd":    &m.inPyCmd,
		"pyscript": &m.inPyScript,
		"policy":   &m.inPolicy,
		"execimpl": &m.inExecImpl,
		"execfix":  &m.inExecFix,
		"execpr":   &m.inExecPR,
		"execrev":  &m.inExecRev,
		"waitmin":  &m.inWaitMin,
		"pollsec":  &m.inPollSec,
		"idlemin":  &m.inIdleMin,
		"maxiters": &m.inMaxIters,
	}
}

func New() model {
	cfg, err := config.Load()
	var loadStatus string
	if err != nil {
		cfg = config.Defaults()
		loadStatus = fmt.Sprintf("Warning: Could not load config (%v), using defaults", err)
	}

	m := model{
		tab: tabRun,
		cfg: cfg,
	}

	// PRD list
	delegate := list.NewDefaultDelegate()
	delegate.ShowDescription = true
	m.prdList = list.New([]list.Item{}, delegate, 0, 0)
	m.prdList.Title = "Select a PRD (.md)"
	m.prdList.SetShowHelp(false)
	m.prdList.SetFilteringEnabled(true)
	m.prdList.DisableQuitKeybindings()

	// Inputs
	m.inRepo = mkInput("Repo path", cfg.RepoPath, 60)
	m.inBase = mkInput("Base branch", cfg.BaseBranch, 20)
	m.inBranch = mkInput("Feature branch (optional)", cfg.Branch, 30)
	m.inCodexModel = mkInput("Codex model", cfg.CodexModel, 24)
	m.inPyCmd = mkInput("Python command", cfg.PythonCommand, 20)
	m.inPyScript = mkInput("Python script path", cfg.PythonScript, 80)
	m.inPolicy = mkInput("Executor policy (codex-first|codex-only|claude-only)", cfg.ExecutorPolicy, 28)
	m.inExecImpl = mkInput("Exec (implement): codex|claude|<empty>", cfg.PhaseExecutors.Implement, 16)
	m.inExecFix = mkInput("Exec (fix): codex|claude|<empty>", cfg.PhaseExecutors.Fix, 16)
	m.inExecPR = mkInput("Exec (pr): codex|claude|<empty>", cfg.PhaseExecutors.PR, 16)
	m.inExecRev = mkInput("Exec (review_fix): codex|claude|<empty>", cfg.PhaseExecutors.ReviewFix, 22)
	m.inWaitMin = mkInput("Wait minutes", fmt.Sprint(cfg.Timings.WaitMinutes), 6)
	m.inPollSec = mkInput("Review poll seconds", fmt.Sprint(cfg.Timings.ReviewPollSeconds), 6)
	m.inIdleMin = mkInput("Idle grace minutes", fmt.Sprint(cfg.Timings.IdleGraceMinutes), 6)
	m.inMaxIters = mkInput("Max local iters", fmt.Sprint(cfg.Timings.MaxLocalIters), 6)

	// Phases
	m.runLocal = cfg.RunPhases.Local
	m.runPR = cfg.RunPhases.PR
	m.runReview = cfg.RunPhases.ReviewFix

	// Flags
	m.flagAllowUnsafe = cfg.Flags.AllowUnsafe
	m.flagDryRun = cfg.Flags.DryRun
	m.flagSyncGit = cfg.Flags.SyncGit
	m.flagInfinite = cfg.Flags.InfiniteReviews

	// Prompt
	m.prompt = textarea.New()
	m.prompt.Placeholder = "Optional initial instruction injected above the PRD…"
	m.prompt.CharLimit = 0
	m.prompt.SetWidth(80)
	m.prompt.SetHeight(8)

	// Logs
	m.logs = viewport.New(100, 20)
	m.logs.SetContent("")

	// Live run feed
	m.runFeed = viewport.New(100, 18)
	m.runFeed.SetContent("")

	// Tags
	m.tagInput = mkInput("Add tag", "", 24)

	// Initially blur all inputs (after prompt is initialized)
	m.blurAllInputs()

	// Scan PRDs
	m.rescanPRDs()

	// Set load status if config failed to load
	if loadStatus != "" {
		m.status = loadStatus
	}

	m.resetRunDashboard()

	return m
}

func mkInput(placeholder, value string, width int) textinput.Model {
	ti := textinput.New()
	ti.Placeholder = placeholder
	ti.SetValue(value)
	ti.Width = width
	return ti
}

func (m model) Init() tea.Cmd {
	return m.scanPRDsCmd()
}

// ------- PRD scan -------
func (m *model) rescanPRDs() { m.prdList.SetItems([]list.Item{}) }

func (m model) scanPRDsCmd() tea.Cmd {
	return func() tea.Msg {
		var items []list.Item
		cwd, err := os.Getwd()
		if err != nil {
			return prdScanMsg{items: nil}
		}
		_ = filepath.WalkDir(cwd, func(path string, d os.DirEntry, err error) error {
			if err != nil {
				return nil
			}
			if d.IsDir() {
				rel, _ := filepath.Rel(cwd, path)
				if strings.Count(rel, string(os.PathSeparator)) > 4 {
					return filepath.SkipDir
				}
				return nil
			}
			if strings.HasSuffix(strings.ToLower(d.Name()), ".md") {
				rel, _ := filepath.Rel(cwd, path)
				items = append(items, item{title: d.Name(), desc: rel, path: path})
			}
			return nil
		})
		sort.Slice(items, func(i, j int) bool { return items[i].(item).path < items[j].(item).path })
		return prdScanMsg{items: items}
	}
}

type prdScanMsg struct{ items []list.Item }

func (m *model) ensureSelectedPRD(items []list.Item) {
	if len(items) == 0 {
		m.clearPRDSelection("No PRD files found.")
		return
	}

	// Keep current selection if it still exists.
	for _, it := range items {
		cand, ok := it.(item)
		if ok && cand.path == m.selectedPRD {
			return
		}
	}

	var bestPath string
	var bestTime time.Time
	for _, it := range items {
		cand, ok := it.(item)
		if !ok {
			continue
		}
		if meta, ok := m.cfg.PRDs[cand.path]; ok && !meta.LastUsed.IsZero() {
			if bestPath == "" || meta.LastUsed.After(bestTime) {
				bestTime = meta.LastUsed
				bestPath = cand.path
			}
		}
	}

	if bestPath == "" {
		if cand, ok := items[0].(item); ok {
			bestPath = cand.path
		}
	}

	prev := m.selectedPRD
	if bestPath != "" {
		m.selectedPRD = bestPath
		if meta, ok := m.cfg.PRDs[bestPath]; ok {
			m.tags = append([]string{}, meta.Tags...)
		} else {
			m.tags = nil
		}
		if m.status == "" && prev != bestPath {
			m.status = "Auto-selected PRD: " + filepath.Base(bestPath)
		}
		return
	}

	m.clearPRDSelection("No PRD files found.")
}

func (m *model) clearPRDSelection(statusMsg string) {
	if m.selectedPRD != "" {
		m.selectedPRD = ""
	}
	m.tags = nil
	m.status = statusMsg
}

// ------- Runner/logs messages -------
type runStartMsg struct{}
type runStopMsg struct{}
type logLineMsg struct{ line runner.Line }
type runErrMsg struct{ err error }
type statusMsg struct{ note string }
type runFinishMsg struct{ err error }

// ------- Update -------
func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		// Handle terminal resize
		w, h := msg.Width, msg.Height
		m.prdList.SetSize(w-2, h-10)
		m.logs.Width, m.logs.Height = w-2, h-8
		m.runFeed.Width, m.runFeed.Height = w-2, h-12
		m.prompt.SetWidth(w - 2)
		return m, nil
	case tea.KeyMsg:
		switch msg.String() {
		case "ctrl+c":
			if m.running && m.cancel != nil {
				m.cancel()
				return m, func() tea.Msg { return runStopMsg{} }
			}
			return m, tea.Quit
		case "q":
			if m.running {
				return m, nil
			}
			return m, tea.Quit
		case "?":
			m.tab = tabHelp
			m.blurAllInputs()
			return m, nil
		case "1":
			m.tab = tabRun
			m.blurAllInputs()
			return m, nil
		case "2":
			m.tab = tabPRD
			m.blurAllInputs()
			return m, nil
		case "3":
			m.tab = tabSettings
			m.blurAllInputs()
			return m, nil
		case "4":
			m.tab = tabEnv
			m.blurAllInputs()
			return m, nil
		case "5":
			m.tab = tabPrompt
			m.blurAllInputs()
			return m, nil
		case "6":
			m.tab = tabLogs
			m.blurAllInputs()
			return m, nil
		}

		switch m.tab {
		case tabRun:
			key := msg.String()
			switch key {
			case "enter":
				if m.running {
					return m, nil
				}
				return m, m.startRunCmd()
			case "up", "down":
				if len(m.runFeedBuf) > 0 || m.running {
					var cmd tea.Cmd
					m.runFeed, cmd = m.runFeed.Update(msg)
					return m, cmd
				}
			case "pgup":
				if len(m.runFeedBuf) > 0 || m.running {
					m.runFeed.LineUp(10)
					return m, nil
				}
			case "pgdown":
				if len(m.runFeedBuf) > 0 || m.running {
					m.runFeed.LineDown(10)
					return m, nil
				}
			case "home":
				if len(m.runFeedBuf) > 0 || m.running {
					m.runFeed.GotoTop()
					return m, nil
				}
			case "end":
				if len(m.runFeedBuf) > 0 || m.running {
					m.runFeed.GotoBottom()
					return m, nil
				}
			}

		case tabPRD:
			// Check if tag input is focused
			if m.tagInput.Focused() {
				switch msg.String() {
				case "enter":
					if tag := strings.TrimSpace(m.tagInput.Value()); tag != "" {
						m.tags = append(m.tags, tag)
						m.tagInput.SetValue("")
						m.tagInput.Blur()
					}
					return m, nil
				case "esc":
					m.tagInput.Blur()
					return m, nil
				}
				var cmd tea.Cmd
				m.tagInput, cmd = m.tagInput.Update(msg)
				return m, cmd
			}

			// PRD list navigation and tag management
			switch msg.String() {
			case "enter":
				if sel, ok := m.prdList.SelectedItem().(item); ok {
					m.selectedPRD = sel.path
					if meta, ok := m.cfg.PRDs[sel.path]; ok {
						m.tags = append([]string{}, meta.Tags...)
					} else {
						m.tags = []string{}
					}
					return m, nil
				}
			case "t":
				m.tagInput.Focus()
				return m, nil
			case "left", "right":
				// Let the list handle left/right for filtering
				var cmd tea.Cmd
				m.prdList, cmd = m.prdList.Update(msg)
				return m, cmd
			case "backspace":
				if m.prdList.FilterState() == list.Filtering {
					var cmd tea.Cmd
					m.prdList, cmd = m.prdList.Update(msg)
					return m, cmd
				}
				if len(m.tags) > 0 {
					m.tags = m.tags[:len(m.tags)-1]
				}
				return m, nil
			case "s":
				if m.selectedPRD != "" {
					if m.cfg.PRDs == nil {
						m.cfg.PRDs = map[string]config.PRDMeta{}
					}
					meta := m.cfg.PRDs[m.selectedPRD]
					meta.Tags = append([]string{}, m.tags...)
					meta.LastUsed = time.Now()
					m.cfg.PRDs[m.selectedPRD] = meta
					if err := config.Save(m.cfg); err != nil {
						m.status = "Tag save failed: " + err.Error()
					} else {
						m.status = "Tags saved"
					}
				}
				return m, nil
			case "r":
				m.rescanPRDs()
				m.status = "Rescanning PRDs…"
				return m, m.scanPRDsCmd()
			}
			// Let the list handle up/down arrows and other navigation
			var cmd tea.Cmd
			m.prdList, cmd = m.prdList.Update(msg)
			return m, cmd

		case tabSettings:
			// Handle input field focus and navigation for Settings
			switch msg.String() {
			case "up", "down", "left", "right":
				if m.focusedInput == "" {
					m.focusInput("repo")
				} else {
					m.navigateSettings(msg.String())
				}
				return m, nil
			case "tab":
				// Keep Tab as an alternative navigation
				inputs := settingsInputNames
				if m.focusedInput == "" {
					m.focusInput(inputs[0])
				} else {
					for i, input := range inputs {
						if input == m.focusedInput {
							nextIndex := (i + 1) % len(inputs)
							m.focusInput(inputs[nextIndex])
							break
						}
					}
				}
				return m, nil
			case "enter":
				// If no input is focused, focus the first one
				if m.focusedInput == "" {
					m.focusInput("repo")
				} else {
					// Unfocus current input
					m.blurAllInputs()
				}
				return m, nil
			case "esc":
				m.blurAllInputs()
				return m, nil
			case "s":
				return m, m.saveConfig()
			}

			// Update focused input if any
			if m.focusedInput != "" {
				if field := m.getInputField(m.focusedInput); field != nil {
					var cmd tea.Cmd
					*field, cmd = (*field).Update(msg)
					return m, cmd
				}
			}
			return m, nil

		case tabEnv:
			// Handle flag navigation for Env tab
			switch msg.String() {
			case "up", "down":
				m.navigateFlags(msg.String())
				return m, nil
			case "left", "right":
				if m.focusedFlag != "" {
					m.navigateFlags(msg.String())
				} else {
					m.navigateFlags("down") // Focus first flag
				}
				return m, nil
			case "enter":
				if m.focusedFlag != "" {
					m.toggleFocusedFlag()
				} else {
					m.focusFlag("local") // Focus first flag
				}
				return m, nil
			case "esc":
				m.focusedFlag = ""
				return m, nil
			case "L", "l":
				m.runLocal = !m.runLocal
				return m, nil
			case "P", "p":
				m.runPR = !m.runPR
				return m, nil
			case "R", "r":
				m.runReview = !m.runReview
				return m, nil
			case "a":
				m.flagAllowUnsafe = !m.flagAllowUnsafe
				return m, nil
			case "d":
				m.flagDryRun = !m.flagDryRun
				return m, nil
			case "g":
				m.flagSyncGit = !m.flagSyncGit
				return m, nil
			case "i":
				m.flagInfinite = !m.flagInfinite
				return m, nil
			case "s":
				return m, m.saveConfig()
			}
			return m, nil

		case tabPrompt:
			switch msg.String() {
			case "enter":
				if !m.prompt.Focused() {
					m.focusInput("prompt")
				} else {
					// Add newline if already focused
					var cmd tea.Cmd
					m.prompt, cmd = m.prompt.Update(msg)
					return m, cmd
				}
				return m, nil
			case "up", "down", "left", "right":
				if !m.prompt.Focused() {
					// Arrow keys focus the prompt when not focused
					m.focusInput("prompt")
					return m, nil
				}
				// If focused, let the textarea handle the arrows
				var cmd tea.Cmd
				m.prompt, cmd = m.prompt.Update(msg)
				return m, cmd
			case "esc":
				m.blurAllInputs()
				return m, nil
			}

			// Update the prompt if focused
			if m.prompt.Focused() {
				var cmd tea.Cmd
				m.prompt, cmd = m.prompt.Update(msg)
				return m, cmd
			}
			return m, nil

		case tabLogs:
			switch msg.String() {
			case "up", "down":
				// Ensure viewport handles arrow keys properly
				var cmd tea.Cmd
				m.logs, cmd = m.logs.Update(msg)
				return m, cmd
			case "pgup":
				// Page up
				m.logs.LineUp(10)
				return m, nil
			case "pgdown":
				// Page down
				m.logs.LineDown(10)
				return m, nil
			case "home":
				// Go to top
				m.logs.GotoTop()
				return m, nil
			case "end":
				// Go to bottom
				m.logs.GotoBottom()
				return m, nil
			}
			// Update the logs viewport for any other keys
			var cmd tea.Cmd
			m.logs, cmd = m.logs.Update(msg)
			return m, cmd
		}

	case prdScanMsg:
		m.prdList.SetItems(msg.items)
		m.ensureSelectedPRD(msg.items)
		return m, nil

	case statusMsg:
		m.status = msg.note
		return m, nil

	case runStartMsg:
		m.running = true
		m.errMsg = ""
		m.status = "Running…"
		m.tab = tabRun
		return m, nil

	case runStopMsg:
		m.running = false
		m.cancel = nil
		m.status = "Stopped."
		return m, nil
	case runFinishMsg:
		m.running = false
		m.cancel = nil
		m.runResult = nil
		switch {
		case msg.err == nil:
			m.errMsg = ""
			m.status = "Run finished successfully."
		case errors.Is(msg.err, context.Canceled):
			m.errMsg = ""
			m.status = "Run canceled."
		default:
			m.errMsg = msg.err.Error()
			m.status = "Run failed."
		}
		return m, nil

	case logLineMsg:
		line := msg.line
		prefix := ""
		if line.Err {
			prefix = "[ERR] "
		}
		display := prefix + line.Text
		m.logBuf = append(m.logBuf, display)
		if len(m.logBuf) > 2000 {
			m.logBuf = m.logBuf[len(m.logBuf)-2000:]
		}
		m.logs.SetContent(strings.Join(m.logBuf, "\n"))
		m.handleRunFeedLine(display, line.Text)
		// keep reading
		return m, m.readLogs()

	case runErrMsg:
		m.running = false
		m.errMsg = msg.err.Error()
		m.status = "Error."
		return m, nil
	}
	return m, nil
}

// Input focus management helpers
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

// Define the grid layout for Settings tab
// Grid layout (row, col):
// (0,0) repo                    (0,1) -
// (1,0) base                    (1,1) -
// (2,0) branch                  (2,1) -
// (3,0) codex                   (3,1) -
// (4,0) pycmd                   (4,1) -
// (5,0) pyscript                (5,1) -
// (6,0) policy                  (6,1) -
// (7,0) execimpl  (7,1) execfix (7,2) execpr (7,3) execrev
// (8,0) waitmin   (8,1) pollsec (8,2) idlemin (8,3) maxiters

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
	}
}

// Navigate with arrow keys in Settings tab
func (m *model) navigateSettings(direction string) {
	if m.focusedInput == "" {
		m.focusInput("repo")
		return
	}

	// Define grid positions
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

	// Reverse mapping for finding inputs by position
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

	switch direction {
	case "up":
		if row > 0 {
			// Find the closest input above
			for r := row - 1; r >= 0; r-- {
				if reverseGrid[r][col] != "" {
					m.focusInput(reverseGrid[r][col])
					return
				}
			}
			// If nothing directly above, search horizontally in the row above
			m.searchHorizontalInRow(reverseGrid, row-1, col)
		}
	case "down":
		if row < settingsGridRows-1 {
			// Find the closest input below
			for r := row + 1; r < settingsGridRows; r++ {
				if reverseGrid[r][col] != "" {
					m.focusInput(reverseGrid[r][col])
					return
				}
			}
			// If nothing directly below, search horizontally in the row below
			m.searchHorizontalInRow(reverseGrid, row+1, col)
		}
	case "left":
		if col > 0 {
			if reverseGrid[row][col-1] != "" {
				m.focusInput(reverseGrid[row][col-1])
				return
			}
		}
		// Try to find any input to the left in the same row
		for c := col - 1; c >= 0; c-- {
			if reverseGrid[row][c] != "" {
				m.focusInput(reverseGrid[row][c])
				return
			}
		}
	case "right":
		if col < settingsGridCols-1 {
			if reverseGrid[row][col+1] != "" {
				m.focusInput(reverseGrid[row][col+1])
				return
			}
		}
		// Try to find any input to the right in the same row
		for c := col + 1; c < settingsGridCols; c++ {
			if reverseGrid[row][c] != "" {
				m.focusInput(reverseGrid[row][c])
				return
			}
		}
	}
}

// searchHorizontalInRow searches for the nearest non-empty input field in the target row.
// This function is called when vertical navigation fails to find a direct match above or below,
// helping handle sparse grid layouts by searching horizontally in the nearest row.
// The search alternates left and right from the starting column, checking increasing distances,
// and focuses the first non-empty input found.
//
// Parameters:
//
//	reverseGrid: a 2D array representing the settings grid, where each cell contains the input field name or an empty string if no input is present.
//	targetRow: the row index (0-based) in which to search for a non-empty input field.
//	startCol: the starting column index (0-based) from which to begin the horizontal search.
func (m *model) searchHorizontalInRow(reverseGrid [settingsGridRows][settingsGridCols]string, targetRow, startCol int) {
	if targetRow < 0 || targetRow >= settingsGridRows {
		return
	}
	for offset := 1; offset < settingsGridCols; offset++ {
		// Check left side first
		if startCol-offset >= 0 && reverseGrid[targetRow][startCol-offset] != "" {
			m.focusInput(reverseGrid[targetRow][startCol-offset])
			return
		}
		// Then check right side
		if startCol+offset < settingsGridCols && reverseGrid[targetRow][startCol+offset] != "" {
			m.focusInput(reverseGrid[targetRow][startCol+offset])
			return
		}
	}
}

// Flag navigation for Env tab
func (m *model) focusFlag(flagName string) {
	m.focusedFlag = flagName
}

func (m *model) navigateFlags(direction string) {
	flags := envFlagNames

	if m.focusedFlag == "" {
		m.focusFlag(flags[0])
		return
	}

	// Find current flag index
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
		// Left/right toggles the focused flag
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
	return m.settingsInputMap()[inputName]
}

// ------- Run command -------
func (m *model) startRunCmd() tea.Cmd {
	// hydrate cfg from inputs
	m.hydrateConfigFromInputs()

	if m.selectedPRD == "" {
		m.errMsg = "Select a PRD first (PRD tab)"
		return func() tea.Msg { return statusMsg{note: "No PRD selected"} }
	}
	if err := m.preflightChecks(); err != nil {
		m.errMsg = err.Error()
		return func() tea.Msg { return statusMsg{note: err.Error()} }
	}
	if err := config.Save(m.cfg); err != nil {
		m.errMsg = "Failed to save config: " + err.Error()
		return func() tea.Msg { return statusMsg{note: "Config save failed"} }
	}

	// fresh log channel per run (owned/closed by the run goroutine)
	m.logCh = make(chan runner.Line, 2048)
	ch := m.logCh // capture immutable handle for this run
	m.logBuf = nil
	m.logs.SetContent("")
	m.resetRunDashboard()
	m.runResult = make(chan error, 1)
	m.tab = tabRun

	ctx, cancel := context.WithCancel(context.Background())
	m.cancel = cancel

	go func(logCh chan runner.Line, resultCh chan error) {
		o := runner.Options{
			Config:        m.cfg,
			PRDPath:       m.selectedPRD,
			InitialPrompt: m.prompt.Value(),
			Logs:          logCh,
		}
		err := o.Run(ctx)
		if err != nil && err != context.Canceled {
			select {
			case logCh <- runner.Line{Time: time.Now(), Text: "run error: " + err.Error(), Err: true}:
			default:
			}
		}
		select {
		case resultCh <- err:
		default:
		}
		close(resultCh)
	}(ch, m.runResult)

	return tea.Batch(func() tea.Msg { return runStartMsg{} }, m.readLogs(), m.waitRunResult())
}

func (m *model) preflightChecks() error {
	if strings.TrimSpace(m.cfg.PythonCommand) == "" {
		return errors.New("Set Python command in Settings")
	}
	if _, err := exec.LookPath(m.cfg.PythonCommand); err != nil {
		return fmt.Errorf("Python command not found on PATH: %w", err)
	}
	if strings.TrimSpace(m.cfg.PythonScript) == "" {
		return errors.New("Set Python script path in Settings")
	}
	scriptPath := m.cfg.PythonScript
	if !filepath.IsAbs(scriptPath) {
		if abs, err := filepath.Abs(scriptPath); err == nil {
			scriptPath = abs
		}
	}
	if info, err := os.Stat(scriptPath); err != nil || info.IsDir() {
		if err != nil {
			return fmt.Errorf("Python script not found: %w", err)
		}
		return fmt.Errorf("Python script path points to directory: %s", scriptPath)
	}
	if _, err := os.Stat(m.selectedPRD); err != nil {
		return fmt.Errorf("Selected PRD missing: %w", err)
	}
	return nil
}

func (m *model) hydrateConfigFromInputs() {
	m.cfg.RepoPath = strings.TrimSpace(m.inRepo.Value())
	m.cfg.BaseBranch = strings.TrimSpace(m.inBase.Value())
	m.cfg.Branch = strings.TrimSpace(m.inBranch.Value())
	m.cfg.CodexModel = strings.TrimSpace(m.inCodexModel.Value())
	m.cfg.PythonCommand = strings.TrimSpace(m.inPyCmd.Value())
	m.cfg.PythonScript = strings.TrimSpace(m.inPyScript.Value())
	m.cfg.ExecutorPolicy = strings.TrimSpace(m.inPolicy.Value())
	m.cfg.Timings.WaitMinutes = atoiSafe(m.inWaitMin.Value())
	m.cfg.Timings.ReviewPollSeconds = atoiSafe(m.inPollSec.Value())
	m.cfg.Timings.IdleGraceMinutes = atoiSafe(m.inIdleMin.Value())
	m.cfg.Timings.MaxLocalIters = atoiSafe(m.inMaxIters.Value())
	m.cfg.Flags.AllowUnsafe = m.flagAllowUnsafe
	m.cfg.Flags.DryRun = m.flagDryRun
	m.cfg.Flags.SyncGit = m.flagSyncGit
	m.cfg.Flags.InfiniteReviews = m.flagInfinite
	m.cfg.RunPhases.Local = m.runLocal
	m.cfg.RunPhases.PR = m.runPR
	m.cfg.RunPhases.ReviewFix = m.runReview
	m.cfg.PhaseExecutors.Implement = strings.TrimSpace(m.inExecImpl.Value())
	m.cfg.PhaseExecutors.Fix = strings.TrimSpace(m.inExecFix.Value())
	m.cfg.PhaseExecutors.PR = strings.TrimSpace(m.inExecPR.Value())
	m.cfg.PhaseExecutors.ReviewFix = strings.TrimSpace(m.inExecRev.Value())
}

func (m *model) saveConfig() tea.Cmd {
	m.hydrateConfigFromInputs()
	if err := config.Save(m.cfg); err != nil {
		return func() tea.Msg { return statusMsg{note: "Config save failed: " + err.Error()} }
	}
	return func() tea.Msg { return statusMsg{note: "Config saved"} }
}

func (m *model) resetRunDashboard() {
	m.runFeedBuf = nil
	m.runFeed.SetContent("")
	m.runPhase = ""
	m.runCurrent = ""
	m.runPrevious = ""
	m.runLastComplete = ""
	m.runIterCurrent = 0
	m.runIterTotal = 0
	m.runIterLabel = ""
}

func (m *model) setRunCurrent(action string) {
	action = strings.TrimSpace(action)
	if action == "" {
		return
	}
	if m.runCurrent != action {
		if m.runCurrent != "" {
			m.runPrevious = m.runCurrent
		}
		m.runCurrent = action
	}
	if m.runPhase == "" {
		m.runPhase = "Running"
	}
}

func (m *model) handleRunFeedLine(displayLine, rawLine string) {
	m.runFeedBuf = append(m.runFeedBuf, displayLine)
	if len(m.runFeedBuf) > 800 {
		m.runFeedBuf = m.runFeedBuf[len(m.runFeedBuf)-800:]
	}
	m.runFeed.SetContent(strings.Join(m.runFeedBuf, "\n"))
	m.runFeed.GotoBottom()
	m.consumeRunSummary(rawLine)
}

func (m *model) consumeRunSummary(rawLine string) {
	text := strings.TrimSpace(rawLine)
	if text == "" {
		return
	}

	if match := reIterationHeader.FindStringSubmatch(text); match != nil {
		cur, _ := strconv.Atoi(match[1])
		m.runIterCurrent = cur
		if match[2] != "" {
			if total, err := strconv.Atoi(match[2]); err == nil {
				m.runIterTotal = total
			} else {
				m.runIterTotal = 0
			}
		} else {
			m.runIterTotal = 0
		}
		label := strings.TrimSpace(match[3])
		m.runIterLabel = label
		countLabel := fmt.Sprintf("Iteration %d", cur)
		if m.runIterTotal > 0 {
			countLabel = fmt.Sprintf("Iteration %d/%d", cur, m.runIterTotal)
		}
		m.runPhase = countLabel
		if label != "" {
			m.setRunCurrent(label)
		} else {
			m.setRunCurrent(countLabel)
		}
		return
	}

	if match := reSectionHeader.FindStringSubmatch(text); match != nil {
		section := strings.TrimSpace(match[1])
		if section != "" {
			m.runPhase = section
			m.setRunCurrent(section)
		}
		return
	}

	if strings.HasPrefix(text, "→") {
		action := strings.TrimSpace(strings.TrimPrefix(text, "→"))
		if action != "" {
			m.setRunCurrent(action)
		}
		return
	}

	if strings.HasPrefix(text, "✓") {
		done := strings.TrimSpace(strings.TrimPrefix(text, "✓"))
		if done == "" {
			done = strings.TrimSpace(text)
		}
		m.runLastComplete = done
		m.setRunCurrent(done)
		return
	}

	if strings.HasPrefix(text, "⚠️") {
		m.setRunCurrent(text)
		return
	}

	lower := strings.ToLower(text)
	switch {
	case strings.HasPrefix(lower, "no "):
		m.setRunCurrent(text)
	case strings.HasPrefix(lower, "stopping"):
		m.setRunCurrent(text)
	case strings.HasPrefix(lower, "opened pr"):
		m.setRunCurrent(text)
	case strings.HasSuffix(lower, "done.") || strings.Contains(lower, "done."):
		m.setRunCurrent(text)
	case strings.Contains(lower, "review loop"):
		m.setRunCurrent(text)
	case strings.Contains(lower, "process finished"):
		m.setRunCurrent(text)
	case strings.HasPrefix(lower, "final tasks_left"):
		m.setRunCurrent(text)
	}
}

func (m model) readLogs() tea.Cmd {
	if m.logCh == nil {
		return nil
	}
	ch := m.logCh
	return func() tea.Msg {
		line, ok := <-ch
		if !ok {
			// log channel closed - stop the read loop cleanly; runner handles process completion messaging
			return nil
		}
		return logLineMsg{line: line}
	}
}

func (m model) waitRunResult() tea.Cmd {
	if m.runResult == nil {
		return nil
	}
	ch := m.runResult
	return func() tea.Msg {
		err, ok := <-ch
		if !ok {
			return nil
		}
		return runFinishMsg{err: err}
	}
}

// ------- View -------
func (m model) View() string {
	var b strings.Builder
	b.WriteString(titleStyle.Render("autodev — PRD→PR TUI") + "\n")
	for i, name := range tabNames {
		if tab(i) == m.tab {
			b.WriteString(tabActive.Render(fmt.Sprintf("[%d] %s  ", i+1, name)))
		} else {
			b.WriteString(tabInactive.Render(fmt.Sprintf("[%d] %s  ", i+1, name)))
		}
	}
	b.WriteString("\n\n")

	switch m.tab {
	case tabRun:
		if m.running || len(m.runFeedBuf) > 0 {
			b.WriteString(sectionTitle.Render("Run Dashboard") + "\n")
			if m.selectedPRD == "" {
				b.WriteString("PRD: (none selected)\n")
			} else {
				b.WriteString("PRD: " + m.selectedPRD + "\n")
			}

			b.WriteString(fmt.Sprintf("Executor policy: %s\n", m.cfg.ExecutorPolicy))
			b.WriteString(fmt.Sprintf("Phases -> local:%v pr:%v review_fix:%v\n", m.runLocal, m.runPR, m.runReview))

			switch {
			case m.running:
				b.WriteString(okStyle.Render("Status: Running (Ctrl+C to stop)") + "\n")
			case m.errMsg != "":
				b.WriteString(errorStyle.Render("Status: Error: "+m.errMsg) + "\n")
			case m.status != "":
				b.WriteString("Status: " + m.status + "\n")
			default:
				b.WriteString("Status: Idle\n")
			}

			phase := m.runPhase
			if phase == "" {
				if m.running {
					phase = "Preparing..."
				} else {
					phase = "Idle"
				}
			}
			current := m.runCurrent
			if current == "" {
				if m.running {
					current = "Awaiting updates..."
				} else {
					current = "Idle"
				}
			}
			previous := m.runPrevious
			if previous == "" {
				previous = "(none)"
			}
			lastComplete := m.runLastComplete
			if lastComplete == "" {
				lastComplete = "(none)"
			}

			iteration := "(none)"
			if m.runIterCurrent > 0 || m.runIterLabel != "" {
				if m.runIterCurrent > 0 {
					if m.runIterTotal > 0 {
						iteration = fmt.Sprintf("%d/%d", m.runIterCurrent, m.runIterTotal)
					} else {
						iteration = fmt.Sprintf("%d", m.runIterCurrent)
					}
				} else {
					iteration = ""
				}
				if m.runIterLabel != "" {
					if iteration != "" {
						iteration = fmt.Sprintf("%s - %s", iteration, m.runIterLabel)
					} else {
						iteration = m.runIterLabel
					}
				}
			}

			b.WriteString(fmt.Sprintf("Phase: %s\n", phase))
			b.WriteString(fmt.Sprintf("Current: %s\n", current))
			b.WriteString(fmt.Sprintf("Previous: %s\n", previous))
			b.WriteString(fmt.Sprintf("Last Complete: %s\n", lastComplete))
			b.WriteString(fmt.Sprintf("Iteration: %s\n\n", iteration))

			b.WriteString(sectionTitle.Render("Live Feed") + "\n")
			b.WriteString(m.runFeed.View() + "\n")

			if m.running {
				b.WriteString(helpStyle.Render("Ctrl+C to cancel · ↑/↓ scroll feed · PgUp/PgDn jump · Home/End align\n"))
			} else {
				b.WriteString(helpStyle.Render("Press Enter to start a new run · ↑/↓ scroll feed · PgUp/PgDn jump · Home/End align\n"))
			}
		} else {
			b.WriteString(sectionTitle.Render("Run") + "\n")
			if m.selectedPRD == "" {
				b.WriteString("PRD: (none selected)\n")
			} else {
				b.WriteString("PRD: " + m.selectedPRD + "\n")
			}
			b.WriteString(fmt.Sprintf("Executor policy: %s\n", m.cfg.ExecutorPolicy))
			b.WriteString(fmt.Sprintf("Phases -> local:%v pr:%v review_fix:%v\n", m.runLocal, m.runPR, m.runReview))
			if m.errMsg != "" {
				b.WriteString(errorStyle.Render("Status: Error: "+m.errMsg) + "\n")
			} else if m.status != "" {
				b.WriteString("Status: " + m.status + "\n")
			} else {
				b.WriteString("Status: Idle\n")
			}
			b.WriteString("\nPress Enter to start a run. This view switches into a live dashboard once the automation begins.\n")
		}

	case tabPRD:
		b.WriteString(sectionTitle.Render("PRD selection") + "\n")
		b.WriteString(m.prdList.View())
		b.WriteString("\nSelected: " + m.selectedPRD + "\n")
		b.WriteString("Tags: " + strings.Join(m.tags, ", ") + "\n")
		if m.tagInput.Focused() {
			b.WriteString("Add tag: " + m.tagInput.View() + "\n")
			b.WriteString("Press Enter to add tag, Esc to cancel\n")
		} else {
			b.WriteString("Keys: ↑/↓ select · ←/→ prev/next · / filter · Enter choose · t add-tag · backspace drop-last · s save-tags · r rescan\n")
		}

	case tabSettings:
		b.WriteString(sectionTitle.Render("Settings") + "\n")
		b.WriteString(m.inRepo.View() + "\n")
		b.WriteString(m.inBase.View() + "\n")
		b.WriteString(m.inBranch.View() + "\n")
		b.WriteString(m.inCodexModel.View() + "\n")
		b.WriteString(m.inPyCmd.View() + "\n")
		b.WriteString(m.inPyScript.View() + "\n")
		b.WriteString(m.inPolicy.View() + "\n")
		b.WriteString(m.inExecImpl.View() + "  " + m.inExecFix.View() + "  " + m.inExecPR.View() + "  " + m.inExecRev.View() + "\n")
		b.WriteString(m.inWaitMin.View() + "  ")
		b.WriteString(m.inPollSec.View() + "  ")
		b.WriteString(m.inIdleMin.View() + "  ")
		b.WriteString(m.inMaxIters.View() + "\n")

		if m.focusedInput != "" {
			b.WriteString("\n" + okStyle.Render("Input focused: "+m.focusedInput+" (↑/↓/←/→ to navigate, Enter/Esc to unfocus)") + "\n")
		} else {
			b.WriteString("\nKeys: ↑/↓/←/→ to navigate · Enter to focus first input · s to save · 1-6,? to switch tabs\n")
		}

	case tabEnv:
		b.WriteString(sectionTitle.Render("Env & Flags") + "\n")

		// Render phases with focus indication
		localStyle := lipgloss.NewStyle()
		if m.focusedFlag == "local" {
			localStyle = localStyle.Background(lipgloss.Color("240"))
		}
		prStyle := lipgloss.NewStyle()
		if m.focusedFlag == "pr" {
			prStyle = prStyle.Background(lipgloss.Color("240"))
		}
		reviewStyle := lipgloss.NewStyle()
		if m.focusedFlag == "review" {
			reviewStyle = reviewStyle.Background(lipgloss.Color("240"))
		}

		b.WriteString("Phases: " + localStyle.Render("[L] Local="+fmt.Sprint(m.runLocal)) + "  " +
			prStyle.Render("[P] PR="+fmt.Sprint(m.runPR)) + "  " +
			reviewStyle.Render("[R] ReviewFix="+fmt.Sprint(m.runReview)) + "\n")

		// Render flags with focus indication
		unsafeStyle := lipgloss.NewStyle()
		if m.focusedFlag == "unsafe" {
			unsafeStyle = unsafeStyle.Background(lipgloss.Color("240"))
		}
		dryrunStyle := lipgloss.NewStyle()
		if m.focusedFlag == "dryrun" {
			dryrunStyle = dryrunStyle.Background(lipgloss.Color("240"))
		}
		syncgitStyle := lipgloss.NewStyle()
		if m.focusedFlag == "syncgit" {
			syncgitStyle = syncgitStyle.Background(lipgloss.Color("240"))
		}
		infiniteStyle := lipgloss.NewStyle()
		if m.focusedFlag == "infinite" {
			infiniteStyle = infiniteStyle.Background(lipgloss.Color("240"))
		}

		b.WriteString(unsafeStyle.Render(fmt.Sprintf("[a] Allow Unsafe: %v (AUTO_PRD_ALLOW_UNSAFE_EXECUTION=1 and CI=1)", m.flagAllowUnsafe)) + "\n")
		b.WriteString(dryrunStyle.Render(fmt.Sprintf("[d] Dry Run:     %v", m.flagDryRun)) + "\n")
		b.WriteString(syncgitStyle.Render(fmt.Sprintf("[g] Sync Git:    %v", m.flagSyncGit)) + "\n")
		b.WriteString(infiniteStyle.Render(fmt.Sprintf("[i] Infinite Reviews: %v", m.flagInfinite)) + "\n")

		if m.focusedFlag != "" {
			b.WriteString("\n" + okStyle.Render("Flag focused: "+m.focusedFlag+" (↑/↓ navigate, ←/→/Enter toggle, Esc unfocus)") + "\n")
		} else {
			b.WriteString("\n" + lipgloss.NewStyle().Faint(true).Render("Arrow keys to navigate · Enter/←/→ toggle · Letter keys for direct toggle · s save"))
		}

	case tabPrompt:
		b.WriteString(sectionTitle.Render("Initial Prompt (optional)") + "\n")
		b.WriteString(m.prompt.View() + "\n")
		if m.prompt.Focused() {
			b.WriteString(okStyle.Render("Text area focused (Esc to unfocus)") + "\n")
		} else {
			b.WriteString("Press Enter to edit text, Esc to unfocus\n")
		}

	case tabLogs:
		b.WriteString(sectionTitle.Render("Logs") + "\n")
		b.WriteString(m.logs.View() + "\n")

	case tabHelp:
		b.WriteString(sectionTitle.Render("Help") + "\n")
		b.WriteString("• PRD tab: ↑/↓ navigate list · Enter select · t tag · s save · r rescan\n")
		b.WriteString("• Settings: ↑/↓/←/→ navigate inputs · Enter to focus · Esc to unfocus · s save\n")
		b.WriteString("• Prompt: Arrow keys to focus/edit · Enter for newline · Esc to finish\n")
		b.WriteString("• Env: ↑/↓ navigate flags · ←/→/Enter toggle focused · Letter keys direct toggle · s save\n")
		b.WriteString("• Logs: ↑/↓ scroll · PgUp/PgDown page · Home/End top/bottom\n")
		b.WriteString("• Run: Enter to start · Ctrl+C to stop\n")
		b.WriteString("\nGlobal: 1-6 tabs · ? help · q quit · Ctrl+C force quit\n")
		b.WriteString("\nSee NAVIGATION_GUIDE.md for detailed instructions.")
	}
	return b.String()
}

func atoiSafe(s string) int {
	s = strings.TrimSpace(s)
	if s == "" {
		return 0
	}
	var n int
	fmt.Sscanf(s, "%d", &n)
	return n
}
