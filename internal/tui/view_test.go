package tui

import (
	"errors"
	"strings"
	"testing"

	"github.com/SimoKiihamaki/autodev/internal/config"
	"github.com/charmbracelet/bubbles/viewport"
)

func TestRenderRunViewErrorBanner(t *testing.T) {
	t.Parallel()

	m := model{
		cfg:               config.Defaults(),
		keys:              DefaultKeyMap(),
		runFeed:           viewport.New(80, 16),
		runFeedBuf:        []string{"line one"},
		followLogs:        true,
		runFeedAutoFollow: true,
		errMsg:            "runner exited with error: exit status 1",
		lastRunErr:        errors.New("runner exited with error: exit status 1"),
	}
	m.runFeed.SetContent(strings.Join(m.runFeedBuf, "\n"))

	var b strings.Builder
	renderRunView(&b, m)
	out := b.String()

	if !strings.Contains(out, "Last error: runner exited with error: exit status 1") {
		t.Fatalf("expected error banner in view, got:\n%s", out)
	}

	if !strings.Contains(out, "Y copy error") {
		t.Fatalf("expected copy hint in view, got:\n%s", out)
	}

	if !strings.Contains(out, "Enter retry all") {
		t.Fatalf("expected retry hint in view, got:\n%s", out)
	}
}

func TestBuildHelpOverlayContentIncludesGlobalAndTabActions(t *testing.T) {
	t.Parallel()
	m := model{
		keys: DefaultKeyMap(),
		tabs: defaultTabIDs(),
	}

	content := buildHelpOverlayContent(m)
	if content == "" {
		t.Fatalf("expected help overlay content to render")
	}

	if !strings.Contains(content, "Global") {
		t.Fatalf("expected global section in help overlay, got:\n%s", content)
	}

	if !strings.Contains(content, "Save config") {
		t.Fatalf("expected save action label in help overlay, got:\n%s", content)
	}

	runTitle := tabTitle(tabIDRun)
	if !strings.Contains(content, runTitle) {
		t.Fatalf("expected current tab title %q in help overlay, got:\n%s", runTitle, content)
	}

	if !strings.Contains(content, "Enter") {
		t.Fatalf("expected key combo to appear in help overlay, got:\n%s", content)
	}
}

// TestViewSettingsRendering tests that the settings view contains all expected sections.
func TestViewSettingsRendering(t *testing.T) {
	t.Parallel()

	m := newModelForSettingsTest()
	m.tabIndex = 1 // Settings tab

	var b strings.Builder
	renderSettingsView(&b, m)
	view := b.String()

	// Verify key sections are present
	expectedSections := []string{
		"Settings",
		"Repository",
		"Executors",
		"Timings",
		"Ralph",
		"Security",
	}

	for _, section := range expectedSections {
		if !strings.Contains(view, section) {
			t.Errorf("Settings view should contain '%s' section", section)
		}
	}
}

// TestViewSettingsRepositoryGroup tests the repository settings group rendering.
func TestViewSettingsRepositoryGroup(t *testing.T) {
	t.Parallel()

	m := newModelForSettingsTest()

	var b strings.Builder
	renderRepositoryGroup(&b, m)
	output := b.String()

	// Verify repository section is present
	if !strings.Contains(output, "Repository") {
		t.Error("Repository group should contain 'Repository' title")
	}
}

// TestViewSettingsExecutorsGroup tests the executor settings group rendering.
func TestViewSettingsExecutorsGroup(t *testing.T) {
	t.Parallel()

	m := newModelForSettingsTest()

	var b strings.Builder
	renderExecutorsGroup(&b, m)
	output := b.String()

	// Verify executors section is present
	if !strings.Contains(output, "Executors") {
		t.Error("Executors group should contain 'Executors' title")
	}

	// Verify executor labels are present
	expectedLabels := []string{
		executorLocalLabel,
		executorPRLabel,
		executorReviewLabel,
	}

	for _, label := range expectedLabels {
		if !strings.Contains(output, label) {
			t.Errorf("Executors group should contain '%s' label", label)
		}
	}

	// Verify Codex and Claude options are present
	if !strings.Contains(output, "Codex") {
		t.Error("Executors group should contain 'Codex' option")
	}
	if !strings.Contains(output, "Claude") {
		t.Error("Executors group should contain 'Claude' option")
	}
}

