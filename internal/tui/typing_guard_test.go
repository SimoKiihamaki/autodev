package tui

import (
	"testing"

	"github.com/charmbracelet/bubbles/textarea"
	tea "github.com/charmbracelet/bubbletea"
)

func newModelForTypingGuardTest() model {
	m := newModelForSettingsTest()
	m.keys = DefaultKeyMap()
	m.tabs = defaultTabIDs()
	m.tagInput = mkInput("Add tag", "", 24)
	m.prompt = textarea.New()
	return m
}

func runeKey(r rune) tea.KeyMsg {
	return tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{r}}
}

func altRuneKey(r rune) tea.KeyMsg {
	return tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{r}, Alt: true}
}

func ctrlBackspaceKey() tea.KeyMsg {
	return tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("ctrl+backspace")}
}

func TestTypingGuardBlocksGlobalShortcuts(t *testing.T) {
	t.Parallel()

	keyQuit := runeKey('q')
	keyHelp := runeKey('?')
	keyGotoFirstTab := altRuneKey('1')
	keyResetDefaults := ctrlBackspaceKey()

	t.Run("while_typing_globals_ignored", func(t *testing.T) {
		t.Parallel()
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
		t.Parallel()
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
