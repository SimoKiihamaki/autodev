package tui

import (
	"sort"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
)

type Action string

const (
	ActQuit      Action = "quit"
	ActInterrupt Action = "interrupt"
	ActHelp      Action = "help"

	ActGotoTab1 Action = "goto_tab_1"
	ActGotoTab2 Action = "goto_tab_2"
	ActGotoTab3 Action = "goto_tab_3"
	ActGotoTab4 Action = "goto_tab_4"
	ActGotoTab5 Action = "goto_tab_5"
	ActGotoTab6 Action = "goto_tab_6"
	ActGotoTab7 Action = "goto_tab_7"
	ActGotoTab8 Action = "goto_tab_8"

	ActConfirm          Action = "confirm"
	ActCancel           Action = "cancel"
	ActTabForward       Action = "tab_forward"
	ActTabBackward      Action = "tab_backward"
	ActNavigateUp       Action = "navigate_up"
	ActNavigateDown     Action = "navigate_down"
	ActNavigateLeft     Action = "navigate_left"
	ActNavigateRight    Action = "navigate_right"
	ActAltNavigateUp    Action = "navigate_alt_up"
	ActAltNavigateDown  Action = "navigate_alt_down"
	ActAltNavigateLeft  Action = "navigate_alt_left"
	ActAltNavigateRight Action = "navigate_alt_right"
	ActPageUp           Action = "page_up"
	ActPageDown         Action = "page_down"
	ActScrollTop        Action = "scroll_top"
	ActScrollBottom     Action = "scroll_bottom"
	ActToggleFollow     Action = "toggle_follow"
	ActCopyError        Action = "copy_error"
	ActFocusTags        Action = "focus_tags"
	ActRescanPRDs       Action = "rescan_prds"
	ActSave             Action = "save"
	ActListBackspace    Action = "list_backspace"
	ActCycleBackward    Action = "cycle_backward"

	ActToggleFlagLocal    Action = "toggle_flag_local"
	ActToggleFlagPR       Action = "toggle_flag_pr"
	ActToggleFlagReview   Action = "toggle_flag_review"
	ActToggleFlagUnsafe   Action = "toggle_flag_unsafe"
	ActToggleFlagDryRun   Action = "toggle_flag_dryrun"
	ActToggleFlagSyncGit  Action = "toggle_flag_syncgit"
	ActToggleFlagInfinite Action = "toggle_flag_infinite"
	ActResetDefaults      Action = "reset_defaults"
	ActRefresh            Action = "refresh"
)

// tabActions maps tab indices to their corresponding actions for single source of truth
var tabActions = []Action{
	ActGotoTab1,
	ActGotoTab2,
	ActGotoTab3,
	ActGotoTab4,
	ActGotoTab5,
	ActGotoTab6,
	ActGotoTab7,
	ActGotoTab8,
}

func gotoTabAction(index int) (Action, bool) {
	if index >= 0 && index < len(tabActions) {
		return tabActions[index], true
	}
	return "", false
}

type KeyCombo struct {
	Key   string
	Alt   bool
	Ctrl  bool
	Shift bool
}

func (kc KeyCombo) String() string {
	parts := make([]string, 0)
	if kc.Ctrl {
		parts = append(parts, "ctrl")
	}
	if kc.Alt {
		parts = append(parts, "alt")
	}
	if kc.Shift {
		parts = append(parts, "shift")
	}
	base := strings.ToLower(kc.Key)
	parts = append(parts, base)
	return strings.Join(parts, "+")
}

func (kc KeyCombo) Display() string {
	parts := make([]string, 0)
	if kc.Ctrl {
		parts = append(parts, "Ctrl")
	}
	if kc.Alt {
		parts = append(parts, "Alt")
	}
	if kc.Shift {
		parts = append(parts, "Shift")
	}
	base := strings.ToLower(kc.Key)
	switch base {
	case "pgup":
		base = "PgUp"
	case "pgdown":
		base = "PgDn"
	case "esc":
		base = "Esc"
	case "home":
		base = "Home"
	case "end":
		base = "End"
	case "tab":
		base = "Tab"
	case " ":
		base = "Space"
	case "enter":
		base = "Enter"
	case "up":
		base = "↑"
	case "down":
		base = "↓"
	case "left":
		base = "←"
	case "right":
		base = "→"
	case "backspace":
		base = "Backspace"
	case "space":
		base = "Space"
	default:
		if len(base) == 1 {
			base = strings.ToUpper(base)
		} else {
			base = strings.ToUpper(base[:1]) + base[1:]
		}
	}
	if len(parts) == 0 {
		return base
	}
	parts = append(parts, base)
	return strings.Join(parts, "+")
}

func (kc KeyCombo) Matches(msg tea.KeyMsg) bool {
	return normalizeCombo(kc) == normalizeMsg(msg)
}