// TestViewSettingsTimingsGroup tests the timings settings group rendering.
func TestViewSettingsTimingsGroup(t *testing.T) {
	t.Parallel()

	m := newModelForSettingsTest()

	var b strings.Builder
	renderTimingsGroup(&b, m)
	output := b.String()

	// Verify timings section is present
	if !strings.Contains(output, "Timings") {
		t.Error("Timings group should contain 'Timings' title")
	}
}

// TestViewSettingsRalphGroup tests the Ralph settings group rendering.
func TestViewSettingsRalphGroup(t *testing.T) {
	t.Parallel()

	m := newModelForSettingsTest()

	var b strings.Builder
	renderRalphGroup(&b, m)
	output := b.String()

	// Verify Ralph section is present
	if !strings.Contains(output, "Ralph") {
		t.Error("Ralph group should contain 'Ralph' title")
	}

	// Verify "Autonomous Mode" is mentioned
	if !strings.Contains(output, "Autonomous Mode") {
		t.Error("Ralph group should mention 'Autonomous Mode'")
	}
}

// TestViewSettingsSecurityGroup tests the security settings group rendering.
func TestViewSettingsSecurityGroup(t *testing.T) {
	t.Parallel()

	m := newModelForSettingsTest()

	var b strings.Builder
	renderSecurityGroup(&b, m)
	output := b.String()

	// Verify security section is present
	if !strings.Contains(output, "Security") {
		t.Error("Security group should contain 'Security' title")
	}
}

// TestViewSettingsHelp tests the settings help text rendering.
func TestViewSettingsHelp(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name         string
		focusedInput string
		wantText     string
	}{
		{
			name:         "no input focused shows tab help",
			focusedInput: "",
			wantText:     "", // Should show overlay help (may be empty or have content)
		},
		{
			name:         "input focused shows input help",
			focusedInput: "repo",
			wantText:     "Input focused:",
		},
		{
			name:         "executor toggle focused shows toggle help",
			focusedInput: "toggleLocal",
			wantText:     "Toggle focused:",
		},
	}

	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			m := newModelForSettingsTest()
			m.focusedInput = tc.focusedInput

			var b strings.Builder
			renderSettingsHelp(&b, m)
			output := b.String()

			if tc.wantText != "" {
				if !strings.Contains(output, tc.wantText) {
					t.Errorf("Help text should contain %q", tc.wantText)
				}
			} else {
				// For empty wantText, just verify it doesn't contain input-focused help
				if strings.Contains(output, "Input focused:") || strings.Contains(output, "Toggle focused:") {
					t.Errorf("Help text should not show input/toggle focused help, got: %s", output)
				}
			}
		})
	}
}

// TestIsInSettingsGroup tests the settings group membership check.
func TestIsInSettingsGroup(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name  string
		input string
		group []string
		want  bool
	}{
		{
			name:  "input in group",
			input: "repo",
			group: []string{"repo", "base", "branch"},
			want:  true,
		},
		{
			name:  "input not in group",
			input: "codex",
			group: []string{"repo", "base", "branch"},
			want:  false,
		},
		{
			name:  "empty group",
			input: "repo",
			group: []string{},
			want:  false,
		},
		{
			name:  "empty input",
			input: "",
			group: []string{"repo", "base"},
			want:  false,
		},
	}

	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			got := isInSettingsGroup(tc.input, tc.group)
			if got != tc.want {
				t.Errorf("isInSettingsGroup(%q, %v) = %v, want %v",
					tc.input, tc.group, got, tc.want)
			}
		})
	}
}

// TestRenderExecutorToggle tests executor toggle rendering.
func TestRenderExecutorToggle(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name   string
		label  string
		choice executorChoice
		focus  bool
	}{
		{
			name:   "Codex selected",
			label:  "Local Loop",
			choice: executorCodex,
			focus:  false,
		},
		{
			name:   "Claude selected",
			label:  "PR Push",
			choice: executorClaude,
			focus:  false,
		},
		{
			name:   "focused toggle",
			label:  "Review Fix",
			choice: executorCodex,
			focus:  true,
		},
	}

	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			output := renderExecutorToggle(tc.label, tc.choice, tc.focus)

			// Verify label is present
			if !strings.Contains(output, tc.label) {
				t.Errorf("Toggle should contain label %q", tc.label)
			}

			// Verify both options are present
			if !strings.Contains(output, "Codex") {
				t.Error("Toggle should contain 'Codex' option")
			}
			if !strings.Contains(output, "Claude") {
				t.Error("Toggle should contain 'Claude' option")
			}
		})
	}
}

