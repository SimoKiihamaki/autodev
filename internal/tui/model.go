package tui

import (
	"context"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/SimoKiihamaki/autodev/internal/config"
	"github.com/SimoKiihamaki/autodev/internal/runner"
	"github.com/SimoKiihamaki/autodev/internal/utils"
	"github.com/charmbracelet/bubbles/list"
	"github.com/charmbracelet/bubbles/textarea"
	"github.com/charmbracelet/bubbles/textinput"
	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
)

const runScrollHelp = "↑/↓ scroll · PgUp/PgDn jump · Home/End align · f toggle follow"

// CleanupFinalModel performs cleanup on the final model returned by p.Run().
// It handles the type assertion and calls the model's cleanup logic.
// This is the recommended way to clean up resources after the TUI exits.
func CleanupFinalModel(finalModel interface{}) {
	if m, ok := finalModel.(model); ok {
		m.cleanup()
	}
}

// cleanup performs graceful shutdown without modifying the receiver.
// Called via CleanupFinalModel after the program exits.
func (m model) cleanup() {
	// Cancel any running process
	if m.cancel != nil {
		m.cancel()
	}
	// Close any open log file
	m.closeLogFile("cleanup")
}

// Flag name constants for TUI toggle labels and internal state tracking.
// These are display/UI identifiers, NOT the phase names sent to the Python CLI.
//
// Phase name mapping (TUI → Python CLI):
//   - FlagNameLocal  ("local")  → --phases local
//   - FlagNamePR     ("pr")     → --phases pr
//   - FlagNameReview ("review") → --phases review_fix  (NOTE: different name!)
//
// The actual mapping is implemented in runner.go BuildArgs() which uses
// cfg.RunPhases.ReviewFix → "review_fix" for the --phases CLI argument.
// See tools/auto_prd/constants.py VALID_PHASES for Python-side definitions.
const (
	FlagNameLocal    = "local"
	FlagNamePR       = "pr"
	FlagNameReview   = "review" // Maps to Python phase "review_fix"
	FlagNameUnsafe   = "unsafe"
	FlagNameDryRun   = "dryrun"
	FlagNameSyncGit  = "syncgit"
	FlagNameInfinite = "infinite"
)

type item struct {
	title, desc string
	path        string
	filter      string
}

type executorChoice string

const (
	executorCodex  executorChoice = "codex"
	executorClaude executorChoice = "claude"
)

var executorChoices = []executorChoice{executorCodex, executorClaude}

var quitOptions = []string{"Save", "Discard", "Cancel"}

type toastState struct {
	id        uint64
	message   string
	expiresAt time.Time
}

func (c executorChoice) configValue() string {
	switch c {
	case executorClaude:
		return string(executorClaude)
	default:
		return string(executorCodex)
	}
}

func newItem(title, desc, path string) item {
	parts := []string{title, desc, path}
	filtered := make([]string, 0, len(parts))
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part != "" {
			filtered = append(filtered, part)
		}
	}
	return item{title: title, desc: desc, path: path, filter: strings.Join(filtered, " ")}
}

func (i item) Title() string       { return i.title }
func (i item) Description() string { return i.desc }
func (i item) FilterValue() string {
	return i.filter
}

type model struct {
	tabIndex      int
	tabs          []string
	cfg           config.Config
	defaultConfig config.Config
	status        string
	errMsg        string

	savedConfig config.Config
	dirty       bool
	termWidth   int // Terminal width for responsive layouts

	keys     KeyMap
	typing   bool
	showHelp bool

	prdList      list.Model
	selectedPRD  string
	tags         []string
	tagInput     textinput.Model
	prdPreview   viewport.Model // Markdown preview viewport
	prdPaneRatio float64        // Left pane width ratio (default 0.4)

	inRepo          textinput.Model
	inBase          textinput.Model
	inBranch        textinput.Model
	inCodexModel    textinput.Model
	inPyCmd         textinput.Model
	inPyScript      textinput.Model
	inPolicy        textinput.Model
	inWaitMin       textinput.Model
	inPollSec       textinput.Model
	inIdleMin       textinput.Model
	inMaxIters      textinput.Model
	inCodexTimeout  textinput.Model
	inClaudeTimeout textinput.Model

	settingsInputs map[string]*textinput.Model

	execLocalChoice  executorChoice
	execPRChoice     executorChoice
	execReviewChoice executorChoice

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
	followLogs        bool
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

	quitConfirmActive bool
	quitConfirmIndex  int
	quitAfterSave     bool

	lastSaveErr error
	lastRunErr  error

	toast    *toastState
	toastSeq uint64

	// Tracker state for Progress tab (loaded asynchronously)
	tracker       *Tracker
	trackerErr    error
	trackerLoaded bool
}

