package tui

import (
	"context"
	"fmt"
	"os"
	"strings"

	"github.com/SimoKiihamaki/autodev/internal/config"
	"github.com/SimoKiihamaki/autodev/internal/runner"
	"github.com/charmbracelet/bubbles/list"
	"github.com/charmbracelet/bubbles/textarea"
	"github.com/charmbracelet/bubbles/textinput"
	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
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

const runScrollHelp = "↑/↓ scroll · PgUp/PgDn jump · Home/End align · f toggle follow"

var tabNames = []string{"Run", "PRD", "Settings", "Env", "Prompt", "Logs", "Help"}

type item struct {
	title, desc string
	path        string
}

func (i item) Title() string       { return i.title }
func (i item) Description() string { return i.desc }
func (i item) FilterValue() string {
	return strings.TrimSpace(strings.Join([]string{i.title, i.desc, i.path}, " "))
}

type model struct {
	tab    tab
	cfg    config.Config
	status string
	errMsg string

	prdList     list.Model
	selectedPRD string
	tags        []string
	tagInput    textinput.Model

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

	settingsInputs map[string]*textinput.Model

	focusedInput string
	focusedFlag  string

	runLocal  bool
	runPR     bool
	runReview bool

	flagAllowUnsafe bool
	flagDryRun      bool
	flagSyncGit     bool
	flagInfinite    bool

	prompt textarea.Model

	logs        viewport.Model
	logBuf      []string
	logFile     *os.File
	logFilePath string
	logStatus   string

	runFeed           viewport.Model
	runFeedBuf        []string
	runFeedAutoFollow bool
	runPhase          string
	runCurrent        string
	runPrevious       string
	runLastComplete   string
	runIterCurrent    int
	runIterTotal      int
	runIterLabel      string

	running    bool
	cancel     context.CancelFunc
	logCh      chan runner.Line
	runResult  chan error
	cancelling bool
}

var settingsInputNames = []string{
	"repo", "base", "branch", "codex", "pycmd", "pyscript", "policy",
	"execimpl", "execfix", "execpr", "execrev", "waitmin", "pollsec", "idlemin", "maxiters",
}

var envFlagNames = []string{"local", "pr", "review", "unsafe", "dryrun", "syncgit", "infinite"}

func New() model {
	cfg, err := config.Load()
	var loadStatus string
	if err != nil {
		cfg = config.Defaults()
		loadStatus = fmt.Sprintf("Warning: Could not load config (%v), using defaults", err)
	}

	m := model{tab: tabRun, cfg: cfg}
	m.normalizeLogLevel()

	delegate := list.NewDefaultDelegate()
	delegate.ShowDescription = true
	m.prdList = list.New([]list.Item{}, delegate, 0, 0)
	m.prdList.Title = "Select a PRD (.md)"
	m.prdList.SetShowHelp(false)
	m.prdList.SetFilteringEnabled(true)
	m.prdList.DisableQuitKeybindings()

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

	m.settingsInputs = map[string]*textinput.Model{
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

	m.runLocal = cfg.RunPhases.Local
	m.runPR = cfg.RunPhases.PR
	m.runReview = cfg.RunPhases.ReviewFix

	m.flagAllowUnsafe = cfg.Flags.AllowUnsafe
	m.flagDryRun = cfg.Flags.DryRun
	m.flagSyncGit = cfg.Flags.SyncGit
	m.flagInfinite = cfg.Flags.InfiniteReviews

	m.prompt = textarea.New()
	m.prompt.Placeholder = "Optional initial instruction injected above the PRD…"
	m.prompt.CharLimit = 0
	m.prompt.SetWidth(80)
	m.prompt.SetHeight(8)

	m.logs = viewport.New(100, 20)
	m.logs.SetContent("")

	m.runFeed = viewport.New(100, 18)
	m.runFeed.SetContent("")

	m.tagInput = mkInput("Add tag", "", 24)

	m.blurAllInputs()
	m.rescanPRDs()

	if loadStatus != "" {
		m.status = loadStatus
	}

	m.resetRunDashboard()
	m.resolvePythonScript(true)

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

func (m *model) settingsInputMap() map[string]*textinput.Model {
	out := make(map[string]*textinput.Model, len(m.settingsInputs))
	for k, v := range m.settingsInputs {
		out[k] = v
	}
	return out
}