// TestRenderExecutorOption tests single executor option rendering.
func TestRenderExecutorOption(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name     string
		option   string
		selected bool
	}{
		{
			name:     "selected option is bold",
			option:   "Codex",
			selected: true,
		},
		{
			name:     "unselected option is plain",
			option:   "Claude",
			selected: false,
		},
	}

	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			output := renderExecutorOption(tc.option, tc.selected)

			if !strings.Contains(output, tc.option) {
				t.Errorf("Option should contain %q", tc.option)
			}

			if tc.selected {
				// Selected option should be wrapped in brackets
				if !strings.Contains(output, "[") || !strings.Contains(output, "]") {
					t.Error("Selected option should be wrapped in brackets")
				}
			}
		})
	}
}

// TestExecutorToggleLabel tests toggle name to label mapping.
func TestExecutorToggleLabel(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name string
		want string
	}{
		{"toggleLocal", executorLocalLabel},
		{"togglePR", executorPRLabel},
		{"toggleReview", executorReviewLabel},
		{"unknown", "unknown"},
	}

	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			got := executorToggleLabel(tc.name)
			if got != tc.want {
				t.Errorf("executorToggleLabel(%q) = %q, want %q",
					tc.name, got, tc.want)
			}
		})
	}
}

// TestViewProgressRendering tests the progress view rendering.
func TestViewProgressRendering(t *testing.T) {
	t.Parallel()

	m := newModelForSettingsTest()
	m.tabIndex = 3 // Progress tab

	var b strings.Builder
	renderProgressView(&b, m)
	view := b.String()

	// Should show "Loading tracker..." when tracker not loaded
	if !strings.Contains(view, "Loading tracker") {
		t.Error("Progress view should show loading message when tracker not loaded")
	}
}

// TestRenderNoTracker tests the "no tracker" view rendering.
func TestRenderNoTracker(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name       string
		repoPath   string
		trackerErr error
		wantText   string
	}{
		{
			name:       "no repo configured",
			repoPath:   "",
			trackerErr: nil,
			wantText:   "Configure a repository path",
		},
		{
			name:       "tracker error with repo",
			repoPath:   "/path/to/repo",
			trackerErr: errors.New("tracker not found"),
			wantText:   "Error:",
		},
	}

	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			m := newModelForSettingsTest()
			m.cfg.RepoPath = tc.repoPath
			m.trackerErr = tc.trackerErr

			var b strings.Builder
			renderNoTracker(&b, m, tc.trackerErr)
			output := b.String()

			if !strings.Contains(output, tc.wantText) {
				t.Errorf("No tracker view should contain %q", tc.wantText)
			}

			// Should always show "How to Create a Tracker" section
			if !strings.Contains(output, "How to Create a Tracker") {
				t.Error("No tracker view should show how to create tracker")
			}
		})
	}
}

// TestRenderTrackerOverview tests tracker overview rendering.
func TestRenderTrackerOverview(t *testing.T) {
	t.Parallel()

	tracker := &Tracker{
		Metadata: TrackerMetadata{
			PRDSource: "/path/to/prd.md",
			CreatedAt: "2025-01-19T10:00:00Z",
			CreatedBy: "test-user",
			ProjectContext: struct {
				Language      string `json:"language"`
				Framework     string `json:"framework"`
				TestFramework string `json:"test_framework"`
				BuildSystem   string `json:"build_system"`
			}{
				Language:  "Go",
				Framework: "Bubbletea",
			},
		},
		ValidationSummary: TrackerSummary{
			TotalFeatures:       10,
			TotalTasks:          50,
			EstimatedComplexity: "high",
		},
		Features: []TrackerFeature{
			{Status: "completed"},
			{Status: "completed"},
			{Status: "in_progress"},
			{Status: "pending"},
		},
	}

	var b strings.Builder
	renderTrackerOverview(&b, tracker)
	output := b.String()

	// Verify key information is present
	expectedTexts := []string{
		"PRD:",
		"Created:",
		"Progress Summary",
		"Features:",
		"Tasks:",
		"Complexity:",
	}

	for _, text := range expectedTexts {
		if !strings.Contains(output, text) {
			t.Errorf("Tracker overview should contain %q", text)
		}
	}

	// Should contain project info
	if !strings.Contains(output, "Go") {
		t.Error("Tracker overview should show project language")
	}
}

