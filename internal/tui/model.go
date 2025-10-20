package tui

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/bubbles/list"
	"github.com/charmbracelet/bubbles/textarea"
	"github.com/charmbracelet/bubbles/textinput"
	"github.com/charmbracelet/bubbles/viewport"
	"github.com/charmbracelet/lipgloss"
	"github.com/example/aprd-tui/internal/config"
	"github.com/example/aprd-tui/internal/runner"
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
	tab         tab
	cfg         config.Config
	cfgSaved    bool
	status      string
	errMsg      string

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

	// Runner
	running bool
	cancel  context.CancelFunc
	logCh   chan runner.Line
}

func New() model {
	cfg, _ := config.Load()
	if cfg.PythonCommand == "" { cfg.PythonCommand = "python3" }
	if cfg.ExecutorPolicy == "" { cfg.ExecutorPolicy = "codex-first" }

	m := model{
		tab:   tabRun,
		cfg:   cfg,
		logCh: make(chan runner.Line, 2048),
	}

	// PRD list
	m.prdList = list.New([]list.Item{}, list.NewDefaultDelegate(), 0, 10)
	m.prdList.Title = "Select a PRD (.md)"
	m.prdList.SetShowHelp(false)
	m.prdList.SetFilteringEnabled(true)

	// Inputs
	m.inRepo = mkInput("Repo path", cfg.RepoPath, 60)
	m.inBase = mkInput("Base branch", cfg.BaseBranch, 20)
	m.inBranch = mkInput("Feature branch (optional)", cfg.Branch, 30)
	m.inCodexModel = mkInput("Codex model", cfg.CodexModel, 24)
	m.inPyCmd = mkInput("Python command", cfg.PythonCommand, 20)
	m.inPyScript = mkInput("Python script path", cfg.PythonScript, 80)
	m.inPolicy = mkInput("Executor policy (codex-first|codex-only|claude-only)", cfg.ExecutorPolicy, 28)
	m.inExecImpl = mkInput("Exec (implement): codex|claude|<empty>", cfg.PhaseExecutors.Implement, 16)
	m.inExecFix  = mkInput("Exec (fix): codex|claude|<empty>", cfg.PhaseExecutors.Fix, 16)
	m.inExecPR   = mkInput("Exec (pr): codex|claude|<empty>", cfg.PhaseExecutors.PR, 16)
	m.inExecRev  = mkInput("Exec (review_fix): codex|claude|<empty>", cfg.PhaseExecutors.ReviewFix, 22)
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

	// Tags
	m.tagInput = mkInput("Add tag", "", 24)

	// Scan PRDs
	m.rescanPRDs()

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
	return tea.Batch(m.scanPRDsCmd(), tea.EnterAltScreen)
}

// ------- PRD scan -------
func (m *model) rescanPRDs() { m.prdList.SetItems([]list.Item{}) }

