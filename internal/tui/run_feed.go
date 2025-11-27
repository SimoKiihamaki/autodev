package tui

import (
	"fmt"
	"log"
	"regexp"
	"strconv"
	"strings"
	"sync"

	"github.com/SimoKiihamaki/autodev/internal/runner"
)

// reWordError matches "error" as a whole word, avoiding false positives like
// "error-free" or "without errors". Uses word boundary matching.
var reWordError = regexp.MustCompile(`(?i)\berror\b`)

const (
	feedBufCap           = 800
	iterIndexUnknown     = -1 // iteration index provided but failed to parse
	iterTotalUnspecified = 0  // iteration total omitted entirely in the feed line
	iterTotalUnknown     = -1 // iteration total provided but failed to parse; distinct from unspecified
)

var (
	pythonLogPrefixOnce sync.Once
	rePythonLogPrefix   *regexp.Regexp
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
	m.runFeedAutoFollow = m.followLogs
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
	if len(m.runFeedBuf) > feedBufCap {
		tail := m.runFeedBuf[len(m.runFeedBuf)-feedBufCap:]
		m.runFeedBuf = append([]string(nil), tail...)
	}
	shouldFollow := m.runFeedAutoFollow

	m.runFeed.SetContent(strings.Join(m.runFeedBuf, "\n"))
	if shouldFollow {
		m.runFeed.GotoBottom()
	}

	m.runFeedAutoFollow = m.followLogs && m.runFeed.AtBottom()

	m.consumeRunSummary(rawLine)
}

func (m *model) updateRunFeedFollowFromViewport() {
	m.runFeedAutoFollow = m.followLogs && m.runFeed.AtBottom()
}

func (m *model) formatLogLine(line runner.Line) (string, string) {
	plain := strings.TrimRight(line.Text, "\r\n")
	displayText := plain
	style := logInfoStyle
	lower := strings.ToLower(plain)

	// Priority-based styling: more specific/severe patterns are checked first.
	// This prevents lines with multiple keywords (e.g., "warning: operation completed successfully")
	// from being incorrectly categorized. Order matters - errors take precedence over warnings,
	// warnings over success, etc.
	switch {
	// Highest priority: explicit error flag from runner
	case line.Err:
		displayText = "[ERR] " + plain
		style = logErrorStyle

	// Unicode prefix indicators - explicit intent, check early
	case strings.HasPrefix(plain, "⚠️"):
		style = logWarnStyle
	case strings.HasPrefix(plain, "✓"):
		style = logSuccessStyle
	case strings.HasPrefix(plain, "→"):
		style = logActionStyle

	// Phase/section headers (=== ... ===)
	case reSectionHeader.MatchString(plain):
		style = logPhaseStyle

	// TASKS_LEFT signals - highly visible, specific pattern
	case strings.Contains(lower, "tasks_left"):
		style = logTasksLeftStyle

	// Error patterns - check before warnings and success (higher severity)
	case strings.Contains(lower, "traceback"):
		style = logErrorStyle
	case strings.Contains(lower, "exception"):
		style = logErrorStyle
	case reWordError.MatchString(lower):
		style = logErrorStyle

	// Warning patterns - check before success (higher severity)
	case strings.Contains(lower, "warning"):
		style = logWarnStyle
	case strings.Contains(lower, "warn"):
		style = logWarnStyle

	// System messages - check before generic success patterns
	case strings.Contains(lower, "process finished"):
		style = logSystemStyle
	case strings.Contains(lower, "review loop"):
		style = logSystemStyle

	// Success patterns - lowest priority among keyword-based styles
	case strings.Contains(lower, "success"):
		style = logSuccessStyle
	case strings.Contains(lower, "passed"):
		style = logSuccessStyle
	case strings.Contains(lower, "completed"):
		style = logSuccessStyle
	}
	return style.Render(displayText), plain
}

func (m *model) consumeRunSummary(rawLine string) {
	text := strings.TrimSpace(rawLine)
	if text == "" {
		return
	}
	text = trimAutomationLogPrefix(text)
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

// Helper to check if prefix contains a log level
func containsLogLevel(prefix string) bool {
	return strings.Contains(prefix, "INFO") ||
		strings.Contains(prefix, "WARNING") ||
		strings.Contains(prefix, "ERROR") ||
		strings.Contains(prefix, "DEBUG")
}

// Helper to check if a byte is a digit
func isDigit(b byte) bool {
	return b >= '0' && b <= '9'
}

// startsWithFourDigits checks if the string starts with exactly four digits
func startsWithFourDigits(s string) bool {
	return len(s) >= 4 && isDigit(s[0]) && isDigit(s[1]) && isDigit(s[2]) && isDigit(s[3])
}

func trimAutomationLogPrefix(text string) string {
	idx := strings.Index(text, ": ")
	if idx == -1 {
		return text
	}

	prefix := text[:idx+2]

	// Fast heuristic: prefix starts with 4 digits and contains a log level
	if startsWithFourDigits(prefix) && containsLogLevel(prefix) {

		// Lazy compile regex only when heuristic passes
		pythonLogPrefixOnce.Do(func() {
			rePythonLogPrefix = regexp.MustCompile(`^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3}\s+[A-Z]+\s+[A-Za-z0-9_.]+: $`)
		})

		// Use compiled regex for exact match only when heuristic passes
		if rePythonLogPrefix.MatchString(prefix) {
			return strings.TrimSpace(text[idx+2:])
		}
	}

	return text
}
