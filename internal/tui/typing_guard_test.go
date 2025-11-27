package tui

import (
	"testing"

	"github.com/charmbracelet/bubbles/list"
	"github.com/charmbracelet/bubbles/textarea"
	tea "github.com/charmbracelet/bubbletea"
)

func newModelForTypingGuardTest() model {
	m := newModelForSettingsTest()
	m.keys = DefaultKeyMap()
	m.tabs = defaultTabIDs()
	m.tagInput = mkInput("Add tag", "", 24)
	m.prompt = textarea.New()
	delegate := list.NewDefaultDelegate()
	delegate.ShowDescription = true
	m.prdList = list.New([]list.Item{}, delegate, 0, 0)
	m.prdList.SetFilteringEnabled(true)
	m.prdList.DisableQuitKeybindings()
	return m
}

func runeKey(r rune) tea.KeyMsg {
	return tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{r}}
}

func enterKey() tea.KeyMsg {
	return tea.KeyMsg{Type: tea.KeyEnter}
}

func escKey() tea.KeyMsg {
	return tea.KeyMsg{Type: tea.KeyEsc}
}

func ctrlBackspaceKey() tea.KeyMsg {
	return tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("ctrl+backspace")}
}

func TestTypingGuardBlocksGlobalShortcuts(t *testing.T) {
	// NOTE: Do not use t.Parallel() here. The charmbracelet/bubbles library
	// uses internal state (runeutil.sanitizer) that is not goroutine-safe.
	// Running subtests in parallel causes data races when the sanitizer
	// is written during input handling while keys are being normalized.

	keyQuit := runeKey('q')
	keyHelp := runeKey('?')
	keyGotoFirstTab := runeKey('1')
	keyResetDefaults := ctrlBackspaceKey()

	t.Run("while_typing_globals_ignored", func(t *testing.T) {
		// Do not run in parallel - see note above
		m := newModelForTypingGuardTest()
		m.tabIndex = 2
		m.cfg.BaseBranch = "develop"
		m.focusInput("repo")
		if repo := m.settingsInputs["repo"]; repo != nil {
			repo.Focus()
		}
		m.SetTyping(true)
		m.refreshTypingState()

		if !m.IsTyping() {
			var repoFocused bool
			if input := m.settingsInputs["repo"]; input != nil {
				repoFocused = input.Focused()
			}
			t.Fatalf("expected model to report typing state after focusing input (focusedInput=%q, repoFocused=%v)", m.focusedInput, repoFocused)
		}

		if updated, cmd := m.handleKeyMsg(keyQuit); updated.quitConfirmActive {
			t.Fatalf("quit guard activated while typing; want guard to block global action")
		} else if cmd != nil {
			if msg := cmd(); msg != nil {
				if _, ok := msg.(tea.QuitMsg); ok {
					t.Fatalf("quit shortcut emitted tea.QuitMsg while typing")
				}
			}
		}

		if updated, cmd := m.handleKeyMsg(keyHelp); updated.showHelp {
			t.Fatalf("help overlay toggled while typing; expected guard to block")
		} else if cmd != nil {
			if msg := cmd(); msg != nil {
				if _, ok := msg.(tea.QuitMsg); ok {
					t.Fatalf("help shortcut unexpectedly produced tea.QuitMsg while typing")
				}
			}
		}

		if updated, cmd := m.handleKeyMsg(keyGotoFirstTab); updated.tabIndex != m.tabIndex {
			t.Fatalf("tab index changed while typing; got %d want %d", updated.tabIndex, m.tabIndex)
		} else if cmd != nil {
			if msg := cmd(); msg != nil {
				if _, ok := msg.(tea.QuitMsg); ok {
					t.Fatalf("tab navigation shortcut unexpectedly produced tea.QuitMsg while typing")
				}
			}
		}

		if updated, cmd := m.handleKeyMsg(keyResetDefaults); updated.cfg.BaseBranch != m.cfg.BaseBranch {
			t.Fatalf("reset defaults mutated config while typing; got base branch %q want %q", updated.cfg.BaseBranch, m.cfg.BaseBranch)
		} else if cmd != nil {
			if msg := cmd(); msg != nil {
				if _, ok := msg.(tea.QuitMsg); ok {
					t.Fatalf("reset defaults shortcut unexpectedly produced tea.QuitMsg while typing")
				}
			}
		}
	})

	t.Run("when_not_typing_globals_fire", func(t *testing.T) {
		// Do not run in parallel - see note above
		m := newModelForTypingGuardTest()
		m.tabIndex = 2
		m.cfg.BaseBranch = "develop"
		m.blurAllInputs()
		m.SetTyping(false)
		m.refreshTypingState()

		if m.IsTyping() {
			t.Fatalf("expected model to be idle after blurring inputs")
		}

		if updated, cmd := m.handleKeyMsg(keyQuit); cmd == nil {
			t.Fatalf("quit shortcut returned nil command; expected tea.Quit")
		} else {
			if msg := cmd(); msg == nil {
				t.Fatalf("quit command returned nil message; expected tea.QuitMsg")
			} else if _, ok := msg.(tea.QuitMsg); !ok {
				t.Fatalf("quit command produced %T; expected tea.QuitMsg", msg)
			}
			if updated.quitConfirmActive {
				t.Fatalf("quit confirmation activated unexpectedly without unsaved changes")
			}
		}

		if updated, cmd := m.handleKeyMsg(keyHelp); !updated.showHelp {
			t.Fatalf("help overlay did not toggle on when not typing")
		} else if cmd != nil {
			// Help toggles do not return commands, but if the implementation changes,
			// make sure we don't accidentally return a quit message.
			if msg := cmd(); msg != nil {
				if _, ok := msg.(tea.QuitMsg); ok {
					t.Fatalf("help shortcut produced quit message unexpectedly when not typing")
				}
			}
		}

		if updated, cmd := m.handleKeyMsg(keyGotoFirstTab); updated.tabIndex != 0 {
			t.Fatalf("tab navigation did not switch to index 0; got %d", updated.tabIndex)
		} else if cmd != nil {
			if msg := cmd(); msg != nil {
				if _, ok := msg.(tea.QuitMsg); ok {
					t.Fatalf("tab navigation produced quit message unexpectedly when not typing")
				}
			}
		}

		if updated, cmd := m.handleKeyMsg(keyResetDefaults); cmd == nil {
			t.Fatalf("reset defaults shortcut returned nil command; expected tea.Cmd")
		} else if updated.cfg.BaseBranch != updated.defaultConfig.BaseBranch {
			t.Fatalf("reset defaults did not restore defaults; got base branch %q want %q", updated.cfg.BaseBranch, updated.defaultConfig.BaseBranch)
		}
	})
}