func (m model) scanPRDsCmd() tea.Cmd {
	return func() tea.Msg {
		var items []list.Item
		cwd, _ := os.Getwd()
		_ = filepath.WalkDir(cwd, func(path string, d os.DirEntry, err error) error {
			if err != nil { return nil }
			if d.IsDir() {
				if strings.Count(path, string(os.PathSeparator)) - strings.Count(cwd, string(os.PathSeparator)) > 4 {
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

// ------- Runner/logs messages -------
type runStartMsg struct{}
type runStopMsg struct{}
type logLineMsg struct{ line runner.Line }
type runErrMsg struct{ err error }
type statusMsg struct{ note string }

// ------- Update -------
func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.KeyMsg:
		switch msg.String() {
		case "ctrl+c":
			if m.running && m.cancel != nil {
				m.cancel()
				return m, func() tea.Msg { return runStopMsg{} }
			}
			return m, tea.Quit
		case "q":
			if m.running { return m, nil }
			return m, tea.Quit
		case "?":
			m.tab = tabHelp; return m, nil
		case "1": m.tab = tabRun
		case "2": m.tab = tabPRD
		case "3": m.tab = tabSettings
		case "4": m.tab = tabEnv
		case "5": m.tab = tabPrompt
		case "6": m.tab = tabLogs
		}

		switch m.tab {
		case tabRun:
			if msg.String() == "enter" {
				if m.running { return m, nil }
				return m, m.startRunCmd()
			}

		case tabPRD:
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
			case "backspace":
				if len(m.tags) > 0 { m.tags = m.tags[:len(m.tags)-1] }
			case "s":
				if m.selectedPRD != "" {
					if m.cfg.PRDs == nil { m.cfg.PRDs = map[string]config.PRDMeta{} }
					meta := m.cfg.PRDs[m.selectedPRD]
					meta.Tags = append([]string{}, m.tags...)
					meta.LastUsed = time.Now()
					m.cfg.PRDs[m.selectedPRD] = meta
					_ = config.Save(m.cfg)
					m.cfgSaved = true
				}
			}
			var cmd tea.Cmd
			m.prdList, cmd = m.prdList.Update(msg)
			return m, cmd

		case tabSettings, tabEnv:
			switch msg.String() {
			case "L": m.runLocal = !m.runLocal
			case "P": m.runPR = !m.runPR
			case "R": m.runReview = !m.runReview
			case "a": m.flagAllowUnsafe = !m.flagAllowUnsafe
			case "d": m.flagDryRun = !m.flagDryRun
			case "g": m.flagSyncGit = !m.flagSyncGit
			case "i": m.flagInfinite = !m.flagInfinite
			case "s":
				m.saveConfig()
				return m, func() tea.Msg { return statusMsg{note: "Config saved"} }
			}
			var cmds []tea.Cmd
			m.inRepo, cmds = appendCmd(m.inRepo, msg, cmds)
			m.inBase, cmds = appendCmd(m.inBase, msg, cmds)
			m.inBranch, cmds = appendCmd(m.inBranch, msg, cmds)
			m.inCodexModel, cmds = appendCmd(m.inCodexModel, msg, cmds)
			m.inPyCmd, cmds = appendCmd(m.inPyCmd, msg, cmds)
			m.inPyScript, cmds = appendCmd(m.inPyScript, msg, cmds)
			m.inPolicy, cmds = appendCmd(m.inPolicy, msg, cmds)
			m.inExecImpl, cmds = appendCmd(m.inExecImpl, msg, cmds)
			m.inExecFix, cmds = appendCmd(m.inExecFix, msg, cmds)
			m.inExecPR, cmds = appendCmd(m.inExecPR, msg, cmds)
			m.inExecRev, cmds = appendCmd(m.inExecRev, msg, cmds)
			m.inWaitMin, cmds = appendCmd(m.inWaitMin, msg, cmds)
			m.inPollSec, cmds = appendCmd(m.inPollSec, msg, cmds)
			m.inIdleMin, cmds = appendCmd(m.inIdleMin, msg, cmds)
			m.inMaxIters, cmds = appendCmd(m.inMaxIters, msg, cmds)
			return m, tea.Batch(cmds...)

		case tabPrompt:
			var cmd tea.Cmd
			m.prompt, cmd = m.prompt.Update(msg)
			return m, cmd

		case tabLogs:
			var cmd tea.Cmd
			m.logs, cmd = m.logs.Update(msg)
			return m, cmd
		}

	case prdScanMsg:
		m.prdList.SetItems(msg.items)
		return m, nil

	case statusMsg:
		m.status = msg.note
		return m, nil

	case runStartMsg:
		m.running = true; m.errMsg = ""; m.status = "Running…"
		return m, nil

	case runStopMsg:
		m.running = false; m.status = "Stopped."
		return m, nil

	case logLineMsg:
		line := msg.line
		prefix := ""
		if line.Err { prefix = "[ERR] " }
		m.logBuf = append(m.logBuf, prefix+line.Text)
		if len(m.logBuf) > 2000 { m.logBuf = m.logBuf[len(m.logBuf)-2000:] }
		m.logs.SetContent(strings.Join(m.logBuf, "\n"))
		// keep reading
		return m, m.readLogs()

	case runErrMsg:
		m.running = false; m.errMsg = msg.err.Error(); m.status = "Error."
		return m, nil
	}
	return m, nil
}

func appendCmd(t textinput.Model, msg tea.Msg, cmds []tea.Cmd) (textinput.Model, []tea.Cmd) {
	ti, cmd := t.Update(msg); cmds = append(cmds, cmd); return ti, cmds
}

// ------- Run command -------
func (m *model) startRunCmd() tea.Cmd {
	// hydrate cfg from inputs
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

	if m.selectedPRD == "" {
		m.errMsg = "Select a PRD first (PRD tab)"
		return func() tea.Msg { return statusMsg{note: "No PRD selected"} }
	}
	if m.cfg.PythonScript == "" {
		m.errMsg = "Set Python script path in Settings"
		return func() tea.Msg { return statusMsg{note: "Missing Python script path"} }
	}
	_ = config.Save(m.cfg)

	ctx, cancel := context.WithCancel(context.Background())
	m.cancel = cancel

	go func() {
		o := runner.Options{
			Config:        m.cfg,
			PRDPath:       m.selectedPRD,
			InitialPrompt: m.prompt.Value(),
			Logs:          m.logCh,
		}
		err := o.Run(ctx)
		if err != nil && err != context.Canceled {
			m.logCh <- runner.Line{Time: time.Now(), Text: "run error: " + err.Error(), Err: true}
		}
		m.logCh <- runner.Line{Time: time.Now(), Text: "process finished", Err: false}
		close(m.logCh)
	}()

	return tea.Batch(func() tea.Msg { return runStartMsg{} }, m.readLogs())
}

func (m model) readLogs() tea.Cmd {
	return func() tea.Msg {
		line, ok := <-m.logCh
		if !ok { return nil }
		return logLineMsg{line: line}
	}
}

// ------- View -------
func (m model) View() string {
	var b strings.Builder
	b.WriteString(titleStyle.Render("aprd — PRD→PR TUI") + "\n")
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
		b.WriteString(sectionTitle.Render("Run") + "\n")
		if m.selectedPRD == "" { b.WriteString("PRD: (none selected)\n") } else { b.WriteString("PRD: " + m.selectedPRD + "\n") }
		b.WriteString(fmt.Sprintf("Executor policy: %s\n", m.cfg.ExecutorPolicy))
		b.WriteString(fmt.Sprintf("Phases -> local:%v pr:%v review_fix:%v\n", m.runLocal, m.runPR, m.runReview))
		if m.running {
			b.WriteString(okStyle.Render("Status: Running (Ctrl+C to stop)") + "\n")
		} else if m.errMsg != "" {
			b.WriteString(errorStyle.Render("Status: Error: " + m.errMsg) + "\n")
		} else if m.status != "" {
			b.WriteString("Status: " + m.status + "\n")
		}
		b.WriteString("\nPress Enter to start.\n")

	case tabPRD:
		b.WriteString(sectionTitle.Render("PRD selection") + "\n")
		b.WriteString(m.prdList.View())
		b.WriteString("\nSelected: " + m.selectedPRD + "\n")
		b.WriteString("Tags: " + strings.Join(m.tags, ", ") + "\n")
		b.WriteString("Keys: ↑/↓ select · Enter choose · t add-tag · backspace drop-last · s save-tags\n")

	case tabSettings:
		b.WriteString(sectionTitle.Render("Settings") + "\n")
		b.WriteString(m.inRepo.View()+"\n")
		b.WriteString(m.inBase.View()+"\n")
		b.WriteString(m.inBranch.View()+"\n")
		b.WriteString(m.inCodexModel.View()+"\n")
		b.WriteString(m.inPyCmd.View()+"\n")
		b.WriteString(m.inPyScript.View()+"\n")
		b.WriteString(m.inPolicy.View()+"\n")
		b.WriteString(m.inExecImpl.View()+"  "+m.inExecFix.View()+"  "+m.inExecPR.View()+"  "+m.inExecRev.View()+"\n")
		b.WriteString(m.inWaitMin.View()+"  ")
		b.WriteString(m.inPollSec.View()+"  ")
		b.WriteString(m.inIdleMin.View()+"  ")
		b.WriteString(m.inMaxIters.View()+"\n")
		b.WriteString("\nPress 's' to save.\n")

	case tabEnv:
		b.WriteString(sectionTitle.Render("Env & Flags") + "\n")
		b.WriteString("Phases: [L] Local="+fmt.Sprint(m.runLocal)+"  [P] PR="+fmt.Sprint(m.runPR)+"  [R] ReviewFix="+fmt.Sprint(m.runReview)+"\n")
		b.WriteString(fmt.Sprintf("[a] Allow Unsafe: %v (AUTO_PRD_ALLOW_UNSAFE_EXECUTION=1 and CI=1)\n", m.flagAllowUnsafe))
		b.WriteString(fmt.Sprintf("[d] Dry Run:     %v\n", m.flagDryRun))
		b.WriteString(fmt.Sprintf("[g] Sync Git:    %v\n", m.flagSyncGit))
		b.WriteString(fmt.Sprintf("[i] Infinite Reviews: %v\n", m.flagInfinite))
		b.WriteString(lipgloss.NewStyle().Faint(true).Render("Toggle with the highlighted keys. Save with 's'."))

	case tabPrompt:
		b.WriteString(sectionTitle.Render("Initial Prompt (optional)")+"\n")
		b.WriteString(m.prompt.View()+"\n")

	case tabLogs:
		b.WriteString(sectionTitle.Render("Logs") + "\n")
		b.WriteString(m.logs.View()+"\n")

	case tabHelp:
		b.WriteString(sectionTitle.Render("Help") + "\n")
		b.WriteString("• PRD tab: pick a Markdown spec. Add tags and save.\n")
		b.WriteString("• Settings & Env: fill values; save with 's'.\n")
		b.WriteString("• Prompt: optional initial instruction.\n")
		b.WriteString("• Run tab: press Enter. Logs stream in the Logs tab.\n")
		b.WriteString("• Quit with 'q'. Stop with Ctrl+C.\n")
		b.WriteString("\nTabs: 1 Run · 2 PRD · 3 Settings · 4 Env · 5 Prompt · 6 Logs · ? Help")
	}
	return b.String()
}

func atoiSafe(s string) int {
	s = strings.TrimSpace(s)
	if s == "" { return 0 }
	var n int
	fmt.Sscanf(s, "%d", &n)
	return n
}
