package tui

import (
	"strings"
	"testing"
	"unicode"
)

type keyUsage struct {
	action Action
	tabID  string
}

func isNavigationAction(act Action) bool {
	switch act {
	case ActNavigateUp,
		ActNavigateDown,
		ActNavigateLeft,
		ActNavigateRight,
		ActAltNavigateUp,
		ActAltNavigateDown,
		ActAltNavigateLeft,
		ActAltNavigateRight,
		ActPageUp,
		ActPageDown,
		ActScrollTop,
		ActScrollBottom,
		ActTabForward,
		ActTabBackward,
		ActConfirm,
		ActCancel:
		return true
	default:
		return false
	}
}

func TestDefaultKeyMapHasNoSingleLetterConflicts(t *testing.T) {
	t.Parallel()
	keyMap := DefaultKeyMap()
	seen := make(map[string]keyUsage)

	for _, tabID := range tabIDOrder {
		actions := keyMap.PerTab[tabID]
		if len(actions) == 0 {
			continue
		}

		for action, combos := range actions {
			for _, combo := range combos {
				if combo.Alt || combo.Ctrl || combo.Shift {
					continue
				}

				if isNavigationAction(action) {
					continue
				}

				key := strings.ToLower(combo.Key)
				if key == "" {
					continue
				}

				runes := []rune(key)
				if len(runes) != 1 || !unicode.IsLetter(runes[0]) {
					continue
				}

				if previous, ok := seen[key]; ok {
					if previous.action != action {
						t.Fatalf(
							"key %q is bound to %q on tab %q and %q on tab %q",
							key,
							previous.action,
							previous.tabID,
							action,
							tabID,
						)
					}
					continue
				}

				seen[key] = keyUsage{
					action: action,
					tabID:  tabID,
				}
			}
		}
	}
}
