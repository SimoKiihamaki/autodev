package tui

import (
	"strings"
)

// renderPRDView renders the PRD selection and preview tab.
func renderPRDView(b *strings.Builder, m model) {
	b.WriteString(sectionTitle.Render("PRD Selection & Preview") + "\n")

	// Left pane: file list
	leftContent := m.prdList.View()

	// Right pane: markdown preview
	var rightContent string
	if m.selectedPRD != "" {
		previewBox := NewBorderedBox("Preview", m.prdPreview.View())
		rightContent = previewBox.Render()
	} else {
		rightContent = helpStyle.Render("Select a PRD to preview its contents...")
	}

	// Render split pane
	pane := NewSplitPane(leftContent, rightContent, m.prdPaneRatio)
	b.WriteString(pane.Render(m.termWidth) + "\n")

	// Selection info below the split pane
	renderPRDSelectionInfo(b, m)

	b.WriteString(renderContextualFooter(tabIDPRD, m.keys) + "\n")
}

// renderPRDSelectionInfo renders the selected PRD and tags info.
func renderPRDSelectionInfo(b *strings.Builder, m model) {
	if m.selectedPRD != "" {
		b.WriteString(okStyle.Render("Selected: "+abbreviatePath(m.selectedPRD)) + "\n")
	} else {
		b.WriteString(errorStyle.Render("No PRD selected") + "\n")
	}
	if len(m.tags) > 0 {
		b.WriteString("Tags: " + strings.Join(m.tags, ", ") + "\n")
	}
}