// TestCountFeatureStatuses tests feature status counting.
func TestCountFeatureStatuses(t *testing.T) {
	t.Parallel()

	features := []TrackerFeature{
		{Status: "completed"},
		{Status: "verified"},
		{Status: "in_progress"},
		{Status: "pending"},
		{Status: "blocked"},
		{Status: "failed"},
		{Status: "completed"},
	}

	completed, inProgress, pending, failed := countFeatureStatuses(features)

	if completed != 3 {
		t.Errorf("Completed count = %d, want 3", completed)
	}
	if inProgress != 1 {
		t.Errorf("In progress count = %d, want 1", inProgress)
	}
	if pending != 2 {
		t.Errorf("Pending count = %d, want 2", pending)
	}
	if failed != 1 {
		t.Errorf("Failed count = %d, want 1", failed)
	}
}

// TestCountTaskStatus tests task status counting.
func TestCountTaskStatus(t *testing.T) {
	t.Parallel()

	tasks := []struct {
		ID          string `json:"id"`
		Description string `json:"description"`
		Status      string `json:"status"`
	}{
		{Status: "completed"},
		{Status: "completed"},
		{Status: "pending"},
		{Status: "in_progress"},
	}

	completed, total := countTaskStatus(tasks)

	if completed != 2 {
		t.Errorf("Completed count = %d, want 2", completed)
	}
	if total != 4 {
		t.Errorf("Total count = %d, want 4", total)
	}
}

// TestFeatureStatusIcon tests feature status icon rendering.
func TestFeatureStatusIcon(t *testing.T) {
	t.Parallel()

	tests := []struct {
		status   string
		contains string // Icon character to check for
	}{
		{"completed", "✓"},
		{"verified", "✓"},
		{"in_progress", "►"},
		{"failed", "✗"},
		{"blocked", "⊘"},
		{"pending", "○"},
		{"unknown", "○"},
	}

	for _, tc := range tests {
		tc := tc
		t.Run(tc.status, func(t *testing.T) {
			t.Parallel()

			output := featureStatusIcon(tc.status)
			if !strings.Contains(output, tc.contains) {
				t.Errorf("Status icon for %q should contain %q", tc.status, tc.contains)
			}
		})
	}
}

// TestPriorityBadge tests priority badge rendering.
func TestPriorityBadge(t *testing.T) {
	t.Parallel()

	tests := []struct {
		priority string
		contains string
	}{
		{"critical", "[CRIT]"},
		{"high", "[HIGH]"},
		{"medium", "[MED]"},
		{"low", "[LOW]"},
		{"unknown", "[LOW]"},
	}

	for _, tc := range tests {
		tc := tc
		t.Run(tc.priority, func(t *testing.T) {
			t.Parallel()

			output := priorityBadge(tc.priority)
			if !strings.Contains(output, tc.contains) {
				t.Errorf("Priority badge for %q should contain %q", tc.priority, tc.contains)
			}
		})
	}
}

// TestComplexityBadge tests complexity badge rendering.
func TestComplexityBadge(t *testing.T) {
	t.Parallel()

	tests := []struct {
		complexity string
		contains   string
	}{
		{"XL", "XL"},
		{"L", "L"},
		{"M", "M"},
		{"S", "S"},
		{"unknown", "S"},
	}

	for _, tc := range tests {
		tc := tc
		t.Run(tc.complexity, func(t *testing.T) {
			t.Parallel()

			output := complexityBadge(tc.complexity)
			if !strings.Contains(output, tc.contains) {
				t.Errorf("Complexity badge for %q should contain %q", tc.complexity, tc.contains)
			}
		})
	}
}

// TestRenderProgressBar tests progress bar rendering.
func TestRenderProgressBar(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name       string
		percentage float64
		width      int
		wantFilled int
	}{
		{
			name:       "0% progress",
			percentage: 0.0,
			width:      10,
			wantFilled: 0,
		},
		{
			name:       "50% progress",
			percentage: 50.0,
			width:      10,
			wantFilled: 5,
		},
		{
			name:       "100% progress",
			percentage: 100.0,
			width:      10,
			wantFilled: 10,
		},
		{
			name:       "clamps to max width",
			percentage: 150.0,
			width:      10,
			wantFilled: 10,
		},
		{
			name:       "clamps to min width",
			percentage: -10.0,
			width:      10,
			wantFilled: 0,
		},
	}

	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			output := renderProgressBar(tc.percentage, tc.width)

			// Count filled characters
			filledCount := 0
			for _, r := range output {
				if r == '█' {
					filledCount++
				}
			}

			if filledCount != tc.wantFilled {
				t.Errorf("Progress bar has %d filled chars, want %d",
					filledCount, tc.wantFilled)
			}

			// Verify percentage is shown
			if !strings.Contains(output, "%") {
				t.Error("Progress bar should show percentage")
			}
		})
	}
}