// settingsInputNames defines the navigation order for Settings inputs; keep the
// explicit sequence so keyboard traversal remains predictable.
var settingsInputNames = []string{
	"repo", "base", "branch", "codex", "pycmd", "pyscript", "policy",
	"waitmin", "pollsec", "idlemin", "maxiters", "codextimeout", "claudetimeout",
}

var envFlagNames = []string{
	FlagNameLocal,
	FlagNamePR,
	FlagNameReview,
	FlagNameUnsafe,
	FlagNameDryRun,
	FlagNameSyncGit,
	FlagNameInfinite,
}

func New() model {
	// Load config; warnings are logged internally by config.Load().
	// The function always returns a valid config, falling back to defaults.
	cfg := config.Load()

	m := model{tabIndex: 0, cfg: cfg}
	m.defaultConfig = config.Defaults()
	m.savedConfig = cfg.Clone()
	m.tabs = defaultTabIDs()
	m.keys = DefaultKeyMap()
	m.normalizeLogLevel()

	delegate := list.NewDefaultDelegate()
	delegate.ShowDescription = true
	m.prdList = list.New([]list.Item{}, delegate, 0, 0)
	m.prdList.Title = "Select a PRD (.md)"
	m.prdList.SetShowHelp(false)
	m.prdList.SetFilteringEnabled(true)
	m.prdList.DisableQuitKeybindings()

	// Initialize PRD preview viewport
	m.prdPreview = viewport.New(60, 20)
	m.prdPreview.SetContent("")
	m.prdPaneRatio = 0.4

	m.initSettingsInputs()
	m.initExecutorChoices()

	m.runLocal = cfg.RunPhases.Local
	m.runPR = cfg.RunPhases.PR
	m.runReview = cfg.RunPhases.ReviewFix
	// FollowLogs may be nil if not set; default to true for safety and persist.
	follow := true
	if cfg.FollowLogs != nil {
		follow = *cfg.FollowLogs
	} else {
		cfg.FollowLogs = utils.BoolPtr(follow)
	}
	m.followLogs = follow
	m.runFeedAutoFollow = follow

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

	m.resetRunDashboard()
	m.resolvePythonScript(true)
	m.updateDirtyState()

	return m
}

func (m *model) flash(msg string, ttl time.Duration) tea.Cmd {
	msg = strings.TrimSpace(msg)
	if msg == "" {
		return nil
	}
	if ttl <= 0 {
		// Use configurable toast TTL from config, with fallback to default
		if m.cfg.UI.ToastTTLMs != nil && *m.cfg.UI.ToastTTLMs > 0 {
			ttl = time.Duration(*m.cfg.UI.ToastTTLMs) * time.Millisecond
		} else {
			ttl = time.Duration(config.DefaultToastTTLMs) * time.Millisecond
		}
	}
	m.toastSeq++
	id := m.toastSeq
	m.toast = &toastState{
		id:        id,
		message:   msg,
		expiresAt: time.Now().Add(ttl),
	}
	return tea.Tick(ttl, func(time.Time) tea.Msg {
		return toastExpiredMsg{id: id}
	})
}

func (m *model) resetToDefaults() tea.Cmd {
	base := m.defaultConfig.Clone()
	m.cfg = base
	m.initSettingsInputs()
	m.initExecutorChoices()

	m.runLocal = base.RunPhases.Local
	m.runPR = base.RunPhases.PR
	m.runReview = base.RunPhases.ReviewFix
	m.followLogs = *base.FollowLogs
	m.runFeedAutoFollow = *base.FollowLogs

	m.flagAllowUnsafe = base.Flags.AllowUnsafe
	m.flagDryRun = base.Flags.DryRun
	m.flagSyncGit = base.Flags.SyncGit
	m.flagInfinite = base.Flags.InfiniteReviews

	m.tags = nil
	m.tagInput.SetValue("")
	m.prompt.SetValue("")
	m.focusedInput = ""
	m.focusedFlag = ""
	m.blurAllInputs()
	m.refreshTypingState()
	m.normalizeLogLevel()
	m.updateDirtyState()

	note := "Configuration reset to defaults"
	m.status = note
	if flash := m.flash(note, 0); flash != nil {
		return flash
	}
	return nil
}

