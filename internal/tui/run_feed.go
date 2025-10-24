package tui

import (
	"fmt"
	"log"
	"regexp"
	"strconv"
	"strings"

	"github.com/SimoKiihamaki/autodev/internal/runner"
)

const (
	feedBufCap           = 800
	feedFlushStep        = 16
	feedFollowFlushStep  = 4
	iterIndexUnknown     = -1 // iteration index provided but failed to parse
	iterTotalUnspecified = 0  // iteration total omitted entirely in the feed line
	iterTotalUnknown     = -1 // iteration total provided but failed to parse; distinct from unspecified
)

var (
	reSectionHeader   = regexp.MustCompile(`^=+\s*(.+?)\s*=+$`)
	reIterationHeader = regexp.MustCompile(`^=+\s*Iteration\s+(\d+)(?:/(\d+))?(?::\s*(.+?))?\s*=+$`)
)

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
	m.runFeedAutoFollow = true
	m.runFeedDirtyLines = 0
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
	wasEmpty := len(m.runFeedBuf) == 0
	m.runFeedBuf = append(m.runFeedBuf, displayLine)
	trimmed := false
	if len(m.runFeedBuf) > feedBufCap {
		tail := m.runFeedBuf[len(m.runFeedBuf)-feedBufCap:]
		m.runFeedBuf = append([]string(nil), tail...)
		trimmed = true
	}
	m.runFeedDirtyLines++
	shouldFollow := m.runFeedAutoFollow || m.runFeed.AtBottom()
	flush := wasEmpty || trimmed
	if !flush {
		if shouldFollow {
			flush = m.runFeedDirtyLines >= feedFollowFlushStep
		} else {
			flush = m.runFeedDirtyLines >= feedFlushStep
		}
	}
	if flush {
		m.runFeed.SetContent(strings.Join(m.runFeedBuf, "\n"))
		m.runFeedDirtyLines = 0
		if shouldFollow {
			m.runFeed.GotoBottom()
			m.runFeedAutoFollow = true
		}
	}

	m.consumeRunSummary(rawLine)
}

func (m *model) updateRunFeedFollowFromViewport() {
	m.runFeedAutoFollow = m.runFeed.AtBottom()
}

func (m *model) formatLogLine(line runner.Line) (string, string) {
	plain := strings.TrimRight(line.Text, "\r\n")
	displayText := plain
	style := logInfoStyle
	lower := strings.ToLower(plain)
	switch {
	case line.Err:
		displayText = "[ERR] " + plain
		style = logErrorStyle
	case strings.HasPrefix(plain, "⚠️"):
		style = logWarnStyle
	case strings.HasPrefix(plain, "✓"):
		style = logSuccessStyle
	case strings.HasPrefix(plain, "→"):
		style = logActionStyle
	case strings.Contains(lower, "process finished"):
		style = logSystemStyle
	case strings.Contains(lower, "review loop"):
		style = logSystemStyle
	}
	return style.Render(displayText), plain
}

func (m *model) consumeRunSummary(rawLine string) {
	text := strings.TrimSpace(rawLine)
	if text == "" {
		return
	}

	if m.handleIterationHeader(text) {
		return
	}
	if m.handleSectionHeader(text) {
		return
	}
	if m.handleActionIndicators(text) {
		return
	}
	m.handleStatusPhrases(text)
}

func (m *model) handleIterationHeader(text string) bool {
	match := reIterationHeader.FindStringSubmatch(text)
	if match == nil {
		return false
	}
	if cur, err := strconv.Atoi(match[1]); err == nil {
		m.runIterCurrent = cur
	} else {
		m.runIterCurrent = iterIndexUnknown
		log.Printf("tui: unable to parse iteration index %q: %v (treating as iterIndexUnknown)", match[1], err)
	}
	if match[2] != "" {
		if total, err := strconv.Atoi(match[2]); err == nil {
			m.runIterTotal = total
		} else {
			m.runIterTotal = iterTotalUnknown
			log.Printf(
				"tui: unable to parse iteration total %q: %v (treating as iterTotalUnknown)",
				match[2],
				err,
			)
		}
	} else {
		// No total was provided; record iterTotalUnspecified so views can elide the denominator entirely.
		m.runIterTotal = iterTotalUnspecified
	}
	label := strings.TrimSpace(match[3])
	m.runIterLabel = label
	countLabel := "Iteration"
	if m.runIterCurrent > 0 {
		switch {
		case m.runIterTotal > 0:
			countLabel = fmt.Sprintf("Iteration %d/%d", m.runIterCurrent, m.runIterTotal)
		case m.runIterTotal == iterTotalUnknown:
			countLabel = fmt.Sprintf("Iteration %d/?", m.runIterCurrent)
		default:
			countLabel = fmt.Sprintf("Iteration %d", m.runIterCurrent)
		}
	}
	m.runPhase = countLabel
	if label != "" {
		m.setRunCurrent(label)
	} else {
		m.setRunCurrent(countLabel)
	}
	return true
}

func (m *model) handleSectionHeader(text string) bool {
	match := reSectionHeader.FindStringSubmatch(text)
	if match == nil {
		return false
	}
	section := strings.TrimSpace(match[1])
	if section != "" {
		m.runPhase = section
		m.setRunCurrent(section)
	}
	return true
}

func (m *model) handleActionIndicators(text string) bool {
	switch {
	case strings.HasPrefix(text, "→"):
		action := strings.TrimSpace(strings.TrimPrefix(text, "→"))
		if action != "" {
			m.setRunCurrent(action)
		}
		return true
	case strings.HasPrefix(text, "✓"):
		done := strings.TrimSpace(strings.TrimPrefix(text, "✓"))
		if done == "" {
			done = strings.TrimSpace(text)
		}
		m.runLastComplete = done
		m.setRunCurrent(done)
		return true
	case strings.HasPrefix(text, "⚠️"):
		m.setRunCurrent(text)
		return true
	}
	return false
}

func (m *model) handleStatusPhrases(text string) {
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