// TestFormatTimestamp tests timestamp formatting.
func TestFormatTimestamp(t *testing.T) {
	t.Parallel()

	tests := []struct {
		input    string
		expected string
	}{
		{
			input:    "2025-01-19T10:30:00Z",
			expected: "2025-01-19",
		},
		{
			input:    "short",
			expected: "short",
		},
		{
			input:    "",
			expected: "",
		},
	}

	for _, tc := range tests {
		tc := tc
		t.Run(tc.input, func(t *testing.T) {
			t.Parallel()

			got := formatTimestamp(tc.input)
			if got != tc.expected {
				t.Errorf("formatTimestamp(%q) = %q, want %q",
					tc.input, got, tc.expected)
			}
		})
	}
}

// TestViewPRDRendering tests the PRD view rendering.
func TestViewPRDRendering(t *testing.T) {
	t.Parallel()

	m := newModelForSettingsTest()
	m.tabIndex = 2 // PRD tab

	var b strings.Builder
	renderPRDView(&b, m)
	view := b.String()

	// Verify key sections are present
	if !strings.Contains(view, "PRD Selection") {
		t.Error("PRD view should contain 'PRD Selection' title")
	}
}

// TestViewPRDSelectionInfo tests PRD selection info rendering.
func TestViewPRDSelectionInfo(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name        string
		selectedPRD string
		tags        []string
		wantText    string
	}{
		{
			name:        "PRD selected",
			selectedPRD: "/path/to/prd.md",
			tags:        []string{"feat", "urgent"},
			wantText:    "Selected:",
		},
		{
			name:        "no PRD selected",
			selectedPRD: "",
			tags:        nil,
			wantText:    "No PRD selected",
		},
	}

	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			m := newModelForSettingsTest()
			m.selectedPRD = tc.selectedPRD
			m.tags = tc.tags

			var b strings.Builder
			renderPRDSelectionInfo(&b, m)
			output := b.String()

			if !strings.Contains(output, tc.wantText) {
				t.Errorf("Selection info should contain %q", tc.wantText)
			}

			if len(tc.tags) > 0 {
				if !strings.Contains(output, "Tags:") {
					t.Error("Selection info should show tags when present")
				}
				if !strings.Contains(output, "feat") {
					t.Error("Selection info should show tag 'feat'")
				}
			}
		})
	}
}

// TestViewEnvRendering tests the env view rendering.
func TestViewEnvRendering(t *testing.T) {
	t.Parallel()

	m := newModelForSettingsTest()
	m.tabIndex = 4 // Env tab

	var b strings.Builder
	renderEnvView(&b, m)
	view := b.String()

	// Verify key sections are present
	expectedSections := []string{
		"Env & Flags",
		"Phases:",
	}

	for _, section := range expectedSections {
		if !strings.Contains(view, section) {
			t.Errorf("Env view should contain '%s'", section)
		}
	}
}

// TestRenderPhaseToggles tests phase toggle rendering.
func TestRenderPhaseToggles(t *testing.T) {
	t.Parallel()

	m := newModelForSettingsTest()
	m.runLocal = true
	m.runPR = false
	m.runReview = true

	var b strings.Builder
	renderPhaseToggles(&b, m)
	output := b.String()

	// Verify phases are shown
	if !strings.Contains(output, "Local=") {
		t.Error("Phase toggles should show Local phase")
	}
	if !strings.Contains(output, "PR=") {
		t.Error("Phase toggles should show PR phase")
	}
	if !strings.Contains(output, "Review Fix=") {
		t.Error("Phase toggles should show Review Fix phase")
	}

	// Verify boolean values are shown
	if !strings.Contains(output, "true") {
		t.Error("Phase toggles should show 'true' value")
	}
	if !strings.Contains(output, "false") {
		t.Error("Phase toggles should show 'false' value")
	}
}