func mkInput(placeholder, value string, width int) textinput.Model {
	ti := textinput.New()
	ti.Placeholder = placeholder
	ti.SetValue(value)
	ti.Width = width
	return ti
}

func (m *model) initSettingsInputs() {
	cfg := m.cfg

	m.inRepo = mkInput("Repo path", cfg.RepoPath, 60)
	m.inBase = mkInput("Base branch", cfg.BaseBranch, 20)
	m.inBranch = mkInput("Feature branch (optional)", cfg.Branch, 30)
	m.inCodexModel = mkInput("Codex model", cfg.CodexModel, 24)
	m.inPyCmd = mkInput("Python command", cfg.PythonCommand, 20)
	m.inPyScript = mkInput("Python script path", cfg.PythonScript, 80)
	m.inPolicy = mkInput("Executor policy (codex-first|codex-only|claude-only)", cfg.ExecutorPolicy, 28)
	m.inWaitMin = mkInput("Wait minutes", formatIntPtr(cfg.Timings.WaitMinutes), 6)
	m.inPollSec = mkInput("Review poll seconds", formatIntPtr(cfg.Timings.ReviewPollSeconds), 6)
	m.inIdleMin = mkInput("Idle grace minutes", formatIntPtr(cfg.Timings.IdleGraceMinutes), 6)
	m.inMaxIters = mkInput("Max local iters", formatIntPtr(cfg.Timings.MaxLocalIters), 6)
	m.inCodexTimeout = mkInput("Codex timeout (0=none)", formatIntPtr(cfg.Timings.CodexTimeoutSeconds), 8)
	m.inClaudeTimeout = mkInput("Claude timeout (0=none)", formatIntPtr(cfg.Timings.ClaudeTimeoutSeconds), 8)

	m.settingsInputs = map[string]*textinput.Model{
		// repo + git wiring
		"repo":   &m.inRepo,
		"base":   &m.inBase,
		"branch": &m.inBranch,
		"codex":  &m.inCodexModel,

		// executor configuration
		"pycmd":    &m.inPyCmd,
		"pyscript": &m.inPyScript,
		"policy":   &m.inPolicy,

		// timings + iteration caps
		"waitmin":  &m.inWaitMin,
		"pollsec":  &m.inPollSec,
		"idlemin":  &m.inIdleMin,
		"maxiters": &m.inMaxIters,

		// timeouts
		"codextimeout":  &m.inCodexTimeout,
		"claudetimeout": &m.inClaudeTimeout,
	}
}

func (m *model) initExecutorChoices() {
	phase := m.cfg.PhaseExecutors
	// The Local Loop toggle controls both the Implement and Fix phases,
	// so we merge both fields to determine the local executor choice.
	m.execLocalChoice = resolveExecutorChoice(phase.Implement, phase.Fix)
	m.execPRChoice = resolveExecutorChoice(phase.PR)
	m.execReviewChoice = resolveExecutorChoice(phase.ReviewFix)
}

func resolveExecutorChoice(values ...string) executorChoice {
	for _, raw := range values {
		switch strings.ToLower(strings.TrimSpace(raw)) {
		case string(executorClaude):
			return executorClaude
		}
	}
	return executorCodex
}

func (m model) Init() tea.Cmd {
	return m.scanPRDsCmd()
}

// resetLogState resets the log buffer and viewport content to initial state
func (m *model) resetLogState() {
	m.logBuf = nil
	m.logs.SetContent("")
}

func (m *model) refreshTypingState() {
	m.typing = m.hasTypingFocus()
}

func (m *model) hasTypingFocus() bool {
	if m.tagInput.Focused() || m.prompt.Focused() {
		return true
	}
	for _, input := range m.settingsInputs {
		if input != nil && input.Focused() {
			return true
		}
	}
	return m.prdList.FilterState() == list.Filtering
}

func (m *model) SetTyping(on bool) {
	m.typing = on
}

func (m model) IsTyping() bool {
	return m.typing
}

