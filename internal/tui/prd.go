package tui

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/charmbracelet/bubbles/list"
	tea "github.com/charmbracelet/bubbletea"
)

type prdScanMsg struct{ items []list.Item }

func (m *model) rescanPRDs() {
	m.prdList.SetItems([]list.Item{})
}

func (m model) scanPRDsCmd() tea.Cmd {
	return func() tea.Msg {
		var typed []item
		cwd, err := os.Getwd()
		if err != nil {
			return prdScanMsg{items: nil}
		}
		_ = filepath.WalkDir(cwd, func(path string, d os.DirEntry, err error) error {
			if err != nil {
				return nil
			}
			if d.IsDir() {
				rel, relErr := filepath.Rel(cwd, path)
				if relErr != nil {
					return filepath.SkipDir
				}
				if strings.Count(rel, string(os.PathSeparator)) > 4 {
					return filepath.SkipDir
				}
				return nil
			}
			if strings.HasSuffix(strings.ToLower(d.Name()), ".md") {
				rel, relErr := filepath.Rel(cwd, path)
				if relErr != nil {
					rel = d.Name()
				}
				typed = append(typed, item{title: d.Name(), desc: rel, path: path})
			}
			return nil
		})
		sort.Slice(typed, func(i, j int) bool {
			return typed[i].path < typed[j].path
		})
		items := make([]list.Item, len(typed))
		for i := range typed {
			items[i] = typed[i]
		}
		return prdScanMsg{items: items}
	}
}

func (m *model) ensureSelectedPRD(items []list.Item) {
	if len(items) == 0 {
		m.clearPRDSelection("No PRD files found.")
		return
	}

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

func formatPRDDisplay(path string) string {
	path = strings.TrimSpace(path)
	if path == "" {
		return "(none selected)"
	}
	base := filepath.Base(path)
	dir := filepath.Dir(path)
	if dir == "." || dir == string(filepath.Separator) || dir == "" {
		return base
	}
	prettyDir := abbreviatePath(dir)
	if prettyDir == "" || prettyDir == "." || prettyDir == string(filepath.Separator) {
		return base
	}
	return fmt.Sprintf("%s · %s", base, prettyDir)
}