func TestNumberKeysSwitchTabsFromPRDTab(t *testing.T) {
	t.Parallel()

	m := newModelForTypingGuardTest()
	m.tabIndex = 1 // PRD tab
	m.blurAllInputs()
	m.SetTyping(false)
	m.refreshTypingState()

	updated, _ := m.handleKeyMsg(runeKey('1'))
	if updated.tabIndex != 0 {
		t.Fatalf("expected number key to switch to tab 0, got %d", updated.tabIndex)
	}
}

func TestNumberKeysSwitchTabsFromPromptWhenNotFocused(t *testing.T) {
	t.Parallel()

	m := newModelForTypingGuardTest()
	m.tabIndex = 4 // prompt tab
	m.prompt.Blur()
	m.blurAllInputs()
	m.SetTyping(false)
	m.refreshTypingState()

	updated, _ := m.handleKeyMsg(runeKey('1'))
	if updated.tabIndex != 0 {
		t.Fatalf("expected number key to switch to tab 0, got %d", updated.tabIndex)
	}
}

func TestPromptFocusBlocksNumberKeys(t *testing.T) {
	t.Parallel()

	m := newModelForTypingGuardTest()
	m.tabIndex = 4 // prompt tab
	m.prompt.Blur()
	m.blurAllInputs()

	var cmd tea.Cmd
	m, cmd = m.handleKeyMsg(enterKey())
	if cmd != nil {
		if msg := cmd(); msg != nil {
			if _, ok := msg.(tea.QuitMsg); ok {
				t.Fatalf("enter unexpectedly produced quit message")
			}
		}
	}
	if !m.prompt.Focused() {
		t.Fatalf("prompt should be focused after enter")
	}

	updated, _ := m.handleKeyMsg(runeKey('1'))
	if updated.tabIndex != m.tabIndex {
		t.Fatalf("number key should not switch tabs while prompt focused; got %d want %d", updated.tabIndex, m.tabIndex)
	}
}

func TestPromptEscReenablesNumberKeys(t *testing.T) {
	t.Parallel()

	m := newModelForTypingGuardTest()
	m.tabIndex = 4
	m, _ = m.handleKeyMsg(enterKey())
	if !m.prompt.Focused() {
		t.Fatalf("prompt should be focused after enter")
	}

	m, _ = m.handleKeyMsg(escKey())
	if m.prompt.Focused() {
		t.Fatalf("prompt should blur after esc")
	}

	updated, _ := m.handleKeyMsg(runeKey('1'))
	if updated.tabIndex != 0 {
		t.Fatalf("expected number key to switch to tab 0 after esc, got %d", updated.tabIndex)
	}
}