func (m *model) pendingConfigSnapshot() (config.Config, []string) {
	snapshot := m.cfg.Clone()
	invalid, parseErrs := m.populateConfigFromInputs(&snapshot)
	logParseErrors(parseErrs)
	return snapshot, invalid
}

func (m *model) updateDirtyState() {
	snapshot, invalid := m.pendingConfigSnapshot()
	m.dirty = !snapshot.Equal(m.savedConfig) || len(invalid) > 0
}

func (m *model) markSaved() {
	m.savedConfig = m.cfg.Clone()
	m.updateDirtyState()
}

func (m *model) handleSaveShortcut() tea.Cmd {
	if m.currentTabID() == tabIDPRD && strings.TrimSpace(m.selectedPRD) == "" {
		note := "Select a PRD before saving metadata"
		m.status = note
		m.lastSaveErr = fmt.Errorf("save aborted: no PRD selected")
		if flash := m.flash(note, 0); flash != nil {
			return flash
		}
		return nil
	}

	if m.selectedPRD != "" {
		if m.cfg.PRDs == nil {
			m.cfg.PRDs = make(map[string]config.PRDMeta)
		}
		meta := m.cfg.PRDs[m.selectedPRD]
		meta.LastUsed = time.Now()
		m.cfg.PRDs[m.selectedPRD] = meta
	}

	// Let the save result handler set m.status/m.lastSaveErr and flash on success/failure.
	return m.saveConfig()
}

func (m *model) beginQuitConfirm() {
	m.quitConfirmActive = true
	m.quitConfirmIndex = 0
	m.blurAllInputs()
	if m.status == "" {
		m.status = "Unsaved changes detected; choose an option."
	}
}

func (m *model) cancelQuitConfirm() {
	m.quitConfirmActive = false
	m.quitConfirmIndex = 0
}

func (m *model) moveQuitSelection(delta int) {
	if !m.quitConfirmActive {
		return
	}
	count := len(quitOptions)
	if count == 0 {
		return
	}
	newIndex, ok := wrapIndex(m.quitConfirmIndex, delta, count)
	if ok {
		m.quitConfirmIndex = newIndex
	}
}

func (m model) currentTabID() string {
	if len(m.tabs) == 0 || m.tabIndex < 0 || m.tabIndex >= len(m.tabs) {
		return tabIDRun
	}
	return m.tabs[m.tabIndex]
}

func (m model) tabTitleAt(index int) string {
	if index < 0 || index >= len(m.tabs) {
		return ""
	}
	return tabTitle(m.tabs[index])
}

func (m *model) setActiveTabByID(id string) {
	if idx := indexForTabID(m.tabs, id); idx >= 0 {
		m.tabIndex = idx
	}
}

func (m *model) setActiveTabIndex(idx int) bool {
	if idx < 0 || idx >= len(m.tabs) {
		return false
	}
	m.tabIndex = idx
	return true
}

func indexForTabID(tabs []string, id string) int {
	for i, current := range tabs {
		if current == id {
			return i
		}
	}
	return -1
}

func (m model) hasTabID(id string) bool {
	return indexForTabID(m.tabs, id) >= 0
}

// getLastErrorText returns the most recent error text from the model.
// It checks lastRunErr first, then falls back to errMsg, and trims whitespace.
func getLastErrorText(m *model) string {
	if m.lastRunErr != nil {
		return strings.TrimSpace(m.lastRunErr.Error())
	}
	if m.errMsg != "" {
		return strings.TrimSpace(m.errMsg)
	}
	return ""
}

// Cleanup performs graceful shutdown of the model's resources.
// It should be called before exiting the application to ensure:
// - Any running process is cancelled
// - Log channels are properly closed
// - File handles are released
//
// Deprecated: Use CleanupFinalModel() instead for post-Run() cleanup.
// This method is retained for internal use and backwards compatibility.
func (m *model) Cleanup() {
	// Cancel any running process
	if m.cancel != nil {
		m.cancel()
		m.cancel = nil
	}

	// Close the log channel if still open
	// Note: only the sender should close channels, and we're not the sender
	// The logCh is closed by the runner goroutine when it completes

	// Clear large buffers to help GC
	m.logBuf = nil
	m.runFeedBuf = nil

	// Close any open log file (though this is now handled by Python)
	m.closeLogFile("cleanup")
}