// TestRenderFlagToggles tests flag toggle rendering.
func TestRenderFlagToggles(t *testing.T) {
	t.Parallel()

	m := newModelForSettingsTest()
	m.flagAllowUnsafe = false
	m.flagDryRun = true
	m.flagSyncGit = false
	m.flagInfinite = true
	m.flagSupport = false

	var b strings.Builder
	renderFlagToggles(&b, m)
	output := b.String()

	// Verify all flags are shown
	expectedFlags := []string{
		"Allow Unsafe:",
		"Dry Run:",
		"Sync Git:",
		"Infinite Reviews:",
		"Support Mode:",
	}

	for _, flag := range expectedFlags {
		if !strings.Contains(output, flag) {
			t.Errorf("Flag toggles should show '%s'", flag)
		}
	}
}

// TestRenderEnvHelp tests env help text rendering.
func TestRenderEnvHelp(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name        string
		focusedFlag string
		wantText    string
	}{
		{
			name:        "no flag focused shows general help",
			focusedFlag: "",
			wantText:    "Arrow keys to navigate",
		},
		{
			name:        "flag focused shows flag help",
			focusedFlag: "allow-unsafe",
			wantText:    "Flag focused:",
		},
	}

	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			m := newModelForSettingsTest()
			m.focusedFlag = tc.focusedFlag

			var b strings.Builder
			renderEnvHelp(&b, m)
			output := b.String()

			if !strings.Contains(output, tc.wantText) {
				t.Errorf("Help text should contain %q", tc.wantText)
			}
		})
	}
}

// TestLoadTracker tests tracker loading from file.
func TestLoadTracker(t *testing.T) {
	t.Parallel()

	t.Run("empty repo path returns error", func(t *testing.T) {
		t.Parallel()

		_, err := loadTracker("")
		if err == nil {
			t.Error("loadTracker with empty path should return error")
		}
		if !strings.Contains(err.Error(), "no repository path") {
			t.Errorf("Error should mention 'no repository path', got: %v", err)
		}
	})

	t.Run("non-existent tracker file returns error", func(t *testing.T) {
		t.Parallel()

		_, err := loadTracker("/nonexistent/path")
		if err == nil {
			t.Error("loadTracker with non-existent path should return error")
		}
	})
}

// TestLoadTrackerCmd tests tracker loading command.
func TestLoadTrackerCmd(t *testing.T) {
	t.Parallel()

	cmd := loadTrackerCmd("/test/path")
	if cmd == nil {
		t.Fatal("loadTrackerCmd should return non-nil command")
	}

	// Execute the command to verify it returns correct message type
	msg := cmd()
	if _, ok := msg.(trackerLoadedMsg); !ok {
		t.Errorf("Command should return trackerLoadedMsg, got %T", msg)
	}
}

// TestRenderFeatureList tests feature list rendering.
func TestRenderFeatureList(t *testing.T) {
	t.Parallel()

	tracker := &Tracker{
		Features: []TrackerFeature{
			{
				ID:         "F001",
				Name:       "Test Feature",
				Priority:   "high",
				Complexity: "M",
				Status:     "in_progress",
				Tasks: []struct {
					ID          string `json:"id"`
					Description string `json:"description"`
					Status      string `json:"status"`
				}{
					{Status: "completed"},
					{Status: "pending"},
				},
			},
		},
	}

	var b strings.Builder
	renderFeatureList(&b, tracker)
	output := b.String()

	// Verify feature information is shown
	if !strings.Contains(output, "F001") {
		t.Error("Feature list should show feature ID")
	}
	if !strings.Contains(output, "Test Feature") {
		t.Error("Feature list should show feature name")
	}
	if !strings.Contains(output, "[HIGH]") {
		t.Error("Feature list should show priority badge")
	}
	if !strings.Contains(output, "Tasks:") {
		t.Error("Feature list should show task summary for in-progress features")
	}
}

// TestRenderProgressFooter tests progress view footer rendering.
func TestRenderProgressFooter(t *testing.T) {
	t.Parallel()

	m := newModelForSettingsTest()

	var b strings.Builder
	renderProgressFooter(&b, m)
	output := b.String()

	// Verify help text is present
	if !strings.Contains(output, "refresh") {
		t.Error("Progress footer should mention refresh")
	}
	if !strings.Contains(output, "quit") {
		t.Error("Progress footer should mention quit")
	}
}
