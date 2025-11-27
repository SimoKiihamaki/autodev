package tui

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
)

// TrackerMetadata represents the metadata section of a tracker.
type TrackerMetadata struct {
	PRDSource      string `json:"prd_source"`
	PRDHash        string `json:"prd_hash"`
	CreatedAt      string `json:"created_at"`
	CreatedBy      string `json:"created_by"`
	ProjectContext struct {
		Language      string `json:"language"`
		Framework     string `json:"framework"`
		TestFramework string `json:"test_framework"`
		BuildSystem   string `json:"build_system"`
	} `json:"project_context"`
}

// TrackerFeature represents a feature in the tracker.
type TrackerFeature struct {
	ID          string `json:"id"`
	Name        string `json:"name"`
	Description string `json:"description"`
	Priority    string `json:"priority"`
	Complexity  string `json:"complexity"`
	Status      string `json:"status"`
	Tasks       []struct {
		ID          string `json:"id"`
		Description string `json:"description"`
		Status      string `json:"status"`
	} `json:"tasks"`
	AcceptanceCriteria []struct {
		ID       string `json:"id"`
		Status   string `json:"status"`
		Criteria string `json:"criterion"`
	} `json:"acceptance_criteria"`
}

// TrackerSummary represents the validation summary section.
type TrackerSummary struct {
	TotalFeatures       int      `json:"total_features"`
	TotalTasks          int      `json:"total_tasks"`
	EstimatedComplexity string   `json:"estimated_complexity"`
	CriticalPath        []string `json:"critical_path"`
}

// Tracker represents the full tracker structure.
type Tracker struct {
	Version           string           `json:"version"`
	Metadata          TrackerMetadata  `json:"metadata"`
	Features          []TrackerFeature `json:"features"`
	ValidationSummary TrackerSummary   `json:"validation_summary"`
}

// loadTracker loads the tracker from the repo's .aprd/tracker.json file.
func loadTracker(repoPath string) (*Tracker, error) {
	if repoPath == "" {
		return nil, fmt.Errorf("no repository path configured")
	}

	trackerPath := filepath.Join(repoPath, ".aprd", "tracker.json")
	data, err := os.ReadFile(trackerPath)
	if err != nil {
		return nil, err
	}

	var tracker Tracker
	if err := json.Unmarshal(data, &tracker); err != nil {
		return nil, fmt.Errorf("invalid tracker format: %w", err)
	}

	return &tracker, nil
}

// loadTrackerCmd returns a tea.Cmd that loads the tracker asynchronously.
func loadTrackerCmd(repoPath string) tea.Cmd {
	return func() tea.Msg {
		tracker, err := loadTracker(repoPath)
		return trackerLoadedMsg{tracker: tracker, err: err}
	}
}

// renderProgressView renders the Progress tab content.
func renderProgressView(b *strings.Builder, m model) {
	b.WriteString(sectionTitle.Render("Implementation Progress") + "\n\n")

	// Use cached tracker state loaded asynchronously
	if !m.trackerLoaded {
		b.WriteString(helpStyle.Render("Loading tracker...") + "\n")
		return
	}

	if m.trackerErr != nil {
		renderNoTracker(b, m, m.trackerErr)
		return
	}

	renderTrackerOverview(b, m.tracker)
	renderFeatureList(b, m.tracker)
	renderProgressFooter(b, m)
}

// renderNoTracker renders the view when no tracker is available.
func renderNoTracker(b *strings.Builder, m model, err error) {
	b.WriteString(helpStyle.Render("No implementation tracker found.") + "\n\n")

	if m.cfg.RepoPath == "" {
		b.WriteString("Configure a repository path in Settings to enable progress tracking.\n\n")
	} else {
		fmt.Fprintf(b, "Repository: %s\n", abbreviatePath(m.cfg.RepoPath))
		fmt.Fprintf(b, "%s\n\n", helpStyle.Render(fmt.Sprintf("Error: %v", err)))
	}

	b.WriteString(sectionTitle.Render("How to Create a Tracker") + "\n\n")
	b.WriteString("1. Create a PRD (Product Requirements Document) in markdown format\n")
	b.WriteString("2. Select the PRD in the PRD tab\n")
	b.WriteString("3. Run the automation with the Local phase enabled\n")
	b.WriteString("4. The tracker will be generated at: .aprd/tracker.json\n\n")

	b.WriteString(helpStyle.Render("The tracker enables:\n"))
	b.WriteString("  • Feature-by-feature progress tracking\n")
	b.WriteString("  • Acceptance criteria verification\n")
	b.WriteString("  • Rollback to previous feature states\n")
	b.WriteString("  • Cross-session state persistence\n")
}