// normalizeCombo returns a canonical "mod+mod+key" form with sorted mods.
func normalizeCombo(kc KeyCombo) string {
	mods := make([]string, 0, 3)
	if kc.Ctrl {
		mods = append(mods, "ctrl")
	}
	if kc.Alt {
		mods = append(mods, "alt")
	}
	if kc.Shift {
		mods = append(mods, "shift")
	}
	sort.Strings(mods)
	base := normalizeBaseKey(strings.ToLower(strings.TrimSpace(kc.Key)))
	if base != "" {
		mods = append(mods, base)
	}
	return strings.Join(mods, "+")
}

// normalizeMsg canonicalizes tea.KeyMsg string form into the same scheme.
func normalizeMsg(msg tea.KeyMsg) string {
	raw := strings.ToLower(strings.TrimSpace(msg.String()))
	parts := strings.Split(raw, "+")
	mods, base := make([]string, 0, 3), ""
	for _, p := range parts {
		p = strings.TrimSpace(p)
		switch p {
		case "ctrl", "alt", "shift":
			mods = append(mods, p)
		default:
			base = normalizeBaseKey(p)
		}
	}
	sort.Strings(mods)
	if base != "" {
		mods = append(mods, base)
	}
	return strings.Join(mods, "+")
}

// normalizeBaseKey maps common aliases and whitespace to a single token.
func normalizeBaseKey(k string) string {
	switch k {
	case " ": // some terms return a single space
		return "space"
	case "space":
		return "space"
	case "pgdn", "pgdown":
		return "pgdown"
	case "pgup":
		return "pgup"
	case "esc", "escape":
		return "esc"
	default:
		return k
	}
}

type KeyMap struct {
	Global          map[Action][]KeyCombo
	PerTab          map[string]map[Action][]KeyCombo
	labels          map[Action]string
	typingSensitive map[Action]bool
}

type HelpEntry struct {
	Action Action
	Label  string
	Combos []KeyCombo
}

func (km KeyMap) GlobalActions(msg tea.KeyMsg) []Action {
	return km.matchingActions(km.Global, msg)
}

func (km KeyMap) TabActions(tabID string, msg tea.KeyMsg) []Action {
	return km.matchingActions(km.PerTab[tabID], msg)
}

func (km KeyMap) matchingActions(source map[Action][]KeyCombo, msg tea.KeyMsg) []Action {
	if len(source) == 0 {
		return nil
	}
	var matches []Action
	for act, combos := range source {
		for _, combo := range combos {
			if combo.Matches(msg) {
				matches = append(matches, act)
				break
			}
		}
	}
	sort.Slice(matches, func(i, j int) bool {
		return string(matches[i]) < string(matches[j])
	})
	return matches
}

func (km KeyMap) Label(act Action) string {
	if label, ok := km.labels[act]; ok {
		return label
	}
	return string(act)
}

func (km KeyMap) IsTypingSensitive(act Action) bool {
	return km.typingSensitive[act]
}

func (km KeyMap) GlobalHelpEntries() []HelpEntry {
	return km.helpEntries(km.Global)
}

func (km KeyMap) HelpEntriesForTab(tabID string) []HelpEntry {
	return km.helpEntries(km.PerTab[tabID])
}

func (km KeyMap) helpEntries(source map[Action][]KeyCombo) []HelpEntry {
	if len(source) == 0 {
		return nil
	}
	entries := make([]HelpEntry, 0, len(source))
	for act, combos := range source {
		if len(combos) == 0 {
			continue
		}
		entry := HelpEntry{
			Action: act,
			Label:  km.Label(act),
			Combos: append([]KeyCombo(nil), combos...),
		}
		entries = append(entries, entry)
	}
	sort.Slice(entries, func(i, j int) bool {
		return entries[i].Label < entries[j].Label
	})
	return entries
}