// renderTrackerOverview renders the tracker metadata and summary.
func renderTrackerOverview(b *strings.Builder, tracker *Tracker) {
	meta := tracker.Metadata
	summary := tracker.ValidationSummary

	// Project info
	fmt.Fprintf(b, "PRD: %s\n", abbreviatePath(meta.PRDSource))
	fmt.Fprintf(b, "Created: %s by %s\n", formatTimestamp(meta.CreatedAt), meta.CreatedBy)
	if meta.ProjectContext.Language != "unknown" {
		fmt.Fprintf(b, "Project: %s / %s\n",
			meta.ProjectContext.Language,
			meta.ProjectContext.Framework)
	}
	b.WriteString("\n")

	// Progress summary
	completed, inProgress, pending, failed := countFeatureStatuses(tracker.Features)
	total := len(tracker.Features)

	b.WriteString(sectionTitle.Render("Progress Summary") + "\n")
	fmt.Fprintf(b, "Features: %d total | ", total)
	if completed > 0 {
		fmt.Fprintf(b, "%s | ", okStyle.Render(fmt.Sprintf("%d complete", completed)))
	}
	if inProgress > 0 {
		fmt.Fprintf(b, "%s | ", statusWarnStyle.Render(fmt.Sprintf("%d in progress", inProgress)))
	}
	if failed > 0 {
		fmt.Fprintf(b, "%s | ", errorStyle.Render(fmt.Sprintf("%d failed", failed)))
	}
	if pending > 0 {
		fmt.Fprintf(b, "%d pending", pending)
	}
	b.WriteString("\n")
	fmt.Fprintf(b, "Tasks: %d total\n", summary.TotalTasks)
	fmt.Fprintf(b, "Complexity: %s\n\n", summary.EstimatedComplexity)

	// Progress bar
	if total > 0 {
		progressPct := float64(completed) / float64(total) * 100
		b.WriteString(renderProgressBar(progressPct, 40) + "\n\n")
	}
}

// renderFeatureList renders the list of features with their status.
func renderFeatureList(b *strings.Builder, tracker *Tracker) {
	b.WriteString(sectionTitle.Render("Features") + "\n")

	for _, feature := range tracker.Features {
		statusIcon := featureStatusIcon(feature.Status)
		priorityBadge := priorityBadge(feature.Priority)
		complexityBadge := complexityBadge(feature.Complexity)

		// Feature header
		fmt.Fprintf(b, "%s %s %s %s %s\n",
			statusIcon, feature.ID, feature.Name, priorityBadge, complexityBadge)

		// Task summary for in-progress features
		if feature.Status == "in_progress" {
			completedTasks, totalTasks := countTaskStatus(feature.Tasks)
			fmt.Fprintf(b, "   Tasks: %d/%d complete\n", completedTasks, totalTasks)
		}
	}
}

// renderProgressFooter renders the help footer for the Progress tab.
func renderProgressFooter(b *strings.Builder, m model) {
	b.WriteString("\n")
	b.WriteString(helpStyle.Render("Press u to refresh · Tab cycle fields · q quit\n"))
}

// countFeatureStatuses counts features by status.
func countFeatureStatuses(features []TrackerFeature) (completed, inProgress, pending, failed int) {
	for _, f := range features {
		switch f.Status {
		case "completed", "verified":
			completed++
		case "in_progress":
			inProgress++
		case "pending", "blocked":
			pending++
		case "failed":
			failed++
		}
	}
	return
}

// countTaskStatus counts completed tasks.
func countTaskStatus(tasks []struct {
	ID          string `json:"id"`
	Description string `json:"description"`
	Status      string `json:"status"`
}) (completed, total int) {
	total = len(tasks)
	for _, t := range tasks {
		if t.Status == "completed" {
			completed++
		}
	}
	return
}

// featureStatusIcon returns an icon for a feature status.
func featureStatusIcon(status string) string {
	switch status {
	case "completed", "verified":
		return okStyle.Render("✓")
	case "in_progress":
		return statusWarnStyle.Render("►")
	case "failed":
		return errorStyle.Render("✗")
	case "blocked":
		return errorStyle.Render("⊘")
	default:
		return helpStyle.Render("○")
	}
}

// priorityBadge returns a styled priority badge.
func priorityBadge(priority string) string {
	switch priority {
	case "critical":
		return errorStyle.Render("[CRIT]")
	case "high":
		return statusWarnStyle.Render("[HIGH]")
	case "medium":
		return helpStyle.Render("[MED]")
	default:
		return helpStyle.Render("[LOW]")
	}
}

// complexityBadge returns a styled complexity badge.
func complexityBadge(complexity string) string {
	switch complexity {
	case "XL":
		return errorStyle.Render("XL")
	case "L":
		return statusWarnStyle.Render("L")
	case "M":
		return helpStyle.Render("M")
	default:
		return helpStyle.Render("S")
	}
}

// renderProgressBar renders a text-based progress bar.
func renderProgressBar(percentage float64, width int) string {
	filled := int(percentage / 100 * float64(width))
	if filled > width {
		filled = width
	}
	if filled < 0 {
		filled = 0
	}

	bar := strings.Repeat("█", filled) + strings.Repeat("░", width-filled)
	return fmt.Sprintf("[%s] %.0f%%", bar, percentage)
}

// formatTimestamp formats an ISO timestamp for display.
func formatTimestamp(ts string) string {
	// Simple formatting - just show date part
	if len(ts) >= 10 {
		return ts[:10]
	}
	return ts
}