func DefaultKeyMap() KeyMap {
	ctrl := func(key string) KeyCombo {
		return KeyCombo{Key: key, Ctrl: true}
	}
	alt := func(key string) KeyCombo {
		return KeyCombo{Key: key, Alt: true}
	}
	shift := func(key string) KeyCombo {
		return KeyCombo{Key: key, Shift: true}
	}
	key := func(k string) KeyCombo {
		return KeyCombo{Key: k}
	}

	global := map[Action][]KeyCombo{
		ActQuit:          {key("q")},
		ActInterrupt:     {ctrl("c")},
		ActHelp:          {key("?"), key("f1")},
		ActSave:          {ctrl("s")},
		ActResetDefaults: {ctrl("backspace")},
		ActGotoTab1:      {key("1")},
		ActGotoTab2:      {key("2")},
		ActGotoTab3:      {key("3")},
		ActGotoTab4:      {key("4")},
		ActGotoTab5:      {key("5")},
		ActGotoTab6:      {key("6")},
		ActGotoTab7:      {key("7")},
		ActGotoTab8:      {key("8")},
	}

	perTab := map[string]map[Action][]KeyCombo{
		tabIDRun: {
			ActConfirm:      {key("enter")},
			ActNavigateUp:   {key("up")},
			ActNavigateDown: {key("down")},
			ActPageUp:       {key("pgup")},
			ActPageDown:     {key("pgdown")},
			ActScrollTop:    {key("home")},
			ActScrollBottom: {key("end")},
			ActToggleFollow: {key("f")},
			ActCopyError:    {key("y")},
		},
		tabIDPRD: {
			ActConfirm:       {key("enter")},
			ActFocusTags:     {key("t")},
			ActNavigateLeft:  {key("left")},
			ActNavigateRight: {key("right")},
			ActListBackspace: {key("backspace")},
			ActRescanPRDs:    {key("r")},
			ActCancel:        {key("esc")},
		},
		tabIDSettings: {
			ActCancel:           {key("esc")},
			ActTabForward:       {key("tab")},
			ActTabBackward:      {shift("tab")},
			ActNavigateUp:       {key("up")},
			ActNavigateDown:     {key("down")},
			ActNavigateLeft:     {key("left")},
			ActNavigateRight:    {key("right")},
			ActAltNavigateLeft:  {alt("left")},
			ActAltNavigateRight: {alt("right")},
			ActAltNavigateUp:    {alt("up")},
			ActAltNavigateDown:  {alt("down")},
			ActCycleBackward:    {key(" ")},
		},
		tabIDEnv: {
			ActCancel:             {key("esc")},
			ActNavigateUp:         {key("up")},
			ActNavigateDown:       {key("down")},
			ActNavigateLeft:       {key("left")},
			ActNavigateRight:      {key("right")},
			ActConfirm:            {key("enter")},
			ActToggleFlagLocal:    {key("l")},
			ActToggleFlagPR:       {key("p")},
			ActToggleFlagReview:   {ctrl("r")},
			ActToggleFlagUnsafe:   {key("a")},
			ActToggleFlagDryRun:   {key("d")},
			ActToggleFlagSyncGit:  {key("g")},
			ActToggleFlagInfinite: {key("i")},
		},
		tabIDPrompt: {
			ActConfirm: {key("enter")},
			ActCancel:  {key("esc")},
		},
		tabIDLogs: {
			ActNavigateUp:   {key("up")},
			ActNavigateDown: {key("down")},
			ActPageUp:       {key("pgup")},
			ActPageDown:     {key("pgdown")},
			ActScrollTop:    {key("home")},
			ActScrollBottom: {key("end")},
			ActToggleFollow: {key("f")},
		},
		tabIDProgress: {
			ActRefresh:      {key("u")},
			ActNavigateUp:   {key("up")},
			ActNavigateDown: {key("down")},
		},
		tabIDHelp: {},
	}

	labels := map[Action]string{
		ActQuit:               "Quit",
		ActInterrupt:          "Cancel / Quit",
		ActHelp:               "Toggle help overlay",
		ActGotoTab1:           "Switch to tab 1",
		ActGotoTab2:           "Switch to tab 2",
		ActGotoTab3:           "Switch to tab 3",
		ActGotoTab4:           "Switch to tab 4",
		ActGotoTab5:           "Switch to tab 5",
		ActGotoTab6:           "Switch to tab 6",
		ActGotoTab7:           "Switch to tab 7",
		ActGotoTab8:           "Switch to tab 8",
		ActConfirm:            "Confirm / Activate",
		ActCancel:             "Cancel / Blur",
		ActNavigateUp:         "Move up",
		ActNavigateDown:       "Move down",
		ActNavigateLeft:       "Move left",
		ActNavigateRight:      "Move right",
		ActTabForward:         "Next field",
		ActTabBackward:        "Previous field",
		ActAltNavigateUp:      "Alt move up",
		ActAltNavigateDown:    "Alt move down",
		ActAltNavigateLeft:    "Alt move left",
		ActAltNavigateRight:   "Alt move right",
		ActPageUp:             "Page up",
		ActPageDown:           "Page down",
		ActScrollTop:          "Scroll to top",
		ActScrollBottom:       "Scroll to bottom",
		ActToggleFollow:       "Toggle follow logs",
		ActCopyError:          "Copy last error",
		ActFocusTags:          "Focus tag input",
		ActRescanPRDs:         "Rescan PRDs",
		ActSave:               "Save config",
		ActResetDefaults:      "Reset to defaults",
		ActListBackspace:      "Backspace",
		ActCycleBackward:      "Cycle backward",
		ActToggleFlagLocal:    "Toggle Local",
		ActToggleFlagPR:       "Toggle PR",
		ActToggleFlagReview:   "Toggle Review Fix",
		ActToggleFlagUnsafe:   "Toggle Allow Unsafe",
		ActToggleFlagDryRun:   "Toggle Dry Run",
		ActToggleFlagSyncGit:  "Toggle Sync Git",
		ActToggleFlagInfinite: "Toggle Infinite Reviews",
		ActRefresh:            "Refresh",
	}

	typingSensitive := map[Action]bool{
		ActQuit:          true,
		ActHelp:          true,
		ActGotoTab1:      true,
		ActGotoTab2:      true,
		ActGotoTab3:      true,
		ActGotoTab4:      true,
		ActGotoTab5:      true,
		ActGotoTab6:      true,
		ActGotoTab7:      true,
		ActGotoTab8:      true,
		ActResetDefaults: true,
	}

	return KeyMap{
		Global:          global,
		PerTab:          perTab,
		labels:          labels,
		typingSensitive: typingSensitive,
	}
}
